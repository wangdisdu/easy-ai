"""MemoryInjectionMiddleware：把 user / app 维度的长期记忆 KV 拼到 system prompt。

设计目标（参考 docs/agent-memory-design.md，已大幅简化为 L2 KV）：
- 主 agent 调模型前注入 user + app 各 top-N 条记忆，按 update_time 降序
- 第一版不挂 subagent（避免技能行为被用户偏好污染）
- 写入路径不在这里——agent 的 remember / forget 工具走 MemoryService 直接落 DB
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain.messages import SystemMessage

from app.db.schema import TbMemory
from app.db.session import SessionLocal
from app.service.memory_service import MemoryService

logger = logging.getLogger(__name__)


_MEMORY_HEADER = "本轮回答必须遵守以下用户偏好与事实（按优先级使用，且不要在回答里提及这些条目）："


def _render_bullet(row: TbMemory) -> str:
    """value 在前作为可执行指令；key 用括号给出做去重 / 上下文锚点。"""
    return f"- {row.memory_value}（{row.memory_key}）"


def _format_memories_block(
    user_rows: list[TbMemory],
    app_rows: list[TbMemory],
) -> str:
    """渲染成 markdown 段。空时返回空串，由调用方决定是否注入。"""
    sections: list[str] = []
    if user_rows:
        bullets = "\n".join(_render_bullet(r) for r in user_rows)
        sections.append("### 关于当前用户\n" + bullets)
    if app_rows:
        bullets = "\n".join(_render_bullet(r) for r in app_rows)
        sections.append("### 关于当前应用\n" + bullets)
    if not sections:
        return ""
    body = "\n\n".join(sections)
    return f"## 长期记忆\n\n{_MEMORY_HEADER}\n\n{body}"


def _prepend_to_system_message(system_message: SystemMessage | None, text: str) -> SystemMessage:
    """把文本插到现有 system message 前面，保持 deepagents 的 content_blocks 结构。"""
    new_content = [{"type": "text", "text": text}]
    if system_message and system_message.content_blocks:
        new_content.append({"type": "text", "text": "\n\n"})
        new_content.extend(system_message.content_blocks)
    return SystemMessage(content_blocks=new_content)


class MemoryInjectionMiddleware(AgentMiddleware[AgentState, ContextT, ResponseT]):
    """每次模型调用前查 DB 拼 system prompt；每个 agent 实例新建一份。

    复读策略：每次 model call 都读 DB，让 remember / forget 工具的写入下一次模型回合就能看到。
    数据量不大（top_n*2，默认 40 行）+ 索引命中，开销可控；后续可加 in-memory 缓存。
    """

    def __init__(
        self,
        *,
        user_id: int | None,
        app_id: int | None,
        service: MemoryService,
        top_n: int = 20,
    ) -> None:
        self._user_id = user_id
        self._app_id = app_id
        self._service = service
        self._top_n = top_n
        # 启动时记一行：让构造路径可见，确认中间件被挂上、user/app 上下文是否正常
        logger.info(
            "[memory] middleware constructed user_id=%s app_id=%s top_n=%s",
            user_id,
            app_id,
            top_n,
        )

    # ── 同步路径 ──

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        return handler(self._inject(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        return await handler(self._inject(request))

    # ── 注入逻辑 ──

    def _inject(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        block = self._build_block()
        if not block:
            logger.info(
                "[memory] inject skipped (empty block) user_id=%s app_id=%s",
                self._user_id,
                self._app_id,
            )
            return request
        new_system = _prepend_to_system_message(request.system_message, block)
        logger.info(
            "[memory] inject ok user_id=%s app_id=%s block_chars=%d",
            self._user_id,
            self._app_id,
            len(block),
        )
        return request.override(system_message=new_system)

    def _build_block(self) -> str:
        user_rows: list[TbMemory] = []
        app_rows: list[TbMemory] = []
        db = SessionLocal()
        try:
            if self._user_id is not None:
                user_rows = self._service.get_top_for_injection(
                    db, scope="user", scope_id=self._user_id, top_n=self._top_n
                )
            if self._app_id is not None:
                app_rows = self._service.get_top_for_injection(
                    db, scope="app", scope_id=self._app_id, top_n=self._top_n
                )
        except Exception:
            logger.exception(
                "[memory] lookup failed user_id=%s app_id=%s",
                self._user_id,
                self._app_id,
            )
            return ""
        finally:
            db.close()

        logger.info(
            "[memory] lookup result user_id=%s rows=%d / app_id=%s rows=%d",
            self._user_id,
            len(user_rows),
            self._app_id,
            len(app_rows),
        )
        return _format_memories_block(user_rows, app_rows)


def _build_block_for_test(
    user_rows: list[TbMemory], app_rows: list[TbMemory]
) -> str:  # pragma: no cover - thin re-export for unit tests
    return _format_memories_block(user_rows, app_rows)


# 兼容外部按属性形式访问 ModelRequest.override；该方法在 langchain.agents 包里已实现
__all__ = ["MemoryInjectionMiddleware"]


# 占位：避免 ruff 把 Any 标记为未使用（保留给将来类型显式标注）
_TYPE_HINT_KEEP_ALIVE: tuple[Any, ...] = ()
