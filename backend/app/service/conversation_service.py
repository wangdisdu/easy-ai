from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.app.agent_app import AgentApp
from app.app.app_runtime import AppRuntime
from app.app.llm_app import LlmApp
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbApp, TbConversation, TbConversationMessage
from app.model.conversation_model import (
    ConversationCreateReq,
    ConversationMessageResp,
    ConversationResp,
    ConversationUpdateReq,
)
from app.model.open_model import AgentRunRequest, LlmAppRunReq, ModelGatewayChatMessage

logger = logging.getLogger(__name__)

MAX_CONTEXT_TURNS = 20


class ConversationService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._app_runtime = AppRuntime()
        self._llm_app = LlmApp(app_runtime=self._app_runtime)
        self._agent_app = AgentApp(app_runtime=self._app_runtime)

    # ── CRUD ──

    def create_conversation(
        self,
        db: Session,
        req: ConversationCreateReq,
        req_ctx: RequestContext,
    ) -> ConversationResp:
        app_id = int(req.app_id)
        app = db.get(TbApp, app_id)
        if not app:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "app not found")
        if app.app_status != "published":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not published")

        now = req_ctx.request_time_ms
        entity = TbConversation(
            id=self._id_generator.next_id(),
            user_id=req_ctx.user_id,
            app_id=app_id,
            title="",
            status="active",
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)
        return self._to_conversation_resp(entity, app)

    def page_conversations(
        self,
        db: Session,
        user_id: int,
        page_no: int,
        page_size: int,
    ) -> tuple[list[ConversationResp], int]:
        base = select(TbConversation).where(
            TbConversation.user_id == user_id,
            TbConversation.status == "active",
        )
        total = db.scalar(select(func.count()).select_from(base.subquery()))

        rows = db.scalars(
            base.order_by(desc(TbConversation.update_time))
            .offset((page_no - 1) * page_size)
            .limit(page_size)
        ).all()

        result: list[ConversationResp] = []
        for conv in rows:
            app = db.get(TbApp, conv.app_id)
            resp = self._to_conversation_resp(conv, app)
            # 取最新一条消息作为预览
            last_msg = db.scalar(
                select(TbConversationMessage.content)
                .where(TbConversationMessage.conversation_id == conv.id)
                .order_by(desc(TbConversationMessage.create_time))
                .limit(1)
            )
            resp.last_message = _truncate(last_msg, 100) if last_msg else None
            result.append(resp)
        return result, total or 0

    def get_conversation(self, db: Session, conversation_id: int, user_id: int) -> ConversationResp:
        conv = self._get_own_conversation(db, conversation_id, user_id)
        app = db.get(TbApp, conv.app_id)
        return self._to_conversation_resp(conv, app)

    def update_conversation(
        self,
        db: Session,
        conversation_id: int,
        req: ConversationUpdateReq,
        req_ctx: RequestContext,
    ) -> ConversationResp:
        conv = self._get_own_conversation(db, conversation_id, req_ctx.user_id)
        if req.title is not None:
            conv.title = req.title
        if req.status is not None:
            conv.status = req.status
        conv.update_time = req_ctx.request_time_ms
        conv.update_user = req_ctx.user_id
        db.commit()
        db.refresh(conv)
        app = db.get(TbApp, conv.app_id)
        return self._to_conversation_resp(conv, app)

    def delete_conversation(self, db: Session, conversation_id: int, user_id: int) -> None:
        conv = self._get_own_conversation(db, conversation_id, user_id)
        db.execute(
            delete(TbConversationMessage).where(TbConversationMessage.conversation_id == conv.id)
        )
        db.delete(conv)
        db.commit()

    def list_messages(
        self, db: Session, conversation_id: int, user_id: int
    ) -> list[ConversationMessageResp]:
        self._get_own_conversation(db, conversation_id, user_id)
        rows = db.scalars(
            select(TbConversationMessage)
            .where(TbConversationMessage.conversation_id == conversation_id)
            .order_by(TbConversationMessage.create_time)
        ).all()
        return [self._to_message_resp(msg) for msg in rows]

    # ── 流式对话 ──

    async def send_message_stream(
        self,
        db: Session,
        conversation_id: int,
        content: str,
        req_ctx: RequestContext,
    ) -> AsyncGenerator[str, None]:
        from app.db.session import SessionLocal

        conv = self._get_own_conversation(db, conversation_id, req_ctx.user_id)
        app = self._app_runtime.get_app(db, conv.app_id)
        if app.app_type not in ("llm", "agent"):
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"streaming not supported for app type: {app.app_type}",
            )

        now = req_ctx.request_time_ms

        # 保存用户消息
        user_msg = TbConversationMessage(
            id=self._id_generator.next_id(),
            conversation_id=conversation_id,
            role="user",
            content=content,
            create_time=now,
            create_user=req_ctx.user_id,
        )
        db.add(user_msg)

        # 首条用户消息时自动设置标题
        user_msg_count = db.scalar(
            select(func.count()).select_from(
                select(TbConversationMessage)
                .where(
                    TbConversationMessage.conversation_id == conversation_id,
                    TbConversationMessage.role == "user",
                )
                .subquery()
            )
        )
        if (user_msg_count or 0) == 0:
            conv.title = _truncate(content, 30)

        conv.update_time = now
        conv.update_user = req_ctx.user_id
        db.commit()

        # 加载历史消息构建上下文
        history_rows = db.scalars(
            select(TbConversationMessage)
            .where(
                TbConversationMessage.conversation_id == conversation_id,
                TbConversationMessage.role.in_(["user", "assistant"]),
            )
            .order_by(TbConversationMessage.create_time)
        ).all()

        # 限制上下文窗口
        if len(history_rows) > MAX_CONTEXT_TURNS * 2:
            history_rows = history_rows[-(MAX_CONTEXT_TURNS * 2) :]

        messages = [
            ModelGatewayChatMessage(role=msg.role, content=msg.content or "")
            for msg in history_rows
        ]

        # 准备完毕，关闭 session
        app_id = app.id
        app_type = app.app_type
        db.close()

        # 调用应用执行引擎
        if app_type == "llm":
            llm_req = LlmAppRunReq(app_id=app_id, messages=messages)
            inner_gen = self._llm_app.stream(
                db=SessionLocal(),
                req=llm_req,
                req_ctx=req_ctx,
                request_type="chat",
            )
        else:
            agent_req = AgentRunRequest(app_id=app_id, messages=messages)
            inner_gen = self._agent_app.stream(
                db=SessionLocal(),
                req=agent_req,
                req_ctx=req_ctx,
                request_type="chat",
            )

        # 透传 SSE 事件，同时收集完整回复和工具调用
        full_content = ""
        tool_calls: list[dict[str, Any]] = []
        metadata_extra: dict[str, Any] = {}

        try:
            async for chunk in inner_gen:
                # 解析事件以收集内容
                if chunk.startswith("event: token\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        token_data = json.loads(data_line)
                        full_content += token_data.get("content", "")
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: tool_call_start\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        tc_data = json.loads(data_line)
                        tool_calls.append(
                            {
                                "tool_call_id": tc_data.get("tool_call_id", ""),
                                "name": tc_data.get("name", ""),
                                "arguments": tc_data.get("arguments"),
                                "status": "running",
                                "result": None,
                            }
                        )
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: tool_call_end\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        tc_data = json.loads(data_line)
                        tc_id = tc_data.get("tool_call_id", "")
                        for tc in tool_calls:
                            if tc["tool_call_id"] == tc_id:
                                tc["result"] = tc_data.get("result", "")
                                tc["status"] = tc_data.get("status", "success")
                                break
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: message_complete\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        mc_data = json.loads(data_line)
                        metadata_extra["usage"] = mc_data.get("usage", {})
                        metadata_extra["sources"] = mc_data.get("sources")
                    except (IndexError, json.JSONDecodeError):
                        pass
                elif chunk.startswith("event: done\n"):
                    try:
                        data_line = chunk.split("data: ", 1)[1].split("\n")[0]
                        done_data = json.loads(data_line)
                        metadata_extra["latency_ms"] = done_data.get("latency_ms")
                    except (IndexError, json.JSONDecodeError):
                        pass

                yield chunk

        finally:
            # 保存工具调用消息 + AI 回复消息
            if full_content or tool_calls:
                log_db = SessionLocal()
                try:
                    now_ms = int(time.time() * 1000)

                    # 先保存工具调用消息
                    for tc in tool_calls:
                        tool_msg = TbConversationMessage(
                            id=self._id_generator.next_id(),
                            conversation_id=conversation_id,
                            role="tool",
                            content=tc.get("result") or "",
                            metadata_=json.dumps(
                                {
                                    "tool_name": tc["name"],
                                    "tool_call_id": tc["tool_call_id"],
                                    "arguments": tc.get("arguments"),
                                    "status": tc.get("status", "success"),
                                },
                                ensure_ascii=False,
                            ),
                            create_time=now_ms,
                            create_user=None,
                        )
                        log_db.add(tool_msg)

                    # 保存 AI 回复消息
                    if full_content:
                        ai_msg = TbConversationMessage(
                            id=self._id_generator.next_id(),
                            conversation_id=conversation_id,
                            role="assistant",
                            content=full_content,
                            metadata_=(
                                json.dumps(metadata_extra, ensure_ascii=False)
                                if metadata_extra
                                else None
                            ),
                            create_time=now_ms,
                            create_user=None,
                        )
                        log_db.add(ai_msg)

                    # 更新会话时间
                    db_conv = log_db.get(TbConversation, conversation_id)
                    if db_conv:
                        db_conv.update_time = now_ms
                    log_db.commit()
                except Exception:
                    logger.exception(
                        "failed to save messages for conversation %s",
                        conversation_id,
                    )
                finally:
                    log_db.close()

    # ── Helpers ──

    def _get_own_conversation(
        self, db: Session, conversation_id: int, user_id: int
    ) -> TbConversation:
        conv = db.get(TbConversation, conversation_id)
        if not conv:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "conversation not found")
        if conv.user_id != user_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, "conversation not owned by user")
        return conv

    def _to_conversation_resp(self, conv: TbConversation, app: TbApp | None) -> ConversationResp:
        return ConversationResp(
            id=str(conv.id),
            app_id=str(conv.app_id),
            app_type=app.app_type if app else "",
            app_name=app.name if app else "",
            title=conv.title or "",
            status=conv.status,
            create_time=conv.create_time,
            update_time=conv.update_time,
        )

    def _to_message_resp(self, msg: TbConversationMessage) -> ConversationMessageResp:
        metadata = None
        if msg.metadata_:
            try:
                metadata = json.loads(msg.metadata_)
            except (ValueError, TypeError):
                metadata = msg.metadata_
        return ConversationMessageResp(
            id=str(msg.id),
            conversation_id=str(msg.conversation_id),
            role=msg.role,
            content=msg.content,
            metadata=metadata,
            create_time=msg.create_time,
        )


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
