"""SSE (Server-Sent Events) 格式化工具。

为应用流式输出提供统一的 SSE 事件格式和 StreamingResponse 封装。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from fastapi.responses import StreamingResponse

# SSE 事件类型常量
SSE_EVENT_METADATA = "metadata"
SSE_EVENT_TOKEN = "token"
SSE_EVENT_TOOL_CALL_START = "tool_call_start"
SSE_EVENT_TOOL_CALL_END = "tool_call_end"
SSE_EVENT_TODO_UPDATE = "todo_update"
SSE_EVENT_MESSAGE_COMPLETE = "message_complete"
SSE_EVENT_ERROR = "error"
SSE_EVENT_DONE = "done"


def format_sse_event(event: str, data: dict[str, Any]) -> str:
    """将事件名和数据格式化为 SSE 协议文本。

    格式：
        event: {event}
        data: {json}
        <空行>
    """
    json_str = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {json_str}\n\n"


def format_sse_done() -> str:
    """生成 SSE 终止信号。"""
    return "data: [DONE]\n\n"


def sse_response(generator: AsyncGenerator[str, None]) -> StreamingResponse:
    """将异步生成器封装为 SSE StreamingResponse。"""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
