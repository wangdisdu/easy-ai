import time

import bcrypt
from jose import jwt

from app.core.config import settings

# bcrypt 明文上限 72 字节
BCRYPT_MAX_PASSWORD_BYTES = 72


def _utf8_bytes_limited(s: str) -> bytes:
    """转为 UTF-8 并截断至 bcrypt 允许的 72 字节。"""
    b = s.encode("utf-8")
    if len(b) <= BCRYPT_MAX_PASSWORD_BYTES:
        return b
    return b[:BCRYPT_MAX_PASSWORD_BYTES]


def hash_password(raw_password: str) -> str:
    secret = _utf8_bytes_limited(raw_password)
    return bcrypt.hashpw(secret, bcrypt.gensalt()).decode("ascii")


def verify_password(raw_password: str, password_hash: str) -> bool:
    h = password_hash.encode("ascii")
    secret = _utf8_bytes_limited(raw_password)
    try:
        return bcrypt.checkpw(secret, h)
    except ValueError:
        return False


def create_access_token(user_id: int, expires_in_seconds: int = 24 * 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
