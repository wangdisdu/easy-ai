"""Flowise reverse proxy (M1).

将浏览器对 ``/flowise/*`` 的请求透传到内网 Flowise 服务，并在请求头里注入 easy-ai
身份信息 + HMAC 签名，配合 Flowise 侧的 ``easyaiTrustedHeaderAuth`` 中间件实现
免登录嵌入。

M1 范围：
- 支持 GET/POST/PUT/PATCH/DELETE/OPTIONS，body 流式转发
- 支持响应流式（含 text/event-stream / SSE）
- iframe 入口通过 ``?easyai_token={jwt}`` 携带 easy-ai JWT，proxy 校验后剥离
- WebSocket 升级、Cookie 持久化等留待后续里程碑
"""

import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from jose import JWTError, jwt

from app.core.config import settings

router = APIRouter()

# 这些 hop-by-hop 头不允许在 HTTP/1.1 里转发
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    # easy-ai 自有,不应泄露给上游
    "host",
    "content-length",
}

# Flowise 响应里需要剥掉的头（防止 iframe 嵌入受限 / 长度不符等）
_RESP_STRIP = {
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
    "x-frame-options",
}

# 浏览器默认不带 cookie 的静态资源(<link rel="manifest"> / favicon 等),
# 这些文件不含敏感信息,允许匿名转发,避免出现 401 阻塞页面加载。
_ANON_PATHS = {"manifest.json", "favicon.ico", "robots.txt", "logo192.png", "logo512.png"}


def _resolve_token(request: Request) -> str | None:
    """只接受 httpOnly cookie 或 Authorization 头,不再支持 URL query 传 token。"""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("easyai_token")


def _verify_jwt(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing easy-ai token")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}") from e
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub")
    return str(sub)


def _sign(user_id: str, workspace: str, ts_ms: int) -> str:
    payload = f"{user_id}.{workspace}.{ts_ms}".encode()
    return hmac.new(settings.flowise_shared_secret.encode(), payload, hashlib.sha256).hexdigest()


def _passthrough_query(qs_pairs: list[tuple[str, str]]) -> str:
    return urlencode(qs_pairs, doseq=True)


def _build_upstream_headers(request: Request, user_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() in _HOP_BY_HOP:
            continue
        if k.lower() == "authorization":
            # 不把 easy-ai JWT 泄露给 Flowise
            continue
        out[k] = v
    workspace = settings.flowise_default_workspace or ""
    ts_ms = int(time.time() * 1000)
    out["X-EasyAI-User"] = user_id
    out["X-EasyAI-Workspace"] = workspace
    out["X-EasyAI-Ts"] = str(ts_ms)
    out["X-EasyAI-Sign"] = _sign(user_id, workspace, ts_ms)
    return out


@router.api_route(
    "/flowise/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def flowise_proxy(path: str, request: Request) -> Response:
    if not settings.flowise_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="flowise integration disabled")

    if path in _ANON_PATHS:
        # 匿名静态资源:不校验 token,也不注入 X-EasyAI-* 头
        upstream_headers = {
            k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP and k.lower() != "authorization"
        }
    else:
        user_id = _verify_jwt(_resolve_token(request))
        upstream_headers = _build_upstream_headers(request, user_id)

    upstream_base = settings.flowise_internal_url.rstrip("/")
    qs = _passthrough_query(list(request.query_params.multi_items()))
    upstream_url = f"{upstream_base}/{path}"
    if qs:
        upstream_url = f"{upstream_url}?{qs}"

    body = await request.body()

    client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=False)
    upstream_req = client.build_request(
        method=request.method,
        url=upstream_url,
        headers=upstream_headers,
        content=body if body else None,
    )
    try:
        upstream_resp = await client.send(upstream_req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"flowise upstream error: {e}") from e

    resp_headers = {k: v for k, v in upstream_resp.headers.items() if k.lower() not in _RESP_STRIP}

    async def body_iterator():
        try:
            async for chunk in upstream_resp.aiter_raw():
                yield chunk
        finally:
            await upstream_resp.aclose()
            await client.aclose()

    return StreamingResponse(
        body_iterator(),
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=upstream_resp.headers.get("content-type"),
    )


@router.api_route("/flowise", methods=["GET"])
async def flowise_root(request: Request) -> Response:
    # 入口跳转到 chatflows 列表（嵌入页面通常会带 easyai_token 参数）
    return await flowise_proxy("", request)
