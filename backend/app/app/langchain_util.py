from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, create_model

from app.model.open_model import LiteLLMRuntimeConfig


class LangChainUtil:
    """LangChain 对接 LiteLLM 网关。"""

    def build_chat_model(self, runtime_config: LiteLLMRuntimeConfig) -> Any:
        return ChatOpenAI(
            model=runtime_config.model,
            base_url=runtime_config.base_url,
            api_key=runtime_config.api_key,
            **dict(runtime_config.model_setting),
        )

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
