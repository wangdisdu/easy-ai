from __future__ import annotations

from pydantic import BaseModel


class StatDelta(BaseModel):
    value: float | int | None = None  # 当前窗口值
    compare: float | int | None = None  # 对比窗口值
    delta_pct: float | None = None  # 同比变化百分比，正值为增长
    sub_label: str | None = None  # UI 副标题（例如 "失败 2064 次" / "费用 ¥-"）


class OverviewStats(BaseModel):
    total_requests: StatDelta
    success_rate: StatDelta  # value 为 0-100
    p95_latency_ms: StatDelta
    total_tokens: StatDelta


class TrendPoint(BaseModel):
    label: str  # 例如 "00" "02"
    ts: int  # 桶起始 Unix 毫秒


class AppTrendSeries(BaseModel):
    app_id: str
    app_name: str
    color: str
    data: list[int]


class TrendResp(BaseModel):
    labels: list[str]
    total: list[int]
    apps: list[AppTrendSeries]


class ModelTokenRow(BaseModel):
    model: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    cost: float | None = None  # P0 阶段固定为 None


class AppHealthRow(BaseModel):
    app_id: str
    app_name: str
    app_type: str
    calls: int
    success_rate: float  # 0-100
    p95_latency_ms: int | None
    avg_latency_ms: int | None
    total_tokens: int
    feedback_rate: float | None = None  # P0 阶段固定为 None
    trend: list[int]  # 最近 N 个时间点的调用量


class ErrorAppRow(BaseModel):
    app_id: str
    app_name: str
    app_type: str
    errors: int
    error_rate: float  # 0-100
    top_error: str | None = None  # P0 阶段固定为 None


class RecentRequestRow(BaseModel):
    id: str
    app_id: str | None
    app_name: str | None
    app_type: str | None
    user_id: str | None
    preview: str  # 从 request_payload 解析的查询预览
    latency_ms: int | None
    total_tokens: int | None
    success: bool
    create_time: int
    langfuse_trace_id: str | None = None
    feedback: str | None = None  # P0 阶段固定为 None
