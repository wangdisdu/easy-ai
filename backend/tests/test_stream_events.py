"""Agent 流式协议 v1 的纯逻辑单元测试。

覆盖本次重构风险最高的两块：
- ``MessageStreamState`` 块生命周期合成（text / tool_use 块切换、并行工具、收尾）
- 边界序列化器 ``_frame``（信封字段、type 入载荷、无 SSE event: 行）

不接 DB / 不跑真流，纯对象断言。
"""

from __future__ import annotations

import json

from app.core.sse import (
    PROTOCOL_VERSION,
    BlockDelta,
    BlockStarted,
    BlockStopped,
    MessageCompleted,
    MessageStarted,
    MessageStreamState,
    RunError,
    RunStarted,
    ToolStarted,
    ToolUpdated,
    _frame,
    format_sse_done,
    new_run_id,
)


def _types(events) -> list[str]:
    return [e.type for e in events]


# ── MessageStreamState：块生命周期 ──


def test_text_only_single_block() -> None:
    m = MessageStreamState("r1")
    evs = m.text("你好") + m.text("世界") + m.finish()
    assert _types(evs) == [
        "message.started",
        "block.started",
        "block.delta",
        "block.delta",
        "block.stopped",
        "message.completed",
    ]
    # 两段 delta 同属一个文本块，不重开
    deltas = [e for e in evs if isinstance(e, BlockDelta)]
    assert {d.block_index for d in deltas} == {0}
    assert [d.delta for d in deltas] == ["你好", "世界"]
    started = next(e for e in evs if isinstance(e, BlockStarted))
    assert started.block_type == "text"


def test_empty_text_ignored_and_no_message_without_content() -> None:
    m = MessageStreamState("r1")
    assert m.text("") == []
    # 从未产出任何内容 → finish 不发 message.started/completed
    assert m.finish() == []


def test_text_tool_text_block_switching() -> None:
    m = MessageStreamState("r1")
    evs = (
        m.text("思考中")
        + m.tool_start("tc1", "search", {"q": "x"})
        + m.tool_end("tc1", "completed", "ok")
        + m.text("结论")
        + m.finish()
    )
    assert _types(evs) == [
        "message.started",
        "block.started",  # text block 0
        "block.delta",
        "block.stopped",  # text 0 关闭（工具开始前）
        "block.started",  # tool_use block 1
        "tool.started",
        "tool.updated",
        "block.stopped",  # tool block 1 关闭
        "block.started",  # 新 text block 2
        "block.delta",
        "block.stopped",  # finish 关 text 2
        "message.completed",
    ]
    tool_started = next(e for e in evs if isinstance(e, ToolStarted))
    assert tool_started.block_index == 1
    assert tool_started.status == "pending"
    assert tool_started.arguments == {"q": "x"}
    tool_updated = next(e for e in evs if isinstance(e, ToolUpdated))
    assert tool_updated.status == "completed"
    assert tool_updated.result == "ok"
    # 工具前后两个文本块 index 不同
    text_blocks = [
        e.block_index for e in evs if isinstance(e, BlockStarted) and e.block_type == "text"
    ]
    assert text_blocks == [0, 2]


def test_tool_without_preceding_text() -> None:
    m = MessageStreamState("r1")
    evs = m.tool_start("tc1", "do", {}) + m.tool_end("tc1", "failed", "boom") + m.finish()
    assert _types(evs) == [
        "message.started",
        "block.started",  # tool_use block 0
        "tool.started",
        "tool.updated",
        "block.stopped",
        "message.completed",
    ]
    assert next(e for e in evs if isinstance(e, ToolUpdated)).status == "failed"


def test_parallel_tools_distinct_blocks() -> None:
    m = MessageStreamState("r1")
    evs = (
        m.tool_start("a", "ta", {})
        + m.tool_start("b", "tb", {})
        + m.tool_end("a", "completed", "ra")
        + m.tool_end("b", "completed", "rb")
        + m.finish()
    )
    starts = [e for e in evs if isinstance(e, ToolStarted)]
    assert {s.tool_call_id: s.block_index for s in starts} == {"a": 0, "b": 1}
    stopped_idx = [e.block_index for e in evs if isinstance(e, BlockStopped)]
    assert sorted(stopped_idx) == [0, 1]
    # 收尾不再重复关闭已结束的工具块
    assert _types(m.finish()) == []


def test_finish_closes_unterminated_tool_block() -> None:
    m = MessageStreamState("r1")
    evs = m.tool_start("tc1", "hang", {}) + m.finish()
    # 工具未 end，finish 仍补 block.stopped + message.completed
    assert _types(evs) == [
        "message.started",
        "block.started",
        "tool.started",
        "block.stopped",
        "message.completed",
    ]


def test_message_id_stable_across_calls() -> None:
    m = MessageStreamState("r1")
    evs = m.text("a") + m.text("b") + m.finish()
    ids = {getattr(e, "message_id", None) for e in evs if hasattr(e, "message_id")}
    ids.discard(None)
    assert len(ids) == 1


# ── 边界序列化器 ──


def test_frame_envelope_and_no_event_line() -> None:
    ev = RunStarted(run_id="r1", ext={"app_type": "agent"}, thread_id="c1")
    frame = _frame(ev, 7)
    assert frame.startswith("data: ")
    assert "event:" not in frame
    assert frame.endswith("\n\n")
    payload = json.loads(frame[len("data: ") : -2])
    assert payload["type"] == "run.started"
    assert payload["v"] == PROTOCOL_VERSION
    assert payload["seq"] == 7
    assert payload["run_id"] == "r1"
    assert payload["ext"] == {"app_type": "agent"}
    assert payload["thread_id"] == "c1"
    # parent_run_id 为空时不出现在载荷里
    assert "parent_run_id" not in payload


def test_run_started_omits_optional_when_absent() -> None:
    payload = json.loads(_frame(RunStarted(run_id="r1"), 0)[len("data: ") : -2])
    assert "thread_id" not in payload
    assert "parent_run_id" not in payload


def test_tool_updated_result_optional() -> None:
    p_none = json.loads(
        _frame(ToolUpdated(run_id="r1", tool_call_id="t", status="pending"), 0)[len("data: ") : -2]
    )
    assert "result" not in p_none
    p_res = json.loads(
        _frame(ToolUpdated(run_id="r1", tool_call_id="t", status="failed", result="x"), 1)[
            len("data: ") : -2
        ]
    )
    assert p_res["result"] == "x"


def test_run_error_body() -> None:
    payload = json.loads(
        _frame(RunError(run_id="r1", code="E", message="boom", retriable=True), 0)[
            len("data: ") : -2
        ]
    )
    assert payload["code"] == "E"
    assert payload["message"] == "boom"
    assert payload["retriable"] is True


def test_done_sentinel() -> None:
    assert format_sse_done() == "data: [DONE]\n\n"


def test_new_run_id_unique_prefixed() -> None:
    a, b = new_run_id(), new_run_id()
    assert a != b
    assert a.startswith("r_") and b.startswith("r_")


def test_message_started_default_role() -> None:
    payload = json.loads(
        _frame(MessageStarted(run_id="r1", message_id="m1"), 0)[len("data: ") : -2]
    )
    assert payload["role"] == "assistant"
    assert payload["message_id"] == "m1"


def test_block_event_bodies() -> None:
    bs = json.loads(
        _frame(BlockStarted(run_id="r", message_id="m", block_index=2, block_type="thought"), 0)[
            len("data: ") : -2
        ]
    )
    assert (bs["block_index"], bs["block_type"]) == (2, "thought")
    mc = json.loads(_frame(MessageCompleted(run_id="r", message_id="m"), 0)[len("data: ") : -2])
    assert mc["type"] == "message.completed" and mc["message_id"] == "m"
