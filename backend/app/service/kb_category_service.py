"""KB 文档分类业务层(树形, 单归属)。

分类是纯 easy-ai 侧组织维度, RAGFlow 完全不感知, 因此本服务**不调用
任何 RAGFlow 接口**。唯一的上游副作用在 ``delete_category`` 级联删除文档
时——复用 ``KbDocumentService.delete_documents``(它内部先删 RAGFlow)。

树用物化路径表示:``id_path = /<id>/<id>/...`` 以自身结尾。
- 子树 = ``id_path LIKE '<node.id_path>%'``(含自身)
- 移动 = 重写自身 + 全部后代的 id_path / level
- 同级(kb_id + parent_id)下 name 唯一

详见 docs/knowledge-v2-design.md。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from app.model.kb_model import (
    KbCategoryCreateReq,
    KbCategoryDeletePreview,
    KbCategoryNode,
    KbCategoryUpdateReq,
)
from app.service.kb_document_service import KbDocumentService

logger = logging.getLogger(__name__)

# 树最大层级(根级=1)。约束路径长度与前端展开深度, 见设计讨论。
MAX_DEPTH = 5

# 子分类已停用: 分类降为单层扁平(知识库/分类/文档)。
# schema 仍保留 parent_id/id_path 树结构, 翻 True 即可恢复嵌套, 无需迁移。
SUBCATEGORY_ENABLED = False


class KbCategoryService:
    def __init__(self, id_generator: SnowflakeGenerator, doc_service: KbDocumentService) -> None:
        self._id_generator = id_generator
        # 级联删除时复用其 delete_documents(内部会删 RAGFlow)
        self._doc_service = doc_service

    # ── 读 ────────────────────────────────────────────────────────────

    def get_tree(self, db: Session, kb_id: int) -> list[KbCategoryNode]:
        """返回 kb 的分类树(嵌套)。每个节点 doc_count 为直挂该节点的文档数。"""
        self._get_kb_or_raise(db, kb_id)
        rows = db.scalars(
            select(TbKbCategory)
            .where(TbKbCategory.kb_id == kb_id)
            .order_by(
                TbKbCategory.level.asc(), TbKbCategory.sort.asc(), TbKbCategory.create_time.asc()
            )
        ).all()
        # 直挂文档数(不含子树): group by category_id
        counts = dict(
            db.execute(
                select(TbKbDocument.category_id, func.count(TbKbDocument.id))
                .where(TbKbDocument.kb_id == kb_id)
                .group_by(TbKbDocument.category_id)
            ).all()
        )
        # 分类 → RAG 库 映射(回填节点的 rag_dataset_id / name)
        cat_ids = [r.id for r in rows]
        mapping: dict[int, tuple[str, str]] = {}
        if cat_ids:
            for cid, did, dname in db.execute(
                select(TbKbCategoryMapping.category_id, TbRagDataset.id, TbRagDataset.name)
                .join(TbRagDataset, TbRagDataset.id == TbKbCategoryMapping.rag_dataset_id)
                .where(TbKbCategoryMapping.category_id.in_(cat_ids))
            ).all():
                mapping[int(cid)] = (str(did), dname)
        nodes: dict[int, KbCategoryNode] = {
            r.id: KbCategoryNode.from_entity(
                r,
                int(counts.get(r.id, 0)),
                mapping.get(r.id, (None, None))[0],
                mapping.get(r.id, (None, None))[1],
            )
            for r in rows
        }
        roots: list[KbCategoryNode] = []
        for r in rows:
            node = nodes[r.id]
            parent = nodes.get(r.parent_id)
            if parent is not None:
                parent.children.append(node)
            else:
                roots.append(node)
        return roots

    def resolve_subtree_ids(self, db: Session, kb_id: int, category_id: int) -> list[int]:
        """返回 category_id 及其所有后代分类 id(供文档列表 recursive 过滤用)。
        category_id<=0 视作"未分类", 返回 [0]。"""
        if category_id <= 0:
            return [0]
        node = self._get_category_or_raise(db, kb_id, category_id)
        rows = db.scalars(
            select(TbKbCategory.id).where(
                TbKbCategory.kb_id == kb_id,
                TbKbCategory.id_path.like(f"{node.id_path}%"),
            )
        ).all()
        return list(rows)

    # ── 写 ────────────────────────────────────────────────────────────

    def create_category(
        self, db: Session, kb_id: int, req: KbCategoryCreateReq, req_ctx: RequestContext
    ) -> KbCategoryNode:
        self._get_kb_or_raise(db, kb_id)
        parent_id = int(req.parent_id or 0)
        if parent_id != 0 and not SUBCATEGORY_ENABLED:
            raise ServiceError(ErrorCode.BAD_REQUEST, "subcategory is disabled")
        if parent_id == 0:
            level = 1
            parent_path = "/"
        else:
            parent = self._get_category_or_raise(db, kb_id, parent_id)
            level = parent.level + 1
            if level > MAX_DEPTH:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"category depth exceeds limit {MAX_DEPTH}",
                )
            parent_path = parent.id_path
        self._assert_sibling_name_free(db, kb_id, parent_id, req.name, exclude_id=None)

        now = req_ctx.request_time_ms
        cid = self._id_generator.next_id()
        entity = TbKbCategory(
            id=cid,
            kb_id=kb_id,
            name=req.name,
            parent_id=parent_id,
            id_path=f"{parent_path}{cid}/",
            level=level,
            sort=0,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        logger.info("[kb] action=create_category kb_id=%s cid=%s", kb_id, cid)
        return KbCategoryNode.from_entity(entity, 0)

    def update_category(
        self,
        db: Session,
        kb_id: int,
        category_id: int,
        req: KbCategoryUpdateReq,
        req_ctx: RequestContext,
    ) -> KbCategoryNode:
        entity = self._get_category_or_raise(db, kb_id, category_id)

        # 移动: parent_id 传入且与现父不同(子分类停用时禁止改父)
        if req.parent_id is not None and int(req.parent_id) != entity.parent_id:
            if not SUBCATEGORY_ENABLED:
                raise ServiceError(ErrorCode.BAD_REQUEST, "subcategory is disabled")
            self._move(db, kb_id, entity, int(req.parent_id))

        if req.name is not None and req.name != entity.name:
            self._assert_sibling_name_free(
                db, kb_id, entity.parent_id, req.name, exclude_id=entity.id
            )
            entity.name = req.name
        if req.sort is not None:
            entity.sort = req.sort

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return KbCategoryNode.from_entity(entity)

    def delete_category(
        self,
        db: Session,
        kb_id: int,
        category_id: int,
        confirm: bool,
        req_ctx: RequestContext,
    ) -> KbCategoryDeletePreview:
        """级联删除: 子树全部分类 + 其下文档(文档走 RAGFlow 同步删除)。

        ``confirm=False`` 时只返回影响面(dry-run), 不做任何删除。
        """
        node = self._get_category_or_raise(db, kb_id, category_id)
        sub_cat_ids = list(
            db.scalars(
                select(TbKbCategory.id).where(
                    TbKbCategory.kb_id == kb_id,
                    TbKbCategory.id_path.like(f"{node.id_path}%"),
                )
            ).all()
        )
        doc_ids = list(
            db.scalars(
                select(TbKbDocument.id).where(
                    TbKbDocument.kb_id == kb_id,
                    TbKbDocument.category_id.in_(sub_cat_ids),
                )
            ).all()
        )
        if not confirm:
            return KbCategoryDeletePreview(
                deleted=False,
                category_count=len(sub_cat_ids),
                document_count=len(doc_ids),
            )

        # 先删文档(含 blob + RAGFlow), 失败 fail-fast 不动分类
        if doc_ids:
            self._doc_service.delete_documents(db, kb_id, doc_ids, req_ctx)
        # 清理这些分类的 RAG 库映射
        db.query(TbKbCategoryMapping).filter(
            TbKbCategoryMapping.category_id.in_(sub_cat_ids)
        ).delete(synchronize_session=False)
        db.query(TbKbCategory).filter(
            TbKbCategory.kb_id == kb_id, TbKbCategory.id.in_(sub_cat_ids)
        ).delete(synchronize_session=False)
        db.commit()
        logger.info(
            "[kb] action=delete_category kb_id=%s cid=%s cats=%d docs=%d",
            kb_id,
            category_id,
            len(sub_cat_ids),
            len(doc_ids),
        )
        return KbCategoryDeletePreview(
            deleted=True,
            category_count=len(sub_cat_ids),
            document_count=len(doc_ids),
        )

    # ── 内部 ──────────────────────────────────────────────────────────

    def _move(self, db: Session, kb_id: int, entity: TbKbCategory, new_parent_id: int) -> None:
        """把 entity 子树挂到 new_parent_id 下, 重写自身 + 全部后代 id_path/level。"""
        if new_parent_id == entity.id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "cannot move category into itself")
        if new_parent_id == 0:
            new_parent_path, base_level = "/", 1
        else:
            new_parent = self._get_category_or_raise(db, kb_id, new_parent_id)
            # 禁止移入自身子树(环)
            if new_parent.id_path.startswith(entity.id_path):
                raise ServiceError(
                    ErrorCode.BAD_REQUEST, "cannot move category into its own subtree"
                )
            new_parent_path, base_level = new_parent.id_path, new_parent.level + 1

        old_path = entity.id_path
        new_path = f"{new_parent_path}{entity.id}/"
        depth_shift = base_level - entity.level
        # 子树深度上限校验: 当前子树最大 level + 位移
        max_sub_level = (
            db.scalar(
                select(func.max(TbKbCategory.level)).where(
                    TbKbCategory.kb_id == kb_id,
                    TbKbCategory.id_path.like(f"{old_path}%"),
                )
            )
            or entity.level
        )
        if max_sub_level + depth_shift > MAX_DEPTH:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"move would exceed depth limit {MAX_DEPTH}")

        subtree = db.scalars(
            select(TbKbCategory).where(
                TbKbCategory.kb_id == kb_id,
                TbKbCategory.id_path.like(f"{old_path}%"),
            )
        ).all()
        for c in subtree:
            c.id_path = new_path + c.id_path[len(old_path) :]
            c.level = c.level + depth_shift
        entity.parent_id = new_parent_id

    def _assert_sibling_name_free(
        self, db: Session, kb_id: int, parent_id: int, name: str, exclude_id: int | None
    ) -> None:
        stmt = select(TbKbCategory.id).where(
            TbKbCategory.kb_id == kb_id,
            TbKbCategory.parent_id == parent_id,
            TbKbCategory.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(TbKbCategory.id != exclude_id)
        if db.scalar(stmt):
            raise ServiceError(ErrorCode.DATA_DUPLICATE, f"category name already exists: {name}")

    def _get_kb_or_raise(self, db: Session, kb_id: int) -> TbKb:
        entity = db.get(TbKb, kb_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"kb not found: {kb_id}")
        return entity

    def _get_category_or_raise(self, db: Session, kb_id: int, category_id: int) -> TbKbCategory:
        entity = db.get(TbKbCategory, category_id)
        if not entity or entity.kb_id != kb_id:
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND,
                f"kb_category not found: kb={kb_id} cat={category_id}",
            )
        return entity
