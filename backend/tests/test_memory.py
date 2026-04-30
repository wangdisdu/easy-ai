"""Memory 模块的纯逻辑单元测试。

不接 DB；service 层及 API 鉴权的 DB-touching 用例需配合 PR-G11 引入的
test fixture（pytest-postgresql 或 SQLite-in-memory + ORM 切换）后再补。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from langchain.messages import SystemMessage

from app.app.langchain_util import LangChainUtil
from app.app.memory_middleware import _format_memories_block, _prepend_to_system_message
from app.app.memory_tools import build_memory_tools
from app.core.snowflake import SnowflakeGenerator
from app.model.memory_model import MemoryUpsertReq
from app.service.memory_service import MemoryService


class _Row:
    """假 TbMemory 行：测 _format_memories_block 时只用到 memory_key / memory_value。"""

    def __init__(self, key: str, value: str) -> None:
        self.memory_key = key
        self.memory_value = value


# ── _format_memories_block ─────────────────────────────────────────


def test_format_block_empty_returns_empty_string() -> None:
    """两边都没行 → 不渲染任何 prompt 段，避免污染 system prompt。"""
    assert _format_memories_block([], []) == ""


def test_format_block_user_only() -> None:
    block = _format_memories_block(
        [_Row("language.preference", "用户偏好中文回复")],
        [],
    )
    assert "## 长期记忆" in block
    assert "### 关于当前用户" in block
    # value 在前作为可执行偏好；key 在括号里
    assert "用户偏好中文回复" in block
    assert "language.preference" in block
    assert "### 关于当前应用" not in block


def test_format_block_app_only() -> None:
    block = _format_memories_block(
        [],
        [_Row("product.alpha", "Alpha 是公司主打产品")],
    )
    assert "### 关于当前应用" in block
    assert "Alpha 是公司主打产品" in block
    assert "### 关于当前用户" not in block


def test_format_block_both() -> None:
    block = _format_memories_block(
        [_Row("k1", "v1")],
        [_Row("k2", "v2")],
    )
    assert "### 关于当前用户" in block
    assert "### 关于当前应用" in block
    # user 段在前
    assert block.index("### 关于当前用户") < block.index("### 关于当前应用")


def test_prepend_to_system_message_puts_memory_before_existing_prompt() -> None:
    existing = SystemMessage(content="你是一个代码助手。")
    result = _prepend_to_system_message(existing, "## 长期记忆\n- 用户偏好中文")
    texts = [block["text"] for block in result.content_blocks if block.get("type") == "text"]
    assert texts[0].startswith("## 长期记忆")
    assert texts[-1] == "你是一个代码助手。"


# ── build_memory_tools ─────────────────────────────────────────────


def test_build_memory_tools_no_user() -> None:
    """没登录用户 → 不挂任何工具，避免泄漏到 anonymous 上下文。"""
    svc = MemoryService(SnowflakeGenerator(1))
    tools = build_memory_tools(
        user_id=None,
        app_id=1,
        conversation_id=None,
        service=svc,
        langchain_util=LangChainUtil(),
    )
    assert tools == []


def test_build_memory_tools_with_user() -> None:
    svc = MemoryService(SnowflakeGenerator(1))
    tools = build_memory_tools(
        user_id=42,
        app_id=1,
        conversation_id=None,
        service=svc,
        langchain_util=LangChainUtil(),
    )
    names = [t.name for t in tools]
    assert names == ["remember", "forget", "list_my_memories"]


# ── MemoryUpsertReq 校验 ──────────────────────────────────────────


def test_upsert_req_rejects_bad_scope() -> None:
    with pytest.raises(ValidationError):
        MemoryUpsertReq(
            scope="team",  # type: ignore[arg-type]
            scope_id="1",
            memory_key="k",
            memory_value="v",
        )


def test_upsert_req_rejects_empty_key() -> None:
    with pytest.raises(ValidationError):
        MemoryUpsertReq(
            scope="user",
            scope_id="1",
            memory_key="",
            memory_value="v",
        )


def test_upsert_req_default_source_is_user_explicit() -> None:
    req = MemoryUpsertReq(scope="user", scope_id="1", memory_key="k", memory_value="v")
    assert req.source == "user_explicit"
