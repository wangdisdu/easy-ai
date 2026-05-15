"""KB 检索业务层 (M1)。

把 easy-ai 侧的 ``kb_ids`` 翻译成 RAGFlow ``dataset_ids`` 后透传给
``/api/v1/retrieval``,字段重组成 ``app-factory-design.md`` 中 RAG 应用消费的
"引用溯源" 形态,前端的检索测试面板与 M2 的 RagAppRunner 共用。

约束:
- 多 KB 检索时, 所有 KB 的 ``embedding_model`` 必须一致 (RAGFlow 限制)
- ``document_ids`` 可选, 仅在前端"按指定文档检索"时传

详见 ``docs/knowledge-rag-integration-design.md`` §5.5。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.db.schema import TbKb, TbKbDocument, TbLlmModel, TbLlmProvider
from app.integration import ragflow_client
from app.integration.ragflow_client import build_ragflow_model_ref
from app.model.kb_model import KbRetrieveHit, KbRetrieveReq, KbRetrieveResp
from app.service.kb_errors import to_service_error
from app.service.system_setting_service import (
    AI_DEFAULT_RERANK_KEY,
    SystemSettingService,
)

logger = logging.getLogger(__name__)


class KbRetrieveService:
    """无状态;不持有 SnowflakeGenerator(检索本身不写表)。"""

    def __init__(self) -> None:
        self._system_setting = SystemSettingService()

    def retrieve(self, db: Session, req: KbRetrieveReq, req_ctx: RequestContext) -> KbRetrieveResp:
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

        kb_ids = [int(x) for x in req.kb_ids]
        kbs = db.scalars(select(TbKb).where(TbKb.id.in_(kb_ids))).all()
        if not kbs:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"no kb found for ids={req.kb_ids}")
        if len(kbs) != len(set(kb_ids)):
            missing = set(kb_ids) - {kb.id for kb in kbs}
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"kb not found: {sorted(missing)}")

        # embedding 一致性: RAGFlow /retrieval 要求多 dataset 同 embedding
        embeddings = {kb.embedding_model for kb in kbs}
        if len(embeddings) > 1:
            raise ServiceError(
                ErrorCode.KB_EMBEDDING_MISMATCH,
                f"kb embedding_model must be identical: got {sorted(embeddings)}",
            )

        # 缺失 ragflow_dataset_id 的 KB 跳过 (status=error 的可能场景)
        dataset_ids = [kb.ragflow_dataset_id for kb in kbs if kb.ragflow_dataset_id]
        if not dataset_ids:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"no usable ragflow_dataset_id under kb_ids={req.kb_ids}",
            )

        # document_ids: 把 easy-ai 文档 id 翻译成 ragflow_doc_id
        ragflow_doc_ids: list[str] | None = None
        if req.document_ids:
            doc_int_ids = [int(x) for x in req.document_ids]
            rows = db.scalars(select(TbKbDocument).where(TbKbDocument.id.in_(doc_int_ids))).all()
            ragflow_doc_ids = [r.ragflow_doc_id for r in rows if r.ragflow_doc_id]
            if not ragflow_doc_ids:
                # 文档都没映射的话相当于空集合,索性返回空结果
                return KbRetrieveResp(hits=[], total=0)

        rerank_id = self._resolve_rerank_id(db, req.rerank_id)

        client = ragflow_client.get_client()
        try:
            data = client.retrieve(
                user_id=req_ctx.user_id,
                dataset_ids=dataset_ids,
                question=req.question,
                document_ids=ragflow_doc_ids,
                top_k=req.top_k,
                similarity_threshold=req.similarity_threshold,
                rerank_id=rerank_id,
                keyword=req.keyword,
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[kb] retrieve failed kb_ids=%s err=%s", req.kb_ids, e)
            raise to_service_error(e, "retrieve") from e

        # data 结构: { chunks: [...], doc_aggs: [...], total: int }
        chunks_raw = data.get("chunks") if isinstance(data, dict) else None
        total = int(data.get("total") or 0) if isinstance(data, dict) else 0
        hits: list[KbRetrieveHit] = []
        for c in chunks_raw or []:
            hits.append(_to_hit(c))
        logger.info(
            "[kb] action=retrieve kb_ids=%s top_k=%d hits=%d",
            req.kb_ids,
            req.top_k,
            len(hits),
        )
        return KbRetrieveResp(hits=hits, total=total or len(hits))

    def _resolve_rerank_id(self, db: Session, requested: str | None) -> str | None:
        """req.rerank_id 优先;否则系统默认。任何一步缺失都返回 None
        (rerank 是可选增强,RAGFlow 自身允许 rerank_id 为空)。"""
        if requested:
            return requested if "@" in requested else self._lookup_rerank_ref(db, requested)
        model_id_str = self._system_setting.get(db, AI_DEFAULT_RERANK_KEY)
        if not model_id_str:
            return None
        try:
            model_id = int(model_id_str)
        except ValueError:
            logger.warning(
                "[kb] system default rerank id=%r is not integer, ignored", model_id_str
            )
            return None
        row = db.execute(
            select(TbLlmModel, TbLlmProvider)
            .join(TbLlmProvider, TbLlmProvider.id == TbLlmModel.provider_id)
            .where(TbLlmModel.id == model_id, TbLlmModel.model_type == "Rerank")
            .limit(1)
        ).first()
        if not row:
            logger.warning(
                "[kb] system default rerank id=%s not found or not Rerank type", model_id
            )
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


def _to_hit(chunk: dict) -> KbRetrieveHit:
    """RAGFlow chunk dict → 引用溯源 KbRetrieveHit。字段宽松适配,
    不同 RAGFlow 版本字段名略有差异。"""
    similarity = chunk.get("similarity")
    if similarity is None:
        # 兼容 vector_similarity / term_similarity 两个分项
        similarity = chunk.get("vector_similarity") or chunk.get("term_similarity")
    return KbRetrieveHit(
        chunk_id=str(chunk.get("id") or chunk.get("chunk_id") or ""),
        content=str(chunk.get("content") or chunk.get("content_with_weight") or ""),
        similarity=float(similarity) if similarity is not None else None,
        doc_id=chunk.get("document_id") or chunk.get("doc_id"),
        doc_name=chunk.get("document_keyword") or chunk.get("docnm_kwd"),
        highlight=chunk.get("highlight"),
    )
