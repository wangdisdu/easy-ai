from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, create_model

from app.model.open_model import LiteLLMRuntimeConfig


class LangChainUtil:
    """LangChain 对接 LiteLLM 网关。"""

    def build_chat_model(self, runtime_config: LiteLLMRuntimeConfig) -> Any:
        model = ChatOpenAI(
            model=runtime_config.model,
            base_url=runtime_config.base_url,
            api_key=runtime_config.api_key,
            **dict(runtime_config.model_setting),
        )
        # 把 DB 配置的 max_input_tokens 灌进 model.profile，让 DeepAgents 的
        # SummarizationMiddleware 走 fraction 触发条件，而不是 170k 兜底。
        # 私有 / 国产模型 LangChain 注册表通常没有 profile，这里覆盖式合并。
        if runtime_config.max_input_tokens is not None:
            existing = dict(model.profile or {})
            existing["max_input_tokens"] = runtime_config.max_input_tokens
            model.profile = existing
        return model

    def build_structured_tool(
        self,
        *,
        name: str,
        description: str,
        schema: dict[str, Any] | None,
        func: Callable[..., str],
    ) -> Any:
        args_schema = self._build_args_schema(name, schema or {})
        return StructuredTool.from_function(
            func=func,
            name=name,
            description=description,
            args_schema=args_schema,
        )

    def create_agent(
        self,
        *,
        model: Any,
        tools: list[Any],
        system_prompt: str | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"model": model, "tools": tools}
        if system_prompt:
            kwargs["system_prompt"] = system_prompt
        return create_agent(**kwargs)

    def _build_args_schema(self, tool_name: str, schema: dict[str, Any]) -> type:
        # 用工具名做模型类名后缀，避免多个工具共用同一个 Pydantic 类导致字段串扰
        sanitized = "".join(ch if ch.isalnum() else "_" for ch in tool_name) or "Tool"
        model_name = f"DynamicToolArgs_{sanitized}"

        field_definitions: dict[str, tuple[Any, Any]] = {}
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        for field_name, config in properties.items():
            field_type = self._map_json_schema_type((config or {}).get("type"))
            default = ... if field_name in required else None
            description = (config or {}).get("description")
            field_definitions[field_name] = (
                field_type,
                Field(default=default, description=description),
            )

        if not field_definitions:
            return create_model(model_name, __base__=BaseModel)

        return create_model(model_name, **field_definitions)

    @staticmethod
    def serialize_result(result: dict[str, Any]) -> dict[str, Any]:
        """将 agent.invoke() 返回的 result 转为 JSON 可序列化的 dict。

        LangChain 返回的 messages 列表中包含 HumanMessage / AIMessage / ToolMessage 等
        BaseMessage 子类实例，无法直接 JSON 序列化。这里统一调用 model_dump() 转为 dict，
        并在顶层注入 ``type`` 字段以便前端区分消息类型。
        """

        def _dump(obj: Any) -> Any:
            if isinstance(obj, BaseMessage):
                data = obj.model_dump()
                data["type"] = obj.type  # human / ai / tool / system / ...
                return data
            if isinstance(obj, list):
                return [_dump(item) for item in obj]
            if isinstance(obj, dict):
                return {k: _dump(v) for k, v in obj.items()}
            return obj

        return _dump(result)

    @staticmethod
    def extract_token_usage(
        serialized_result: dict[str, Any],
    ) -> dict[str, int | None]:
        """从序列化后的 result 中汇总所有消息的 token 用量。

        若没有任何消息包含 usage_metadata，返回全部为 None，语义上表示"无法提取"，
        与"用量为 0"区分开。
        """
        total = 0
        input_tokens = 0
        output_tokens = 0
        found = False
        messages = serialized_result.get("messages") or []
        for msg in messages:
            usage = msg.get("usage_metadata")
            if not isinstance(usage, dict):
                continue
            found = True
            total += usage.get("total_tokens", 0) or 0
            input_tokens += usage.get("input_tokens", 0) or 0
            output_tokens += usage.get("output_tokens", 0) or 0
        if not found:
            return {"total_tokens": None, "input_tokens": None, "output_tokens": None}
        return {
            "total_tokens": total,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _map_json_schema_type(self, json_type: str | None) -> Any:
        mapping: dict[str | None, Any] = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
            None: str,
        }
        return mapping.get(json_type, str)
