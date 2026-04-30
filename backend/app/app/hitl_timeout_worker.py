"""HITL 超时回收：扫 tb_tool_audit 找出过期未响应的 hitl_required，按 reject 续跑 agent。

复刻 CheckpointPurger 的进程内定时模式：
- 每个 worker 进程都会启动它，靠 Postgres advisory lock 互斥每条记录避免重复 reject
- _run_once 一批拿出已过 deadline 的行，逐条加锁、续跑、写 hitl_timeout 审计、放锁
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.session import SessionLocal
from app.model.conversation_model import HitlResponseReq
from app.service.conversation_service import ConversationService
from app.service.policy_service import PolicyAuditWriter

logger = logging.getLogger(__name__)


class HitlTimeoutWorker:
    """定时检查并回收过期的 HITL 暂停。"""

    def __init__(
        self,
        *,
        interval_seconds: int,
        default_timeout_seconds: int,
        batch_size: int = 20,
    ) -> None:
        self._interval = interval_seconds
        self._default_timeout = default_timeout_seconds
        self._batch_size = batch_size
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        # 每个 worker 持有一份 ConversationService；复用其 respond_hitl_stream 续跑。
        self._service = ConversationService(SnowflakeGenerator(settings.snowflake_worker_id))

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="hitl-timeout-worker")
        logger.info(
            "hitl timeout worker started: interval=%ds default_timeout=%ds",
            self._interval,
            self._default_timeout,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except TimeoutError:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        logger.info("hitl timeout worker stopped")

    async def _loop(self) -> None:
        # 启动后延迟 30s 让 web 全部就绪再扫；避免冷启动期间误触发
        if await self._sleep_or_stop(30):
            return
        while not self._stop_event.is_set():
            try:
                await self._run_once()
            except Exception:
                logger.exception("hitl timeout worker iteration failed")
            if await self._sleep_or_stop(self._interval):
                return

    async def _sleep_or_stop(self, seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False

    async def _run_once(self) -> None:
        rows = self._fetch_expired()
        if not rows:
            return
        logger.info("hitl timeout worker: %d expired hitls to reject", len(rows))
        for row in rows:
            await self._reject_one(row)

    def _fetch_expired(self) -> list[dict]:
        """SQL 选出 deadline 已过且无后续响应的 hitl_required 审计行。"""
        sql = text("""
            SELECT
                a.id            AS audit_id,
                a.tool_id       AS tool_id,
                a.run_id        AS run_id,
                a.user_id       AS user_id,
                a.app_id        AS app_id,
                a.create_time   AS create_time,
                COALESCE(t.hitl_timeout_seconds, :default_timeout) AS timeout_s
            FROM tb_tool_audit a
            LEFT JOIN tb_tool t ON t.id = a.tool_id
            WHERE a.event_type = 'hitl_required'
              AND a.run_id IS NOT NULL
              AND a.create_time
                  + COALESCE(t.hitl_timeout_seconds, :default_timeout) * 1000
                  < :now_ms
              AND NOT EXISTS (
                  SELECT 1 FROM tb_tool_audit r
                  WHERE r.run_id = a.run_id
                    AND COALESCE(r.tool_id, 0) = COALESCE(a.tool_id, 0)
                    AND r.event_type IN (
                        'hitl_confirmed', 'hitl_modified',
                        'hitl_rejected', 'hitl_timeout'
                    )
                    AND r.id > a.id
              )
            ORDER BY a.id
            LIMIT :batch
            """)
        import time

        now_ms = int(time.time() * 1000)
        db = SessionLocal()
        try:
            result = db.execute(
                sql,
                {
                    "default_timeout": self._default_timeout,
                    "now_ms": now_ms,
                    "batch": self._batch_size,
                },
            )
            return [dict(r._mapping) for r in result]
        finally:
            db.close()

    async def _reject_one(self, row: dict) -> None:
        audit_id = int(row["audit_id"])
        run_id = str(row["run_id"]) if row["run_id"] is not None else None
        if not run_id:
            return
        try:
            conv_id = int(run_id)
        except ValueError:
            logger.warning("hitl timeout: skipping non-numeric run_id=%r", run_id)
            return
        user_id_raw = row.get("user_id")
        try:
            user_id = int(user_id_raw) if user_id_raw is not None else 0
        except (TypeError, ValueError):
            user_id = 0
        tool_id_raw = row.get("tool_id")
        tool_id_int = int(tool_id_raw) if tool_id_raw is not None else None
        app_id_raw = row.get("app_id")
        app_id_int = int(app_id_raw) if app_id_raw is not None else None

        # 抢锁；同一行同时只允许一个 worker 处理
        lock_db = SessionLocal()
        try:
            got_lock = lock_db.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": audit_id},
            ).scalar()
            if not got_lock:
                logger.debug("hitl timeout: audit %s held by other worker", audit_id)
                return
            try:
                # 1. 先写 hitl_timeout 审计标记。即便后续 resume 失败，这条标记
                #    也已让下一轮扫描跳过该行（因为 NOT EXISTS 会命中后续 r.id > a.id）。
                self._write_timeout_audit(
                    audit_id, conv_id, run_id, user_id, app_id_int, tool_id_int
                )
                # 2. 触发 reject 续跑。失败仅记日志，避免阻塞其它行。
                await self._drive_reject(conv_id, user_id)
            finally:
                lock_db.execute(
                    text("SELECT pg_advisory_unlock(:k)"),
                    {"k": audit_id},
                )
        except Exception:
            logger.exception("hitl timeout: failed to reject audit_id=%s", audit_id)
        finally:
            lock_db.close()

    def _write_timeout_audit(
        self,
        original_audit_id: int,
        conv_id: int,
        run_id: str,
        user_id: int,
        app_id: int | None,
        tool_id: int | None,
    ) -> None:
        writer = PolicyAuditWriter(SnowflakeGenerator(settings.snowflake_worker_id))
        db = SessionLocal()
        try:
            writer.write(
                db,
                event_type="hitl_timeout",
                tool_id=tool_id,
                conversation_id=conv_id,
                run_id=run_id,
                user_id=user_id or None,
                app_id=app_id,
                parameters={},
                decision_reason=f"timeout reject (origin audit_id={original_audit_id})",
                matched_rule_id=None,
            )
        except Exception:
            logger.exception("hitl timeout audit write failed conv=%s", conv_id)
        finally:
            db.close()

    async def _drive_reject(self, conv_id: int, user_id: int) -> None:
        """用伪造的 RequestContext 调 respond_hitl_stream(reject) 续跑 agent。"""
        import time

        if user_id <= 0:
            logger.warning(
                "hitl timeout: missing original user_id for conv=%s; skipping resume",
                conv_id,
            )
            return
        req_ctx = RequestContext(
            user_id=user_id,
            client_ip=None,
            request_time_ms=int(time.time() * 1000),
        )
        # respond_hitl_stream 是 async generator；开 session 给它，遍历完不留 chunks
        db = SessionLocal()
        try:
            gen = self._service.respond_hitl_stream(
                db,
                conv_id,
                "timeout",
                HitlResponseReq(action="reject"),
                req_ctx,
            )
            async for _chunk in gen:
                pass
        except ServiceError as exc:
            # 会话被删 / checkpoint 已清 / 应用类型变更等业务态：audit 已留痕，不再 resume，
            # 也不抛 traceback——这些都是合规的"暂停一直没响应到清理时刻"。
            logger.info(
                "hitl timeout: skipping resume for conv=%s (%s)",
                conv_id,
                exc.msg,
            )
        except Exception:
            logger.exception("hitl timeout: respond_hitl_stream failed conv=%s", conv_id)
        finally:
            with contextlib.suppress(Exception):
                db.close()
