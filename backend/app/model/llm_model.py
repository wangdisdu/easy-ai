from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbLlmModel, TbLlmProvider

# ── LLM Model item (for inline creation with provider) ──


class LlmModelItem(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    model_type: str = Field(min_length=1, max_length=255)


# ── Provider ──


class LlmProviderCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider_type: str = Field(min_length=1, max_length=255)
    base_url: str = Field(min_length=1)
    api_key: str | None = Field(default=None)
    models: list[LlmModelItem] = Field(default_factory=list)


class LlmProviderUpdateReq(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    provider_type: str | None = Field(default=None, max_length=255)
    base_url: str | None = Field(default=None)
    api_key: str | None = Field(default=None)


class LlmProviderPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class LlmModelResp(BaseModel):
    id: str
    model: str
    model_type: str
    status: str

    @classmethod
    def from_entity(cls, entity: TbLlmModel) -> LlmModelResp:
        return cls(
            id=str(entity.id),
            model=entity.model,
            model_type=entity.model_type,
            status=entity.status,
        )


class LlmProviderResp(BaseModel):
    id: str
    name: str
    provider_type: str
    base_url: str
    api_key: str | None = None
    status: str
    last_check: int | None = None
    models: list[LlmModelResp] = []
    create_time: int
    update_time: int

    @classmethod
    def from_entity(
        cls, entity: TbLlmProvider, models: list[LlmModelResp] | None = None
    ) -> LlmProviderResp:
        return cls(
            id=str(entity.id),
            name=entity.name,
            provider_type=entity.provider_type,
            base_url=entity.base_url,
            api_key=entity.api_key,
            status=entity.status,
            last_check=entity.last_check,
            models=models or [],
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


# ── Model CRUD ──


class LlmModelCreateReq(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    model_type: str = Field(min_length=1, max_length=255)


class LlmModelUpdateReq(BaseModel):
    model: str | None = Field(default=None, max_length=255)
    model_type: str | None = Field(default=None, max_length=255)
