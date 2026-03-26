import time

from fastapi import Request
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings


class RequestContext(BaseModel):
    user_id: int | None = None
    client_ip: str | None = None
    request_time_ms: int


def build_request_context(request: Request) -> RequestContext:
    user_id: int | None = None
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
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
