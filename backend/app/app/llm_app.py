from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from langfuse import propagate_attributes
from langfuse.langchain import CallbackHandler
from sqlalchemy.orm import Session

from app.app.app_runtime import AppRuntime
from app.app.langchain_util import LangChainUtil
from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.core.sse import (
    SSE_EVENT_DONE,
    SSE_EVENT_ERROR,
    SSE_EVENT_MESSAGE_COMPLETE,
    SSE_EVENT_METADATA,
    SSE_EVENT_TOKEN,
    format_sse_done,
    format_sse_event,
)
from app.model.open_model import LlmAppRunReq, ModelGatewayChatMessage
from app.service.app_log_service import AppLogService

logger = logging.getLogger(__name__)


class LlmApp:
    """利用 LangChain Agents + LiteLLM 运行 LLM 应用。"""

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
        req: LlmAppRunReq,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> dict[str, Any]:
        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "llm":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not llm type")

        app_config = self._app_runtime.get_app_config(db, req.app_id)
        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        model = self._langchain_util.build_chat_model(runtime_config)
        agent = self._langchain_util.create_agent(
            model=model,
            tools=[],
            system_prompt=self._build_system_prompt(app_config),
        )

        final_messages = req.messages or self._build_messages_from_inputs(app_config, req.inputs)
        payload = {"messages": [message.model_dump() for message in final_messages]}
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
        req: LlmAppRunReq,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> AsyncGenerator[str, None]:
        """流式执行 LLM 应用，通过 SSE 事件逐 token 输出。

        db 会在流开始前关闭；日志写入在 finally 块中使用独立 session。
        """
        from app.db.session import SessionLocal

        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "llm":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not llm type")

        app_config = self._app_runtime.get_app_config(db, req.app_id)
        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        model = self._langchain_util.build_chat_model(runtime_config)
        agent = self._langchain_util.create_agent(
            model=model,
            tools=[],
            system_prompt=self._build_system_prompt(app_config),
        )

        final_messages = req.messages or self._build_messages_from_inputs(app_config, req.inputs)
        payload = {"messages": [message.model_dump() for message in final_messages]}
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
                        # 提取 usage（通常在最后一个 chunk 上）
                        usage = getattr(chunk, "usage_metadata", None)
                        if isinstance(usage, dict) and usage.get("total_tokens"):
                            token_usage = {
                                "total_tokens": usage.get("total_tokens"),
                                "input_tokens": usage.get("input_tokens"),
                                "output_tokens": usage.get("output_tokens"),
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

    def _build_system_prompt(self, app_config: dict[str, Any]) -> str | None:
        value = app_config.get("system_prompt")
        return value if isinstance(value, str) and value.strip() else None

    def _build_messages_from_inputs(
        self, app_config: dict[str, Any], inputs: dict[str, Any]
    ) -> list[ModelGatewayChatMessage]:
        user_prompt = app_config.get("user_prompt")
        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ServiceError(ErrorCode.BAD_REQUEST, "llm app user_prompt not configured")
        rendered = user_prompt
        for key, value in inputs.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return [ModelGatewayChatMessage(role="user", content=rendered)]
