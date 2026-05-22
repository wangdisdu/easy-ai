import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.db.session import get_db
from app.model.alert_record_model import (
    AlertActiveResp,
    AlertRecordPageReq,
    AlertRecordResp,
    AlertTraceResp,
)
from app.service.alert_record_service import AlertRecordService

router = APIRouter(prefix="/observability/alert", tags=["observability-alert"])
service = AlertRecordService()


@router.get("/page", response_model=PagedResp[AlertRecordResp])
def page_alert_record(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    level: str | None = Query(default=None),
    status: str | None = Query(default=None),
    rule_id: str | None = Query(default=None),
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
) -> PagedResp[AlertRecordResp]:
    data, total = service.page_record(
        db=db,
        req=AlertRecordPageReq(
            page_no=page_no,
            page_size=page_size,
            level=level,
            status=status,
            rule_id=rule_id,
            from_ms=from_ms,
            to_ms=to_ms,
        ),
        now_ms=int(time.time() * 1000),
    )
    return PagedResp(data=data, total=total)


@router.get("/active", response_model=Resp[AlertActiveResp])
def get_active_alerts(db: Session = Depends(get_db)) -> Resp[AlertActiveResp]:
    """AlertsBell 轮询:当前活跃(firing)告警的分级计数 + 最近若干条。"""
    return Resp(data=service.get_active(db=db, now_ms=int(time.time() * 1000)))


@router.get("/{record_id}", response_model=Resp[AlertRecordResp])
def get_alert_record(record_id: str, db: Session = Depends(get_db)) -> Resp[AlertRecordResp]:
    return Resp(
        data=service.get_record_by_id(
            db=db, record_id=int(record_id), now_ms=int(time.time() * 1000)
        )
    )


@router.get("/{record_id}/trace", response_model=Resp[AlertTraceResp])
def get_alert_trace(record_id: str, db: Session = Depends(get_db)) -> Resp[AlertTraceResp]:
    """告警溯源曲线:该告警指标在触发前后的时序(数据来自 tb_app_metric_minute)。"""
    return Resp(
        data=service.get_trace(db=db, record_id=int(record_id), now_ms=int(time.time() * 1000))
    )


@router.post("/{record_id}/acknowledge", response_model=Resp[AlertRecordResp])
def acknowledge_alert_record(
    record_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRecordResp]:
    """确认告警(告警中心「确认」/ AlertsBell「标记已读」)。"""
    return Resp(data=service.acknowledge(db=db, record_id=int(record_id), req_ctx=req_ctx))


@router.post("/{record_id}/resolve", response_model=Resp[AlertRecordResp])
def resolve_alert_record(
    record_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRecordResp]:
    """恢复告警(告警中心「恢复」)。"""
    return Resp(data=service.resolve(db=db, record_id=int(record_id), req_ctx=req_ctx))
