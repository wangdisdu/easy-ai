import logging

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbLlmModel, TbLlmProvider
from app.model.llm_model import (
    LlmModelCreateReq,
    LlmModelResp,
    LlmModelUpdateReq,
    LlmProviderCreateReq,
    LlmProviderPageReq,
    LlmProviderResp,
    LlmProviderUpdateReq,
)

VALID_PROVIDER_TYPES = {"openai", "openai_compatible", "anthropic", "gemini", "azure", "ollama"}
VALID_MODEL_TYPES = {"LLM", "Embedding", "Rerank", "Vision", "OCR"}
VALID_MODEL_STATUSES = {"active", "inactive"}
LEGACY_PROVIDER_TYPE_MAP = {
    "OpenAI Compatible": "openai",
    "Ollama": "ollama",
}

PREDEFINED_PROVIDERS: dict[str, str] = {
    "OpenAI": "https://api.openai.com/v1",
    "阿里云百炼": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "智谱模型": "https://open.bigmodel.cn/api/paas/v4",
    "火山引擎": "https://ark.cn-beijing.volces.com/api/v3",
    "硅基流动": "https://api.siliconflow.cn/v1",
}

logger = logging.getLogger(__name__)


class LlmService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id = id_generator

    def _normalize_provider_type(self, provider_type: str) -> str:
        return LEGACY_PROVIDER_TYPE_MAP.get(provider_type, provider_type)

    # ── Provider CRUD ──

    def create_provider(
        self, db: Session, req: LlmProviderCreateReq, req_ctx: RequestContext
    ) -> LlmProviderResp:
        provider_type = self._normalize_provider_type(req.provider_type)
        if provider_type not in VALID_PROVIDER_TYPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid provider_type: {req.provider_type}")

        existing = db.scalar(select(TbLlmProvider).where(TbLlmProvider.name == req.name))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "provider name already exists")

        now = req_ctx.request_time_ms
        provider = TbLlmProvider(
            id=self._id.next_id(),
            name=req.name,
            provider_type=provider_type,
            base_url=req.base_url,
            api_key=req.api_key or None,
            status="unconfigured",
            last_check=None,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(provider)
        db.flush()

        model_resps: list[LlmModelResp] = []
        for m in req.models:
            if m.model_type not in VALID_MODEL_TYPES:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid model_type: {m.model_type}")
            entity = TbLlmModel(
                id=self._id.next_id(),
                provider_id=provider.id,
                model=m.model,
                model_type=m.model_type,
                status="active",
                max_input_tokens=m.max_input_tokens,
                create_time=now,
                update_time=now,
                create_user=req_ctx.user_id,
                update_user=req_ctx.user_id,
            )
            db.add(entity)
            model_resps.append(LlmModelResp.from_entity(entity))

        db.commit()
        db.refresh(provider)
        return LlmProviderResp.from_entity(provider, model_resps)

    def page_provider(
        self, db: Session, req: LlmProviderPageReq
    ) -> tuple[list[LlmProviderResp], int]:
        stmt = select(TbLlmProvider)
        count_stmt = select(func.count(TbLlmProvider.id))

        if req.keyword:
            kw = f"%{req.keyword}%"
            cond = or_(TbLlmProvider.name.like(kw), TbLlmProvider.base_url.like(kw))
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbLlmProvider.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [self._to_provider_resp(db, r) for r in rows], total

    def get_provider(self, db: Session, provider_id: int) -> LlmProviderResp:
        entity = db.get(TbLlmProvider, provider_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")
        return self._to_provider_resp(db, entity)

    def update_provider(
        self,
        db: Session,
        provider_id: int,
        req: LlmProviderUpdateReq,
        req_ctx: RequestContext,
    ) -> LlmProviderResp:
        entity = db.get(TbLlmProvider, provider_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")

        if req.name is not None and req.name != entity.name:
            dup = db.scalar(select(TbLlmProvider).where(TbLlmProvider.name == req.name))
            if dup:
                raise ServiceError(ErrorCode.DATA_DUPLICATE, "provider name already exists")
            entity.name = req.name

        if req.provider_type is not None:
            provider_type = self._normalize_provider_type(req.provider_type)
            if provider_type not in VALID_PROVIDER_TYPES:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST, f"invalid provider_type: {req.provider_type}"
                )
            entity.provider_type = provider_type
        if req.base_url is not None:
            entity.base_url = req.base_url
        if req.api_key is not None:
            entity.api_key = req.api_key or None

        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return self._to_provider_resp(db, entity)

    def delete_provider(self, db: Session, provider_id: int) -> None:
        entity = db.get(TbLlmProvider, provider_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")
        db.query(TbLlmModel).filter(TbLlmModel.provider_id == provider_id).delete()
        db.delete(entity)
        db.commit()

    def test_connection(
        self, db: Session, provider_id: int, req_ctx: RequestContext
    ) -> LlmProviderResp:
        entity = db.get(TbLlmProvider, provider_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")

        try:
            model_count = len(self.list_available_models(db, provider_id))
            entity.status = "connected"
            logger.info(
                "llm provider connection test succeeded: provider_id=%s, name=%s, "
                "provider_type=%s, base_url=%s, model_count=%s",
                provider_id,
                entity.name,
                entity.provider_type,
                entity.base_url,
                model_count,
            )
        except Exception as e:
            logger.exception(
                "llm provider connection test failed: provider_id=%s, name=%s, "
                "provider_type=%s, base_url=%s, user_id=%s, error_type=%s, error=%s",
                provider_id,
                entity.name,
                entity.provider_type,
                entity.base_url,
                req_ctx.user_id,
                type(e).__name__,
                str(e),
            )
            entity.status = "error"

        entity.last_check = req_ctx.request_time_ms
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return self._to_provider_resp(db, entity)

    def list_available_models(self, db: Session, provider_id: int) -> list[str]:
        entity = db.get(TbLlmProvider, provider_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")
        return self._fetch_provider_models(entity)

    def _fetch_provider_models(self, entity: TbLlmProvider) -> list[str]:
        provider_type = self._normalize_provider_type(entity.provider_type)
        if provider_type in {"openai", "openai_compatible", "anthropic", "gemini", "azure"}:
            return self._fetch_openai_compatible_models(entity)
        if provider_type == "ollama":
            return self._fetch_ollama_models(entity)
        raise ValueError(f"unsupported provider_type: {entity.provider_type}")

    def _fetch_openai_compatible_models(self, entity: TbLlmProvider) -> list[str]:
        headers = {"Accept": "application/json"}
        if entity.api_key:
            headers["Authorization"] = f"Bearer {entity.api_key}"

        models_url = f"{entity.base_url.rstrip('/')}/models"
        try:
            with httpx.Client(timeout=20.0, headers=headers) as client:
                response = client.get(models_url)
        except httpx.HTTPError as e:
            raise ValueError(f"request {models_url} failed: {e}") from e

        if response.status_code >= 400:
            raise ValueError(
                f"request {models_url} failed with status={response.status_code}, "
                f"response={self._truncate_response_text(response.text)}"
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise ValueError(
                f"request {models_url} returned invalid json: "
                f"{self._truncate_response_text(response.text)}"
            ) from e

        models = payload.get("data")
        if not isinstance(models, list):
            raise ValueError(f"request {models_url} returned unexpected payload: {payload}")
        if not models:
            raise ValueError(f"request {models_url} succeeded but returned no models")
        return [str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")]

    def _fetch_ollama_models(self, entity: TbLlmProvider) -> list[str]:
        tags_url = f"{entity.base_url.rstrip('/')}/api/tags"
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(tags_url)
        except httpx.HTTPError as e:
            raise ValueError(f"request {tags_url} failed: {e}") from e

        if response.status_code >= 400:
            raise ValueError(
                f"request {tags_url} failed with status={response.status_code}, "
                f"response={self._truncate_response_text(response.text)}"
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise ValueError(
                f"request {tags_url} returned invalid json: "
                f"{self._truncate_response_text(response.text)}"
            ) from e

        models = payload.get("models")
        if not isinstance(models, list):
            raise ValueError(f"request {tags_url} returned unexpected payload: {payload}")
        return [
            str(item.get("name")) for item in models if isinstance(item, dict) and item.get("name")
        ]

    def _truncate_response_text(self, text: str, limit: int = 500) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit]}..."

    # ── Model CRUD ──

    def create_model(
        self,
        db: Session,
        provider_id: int,
        req: LlmModelCreateReq,
        req_ctx: RequestContext,
    ) -> LlmModelResp:
        provider = db.get(TbLlmProvider, provider_id)
        if not provider:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "provider not found")
        if req.model_type not in VALID_MODEL_TYPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid model_type: {req.model_type}")

        dup = db.scalar(
            select(TbLlmModel).where(
                TbLlmModel.provider_id == provider_id,
                TbLlmModel.model == req.model,
            )
        )
        if dup:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "model already exists in this provider")

        now = req_ctx.request_time_ms
        entity = TbLlmModel(
            id=self._id.next_id(),
            provider_id=provider_id,
            model=req.model,
            model_type=req.model_type,
            status="active",
            max_input_tokens=req.max_input_tokens,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return LlmModelResp.from_entity(entity)

    def update_model(
        self, db: Session, model_id: int, req: LlmModelUpdateReq, req_ctx: RequestContext
    ) -> LlmModelResp:
        entity = db.get(TbLlmModel, model_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "model not found")

        if req.model is not None:
            entity.model = req.model
        if req.model_type is not None:
            if req.model_type not in VALID_MODEL_TYPES:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid model_type: {req.model_type}")
            entity.model_type = req.model_type
        if req.max_input_tokens is not None:
            entity.max_input_tokens = req.max_input_tokens
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return LlmModelResp.from_entity(entity)

    def toggle_model_status(
        self, db: Session, model_id: int, status: str, req_ctx: RequestContext
    ) -> LlmModelResp:
        if status not in VALID_MODEL_STATUSES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid status: {status}")
        entity = db.get(TbLlmModel, model_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "model not found")

        entity.status = status
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return LlmModelResp.from_entity(entity)

    def delete_model(self, db: Session, model_id: int) -> None:
        entity = db.get(TbLlmModel, model_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "model not found")
        db.delete(entity)
        db.commit()

    # ── Internal ──

    def _to_provider_resp(self, db: Session, entity: TbLlmProvider) -> LlmProviderResp:
        models = db.scalars(select(TbLlmModel).where(TbLlmModel.provider_id == entity.id)).all()
        return LlmProviderResp.from_entity(entity, [LlmModelResp.from_entity(m) for m in models])
