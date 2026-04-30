from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConversationCreateReq(BaseModel):
    app_id: str = Field(min_length=1)


class ConversationUpdateReq(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None)


class ConversationResp(BaseModel):
    id: str
    app_id: str
    app_type: str = ""
    app_name: str = ""
    title: str = ""
    status: str = "active"
    last_message: str | None = None
    create_time: int = 0
    update_time: int = 0


class ConversationMessageResp(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str | None = None
    metadata: Any = None
    create_time: int = 0


class SendMessageReq(BaseModel):
    content: str = Field(min_length=1)


class HitlResponseReq(BaseModel):
    """HITL 用户响应：confirm 按原参数执行；modify 用 parameters 覆盖；reject 取消。"""

    action: str = Field(pattern="^(confirm|modify|reject)$")
    parameters: dict[str, Any] | None = None
