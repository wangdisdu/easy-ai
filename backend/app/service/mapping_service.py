"""分类 → RAG 库 映射业务层。

映射是 N:1 互斥:一个本地分类只能映射到一个 RAG 库。``set_mapping`` 全量覆盖
某 RAG 库映射的分类集合 —— 新增分类的文档置 ``pending`` 交向量化 worker;
移除分类的文档解绑并尽力从 RAGFlow 删除其文档。

详见 ``docs/knowledge-v2-design.md`` §2 / §8。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import (
    TbKb,
    TbKbCategory,
    TbKbCategoryMapping,
    TbKbDocument,
    TbRagDataset,
)
from app.integration import ragflow_client
from app.model.rag_dataset_model import LocalCategoryItem, MappedCategory

logger = logging.getLogger(__name__)

# 文档解绑时重置的字段
_UNBIND_FIELDS = {
    TbKbDocument.rag_dataset_id: None,
    TbKbDocument.ragflow_doc_id: None,
    TbKbDocument.vectorize_status: "not_mapped",
    TbKbDocument.error_message: None,
    TbKbDocument.parse_progress: 0.0,
    TbKbDocument.parse_begin_at: None,
    TbKbDocument.parse_duration_sec: None,
    TbKbDocument.parse_progress_msg: None,
}


class MappingService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    # ── 读 ────────────────────────────────────────────────────────────

    def get_mapped_categories(self, db: Session, dataset_id: int) -> list[MappedCategory]:
        self._get_dataset_or_raise(db, dataset_id)
        rows = db.execute(
            select(TbKbCategory, TbKb)
            .join(TbKbCategoryMapping, TbKbCategoryMapping.category_id == TbKbCategory.id)
            .join(TbKb, TbKb.id == TbKbCategory.kb_id)
            .where(TbKbCategoryMapping.rag_dataset_id == dataset_id)
        ).all()
        counts = self._doc_counts(db, [c.id for c, _ in rows])
        return [
            MappedCategory(
                category_id=str(c.id),
                category_name=c.name,
                kb_id=str(kb.id),
                kb_name=kb.name,
                doc_count=counts.get(c.id, 0),
            )
            for c, kb in rows
        ]

    def list_local_categories(self, db: Session) -> list[LocalCategoryItem]:
        """全量本地分类 + 占用情况,供映射配置面板渲染。"""
        rows = db.execute(
            select(TbKbCategory, TbKb)
            .join(TbKb, TbKb.id == TbKbCategory.kb_id)
            .order_by(TbKb.create_time.asc(), TbKbCategory.create_time.asc())
        ).all()
        mapped = {
            int(cid): int(did)
            for cid, did in db.execute(
                select(TbKbCategoryMapping.category_id, TbKbCategoryMapping.rag_dataset_id)
            ).all()
        }
        counts = self._doc_counts(db, [c.id for c, _ in rows])
        return [
            LocalCategoryItem(
                kb_id=str(kb.id),
                kb_name=kb.name,
                category_id=str(c.id),
                category_name=c.name,
                doc_count=counts.get(c.id, 0),
                mapped_dataset_id=str(mapped[c.id]) if c.id in mapped else None,
            )
            for c, kb in rows
        ]

    # ── 写 ────────────────────────────────────────────────────────────

    def set_mapping(
        self,
        db: Session,
        dataset_id: int,
        category_ids: list[str],
        req_ctx: RequestContext,
    ) -> None:
        """全量覆盖某 RAG 库映射的分类集合。"""
        dataset = self._get_dataset_or_raise(db, dataset_id)
        new_ids = {int(x) for x in category_ids}

        if new_ids:
            found = set(
                db.scalars(select(TbKbCategory.id).where(TbKbCategory.id.in_(new_ids))).all()
            )
            missing = new_ids - found
            if missing:
                raise ServiceError(
                    ErrorCode.DATA_NOT_FOUND, f"category not found: {sorted(missing)}"
                )

        current = set(
            db.scalars(
                select(TbKbCategoryMapping.category_id).where(
                    TbKbCategoryMapping.rag_dataset_id == dataset_id
                )
            ).all()
        )
        added = new_ids - current
        removed = current - new_ids

        # 互斥校验:新增分类不能已被其它 RAG 库占用
        if added:
            conflict = db.execute(
                select(TbKbCategoryMapping.category_id).where(
                    TbKbCategoryMapping.category_id.in_(added),
                    TbKbCategoryMapping.rag_dataset_id != dataset_id,
                )
            ).all()
            if conflict:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"分类已映射到其它 RAG 库: {sorted(int(c[0]) for c in conflict)}",
                )

        now = req_ctx.request_time_ms
        for cat_id in removed:
            self._unmap_category(db, dataset, cat_id, req_ctx.user_id, now)
        for cat_id in added:
            db.add(
                TbKbCategoryMapping(
                    id=self._id_generator.next_id(),
                    category_id=cat_id,
                    rag_dataset_id=dataset_id,
                    status="active",
                    create_time=now,
                    update_time=now,
                    create_user=req_ctx.user_id,
                    update_user=req_ctx.user_id,
                )
            )
            # 该分类下文档绑定到本 RAG 库并置 pending, 交向量化 worker
            db.query(TbKbDocument).filter(TbKbDocument.category_id == cat_id).update(
                {
                    TbKbDocument.rag_dataset_id: dataset_id,
                    TbKbDocument.ragflow_doc_id: None,
                    TbKbDocument.vectorize_status: "pending",
                    TbKbDocument.error_message: None,
                    TbKbDocument.parse_progress: 0.0,
                    TbKbDocument.parse_begin_at: None,
                    TbKbDocument.parse_duration_sec: None,
                    TbKbDocument.parse_progress_msg: None,
                    TbKbDocument.update_time: now,
                },
                synchronize_session=False,
            )
        db.commit()
        logger.info(
            "[mapping] action=set dataset=%s added=%d removed=%d",
            dataset_id,
            len(added),
            len(removed),
        )

    # ── 内部 ──────────────────────────────────────────────────────────

    def _unmap_category(
        self,
        db: Session,
        dataset: TbRagDataset,
        cat_id: int,
        user_id: int | None,
        now: int,
    ) -> None:
        db.query(TbKbCategoryMapping).filter(
            TbKbCategoryMapping.category_id == cat_id,
            TbKbCategoryMapping.rag_dataset_id == dataset.id,
        ).delete(synchronize_session=False)

        docs = db.scalars(
            select(TbKbDocument).where(
                TbKbDocument.category_id == cat_id,
                TbKbDocument.rag_dataset_id == dataset.id,
            )
        ).all()
        ragflow_ids = [d.ragflow_doc_id for d in docs if d.ragflow_doc_id]
        if ragflow_ids and dataset.ragflow_dataset_id and settings.ragflow_enabled:
            try:
                ragflow_client.get_client().delete_documents(
                    dataset.ragflow_dataset_id, ragflow_ids, user_id=user_id
                )
            except ragflow_client.RagflowClientError as e:
                logger.warning(
                    "[mapping] best-effort delete ragflow docs failed dataset=%s: %s",
                    dataset.id,
                    e,
                )
        db.query(TbKbDocument).filter(
            TbKbDocument.category_id == cat_id,
            TbKbDocument.rag_dataset_id == dataset.id,
        ).update(
            {**_UNBIND_FIELDS, TbKbDocument.update_time: now},
            synchronize_session=False,
        )

    def _doc_counts(self, db: Session, cat_ids: list[int]) -> dict[int, int]:
        if not cat_ids:
            return {}
        rows = db.execute(
            select(TbKbDocument.category_id, func.count(TbKbDocument.id))
            .where(TbKbDocument.category_id.in_(cat_ids))
            .group_by(TbKbDocument.category_id)
        ).all()
        return {int(cid): int(cnt) for cid, cnt in rows}

    def _get_dataset_or_raise(self, db: Session, dataset_id: int) -> TbRagDataset:
        entity = db.get(TbRagDataset, dataset_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"rag_dataset not found: {dataset_id}")
        return entity
