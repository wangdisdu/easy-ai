"""知识库 (KB) API 路由(v2 纯组织层)。

知识库 v2 重构后,知识库不再绑定 RAGFlow —— 仅声明端点,逻辑在
``KbService``。响应统一 ``Resp[T]`` / ``PagedResp[T]``。详见
``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.kb_model import KbCreateReq, KbOption, KbPageReq, KbResp, KbUpdateReq
from app.service.kb_document_service import KbDocumentService
from app.service.kb_service import KbService

router = APIRouter(prefix="/kb", tags=["kb"])
_id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
service = KbService(_id_gen, KbDocumentService(_id_gen))


@router.get("/page", response_model=PagedResp[KbResp])
def page_kb(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[KbResp]:
    data, total = service.page_kb(
        db=db, req=KbPageReq(page_no=page_no, page_size=page_size, keyword=keyword)
    )
    return PagedResp(data=data, total=total)


@router.get("/options", response_model=Resp[list[KbOption]])
def list_kb_options(db: Session = Depends(get_db)) -> Resp[list[KbOption]]:
    return Resp(data=service.list_kb_options(db=db))


@router.post("", response_model=Resp[KbResp])
def create_kb(
    req: KbCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[KbResp]:
    return Resp(data=service.create_kb(db=db, req=req, req_ctx=req_ctx))


@router.get("/{kb_id}", response_model=Resp[KbResp])
def get_kb(kb_id: str, db: Session = Depends(get_db)) -> Resp[KbResp]:
    return Resp(data=service.get_kb_by_id(db=db, kb_id=int(kb_id)))


@router.put("/{kb_id}", response_model=Resp[KbResp])
def update_kb(
    kb_id: str,
    req: KbUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[KbResp]:
    return Resp(data=service.update_kb(db=db, kb_id=int(kb_id), req=req, req_ctx=req_ctx))


@router.delete("/{kb_id}", response_model=Resp[bool])
def delete_kb(
    kb_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    service.delete_kb(db=db, kb_id=int(kb_id), req_ctx=req_ctx)
    return Resp(data=True)
