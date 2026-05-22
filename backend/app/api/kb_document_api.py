"""KB 文档 API 路由(/api/v1/kb/{kb_id}/document)。

仅声明端点;逻辑在 ``KbDocumentService`` / ``VectorizationService``。文件上传
走 multipart;批量删除用 JSON body;原文下载从 blob 存储读取。
详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import io
import urllib.parse

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.kb_model import (
    KbChunkResp,
    KbDocumentMoveReq,
    KbDocumentPageReq,
    KbDocumentResp,
)
from app.service.kb_document_service import KbDocumentService
from app.service.vectorization_service import VectorizationService

router = APIRouter(prefix="/kb", tags=["kb"])
_id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
service = KbDocumentService(_id_gen)
vectorize_service = VectorizationService(_id_gen)


class KbDocumentIdsReq(BaseModel):
    """批量删除的 body。"""

    ids: list[str] = Field(min_length=1)


@router.get("/document-by-ref/{ref}", response_model=Resp[KbDocumentResp])
def get_document_by_ref(ref: str, db: Session = Depends(get_db)) -> Resp[KbDocumentResp]:
    return Resp(data=service.get_document_by_ref(db, ref))


@router.get("/{kb_id}/document/page", response_model=PagedResp[KbDocumentResp])
def page_documents(
    kb_id: str,
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    category_id: str | None = Query(default=None, description='分类id; "0"=未分类'),
    recursive: bool = Query(default=False, description="True 时含子树文档"),
    vectorize_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[KbDocumentResp]:
    data, total = service.page_documents(
        db=db,
        kb_id=int(kb_id),
        req=KbDocumentPageReq(
            page_no=page_no,
            page_size=page_size,
            keyword=keyword,
            category_id=category_id,
            recursive=recursive,
            vectorize_status=vectorize_status,
        ),
    )
    return PagedResp(data=data, total=total)


@router.post("/{kb_id}/document", response_model=Resp[list[KbDocumentResp]])
async def upload_documents(
    kb_id: str,
    files: list[UploadFile] = File(...),
    category_id: str = Form(default="0"),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[list[KbDocumentResp]]:
    blobs: list[tuple[str, bytes]] = []
    for f in files:
        if not f.filename:
            continue
        blobs.append((f.filename, await f.read()))
    return Resp(
        data=service.upload_documents(
            db=db,
            kb_id=int(kb_id),
            files=blobs,
            category_id=int(category_id or 0),
            req_ctx=req_ctx,
        )
    )


@router.get("/{kb_id}/document/{doc_id}", response_model=Resp[KbDocumentResp])
def get_document(kb_id: str, doc_id: str, db: Session = Depends(get_db)) -> Resp[KbDocumentResp]:
    return Resp(data=service.get_document_detail(db=db, kb_id=int(kb_id), doc_id=int(doc_id)))


@router.get("/{kb_id}/document/{doc_id}/download")
def download_document(
    kb_id: str,
    doc_id: str,
    inline: bool = Query(default=False, description="true=浏览器内嵌预览, false=另存为"),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """获取上传文件原始字节(从 easy-ai blob 存储读取)。"""
    blob, mime, filename = service.download_document(db=db, kb_id=int(kb_id), doc_id=int(doc_id))
    disposition = "inline" if inline else "attachment"
    quoted = urllib.parse.quote(filename)
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii")
    return StreamingResponse(
        io.BytesIO(blob),
        media_type=mime,
        headers={
            "Content-Disposition": (
                f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted}"
            ),
            "Content-Length": str(len(blob)),
        },
    )


@router.get("/{kb_id}/document/{doc_id}/chunk", response_model=PagedResp[KbChunkResp])
def list_chunks(
    kb_id: str,
    doc_id: str,
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=200),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> PagedResp[KbChunkResp]:
    chunks, total = service.list_document_chunks(
        db=db,
        kb_id=int(kb_id),
        doc_id=int(doc_id),
        req_ctx=req_ctx,
        page=page_no,
        page_size=page_size,
        keywords=keyword,
    )
    return PagedResp(data=chunks, total=total)


@router.post("/{kb_id}/document/{doc_id}/revectorize", response_model=Resp[bool])
def revectorize_document(
    kb_id: str,
    doc_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    """把文档重新置入向量化队列(交向量化 worker 重推 RAGFlow)。"""
    count = vectorize_service.revectorize(
        db=db, kb_id=int(kb_id), doc_ids=[int(doc_id)], req_ctx=req_ctx
    )
    return Resp(data=count > 0)


@router.put("/{kb_id}/document/move", response_model=Resp[int])
def move_documents(
    kb_id: str,
    body: KbDocumentMoveReq = Body(...),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[int]:
    count = service.move_documents(
        db=db,
        kb_id=int(kb_id),
        doc_ids=[int(x) for x in body.ids],
        category_id=int(body.category_id or 0),
        req_ctx=req_ctx,
    )
    return Resp(data=count)


@router.delete("/{kb_id}/document", response_model=Resp[int])
def delete_documents(
    kb_id: str,
    body: KbDocumentIdsReq = Body(...),
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[int]:
    count = service.delete_documents(
        db=db, kb_id=int(kb_id), doc_ids=[int(x) for x in body.ids], req_ctx=req_ctx
    )
    return Resp(data=count)
