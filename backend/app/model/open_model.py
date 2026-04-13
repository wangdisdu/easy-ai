from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelGatewayChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str = Field(default="")


class LiteLLMRuntimeConfig(BaseModel):
    model: str
    base_url: str
    api_key: str | None = None
    provider_id: int | None = None
    model_id: int | None = None
    model_setting: dict[str, Any] = Field(default_factory=dict)


class AppLogResp(BaseModel):
    id: str
    app_id: str | None = None
    app_type: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    model: str | None = None
    request_type: str
    success: bool
    response_status: int | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    langfuse_trace_id: str | None = None
    total_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_payload: Any = None
    response_payload: Any = None
    create_time: int


class GatewayHealthResp(BaseModel):
    status: str
    gateway_url: str
    latency_ms: int | None = None
    models_count: int | None = None
    error_message: str | None = None


class AppRunReq(BaseModel):
    messages: list[ModelGatewayChatMessage] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    query: str | None = None


class AppTestReq(AppRunReq):
    pass


class LlmAppRunReq(BaseModel):
    app_id: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)
    messages: list[ModelGatewayChatMessage] = Field(default_factory=list)


class LiteLLMChatRequest(BaseModel):
    messages: list[ModelGatewayChatMessage]
    runtime_config: LiteLLMRuntimeConfig
    extra_body: dict[str, Any] = Field(default_factory=dict)


class LiteLLMEmbeddingRequest(BaseModel):
    input: str | list[str]
    runtime_config: LiteLLMRuntimeConfig
    extra_body: dict[str, Any] = Field(default_factory=dict)


class LiteLLMRerankRequest(BaseModel):
    query: str
    documents: list[str]
    runtime_config: LiteLLMRuntimeConfig
    top_n: int | None = None
    extra_body: dict[str, Any] = Field(default_factory=dict)


class ModelGatewayResponse(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    raw_response: dict[str, Any] = Field(default_factory=dict)
    response_status: int | None = None
    latency_ms: int | None = None


class AgentRunRequest(BaseModel):
    app_id: int = 0
    messages: list[ModelGatewayChatMessage] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


class RagRunRequest(BaseModel):
    app_id: int = 0
    query: str
    variables: dict[str, Any] = Field(default_factory=dict)
