from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.app.agent_app import AgentApp
from app.app.app_runtime import AppRuntime
from app.app.checkpointer_factory import get_checkpointer_factory
from app.app.llm_app import LlmApp
from app.app.rag_app import RagApp
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbApp, TbConversation, TbConversationMessage, TbSessionAudit
from app.model.conversation_model import (
    ConversationCreateReq,
    ConversationMessageResp,
    ConversationResp,
    ConversationUpdateReq,
    HitlResponseReq,
)
from app.model.open_model import AgentRunRequest, LlmAppRunReq, ModelGatewayChatMessage

logger = logging.getLogger(__name__)

MAX_CONTEXT_TURNS = 20


class ConversationService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._app_runtime = AppRuntime()
        self._llm_app = LlmApp(app_runtime=self._app_runtime)
        self._agent_app = AgentApp(app_runtime=self._app_runtime)
        self._rag_app = RagApp(app_runtime=self._app_runtime)

    # ── CRUD ──

    def create_conversation(
        self,
        db: Session,
        req: ConversationCreateReq,
        req_ctx: RequestContext,
    ) -> ConversationResp:
        app_id = int(req.app_id)
        app = db.get(TbApp, app_id)
        if not app:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        if app.app_status != "published":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not published")

        now = req_ctx.request_time_ms
        entity = TbConversation(
            id=self._id_generator.next_id(),
            user_id=req_ctx.user_id,
            app_id=app_id,
            title="",
            status="active",
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return self._to_conversation_resp(entity, app)

    def page_conversations(
        self,
        db: Session,
        user_id: int,
        page_no: int,
        page_size: int,
    ) -> tuple[list[ConversationResp], int]:
        base = select(TbConversation).where(
            TbConversation.user_id == user_id,
            TbConversation.status == "active",
        )
        total = db.scalar(select(func.count()).select_from(base.subquery()))

        rows = db.scalars(
            base.order_by(desc(TbConversation.update_time))
            .offset((page_no - 1) * page_size)
            .limit(page_size)
        ).all()
        if not rows:
            return [], total or 0

        app_ids = list({conv.app_id for conv in rows})
        app_map = {
            app.id: app for app in db.scalars(select(TbApp).where(TbApp.id.in_(app_ids))).all()
        }

        conversation_ids = [conv.id for conv in rows]
        latest_ranked = (
            select(
                TbConversationMessage.conversation_id.label("conversation_id"),
                TbConversationMessage.content.label("content"),
                func.row_number()
                .over(
                    partition_by=TbConversationMessage.conversation_id,
                    order_by=(
                        desc(TbConversationMessage.create_time),
                        desc(TbConversationMessage.id),
                    ),
                )
                .label("rn"),
            )
            .where(TbConversationMessage.conversation_id.in_(conversation_ids))
            .subquery()
        )
        latest_message_map = {
            int(row.conversation_id): row.content
            for row in db.execute(
                select(latest_ranked.c.conversation_id, latest_ranked.c.content).where(
                    latest_ranked.c.rn == 1
                )
            ).all()
        }

        result: list[ConversationResp] = []
        for conv in rows:
            app = app_map.get(conv.app_id)
            resp = self._to_conversation_resp(conv, app)
            last_msg = latest_message_map.get(conv.id)
            resp.last_message = _truncate(last_msg, 100) if last_msg else None
            result.append(resp)
        return result, total or 0

    def get_conversation(self, db: Session, conversation_id: int, user_id: int) -> ConversationResp:
        conv = self._get_own_conversation(db, conversation_id, user_id)
        app = db.get(TbApp, conv.app_id)
        return self._to_conversation_resp(conv, app)

    def update_conversation(
        self,
        db: Session,
        conversation_id: int,
        req: ConversationUpdateReq,
        req_ctx: RequestContext,
    ) -> ConversationResp:
        conv = self._get_own_conversation(db, conversation_id, req_ctx.user_id)
        if req.title is not None:
            conv.title = req.title
        if req.status is not None:
            conv.status = req.status
        conv.update_time = req_ctx.request_time_ms
        conv.update_user = req_ctx.user_id
        db.commit()
        db.refresh(conv)
        app = db.get(TbApp, conv.app_id)
        return self._to_conversation_resp(conv, app)

    async def delete_conversation(self, db: Session, conversation_id: int, user_id: int) -> None:
        conv = self._get_own_conversation(db, conversation_id, user_id)
        thread_id = conv.thread_id
        # 先删 checkpoint，再删业务行：checkpoint 删失败时整事务作废，避免出现
        # "业务行没了 / checkpoint 残留无主"，purge 也无法回收。
        if thread_id:
            await self._delete_checkpoint_thread(thread_id)
        db.execute(
            delete(TbConversationMessage).where(TbConversationMessage.conversation_id == conv.id)
        )
        db.execute(delete(TbSessionAudit).where(TbSessionAudit.conversation_id == conv.id))
        db.delete(conv)
        db.commit()

    async def reset_conversation(
        self,
        db: Session,
        conversation_id: int,
        user_id: int,
        req_ctx: RequestContext,
    ) -> None:
        """清运行态（checkpoint），保留业务消息和反馈。

        重置后下一轮发消息会因 prior_count > 1 走降级重建——历史还在，
        但 todos / 虚拟工作文件 / 工具中间态丢失。
        """
        conv = self._get_own_conversation(db, conversation_id, user_id)
        thread_id = conv.thread_id
        if not thread_id:
            return
        await self._delete_checkpoint_thread(thread_id)
        conv.checkpoint_status = "active"
        db.add(
            TbSessionAudit(
                id=self._id_generator.next_id(),
                conversation_id=conversation_id,
                event_type="checkpoint_reset",
                payload=None,
                create_time=req_ctx.request_time_ms,
            )
        )
        db.commit()

    async def purge_expired_checkpoints(
        self,
        db: Session,
        ttl_days: int = 30,
        *,
        now_ms: int | None = None,
    ) -> int:
        """清理长时间未更新会话的 checkpoint，返回被清理 thread 数。

        当前以 `update_time` 不活跃为代理条件；待会话归档状态机落地后改成
        archived + ttl_days 触发（见 long-session-design 后续 PR）。
        """
        current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        cutoff_ms = current_ms - ttl_days * 86_400_000
        rows = db.scalars(
            select(TbConversation).where(
                TbConversation.update_time < cutoff_ms,
                TbConversation.thread_id.is_not(None),
                TbConversation.checkpoint_status != "purged",
            )
        ).all()
        purged = 0
        for conv in rows:
            try:
                await self._delete_checkpoint_thread(conv.thread_id)
            except Exception:
                logger.exception("purge: failed to delete checkpoint thread %s", conv.thread_id)
                continue
            conv.checkpoint_status = "purged"
            db.add(
                TbSessionAudit(
                    id=self._id_generator.next_id(),
                    conversation_id=conv.id,
                    event_type="checkpoint_purged",
                    payload=json.dumps({"thread_id": conv.thread_id}),
                    create_time=current_ms,
                )
            )
            purged += 1
        if purged > 0:
            db.commit()
        return purged

    async def cascade_delete_user_checkpoints(self, db: Session, user_id: int) -> int:
        """被遗忘权 / 用户删除时调用：清掉该用户所有会话的 checkpoint。

        只删 checkpoint 不删业务消息，业务侧的级联由调用方决定。
        返回被清理 thread 数。
        """
        thread_ids = [
            tid
            for tid in db.scalars(
                select(TbConversation.thread_id).where(
                    TbConversation.user_id == user_id,
                    TbConversation.thread_id.is_not(None),
                )
            ).all()
            if tid
        ]
        deleted = 0
        for tid in thread_ids:
            try:
                await self._delete_checkpoint_thread(tid)
                deleted += 1
            except Exception:
                logger.exception("rtb-forgotten: failed to delete thread %s", tid)
        return deleted

    async def _delete_checkpoint_thread(self, thread_id: str) -> None:
        saver = get_checkpointer_factory().get()
        await saver.adelete_thread(thread_id)

    def list_messages(
        self, db: Session, conversation_id: int, user_id: int
    ) -> list[ConversationMessageResp]:
        self._get_own_conversation(db, conversation_id, user_id)
        rows = db.scalars(
            select(TbConversationMessage)
            .where(TbConversationMessage.conversation_id == conversation_id)
            .order_by(TbConversationMessage.create_time)
        ).all()
        return [self._to_message_resp(msg) for msg in rows]

    # ── 流式对话 ──

    async def send_message_stream(
        self,
        db: Session,
        conversation_id: int,
        content: str,
        req_ctx: RequestContext,
    ) -> AsyncGenerator[str, None]:
        from app.db.session import SessionLocal

        conv = self._get_own_conversation(db, conversation_id, req_ctx.user_id)
        app = self._app_runtime.get_app(db, conv.app_id)
        if app.app_type not in ("llm", "agent", "rag"):
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"streaming not supported for app type: {app.app_type}",
            )

        now = req_ctx.request_time_ms

        # 长会话对所有 agent app 默认开启，由 LangGraph Checkpointer 持久化运行态。
        long_session_active = app.app_type == "agent"
        if long_session_active and not conv.thread_id:
            # 首次调用落地 thread_id（与 conversation id 同字面量），之后永不变。
            conv.thread_id = str(conv.id)

        # 保存用户消息
        user_msg = TbConversationMessage(
            id=self._id_generator.next_id(),
            conversation_id=conversation_id,
            role="user",
            content=content,
            create_time=now,
            create_user=req_ctx.user_id,
        )
        db.add(user_msg)

        # 首条用户消息时自动设置标题
        user_msg_count = db.scalar(
            select(func.count()).select_from(
                select(TbConversationMessage)
                .where(
                    TbConversationMessage.conversation_id == conversation_id,
                    TbConversationMessage.role == "user",
                )
                .subquery()
            )
        )
        if (user_msg_count or 0) == 0:
            conv.title = _truncate(content, 30)

        conv.update_time = now
        conv.update_user = req_ctx.user_id
        db.commit()

        # 决定本轮的消息输入协议：
        #   - 长会话关：沿用全量历史
        #   - 长会话开 + checkpoint 命中：只传新这一句，历史由 saver 恢复
        #   - 长会话开 + checkpoint 缺失但已有历史：降级重建，写 audit
        #   - 长会话开 + 首次调用：只传新这一句（checkpoint 从此生成）
        thread_id_for_call: str | None = None
        use_checkpoint_for_call = False
        degraded_for_call = False

        if long_session_active:
            thread_id_for_call = conv.thread_id
            saver = get_checkpointer_factory().get()
            ckpt = await saver.aget_tuple({"configurable": {"thread_id": thread_id_for_call}})

            if ckpt is not None:
                # 正常路径：只传本轮新消息
                messages = [ModelGatewayChatMessage(role="user", content=content)]
            else:
                # checkpoint 缺失。区分"首次调用"与"被清理后真正降级"：
                # 用刚保存完后 tb_conversation_message 中 user/assistant 的总数判断，
                # 1 条说明只有这条新写入的 user_msg，是首次。
                prior_count = (
                    db.scalar(
                        select(func.count())
                        .select_from(TbConversationMessage)
                        .where(
                            TbConversationMessage.conversation_id == conversation_id,
                            TbConversationMessage.role.in_(["user", "assistant"]),
                        )
                    )
                    or 0
                )
                if prior_count <= 1:
                    messages = [ModelGatewayChatMessage(role="user", content=content)]
                else:
                    history_rows = self._load_history_rows(db, conversation_id)
                    messages = [
                        ModelGatewayChatMessage(role=m.role, content=m.content or "")
                        for m in history_rows
                    ]
                    degraded_for_call = True
                    conv.checkpoint_status = "degraded"
                    db.add(
                        TbSessionAudit(
                            id=self._id_generator.next_id(),
                            conversation_id=conversation_id,
                            event_type="checkpoint_rebuilt_from_messages",
                            payload=json.dumps({"history_count": len(history_rows)}),
                            create_time=now,
                        )
                    )
                    db.commit()
            use_checkpoint_for_call = True
        else:
            history_rows = self._load_history_rows(db, conversation_id)
            messages = [
                ModelGatewayChatMessage(role=m.role, content=m.content or "") for m in history_rows
            ]

        # 准备完毕，关闭 session
        app_id = app.id
        app_type = app.app_type
        db.close()

        # 调用应用执行引擎
        if app_type == "llm":
            llm_req = LlmAppRunReq(app_id=app_id, messages=messages)
            inner_gen = self._llm_app.stream(
                db=SessionLocal(),
                req=llm_req,
                req_ctx=req_ctx,
                request_type="chat",
            )
        elif app_type == "rag":
            # RagApp 当前为非真流桥接(asyncio.to_thread 包同步 run),
            # 真 token-level streaming 留给 M2.2
            from app.model.open_model import RagRunRequest

            rag_req = RagRunRequest(app_id=app_id, messages=messages)
            inner_gen = self._rag_app.stream(
                db=SessionLocal(),
                req=rag_req,
                req_ctx=req_ctx,
                request_type="chat",
            )
        else:
            agent_req = AgentRunRequest(
                app_id=app_id,
                messages=messages,
                thread_id=thread_id_for_call,
                use_checkpoint=use_checkpoint_for_call,
                degraded=degraded_for_call,
            )
            inner_gen = self._agent_app.stream(
                db=SessionLocal(),
                req=agent_req,
                req_ctx=req_ctx,
                request_type="chat",
            )

        async for chunk in self._consume_and_save_stream(inner_gen, conversation_id):
            yield chunk

    async def respond_hitl_stream(
        self,
        db: Session,
        conversation_id: int,
        hitl_id: str,
        req: HitlResponseReq,
        req_ctx: RequestContext,
    ) -> AsyncGenerator[str, None]:
        """HITL 用户响应到达后续跑被 interrupt() 暂停的 agent。

        - 校验会话归属、应用类型为 agent
        - 通过 LangGraph 状态校验目标 hitl_id 存在 pending interrupt
        - 调 AgentApp.resume_stream() 透传 SSE
        - 续跑产生的 assistant 文本与工具消息照常入库
        """
        from app.db.session import SessionLocal

        conv = self._get_own_conversation(db, conversation_id, req_ctx.user_id)
        app = self._app_runtime.get_app(db, conv.app_id)
        if app.app_type != "agent":
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                "hitl resume is only supported for agent apps",
            )
        thread_id = conv.thread_id
        if not thread_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "conversation has no active thread")

        saver = get_checkpointer_factory().get()
        ckpt = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})
        if ckpt is None:
            raise ServiceError(ErrorCode.BAD_REQUEST, "no checkpoint to resume from")

        app_id = app.id
        db.close()

        agent_req = AgentRunRequest(
            app_id=app_id,
            messages=[],
            thread_id=thread_id,
            use_checkpoint=True,
            degraded=False,
        )
        hitl_response: dict[str, Any] = {"action": req.action}
        if req.action == "modify" and isinstance(req.parameters, dict):
            hitl_response["parameters"] = req.parameters

        inner_gen = self._agent_app.resume_stream(
            db=SessionLocal(),
            req=agent_req,
            req_ctx=req_ctx,
            hitl_response=hitl_response,
            request_type="chat",
        )

        async for chunk in self._consume_and_save_stream(inner_gen, conversation_id):
            yield chunk

    async def _consume_and_save_stream(
        self,
        inner_gen: AsyncGenerator[str, None],
        conversation_id: int,
    ) -> AsyncGenerator[str, None]:
        """透传 SSE 同时收集 token / 工具调用 / 元数据；在末尾把 assistant + tool 消息持久化。"""
        from app.db.session import SessionLocal

        full_content = ""
        tool_calls: list[dict[str, Any]] = []
        metadata_extra: dict[str, Any] = {}

        try:
            async for chunk in inner_gen:
                if chunk.startswith("event: token\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        token_data = json.loads(data_line)
                        full_content += token_data.get("content", "")
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: tool_call_start\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        tc_data = json.loads(data_line)
                        tool_calls.append(
                            {
                                "tool_call_id": tc_data.get("tool_call_id", ""),
                                "name": tc_data.get("name", ""),
                                "arguments": tc_data.get("arguments"),
                                "status": "running",
                                "result": None,
                            }
                        )
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: tool_call_end\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        tc_data = json.loads(data_line)
                        tc_id = tc_data.get("tool_call_id", "")
                        for tc in tool_calls:
                            if tc["tool_call_id"] == tc_id:
                                tc["result"] = tc_data.get("result", "")
                                tc["status"] = tc_data.get("status", "success")
                                break
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: message_complete\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        mc_data = json.loads(data_line)
                        metadata_extra["usage"] = mc_data.get("usage", {})
                        metadata_extra["sources"] = mc_data.get("sources")
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: done\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        done_data = json.loads(data_line)
                        metadata_extra["latency_ms"] = done_data.get("latency_ms")
                    except (IndexError, json.JSONDecodeError):
                        pass

                yield chunk

        finally:
            if full_content or tool_calls:
                log_db = SessionLocal()
                try:
                    now_ms = int(time.time() * 1000)

                    for tc in tool_calls:
                        tool_msg = TbConversationMessage(
                            id=self._id_generator.next_id(),
                            conversation_id=conversation_id,
                            role="tool",
                            content=tc.get("result") or "",
                            metadata_=json.dumps(
                                {
                                    "tool_name": tc["name"],
                                    "tool_call_id": tc["tool_call_id"],
                                    "arguments": tc.get("arguments"),
                                    "status": tc.get("status", "success"),
                                },
                                ensure_ascii=False,
                            ),
                            create_time=now_ms,
                            create_user=None,
                        )
                        log_db.add(tool_msg)

                    if full_content:
                        ai_msg = TbConversationMessage(
                            id=self._id_generator.next_id(),
                            conversation_id=conversation_id,
                            role="assistant",
                            content=full_content,
                            metadata_=(
                                json.dumps(metadata_extra, ensure_ascii=False)
                                if metadata_extra
                                else None
                            ),
                            create_time=now_ms,
                            create_user=None,
                        )
                        log_db.add(ai_msg)

                    db_conv = log_db.get(TbConversation, conversation_id)
                    if db_conv:
                        db_conv.update_time = now_ms
                    log_db.commit()
                except Exception:
                    logger.exception(
                        "failed to save messages for conversation %s",
                        conversation_id,
                    )
                finally:
                    log_db.close()

    # ── Helpers ──

    def _get_own_conversation(
        self, db: Session, conversation_id: int, user_id: int
    ) -> TbConversation:
        conv = db.get(TbConversation, conversation_id)
        if not conv:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "conversation not found")
        if conv.user_id != user_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "conversation not owned by user")
        return conv

    def _load_history_rows(self, db: Session, conversation_id: int) -> list[TbConversationMessage]:
        """读取对话的 user/assistant 历史消息，按时间序，受 MAX_CONTEXT_TURNS 限制。"""
        rows = db.scalars(
            select(TbConversationMessage)
            .where(
                TbConversationMessage.conversation_id == conversation_id,
                TbConversationMessage.role.in_(["user", "assistant"]),
            )
            .order_by(TbConversationMessage.create_time)
        ).all()
        if len(rows) > MAX_CONTEXT_TURNS * 2:
            rows = rows[-(MAX_CONTEXT_TURNS * 2) :]
        return list(rows)

    def _to_conversation_resp(self, conv: TbConversation, app: TbApp | None) -> ConversationResp:
        return ConversationResp(
            id=str(conv.id),
            app_id=str(conv.app_id),
            app_type=app.app_type if app else "",
            app_name=app.name if app else "",
            title=conv.title or "",
            status=conv.status,
            create_time=conv.create_time,
            update_time=conv.update_time,
        )

    def _to_message_resp(self, msg: TbConversationMessage) -> ConversationMessageResp:
        metadata = None
        if msg.metadata_:
            try:
                metadata = json.loads(msg.metadata_)
            except (ValueError, TypeError):
                metadata = msg.metadata_
        return ConversationMessageResp(
            id=str(msg.id),
            conversation_id=str(msg.conversation_id),
            role=msg.role,
            content=msg.content,
            metadata=metadata,
            create_time=msg.create_time,
        )


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
