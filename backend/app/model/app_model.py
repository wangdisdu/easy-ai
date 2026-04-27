from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from app.db.schema import TbApp, TbAppVersion


class AppCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    app_type: str = Field(min_length=1, max_length=255)
    provider_id: str | None = Field(default=None)
    model_id: str | None = Field(default=None)
    model_setting: dict[str, Any] | None = Field(default=None)
    app_config: dict[str, Any] | None = Field(default=None)
    access_scope: str | None = Field(default="internal", max_length=255)
    rate_limit: int | None = Field(default=60, ge=1)
    enable_log: bool | None = Field(default=True)
    # 仅 agent 应用使用：长会话开关，开启后 Checkpointer 持久化运行态
    enable_long_session: bool | None = Field(default=False)
    # 仅 agent 应用使用：绑定的工具/技能 ID 列表
    tool_ids: list[str] | None = Field(default=None)
    skill_ids: list[str] | None = Field(default=None)


class AppUpdateReq(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None)
    provider_id: str | None = Field(default=None)
    model_id: str | None = Field(default=None)
    model_setting: dict[str, Any] | None = Field(default=None)
    app_config: dict[str, Any] | None = Field(default=None)
    access_scope: str | None = Field(default=None, max_length=255)
    rate_limit: int | None = Field(default=None, ge=1)
    enable_log: bool | None = Field(default=None)
    enable_long_session: bool | None = Field(default=None)
    # 仅 agent 应用使用：绑定的工具/技能 ID 列表，None 表示不更新，[] 表示清空
    tool_ids: list[str] | None = Field(default=None)
    skill_ids: list[str] | None = Field(default=None)


class AppPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    app_type: str | None = Field(default=None, max_length=255)
    app_status: str | None = Field(default=None, max_length=255)


class AppPublishReq(BaseModel):
    version: str = Field(min_length=1, max_length=255)
    version_note: str | None = Field(default=None)


class AppResp(BaseModel):
    id: str
    name: str
    description: str | None = None
    app_type: str
    app_status: str
    provider_id: str | None = None
    model_id: str | None = None
    model: str | None = None
    model_setting: dict[str, Any] | None = None
    app_config: dict[str, Any] | None = None
    access_scope: str | None = None
    rate_limit: int | None = None
    enable_log: bool | None = None
    enable_long_session: bool | None = None
    version_id: str | None = None
    current_version: str | None = None
    # 仅 agent_flow 类型有值：对应 Flowise 端的 chatflow uuid
    flowise_chatflow_id: str | None = None
    # 仅 agent 应用返回：绑定的工具/技能 ID 列表
    tool_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbApp) -> AppResp:
        model_setting = parse_json_object(entity.model_setting)
        app_config = parse_json_object(entity.app_config)
        return cls(
            id=str(entity.id),
            name=entity.name,
            description=entity.description,
            app_type=normalize_app_type(entity.app_type),
            app_status=entity.app_status,
            provider_id=str(entity.provider_id) if entity.provider_id is not None else None,
            model_id=str(entity.model_id) if entity.model_id is not None else None,
            model=entity.model,
            model_setting=model_setting,
            app_config=app_config,
            access_scope=entity.access_scope,
            rate_limit=entity.rate_limit,
            enable_log=bool(entity.enable_log) if entity.enable_log is not None else None,
            enable_long_session=bool(entity.enable_long_session),
            version_id=entity.version_id,
            current_version=entity.current_version,
            flowise_chatflow_id=entity.flowise_chatflow_id,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class AppVersionResp(BaseModel):
    id: str
    app_id: str
    version: str
    version_note: str | None = None
    published_time: int
    create_time: int

    @classmethod
    def from_entity(cls, entity: TbAppVersion) -> AppVersionResp:
        return cls(
            id=str(entity.id),
            app_id=str(entity.app_id),
            version=entity.version,
            version_note=entity.version_note,
            published_time=entity.published_time,
            create_time=entity.create_time,
        )


def normalize_app_type(app_type: str) -> str:
    mapping = {
        "RAG": "rag",
        "LLM": "llm",
        "NL2SQL": "nl2sql",
        "Agent": "agent",
        "AgentFlow": "agent_flow",
        "Agent Flow": "agent_flow",
    }
    return mapping.get(app_type, app_type)


def parse_json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_app_config(raw_config: str | None) -> dict[str, Any]:
    return parse_json_object(raw_config)


def parse_model_setting(raw_value: str | None) -> dict[str, Any]:
    return parse_json_object(raw_value)
