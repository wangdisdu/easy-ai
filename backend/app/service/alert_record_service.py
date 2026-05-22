from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.db.schema import TbAlertRecord
from app.model.alert_record_model import (
    AlertActiveResp,
    AlertRecordPageReq,
    AlertRecordResp,
    AlertTracePoint,
    AlertTraceResp,
)
from app.service.metric_rollup_service import MetricRollupService

# 告警溯源曲线的展示窗口:触发前 30 分钟、恢复后 10 分钟
_TRACE_LOOKBACK_MS = 30 * 60_000
_TRACE_LOOKAHEAD_MS = 10 * 60_000
# 曲线目标点数上限(步长据此按分钟取整)
_TRACE_MAX_POINTS = 120

# AlertsBell「活跃告警」的展示条数上限
_ACTIVE_LIMIT = 20


class AlertRecordService:
    """告警记录查询与状态流转。记录由 AlertEvaluator 写入,此处不负责创建。

    状态机: firing --acknowledge--> acknowledged --resolve--> resolved
                  \\------------------resolve------------------/
    """

    def __init__(self) -> None:
        self._rollup = MetricRollupService()

    def _get_or_404(self, db: Session, record_id: int) -> TbAlertRecord:
        entity = db.get(TbAlertRecord, record_id)
        if not entity:
            raise ServiceError(ErrorCode.ALERT_RECORD_NOT_FOUND, "alert record not found")
        return entity

    # ── 查询 ──

    def page_record(
        self, db: Session, req: AlertRecordPageReq, *, now_ms: int
    ) -> tuple[list[AlertRecordResp], int]:
        stmt = select(TbAlertRecord)
        count_stmt = select(func.count(TbAlertRecord.id))

        conditions = []
        if req.level:
            conditions.append(TbAlertRecord.level == req.level)
        if req.status:
            conditions.append(TbAlertRecord.status == req.status)
        if req.rule_id:
            conditions.append(TbAlertRecord.rule_id == int(req.rule_id))
        if req.from_ms is not None:
            conditions.append(TbAlertRecord.triggered_at >= req.from_ms)
        if req.to_ms is not None:
            conditions.append(TbAlertRecord.triggered_at < req.to_ms)

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbAlertRecord.triggered_at.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [AlertRecordResp.from_entity(r, now_ms=now_ms) for r in rows], total

    def get_record_by_id(self, db: Session, record_id: int, *, now_ms: int) -> AlertRecordResp:
        return AlertRecordResp.from_entity(self._get_or_404(db, record_id), now_ms=now_ms)

    def get_active(self, db: Session, *, now_ms: int) -> AlertActiveResp:
        """AlertsBell 数据:活跃 = status=firing(尚未确认、未恢复)。"""
        level_rows = db.execute(
            select(TbAlertRecord.level, func.count(TbAlertRecord.id))
            .where(TbAlertRecord.status == "firing")
            .group_by(TbAlertRecord.level)
        ).all()
        counts = {str(lvl): int(c) for lvl, c in level_rows}

        items = db.scalars(
            select(TbAlertRecord)
            .where(TbAlertRecord.status == "firing")
            .order_by(TbAlertRecord.triggered_at.desc())
            .limit(_ACTIVE_LIMIT)
        ).all()

        return AlertActiveResp(
            total=sum(counts.values()),
            critical=counts.get("critical", 0),
            warning=counts.get("warning", 0),
            info=counts.get("info", 0),
            items=[AlertRecordResp.from_entity(r, now_ms=now_ms) for r in items],
        )

    # ── 状态流转 ──

    def acknowledge(self, db: Session, record_id: int, req_ctx: RequestContext) -> AlertRecordResp:
        """确认告警(原型「确认」按钮 / AlertsBell「标记已读」)。firing → acknowledged。"""
        entity = self._get_or_404(db, record_id)
        now = req_ctx.request_time_ms
        if entity.status == "resolved":
            raise ServiceError(ErrorCode.BAD_REQUEST, "已恢复的告警不可确认")
        if entity.status == "firing":
            entity.status = "acknowledged"
            entity.acknowledged_at = now
            entity.acknowledged_by = req_ctx.user_id
            entity.update_time = now
            entity.update_user = req_ctx.user_id
            db.commit()
            db.refresh(entity)
        # 已是 acknowledged 则幂等返回
        return AlertRecordResp.from_entity(entity, now_ms=now)

    def resolve(self, db: Session, record_id: int, req_ctx: RequestContext) -> AlertRecordResp:
        """恢复告警(原型「恢复」按钮)。firing/acknowledged → resolved。"""
        entity = self._get_or_404(db, record_id)
        now = req_ctx.request_time_ms
        if entity.status != "resolved":
            entity.status = "resolved"
            entity.resolved_at = now
            entity.update_time = now
            entity.update_user = req_ctx.user_id
            db.commit()
            db.refresh(entity)
        # 已是 resolved 则幂等返回
        return AlertRecordResp.from_entity(entity, now_ms=now)

    # ── 告警溯源曲线 ──

    def get_trace(self, db: Session, record_id: int, *, now_ms: int) -> AlertTraceResp:
        """返回该告警指标在触发前后的时序曲线,数据来自 tb_app_metric_minute。"""
        record = self._get_or_404(db, record_id)
        end = record.resolved_at if record.resolved_at is not None else now_ms
        from_ms = record.triggered_at - _TRACE_LOOKBACK_MS
        to_ms = min(now_ms, end + _TRACE_LOOKAHEAD_MS)
        if to_ms <= from_ms:
            to_ms = from_ms + 60_000
        # 步长:控制点数 ≤ _TRACE_MAX_POINTS,且按整分钟对齐
        step_ms = max(60_000, (to_ms - from_ms) // _TRACE_MAX_POINTS // 60_000 * 60_000)
        # per_app 范围的告警只看其应用;其余按全局
        app_id = record.app_id if record.scope == "per_app" and record.app_id else None
        series = self._rollup.metric_series(db, record.metric_type, from_ms, to_ms, step_ms, app_id)
        return AlertTraceResp(
            record_id=str(record.id),
            metric_type=record.metric_type,
            threshold=record.threshold,
            triggered_at=record.triggered_at,
            resolved_at=record.resolved_at,
            step_ms=step_ms,
            points=[AlertTracePoint(ts=ts, value=v) for ts, v in series],
        )
