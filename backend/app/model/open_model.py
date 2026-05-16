from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    # 模型最大输入 token；None 时摘要中间件回退到 170k 兜底
    max_input_tokens: int | None = None


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
    # 长会话 LangGraph 线程标识；启用 checkpoint 时由调用方提供 str(conversation_id)
    thread_id: str | None = None
    # 是否走 Checkpointer：True 时 messages 只需带本轮新消息（历史由 saver 恢复）
    use_checkpoint: bool = False
    # 仅用作 SSE 提示信号：本轮是否走过"checkpoint 缺失 + 业务消息重建"的降级路径
    degraded: bool = False
    # HITL 续跑时指向被中断的原 run（协议 run.started.parent_run_id），用于审计追溯
    parent_run_id: str | None = None


class RagRunRequest(BaseModel):
    app_id: int = 0
    # 单轮兼容:query 是最后一条用户问题
    query: str = ""
    # 多轮上下文:messages 非空时,query 自动取最后一条 user 消息的 content
    messages: list[ModelGatewayChatMessage] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)


class HitlSelected(BaseModel):
    """协议 hitl.required.options 的裁决选择。"""

    option_id: Literal["confirm", "modify", "reject"]
    parameters: dict[str, Any] | None = None


class HitlOutcome(BaseModel):
    """协议续跑请求体的 outcome：二选一 selected / cancelled。"""

    selected: HitlSelected | None = None
    cancelled: bool | None = None

    @model_validator(mode="after")
    def _require_one(self) -> HitlOutcome:
        if self.selected is None and not self.cancelled:
            raise ValueError("outcome requires 'selected' or 'cancelled'")
        return self

    @property
    def action(self) -> str:
        """映射到内部 resume 契约（confirm/modify/reject），不改 PolicyMiddleware。"""
        if self.cancelled:
            return "reject"
        return self.selected.option_id if self.selected else "reject"

    @property
    def resolved_parameters(self) -> dict[str, Any] | None:
        return self.selected.parameters if self.selected else None


class AppTestHitlRespondReq(BaseModel):
    thread_id: str
    hitl_id: str | None = None
    outcome: HitlOutcome
    parent_run_id: str | None = None
