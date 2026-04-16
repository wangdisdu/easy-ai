from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from deepagents import create_deep_agent
from langfuse import propagate_attributes
from langfuse.langchain import CallbackHandler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app.app_runtime import AppRuntime
from app.app.langchain_util import LangChainUtil
from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.mcp_client import call_tool as mcp_call_tool
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.core.sse import (
    SSE_EVENT_DONE,
    SSE_EVENT_ERROR,
    SSE_EVENT_MESSAGE_COMPLETE,
    SSE_EVENT_METADATA,
    SSE_EVENT_TOKEN,
    SSE_EVENT_TOOL_CALL_END,
    SSE_EVENT_TOOL_CALL_START,
    format_sse_done,
    format_sse_event,
)
from app.db.schema import TbAppSkill, TbAppTool, TbMcpServer, TbSkill, TbSkillTool, TbTool
from app.model.open_model import AgentRunRequest
from app.service.app_log_service import AppLogService

logger = logging.getLogger(__name__)


class AgentApp:
    """利用 DeepAgents + LiteLLM + 技能 + 工具运行 Agent 应用。"""

    def __init__(
        self,
        app_runtime: AppRuntime | None = None,
        langchain_util: LangChainUtil | None = None,
        log_service: AppLogService | None = None,
    ) -> None:
        self._app_runtime = app_runtime or AppRuntime()
        self._langchain_util = langchain_util or LangChainUtil()
        self._log_service = log_service or AppLogService(
            SnowflakeGenerator(settings.snowflake_worker_id)
        )

    def run(
        self,
        db: Session,
        req: AgentRunRequest,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> dict[str, Any]:
        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "agent":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not agent type")

        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        app_config = self._app_runtime.get_app_config(db, req.app_id)
        model = self._langchain_util.build_chat_model(runtime_config)
        tools = self._build_tools(db, req.app_id)
        system_prompt = self._build_system_prompt(db, req.app_id, app_config)
        agent = self._create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            app_config=app_config,
        )
        payload = {"messages": [message.model_dump() for message in req.messages]}
        observation_metadata = {
            "app_id": str(app.id),
            "app_name": app.name,
            "app_type": app.app_type,
            "request_type": request_type,
        }
        handler = CallbackHandler()
        started_at = time.perf_counter()
        try:
            with propagate_attributes(metadata=observation_metadata):
                result = agent.invoke(payload, config={"callbacks": [handler]})
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = handler.last_trace_id
            serialized_result = self._langchain_util.serialize_result(result)
            token_usage = self._langchain_util.extract_token_usage(serialized_result)
            response = {
                "app_id": str(app.id),
                "app_type": app.app_type,
                "model": runtime_config.model,
                "result": serialized_result,
                "latency_ms": latency_ms,
            }
            self._log_service.create_log(
                db,
                app_id=app.id,
                app_type=app.app_type,
                provider_id=runtime_config.provider_id,
                model_id=runtime_config.model_id,
                model=runtime_config.model,
                request_type=request_type,
                request_payload=payload,
                response_payload=response,
                success=True,
                response_status=200,
                latency_ms=latency_ms,
                error_message=None,
                langfuse_trace_id=trace_id,
                total_tokens=token_usage["total_tokens"],
                input_tokens=token_usage["input_tokens"],
                output_tokens=token_usage["output_tokens"],
                now=req_ctx.request_time_ms,
                user_id=req_ctx.user_id,
            )
            return response
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = handler.last_trace_id
            self._log_service.create_log(
                db,
                app_id=app.id,
                app_type=app.app_type,
                provider_id=runtime_config.provider_id,
                model_id=runtime_config.model_id,
                model=runtime_config.model,
                request_type=request_type,
                request_payload=payload,
                response_payload=None,
                success=False,
                response_status=None,
                latency_ms=latency_ms,
                error_message=str(exc),
                langfuse_trace_id=trace_id,
                total_tokens=None,
                input_tokens=None,
                output_tokens=None,
                now=req_ctx.request_time_ms,
                user_id=req_ctx.user_id,
            )
            raise

    async def stream(
        self,
        db: Session,
        req: AgentRunRequest,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> AsyncGenerator[str, None]:
        """流式执行 Agent 应用，通过 SSE 事件输出 token 和工具调用过程。

        db 会在流开始前关闭；日志写入在 finally 块中使用独立 session。
        """
        from app.db.session import SessionLocal

        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "agent":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not agent type")

        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        app_config = self._app_runtime.get_app_config(db, req.app_id)
        model = self._langchain_util.build_chat_model(runtime_config)
        tools = self._build_tools(db, req.app_id)
        system_prompt = self._build_system_prompt(db, req.app_id, app_config)
        agent = self._create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            app_config=app_config,
        )
        payload = {"messages": [message.model_dump() for message in req.messages]}
        observation_metadata = {
            "app_id": str(app.id),
            "app_name": app.name,
            "app_type": app.app_type,
            "request_type": request_type,
        }

        # 流前 DB 操作完成，关闭 session
        app_id = app.id
        app_type = app.app_type
        db.close()

        handler = CallbackHandler()
        started_at = time.perf_counter()
        full_content = ""
        token_usage: dict[str, int | None] = {
            "total_tokens": None,
            "input_tokens": None,
            "output_tokens": None,
        }
        accumulated_usage: dict[str, int] = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        usage_found = False
        success = True
        error_message: str | None = None
        trace_id: str | None = None

        yield format_sse_event(
            SSE_EVENT_METADATA,
            {
                "app_id": str(app_id),
                "app_type": app_type,
                "model": runtime_config.model,
            },
        )

        try:
            with propagate_attributes(metadata=observation_metadata):
                async for event in agent.astream_events(
                    payload, version="v2", config={"callbacks": [handler]}
                ):
                    kind = event.get("event")

                    if kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            full_content += chunk.content
                            yield format_sse_event(
                                SSE_EVENT_TOKEN,
                                {
                                    "content": chunk.content,
                                },
                            )
                        usage = getattr(chunk, "usage_metadata", None) if chunk else None
                        if isinstance(usage, dict) and usage.get("total_tokens"):
                            usage_found = True
                            accumulated_usage["total_tokens"] += usage.get("total_tokens", 0)
                            accumulated_usage["input_tokens"] += usage.get("input_tokens", 0)
                            accumulated_usage["output_tokens"] += usage.get("output_tokens", 0)

                    elif kind == "on_tool_start":
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_START,
                            {
                                "tool_call_id": event.get("run_id", ""),
                                "name": event.get("name", ""),
                                "arguments": event.get("data", {}).get("input", {}),
                            },
                        )

                    elif kind == "on_tool_end":
                        output = event.get("data", {}).get("output", "")
                        if hasattr(output, "content"):
                            output = output.content
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_END,
                            {
                                "tool_call_id": event.get("run_id", ""),
                                "name": event.get("name", ""),
                                "result": str(output) if output else "",
                                "status": "success",
                            },
                        )

                    elif kind == "on_tool_error":
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_END,
                            {
                                "tool_call_id": event.get("run_id", ""),
                                "name": event.get("name", ""),
                                "result": str(event.get("data", {}).get("error", "")),
                                "status": "error",
                            },
                        )

            if usage_found:
                token_usage = {
                    "total_tokens": accumulated_usage["total_tokens"],
                    "input_tokens": accumulated_usage["input_tokens"],
                    "output_tokens": accumulated_usage["output_tokens"],
                }

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = handler.last_trace_id

            yield format_sse_event(
                SSE_EVENT_MESSAGE_COMPLETE,
                {
                    "content": full_content,
                    "usage": token_usage,
                },
            )
            yield format_sse_event(
                SSE_EVENT_DONE,
                {
                    "latency_ms": latency_ms,
                    **token_usage,
                },
            )
            yield format_sse_done()

        except Exception as exc:
            success = False
            error_message = str(exc)
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = handler.last_trace_id
            yield format_sse_event(
                SSE_EVENT_ERROR,
                {
                    "code": "INTERNAL_ERROR",
                    "message": error_message,
                },
            )
            yield format_sse_done()

        finally:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = trace_id or handler.last_trace_id
            log_db = SessionLocal()
            try:
                response_payload = (
                    {
                        "app_id": str(app_id),
                        "app_type": app_type,
                        "model": runtime_config.model,
                        "result": {"content": full_content},
                        "latency_ms": latency_ms,
                    }
                    if success
                    else None
                )
                self._log_service.create_log(
                    log_db,
                    app_id=app_id,
                    app_type=app_type,
                    provider_id=runtime_config.provider_id,
                    model_id=runtime_config.model_id,
                    model=runtime_config.model,
                    request_type=request_type,
                    request_payload=payload,
                    response_payload=response_payload,
                    success=success,
                    response_status=200 if success else None,
                    latency_ms=latency_ms,
                    error_message=error_message,
                    langfuse_trace_id=trace_id,
                    total_tokens=token_usage["total_tokens"],
                    input_tokens=token_usage["input_tokens"],
                    output_tokens=token_usage["output_tokens"],
                    now=req_ctx.request_time_ms,
                    user_id=req_ctx.user_id,
                )
            except Exception:
                logger.exception("failed to write stream log for app %s", app_id)
            finally:
                log_db.close()

    def _create_deep_agent(
        self,
        *,
        model: Any,
        tools: list[Any],
        system_prompt: str,
        app_config: dict[str, Any],
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "system_prompt": system_prompt,
        }
        subagents = app_config.get("sub_agents")
        if isinstance(subagents, list) and subagents:
            kwargs["subagents"] = subagents
        return create_deep_agent(**kwargs)

    def _build_system_prompt(self, db: Session, app_id: int, app_config: dict[str, Any]) -> str:
        parts: list[str] = []
        system_prompt = app_config.get("system_prompt")
        if isinstance(system_prompt, str) and system_prompt.strip():
            parts.append(system_prompt.strip())

        skill_rows = db.scalars(select(TbAppSkill).where(TbAppSkill.app_id == app_id)).all()
        if skill_rows:
            parts.append("以下是当前可用技能，请在需要时遵循其说明：")
        for binding in skill_rows:
            skill = db.get(TbSkill, binding.skill_id)
            if not skill:
                continue
            parts.append(f"[技能:{skill.name}]\n{skill.instruction}")

        return "\n\n".join(parts).strip()

    def _build_tools(self, db: Session, app_id: int) -> list[Any]:
        # 收集应用直接绑定的工具 + 应用所绑定技能依赖的工具，按 tool_id 去重
        tool_ids: list[int] = []
        seen: set[int] = set()

        for binding in db.scalars(select(TbAppTool).where(TbAppTool.app_id == app_id)).all():
            if binding.tool_id not in seen:
                seen.add(binding.tool_id)
                tool_ids.append(binding.tool_id)

        skill_bindings = db.scalars(select(TbAppSkill).where(TbAppSkill.app_id == app_id)).all()
        if skill_bindings:
            skill_ids = [b.skill_id for b in skill_bindings]
            skill_tool_rows = db.scalars(
                select(TbSkillTool).where(TbSkillTool.skill_id.in_(skill_ids))
            ).all()
            for row in skill_tool_rows:
                if row.tool_id not in seen:
                    seen.add(row.tool_id)
                    tool_ids.append(row.tool_id)

        tools: list[Any] = []
        for tool_id in tool_ids:
            tool = db.get(TbTool, tool_id)
            if not tool or tool.tool_status != "enabled":
                continue
            tools.append(self._build_tool(db, tool))
        return tools

    def _build_tool(self, db: Session, tool: TbTool) -> Any:
        parameters = self._parse_json(tool.parameters)
        if tool.source == "api":
            func = self._build_api_tool_callable(tool)
        elif tool.source == "mcp":
            func = self._build_mcp_tool_callable(db, tool)
        else:
            raise ServiceError(
                ErrorCode.INTERNAL_ERROR,
                f"unsupported tool source: {tool.source}",
            )
        return self._langchain_util.build_structured_tool(
            name=tool.tool_name,
            description=tool.description,
            schema=parameters,
            func=func,
        )

    def _build_mcp_tool_callable(self, db: Session, tool: TbTool):
        if tool.mcp_server_id is None:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"mcp tool {tool.tool_name} missing mcp_server_id",
            )
        server = db.get(TbMcpServer, tool.mcp_server_id)
        if not server:
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND,
                f"mcp server {tool.mcp_server_id} not found",
            )
        if server.server_status != "enabled":
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"mcp server {server.server_name} is disabled",
            )

        transport = server.transport
        endpoint_url = server.endpoint_url
        headers = self._parse_mcp_headers(server.headers)
        remote_tool_name = tool.tool_name

        def call_mcp_tool(**kwargs: Any) -> str:
            try:
                return mcp_call_tool(
                    transport=transport,
                    url=endpoint_url,
                    tool_name=remote_tool_name,
                    arguments=kwargs,
                    headers=headers,
                )
            except ServiceError:
                raise
            except Exception as exc:
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    f"mcp tool {remote_tool_name} invocation failed: {exc}",
                ) from exc

        return call_mcp_tool

    def _parse_mcp_headers(self, raw: str | None) -> dict[str, str] | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(parsed, dict):
            return None
        return {str(k): str(v) for k, v in parsed.items()}

    def _build_api_tool_callable(self, tool: TbTool):
        api_config = self._parse_json(tool.api_config)
        method = str(api_config.get("method") or "POST").upper()
        url = str(api_config.get("url") or api_config.get("endpoint") or "")
        headers_config = api_config.get("headers") or []
        body_template = api_config.get("body")

        def call_api_tool(**kwargs: Any) -> str:
            final_url = self._render_template(url, kwargs)
            if not final_url:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"tool {tool.tool_name} api url missing")

            headers: dict[str, str] = {}
            if isinstance(headers_config, list):
                for item in headers_config:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("key")
                    if not key:
                        continue
                    headers[str(key)] = self._render_template(str(item.get("value") or ""), kwargs)

            json_body: Any = None
            content: str | None = None
            if isinstance(body_template, dict):
                json_body = self._render_object(body_template, kwargs)
            elif isinstance(body_template, str) and body_template:
                rendered = self._render_template(body_template, kwargs)
                try:
                    json_body = json.loads(rendered)
                except ValueError:
                    content = rendered

            with httpx.Client(timeout=30.0) as client:
                response = client.request(
                    method,
                    final_url,
                    headers=headers,
                    json=json_body,
                    content=content,
                )
            if response.status_code >= 400:
                error_detail = (
                    f"tool {tool.tool_name} request failed: "
                    f"status={response.status_code}, body={response.text}"
                )
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    error_detail,
                )
            return response.text

        return call_api_tool

    def _render_template(self, template: str, values: dict[str, Any]) -> str:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def _render_object(self, value: Any, values: dict[str, Any]) -> Any:
        if isinstance(value, str):
            return self._render_template(value, values)
        if isinstance(value, list):
            return [self._render_object(item, values) for item in value]
        if isinstance(value, dict):
            return {key: self._render_object(item, values) for key, item in value.items()}
        return value

    def _parse_json(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
