from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.llm_model import (
    LlmModelCreateReq,
    LlmModelResp,
    LlmModelUpdateReq,
    LlmProviderCreateReq,
    LlmProviderPageReq,
    LlmProviderResp,
    LlmProviderUpdateReq,
)
from app.model.open_model import AppLogResp, GatewayHealthResp
from app.service.app_log_service import AppLogService
from app.service.llm_service import PREDEFINED_PROVIDERS, LlmService
from app.service.model_gateway_service import ModelGatewayService

router = APIRouter(prefix="/llm", tags=["llm"])
service = LlmService(SnowflakeGenerator(settings.snowflake_worker_id))
gateway_service = ModelGatewayService()
app_log_service = AppLogService(SnowflakeGenerator(settings.snowflake_worker_id))

# ── Provider ──


@router.get("/provider/predefined", response_model=Resp[dict[str, str]])
def get_predefined_providers() -> Resp[dict[str, str]]:
    return Resp(data=PREDEFINED_PROVIDERS)


@router.get("/provider/page", response_model=PagedResp[LlmProviderResp])
def page_provider(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[LlmProviderResp]:
    data, total = service.page_provider(
        db=db,
        req=LlmProviderPageReq(page_no=page_no, page_size=page_size, keyword=keyword),
    )
    return PagedResp(data=data, total=total)


@router.post("/provider", response_model=Resp[LlmProviderResp])
def create_provider(
    req: LlmProviderCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmProviderResp]:
    return Resp(data=service.create_provider(db=db, req=req, req_ctx=req_ctx))


@router.get("/provider/{provider_id}", response_model=Resp[LlmProviderResp])
def get_provider(provider_id: str, db: Session = Depends(get_db)) -> Resp[LlmProviderResp]:
    return Resp(data=service.get_provider(db=db, provider_id=int(provider_id)))


@router.put("/provider/{provider_id}", response_model=Resp[LlmProviderResp])
def update_provider(
    provider_id: str,
    req: LlmProviderUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmProviderResp]:
    return Resp(
        data=service.update_provider(db=db, provider_id=int(provider_id), req=req, req_ctx=req_ctx)
    )


@router.delete("/provider/{provider_id}", response_model=Resp[bool])
def delete_provider(provider_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_provider(db=db, provider_id=int(provider_id))
    return Resp(data=True)


@router.post("/provider/{provider_id}/test", response_model=Resp[LlmProviderResp])
def test_connection(
    provider_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmProviderResp]:
    return Resp(data=service.test_connection(db=db, provider_id=int(provider_id), req_ctx=req_ctx))


@router.get("/provider/{provider_id}/available-models", response_model=Resp[list[str]])
def get_available_models(
    provider_id: str,
    db: Session = Depends(get_db),
) -> Resp[list[str]]:
    return Resp(data=service.list_available_models(db=db, provider_id=int(provider_id)))


@router.get("/gateway/health", response_model=Resp[GatewayHealthResp])
def gateway_health(
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[GatewayHealthResp]:
    return Resp(data=gateway_service.health_check(db=db, req_ctx=req_ctx))


@router.get("/log", response_model=Resp[list[AppLogResp]])
def list_app_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> Resp[list[AppLogResp]]:
    return Resp(data=app_log_service.list_logs(db=db, limit=limit))


# ── Model ──


@router.post("/provider/{provider_id}/model", response_model=Resp[LlmModelResp])
def create_model(
    provider_id: str,
    req: LlmModelCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmModelResp]:
    return Resp(
        data=service.create_model(db=db, provider_id=int(provider_id), req=req, req_ctx=req_ctx)
    )


@router.put("/model/{model_id}", response_model=Resp[LlmModelResp])
def update_model(
    model_id: str,
    req: LlmModelUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmModelResp]:
    return Resp(data=service.update_model(db=db, model_id=int(model_id), req=req, req_ctx=req_ctx))


@router.post("/model/{model_id}/enable", response_model=Resp[LlmModelResp])
def enable_model(
    model_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmModelResp]:
    return Resp(
        data=service.toggle_model_status(
            db=db, model_id=int(model_id), status="active", req_ctx=req_ctx
        )
    )


@router.post("/model/{model_id}/disable", response_model=Resp[LlmModelResp])
def disable_model(
    model_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[LlmModelResp]:
    return Resp(
        data=service.toggle_model_status(
            db=db, model_id=int(model_id), status="inactive", req_ctx=req_ctx
        )
    )


@router.delete("/model/{model_id}", response_model=Resp[bool])
def delete_model(model_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_model(db=db, model_id=int(model_id))
    return Resp(data=True)
