import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbAlertRule
from app.model.alert_rule_model import (
    AlertRuleCreateReq,
    AlertRuleEvaluateResp,
    AlertRulePageReq,
    AlertRuleResp,
    AlertRuleUpdateReq,
)
from app.service.alert_evaluator import AlertEvaluator

# 单位 % 仅适用于「比率类」指标, ms 仅适用于「延迟类」指标——粗校验。
_RATE_METRICS = {"success_rate", "error_rate", "negative_feedback_rate"}
_LATENCY_METRICS = {"p95_latency", "request_latency"}


class AlertRuleService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._evaluator = AlertEvaluator(id_generator)

    # ── Helpers ──

    def _validate_config(self, metric_type: str, unit: str | None) -> None:
        if unit == "%" and metric_type not in _RATE_METRICS:
            raise ServiceError(ErrorCode.ALERT_RULE_INVALID_CONFIG, "单位 % 仅适用于比率类指标")
        if unit == "ms" and metric_type not in _LATENCY_METRICS:
            raise ServiceError(ErrorCode.ALERT_RULE_INVALID_CONFIG, "单位 ms 仅适用于延迟类指标")

    def _ensure_name_unique(
        self, db: Session, rule_name: str, exclude_id: int | None = None
    ) -> None:
        stmt = select(func.count(TbAlertRule.id)).where(TbAlertRule.rule_name == rule_name)
        if exclude_id is not None:
            stmt = stmt.where(TbAlertRule.id != exclude_id)
        if (db.scalar(stmt) or 0) > 0:
            raise ServiceError(ErrorCode.ALERT_RULE_NAME_DUPLICATE, f"规则名已存在: {rule_name}")

    def _get_or_404(self, db: Session, rule_id: int) -> TbAlertRule:
        entity = db.get(TbAlertRule, rule_id)
        if not entity:
            raise ServiceError(ErrorCode.ALERT_RULE_NOT_FOUND, "alert rule not found")
        return entity

    # ── CRUD ──

    def create_rule(
        self, db: Session, req: AlertRuleCreateReq, req_ctx: RequestContext
    ) -> AlertRuleResp:
        self._validate_config(req.metric_type, req.threshold_unit)
        self._ensure_name_unique(db, req.rule_name)
        now = req_ctx.request_time_ms
        entity = TbAlertRule(
            id=self._id_generator.next_id(),
            rule_name=req.rule_name,
            description=req.description,
            metric_type=req.metric_type,
            target_error_type=req.target_error_type,
            operator=req.operator,
            threshold=req.threshold,
            threshold_unit=req.threshold_unit,
            scope=req.scope,
            level=req.level,
            window_minutes=req.window_minutes,
            cooldown_minutes=req.cooldown_minutes,
            notify_channels=json.dumps(req.notify_channels, ensure_ascii=False),
            message_template=req.message_template,
            enabled=1 if req.enabled else 0,
            trigger_count=0,
            last_triggered_at=None,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return AlertRuleResp.from_entity(entity)

    def page_rule(self, db: Session, req: AlertRulePageReq) -> tuple[list[AlertRuleResp], int]:
        stmt = select(TbAlertRule)
        count_stmt = select(func.count(TbAlertRule.id))

        conditions = []
        if req.keyword:
            conditions.append(TbAlertRule.rule_name.like(f"%{req.keyword}%"))
        if req.metric_type:
            conditions.append(TbAlertRule.metric_type == req.metric_type)
        if req.enabled is not None:
            conditions.append(TbAlertRule.enabled == (1 if req.enabled else 0))

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbAlertRule.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [AlertRuleResp.from_entity(r) for r in rows], total

    def get_rule_by_id(self, db: Session, rule_id: int) -> AlertRuleResp:
        return AlertRuleResp.from_entity(self._get_or_404(db, rule_id))

    def update_rule(
        self,
        db: Session,
        rule_id: int,
        req: AlertRuleUpdateReq,
        req_ctx: RequestContext,
    ) -> AlertRuleResp:
        entity = self._get_or_404(db, rule_id)

        if req.rule_name is not None:
            self._ensure_name_unique(db, req.rule_name, exclude_id=rule_id)
            entity.rule_name = req.rule_name
        if req.description is not None:
            entity.description = req.description
        if req.metric_type is not None:
            entity.metric_type = req.metric_type
        if req.operator is not None:
            entity.operator = req.operator
        if req.threshold is not None:
            entity.threshold = req.threshold
        if req.threshold_unit is not None:
            entity.threshold_unit = req.threshold_unit
        if req.scope is not None:
            entity.scope = req.scope
        if req.level is not None:
            entity.level = req.level
        if req.window_minutes is not None:
            entity.window_minutes = req.window_minutes
        if req.cooldown_minutes is not None:
            entity.cooldown_minutes = req.cooldown_minutes
        if req.notify_channels is not None:
            entity.notify_channels = json.dumps(req.notify_channels, ensure_ascii=False)
        if req.message_template is not None:
            entity.message_template = req.message_template
        if req.enabled is not None:
            entity.enabled = 1 if req.enabled else 0

        # target_error_type 随最终的 metric_type 归一化:仅 LLM 错误计数指标保留。
        if entity.metric_type == "llm_error_count_by_type":
            if req.target_error_type is not None:
                entity.target_error_type = req.target_error_type
        else:
            entity.target_error_type = None

        self._validate_config(entity.metric_type, entity.threshold_unit)

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return AlertRuleResp.from_entity(entity)

    def delete_rule(self, db: Session, rule_id: int) -> None:
        entity = self._get_or_404(db, rule_id)
        db.delete(entity)
        db.commit()
        # tb_alert_record 历史记录有意保留:其 rule_name 为触发时快照,不受影响。

    def toggle_rule(
        self, db: Session, rule_id: int, enabled: bool, req_ctx: RequestContext
    ) -> AlertRuleResp:
        entity = self._get_or_404(db, rule_id)
        entity.enabled = 1 if enabled else 0
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return AlertRuleResp.from_entity(entity)

    # ── 立即评估（原型「立即评估」按钮）──

    def evaluate_rule(
        self, db: Session, rule_id: int, req_ctx: RequestContext
    ) -> AlertRuleEvaluateResp:
        entity = self._get_or_404(db, rule_id)
        return self._evaluator.evaluate(db, entity, now_ms=req_ctx.request_time_ms)
