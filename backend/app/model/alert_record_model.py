from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbAlertRecord


class AlertRecordPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    level: str | None = Field(default=None, max_length=16)  # critical/warning/info
    status: str | None = Field(default=None, max_length=16)  # firing/resolved/acknowledged
    rule_id: str | None = Field(default=None)
    from_ms: int | None = Field(default=None)  # triggered_at >= from_ms
    to_ms: int | None = Field(default=None)  # triggered_at < to_ms


class AlertRecordResp(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    level: str
    status: str
    metric_type: str
    scope: str
    app_id: str | None = None
    app_name: str | None = None
    observed_value: float
    threshold: float
    message: str
    triggered_at: int
    resolved_at: int | None = None
    acknowledged_at: int | None = None
    acknowledged_by: str | None = None
    # 持续时长: firing/acknowledged 取 now-triggered, resolved 取 resolved-triggered
    duration_ms: int
    create_time: int

    @classmethod
    def from_entity(cls, e: TbAlertRecord, *, now_ms: int) -> AlertRecordResp:
        end = e.resolved_at if e.resolved_at is not None else now_ms
        return cls(
            id=str(e.id),
            rule_id=str(e.rule_id),
            rule_name=e.rule_name,
            level=e.level,
            status=e.status,
            metric_type=e.metric_type,
            scope=e.scope,
            app_id=str(e.app_id) if e.app_id is not None else None,
            app_name=e.app_name,
            observed_value=e.observed_value,
            threshold=e.threshold,
            message=e.message,
            triggered_at=e.triggered_at,
            resolved_at=e.resolved_at,
            acknowledged_at=e.acknowledged_at,
            acknowledged_by=(str(e.acknowledged_by) if e.acknowledged_by is not None else None),
            duration_ms=max(0, end - e.triggered_at),
            create_time=e.create_time,
        )


class AlertActiveResp(BaseModel):
    """AlertsBell 用:当前活跃(firing)告警的分级计数 + 最近若干条。"""

    total: int
    critical: int
    warning: int
    info: int
    items: list[AlertRecordResp] = Field(default_factory=list)


class AlertTracePoint(BaseModel):
    ts: int  # 桶起点 Unix ms
    value: float | None = None  # 该桶的指标值;无数据 / 指标不支持为 None


class AlertTraceResp(BaseModel):
    """告警溯源曲线:某告警指标在触发前后的时序。"""

    record_id: str
    metric_type: str
    threshold: float
    triggered_at: int
    resolved_at: int | None = None
    step_ms: int  # 采样步长
    points: list[AlertTracePoint] = Field(default_factory=list)
