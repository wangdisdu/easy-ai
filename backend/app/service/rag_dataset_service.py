"""RAG 库业务层。

每个 ``tb_rag_dataset`` 与一个 RAGFlow Dataset 1:1。RAG 库持有 embedding /
分块配置;本地分类通过 ``tb_kb_category_mapping`` 映射进来。

- create: 调 RAGFlow ``create_dataset``,落本地;本地失败尽力回滚上游
- update: name / description 双边同步;embedding / 分块不可改
- delete: 删 RAGFlow dataset + 映射;关联文档解绑(原文仍在 easy-ai)
- sync: 把该库全部文档重置为 pending,交向量化 worker 重推

详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbKbCategoryMapping, TbKbDocument, TbLlmModel, TbLlmProvider, TbRagDataset
from app.integration import ragflow_client
from app.integration.ragflow_client import build_ragflow_model_ref
from app.model.rag_dataset_model import (
    VALID_CHUNK_METHODS,
    RagDatasetCreateReq,
    RagDatasetOption,
    RagDatasetPageReq,
    RagDatasetResp,
    RagDatasetUpdateReq,
)
from app.service.kb_errors import to_service_error
from app.service.system_setting_service import (
    AI_DEFAULT_EMBEDDING_KEY,
    SystemSettingService,
)

logger = logging.getLogger(__name__)


class RagDatasetService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._system_setting = SystemSettingService()

    # ── 写操作 ────────────────────────────────────────────────────────

    def create(
        self, db: Session, req: RagDatasetCreateReq, req_ctx: RequestContext
    ) -> RagDatasetResp:
        self._require_ragflow_enabled()
        chunk_method = req.chunk_method or "naive"
        if chunk_method not in VALID_CHUNK_METHODS:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid chunk_method: {chunk_method}")

        embedding_ref = self._resolve_embedding_model_ref(db, req.embedding_model)

        client = ragflow_client.get_client()
        try:
            dataset = client.create_dataset(
                name=req.name,
                user_id=req_ctx.user_id,
                embedding_model=embedding_ref,
                chunk_method=chunk_method,
                description=req.description,
                parser_config=req.parser_config,
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[rag] create_dataset failed name=%s err=%s", req.name, e)
            raise to_service_error(e, "create_dataset") from e
        ragflow_dataset_id = dataset.get("id")
        if not ragflow_dataset_id:
            raise ServiceError(
                ErrorCode.INTERNAL_ERROR, f"ragflow dataset response missing id: {dataset}"
            )

        now = req_ctx.request_time_ms
        entity = TbRagDataset(
            id=self._id_generator.next_id(),
            name=req.name,
            description=req.description,
            ragflow_dataset_id=ragflow_dataset_id,
            embedding_model=embedding_ref,
            chunk_method=chunk_method,
            parser_config=(
                json.dumps(req.parser_config, ensure_ascii=False) if req.parser_config else None
            ),
            doc_count=0,
            chunk_count=0,
            status="ready",
            last_synced_at=now,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("[rag] local insert failed, rolling back ragflow=%s", ragflow_dataset_id)
            self._best_effort_delete(ragflow_dataset_id, req_ctx.user_id)
            raise ServiceError(ErrorCode.INTERNAL_ERROR, f"rag_dataset insert failed: {e}") from e
        db.refresh(entity)
        logger.info("[rag] action=create id=%s ragflow=%s", entity.id, ragflow_dataset_id)
        return RagDatasetResp.from_entity(entity)

    def update(
        self,
        db: Session,
        dataset_id: int,
        req: RagDatasetUpdateReq,
        req_ctx: RequestContext,
    ) -> RagDatasetResp:
        entity = self._get_or_raise(db, dataset_id)
        changed: dict[str, object] = {}
        if req.name is not None and req.name != entity.name:
            entity.name = req.name
            changed["name"] = req.name
        if req.description is not None and req.description != (entity.description or ""):
            entity.description = req.description
            changed["description"] = req.description
        if not changed:
            return self._to_resp(db, entity)

        if entity.ragflow_dataset_id:
            self._require_ragflow_enabled()
            client = ragflow_client.get_client()
            try:
                client.update_dataset(entity.ragflow_dataset_id, user_id=req_ctx.user_id, **changed)
            except ragflow_client.RagflowClientError as e:
                logger.error("[rag] update_dataset failed id=%s err=%s", dataset_id, e)
                raise to_service_error(e, "update_dataset") from e

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        logger.info("[rag] action=update id=%s fields=%s", dataset_id, list(changed))
        return self._to_resp(db, entity)

    def delete(self, db: Session, dataset_id: int, req_ctx: RequestContext) -> None:
        entity = self._get_or_raise(db, dataset_id)
        if entity.ragflow_dataset_id:
            self._require_ragflow_enabled()
            client = ragflow_client.get_client()
            try:
                client.delete_datasets([entity.ragflow_dataset_id], user_id=req_ctx.user_id)
            except ragflow_client.RagflowClientError as e:
                logger.error("[rag] delete_dataset failed id=%s err=%s", dataset_id, e)
                raise to_service_error(e, "delete_dataset") from e

        # 解绑映射 + 关联文档(原文仍在 easy-ai blob, 只是失去 RAG 库)
        db.query(TbKbCategoryMapping).filter(
            TbKbCategoryMapping.rag_dataset_id == dataset_id
        ).delete(synchronize_session=False)
        db.query(TbKbDocument).filter(TbKbDocument.rag_dataset_id == dataset_id).update(
            {
                TbKbDocument.rag_dataset_id: None,
                TbKbDocument.ragflow_doc_id: None,
                TbKbDocument.vectorize_status: "not_mapped",
                TbKbDocument.update_time: req_ctx.request_time_ms,
            },
            synchronize_session=False,
        )
        db.delete(entity)
        db.commit()
        logger.info("[rag] action=delete id=%s", dataset_id)

    def sync(self, db: Session, dataset_id: int, req_ctx: RequestContext) -> int:
        """把该 RAG 库的全部文档重置为 pending,交向量化 worker 重推。"""
        self._get_or_raise(db, dataset_id)
        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.rag_dataset_id == dataset_id)
        ).all()
        now = req_ctx.request_time_ms
        for row in rows:
            row.vectorize_status = "pending"
            row.error_message = None
            row.parse_progress = 0.0
            row.parse_begin_at = None
            row.parse_duration_sec = None
            row.parse_progress_msg = None
            row.update_time = now
            row.update_user = req_ctx.user_id
        db.commit()
        logger.info("[rag] action=sync id=%s docs=%d", dataset_id, len(rows))
        return len(rows)

    # ── 读操作 ────────────────────────────────────────────────────────

    def page(self, db: Session, req: RagDatasetPageReq) -> tuple[list[RagDatasetResp], int]:
        stmt = select(TbRagDataset)
        count_stmt = select(func.count(TbRagDataset.id))
        conditions = []
        if req.keyword:
            kw = f"%{req.keyword}%"
            conditions.append(or_(TbRagDataset.name.like(kw)))
        if req.status:
            conditions.append(TbRagDataset.status == req.status)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = db.scalar(count_stmt) or 0
        rows = db.scalars(
            stmt.order_by(TbRagDataset.create_time.desc())
            .offset((req.page_no - 1) * req.page_size)
            .limit(req.page_size)
        ).all()
        ids = [r.id for r in rows]
        stats = self._aggregate_stats(db, ids)
        mapped = self._mapped_counts(db, ids)
        return [self._build(r, stats, mapped) for r in rows], total

    def get(self, db: Session, dataset_id: int) -> RagDatasetResp:
        entity = self._get_or_raise(db, dataset_id)
        return self._to_resp(db, entity)

    def list_options(self, db: Session) -> list[RagDatasetOption]:
        rows = db.scalars(select(TbRagDataset).order_by(TbRagDataset.create_time.desc())).all()
        stats = self._aggregate_stats(db, [r.id for r in rows])
        return [
            RagDatasetOption(
                id=str(r.id),
                name=r.name,
                embedding_model=r.embedding_model,
                chunk_method=r.chunk_method,
                doc_count=stats.get(r.id, (0, 0))[0],
            )
            for r in rows
        ]

    # ── 内部 ──────────────────────────────────────────────────────────

    def _build(
        self,
        entity: TbRagDataset,
        stats: dict[int, tuple[int, int]],
        mapped: dict[int, int],
    ) -> RagDatasetResp:
        resp = RagDatasetResp.from_entity(entity, mapped.get(entity.id, 0))
        dc, cc = stats.get(entity.id, (0, 0))
        resp.doc_count = dc
        resp.chunk_count = cc
        return resp

    def _to_resp(self, db: Session, entity: TbRagDataset) -> RagDatasetResp:
        stats = self._aggregate_stats(db, [entity.id])
        mapped = self._mapped_counts(db, [entity.id])
        return self._build(entity, stats, mapped)

    def _aggregate_stats(self, db: Session, dataset_ids: list[int]) -> dict[int, tuple[int, int]]:
        if not dataset_ids:
            return {}
        rows = db.execute(
            select(
                TbKbDocument.rag_dataset_id,
                func.count(TbKbDocument.id),
                func.coalesce(func.sum(TbKbDocument.chunks_count), 0),
            )
            .where(TbKbDocument.rag_dataset_id.in_(dataset_ids))
            .group_by(TbKbDocument.rag_dataset_id)
        ).all()
        return {int(did): (int(dc or 0), int(cc or 0)) for did, dc, cc in rows}

    def _mapped_counts(self, db: Session, dataset_ids: list[int]) -> dict[int, int]:
        if not dataset_ids:
            return {}
        rows = db.execute(
            select(TbKbCategoryMapping.rag_dataset_id, func.count(TbKbCategoryMapping.id))
            .where(TbKbCategoryMapping.rag_dataset_id.in_(dataset_ids))
            .group_by(TbKbCategoryMapping.rag_dataset_id)
        ).all()
        return {int(did): int(cnt) for did, cnt in rows}

    def _get_or_raise(self, db: Session, dataset_id: int) -> TbRagDataset:
        entity = db.get(TbRagDataset, dataset_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"rag_dataset not found: {dataset_id}")
        return entity

    def _require_ragflow_enabled(self) -> None:
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

    def _best_effort_delete(self, ragflow_dataset_id: str, user_id: int | None) -> None:
        try:
            ragflow_client.get_client().delete_datasets([ragflow_dataset_id], user_id=user_id)
        except ragflow_client.RagflowClientError as e:
            logger.warning(
                "[rag] best-effort delete failed ragflow=%s err=%s", ragflow_dataset_id, e
            )

    def _resolve_embedding_model_ref(self, db: Session, requested: str | None) -> str:
        """归一化 embedding 入参为 RAGFlow ``"{model}@{factory}"`` 串。
        留空时从 ``ai.default.embedding_model_id`` 系统设置反查。"""
        if requested:
            if "@" in requested:
                return requested
            row = db.execute(
                select(TbLlmModel, TbLlmProvider)
                .join(TbLlmProvider, TbLlmProvider.id == TbLlmModel.provider_id)
                .where(TbLlmModel.model == requested, TbLlmModel.model_type == "Embedding")
                .limit(1)
            ).first()
            if not row:
                raise ServiceError(
                    ErrorCode.KB_EMBEDDING_NOT_CONFIGURED,
                    f"embedding model {requested!r} not found in LLM management",
                )
            _, provider = row
            return build_ragflow_model_ref(requested, provider.provider_type)

        model_id_str = self._system_setting.get(db, AI_DEFAULT_EMBEDDING_KEY)
        if not model_id_str:
            raise ServiceError(
                ErrorCode.KB_EMBEDDING_NOT_CONFIGURED,
                "no embedding model specified and no system default configured "
                f"(set system-setting {AI_DEFAULT_EMBEDDING_KEY})",
            )
        try:
            model_id = int(model_id_str)
        except ValueError as e:
            raise ServiceError(
                ErrorCode.KB_EMBEDDING_NOT_CONFIGURED,
                f"system default embedding model id {model_id_str!r} is not an integer",
            ) from e
        row = db.execute(
            select(TbLlmModel, TbLlmProvider)
            .join(TbLlmProvider, TbLlmProvider.id == TbLlmModel.provider_id)
            .where(TbLlmModel.id == model_id)
            .limit(1)
        ).first()
        if not row:
            raise ServiceError(
                ErrorCode.KB_EMBEDDING_NOT_CONFIGURED,
                f"system default embedding model id={model_id} not found in LLM management",
            )
        llm_model, provider = row
        if llm_model.model_type != "Embedding":
            raise ServiceError(
                ErrorCode.KB_EMBEDDING_NOT_CONFIGURED,
                f"system default model id={model_id} is type {llm_model.model_type}, "
                "expected Embedding",
            )
        return build_ragflow_model_ref(llm_model.model, provider.provider_type)
