"""检索业务层(v2)。

检索面向 **RAG 库**(``tb_rag_dataset``),把 ``dataset_ids`` 翻译成 RAGFlow
``dataset_ids`` 后透传 ``/api/v1/retrieval``,命中结果重组成引用溯源形态。
前端「知识向量化」Tab 的检索测试与 RAG 应用 runtime 共用。

约束:多 RAG 库检索时所有库的 ``embedding_model`` 必须一致(RAGFlow 限制)。
详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.doc_ref import encode_doc_ref
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.db.schema import TbKbDocument, TbLlmModel, TbLlmProvider, TbRagDataset
from app.integration import ragflow_client
from app.integration.ragflow_client import build_ragflow_model_ref
from app.model.rag_dataset_model import RetrieveHit, RetrieveReq, RetrieveResp
from app.service.kb_errors import to_service_error
from app.service.system_setting_service import (
    AI_DEFAULT_RERANK_KEY,
    SystemSettingService,
)

logger = logging.getLogger(__name__)


class KbRetrieveService:
    """无状态;检索本身不写表。"""

    def __init__(self) -> None:
        self._system_setting = SystemSettingService()

    def retrieve(self, db: Session, req: RetrieveReq, req_ctx: RequestContext) -> RetrieveResp:
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

        dataset_ids = [int(x) for x in req.dataset_ids]
        datasets = db.scalars(select(TbRagDataset).where(TbRagDataset.id.in_(dataset_ids))).all()
        if not datasets:
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND, f"no rag_dataset found for ids={req.dataset_ids}"
            )
        if len(datasets) != len(set(dataset_ids)):
            missing = set(dataset_ids) - {d.id for d in datasets}
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND, f"rag_dataset not found: {sorted(missing)}"
            )

        # embedding 一致性: RAGFlow /retrieval 要求多 dataset 同 embedding
        embeddings = {d.embedding_model for d in datasets}
        if len(embeddings) > 1:
            raise ServiceError(
                ErrorCode.KB_EMBEDDING_MISMATCH,
                f"rag_dataset embedding_model must be identical: got {sorted(embeddings)}",
            )

        ragflow_ids = [d.ragflow_dataset_id for d in datasets if d.ragflow_dataset_id]
        if not ragflow_ids:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"no usable ragflow_dataset_id under dataset_ids={req.dataset_ids}",
            )

        # document_ids: easy-ai 文档 id → ragflow_doc_id
        ragflow_doc_ids: list[str] | None = None
        if req.document_ids:
            doc_int_ids = [int(x) for x in req.document_ids]
            rows = db.scalars(select(TbKbDocument).where(TbKbDocument.id.in_(doc_int_ids))).all()
            ragflow_doc_ids = [r.ragflow_doc_id for r in rows if r.ragflow_doc_id]
            if not ragflow_doc_ids:
                return RetrieveResp(hits=[], total=0)

        rerank_id = self._resolve_rerank_id(db, req.rerank_id)

        client = ragflow_client.get_client()
        try:
            data = client.retrieve(
                user_id=req_ctx.user_id,
                dataset_ids=ragflow_ids,
                question=req.question,
                document_ids=ragflow_doc_ids,
                top_k=req.top_k,
                similarity_threshold=req.similarity_threshold,
                vector_similarity_weight=req.vector_similarity_weight,
                rerank_id=rerank_id,
                keyword=req.keyword,
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[retrieve] failed dataset_ids=%s err=%s", req.dataset_ids, e)
            raise to_service_error(e, "retrieve") from e

        chunks_raw = data.get("chunks") if isinstance(data, dict) else None
        total = int(data.get("total") or 0) if isinstance(data, dict) else 0
        doc_lookup = self._build_doc_lookup(db, chunks_raw or [])
        hits = [_to_hit(c, doc_lookup) for c in (chunks_raw or [])]
        logger.info(
            "[retrieve] dataset_ids=%s top_k=%d hits=%d", req.dataset_ids, req.top_k, len(hits)
        )
        return RetrieveResp(hits=hits, total=total or len(hits))

    def _build_doc_lookup(self, db: Session, chunks: list[dict]) -> dict[str, TbKbDocument]:
        ids = {c.get("document_id") or c.get("doc_id") for c in chunks}
        ids.discard(None)
        ids.discard("")
        if not ids:
            return {}
        rows = db.scalars(select(TbKbDocument).where(TbKbDocument.ragflow_doc_id.in_(ids))).all()
        return {r.ragflow_doc_id: r for r in rows if r.ragflow_doc_id}

    def _resolve_rerank_id(self, db: Session, requested: str | None) -> str | None:
        """req.rerank_id 优先;否则系统默认。任一步缺失返回 None(rerank 可选)。"""
        if requested:
            return requested if "@" in requested else self._lookup_rerank_ref(db, requested)
        model_id_str = self._system_setting.get(db, AI_DEFAULT_RERANK_KEY)
        if not model_id_str:
            return None
        try:
            model_id = int(model_id_str)
        except ValueError:
            logger.warning("[retrieve] system default rerank id=%r not integer", model_id_str)
            return None
        row = db.execute(
            select(TbLlmModel, TbLlmProvider)
            .join(TbLlmProvider, TbLlmProvider.id == TbLlmModel.provider_id)
            .where(TbLlmModel.id == model_id, TbLlmModel.model_type == "Rerank")
            .limit(1)
        ).first()
        if not row:
            logger.warning("[retrieve] system default rerank id=%s not found", model_id)
            return None
        llm_model, provider = row
        return build_ragflow_model_ref(llm_model.model, provider.provider_type)

    def _lookup_rerank_ref(self, db: Session, model_name: str) -> str | None:
        row = db.execute(
            select(TbLlmModel, TbLlmProvider)
            .join(TbLlmProvider, TbLlmProvider.id == TbLlmModel.provider_id)
            .where(TbLlmModel.model == model_name, TbLlmModel.model_type == "Rerank")
            .limit(1)
        ).first()
        if not row:
            return None
        llm_model, provider = row
        return build_ragflow_model_ref(llm_model.model, provider.provider_type)


def _to_hit(chunk: dict, doc_lookup: dict[str, TbKbDocument]) -> RetrieveHit:
    similarity = chunk.get("similarity")
    if similarity is None:
        similarity = chunk.get("vector_similarity") or chunk.get("term_similarity")
    ragflow_did = chunk.get("document_id") or chunk.get("doc_id")
    doc_entity = doc_lookup.get(ragflow_did) if ragflow_did else None
    return RetrieveHit(
        chunk_id=str(chunk.get("id") or chunk.get("chunk_id") or ""),
        content=str(chunk.get("content") or chunk.get("content_with_weight") or ""),
        similarity=float(similarity) if similarity is not None else None,
        doc_id=ragflow_did,
        doc_name=(
            chunk.get("document_keyword")
            or chunk.get("docnm_kwd")
            or (doc_entity.name if doc_entity else None)
        ),
        highlight=chunk.get("highlight"),
        easyai_doc_id=str(doc_entity.id) if doc_entity else None,
        doc_ref=encode_doc_ref(doc_entity.id) if doc_entity else None,
        kb_id=str(doc_entity.kb_id) if doc_entity else None,
    )
