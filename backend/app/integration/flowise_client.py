"""Server-to-server Flowise API client.

复用 /flowise/* 反向代理的 trusted-header 协议（HMAC-SHA256），但走的是后端
直连 Flowise 内网地址，不经过浏览器。调用方传入 easy-ai user_id，Flowise 侧
trustedHeaderAuth 中间件会构造对应的 LoggedInUser，使其落到默认 workspace 的
admin 权限。

只暴露 agent_flow 业务联动需要的最小接口。
"""

import hashlib
import hmac
import json
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_AGENTFLOW_EMPTY_FLOW_DATA = json.dumps({"nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}})


class FlowiseClientError(RuntimeError):
    pass


def _sign(user_id: str, workspace: str, ts_ms: int) -> str:
    payload = f"{user_id}.{workspace}.{ts_ms}".encode()
    return hmac.new(settings.flowise_shared_secret.encode(), payload, hashlib.sha256).hexdigest()


def _headers(user_id: str) -> dict[str, str]:
    workspace = settings.flowise_default_workspace or ""
    ts_ms = int(time.time() * 1000)
    return {
        "Content-Type": "application/json",
        "X-EasyAI-User": str(user_id),
        "X-EasyAI-Workspace": workspace,
        "X-EasyAI-Ts": str(ts_ms),
        "X-EasyAI-Sign": _sign(str(user_id), workspace, ts_ms),
    }


def _base_url() -> str:
    return settings.flowise_internal_url.rstrip("/")


def create_agentflow(name: str, user_id: int | str) -> str:
    """创建一个空的 Agent Flow v2 chatflow，返回 Flowise 端的 uuid。"""
    body = {
        "name": name,
        "type": "AGENTFLOW",
        "flowData": _AGENTFLOW_EMPTY_FLOW_DATA,
        "deployed": False,
        "isPublic": False,
    }
    url = f"{_base_url()}/api/v1/chatflows"
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            resp = client.post(url, headers=_headers(user_id), json=body)
    except httpx.HTTPError as e:
        raise FlowiseClientError(f"flowise unreachable: {e}") from e
    if resp.status_code >= 400:
        raise FlowiseClientError(f"flowise create chatflow failed: {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    chatflow_id = data.get("id")
    if not chatflow_id:
        raise FlowiseClientError(f"flowise response missing id: {data}")
    return str(chatflow_id)


def rename_chatflow(chatflow_id: str, name: str, user_id: int | str) -> None:
    """更新 Flowise chatflow 名称。失败仅记录日志,不抛出(best-effort)。"""
    url = f"{_base_url()}/api/v1/chatflows/{chatflow_id}"
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            resp = client.put(url, headers=_headers(user_id), json={"name": name})
        if resp.status_code >= 400:
            logger.warning(
                "flowise rename chatflow %s failed: %s %s", chatflow_id, resp.status_code, resp.text[:200]
            )
    except httpx.HTTPError as e:
        logger.warning("flowise rename chatflow %s unreachable: %s", chatflow_id, e)


def delete_chatflow(chatflow_id: str, user_id: int | str) -> None:
    """删除 Flowise chatflow。失败仅记录日志，不抛出（best-effort）。"""
    url = f"{_base_url()}/api/v1/chatflows/{chatflow_id}"
    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            resp = client.delete(url, headers=_headers(user_id))
        if resp.status_code >= 400 and resp.status_code != 404:
            logger.warning(
                "flowise delete chatflow %s failed: %s %s", chatflow_id, resp.status_code, resp.text[:200]
            )
    except httpx.HTTPError as e:
        logger.warning("flowise delete chatflow %s unreachable: %s", chatflow_id, e)
