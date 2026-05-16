from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.model.open_model import HitlOutcome


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
    """HITL 续跑请求体（协议 v1）：outcome 二选一 selected / cancelled。

    hitl_id 也在 URL path 上，body 内可选，便于客户端自校验。
    """

    hitl_id: str | None = None
    outcome: HitlOutcome
    # 被中断 run 的 run_id（前端从 hitl.required 事件信封捕获后回传），
    # 续跑新 run 的 run.started.parent_run_id 据此指回，供审计追溯
    parent_run_id: str | None = None
