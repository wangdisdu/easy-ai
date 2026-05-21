"""限流的抽象接口与 fallback 解析。

设计要点(详见 docs/application-integration-design.md §8):

- 三态:None=继承上一层,0=显式不限,>0=具体阈值
- 优先级:ApiKey.rate_limit → Integration.rate_limit → GlobalDefaults
- 日配额仅在 Integration 级
- Protocol 抽象,P0 用 MemoryRateLimiter,P1 切 Redis 不动 Dependency
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, Protocol


@dataclass(frozen=True)
class GlobalDefaults:
    """平台兜底默认值,所有都用"具体阈值"语义(不是三态)。

    P0 直接使用模块级常量 GLOBAL_DEFAULTS;P1 后再考虑接入 system_setting。
    """

    key_rpm: int = 100
    integration_rpm: int = 1000
    day_quota: int = 100000


GLOBAL_DEFAULTS = GlobalDefaults()


class Limits(NamedTuple):
    """解析后送给限流器的具体阈值。0 = 不限,>0 = 具体值,不应为 None。"""

    key_rpm: int
    int_rpm: int
    day_quota: int


class Decision(NamedTuple):
    """限流器返回的决策。`reason` 在 allowed=True 时固定为 OK。"""

    allowed: bool
    reason: str  # 'OK' | 'KEY_RPM' | 'INTEGRATION_RPM' | 'DAY_QUOTA'
    key_used: int
    int_used: int
    day_used: int


class _IntegrationCfg(Protocol):
    rate_limit: int | None
    quota: int | None


class _ApiKeyCfg(Protocol):
    rate_limit: int | None


def resolve_limits(
    intg: _IntegrationCfg,
    key: _ApiKeyCfg,
    defaults: GlobalDefaults = GLOBAL_DEFAULTS,
) -> Limits:
    """三态 fallback 解析。

    - Key 级:Key 显式 → Integration 显式 → defaults.key_rpm
    - Integration 级:Integration 显式 → defaults.integration_rpm
    - 日配额:Integration 显式 → defaults.day_quota

    注意 `0` 是合法的"显式不限",不要把它当作 falsy 跳过。
    """
    if key.rate_limit is not None:
        key_rpm = key.rate_limit
    elif intg.rate_limit is not None:
        key_rpm = intg.rate_limit
    else:
        key_rpm = defaults.key_rpm

    int_rpm = intg.rate_limit if intg.rate_limit is not None else defaults.integration_rpm
    day_quota = intg.quota if intg.quota is not None else defaults.day_quota

    return Limits(key_rpm=key_rpm, int_rpm=int_rpm, day_quota=day_quota)


class RateLimiter(Protocol):
    """限流器协议,P0 内存实现 + P1 Redis 实现走相同接口。"""

    async def check_and_incr(self, intg_id: int, key_id: int, limits: Limits) -> Decision: ...

    async def drop_key(self, intg_id: int, key_id: int) -> None:
        """Key 重置/删除时清桶,让新 Key 从 0 起。"""
