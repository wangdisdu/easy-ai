from __future__ import annotations

import json
import math
import time
from typing import Any

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.db.schema import TbApp, TbAppLog
from app.model.observability_model import (
    AppHealthRow,
    AppTrendSeries,
    ErrorAppRow,
    ModelTokenRow,
    OverviewStats,
    RecentRequestRow,
    StatDelta,
    TrendResp,
)

# 趋势图默认参数：2 小时一个桶，共 12 个点
_BUCKET_MS = 2 * 60 * 60 * 1000
_BUCKET_COUNT = 12
# 应用健康度排行的趋势 SparkLine 点数
_HEALTH_TREND_POINTS = 7

# 5 个固定展示色，对应 Top 5 应用
_APP_COLORS = ["#3B82F6", "#06B6D4", "#F59E0B", "#10B981", "#8B5CF6"]


class ObservabilityService:
    """可观测性总览聚合查询。数据源：tb_app_log。"""

    # ══════════════════════════════════
    # 核心指标
    # ══════════════════════════════════

    def get_overview_stats(self, db: Session, *, from_ms: int, to_ms: int) -> OverviewStats:
        window = to_ms - from_ms
        prev_from = from_ms - window
        prev_to = from_ms

        current = self._aggregate_basic(db, from_ms, to_ms)
        previous = self._aggregate_basic(db, prev_from, prev_to)

        total = current["total"]
        prev_total = previous["total"]
        success = current["success"]
        fail = total - success
        success_rate = (success / total * 100) if total else 0.0
        prev_success_rate = (previous["success"] / prev_total * 100) if prev_total else 0.0

        p95 = self._p95_latency(db, from_ms, to_ms)
        prev_p95 = self._p95_latency(db, prev_from, prev_to)

        tokens = current["tokens"]
        prev_tokens = previous["tokens"]

        return OverviewStats(
            total_requests=StatDelta(
                value=total,
                compare=prev_total,
                delta_pct=_pct_delta(total, prev_total),
                sub_label=f"较上一周期 {_delta_label(total, prev_total)}",
            ),
            success_rate=StatDelta(
                value=round(success_rate, 2),
                compare=round(prev_success_rate, 2),
                delta_pct=_pct_delta(success_rate, prev_success_rate),
                sub_label=f"失败 {fail} 次",
            ),
            p95_latency_ms=StatDelta(
                value=p95,
                compare=prev_p95,
                delta_pct=_pct_delta(p95, prev_p95),
                sub_label=f"较上一周期 {_delta_label(p95, prev_p95)}",
            ),
            total_tokens=StatDelta(
                value=tokens,
                compare=prev_tokens,
                delta_pct=_pct_delta(tokens, prev_tokens),
                sub_label="费用 -",  # P0 阶段不计算费用
            ),
        )

    def _aggregate_basic(self, db: Session, from_ms: int, to_ms: int) -> dict[str, int]:
        row = db.execute(
            select(
                func.count(TbAppLog.id),
                func.coalesce(func.sum(TbAppLog.success), 0),
                func.coalesce(func.sum(TbAppLog.total_tokens), 0),
            ).where(TbAppLog.create_time >= from_ms, TbAppLog.create_time < to_ms)
        ).one()
        return {"total": int(row[0] or 0), "success": int(row[1] or 0), "tokens": int(row[2] or 0)}

    def _p95_latency(self, db: Session, from_ms: int, to_ms: int) -> int | None:
        """应用层近似 P95：拉取全部 latency_ms 排序取第 95 分位。"""
        rows = db.scalars(
            select(TbAppLog.latency_ms)
            .where(
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.latency_ms.isnot(None),
            )
            .order_by(TbAppLog.latency_ms)
            .limit(10000)
        ).all()
        if not rows:
            return None
        n = len(rows)
        idx = min(n - 1, math.ceil(n * 0.95) - 1)
        return int(rows[idx])

    # ══════════════════════════════════
    # 调用量趋势
    # ══════════════════════════════════

    def get_trend(self, db: Session, *, from_ms: int, to_ms: int, top: int = 5) -> TrendResp:
        bucket_ms = _BUCKET_MS
        bucket_count = max(1, (to_ms - from_ms + bucket_ms - 1) // bucket_ms)

        labels: list[str] = []
        bucket_starts: list[int] = []
        for i in range(bucket_count):
            start = from_ms + i * bucket_ms
            bucket_starts.append(start)
            t = time.localtime(start / 1000)
            labels.append(f"{t.tm_hour:02d}")

        # 1) 查询 Top N 应用 ID（按调用量降序）
        top_app_rows = db.execute(
            select(TbAppLog.app_id, func.count(TbAppLog.id).label("c"))
            .where(
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.app_id.isnot(None),
            )
            .group_by(TbAppLog.app_id)
            .order_by(desc("c"))
            .limit(top)
        ).all()
        top_app_ids = [int(r[0]) for r in top_app_rows]

        # 2) 按桶 + app_id 聚合
        bucket_expr = ((TbAppLog.create_time - from_ms) / bucket_ms).label("bucket")
        per_app_buckets: dict[int, list[int]] = {
            app_id: [0] * bucket_count for app_id in top_app_ids
        }
        total_buckets = [0] * bucket_count

        all_rows = db.execute(
            select(TbAppLog.app_id, bucket_expr, func.count(TbAppLog.id))
            .where(TbAppLog.create_time >= from_ms, TbAppLog.create_time < to_ms)
            .group_by(TbAppLog.app_id, "bucket")
        ).all()
        for row in all_rows:
            app_id_val, bucket_idx, cnt = row
            idx = int(bucket_idx) if bucket_idx is not None else 0
            if idx < 0 or idx >= bucket_count:
                continue
            total_buckets[idx] += int(cnt)
            if app_id_val is not None and int(app_id_val) in per_app_buckets:
                per_app_buckets[int(app_id_val)][idx] += int(cnt)

        # 3) 补充应用名
        app_map = _load_app_map(db, top_app_ids)
        apps: list[AppTrendSeries] = []
        for i, app_id in enumerate(top_app_ids):
            info = app_map.get(app_id)
            apps.append(
                AppTrendSeries(
                    app_id=str(app_id),
                    app_name=info.name if info else f"应用 {app_id}",
                    color=_APP_COLORS[i % len(_APP_COLORS)],
                    data=per_app_buckets[app_id],
                )
            )

        return TrendResp(labels=labels, total=total_buckets, apps=apps)

    # ══════════════════════════════════
    # Token 按模型
    # ══════════════════════════════════

    def get_tokens_by_model(self, db: Session, *, from_ms: int, to_ms: int) -> list[ModelTokenRow]:
        rows = db.execute(
            select(
                TbAppLog.model,
                func.coalesce(func.sum(TbAppLog.total_tokens), 0),
                func.coalesce(func.sum(TbAppLog.input_tokens), 0),
                func.coalesce(func.sum(TbAppLog.output_tokens), 0),
            )
            .where(
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.model.isnot(None),
                TbAppLog.total_tokens.isnot(None),
            )
            .group_by(TbAppLog.model)
            .order_by(desc(func.sum(TbAppLog.total_tokens)))
        ).all()
        return [
            ModelTokenRow(
                model=str(r[0]),
                total_tokens=int(r[1] or 0),
                input_tokens=int(r[2] or 0),
                output_tokens=int(r[3] or 0),
                cost=None,
            )
            for r in rows
        ]

    # ══════════════════════════════════
    # 应用健康度排行
    # ══════════════════════════════════

    def get_app_health(
        self,
        db: Session,
        *,
        from_ms: int,
        to_ms: int,
        sort: str = "calls",
        limit: int = 20,
    ) -> list[AppHealthRow]:
        success_case = case((TbAppLog.success == 1, 1), else_=0)
        rows = db.execute(
            select(
                TbAppLog.app_id,
                func.count(TbAppLog.id),
                func.coalesce(func.sum(success_case), 0),
                func.coalesce(func.avg(TbAppLog.latency_ms), 0),
                func.coalesce(func.sum(TbAppLog.total_tokens), 0),
            )
            .where(
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.app_id.isnot(None),
            )
            .group_by(TbAppLog.app_id)
        ).all()

        app_ids = [int(r[0]) for r in rows]
        app_map = _load_app_map(db, app_ids)

        # 每个应用的 P95（应用层近似）
        p95_map: dict[int, int | None] = {
            app_id: self._p95_latency_for_app(db, app_id, from_ms, to_ms) for app_id in app_ids
        }

        # 每个应用的趋势（最近 N 个时间点）
        trend_map = self._app_trend_map(db, app_ids, from_ms, to_ms, _HEALTH_TREND_POINTS)

        result: list[AppHealthRow] = []
        for r in rows:
            app_id = int(r[0])
            calls = int(r[1] or 0)
            success = int(r[2] or 0)
            avg_latency = float(r[3] or 0)
            tokens = int(r[4] or 0)
            success_rate = (success / calls * 100) if calls else 0.0
            info = app_map.get(app_id)
            result.append(
                AppHealthRow(
                    app_id=str(app_id),
                    app_name=info.name if info else f"应用 {app_id}",
                    app_type=info.app_type if info else "-",
                    calls=calls,
                    success_rate=round(success_rate, 2),
                    p95_latency_ms=p95_map.get(app_id),
                    avg_latency_ms=int(avg_latency) if avg_latency else None,
                    total_tokens=tokens,
                    feedback_rate=None,
                    trend=trend_map.get(app_id, [0] * _HEALTH_TREND_POINTS),
                )
            )

        if sort == "calls":
            result.sort(key=lambda x: x.calls, reverse=True)
        elif sort == "success_rate":
            result.sort(key=lambda x: x.success_rate)
        # feedback_rate 维度在 P0 阶段无数据，保持原顺序
        return result[:limit]

    def _p95_latency_for_app(
        self, db: Session, app_id: int, from_ms: int, to_ms: int
    ) -> int | None:
        rows = db.scalars(
            select(TbAppLog.latency_ms)
            .where(
                TbAppLog.app_id == app_id,
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.latency_ms.isnot(None),
            )
            .order_by(TbAppLog.latency_ms)
            .limit(5000)
        ).all()
        if not rows:
            return None
        n = len(rows)
        idx = min(n - 1, math.ceil(n * 0.95) - 1)
        return int(rows[idx])

    def _app_trend_map(
        self,
        db: Session,
        app_ids: list[int],
        from_ms: int,
        to_ms: int,
        points: int,
    ) -> dict[int, list[int]]:
        if not app_ids:
            return {}
        bucket_ms = max(1, (to_ms - from_ms) // points)
        bucket_expr = ((TbAppLog.create_time - from_ms) / bucket_ms).label("bucket")
        rows = db.execute(
            select(TbAppLog.app_id, bucket_expr, func.count(TbAppLog.id))
            .where(
                TbAppLog.app_id.in_(app_ids),
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
            )
            .group_by(TbAppLog.app_id, "bucket")
        ).all()
        result: dict[int, list[int]] = {app_id: [0] * points for app_id in app_ids}
        for app_id_val, bucket_idx, cnt in rows:
            if app_id_val is None:
                continue
            idx = int(bucket_idx) if bucket_idx is not None else 0
            if idx < 0 or idx >= points:
                continue
            result[int(app_id_val)][idx] += int(cnt)
        return result

    # ══════════════════════════════════
    # 错误率排行
    # ══════════════════════════════════

    def get_errors_by_app(
        self, db: Session, *, from_ms: int, to_ms: int, limit: int = 20
    ) -> list[ErrorAppRow]:
        fail_case = case((TbAppLog.success == 0, 1), else_=0)
        rows = db.execute(
            select(
                TbAppLog.app_id,
                func.count(TbAppLog.id),
                func.coalesce(func.sum(fail_case), 0),
            )
            .where(
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.app_id.isnot(None),
            )
            .group_by(TbAppLog.app_id)
        ).all()

        app_ids = [int(r[0]) for r in rows]
        app_map = _load_app_map(db, app_ids)

        result: list[ErrorAppRow] = []
        for r in rows:
            app_id = int(r[0])
            calls = int(r[1] or 0)
            errors = int(r[2] or 0)
            if errors == 0:
                continue
            rate = (errors / calls * 100) if calls else 0.0
            info = app_map.get(app_id)
            result.append(
                ErrorAppRow(
                    app_id=str(app_id),
                    app_name=info.name if info else f"应用 {app_id}",
                    app_type=info.app_type if info else "-",
                    errors=errors,
                    error_rate=round(rate, 2),
                    top_error=None,
                )
            )
        result.sort(key=lambda x: x.error_rate, reverse=True)
        return result[:limit]

    # ══════════════════════════════════
    # 最近请求
    # ══════════════════════════════════

    def get_recent_requests(self, db: Session, *, limit: int = 20) -> list[RecentRequestRow]:
        rows = db.scalars(select(TbAppLog).order_by(desc(TbAppLog.create_time)).limit(limit)).all()
        app_ids = [int(r.app_id) for r in rows if r.app_id is not None]
        app_map = _load_app_map(db, app_ids)

        result: list[RecentRequestRow] = []
        for r in rows:
            info = app_map.get(int(r.app_id)) if r.app_id is not None else None
            result.append(
                RecentRequestRow(
                    id=str(r.id),
                    app_id=str(r.app_id) if r.app_id is not None else None,
                    app_name=info.name if info else None,
                    app_type=info.app_type if info else r.app_type,
                    user_id=str(r.create_user) if r.create_user is not None else None,
                    preview=_extract_preview(r.request_payload),
                    latency_ms=r.latency_ms,
                    total_tokens=r.total_tokens,
                    success=bool(r.success),
                    create_time=r.create_time,
                    langfuse_trace_id=r.langfuse_trace_id,
                    feedback=None,
                )
            )
        return result


# ══════════════════════════════════
# 工具函数
# ══════════════════════════════════


class _AppInfo:
    __slots__ = ("name", "app_type")

    def __init__(self, name: str, app_type: str) -> None:
        self.name = name
        self.app_type = app_type


def _load_app_map(db: Session, app_ids: list[int]) -> dict[int, _AppInfo]:
    if not app_ids:
        return {}
    rows = db.execute(
        select(TbApp.id, TbApp.name, TbApp.app_type).where(TbApp.id.in_(app_ids))
    ).all()
    return {int(r[0]): _AppInfo(name=str(r[1]), app_type=str(r[2])) for r in rows}


def _pct_delta(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _delta_label(current: float | int | None, previous: float | int | None) -> str:
    pct = _pct_delta(current, previous)
    if pct is None:
        return "-"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct}%"


def _extract_preview(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        payload: Any = json.loads(raw)
    except ValueError:
        return _truncate(str(raw))
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            for msg in reversed(messages):
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") == "user" or msg.get("type") == "human":
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        return _truncate(content)
            if messages:
                last = messages[-1]
                if isinstance(last, dict):
                    content = last.get("content")
                    if isinstance(content, str):
                        return _truncate(content)
        for key in ("query", "question", "prompt", "input"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return _truncate(val)
    return _truncate(json.dumps(payload, ensure_ascii=False))


def _truncate(text: str, max_len: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) > max_len:
        return normalized[:max_len] + "…"
    return normalized
