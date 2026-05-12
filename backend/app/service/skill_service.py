import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbSkill, TbSkillTool, TbSkillVersion
from app.model.skill_model import (
    SkillCreateReq,
    SkillPageReq,
    SkillPublishReq,
    SkillResp,
    SkillToolResp,
    SkillUpdateReq,
    SkillVersionResp,
)
from app.service.app_category_service import TARGET_SKILL, AppCategoryService

VALID_STATUSES = {"enabled", "disabled", "draft"}

# 与 DeepAgents 内置 subagent 同名会顶替框架默认的 general-purpose 通用代理
# （见 deepagents/graph.py 的 insert 判定）。大小写不敏感地拦截。
RESERVED_SKILL_NAMES = frozenset({"general-purpose"})


def _validate_skill_name(name: str | None) -> None:
    if name is None:
        return
    if name.strip().lower() in RESERVED_SKILL_NAMES:
        raise ServiceError(
            ErrorCode.BAD_REQUEST,
            f"skill name '{name}' is reserved",
        )


def _to_int_ids(ids: list[str]) -> list[int]:
    return [int(x) for x in ids if str(x).strip()]


class SkillService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._category_service = AppCategoryService(id_generator)

    # ── Helpers ──

    def _load_skill_tools(
        self, db: Session, skill_ids: list[int]
    ) -> dict[int, list[SkillToolResp]]:
        if not skill_ids:
            return {}
        rows = db.scalars(select(TbSkillTool).where(TbSkillTool.skill_id.in_(skill_ids))).all()
        result: dict[int, list[SkillToolResp]] = {}
        for row in rows:
            result.setdefault(row.skill_id, []).append(
                SkillToolResp(
                    tool_id=str(row.tool_id),
                    tool_source=row.tool_source,
                    tool_name=row.tool_name,
                )
            )
        return result

    def _sync_skill_tools(
        self, db: Session, skill_id: int, tools: list, now: int, user_id: int | None
    ) -> None:
        db.query(TbSkillTool).filter(TbSkillTool.skill_id == skill_id).delete()
        for t in tools:
            db.add(
                TbSkillTool(
                    id=self._id_generator.next_id(),
                    skill_id=skill_id,
                    tool_id=int(t.tool_id) if t.tool_id and t.tool_id != "0" else 0,
                    tool_source=t.tool_source,
                    tool_name=t.tool_name,
                    create_time=now,
                    update_time=now,
                    create_user=user_id,
                    update_user=user_id,
                )
            )

    # ── CRUD ──

    def create_skill(self, db: Session, req: SkillCreateReq, req_ctx: RequestContext) -> SkillResp:
        _validate_skill_name(req.name)
        now = req_ctx.request_time_ms
        entity = TbSkill(
            id=self._id_generator.next_id(),
            name=req.name,
            description=req.description,
            instruction=req.instruction,
            skill_status="draft",
            current_version=None,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.flush()
        if req.tools:
            self._sync_skill_tools(db, entity.id, req.tools, now, req_ctx.user_id)
        if req.category_ids is not None:
            self._category_service.sync_relations(
                db, TARGET_SKILL, entity.id, _to_int_ids(req.category_ids), req_ctx
            )
        db.commit()
        db.refresh(entity)
        tools_map = self._load_skill_tools(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity, tools_map.get(entity.id, []), refs_map.get(entity.id, [])
        )

    def page_skill(self, db: Session, req: SkillPageReq) -> tuple[list[SkillResp], int]:
        stmt = select(TbSkill)
        count_stmt = select(func.count(TbSkill.id))

        conditions = []
        if req.keyword:
            kw = f"%{req.keyword}%"
            conditions.append(or_(TbSkill.name.like(kw), TbSkill.description.like(kw)))
        if req.category_id:
            target_ids = self._category_service.target_ids_by_category(
                db, TARGET_SKILL, int(req.category_id)
            )
            if not target_ids:
                return [], 0
            conditions.append(TbSkill.id.in_(target_ids))
        if req.skill_status:
            conditions.append(TbSkill.skill_status == req.skill_status)

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbSkill.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()

        skill_ids = [r.id for r in rows]
        tools_map = self._load_skill_tools(db, skill_ids)
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, skill_ids)
        return [
            SkillResp.from_entity(r, tools_map.get(r.id, []), refs_map.get(r.id, [])) for r in rows
        ], total

    def get_skill_by_id(self, db: Session, skill_id: int) -> SkillResp:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        tools_map = self._load_skill_tools(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity, tools_map.get(entity.id, []), refs_map.get(entity.id, [])
        )

    def update_skill(
        self, db: Session, skill_id: int, req: SkillUpdateReq, req_ctx: RequestContext
    ) -> SkillResp:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")

        if req.name is not None:
            _validate_skill_name(req.name)
            entity.name = req.name
        if req.description is not None:
            entity.description = req.description
        if req.instruction is not None:
            entity.instruction = req.instruction

        now = req_ctx.request_time_ms
        if req.tools is not None:
            self._sync_skill_tools(db, skill_id, req.tools, now, req_ctx.user_id)
        if req.category_ids is not None:
            self._category_service.sync_relations(
                db, TARGET_SKILL, skill_id, _to_int_ids(req.category_ids), req_ctx
            )

        entity.update_time = now
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        tools_map = self._load_skill_tools(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity, tools_map.get(entity.id, []), refs_map.get(entity.id, [])
        )

    def delete_skill(self, db: Session, skill_id: int) -> None:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        db.query(TbSkillTool).filter(TbSkillTool.skill_id == skill_id).delete()
        db.query(TbSkillVersion).filter(TbSkillVersion.skill_id == skill_id).delete()
        self._category_service.delete_relations_for_target(db, TARGET_SKILL, skill_id)
        db.delete(entity)
        db.commit()

    def toggle_skill_status(
        self, db: Session, skill_id: int, status: str, req_ctx: RequestContext
    ) -> SkillResp:
        if status not in VALID_STATUSES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid status: {status}")
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        entity.skill_status = status
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        tools_map = self._load_skill_tools(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity, tools_map.get(entity.id, []), refs_map.get(entity.id, [])
        )

    # ── Publish ──

    def publish_skill(
        self, db: Session, skill_id: int, req: SkillPublishReq, req_ctx: RequestContext
    ) -> SkillVersionResp:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")

        tools_map = self._load_skill_tools(db, [entity.id])
        tool_list = tools_map.get(entity.id, [])
        category_ids = self._category_service.load_category_ids_map(
            db, TARGET_SKILL, [entity.id]
        ).get(entity.id, [])

        now = req_ctx.request_time_ms
        snapshot = json.dumps(
            {
                "name": entity.name,
                "description": entity.description,
                "category_ids": category_ids,
                "instruction": entity.instruction,
                "tools": [
                    {"tool_source": t.tool_source, "tool_name": t.tool_name, "tool_id": t.tool_id}
                    for t in tool_list
                ],
            },
            ensure_ascii=False,
        )

        version = TbSkillVersion(
            id=self._id_generator.next_id(),
            skill_id=skill_id,
            version=req.version,
            version_note=req.version_note,
            skill_snapshot=snapshot,
            published_time=now,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(version)

        entity.skill_status = "enabled"
        entity.current_version = req.version
        entity.update_time = now
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(version)
        return SkillVersionResp.from_entity(version)

    def list_skill_versions(self, db: Session, skill_id: int) -> list[SkillVersionResp]:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        rows = db.scalars(
            select(TbSkillVersion)
            .where(TbSkillVersion.skill_id == skill_id)
            .order_by(TbSkillVersion.published_time.desc())
        ).all()
        return [SkillVersionResp.from_entity(r) for r in rows]
