"""应用集成限流子模块。

P0 单机内存实现(memory.MemoryRateLimiter)。P1 切换到 Redis 时只换实现,
RateLimiter 协议与 Dependency 不动。详见 docs/application-integration-design.md §9。
"""

from app.core.rate_limit.base import (
    GLOBAL_DEFAULTS,
    Decision,
    GlobalDefaults,
    Limits,
    RateLimiter,
    resolve_limits,
)
from app.core.rate_limit.memory import MemoryRateLimiter

__all__ = [
    "GLOBAL_DEFAULTS",
    "Decision",
    "GlobalDefaults",
    "Limits",
    "MemoryRateLimiter",
    "RateLimiter",
    "resolve_limits",
]
