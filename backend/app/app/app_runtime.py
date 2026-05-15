from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.db.schema import TbApp, TbLlmModel, TbLlmProvider
from app.model.app_model import parse_app_config, parse_model_setting
from app.model.open_model import LiteLLMRuntimeConfig


class AppRuntime:
    """应用域共享运行时公共组件。"""

    def get_app(self, db: Session, app_id: int) -> TbApp:
        app = db.get(TbApp, app_id)
        if not app:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        return app

    def get_app_config(self, db: Session, app_id: int) -> dict:
        app = self.get_app(db, app_id)
        return parse_app_config(app.app_config)

    def build_chat_runtime(self, db: Session, app_id: int) -> LiteLLMRuntimeConfig:
        return self._build_runtime(db, app_id)

    def build_embedding_runtime(self, db: Session, app_id: int) -> LiteLLMRuntimeConfig:
        return self._build_runtime(db, app_id)

    def build_chat_runtime_by_model(
        self,
        db: Session,
        *,
        provider_id: str,
        model_id: str,
        model_setting: dict | None = None,
    ) -> LiteLLMRuntimeConfig:
        return self._build_runtime_by_model(
            db=db,
            provider_id=provider_id,
            model_id=model_id,
            model_setting=model_setting,
        )

    def build_chat_runtime_by_model_name(
        self,
        db: Session,
        *,
        model_name: str,
        model_setting: dict | None = None,
        model_type: str = "LLM",
    ) -> LiteLLMRuntimeConfig:
        """按模型 name 解析(RAG summary / 子任务模型场景)。重名时按 id 升序取
        首个 active 模型 + active provider。"""
        rows = db.scalars(
            select(TbLlmModel)
            .where(TbLlmModel.model == model_name, TbLlmModel.model_type == model_type)
            .order_by(TbLlmModel.id.asc())
        ).all()
        for m in rows:
            if m.status != "active":
                continue
            provider = db.get(TbLlmProvider, m.provider_id) if m.provider_id else None
            if not provider or provider.status not in {"active", "connected"}:
                continue
            return self._build_runtime_by_model(
                db=db,
                provider_id=str(provider.id),
                model_id=str(m.id),
                model_setting=model_setting,
            )
        raise ServiceError(
            ErrorCode.DATA_NOT_FOUND,
            f"model {model_name!r} ({model_type}) not found or no active provider",
        )

    def _build_runtime(self, db: Session, app_id: int) -> LiteLLMRuntimeConfig:
        app = self.get_app(db, app_id)
        if not app.model_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "app model not configured")

        return self._build_runtime_by_model(
            db=db,
            provider_id=str(app.provider_id or ""),
            model_id=str(app.model_id),
            model_setting=parse_model_setting(app.model_setting),
            app_model=app.model,
        )

    def _build_runtime_by_model(
        self,
        db: Session,
        *,
        provider_id: str,
        model_id: str,
        model_setting: dict | None = None,
        app_model: str | None = None,
    ) -> LiteLLMRuntimeConfig:
        if not provider_id or not model_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "provider and model must be configured")

        model_entity = db.get(TbLlmModel, int(model_id))
        if not model_entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "model not found")
        if model_entity.status != "active":
            raise ServiceError(ErrorCode.BAD_REQUEST, "model is inactive")
        if model_entity.provider_id != int(provider_id):
            raise ServiceError(ErrorCode.BAD_REQUEST, "model does not belong to provider")

        provider_entity = (
            db.get(TbLlmProvider, model_entity.provider_id) if model_entity.provider_id else None
        )
        if not provider_entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")
        if provider_entity.status not in {"active", "connected"}:
            raise ServiceError(ErrorCode.BAD_REQUEST, "provider is inactive")

        return LiteLLMRuntimeConfig(
            model=model_entity.model,
            base_url=provider_entity.base_url.rstrip("/"),
            api_key=provider_entity.api_key,
            provider_id=provider_entity.id,
            model_id=model_entity.id,
            model_setting=model_setting or {},
            max_input_tokens=model_entity.max_input_tokens,
        )
