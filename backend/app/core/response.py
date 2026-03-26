from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Resp(BaseModel, Generic[T]):
    code: int = 0
    msg: str = "ok"
    data: T | None = None


class PagedResp(Resp[list[T]], Generic[T]):
    total: int
