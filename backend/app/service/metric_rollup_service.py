"""指标聚合层:把 tb_app_log 预聚合成 tb_app_metric_minute 分钟桶。

被三处复用:
- MetricRollupWorker —— 后台周期任务(回算尾部分钟)
- rebuild() —— 按 tb_app_log 重建任意区间
- ObservabilityService / 告警溯源 —— 通过 fetch_rows() 读聚合数据

详见 docs/observability-metrics-rollup-design.md。
"""

from __future__ import annotations

import json
import math
import time

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.schema import TbAppLog, TbAppMetricMinute

_MINUTE_MS = 60_000

# 延迟直方图区间上界(ms)。边界贴近常用告警阈值(含 6000ms),并向上覆盖到
# 5 分钟以容纳较慢的 agent 调用。共 17 个有界桶 + 1 个溢出桶 = 18 个槽位。
_LATENCY_BUCKETS_MS = [
    50,
    100,
    200,
    300,
    500,
    800,
    1200,
    2000,
    3000,
    5000,
    6000,
    8000,
    15000,
    30000,
    60000,
    120000,
    300000,
]
_HIST_SLOTS = len(_LATENCY_BUCKETS_MS) + 1

# UPSERT 时需覆盖更新的列(主键 bucket_start/app_id 除外)
_UPSERT_COLS = (
    "request_count",
    "success_count",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "latency_count",
    "latency_sum",
    "latency_histogram",
    "update_time",
)


def align_minute(ms: int) -> int:
    """把 Unix 毫秒向下对齐到所在分钟的起点。"""
    return ms // _MINUTE_MS * _MINUTE_MS


def ceil_minute(ms: int) -> int:
    """把 Unix 毫秒向上对齐到分钟边界。已对齐则不变。"""
    return (ms + _MINUTE_MS - 1) // _MINUTE_MS * _MINUTE_MS


# ── 直方图工具 ──


def parse_histogram(raw: str | None) -> list[int]:
    """把存储的 JSON 字符串解析回定长计数数组;非法则返回全零。"""
    try:
        h = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        h = None
    if not isinstance(h, list) or len(h) != _HIST_SLOTS:
        return [0] * _HIST_SLOTS
    return [int(x) for x in h]


def merge_histograms(histograms: list[list[int]]) -> list[int]:
    """逐元素相加多个直方图。"""
    merged = [0] * _HIST_SLOTS
    for h in histograms:
        for i in range(_HIST_SLOTS):
            merged[i] += h[i]
    return merged


def percentile_from_histogram(hist: list[int], p: float) -> int | None:
    """从合并直方图估算分位数(ms)。桶内线性插值,误差不超过桶宽。

    p 取 0-1,例如 0.95。无样本返回 None。
    """
    total = sum(hist)
    if total == 0:
        return None
    rank = math.ceil(total * p)
    cum = 0
    lo = 0
    for i, hi in enumerate(_LATENCY_BUCKETS_MS):
        c = hist[i]
        if cum + c >= rank:
            if c <= 0:
                return int(lo)
            return int(round(lo + (hi - lo) * (rank - cum) / c))
        cum += c
        lo = hi
    # 落入溢出桶:返回最后一个有限边界作为下界估计
    return int(lo)


class MetricRollupService:
    """tb_app_log → tb_app_metric_minute 的聚合与读取。无状态。"""

    # ── 聚合写入 ──

    def roll_up(self, db: Session, from_ms: int, to_ms: int) -> int:
        """把 [from_ms, to_ms) 内的 tb_app_log 聚合成分钟桶并 UPSERT。

        区间按分钟对齐。返回写入的桶数。重跑幂等(按主键覆盖)。
        """
        # 起点向下对齐(含首个不完整桶),终点向上对齐(含末个不完整桶)。
        # worker 传入的 to_ms 已对齐到整分钟,ceil 不改变它 —— 当前分钟仍不参与。
        from_b = align_minute(from_ms)
        to_b = ceil_minute(to_ms)
        if to_b <= from_b:
            return 0

        # 用整数取模直接算出分钟桶起点:bucket_start = create_time - create_time % 60000。
        # 全程整数运算,避开 SQLAlchemy 2.0 真除(/ 得 numeric)与 CAST AS bigint
        # (四舍五入而非截断)两个会把行算进错桶的坑。
        bucket_col = (TbAppLog.create_time - TbAppLog.create_time % _MINUTE_MS).label("b")
        app_col = func.coalesce(TbAppLog.app_id, 0).label("a")

        # 直方图:每槽位一个 FILTER 计数,单次扫描算齐
        hist_cols = []
        lo = 0
        for hi in _LATENCY_BUCKETS_MS:
            hist_cols.append(
                func.count(TbAppLog.id).filter(TbAppLog.latency_ms >= lo, TbAppLog.latency_ms < hi)
            )
            lo = hi
        hist_cols.append(func.count(TbAppLog.id).filter(TbAppLog.latency_ms >= lo))

        stmt = (
            select(
                bucket_col,
                app_col,
                func.count(TbAppLog.id),
                func.coalesce(func.sum(TbAppLog.success), 0),
                func.coalesce(func.sum(TbAppLog.total_tokens), 0),
                func.coalesce(func.sum(TbAppLog.input_tokens), 0),
                func.coalesce(func.sum(TbAppLog.output_tokens), 0),
                func.count(TbAppLog.id).filter(TbAppLog.latency_ms.isnot(None)),
                func.coalesce(func.sum(TbAppLog.latency_ms), 0),
                *hist_cols,
            )
            .where(TbAppLog.create_time >= from_b, TbAppLog.create_time < to_b)
            .group_by(bucket_col, app_col)
        )

        now = int(time.time() * 1000)
        rows: list[dict] = []
        for r in db.execute(stmt).all():
            histogram = [int(r[9 + i]) for i in range(_HIST_SLOTS)]
            rows.append(
                {
                    "bucket_start": int(r[0]),
                    "app_id": int(r[1]),
                    "request_count": int(r[2]),
                    "success_count": int(r[3]),
                    "total_tokens": int(r[4]),
                    "input_tokens": int(r[5]),
                    "output_tokens": int(r[6]),
                    "latency_count": int(r[7]),
                    "latency_sum": int(r[8]),
                    "latency_histogram": json.dumps(histogram),
                    "update_time": now,
                }
            )
        if not rows:
            return 0

        ins = pg_insert(TbAppMetricMinute).values(rows)
        ins = ins.on_conflict_do_update(
            index_elements=["bucket_start", "app_id"],
            set_={c: getattr(ins.excluded, c) for c in _UPSERT_COLS},
        )
        db.execute(ins)
        db.commit()
        return len(rows)

    def rebuild(self, db: Session, from_ms: int, to_ms: int) -> int:
        """重建 [from_ms, to_ms):先删该区间桶,再从 tb_app_log 重算。

        删除步骤可处理「原始日志被清理后某桶应清零」的情况。
        """
        from_b = align_minute(from_ms)
        to_b = ceil_minute(to_ms)
        db.execute(
            delete(TbAppMetricMinute).where(
                TbAppMetricMinute.bucket_start >= from_b,
                TbAppMetricMinute.bucket_start < to_b,
            )
        )
        db.commit()
        return self.roll_up(db, from_b, to_b)

    # ── 读取 ──

    def fetch_rows(
        self, db: Session, from_ms: int, to_ms: int, app_id: int | None = None
    ) -> list[TbAppMetricMinute]:
        """读取 [from_ms, to_ms) 内的分钟桶, 按 bucket_start 升序。"""
        # bucket_start 是分钟对齐值;from_ms 向下对齐才不会漏掉首个不完整桶。
        stmt = select(TbAppMetricMinute).where(
            TbAppMetricMinute.bucket_start >= align_minute(from_ms),
            TbAppMetricMinute.bucket_start < to_ms,
        )
        if app_id is not None:
            stmt = stmt.where(TbAppMetricMinute.app_id == app_id)
        return list(db.scalars(stmt.order_by(TbAppMetricMinute.bucket_start)).all())

    def metric_series(
        self,
        db: Session,
        metric_type: str,
        from_ms: int,
        to_ms: int,
        step_ms: int,
        app_id: int | None = None,
    ) -> list[tuple[int, float | None]]:
        """把 [from_ms, to_ms) 按 step_ms 分桶, 逐桶算出 metric_type 的值。

        用于告警溯源曲线。聚合表不支持的指标(consecutive_failures /
        negative_feedback_rate)逐点返回 None。
        """
        rows = self.fetch_rows(db, from_ms, to_ms, app_id=app_id)
        n = max(1, (to_ms - from_ms + step_ms - 1) // step_ms)
        binned: list[list[TbAppMetricMinute]] = [[] for _ in range(n)]
        for r in rows:
            idx = (r.bucket_start - from_ms) // step_ms
            if 0 <= idx < n:
                binned[idx].append(r)
        return [(from_ms + i * step_ms, _metric_value(metric_type, binned[i])) for i in range(n)]


def _metric_value(metric_type: str, rows: list[TbAppMetricMinute]) -> float | None:
    """从一组分钟桶算出某指标的值;无数据或指标不支持返回 None。"""
    if not rows:
        return None
    requests = sum(r.request_count for r in rows)
    success = sum(r.success_count for r in rows)
    if metric_type == "success_rate":
        return round(success / requests * 100, 2) if requests else None
    if metric_type == "error_rate":
        return round((requests - success) / requests * 100, 2) if requests else None
    if metric_type in ("p95_latency", "request_latency"):
        hist = merge_histograms([parse_histogram(r.latency_histogram) for r in rows])
        p = percentile_from_histogram(hist, 0.95)
        return float(p) if p is not None else None
    if metric_type == "token_usage_daily":
        return float(sum(r.total_tokens for r in rows))
    if metric_type == "llm_error_count_by_type":
        return float(requests - success)
    # consecutive_failures / negative_feedback_rate: 聚合表不支持
    return None
