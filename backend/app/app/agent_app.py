from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx
from deepagents import create_deep_agent
from deepagents.backends.utils import create_file_data
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
from app.db.schema import TbApp, TbAppSkill, TbAppTool, TbMcpServer, TbSkill, TbSkillTool, TbTool
from app.model.open_model import AgentRunRequest
from app.service.app_log_service import ZERO_USAGE, AppLogService

logger = logging.getLogger(__name__)


@dataclass
class _Prepared:
    """run / stream 共用的一次准备结果。"""

    app: TbApp
    runtime_config: Any
    app_config: dict[str, Any]
    agent: Any
    payload: dict[str, Any]
    observation_metadata: dict[str, Any]


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
        prep = self._prepare(db, req, request_type)
        handler = CallbackHandler()
        started_at = time.perf_counter()
        try:
            with propagate_attributes(metadata=prep.observation_metadata):
                result = prep.agent.invoke(prep.payload, config={"callbacks": [handler]})
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            serialized_result = self._langchain_util.serialize_result(result)
            token_usage = self._langchain_util.extract_token_usage(serialized_result)
            response = {
                "app_id": str(prep.app.id),
                "app_type": prep.app.app_type,
                "model": prep.runtime_config.model,
                "result": serialized_result,
                "latency_ms": latency_ms,
            }
            self._log_service.log_execution(
                db,
                app=prep.app,
                runtime_config=prep.runtime_config,
                req_ctx=req_ctx,
                request_type=request_type,
                request_payload=prep.payload,
                response_payload=response,
                success=True,
                latency_ms=latency_ms,
                trace_id=handler.last_trace_id,
                error_message=None,
                token_usage=token_usage,
            )
            return response
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            self._log_service.log_execution(
                db,
                app=prep.app,
                runtime_config=prep.runtime_config,
                req_ctx=req_ctx,
                request_type=request_type,
                request_payload=prep.payload,
                response_payload=None,
                success=False,
                latency_ms=latency_ms,
                trace_id=handler.last_trace_id,
                error_message=str(exc),
                token_usage=dict(ZERO_USAGE),
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
        prep = self._prepare(db, req, request_type)
        # 流前 DB 操作完成，关闭 session（日志写入走独立 session）
        db.close()

        handler = CallbackHandler()
        started_at = time.perf_counter()
        full_content = ""
        token_usage: dict[str, int | None] = dict(ZERO_USAGE)
        # Agent 会多次调模型，usage 需按轮次累加而非取最后一次
        accumulated: dict[str, int] = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        usage_found = False
        success = True
        error_message: str | None = None
        trace_id: str | None = None

        yield format_sse_event(
            SSE_EVENT_METADATA,
            {
                "app_id": str(prep.app.id),
                "app_type": prep.app.app_type,
                "model": prep.runtime_config.model,
            },
        )

        try:
            with propagate_attributes(metadata=prep.observation_metadata):
                async for event in prep.agent.astream_events(
                    prep.payload, version="v2", config={"callbacks": [handler]}
                ):
                    kind = event.get("event")
                    data = event.get("data") or {}

                    if kind == "on_chat_model_stream":
                        chunk = data.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            full_content += chunk.content
                            yield format_sse_event(SSE_EVENT_TOKEN, {"content": chunk.content})
                        usage = getattr(chunk, "usage_metadata", None) if chunk else None
                        if isinstance(usage, dict) and usage.get("total_tokens"):
                            usage_found = True
                            for key in accumulated:
                                accumulated[key] += usage.get(key, 0)

                    elif kind == "on_tool_start":
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_START,
                            {
                                "tool_call_id": event.get("run_id", ""),
                                "name": event.get("name", ""),
                                "arguments": data.get("input", {}),
                            },
                        )

                    elif kind == "on_tool_end":
                        output = data.get("output", "")
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
                                "result": str(data.get("error", "")),
                                "status": "error",
                            },
                        )

            if usage_found:
                token_usage = dict(accumulated)

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = handler.last_trace_id

            yield format_sse_event(
                SSE_EVENT_MESSAGE_COMPLETE,
                {"content": full_content, "usage": token_usage},
            )
            yield format_sse_event(
                SSE_EVENT_DONE,
                {"latency_ms": latency_ms, **token_usage},
            )
            yield format_sse_done()

        except Exception as exc:
            success = False
            error_message = str(exc)
            trace_id = handler.last_trace_id
            yield format_sse_event(
                SSE_EVENT_ERROR,
                {"code": "INTERNAL_ERROR", "message": error_message},
            )
            yield format_sse_done()

        finally:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            trace_id = trace_id or handler.last_trace_id
            self._log_stream_finally(
                prep,
                req_ctx,
                request_type,
                success=success,
                full_content=full_content,
                latency_ms=latency_ms,
                trace_id=trace_id,
                error_message=error_message,
                token_usage=token_usage,
            )

    def _prepare(self, db: Session, req: AgentRunRequest, request_type: str) -> _Prepared:
        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "agent":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not agent type")

        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        app_config = self._app_runtime.get_app_config(db, req.app_id)
        model = self._langchain_util.build_chat_model(runtime_config)
        tools = self._build_tools(db, req.app_id)
        system_prompt = (app_config.get("system_prompt") or "").strip()
        skill_files = self._build_skill_files(db, req.app_id)
        agent_kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "system_prompt": system_prompt,
            "skills": ["/skills/"],
        }
        subagents = app_config.get("sub_agents")
        if isinstance(subagents, list) and subagents:
            agent_kwargs["subagents"] = subagents
        agent = create_deep_agent(**agent_kwargs)
        payload: dict[str, Any] = {
            "messages": [message.model_dump() for message in req.messages],
        }
        if skill_files:
            payload["files"] = skill_files
        observation_metadata = {
            "app_id": str(app.id),
            "app_name": app.name,
            "app_type": app.app_type,
            "request_type": request_type,
        }
        return _Prepared(
            app=app,
            runtime_config=runtime_config,
            app_config=app_config,
            agent=agent,
            payload=payload,
            observation_metadata=observation_metadata,
        )

    def _log_stream_finally(
        self,
        prep: _Prepared,
        req_ctx: RequestContext,
        request_type: str,
        *,
        success: bool,
        full_content: str,
        latency_ms: int,
        trace_id: str | None,
        error_message: str | None,
        token_usage: dict[str, int | None],
    ) -> None:
        """流式执行结束后用独立 session 写日志，吞掉日志写入异常不影响流。"""
        from app.db.session import SessionLocal

        log_db = SessionLocal()
        try:
            response_payload = (
                {
                    "app_id": str(prep.app.id),
                    "app_type": prep.app.app_type,
                    "model": prep.runtime_config.model,
                    "result": {"content": full_content},
                    "latency_ms": latency_ms,
                }
                if success
                else None
            )
            self._log_service.log_execution(
                log_db,
                app=prep.app,
                runtime_config=prep.runtime_config,
                req_ctx=req_ctx,
                request_type=request_type,
                request_payload=prep.payload,
                response_payload=response_payload,
                success=success,
                latency_ms=latency_ms,
                trace_id=trace_id,
                error_message=error_message,
                token_usage=token_usage,
            )
        except Exception:
            logger.exception("failed to write stream log for app %s", prep.app.id)
        finally:
            log_db.close()

    def _build_skill_files(self, db: Session, app_id: int) -> dict[str, Any]:
        """把绑定到应用的 enabled 技能合成虚拟 SKILL.md，供 DeepAgents SkillsMiddleware 读取。

        每条返回值形如 {"/skills/<name>/SKILL.md": FileData}，可直接合并进 invoke/astream_events
        的 payload 的 files 字段。StateBackend 会从中读出技能目录与内容。
        """
        files: dict[str, Any] = {}
        bindings = db.scalars(select(TbAppSkill).where(TbAppSkill.app_id == app_id)).all()
        for binding in bindings:
            skill = db.get(TbSkill, binding.skill_id)
            if not skill or skill.skill_status != "enabled":
                continue
            description = skill.description or skill.name
            if len(description) > 1024:
                description = description[:1024]
            content = (
                "---\n"
                f"name: {skill.name}\n"
                f"description: {description}\n"
                "---\n\n"
                f"{skill.instruction}"
            )
            files[f"/skills/{skill.name}/SKILL.md"] = create_file_data(content)
        return files

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
