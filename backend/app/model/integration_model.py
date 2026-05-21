"""应用集成相关 Pydantic 模型。

参见 docs/application-integration-design.md §3、§4、§5。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import (
    TbApiAccessLog,
    TbIntegration,
    TbIntegrationApp,
    TbIntegrationKey,
)

# P0 仅支持下列三类。P1 扩展 agent_flow / kb_push 时,在此处放开并补 dispatcher 分支。
SUPPORTED_APP_TYPES: frozenset[str] = frozenset({"agent", "llm", "rag"})


# ── 绑定 ──


class BoundAppItem(BaseModel):
    app_type: str = Field(min_length=1, max_length=32)
    app_id: str = Field(min_length=1)


# ── 创建 / 更新 ──


class IntegrationCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    # 三态:None=继承全局默认,0=不限,>0=具体阈值
    quota: int | None = Field(default=None, ge=0)
    rate_limit: int | None = Field(default=None, ge=0)
    timeout: int | None = Field(default=None, ge=1)
    whitelist: str | None = Field(default=None)
    expire_at: int | None = Field(default=None)
    bound_apps: list[BoundAppItem] = Field(default_factory=list)


class IntegrationUpdateReq(BaseModel):
    """集成更新请求。

    service 层用 `model_fields_set` 区分"字段未提供"与"显式置 null":
    - 请求体里没这个 key → 不修改
    - 请求体里 key 为 null → 写回 NULL(quota/rate_limit/timeout 即"继承全局默认")

    因此这里所有字段 `default=None` 只是表示"可省略",不要在 service 里
    用 `is not None` 判断,否则永远无法把配额清回继承态。
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    quota: int | None = Field(default=None, ge=0)
    rate_limit: int | None = Field(default=None, ge=0)
    timeout: int | None = Field(default=None, ge=1)
    whitelist: str | None = Field(default=None)
    expire_at: int | None = Field(default=None)
    # bound_apps 例外:None = 不修改绑定;[] = 解绑全部(语义上 None 即"省略")
    bound_apps: list[BoundAppItem] | None = Field(default=None)


class IntegrationStatusReq(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


class IntegrationPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


# ── Key 管理 ──


class IntegrationKeyUpdateReq(BaseModel):
    """修改 Key 的限流或启停。两个字段都是可选,均不传则等价于无操作。"""

    rate_limit: int | None = Field(default=None, ge=0)
    rate_limit_inherit: bool = Field(default=False)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


# ── Resp ──


class IntegrationKeyResp(BaseModel):
    id: str
    integration_id: str
    masked: str
    status: str
    rate_limit: int | None
    last_used_at: int | None
    create_time: int

    @classmethod
    def from_entity(cls, entity: TbIntegrationKey) -> IntegrationKeyResp:
        return cls(
            id=str(entity.id),
            integration_id=str(entity.integration_id),
            masked=f"{entity.key_prefix}****{entity.key_suffix}",
            status=entity.status,
            rate_limit=entity.rate_limit,
            last_used_at=entity.last_used_at,
            create_time=entity.create_time,
        )


class IntegrationKeyPlaintextResp(BaseModel):
    """生成/重置时返回的明文,**只返回一次**,后续接口不再下发明文。"""

    key: IntegrationKeyResp
    plaintext: str


class IntegrationResp(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    quota: int | None
    rate_limit: int | None
    timeout: int | None
    whitelist: str | None
    expire_at: int | None
    create_time: int
    update_time: int
    bound_apps: list[BoundAppItem] = Field(default_factory=list)
    keys: list[IntegrationKeyResp] = Field(default_factory=list)

    @classmethod
    def from_entity(
        cls,
        entity: TbIntegration,
        bindings: list[TbIntegrationApp] | None = None,
        keys: list[TbIntegrationKey] | None = None,
    ) -> IntegrationResp:
        return cls(
            id=str(entity.id),
            name=entity.name,
            description=entity.description,
            status=entity.status,
            quota=entity.quota,
            rate_limit=entity.rate_limit,
            timeout=entity.timeout,
            whitelist=entity.whitelist,
            expire_at=entity.expire_at,
            create_time=entity.create_time,
            update_time=entity.update_time,
            bound_apps=[
                BoundAppItem(app_type=b.app_type, app_id=str(b.app_id)) for b in (bindings or [])
            ],
            keys=[IntegrationKeyResp.from_entity(k) for k in (keys or [])],
        )


class IntegrationCreateResp(BaseModel):
    """创建集成的复合响应:集成本体 + 首把 Key 的明文。

    若 Key 生成失败(理论上不应发生),`first_key` 为 None,前端提示用户手动补建。
    """

    integration: IntegrationResp
    first_key: IntegrationKeyPlaintextResp | None


# ── 调用日志 ──


class ApiAccessLogPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    integration_id: str | None = Field(default=None)
    # True 仅看失败调用(status_code >= 400)
    only_failed: bool = Field(default=False)


class ApiAccessLogResp(BaseModel):
    id: str
    integration_id: str | None
    key_id: str | None
    app_type: str | None
    app_id: str | None
    status_code: int
    code: str
    reason: str | None
    latency_ms: int | None
    client_ip: str | None
    request_bytes: int | None
    error_message: str | None
    create_time: int

    @classmethod
    def from_entity(cls, e: TbApiAccessLog) -> ApiAccessLogResp:
        return cls(
            id=str(e.id),
            integration_id=str(e.integration_id) if e.integration_id is not None else None,
            key_id=str(e.key_id) if e.key_id is not None else None,
            app_type=e.app_type,
            app_id=str(e.app_id) if e.app_id is not None else None,
            status_code=e.status_code,
            code=e.code,
            reason=e.reason,
            latency_ms=e.latency_ms,
            client_ip=e.client_ip,
            request_bytes=e.request_bytes,
            error_message=e.error_message,
            create_time=e.create_time,
        )
