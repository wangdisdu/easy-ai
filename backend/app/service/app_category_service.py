from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbAppCategory, TbAppCategoryRel
from app.model.app_category_model import (
    AppCategoryCreateReq,
    AppCategoryPageReq,
    AppCategoryRef,
    AppCategoryResp,
    AppCategoryUpdateReq,
)

# 中间表 target_type 合法值
TARGET_APP = "app"
TARGET_SKILL = "skill"
VALID_TARGET_TYPES = {TARGET_APP, TARGET_SKILL}


class AppCategoryService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    # ── CRUD ──

    def create_category(
        self, db: Session, req: AppCategoryCreateReq, req_ctx: RequestContext
    ) -> AppCategoryResp:
        if db.scalar(select(TbAppCategory).where(TbAppCategory.code == req.code)):
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "category code already exists")

        now = req_ctx.request_time_ms
        entity = TbAppCategory(
            id=self._id_generator.next_id(),
            code=req.code,
            name=req.name,
            description=req.description,
            sort_order=req.sort_order,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return AppCategoryResp.from_entity(entity)

    def page_category(
        self, db: Session, req: AppCategoryPageReq
    ) -> tuple[list[AppCategoryResp], int]:
        stmt = select(TbAppCategory)
        count_stmt = select(func.count(TbAppCategory.id))
        if req.keyword:
            kw = f"%{req.keyword}%"
            cond = or_(TbAppCategory.code.like(kw), TbAppCategory.name.like(kw))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbAppCategory.sort_order.asc(), TbAppCategory.create_time.desc())
            .offset(offset)
            .limit(req.page_size)
        ).all()
        return [AppCategoryResp.from_entity(r) for r in rows], total

    def list_all(self, db: Session) -> list[AppCategoryResp]:
        rows = db.scalars(
            select(TbAppCategory).order_by(
                TbAppCategory.sort_order.asc(), TbAppCategory.create_time.desc()
            )
        ).all()
        return [AppCategoryResp.from_entity(r) for r in rows]

    def get_category_by_id(self, db: Session, category_id: int) -> AppCategoryResp:
        entity = db.get(TbAppCategory, category_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "category not found")
        return AppCategoryResp.from_entity(entity)

    def update_category(
        self,
        db: Session,
        category_id: int,
        req: AppCategoryUpdateReq,
        req_ctx: RequestContext,
    ) -> AppCategoryResp:
        entity = db.get(TbAppCategory, category_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "category not found")

        if req.name is not None:
            entity.name = req.name
        if req.description is not None:
            entity.description = req.description
        if req.sort_order is not None:
            entity.sort_order = req.sort_order

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return AppCategoryResp.from_entity(entity)

    def delete_category(self, db: Session, category_id: int) -> None:
        entity = db.get(TbAppCategory, category_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "category not found")

        used = db.scalar(
            select(func.count(TbAppCategoryRel.id)).where(
                TbAppCategoryRel.category_id == category_id
            )
        )
        if (used or 0) > 0:
            raise ServiceError(ErrorCode.BAD_REQUEST, "category is in use, cannot delete")

        db.delete(entity)
        db.commit()

    # ── 关系表辅助方法（供 app_service / skill_service 复用）──

    def validate_category_ids(self, db: Session, category_ids: list[int]) -> None:
        if not category_ids:
            return
        ids = set(category_ids)
        rows = db.scalars(select(TbAppCategory.id).where(TbAppCategory.id.in_(ids))).all()
        missing = ids - set(rows)
        if missing:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "category not found")

    def sync_relations(
        self,
        db: Session,
        target_type: str,
        target_id: int,
        category_ids: list[int],
        req_ctx: RequestContext,
    ) -> None:
        """全量同步某 target 的分类关系；category_ids=[] 表示清空。"""
        if target_type not in VALID_TARGET_TYPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid target_type: {target_type}")

        self.validate_category_ids(db, category_ids)

        existing_rows = db.scalars(
            select(TbAppCategoryRel).where(
                TbAppCategoryRel.target_type == target_type,
                TbAppCategoryRel.target_id == target_id,
            )
        ).all()
        existing_set = {row.category_id for row in existing_rows}
        target_set = set(category_ids)

        for row in existing_rows:
            if row.category_id not in target_set:
                db.delete(row)

        now = req_ctx.request_time_ms
        for cid in target_set - existing_set:
            db.add(
                TbAppCategoryRel(
                    id=self._id_generator.next_id(),
                    category_id=cid,
                    target_type=target_type,
                    target_id=target_id,
                    create_time=now,
                    update_time=now,
                    create_user=req_ctx.user_id,
                    update_user=req_ctx.user_id,
                )
            )

    def delete_relations_for_target(self, db: Session, target_type: str, target_id: int) -> None:
        db.query(TbAppCategoryRel).filter(
            TbAppCategoryRel.target_type == target_type,
            TbAppCategoryRel.target_id == target_id,
        ).delete()

    def load_category_ids_map(
        self, db: Session, target_type: str, target_ids: list[int]
    ) -> dict[int, list[int]]:
        if not target_ids:
            return {}
        rows = db.scalars(
            select(TbAppCategoryRel).where(
                TbAppCategoryRel.target_type == target_type,
                TbAppCategoryRel.target_id.in_(target_ids),
            )
        ).all()
        result: dict[int, list[int]] = {tid: [] for tid in target_ids}
        for r in rows:
            result.setdefault(r.target_id, []).append(r.category_id)
        return result

    def load_refs_map(
        self, db: Session, target_type: str, target_ids: list[int]
    ) -> dict[int, list[AppCategoryRef]]:
        """按目标加载分类引用（id + name），列表接口使用。"""
        if not target_ids:
            return {}
        rows = db.execute(
            select(
                TbAppCategoryRel.target_id,
                TbAppCategory.id,
                TbAppCategory.name,
                TbAppCategory.sort_order,
            )
            .join(TbAppCategory, TbAppCategory.id == TbAppCategoryRel.category_id)
            .where(
                TbAppCategoryRel.target_type == target_type,
                TbAppCategoryRel.target_id.in_(target_ids),
            )
            .order_by(TbAppCategory.sort_order.asc())
        ).all()
        result: dict[int, list[AppCategoryRef]] = {tid: [] for tid in target_ids}
        for target_id, cid, cname, _ in rows:
            result.setdefault(target_id, []).append(AppCategoryRef(id=str(cid), name=cname))
        return result

    def target_ids_by_category(self, db: Session, target_type: str, category_id: int) -> list[int]:
        rows = db.scalars(
            select(TbAppCategoryRel.target_id).where(
                TbAppCategoryRel.target_type == target_type,
                TbAppCategoryRel.category_id == category_id,
            )
        ).all()
        return list(rows)
