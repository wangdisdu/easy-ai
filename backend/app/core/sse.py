"""Agent 流式通信协议 v1 —— 单一事实源。

见 docs/agent-streaming-protocol.md。本模块定义：

- 信封与全部事件的**结构化对象**（dataclass）。协议产生收口于此，
  ``*_app.stream()`` / service / api 在内部一律传递 ``StreamEvent`` 对象，
  不再拼接或反解析 SSE 文本。
- ``MessageStreamState``：把 LangChain ``astream_events`` 的扁平 token/工具
  事件投影成"消息 → 内容块（block）→ delta"的块生命周期。
- 边界序列化：``sse_response`` 在 API 边界**一次**把对象序列化为
  ``data: <json>\\n\\n``（事件类型在载荷 ``type`` 字段，不用 SSE ``event:``
  行，使信封传输无关），并统一分配 ``seq``、补 ``[DONE]`` 哨兵。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from fastapi.responses import StreamingResponse

# 协议大版本。结构性扩展才递增；新增可选字段 / ext.* 演进不动这里。
PROTOCOL_VERSION = 1


def new_run_id() -> str:
    """一次执行的稳定 id。"""
    return f"r_{uuid.uuid4().hex}"


def _new_message_id() -> str:
    return f"m_{uuid.uuid4().hex}"


# ── 事件对象 ──
#
# 每个事件携带 run_id；type 为类常量；body() 返回事件专属载荷字段。
# 信封字段（type/v/seq/run_id）由序列化器统一拼装，事件对象不重复持有。


@dataclass
class StreamEvent:
    type: ClassVar[str] = ""
    run_id: str

    def body(self) -> dict[str, Any]:
        return {}


@dataclass
class RunStarted(StreamEvent):
    type: ClassVar[str] = "run.started"
    ext: dict[str, Any] = field(default_factory=dict)
    thread_id: str | None = None
    parent_run_id: str | None = None

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ext": self.ext}
        if self.thread_id:
            out["thread_id"] = self.thread_id
        if self.parent_run_id:
            out["parent_run_id"] = self.parent_run_id
        return out


@dataclass
class RunFinished(StreamEvent):
    type: ClassVar[str] = "run.finished"
    stop_reason: str = "end_turn"  # end_turn|max_tokens|hitl_interrupt|cancelled|error
    ext: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {"stop_reason": self.stop_reason, "ext": self.ext}


@dataclass
class RunError(StreamEvent):
    type: ClassVar[str] = "run.error"
    code: str = "INTERNAL_ERROR"
    message: str = ""
    retriable: bool = False

    def body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retriable": self.retriable}


@dataclass
class MessageStarted(StreamEvent):
    type: ClassVar[str] = "message.started"
    message_id: str = ""
    role: str = "assistant"

    def body(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "role": self.role}


@dataclass
class MessageCompleted(StreamEvent):
    type: ClassVar[str] = "message.completed"
    message_id: str = ""

    def body(self) -> dict[str, Any]:
        return {"message_id": self.message_id}


@dataclass
class BlockStarted(StreamEvent):
    type: ClassVar[str] = "block.started"
    message_id: str = ""
    block_index: int = 0
    block_type: str = "text"  # text|thought|tool_use

    def body(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "block_index": self.block_index,
            "block_type": self.block_type,
        }


@dataclass
class BlockDelta(StreamEvent):
    type: ClassVar[str] = "block.delta"
    message_id: str = ""
    block_index: int = 0
    delta: str = ""

    def body(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "block_index": self.block_index,
            "delta": self.delta,
        }


@dataclass
class BlockStopped(StreamEvent):
    type: ClassVar[str] = "block.stopped"
    message_id: str = ""
    block_index: int = 0

    def body(self) -> dict[str, Any]:
        return {"message_id": self.message_id, "block_index": self.block_index}


@dataclass
class ToolStarted(StreamEvent):
    type: ClassVar[str] = "tool.started"
    message_id: str = ""
    block_index: int = 0
    tool_call_id: str = ""
    name: str = ""
    status: str = "pending"
    arguments: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "block_index": self.block_index,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "status": self.status,
            "arguments": self.arguments,
        }


@dataclass
class ToolUpdated(StreamEvent):
    type: ClassVar[str] = "tool.updated"
    tool_call_id: str = ""
    status: str = "completed"  # pending|in_progress|completed|failed
    result: str | None = None

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"tool_call_id": self.tool_call_id, "status": self.status}
        if self.result is not None:
            out["result"] = self.result
        return out


@dataclass
class PlanUpdated(StreamEvent):
    type: ClassVar[str] = "plan.updated"
    entries: list[dict[str, Any]] = field(default_factory=list)

    def body(self) -> dict[str, Any]:
        return {"entries": self.entries}


@dataclass
class HitlRequired(StreamEvent):
    type: ClassVar[str] = "hitl.required"
    hitl_id: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    risk_level: str = "low"
    options: list[dict[str, str]] = field(default_factory=list)

    def body(self) -> dict[str, Any]:
        return {
            "hitl_id": self.hitl_id,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "options": self.options,
        }


@dataclass
class ExtReferences(StreamEvent):
    """RAG 检索引用（受控扩展，独立 ext_version）。"""

    type: ClassVar[str] = "ext.references"
    ext_version: int = 1
    items: list[dict[str, Any]] = field(default_factory=list)

    def body(self) -> dict[str, Any]:
        return {"ext_version": self.ext_version, "items": self.items}


# HITL 选项：confirm/modify 放行一次，reject 拒绝一次。
DEFAULT_HITL_OPTIONS: list[dict[str, str]] = [
    {"option_id": "confirm", "kind": "allow_once"},
    {"option_id": "modify", "kind": "allow_once"},
    {"option_id": "reject", "kind": "reject_once"},
]


class MessageStreamState:
    """把扁平的 token/工具事件投影成"消息 → 块 → delta"的块生命周期。

    LangChain ``astream_events`` 没有"块"概念，这里按规则合成：

    - 首个文本 delta 触发 ``message.started`` + ``block.started(text)``。
    - 工具调用各自成一个 ``tool_use`` 块；开始前先关闭打开的文本块。
    - 工具结束后再来的文本开新的文本块（新 block_index）。
    - ``thought`` 块仅当模型产出 reasoning 时才发（当前 litellm 链路一般不产出，
      结构上保留）。

    所有方法返回 ``list[StreamEvent]``，由调用方逐个 yield。
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.message_id = _new_message_id()
        self._started = False
        self._finished = False
        self._next_index = 0
        self._open_text_index: int | None = None
        # tool_call_id -> block_index
        self._tool_blocks: dict[str, int] = {}

    def _ensure_message(self) -> list[StreamEvent]:
        if self._started:
            return []
        self._started = True
        return [MessageStarted(run_id=self.run_id, message_id=self.message_id)]

    def _close_text(self) -> list[StreamEvent]:
        if self._open_text_index is None:
            return []
        idx = self._open_text_index
        self._open_text_index = None
        return [BlockStopped(run_id=self.run_id, message_id=self.message_id, block_index=idx)]

    def text(self, delta: str) -> list[StreamEvent]:
        if not delta:
            return []
        events = self._ensure_message()
        if self._open_text_index is None:
            idx = self._next_index
            self._next_index += 1
            self._open_text_index = idx
            events.append(
                BlockStarted(
                    run_id=self.run_id,
                    message_id=self.message_id,
                    block_index=idx,
                    block_type="text",
                )
            )
        events.append(
            BlockDelta(
                run_id=self.run_id,
                message_id=self.message_id,
                block_index=self._open_text_index,
                delta=delta,
            )
        )
        return events

    def tool_start(
        self, tool_call_id: str, name: str, arguments: dict[str, Any]
    ) -> list[StreamEvent]:
        events = self._ensure_message()
        events += self._close_text()
        idx = self._next_index
        self._next_index += 1
        self._tool_blocks[tool_call_id] = idx
        events.append(
            BlockStarted(
                run_id=self.run_id,
                message_id=self.message_id,
                block_index=idx,
                block_type="tool_use",
            )
        )
        events.append(
            ToolStarted(
                run_id=self.run_id,
                message_id=self.message_id,
                block_index=idx,
                tool_call_id=tool_call_id,
                name=name,
                status="pending",
                arguments=arguments,
            )
        )
        return events

    def tool_end(self, tool_call_id: str, status: str, result: str | None) -> list[StreamEvent]:
        events: list[StreamEvent] = [
            ToolUpdated(run_id=self.run_id, tool_call_id=tool_call_id, status=status, result=result)
        ]
        idx = self._tool_blocks.pop(tool_call_id, None)
        if idx is not None:
            events.append(
                BlockStopped(run_id=self.run_id, message_id=self.message_id, block_index=idx)
            )
        return events

    def finish(self) -> list[StreamEvent]:
        """收尾：关闭未结束的块并发 message.completed。幂等（应只调一次）。"""
        if not self._started or self._finished:
            return []
        self._finished = True
        events = self._close_text()
        for idx in self._tool_blocks.values():
            events.append(
                BlockStopped(run_id=self.run_id, message_id=self.message_id, block_index=idx)
            )
        self._tool_blocks.clear()
        events.append(MessageCompleted(run_id=self.run_id, message_id=self.message_id))
        return events


# ── 边界序列化 ──


def _frame(event: StreamEvent, seq: int) -> str:
    payload: dict[str, Any] = {
        "type": event.type,
        "v": PROTOCOL_VERSION,
        "seq": seq,
        "run_id": event.run_id,
        **event.body(),
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def format_sse_done() -> str:
    return "data: [DONE]\n\n"


async def _serialize(
    event_gen: AsyncGenerator[StreamEvent, None],
) -> AsyncGenerator[str, None]:
    """在 API 边界一次性序列化：分配单调 seq，补 [DONE] 哨兵。"""
    seq = 0
    async for event in event_gen:
        yield _frame(event, seq)
        seq += 1
    yield format_sse_done()


def sse_response(event_gen: AsyncGenerator[StreamEvent, None]) -> StreamingResponse:
    """把 StreamEvent 异步生成器封装为 SSE StreamingResponse。"""
    return StreamingResponse(
        _serialize(event_gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
