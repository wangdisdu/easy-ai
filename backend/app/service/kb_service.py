"""知识库 (KB) 业务层(v2 纯组织层)。

知识库 v2 重构后,``tb_kb`` 不再绑定 RAGFlow —— 退化为纯组织单元(知识库 →
分类 → 文档)。向量化由 RAG 库承担,见 ``rag_dataset_service``。

- create_kb / update_kb: 纯本地,无上游调用
- delete_kb: 级联删除分类 + 文档(文档走 ``KbDocumentService`` 删 blob/RAGFlow)
  + 清理分类映射 + 删除该 KB 的 blob 目录

详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbKb, TbKbCategory, TbKbCategoryMapping, TbKbDocument
from app.integration import kb_storage
from app.model.kb_model import KbCreateReq, KbOption, KbPageReq, KbResp, KbUpdateReq
from app.service.kb_document_service import KbDocumentService

logger = logging.getLogger(__name__)


class KbService:
    def __init__(self, id_generator: SnowflakeGenerator, doc_service: KbDocumentService) -> None:
        self._id_generator = id_generator
        # 删除知识库时复用其 delete_documents(内部删 blob + RAGFlow)
        self._doc_service = doc_service

    # ── 写操作 ────────────────────────────────────────────────────────

    def create_kb(self, db: Session, req: KbCreateReq, req_ctx: RequestContext) -> KbResp:
        existing = db.scalar(select(TbKb).where(TbKb.code == req.code))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, f"kb code already exists: {req.code}")

        now = req_ctx.request_time_ms
        entity = TbKb(
            id=self._id_generator.next_id(),
            code=req.code,
            name=req.name,
            description=req.description,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        logger.info("[kb] action=create kb_id=%s code=%s", entity.id, entity.code)
        return KbResp.from_entity(entity, 0, 0)

    def update_kb(
        self, db: Session, kb_id: int, req: KbUpdateReq, req_ctx: RequestContext
    ) -> KbResp:
        entity = self._get_entity_or_raise(db, kb_id)
        changed = False
        if req.name is not None and req.name != entity.name:
            entity.name = req.name
            changed = True
        if req.description is not None and req.description != (entity.description or ""):
            entity.description = req.description
            changed = True
        if changed:
            entity.update_time = req_ctx.request_time_ms
            entity.update_user = req_ctx.user_id
            db.commit()
            db.refresh(entity)
            logger.info("[kb] action=update kb_id=%s", kb_id)
        return self._to_resp(db, entity)

    def delete_kb(self, db: Session, kb_id: int, req_ctx: RequestContext) -> None:
        entity = self._get_entity_or_raise(db, kb_id)

        # 1. 级联删文档(含 blob + RAGFlow)
        doc_ids = list(db.scalars(select(TbKbDocument.id).where(TbKbDocument.kb_id == kb_id)).all())
        if doc_ids:
            self._doc_service.delete_documents(db, kb_id, doc_ids, req_ctx)

        # 2. 清理分类映射 + 分类
        cat_ids = list(db.scalars(select(TbKbCategory.id).where(TbKbCategory.kb_id == kb_id)).all())
        if cat_ids:
            db.query(TbKbCategoryMapping).filter(
                TbKbCategoryMapping.category_id.in_(cat_ids)
            ).delete(synchronize_session=False)
        db.query(TbKbCategory).filter(TbKbCategory.kb_id == kb_id).delete(synchronize_session=False)

        # 3. 删知识库 + blob 目录
        db.delete(entity)
        db.commit()
        kb_storage.delete_kb_dir(kb_id)
        logger.info(
            "[kb] action=delete kb_id=%s docs=%d cats=%d", kb_id, len(doc_ids), len(cat_ids)
        )

    # ── 读操作 ────────────────────────────────────────────────────────

    def page_kb(self, db: Session, req: KbPageReq) -> tuple[list[KbResp], int]:
        stmt = select(TbKb)
        count_stmt = select(func.count(TbKb.id))
        if req.keyword:
            kw = f"%{req.keyword}%"
            cond = or_(TbKb.code.like(kw), TbKb.name.like(kw))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        rows = db.scalars(
            stmt.order_by(TbKb.create_time.desc())
            .offset((req.page_no - 1) * req.page_size)
            .limit(req.page_size)
        ).all()
        ids = [r.id for r in rows]
        doc_stats = self._doc_counts(db, ids)
        cat_stats = self._category_counts(db, ids)
        return [
            KbResp.from_entity(r, doc_stats.get(r.id, 0), cat_stats.get(r.id, 0)) for r in rows
        ], total

    def get_kb_by_id(self, db: Session, kb_id: int) -> KbResp:
        return self._to_resp(db, self._get_entity_or_raise(db, kb_id))

    def list_kb_options(self, db: Session) -> list[KbOption]:
        rows = db.scalars(select(TbKb).order_by(TbKb.create_time.desc())).all()
        doc_stats = self._doc_counts(db, [r.id for r in rows])
        return [
            KbOption(
                id=str(r.id),
                code=r.code,
                name=r.name,
                doc_count=doc_stats.get(r.id, 0),
            )
            for r in rows
        ]

    # ── 内部 ──────────────────────────────────────────────────────────

    def _to_resp(self, db: Session, entity: TbKb) -> KbResp:
        doc_stats = self._doc_counts(db, [entity.id])
        cat_stats = self._category_counts(db, [entity.id])
        return KbResp.from_entity(entity, doc_stats.get(entity.id, 0), cat_stats.get(entity.id, 0))

    def _doc_counts(self, db: Session, kb_ids: list[int]) -> dict[int, int]:
        if not kb_ids:
            return {}
        rows = db.execute(
            select(TbKbDocument.kb_id, func.count(TbKbDocument.id))
            .where(TbKbDocument.kb_id.in_(kb_ids))
            .group_by(TbKbDocument.kb_id)
        ).all()
        return {int(kid): int(cnt) for kid, cnt in rows}

    def _category_counts(self, db: Session, kb_ids: list[int]) -> dict[int, int]:
        if not kb_ids:
            return {}
        rows = db.execute(
            select(TbKbCategory.kb_id, func.count(TbKbCategory.id))
            .where(TbKbCategory.kb_id.in_(kb_ids))
            .group_by(TbKbCategory.kb_id)
        ).all()
        return {int(kid): int(cnt) for kid, cnt in rows}

    def _get_entity_or_raise(self, db: Session, kb_id: int) -> TbKb:
        entity = db.get(TbKb, kb_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"kb not found: {kb_id}")
        return entity
