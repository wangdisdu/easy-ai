"""KB 检索 API (/api/v1/kb/retrieve)。

把 kb_ids + question 透传给 RAGFlow ``/retrieval``,返回引用溯源形式的命中列表。
RAG 应用 runtime (M2) 与前端检索测试面板共用此接口。

详见 ``docs/knowledge-rag-integration-design.md`` §6.3。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.db.session import get_db
from app.model.kb_model import KbRetrieveReq, KbRetrieveResp
from app.service.kb_retrieve_service import KbRetrieveService

router = APIRouter(prefix="/kb", tags=["kb"])
service = KbRetrieveService()


@router.post("/retrieve", response_model=Resp[KbRetrieveResp])
def retrieve(
    req: KbRetrieveReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[KbRetrieveResp]:
    return Resp(data=service.retrieve(db=db, req=req, req_ctx=req_ctx))
