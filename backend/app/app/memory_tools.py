"""Agent 自带的记忆工具：remember / forget / list_my_memories。

设计约束：
- agent 写入只允许 scope='user'，scope_id 固定为当前 user。这条规则强约束在工具层，
  不让模型有机会把 app/team 级别的 prompt 污染。app 级别只能管理员用 API 写。
- 工具描述里写清楚使用场景，引导模型不要乱记瞬时信息。
"""

from __future__ import annotations

import logging
from typing import Any

from app.app.langchain_util import LangChainUtil
from app.db.session import SessionLocal
from app.service.memory_service import MemoryService

logger = logging.getLogger(__name__)


_REMEMBER_DESC = """记下一条关于当前用户的长期事实或偏好；下次对话能继续看到。

使用时机：
- 用户明确要求记住（"记住我喜欢中文回复"）
- 用户提供未来还会用到的身份信息（邮箱、姓名、所在地等）
- 用户对你的行为给出了能复用的偏好（"代码示例用 TypeScript"）
- 用户纠正你之前的事实理解

不要使用的场景：
- 一次性请求（"算 25*4"）
- 瞬时状态（"我现在在外面"）
- 寒暄、确认、感谢
- 任何 API key / token / password / 凭证类敏感信息

memory_key：用 dot 命名空间，如 "language.preference" / "profile.email" / "code.language"。
memory_value：纯文本短句，不要塞超过 300 字。已存在的 key 会被覆盖。
"""

_FORGET_DESC = """删除一条之前记下的用户记忆。

适用场景：
- 用户主动要求删除某条记忆
- 你发现旧记忆已被新的覆盖、或事实已变（用户换了邮箱等）
"""

_LIST_DESC = """查看当前用户已记下的全部长期记忆。

在 remember 之前先调用一次，避免重复记录已存在的事实。返回 key:value 列表。
"""


def build_memory_tools(
    *,
    user_id: int | None,
    app_id: int | None,
    conversation_id: int | None,
    service: MemoryService,
    langchain_util: LangChainUtil,
) -> list[Any]:
    """工厂函数：每次 agent 启动时按 run-context 闭包出一组工具。

    user_id 为空（系统调用 / 未登录）→ 返回空列表，工具不挂载。
    """
    if user_id is None:
        return []

    def _remember(memory_key: str, memory_value: str) -> str:
        logger.info(
            "[memory] tool=remember user_id=%s key=%s value_chars=%d",
            user_id,
            memory_key,
            len(memory_value or ""),
        )
        db = SessionLocal()
        try:
            service.upsert_memory(
                db,
                scope="user",
                scope_id=user_id,
                memory_key=memory_key,
                memory_value=memory_value,
                source="agent_learned",
                actor_user_id=user_id,
                app_id=app_id,
                conversation_id=conversation_id,
            )
            logger.info("[memory] tool=remember ok user_id=%s key=%s", user_id, memory_key)
            return f"已记下 {memory_key}: {memory_value}"
        except Exception as exc:
            logger.exception("[memory] tool=remember failed user_id=%s key=%s", user_id, memory_key)
            return f"记忆保存失败：{exc}"
        finally:
            db.close()

    def _forget(memory_key: str) -> str:
        logger.info("[memory] tool=forget user_id=%s key=%s", user_id, memory_key)
        db = SessionLocal()
        try:
            ok = service.delete_memory(
                db,
                scope="user",
                scope_id=user_id,
                memory_key=memory_key,
                actor_user_id=user_id,
                app_id=app_id,
                conversation_id=conversation_id,
            )
            logger.info("[memory] tool=forget ok=%s user_id=%s key=%s", ok, user_id, memory_key)
            return f"已删除 {memory_key}" if ok else f"未找到 {memory_key}（可能从未记过）"
        except Exception as exc:
            logger.exception("[memory] tool=forget failed user_id=%s key=%s", user_id, memory_key)
            return f"删除失败：{exc}"
        finally:
            db.close()

    def _list_my_memories() -> str:
        logger.info("[memory] tool=list_my_memories user_id=%s", user_id)
        db = SessionLocal()
        try:
            rows = service.list_memories(db, scope="user", scope_id=user_id, limit=200)
            logger.info("[memory] tool=list_my_memories ok user_id=%s rows=%d", user_id, len(rows))
            if not rows:
                return "（还没有记下任何关于你的事实）"
            return "\n".join(f"- {r.memory_key}: {r.memory_value}" for r in rows)
        except Exception as exc:
            logger.exception("[memory] tool=list_my_memories failed user_id=%s", user_id)
            return f"读取失败：{exc}"
        finally:
            db.close()

    remember_tool = langchain_util.build_structured_tool(
        name="remember",
        description=_REMEMBER_DESC,
        schema={
            "type": "object",
            "properties": {
                "memory_key": {
                    "type": "string",
                    "description": "唯一键，dot 命名空间，如 language.preference",
                },
                "memory_value": {
                    "type": "string",
                    "description": "纯文本短句，不要超过 300 字",
                },
            },
            "required": ["memory_key", "memory_value"],
        },
        func=_remember,
    )
    forget_tool = langchain_util.build_structured_tool(
        name="forget",
        description=_FORGET_DESC,
        schema={
            "type": "object",
            "properties": {
                "memory_key": {"type": "string", "description": "要删除的记忆键"},
            },
            "required": ["memory_key"],
        },
        func=_forget,
    )
    list_tool = langchain_util.build_structured_tool(
        name="list_my_memories",
        description=_LIST_DESC,
        schema={"type": "object", "properties": {}, "required": []},
        func=_list_my_memories,
    )
    return [remember_tool, forget_tool, list_tool]
