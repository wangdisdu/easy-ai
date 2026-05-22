from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.db.schema import TbAlertRule

# 监控指标类型。与 web-demo 原型告警规则表单一致。
MetricType = Literal[
    "success_rate",
    "p95_latency",
    "error_rate",
    "token_usage_daily",
    "request_latency",
    "consecutive_failures",
    "negative_feedback_rate",
    "llm_error_count_by_type",
]
Operator = Literal["lt", "lte", "gt", "gte", "eq"]
Scope = Literal["global", "per_app", "per_request"]
AlertLevel = Literal["critical", "warning", "info"]
# P1 仅站内信;后续扩展 email / webhook
NotifyChannel = Literal["inbox"]


class AlertRuleCreateReq(BaseModel):
    rule_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    metric_type: MetricType
    target_error_type: str | None = Field(default=None, max_length=64)
    operator: Operator
    threshold: float
    threshold_unit: str | None = Field(default=None, max_length=16)
    scope: Scope = "global"
    level: AlertLevel = "warning"
    window_minutes: int = Field(default=5, ge=1, le=1440)
    cooldown_minutes: int = Field(default=10, ge=0, le=1440)
    notify_channels: list[NotifyChannel] = Field(default_factory=lambda: ["inbox"])
    message_template: str | None = Field(default=None)
    enabled: bool = True

    @model_validator(mode="after")
    def _normalize(self) -> AlertRuleCreateReq:
        # 非 LLM 错误计数指标，target_error_type 一律清空（与原型 ht() 保存逻辑一致）
        if self.metric_type != "llm_error_count_by_type":
            self.target_error_type = None
        return self


class AlertRuleUpdateReq(BaseModel):
    """字段为 None 表示不更新该字段。"""

    rule_name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    metric_type: MetricType | None = Field(default=None)
    target_error_type: str | None = Field(default=None, max_length=64)
    operator: Operator | None = Field(default=None)
    threshold: float | None = Field(default=None)
    threshold_unit: str | None = Field(default=None, max_length=16)
    scope: Scope | None = Field(default=None)
    level: AlertLevel | None = Field(default=None)
    window_minutes: int | None = Field(default=None, ge=1, le=1440)
    cooldown_minutes: int | None = Field(default=None, ge=0, le=1440)
    notify_channels: list[NotifyChannel] | None = Field(default=None)
    message_template: str | None = Field(default=None)
    enabled: bool | None = Field(default=None)


class AlertRulePageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)  # 命中 rule_name
    metric_type: str | None = Field(default=None, max_length=64)
    enabled: bool | None = Field(default=None)


class AlertRuleResp(BaseModel):
    id: str
    rule_name: str
    description: str | None = None
    metric_type: str
    target_error_type: str | None = None
    operator: str
    threshold: float
    threshold_unit: str | None = None
    scope: str
    level: str
    window_minutes: int
    cooldown_minutes: int
    notify_channels: list[str] = Field(default_factory=list)
    message_template: str | None = None
    enabled: bool
    trigger_count: int
    last_triggered_at: int | None = None
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, e: TbAlertRule) -> AlertRuleResp:
        try:
            channels = json.loads(e.notify_channels) if e.notify_channels else []
        except ValueError:
            channels = []
        return cls(
            id=str(e.id),
            rule_name=e.rule_name,
            description=e.description,
            metric_type=e.metric_type,
            target_error_type=e.target_error_type,
            operator=e.operator,
            threshold=e.threshold,
            threshold_unit=e.threshold_unit,
            scope=e.scope,
            level=e.level,
            window_minutes=e.window_minutes,
            cooldown_minutes=e.cooldown_minutes,
            notify_channels=channels if isinstance(channels, list) else [],
            message_template=e.message_template,
            enabled=bool(e.enabled),
            trigger_count=e.trigger_count,
            last_triggered_at=e.last_triggered_at,
            create_time=e.create_time,
            update_time=e.update_time,
        )


class AlertRuleEvaluateResp(BaseModel):
    """「立即评估」结果。"""

    triggered: bool  # 是否命中阈值
    observed_value: float | None = None  # 实测指标值；窗口内无数据时为 None
    threshold: float
    message: str  # 渲染后的告警文案，或「未触发」说明
    record_id: str | None = None  # 实际写入告警记录时返回其 ID（冷却期内不写）
