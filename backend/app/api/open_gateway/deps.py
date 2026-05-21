"""对外网关 Dependency 链。

顺序:integration_auth → app_bound → rate_limit。绑定校验先于限流计数,
避免攻击者用合法 Key 调用未绑定应用反复消耗集成的配额(详见
docs/application-integration-design.md §7.3)。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.integration_api import service as integration_service
from app.core.integration_errors import IntegrationApiError
from app.core.rate_limit import Decision, Limits, MemoryRateLimiter, resolve_limits
from app.db.schema import TbIntegration, TbIntegrationKey
from app.db.session import get_db
from app.model.integration_model import SUPPORTED_APP_TYPES

logger = logging.getLogger(__name__)


@dataclass
class AuthCtx:
    integration: TbIntegration
    key: TbIntegrationKey


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _build_ratelimit_headers(d: Decision, limits: Limits) -> dict[str, str]:
    headers: dict[str, str] = {}
    # 0 = 不限,不输出 Limit 头(无意义);只输出 Used 让客户端可观测
    if limits.key_rpm > 0:
        headers["X-RateLimit-Limit-Key"] = str(limits.key_rpm)
    if limits.int_rpm > 0:
        headers["X-RateLimit-Limit-Integration"] = str(limits.int_rpm)
    if limits.day_quota > 0:
        headers["X-Quota-Limit"] = str(limits.day_quota)
    headers["X-RateLimit-Used-Key"] = str(d.key_used)
    headers["X-RateLimit-Used-Integration"] = str(d.int_used)
    headers["X-Quota-Used"] = str(d.day_used)
    return headers


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ip_in_whitelist(client_ip: str | None, whitelist: str | None) -> bool:
    """P0 仅做精确 IP 字符串匹配,逗号分隔。P1 再扩 CIDR。"""
    if not whitelist:
        return True
    if client_ip is None:
        return False
    allowed = {ip.strip() for ip in whitelist.split(",") if ip.strip()}
    return client_ip in allowed


def integration_auth(request: Request, db: Session = Depends(get_db)) -> AuthCtx:
    # 最早可达点:记录起算时刻,供 access_log 计算 latency
    request.state.access_start = time.perf_counter()

    raw_key = _extract_bearer(request)
    if not raw_key:
        raise IntegrationApiError(401, "API_KEY_INVALID", "missing bearer token")

    found = integration_service.lookup_by_key_plain(db, raw_key)
    if found is None:
        raise IntegrationApiError(401, "API_KEY_INVALID", "key not found")
    intg, key = found
    # 解析成功即写到 state,后续校验即便拒绝,日志也能带上 intg/key
    request.state.access_intg_id = intg.id
    request.state.access_key_id = key.id

    if intg.status != "active":
        raise IntegrationApiError(403, "INTEGRATION_DISABLED", "integration disabled")
    if intg.expire_at is not None and intg.expire_at < _now_ms():
        raise IntegrationApiError(403, "INTEGRATION_EXPIRED", "integration expired")
    if key.status != "active":
        raise IntegrationApiError(403, "API_KEY_DISABLED", "key not usable")

    client_ip = request.client.host if request.client else None
    if not _ip_in_whitelist(client_ip, intg.whitelist):
        raise IntegrationApiError(403, "IP_NOT_ALLOWED", "ip not whitelisted")

    return AuthCtx(integration=intg, key=key)


def app_bound(
    app_type: str,
    app_id: str,
    db: Session = Depends(get_db),
    ctx: AuthCtx = Depends(integration_auth),
) -> AuthCtx:
    if app_type not in SUPPORTED_APP_TYPES:
        raise IntegrationApiError(403, "APP_NOT_BOUND", f"unsupported app_type: {app_type}")
    try:
        app_id_int = int(app_id)
    except (TypeError, ValueError) as e:
        raise IntegrationApiError(400, "BAD_REQUEST", "invalid app_id") from e

    if not integration_service.is_app_bound(db, ctx.integration.id, app_type, app_id_int):
        raise IntegrationApiError(403, "APP_NOT_BOUND", "app not bound to integration")
    return ctx


async def rate_limit(request: Request, ctx: AuthCtx = Depends(app_bound)) -> AuthCtx:
    limiter: MemoryRateLimiter = request.app.state.limiter
    limits = resolve_limits(ctx.integration, ctx.key)
    d = await limiter.check_and_incr(ctx.integration.id, ctx.key.id, limits)
    headers = _build_ratelimit_headers(d, limits)
    if not d.allowed:
        retry_after = 60 - (int(time.time()) % 60)
        headers["Retry-After"] = str(retry_after)
        raise IntegrationApiError(
            429,
            "RATE_LIMITED",
            "rate limit exceeded",
            headers=headers,
            extra={"reason": d.reason},
        )
    request.state.rl_headers = headers
    return ctx
