"""KB 文档分类 API 路由(/api/v1/kb/{kb_id}/category)。

分类是树形、单归属、纯 easy-ai 侧的组织维度, 不参与 RAGFlow 建模。
仅声明端点; 逻辑在 ``KbCategoryService``。删除为级联(子树分类 + 其下
文档一并删除, 文档会同步从 RAGFlow 移除), 故 DELETE 需显式 ``confirm``,
不带时返回影响面 dry-run。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.kb_model import (
    KbCategoryCreateReq,
    KbCategoryDeletePreview,
    KbCategoryNode,
    KbCategoryUpdateReq,
)
from app.service.kb_category_service import KbCategoryService
from app.service.kb_document_service import KbDocumentService

router = APIRouter(prefix="/kb", tags=["kb"])
_id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
service = KbCategoryService(_id_gen, KbDocumentService(_id_gen))


@router.get("/{kb_id}/category/tree", response_model=Resp[list[KbCategoryNode]])
def get_category_tree(kb_id: str, db: Session = Depends(get_db)) -> Resp[list[KbCategoryNode]]:
    return Resp(data=service.get_tree(db=db, kb_id=int(kb_id)))


@router.post("/{kb_id}/category", response_model=Resp[KbCategoryNode])
def create_category(
    kb_id: str,
    req: KbCategoryCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[KbCategoryNode]:
    return Resp(data=service.create_category(db=db, kb_id=int(kb_id), req=req, req_ctx=req_ctx))


@router.put("/{kb_id}/category/{cat_id}", response_model=Resp[KbCategoryNode])
def update_category(
    kb_id: str,
    cat_id: str,
    req: KbCategoryUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[KbCategoryNode]:
    return Resp(
        data=service.update_category(
            db=db, kb_id=int(kb_id), category_id=int(cat_id), req=req, req_ctx=req_ctx
        )
    )


@router.delete("/{kb_id}/category/{cat_id}", response_model=Resp[KbCategoryDeletePreview])
def delete_category(
    kb_id: str,
    cat_id: str,
    confirm: bool = Query(
        default=False, description="False=只返回影响面 dry-run; True=真正级联删除"
    ),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[KbCategoryDeletePreview]:
    return Resp(
        data=service.delete_category(
            db=db,
            kb_id=int(kb_id),
            category_id=int(cat_id),
            confirm=confirm,
            req_ctx=req_ctx,
        )
    )
