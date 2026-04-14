import time

from fastapi import Request
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings


class RequestContext(BaseModel):
    user_id: int | None = None
    client_ip: str | None = None
    request_time_ms: int


def _extract_token(request: Request) -> str | None:
    # 优先 cookie（前端浏览器流量），回退 Bearer（curl/SDK/CLI）
    cookie_token = request.cookies.get("easyai_token")
    if cookie_token:
        return cookie_token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def build_request_context(request: Request) -> RequestContext:
    user_id: int | None = None
    token = _extract_token(request)
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            sub = payload.get("sub")
            if sub is not None:
                user_id = int(sub)
        except (JWTError, ValueError, TypeError):
            user_id = None

    return RequestContext(
        user_id=user_id,
        client_ip=request.client.host if request.client else None,
        request_time_ms=int(time.time() * 1000),
    )
