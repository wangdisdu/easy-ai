"""RAG 库 API 路由(/api/v1/rag-dataset)。

RAG 库对应 RAGFlow Dataset,持有 embedding / 分块配置。本路由还承载分类映射
与检索测试。仅声明端点;逻辑在 ``RagDatasetService`` / ``MappingService`` /
``KbRetrieveService``。详见 ``docs/knowledge-v2-design.md``。

注意:静态路径(/page /options /local-categories /retrieve)必须在 /{dataset_id}
之前注册,否则会被动态段吞掉。
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.rag_dataset_model import (
    LocalCategoryItem,
    MappedCategory,
    MappingSetReq,
    RagDatasetCreateReq,
    RagDatasetOption,
    RagDatasetPageReq,
    RagDatasetResp,
    RagDatasetUpdateReq,
    RetrieveReq,
    RetrieveResp,
)
from app.service.kb_retrieve_service import KbRetrieveService
from app.service.mapping_service import MappingService
from app.service.rag_dataset_service import RagDatasetService

router = APIRouter(prefix="/rag-dataset", tags=["rag-dataset"])
_id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
service = RagDatasetService(_id_gen)
mapping_service = MappingService(_id_gen)
retrieve_service = KbRetrieveService()


# ── 静态路径(须在 /{dataset_id} 之前)─────────────────────────────────


@router.get("/page", response_model=PagedResp[RagDatasetResp])
def page_datasets(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[RagDatasetResp]:
    data, total = service.page(
        db=db,
        req=RagDatasetPageReq(page_no=page_no, page_size=page_size, keyword=keyword, status=status),
    )
    return PagedResp(data=data, total=total)


@router.get("/options", response_model=Resp[list[RagDatasetOption]])
def list_options(db: Session = Depends(get_db)) -> Resp[list[RagDatasetOption]]:
    return Resp(data=service.list_options(db=db))


@router.get("/local-categories", response_model=Resp[list[LocalCategoryItem]])
def list_local_categories(
    db: Session = Depends(get_db),
) -> Resp[list[LocalCategoryItem]]:
    """全量本地分类 + 占用情况,供映射配置面板渲染。"""
    return Resp(data=mapping_service.list_local_categories(db=db))


@router.post("/retrieve", response_model=Resp[RetrieveResp])
def retrieve(
    req: RetrieveReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[RetrieveResp]:
    return Resp(data=retrieve_service.retrieve(db=db, req=req, req_ctx=req_ctx))


@router.post("", response_model=Resp[RagDatasetResp])
def create_dataset(
    req: RagDatasetCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[RagDatasetResp]:
    return Resp(data=service.create(db=db, req=req, req_ctx=req_ctx))


# ── 动态路径 ────────────────────────────────────────────────────────────


@router.get("/{dataset_id}", response_model=Resp[RagDatasetResp])
def get_dataset(dataset_id: str, db: Session = Depends(get_db)) -> Resp[RagDatasetResp]:
    return Resp(data=service.get(db=db, dataset_id=int(dataset_id)))


@router.put("/{dataset_id}", response_model=Resp[RagDatasetResp])
def update_dataset(
    dataset_id: str,
    req: RagDatasetUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[RagDatasetResp]:
    return Resp(data=service.update(db=db, dataset_id=int(dataset_id), req=req, req_ctx=req_ctx))


@router.delete("/{dataset_id}", response_model=Resp[bool])
def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    service.delete(db=db, dataset_id=int(dataset_id), req_ctx=req_ctx)
    return Resp(data=True)


@router.post("/{dataset_id}/sync", response_model=Resp[int])
def sync_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[int]:
    """把该 RAG 库的全部文档重新置入向量化队列。"""
    return Resp(data=service.sync(db=db, dataset_id=int(dataset_id), req_ctx=req_ctx))


@router.get("/{dataset_id}/mapping", response_model=Resp[list[MappedCategory]])
def get_mapping(dataset_id: str, db: Session = Depends(get_db)) -> Resp[list[MappedCategory]]:
    return Resp(data=mapping_service.get_mapped_categories(db=db, dataset_id=int(dataset_id)))


@router.put("/{dataset_id}/mapping", response_model=Resp[bool])
def set_mapping(
    dataset_id: str,
    body: MappingSetReq = Body(...),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    """全量覆盖该 RAG 库映射的分类集合。"""
    mapping_service.set_mapping(
        db=db,
        dataset_id=int(dataset_id),
        category_ids=body.category_ids,
        req_ctx=req_ctx,
    )
    return Resp(data=True)
