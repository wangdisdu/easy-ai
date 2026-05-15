"""知识库 (KB) 业务层。

每个 ``tb_kb`` 与 RAGFlow Dataset 1:1 映射:
- create_kb: 先调 RAGFlow ``create_dataset``,拿到 ``ragflow_dataset_id`` 后落本地;
  本地 commit 失败时尽力回滚 RAGFlow 侧
- update_kb: name / description 同步两边; embedding_model / chunk_method 不可改
- delete_kb: 先调 RAGFlow ``delete_datasets``,再删本地; RAGFlow 失败则中止

``doc_count`` / ``chunk_count`` 在读时实时聚合 ``tb_kb_document``,不依赖
``tb_kb`` 上的同名缓存列(那两列保留但不再维护)。文档解析状态由后台 poller
更新到 ``tb_kb_document.chunks_count``,所以聚合天然实时。

详见 ``docs/knowledge-rag-integration-design.md`` §5.3。
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
from app.db.schema import TbKb, TbKbDocument, TbLlmModel, TbLlmProvider
from app.integration import ragflow_client
from app.integration.ragflow_client import build_ragflow_model_ref
from app.model.kb_model import (
    VALID_CHUNK_METHODS,
    KbCreateReq,
    KbOption,
    KbPageReq,
    KbResp,
    KbUpdateReq,
)
from app.service.kb_errors import to_service_error
from app.service.system_setting_service import (
    AI_DEFAULT_EMBEDDING_KEY,
    SystemSettingService,
)

logger = logging.getLogger(__name__)


class KbService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._system_setting = SystemSettingService()

    # ── 写操作 ────────────────────────────────────────────────────────

    def create_kb(self, db: Session, req: KbCreateReq, req_ctx: RequestContext) -> KbResp:
        self._require_ragflow_enabled()
        chunk_method = req.chunk_method or "naive"
        if chunk_method not in VALID_CHUNK_METHODS:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"invalid chunk_method: {chunk_method}",
            )

        # 1. 校验 code 唯一
        existing = db.scalar(select(TbKb).where(TbKb.code == req.code))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, f"kb code already exists: {req.code}")

        # 2. 解析 embedding_model:优先 req,其次系统默认。落库前归一化为
        # RAGFlow 可识别的 "{model}@{factory}" 串。
        embedding_ref = self._resolve_embedding_model_ref(db, req.embedding_model)

        # 3. 调 RAGFlow 创建 dataset
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
            logger.error("[kb] create_dataset failed code=%s err=%s", req.code, e)
            raise to_service_error(e, "create_dataset") from e
        dataset_id = dataset.get("id")
        if not dataset_id:
            raise ServiceError(
                ErrorCode.INTERNAL_ERROR, f"ragflow dataset response missing id: {dataset}"
            )

        # 3. 落本地; 失败时尽力删 RAGFlow 那边的 dataset 避免孤儿
        now = req_ctx.request_time_ms
        entity = TbKb(
            id=self._id_generator.next_id(),
            code=req.code,
            name=req.name,
            description=req.description,
            ragflow_dataset_id=dataset_id,
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
            logger.error("[kb] local insert failed, rolling back ragflow dataset_id=%s", dataset_id)
            self._best_effort_delete_dataset(dataset_id, req_ctx.user_id)
            raise ServiceError(ErrorCode.INTERNAL_ERROR, f"kb local insert failed: {e}") from e
        db.refresh(entity)
        logger.info(
            "[kb] action=create kb_id=%s code=%s dataset_id=%s", entity.id, entity.code, dataset_id
        )
        # 刚建,doc_count/chunk_count 必然 0,无需查
        return self._to_resp(entity, {})

    def update_kb(
        self, db: Session, kb_id: int, req: KbUpdateReq, req_ctx: RequestContext
    ) -> KbResp:
        entity = self._get_entity_or_raise(db, kb_id)
        # 拒绝 embedding_model / chunk_method 修改: 由 model 层屏蔽,这里二重保险
        changed_fields: dict[str, object] = {}
        if req.name is not None and req.name != entity.name:
            entity.name = req.name
            changed_fields["name"] = req.name
        if req.description is not None and req.description != (entity.description or ""):
            entity.description = req.description
            changed_fields["description"] = req.description

        if not changed_fields:
            return self._to_resp(entity, self._aggregate_stats(db, [entity.id]))

        # 同步 RAGFlow 侧
        if entity.ragflow_dataset_id:
            self._require_ragflow_enabled()
            client = ragflow_client.get_client()
            try:
                client.update_dataset(
                    entity.ragflow_dataset_id, user_id=req_ctx.user_id, **changed_fields
                )
            except ragflow_client.RagflowClientError as e:
                logger.error("[kb] update_dataset failed kb_id=%s err=%s", kb_id, e)
                raise to_service_error(e, "update_dataset") from e

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        logger.info("[kb] action=update kb_id=%s fields=%s", kb_id, list(changed_fields))
        return self._to_resp(entity, self._aggregate_stats(db, [entity.id]))

    def delete_kb(self, db: Session, kb_id: int, req_ctx: RequestContext) -> None:
        entity = self._get_entity_or_raise(db, kb_id)
        dataset_id = entity.ragflow_dataset_id
        if dataset_id:
            self._require_ragflow_enabled()
            client = ragflow_client.get_client()
            try:
                client.delete_datasets([dataset_id], user_id=req_ctx.user_id)
            except ragflow_client.RagflowClientError as e:
                logger.error("[kb] delete_dataset failed kb_id=%s err=%s", kb_id, e)
                raise to_service_error(e, "delete_dataset") from e

        db.delete(entity)
        db.commit()
        logger.info("[kb] action=delete kb_id=%s dataset_id=%s", kb_id, dataset_id)

    # ── 读操作 ────────────────────────────────────────────────────────

    def page_kb(self, db: Session, req: KbPageReq) -> tuple[list[KbResp], int]:
        stmt = select(TbKb)
        count_stmt = select(func.count(TbKb.id))
        conditions = []
        if req.keyword:
            keyword = f"%{req.keyword}%"
            conditions.append(or_(TbKb.code.like(keyword), TbKb.name.like(keyword)))
        if req.status:
            conditions.append(TbKb.status == req.status)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = db.scalar(count_stmt) or 0
        rows = db.scalars(
            stmt.order_by(TbKb.create_time.desc())
            .offset((req.page_no - 1) * req.page_size)
            .limit(req.page_size)
        ).all()
        stats = self._aggregate_stats(db, [r.id for r in rows])
        return [self._to_resp(r, stats) for r in rows], total

    def get_kb_by_id(self, db: Session, kb_id: int) -> KbResp:
        entity = self._get_entity_or_raise(db, kb_id)
        stats = self._aggregate_stats(db, [entity.id])
        return self._to_resp(entity, stats)

    def list_kb_options(self, db: Session) -> list[KbOption]:
        rows = db.scalars(
            select(TbKb).where(TbKb.status == "ready").order_by(TbKb.create_time.desc())
        ).all()
        return [
            KbOption(
                id=str(r.id),
                code=r.code,
                name=r.name,
                embedding_model=r.embedding_model,
                chunk_method=r.chunk_method,
                doc_count=r.doc_count,
            )
            for r in rows
        ]

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _aggregate_stats(
        self, db: Session, kb_ids: list[int]
    ) -> dict[int, tuple[int, int]]:
        """批量算 (doc_count, chunk_count): 一次 GROUP BY 即可,空集合直接跳。"""
        if not kb_ids:
            return {}
        rows = db.execute(
            select(
                TbKbDocument.kb_id,
                func.count(TbKbDocument.id),
                func.coalesce(func.sum(TbKbDocument.chunks_count), 0),
            )
            .where(TbKbDocument.kb_id.in_(kb_ids))
            .group_by(TbKbDocument.kb_id)
        ).all()
        return {int(kb_id): (int(dc or 0), int(cc or 0)) for kb_id, dc, cc in rows}

    def _to_resp(self, entity: TbKb, stats: dict[int, tuple[int, int]]) -> KbResp:
        dc, cc = stats.get(entity.id, (0, 0))
        resp = KbResp.from_entity(entity)
        resp.doc_count = dc
        resp.chunk_count = cc
        return resp

    def _require_ragflow_enabled(self) -> None:
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

    def _get_entity_or_raise(self, db: Session, kb_id: int) -> TbKb:
        entity = db.get(TbKb, kb_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"kb not found: {kb_id}")
        return entity

    def _resolve_embedding_model_ref(self, db: Session, requested: str | None) -> str:
        """归一化 embedding 入参为 RAGFlow ``"{model}@{factory}"`` 串:
        - requested 非空且含 ``@``: 视为已经是 ragflow ref,直接使用
        - requested 非空不含 ``@``: 视作 model 名,根据 LLM 管理回查 provider 拼出
        - requested 为空: 从 ``ai.default.embedding_model_id`` 取 tb_llm_model.id 反查
        - 均无: 抛 KB_EMBEDDING_NOT_CONFIGURED"""
        if requested:
            if "@" in requested:
                return requested
            # 用模型名搜 LLM 管理找 provider
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

        # 走系统默认
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

    def _best_effort_delete_dataset(self, dataset_id: str, user_id: int | None) -> None:
        try:
            client = ragflow_client.get_client()
            client.delete_datasets([dataset_id], user_id=user_id)
        except ragflow_client.RagflowClientError as e:
            logger.warning(
                "[kb] best-effort delete_dataset failed dataset_id=%s err=%s",
                dataset_id,
                e,
            )
