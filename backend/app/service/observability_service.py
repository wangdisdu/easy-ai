from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.schema import TbApp, TbAppLog, TbAppMetricMinute
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
from app.service.metric_rollup_service import (
    MetricRollupService,
    merge_histograms,
    parse_histogram,
    percentile_from_histogram,
)

# 趋势图默认参数：2 小时一个桶
_BUCKET_MS = 2 * 60 * 60 * 1000
# 应用健康度排行的趋势 SparkLine 点数
_HEALTH_TREND_POINTS = 7

# 5 个固定展示色，对应 Top 5 应用
_APP_COLORS = ["#3B82F6", "#06B6D4", "#F59E0B", "#10B981", "#8B5CF6"]


class ObservabilityService:
    """可观测性总览聚合查询。

    指标类查询(总览/趋势/健康度/错误率)读预聚合表 tb_app_metric_minute;
    模型维度与请求明细仍读原始表 tb_app_log。详见
    docs/observability-metrics-rollup-design.md。
    """

    def __init__(self) -> None:
        self._rollup = MetricRollupService()

    # ══════════════════════════════════
    # 核心指标
    # ══════════════════════════════════

    def get_overview_stats(self, db: Session, *, from_ms: int, to_ms: int) -> OverviewStats:
        window = to_ms - from_ms
        current = self._sum_rows(self._rollup.fetch_rows(db, from_ms, to_ms))
        previous = self._sum_rows(self._rollup.fetch_rows(db, from_ms - window, from_ms))

        total = current["requests"]
        prev_total = previous["requests"]
        success = current["success"]
        fail = total - success
        success_rate = (success / total * 100) if total else 0.0
        prev_success_rate = (previous["success"] / prev_total * 100) if prev_total else 0.0

        p95 = percentile_from_histogram(current["hist"], 0.95)
        prev_p95 = percentile_from_histogram(previous["hist"], 0.95)

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

    @staticmethod
    def _sum_rows(rows: list[TbAppMetricMinute]) -> dict[str, Any]:
        """把一组分钟桶汇总成标量 + 合并直方图。"""
        return {
            "requests": sum(r.request_count for r in rows),
            "success": sum(r.success_count for r in rows),
            "tokens": sum(r.total_tokens for r in rows),
            "latency_sum": sum(r.latency_sum for r in rows),
            "latency_count": sum(r.latency_count for r in rows),
            "hist": merge_histograms([parse_histogram(r.latency_histogram) for r in rows]),
        }

    # ══════════════════════════════════
    # 调用量趋势
    # ══════════════════════════════════

    def get_trend(self, db: Session, *, from_ms: int, to_ms: int, top: int = 5) -> TrendResp:
        bucket_ms = _BUCKET_MS
        bucket_count = max(1, (to_ms - from_ms + bucket_ms - 1) // bucket_ms)

        labels: list[str] = []
        for i in range(bucket_count):
            start = from_ms + i * bucket_ms
            t = time.localtime(start / 1000)
            labels.append(f"{t.tm_hour:02d}")

        rows = self._rollup.fetch_rows(db, from_ms, to_ms)

        # Top N 应用(按调用量降序，排除无归属应用 app_id=0)
        per_app_total: dict[int, int] = {}
        for r in rows:
            if r.app_id == 0:
                continue
            per_app_total[r.app_id] = per_app_total.get(r.app_id, 0) + r.request_count
        top_app_ids = sorted(per_app_total, key=lambda a: per_app_total[a], reverse=True)[:top]

        per_app_buckets: dict[int, list[int]] = {a: [0] * bucket_count for a in top_app_ids}
        total_buckets = [0] * bucket_count
        for r in rows:
            idx = (r.bucket_start - from_ms) // bucket_ms
            if idx < 0 or idx >= bucket_count:
                continue
            total_buckets[idx] += r.request_count
            if r.app_id in per_app_buckets:
                per_app_buckets[r.app_id][idx] += r.request_count

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
    # Token 按模型（仍读原始表：聚合层无 model 维度）
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
        rows = self._rollup.fetch_rows(db, from_ms, to_ms)
        by_app = _group_by_app(rows)

        trend_bucket_ms = max(1, (to_ms - from_ms) // _HEALTH_TREND_POINTS)
        app_map = _load_app_map(db, list(by_app.keys()))

        result: list[AppHealthRow] = []
        for app_id, app_rows in by_app.items():
            agg = self._sum_rows(app_rows)
            calls = agg["requests"]
            success = agg["success"]
            success_rate = (success / calls * 100) if calls else 0.0
            lat_count = agg["latency_count"]
            avg_latency = (agg["latency_sum"] / lat_count) if lat_count else 0.0

            trend = [0] * _HEALTH_TREND_POINTS
            for r in app_rows:
                idx = (r.bucket_start - from_ms) // trend_bucket_ms
                if 0 <= idx < _HEALTH_TREND_POINTS:
                    trend[idx] += r.request_count

            info = app_map.get(app_id)
            result.append(
                AppHealthRow(
                    app_id=str(app_id),
                    app_name=info.name if info else f"应用 {app_id}",
                    app_type=info.app_type if info else "-",
                    calls=calls,
                    success_rate=round(success_rate, 2),
                    p95_latency_ms=percentile_from_histogram(agg["hist"], 0.95),
                    avg_latency_ms=int(avg_latency) if avg_latency else None,
                    total_tokens=agg["tokens"],
                    feedback_rate=None,
                    trend=trend,
                )
            )

        if sort == "calls":
            result.sort(key=lambda x: x.calls, reverse=True)
        elif sort == "success_rate":
            result.sort(key=lambda x: x.success_rate)
        # feedback_rate 维度在 P0 阶段无数据，保持原顺序
        return result[:limit]

    # ══════════════════════════════════
    # 错误率排行
    # ══════════════════════════════════

    def get_errors_by_app(
        self, db: Session, *, from_ms: int, to_ms: int, limit: int = 20
    ) -> list[ErrorAppRow]:
        rows = self._rollup.fetch_rows(db, from_ms, to_ms)
        by_app = _group_by_app(rows)
        app_map = _load_app_map(db, list(by_app.keys()))

        result: list[ErrorAppRow] = []
        for app_id, app_rows in by_app.items():
            calls = sum(r.request_count for r in app_rows)
            errors = calls - sum(r.success_count for r in app_rows)
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
    # 最近请求（仍读原始表：明细数据无法聚合）
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


def _group_by_app(rows: list[TbAppMetricMinute]) -> dict[int, list[TbAppMetricMinute]]:
    """按 app_id 分组,排除无归属应用(app_id=0)。"""
    grouped: dict[int, list[TbAppMetricMinute]] = {}
    for r in rows:
        if r.app_id == 0:
            continue
        grouped.setdefault(r.app_id, []).append(r)
    return grouped


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
