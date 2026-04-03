import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import (
    TbApp,
    TbAppSkill,
    TbAppTool,
    TbAppVersion,
    TbLlmModel,
    TbLlmProvider,
    TbSkill,
    TbTool,
)
from app.model.app_model import (
    AppCreateReq,
    AppPageReq,
    AppPublishReq,
    AppResp,
    AppUpdateReq,
    AppVersionResp,
    normalize_app_type,
    parse_app_config,
    parse_model_setting,
)

VALID_APP_TYPES = {"rag", "llm", "nl2sql", "agent", "agent_flow"}
VALID_STATUSES = {"draft", "published", "offline"}
VALID_ACCESS_SCOPES = {"internal", "api", "embed"}


class AppService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def create_app(self, db: Session, req: AppCreateReq, req_ctx: RequestContext) -> AppResp:
        app_type = normalize_app_type(req.app_type)
        self._validate_app_type(app_type)
        access_scope = self._validate_access_scope(req.access_scope or "internal")

        model_entity = self._resolve_model(db, req.provider_id, req.model_id)
        model_setting_payload = self._build_model_setting(base_setting=req.model_setting)
        app_config_payload = self._build_app_config(base_config=req.app_config)
        now = req_ctx.request_time_ms

        entity = TbApp(
            id=self._id_generator.next_id(),
            name=req.name,
            description=req.description,
            app_type=app_type,
            app_status="draft",
            app_config=(
                json.dumps(app_config_payload, ensure_ascii=False) if app_config_payload else None
            ),
            provider_id=int(req.provider_id) if req.provider_id else None,
            model_id=int(req.model_id) if req.model_id else None,
            model=model_entity.model if model_entity else None,
            model_setting=(
                json.dumps(model_setting_payload, ensure_ascii=False)
                if model_setting_payload
                else None
            ),
            access_scope=access_scope,
            rate_limit=req.rate_limit if req.rate_limit is not None else 60,
            enable_log=1 if req.enable_log is None or req.enable_log else 0,
            version_id=None,
            current_version=None,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.flush()
        self._sync_app_bindings(db, entity.id, app_type, req.tool_ids, req.skill_ids, req_ctx)
        db.commit()
        db.refresh(entity)
        return self._to_app_resp(db, entity)

    def page_app(self, db: Session, req: AppPageReq) -> tuple[list[AppResp], int]:
        stmt = select(TbApp)
        count_stmt = select(func.count(TbApp.id))

        conditions = []
        if req.keyword:
            keyword = f"%{req.keyword}%"
            conditions.append(or_(TbApp.name.like(keyword), TbApp.description.like(keyword)))
        if req.app_type:
            conditions.append(TbApp.app_type == normalize_app_type(req.app_type))
        if req.app_status:
            if req.app_status not in VALID_STATUSES:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid app_status: {req.app_status}")
            conditions.append(TbApp.app_status == req.app_status)

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbApp.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [self._to_app_resp(db, row) for row in rows], total

    def get_app_by_id(self, db: Session, app_id: int) -> AppResp:
        entity = db.get(TbApp, app_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        return self._to_app_resp(db, entity)

    def update_app(
        self, db: Session, app_id: int, req: AppUpdateReq, req_ctx: RequestContext
    ) -> AppResp:
        entity = db.get(TbApp, app_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")

        existing_app_config = parse_app_config(entity.app_config)
        existing_model_setting = parse_model_setting(entity.model_setting)
        incoming_provider_id = (
            req.provider_id if req.provider_id is not None else str(entity.provider_id or "")
        )
        incoming_model_id = req.model_id if req.model_id is not None else str(entity.model_id or "")
        model_entity = self._resolve_model(
            db,
            incoming_provider_id or None,
            incoming_model_id or None,
        )

        if req.name is not None:
            entity.name = req.name
        if req.description is not None:
            entity.description = req.description
        if req.access_scope is not None:
            entity.access_scope = self._validate_access_scope(req.access_scope)
        if req.rate_limit is not None:
            entity.rate_limit = req.rate_limit
        if req.enable_log is not None:
            entity.enable_log = 1 if req.enable_log else 0
        if req.provider_id is not None:
            entity.provider_id = int(req.provider_id) if req.provider_id else None
        if req.model_id is not None:
            entity.model_id = int(req.model_id) if req.model_id else None
            entity.model = model_entity.model if model_entity else None
        elif model_entity is not None:
            entity.model = model_entity.model

        next_app_config = self._build_app_config(
            base_config=req.app_config,
            existing_config=existing_app_config,
        )
        next_model_setting = self._build_model_setting(
            base_setting=req.model_setting,
            existing_setting=existing_model_setting,
        )
        entity.app_config = (
            json.dumps(next_app_config, ensure_ascii=False) if next_app_config else None
        )
        entity.model_setting = (
            json.dumps(next_model_setting, ensure_ascii=False) if next_model_setting else None
        )
        self._sync_app_bindings(
            db,
            app_id,
            normalize_app_type(entity.app_type),
            req.tool_ids,
            req.skill_ids,
            req_ctx,
        )
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return self._to_app_resp(db, entity)

    def delete_app(self, db: Session, app_id: int) -> None:
        entity = db.get(TbApp, app_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        db.query(TbAppVersion).filter(TbAppVersion.app_id == app_id).delete()
        db.query(TbAppTool).filter(TbAppTool.app_id == app_id).delete()
        db.query(TbAppSkill).filter(TbAppSkill.app_id == app_id).delete()
        db.delete(entity)
        db.commit()

    def publish_app(
        self, db: Session, app_id: int, req: AppPublishReq, req_ctx: RequestContext
    ) -> AppVersionResp:
        entity = db.get(TbApp, app_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")

        now = req_ctx.request_time_ms
        snapshot = {
            "name": entity.name,
            "description": entity.description,
            "app_type": normalize_app_type(entity.app_type),
            "app_status": entity.app_status,
            "app_config": parse_app_config(entity.app_config),
            "tool_ids": self._load_tool_ids(db, entity.id),
            "skill_ids": self._load_skill_ids(db, entity.id),
            "provider_id": entity.provider_id,
            "model_id": entity.model_id,
            "model": entity.model,
            "model_setting": parse_model_setting(entity.model_setting),
            "access_scope": entity.access_scope,
            "rate_limit": entity.rate_limit,
            "enable_log": bool(entity.enable_log) if entity.enable_log is not None else None,
        }

        version = TbAppVersion(
            id=self._id_generator.next_id(),
            app_id=app_id,
            version=req.version,
            version_note=req.version_note,
            app_snapshot=json.dumps(snapshot, ensure_ascii=False),
            published_time=now,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(version)

        entity.app_status = "published"
        entity.version_id = str(version.id)
        entity.current_version = req.version
        entity.update_time = now
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(version)
        return AppVersionResp.from_entity(version)

    def list_versions(self, db: Session, app_id: int) -> list[AppVersionResp]:
        entity = db.get(TbApp, app_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        rows = db.scalars(
            select(TbAppVersion)
            .where(TbAppVersion.app_id == app_id)
            .order_by(TbAppVersion.published_time.desc())
        ).all()
        return [AppVersionResp.from_entity(row) for row in rows]

    def offline_app(self, db: Session, app_id: int, req_ctx: RequestContext) -> AppResp:
        entity = db.get(TbApp, app_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        if entity.app_status != "published":
            raise ServiceError(ErrorCode.BAD_REQUEST, "only published app can go offline")

        entity.app_status = "offline"
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return self._to_app_resp(db, entity)

    def _validate_app_type(self, app_type: str) -> None:
        if app_type not in VALID_APP_TYPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid app_type: {app_type}")

    def _validate_access_scope(self, access_scope: str) -> str:
        if access_scope not in VALID_ACCESS_SCOPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid access_scope: {access_scope}")
        return access_scope

    def _resolve_model(
        self, db: Session, provider_id: str | None, model_id: str | None
    ) -> TbLlmModel | None:
        if not model_id:
            return None
        model_entity = db.get(TbLlmModel, int(model_id))
        if not model_entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "model not found")
        if provider_id:
            provider_entity = db.get(TbLlmProvider, int(provider_id))
            if not provider_entity:
                raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")
            if model_entity.provider_id != int(provider_id):
                raise ServiceError(ErrorCode.BAD_REQUEST, "model does not belong to provider")
        return model_entity

    def _build_app_config(
        self,
        base_config: dict[str, Any] | None,
        existing_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = dict(existing_config or {})
        if base_config is not None:
            config = dict(base_config)
        return config

    def _build_model_setting(
        self,
        base_setting: dict[str, Any] | None,
        existing_setting: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        setting = dict(existing_setting or {})
        if base_setting is not None:
            setting = dict(base_setting)
        return setting

    def _to_app_resp(self, db: Session, entity: TbApp) -> AppResp:
        app = AppResp.from_entity(entity)
        if normalize_app_type(entity.app_type) == "agent":
            app.tool_ids = self._load_tool_ids(db, entity.id)
            app.skill_ids = self._load_skill_ids(db, entity.id)
        return app

    def _load_tool_ids(self, db: Session, app_id: int) -> list[str]:
        rows = db.scalars(select(TbAppTool).where(TbAppTool.app_id == app_id)).all()
        return [str(row.tool_id) for row in rows]

    def _load_skill_ids(self, db: Session, app_id: int) -> list[str]:
        rows = db.scalars(select(TbAppSkill).where(TbAppSkill.app_id == app_id)).all()
        return [str(row.skill_id) for row in rows]

    def _sync_app_bindings(
        self,
        db: Session,
        app_id: int,
        app_type: str,
        tool_ids: list[str] | None,
        skill_ids: list[str] | None,
        req_ctx: RequestContext,
    ) -> None:
        # 仅 agent 应用涉及工具/技能绑定，其它类型即使传了相关字段也忽略
        if app_type != "agent":
            return
        now = req_ctx.request_time_ms
        self._sync_app_tools(db, app_id, tool_ids, req_ctx.user_id, now)
        self._sync_app_skills(db, app_id, skill_ids, req_ctx.user_id, now)

    def _sync_app_tools(
        self,
        db: Session,
        app_id: int,
        tool_ids: Any,
        user_id: int | None,
        now: int,
    ) -> None:
        if tool_ids is None:
            return
        normalized_ids = [int(item) for item in tool_ids if str(item).strip()]
        existing_rows = db.scalars(select(TbAppTool).where(TbAppTool.app_id == app_id)).all()
        existing_map = {row.tool_id: row for row in existing_rows}
        target_ids = set(normalized_ids)

        for row in existing_rows:
            if row.tool_id not in target_ids:
                db.delete(row)

        if not target_ids:
            return

        tool_rows = db.scalars(select(TbTool).where(TbTool.id.in_(target_ids))).all()
        tool_map = {row.id: row for row in tool_rows}
        missing_ids = target_ids - set(tool_map)
        if missing_ids:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")

        for tool_id in normalized_ids:
            existing = existing_map.get(tool_id)
            if existing:
                existing.tool_name = tool_map[tool_id].tool_name
                existing.update_time = now
                existing.update_user = user_id
                continue
            db.add(
                TbAppTool(
                    id=self._id_generator.next_id(),
                    app_id=app_id,
                    tool_id=tool_id,
                    tool_name=tool_map[tool_id].tool_name,
                    create_time=now,
                    update_time=now,
                    create_user=user_id,
                    update_user=user_id,
                )
            )

    def _sync_app_skills(
        self,
        db: Session,
        app_id: int,
        skill_ids: Any,
        user_id: int | None,
        now: int,
    ) -> None:
        if skill_ids is None:
            return
        normalized_ids = [int(item) for item in skill_ids if str(item).strip()]
        existing_rows = db.scalars(select(TbAppSkill).where(TbAppSkill.app_id == app_id)).all()
        existing_map = {row.skill_id: row for row in existing_rows}
        target_ids = set(normalized_ids)

        for row in existing_rows:
            if row.skill_id not in target_ids:
                db.delete(row)

        if not target_ids:
            return

        skill_rows = db.scalars(select(TbSkill).where(TbSkill.id.in_(target_ids))).all()
        skill_map = {row.id: row for row in skill_rows}
        missing_ids = target_ids - set(skill_map)
        if missing_ids:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")

        for skill_id in normalized_ids:
            existing = existing_map.get(skill_id)
            if existing:
                existing.skill_name = skill_map[skill_id].name
                existing.update_time = now
                existing.update_user = user_id
                continue
            db.add(
                TbAppSkill(
                    id=self._id_generator.next_id(),
                    app_id=app_id,
                    skill_id=skill_id,
                    skill_name=skill_map[skill_id].name,
                    create_time=now,
                    update_time=now,
                    create_user=user_id,
                    update_user=user_id,
                )
            )
