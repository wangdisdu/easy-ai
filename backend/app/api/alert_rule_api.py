from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.alert_rule_model import (
    AlertRuleCreateReq,
    AlertRuleEvaluateResp,
    AlertRulePageReq,
    AlertRuleResp,
    AlertRuleUpdateReq,
)
from app.service.alert_rule_service import AlertRuleService

router = APIRouter(prefix="/observability/alert-rule", tags=["observability-alert"])
service = AlertRuleService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[AlertRuleResp])
def page_alert_rule(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    metric_type: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[AlertRuleResp]:
    data, total = service.page_rule(
        db=db,
        req=AlertRulePageReq(
            page_no=page_no,
            page_size=page_size,
            keyword=keyword,
            metric_type=metric_type,
            enabled=enabled,
        ),
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[AlertRuleResp])
def create_alert_rule(
    req: AlertRuleCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRuleResp]:
    return Resp(data=service.create_rule(db=db, req=req, req_ctx=req_ctx))


@router.get("/{rule_id}", response_model=Resp[AlertRuleResp])
def get_alert_rule(rule_id: str, db: Session = Depends(get_db)) -> Resp[AlertRuleResp]:
    return Resp(data=service.get_rule_by_id(db=db, rule_id=int(rule_id)))


@router.put("/{rule_id}", response_model=Resp[AlertRuleResp])
def update_alert_rule(
    rule_id: str,
    req: AlertRuleUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRuleResp]:
    return Resp(data=service.update_rule(db=db, rule_id=int(rule_id), req=req, req_ctx=req_ctx))


@router.delete("/{rule_id}", response_model=Resp[bool])
def delete_alert_rule(rule_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_rule(db=db, rule_id=int(rule_id))
    return Resp(data=True)


@router.post("/{rule_id}/enable", response_model=Resp[AlertRuleResp])
def enable_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRuleResp]:
    return Resp(
        data=service.toggle_rule(db=db, rule_id=int(rule_id), enabled=True, req_ctx=req_ctx)
    )


@router.post("/{rule_id}/disable", response_model=Resp[AlertRuleResp])
def disable_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRuleResp]:
    return Resp(
        data=service.toggle_rule(db=db, rule_id=int(rule_id), enabled=False, req_ctx=req_ctx)
    )


@router.post("/{rule_id}/evaluate", response_model=Resp[AlertRuleEvaluateResp])
def evaluate_alert_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AlertRuleEvaluateResp]:
    """原型「立即评估」按钮:同步评估一次,命中且不在冷却期则落告警记录。"""
    return Resp(data=service.evaluate_rule(db=db, rule_id=int(rule_id), req_ctx=req_ctx))
