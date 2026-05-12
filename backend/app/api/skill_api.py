from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.skill_model import (
    SkillCreateReq,
    SkillPageReq,
    SkillPublishReq,
    SkillResp,
    SkillUpdateReq,
    SkillVersionResp,
)
from app.service.skill_service import SkillService

router = APIRouter(prefix="/skill", tags=["skill"])
service = SkillService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[SkillResp])
def page_skill(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    skill_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[SkillResp]:
    data, total = service.page_skill(
        db=db,
        req=SkillPageReq(
            page_no=page_no,
            page_size=page_size,
            keyword=keyword,
            category_id=category_id,
            skill_status=skill_status,
        ),
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[SkillResp])
def create_skill(
    req: SkillCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SkillResp]:
    return Resp(data=service.create_skill(db=db, req=req, req_ctx=req_ctx))


@router.get("/{skill_id}", response_model=Resp[SkillResp])
def get_skill(skill_id: str, db: Session = Depends(get_db)) -> Resp[SkillResp]:
    return Resp(data=service.get_skill_by_id(db=db, skill_id=int(skill_id)))


@router.put("/{skill_id}", response_model=Resp[SkillResp])
def update_skill(
    skill_id: str,
    req: SkillUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SkillResp]:
    return Resp(data=service.update_skill(db=db, skill_id=int(skill_id), req=req, req_ctx=req_ctx))


@router.delete("/{skill_id}", response_model=Resp[bool])
def delete_skill(skill_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_skill(db=db, skill_id=int(skill_id))
    return Resp(data=True)


@router.post("/{skill_id}/enable", response_model=Resp[SkillResp])
def enable_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SkillResp]:
    return Resp(
        data=service.toggle_skill_status(
            db=db, skill_id=int(skill_id), status="enabled", req_ctx=req_ctx
        )
    )


@router.post("/{skill_id}/disable", response_model=Resp[SkillResp])
def disable_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SkillResp]:
    return Resp(
        data=service.toggle_skill_status(
            db=db, skill_id=int(skill_id), status="disabled", req_ctx=req_ctx
        )
    )


@router.post("/{skill_id}/publish", response_model=Resp[SkillVersionResp])
def publish_skill(
    skill_id: str,
    req: SkillPublishReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SkillVersionResp]:
    return Resp(data=service.publish_skill(db=db, skill_id=int(skill_id), req=req, req_ctx=req_ctx))


@router.get("/{skill_id}/version", response_model=Resp[list[SkillVersionResp]])
def list_skill_versions(
    skill_id: str, db: Session = Depends(get_db)
) -> Resp[list[SkillVersionResp]]:
    return Resp(data=service.list_skill_versions(db=db, skill_id=int(skill_id)))
