from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx
from deepagents import create_deep_agent
from langfuse import propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.errors import GraphInterrupt
from langgraph.types import Command, Interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app.app_runtime import AppRuntime
from app.app.backend_factory import BackendFactory
from app.app.checkpointer_factory import CheckpointerFactory, get_checkpointer_factory
from app.app.langchain_util import LangChainUtil
from app.app.memory_middleware import MemoryInjectionMiddleware
from app.app.memory_tools import build_memory_tools
from app.app.policy_middleware import PolicyMiddleware
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
    SSE_EVENT_TODO_UPDATE,
    SSE_EVENT_TOKEN,
    SSE_EVENT_TOOL_CALL_END,
    SSE_EVENT_TOOL_CALL_START,
    SSE_EVENT_TOOL_HITL_REQUIRED,
    format_sse_done,
    format_sse_event,
)
from app.db.schema import TbApp, TbAppSkill, TbAppTool, TbMcpServer, TbSkill, TbSkillTool, TbTool
from app.db.session import SessionLocal
from app.model.open_model import AgentRunRequest
from app.service.app_log_service import ZERO_USAGE, AppLogService
from app.service.memory_service import MemoryService
from app.service.policy_service import PolicyAuditWriter
from app.service.skill_service import RESERVED_SKILL_NAMES

logger = logging.getLogger(__name__)


def _thread_id_to_int(thread_id: str | None) -> int | None:
    """Snowflake thread_id → int；UUID 形式（测试流）→ None。"""
    if not thread_id:
        return None
    try:
        return int(thread_id)
    except (TypeError, ValueError):
        return None


def _is_subagent_hitl_interrupt(error: Any) -> bool:
    """子代理内部的 PolicyMiddleware 触发了 interrupt()，GraphInterrupt 向上冒泡。

    区分普通工具报错：args[0] 是 Interrupt 元组且首个 Interrupt 的 value.type 为
    tool_hitl_required。
    """
    if not isinstance(error, GraphInterrupt) or not error.args:
        return False
    interrupts = error.args[0]
    if not isinstance(interrupts, tuple):
        return False
    return any(
        isinstance(i, Interrupt)
        and isinstance(getattr(i, "value", None), dict)
        and i.value.get("type") == "tool_hitl_required"
        for i in interrupts
    )


def _serialize_todos(todos: Any) -> list[dict[str, str]]:
    """把 LangChain Todo TypedDict 列表归一化成纯 JSON。

    输入可能是 list[TypedDict]、list[dict]、None；输出统一为 list[dict] 含
    content + status 两个 string 字段，方便 SSE 序列化和前端渲染。
    """
    out: list[dict[str, str]] = []
    if not isinstance(todos, list):
        return out
    for t in todos:
        if not isinstance(t, dict):
            continue
        out.append(
            {
                "content": str(t.get("content") or ""),
                "status": str(t.get("status") or "pending"),
            }
        )
    return out


def _describe_exception(exc: BaseException) -> str:
    """给 ServiceError message 取一个有信息量的描述。

    Python 3.11+ 在 asyncio/anyio TaskGroup 里抛出的是 BaseExceptionGroup，
    默认 str() 只会打印 "unhandled errors in a TaskGroup (1 sub-exception)"，
    没有任何根因。这里递归展开 exceptions 找到第一条非 group 异常，拼出
    "ClassName: message" 形式，方便日志和面向用户的错误文案。
    """
    current: BaseException = exc
    while isinstance(current, BaseExceptionGroup) and current.exceptions:
        current = current.exceptions[0]
    return f"{type(current).__name__}: {current}"


@dataclass
class _Prepared:
    """run / stream 共用的一次准备结果。"""

    app: TbApp
    runtime_config: Any
    app_config: dict[str, Any]
    agent: Any
    payload: dict[str, Any]
    observation_metadata: dict[str, Any]
    thread_id: str | None
    use_checkpoint: bool
    degraded: bool

    def invoke_config(self, handler: Any) -> dict[str, Any]:
        """组装 ainvoke / astream_events 的 config。

        启用 checkpoint 时必须带 configurable.thread_id，LangGraph 据此查找/写入快照。
        """
        config: dict[str, Any] = {"callbacks": [handler]}
        if self.use_checkpoint and self.thread_id:
            config["configurable"] = {"thread_id": self.thread_id}
        return config


class AgentApp:
    """利用 DeepAgents + LiteLLM + 技能 + 工具运行 Agent 应用。"""

    def __init__(
        self,
        app_runtime: AppRuntime | None = None,
        langchain_util: LangChainUtil | None = None,
        log_service: AppLogService | None = None,
        backend_factory: BackendFactory | None = None,
        checkpointer_factory: CheckpointerFactory | None = None,
    ) -> None:
        self._app_runtime = app_runtime or AppRuntime()
        self._langchain_util = langchain_util or LangChainUtil()
        self._log_service = log_service or AppLogService(
            SnowflakeGenerator(settings.snowflake_worker_id)
        )
        self._backend_factory = backend_factory or BackendFactory()
        self._checkpointer_factory = checkpointer_factory or get_checkpointer_factory()

    async def run(
        self,
        db: Session,
        req: AgentRunRequest,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> dict[str, Any]:
        prep = self._prepare(db, req, req_ctx, request_type)
        handler = CallbackHandler()
        started_at = time.perf_counter()
        try:
            with propagate_attributes(metadata=prep.observation_metadata):
                result = await prep.agent.ainvoke(prep.payload, config=prep.invoke_config(handler))
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
            logger.exception("agent app %s run failed", prep.app.id)
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
                error_message=_describe_exception(exc),
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
        prep = self._prepare(db, req, req_ctx, request_type)
        # 流前 DB 操作完成，关闭 session（日志写入走独立 session）
        db.close()
        async for chunk in self._stream_with_input(
            prep, prep.payload, req_ctx, request_type=request_type, emit_initial_todos=True
        ):
            yield chunk

    async def resume_stream(
        self,
        db: Session,
        req: AgentRunRequest,
        req_ctx: RequestContext,
        *,
        hitl_response: dict[str, Any],
        request_type: str = "chat",
    ) -> AsyncGenerator[str, None]:
        """HITL 用户响应到达后续跑被 interrupt() 暂停的 agent。

        与 stream 共享 _prepare（同一会话同一线程，agent 工具与中间件配置必须保持一致），
        差别仅在 astream_events 的输入：用 Command(resume=...) 把响应注入到 interrupt() 调用站点。
        """
        prep = self._prepare(db, req, req_ctx, request_type)
        db.close()
        async for chunk in self._stream_with_input(
            prep,
            Command(resume=hitl_response),
            req_ctx,
            request_type=request_type,
            emit_initial_todos=False,
        ):
            yield chunk

    async def _stream_with_input(
        self,
        prep: _Prepared,
        agent_input: Any,
        req_ctx: RequestContext,
        *,
        request_type: str,
        emit_initial_todos: bool,
    ) -> AsyncGenerator[str, None]:
        """stream / resume_stream 共用的事件循环；agent_input 决定是新发起还是 resume。"""
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

        metadata_event: dict[str, Any] = {
            "app_id": str(prep.app.id),
            "app_type": prep.app.app_type,
            "model": prep.runtime_config.model,
        }
        if prep.use_checkpoint and prep.thread_id:
            metadata_event["thread_id"] = prep.thread_id
        if prep.degraded:
            metadata_event["degraded"] = True
        yield format_sse_event(SSE_EVENT_METADATA, metadata_event)

        # 初始 todos 快照：用户重新打开会话发消息时，先把 checkpoint 里已有的
        # todos 推一次，避免 panel 留白等下一次 write_todos。resume 路径不需要重发。
        if emit_initial_todos and prep.use_checkpoint and prep.thread_id:
            try:
                saver = self._checkpointer_factory.get()
                ckpt = await saver.aget_tuple({"configurable": {"thread_id": prep.thread_id}})
                if ckpt is not None:
                    existing = ckpt.checkpoint.get("channel_values", {}).get("todos")
                    serialized = _serialize_todos(existing)
                    if serialized:
                        yield format_sse_event(SSE_EVENT_TODO_UPDATE, {"todos": serialized})
            except Exception:
                logger.warning(
                    "failed to load initial todos snapshot for thread %s",
                    prep.thread_id,
                    exc_info=True,
                )

        # 卡顿诊断：跟踪 LLM 调用 / 工具调用的起止 timing。
        # 出问题时 tail log，"X_start 没有对应 X_end"那条就是卡的位置。
        chat_model_started_at: float | None = None
        tool_call_starts: dict[str, tuple[str, float]] = {}  # run_id -> (name, t0)

        try:
            with propagate_attributes(metadata=prep.observation_metadata):
                async for event in prep.agent.astream_events(
                    agent_input, version="v2", config=prep.invoke_config(handler)
                ):
                    kind = event.get("event")
                    data = event.get("data") or {}

                    if kind == "on_chat_model_start":
                        chat_model_started_at = time.perf_counter()
                        logger.info("[stream] thread=%s chat_model_start", prep.thread_id)
                    elif kind == "on_chat_model_end":
                        if chat_model_started_at is not None:
                            elapsed = time.perf_counter() - chat_model_started_at
                            logger.info(
                                "[stream] thread=%s chat_model_end elapsed=%.2fs",
                                prep.thread_id,
                                elapsed,
                            )
                            chat_model_started_at = None

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
                        run_id = event.get("run_id", "")
                        tool_name = event.get("name", "")
                        tool_call_starts[run_id] = (tool_name, time.perf_counter())
                        logger.info(
                            "[stream] thread=%s tool_start name=%s run_id=%s",
                            prep.thread_id,
                            tool_name,
                            run_id,
                        )
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_START,
                            {
                                "tool_call_id": run_id,
                                "name": tool_name,
                                "arguments": data.get("input", {}),
                            },
                        )

                    elif kind == "on_tool_end":
                        run_id = event.get("run_id", "")
                        tool_name = event.get("name", "")
                        if run_id in tool_call_starts:
                            _, t0 = tool_call_starts.pop(run_id)
                            elapsed = time.perf_counter() - t0
                            logger.info(
                                "[stream] thread=%s tool_end name=%s elapsed=%.2fs",
                                prep.thread_id,
                                tool_name,
                                elapsed,
                            )
                        output = data.get("output", "")
                        if hasattr(output, "content"):
                            output = output.content
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_END,
                            {
                                "tool_call_id": run_id,
                                "name": tool_name,
                                "result": str(output) if output else "",
                                "status": "success",
                            },
                        )
                        # write_todos 工具的入参就是新的 todos 全量快照，
                        # 借这个事件推一条 todo_update 给前端，不用额外读 state。
                        if tool_name == "write_todos":
                            tool_input = data.get("input") or {}
                            new_todos = (
                                tool_input.get("todos") if isinstance(tool_input, dict) else None
                            )
                            yield format_sse_event(
                                SSE_EVENT_TODO_UPDATE,
                                {"todos": _serialize_todos(new_todos)},
                            )

                    elif kind == "on_tool_error":
                        run_id = event.get("run_id", "")
                        tool_name = event.get("name", "")
                        error = data.get("error")
                        subagent_hitl = _is_subagent_hitl_interrupt(error)
                        if run_id in tool_call_starts:
                            _, t0 = tool_call_starts.pop(run_id)
                            elapsed = time.perf_counter() - t0
                            if subagent_hitl:
                                logger.info(
                                    "[stream] thread=%s tool_end name=%s elapsed=%.2fs (subagent hitl)",
                                    prep.thread_id,
                                    tool_name,
                                    elapsed,
                                )
                            else:
                                logger.warning(
                                    "[stream] thread=%s tool_error name=%s elapsed=%.2fs error=%s",
                                    prep.thread_id,
                                    tool_name,
                                    elapsed,
                                    error,
                                )
                        yield format_sse_event(
                            SSE_EVENT_TOOL_CALL_END,
                            {
                                "tool_call_id": run_id,
                                "name": tool_name,
                                "result": "" if subagent_hitl else str(error or ""),
                                "status": "subagent_hitl" if subagent_hitl else "error",
                            },
                        )

            if usage_found:
                token_usage = dict(accumulated)

            # astream_events 自然结束后，若 PolicyMiddleware 调用过 interrupt()，
            # LangGraph 会把 pending interrupt 写在 state.tasks[].interrupts 上。
            # 把每条匹配 type=tool_hitl_required 的载荷推 SSE，并写一条 hitl_required 审计。
            for hitl_payload in await self._collect_pending_hitl(prep):
                yield format_sse_event(SSE_EVENT_TOOL_HITL_REQUIRED, hitl_payload)
                self._audit_hitl_required(hitl_payload, prep, req_ctx)

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
            error_message = _describe_exception(exc)
            trace_id = handler.last_trace_id
            logger.exception("agent app %s stream failed", prep.app.id)
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

    def _prepare(
        self,
        db: Session,
        req: AgentRunRequest,
        req_ctx: RequestContext,
        request_type: str,
    ) -> _Prepared:
        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "agent":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not agent type")

        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        app_config = self._app_runtime.get_app_config(db, req.app_id)
        model = self._langchain_util.build_chat_model(runtime_config)
        # 主 agent 只挂应用直接绑定的工具；技能工具随技能 subagent 懒加载，
        # 避免所有技能的工具 schema 从第一轮就挤占主 agent 上下文。
        tools, tool_metadata = self._build_app_tools_with_metadata(db, req.app_id)
        # 记忆工具（remember / forget / list_my_memories）：随主 agent 走，
        # 不进 PolicyMiddleware 治理（中间件按 name 找不到 tool_id 会透传）。
        thread_id_int = _thread_id_to_int(req.thread_id)
        memory_service = MemoryService(SnowflakeGenerator(settings.snowflake_worker_id))
        memory_tools = build_memory_tools(
            user_id=req_ctx.user_id,
            app_id=app.id,
            conversation_id=thread_id_int,
            service=memory_service,
            langchain_util=self._langchain_util,
        )
        logger.info(
            "[memory] tools wired count=%d user_id=%s app_id=%s",
            len(memory_tools),
            req_ctx.user_id,
            app.id,
        )
        if memory_tools:
            tools = list(tools) + memory_tools
        system_prompt = (app_config.get("system_prompt") or "").strip()
        backend = self._backend_factory.create(app_config)

        skill_subagents = self._build_skill_subagents(
            db, app.id, model=model, req=req, req_ctx=req_ctx
        )
        extra_subagents = app_config.get("sub_agents")
        all_subagents: list[Any] = list(skill_subagents)
        if isinstance(extra_subagents, list):
            all_subagents.extend(extra_subagents)

        # 长会话对所有 agent app 默认开启；调用方仍需 use_checkpoint=True 显式确认
        # （直 API 一次性调用不需要 checkpoint）。thread_id 缺失时仍降级，避免运行态污染。
        use_checkpoint = bool(req.use_checkpoint and req.thread_id)
        agent_kwargs: dict[str, Any] = {
            "model": model,
            "tools": tools,
            "system_prompt": system_prompt,
            "backend": backend,
        }
        if all_subagents:
            agent_kwargs["subagents"] = all_subagents
        if use_checkpoint:
            agent_kwargs["checkpointer"] = self._checkpointer_factory.get()

        # 主 agent 中间件链：
        #   - PolicyMiddleware：治理 user-bound 工具的调用（subagent 工具治理由
        #     _build_skill_subagents 单独挂；framework 内置工具透传）。
        #   - MemoryInjectionMiddleware：每次模型调用前把当前 user + app 维度的长期记忆
        #     注入 system prompt 末尾；subagent 第一版不注入，避免污染技能行为。
        main_middlewares: list[Any] = []
        if tool_metadata["name_to_id"]:
            main_middlewares.append(
                self._make_policy_middleware(
                    tool_metadata=tool_metadata,
                    req=req,
                    req_ctx=req_ctx,
                    app_id=app.id,
                )
            )
        main_middlewares.append(
            MemoryInjectionMiddleware(
                user_id=req_ctx.user_id,
                app_id=app.id,
                service=memory_service,
            )
        )
        agent_kwargs["middleware"] = main_middlewares
        agent = create_deep_agent(**agent_kwargs)
        payload: dict[str, Any] = {
            "messages": [message.model_dump() for message in req.messages],
        }
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
            thread_id=req.thread_id,
            use_checkpoint=use_checkpoint,
            degraded=req.degraded,
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

    def _build_app_tools(self, db: Session, app_id: int) -> list[Any]:
        tools, _ = self._build_app_tools_with_metadata(db, app_id)
        return tools

    def _build_app_tools_with_metadata(
        self, db: Session, app_id: int
    ) -> tuple[list[Any], dict[str, Any]]:
        """收集应用直接绑定的工具，同时返回 PolicyMiddleware 需要的元数据。

        返回 (tools, {"name_to_id": ..., "id_to_risk": ...})。
        技能工具不在这里——它们走 subagent 各自加载。
        """
        tool_ids: list[int] = []
        seen: set[int] = set()
        for binding in db.scalars(select(TbAppTool).where(TbAppTool.app_id == app_id)).all():
            if binding.tool_id not in seen:
                seen.add(binding.tool_id)
                tool_ids.append(binding.tool_id)
        return self._load_tools_with_metadata(db, tool_ids)

    def _build_skill_subagents(
        self,
        db: Session,
        app_id: int,
        *,
        model: Any,
        req: AgentRunRequest,
        req_ctx: RequestContext,
    ) -> list[dict[str, Any]]:
        """每个 enabled 绑定技能渲染成一个 SubAgent 规格。

        - name/description 来自 TbSkill，主 agent 通过 task 工具按名字委派
        - system_prompt 用 skill.instruction（渐进披露：主 agent 看不到，委派时才进入上下文）
        - tools 只含该技能通过 TbSkillTool 声明的工具，天然做到工具隔离
        - middleware 挂当前技能工具子集对应的 PolicyMiddleware，覆盖技能内的工具治理
        """
        subagents: list[dict[str, Any]] = []
        bindings = db.scalars(select(TbAppSkill).where(TbAppSkill.app_id == app_id)).all()
        for binding in bindings:
            skill = db.get(TbSkill, binding.skill_id)
            if not skill or skill.skill_status != "enabled":
                continue
            # 和 DeepAgents 内置 general-purpose 同名会顶替框架默认子代理，
            # service 层已在写入时拦截，这里做一次兜底防历史脏数据。
            if skill.name.strip().lower() in RESERVED_SKILL_NAMES:
                logger.warning(
                    "skipping skill %s (id=%s): name collides with reserved subagent",
                    skill.name,
                    skill.id,
                )
                continue
            tool_rows = db.scalars(
                select(TbSkillTool).where(TbSkillTool.skill_id == skill.id)
            ).all()
            # 按 tool_id 去重，保持声明顺序
            tool_ids: list[int] = []
            seen: set[int] = set()
            for row in tool_rows:
                if row.tool_id not in seen:
                    seen.add(row.tool_id)
                    tool_ids.append(row.tool_id)
            skill_tools, skill_tool_metadata = self._load_tools_with_metadata(db, tool_ids)
            description = (skill.description or skill.name).strip()
            if len(description) > 1024:
                description = description[:1024]
            spec: dict[str, Any] = {
                "name": skill.name,
                "description": description,
                "system_prompt": skill.instruction,
                "tools": skill_tools,
                "model": model,
            }
            if skill_tool_metadata["name_to_id"]:
                spec["middleware"] = [
                    self._make_policy_middleware(
                        tool_metadata=skill_tool_metadata,
                        req=req,
                        req_ctx=req_ctx,
                        app_id=app_id,
                    )
                ]
            subagents.append(spec)
        return subagents

    def _load_tools_by_ids(self, db: Session, tool_ids: list[int]) -> list[Any]:
        tools, _ = self._load_tools_with_metadata(db, tool_ids)
        return tools

    def _load_tools_with_metadata(
        self, db: Session, tool_ids: list[int]
    ) -> tuple[list[Any], dict[str, Any]]:
        """加载工具同时收集 PolicyMiddleware 需要的 name→id / id→risk / id→hitl_timeout 映射。"""
        tools: list[Any] = []
        name_to_id: dict[str, int] = {}
        id_to_risk: dict[int, str] = {}
        id_to_timeout: dict[int, int | None] = {}
        for tool_id in tool_ids:
            tool = db.get(TbTool, tool_id)
            if not tool or tool.tool_status != "enabled":
                continue
            tools.append(self._build_tool(db, tool))
            if tool.tool_name not in name_to_id:
                name_to_id[tool.tool_name] = tool.id
            id_to_risk[tool.id] = (tool.risk_level or "low").lower()
            id_to_timeout[tool.id] = tool.hitl_timeout_seconds
        return (
            tools,
            {
                "name_to_id": name_to_id,
                "id_to_risk": id_to_risk,
                "id_to_hitl_timeout": id_to_timeout,
            },
        )

    async def _collect_pending_hitl(self, prep: _Prepared) -> list[dict[str, Any]]:
        """从 LangGraph state.tasks 提取 PolicyMiddleware 写下的 tool_hitl_required 载荷。

        没启用 checkpoint / 取 state 失败 / 没 interrupt 都返回空列表。
        """
        if not (prep.use_checkpoint and prep.thread_id):
            return []
        config = {"configurable": {"thread_id": prep.thread_id}}
        try:
            state = await prep.agent.aget_state(config)
        except Exception:
            logger.exception("failed to read interrupt state for thread %s", prep.thread_id)
            return []
        payloads: list[dict[str, Any]] = []
        for task in getattr(state, "tasks", ()) or ():
            for itr in getattr(task, "interrupts", ()) or ():
                value = getattr(itr, "value", None)
                if isinstance(value, dict) and value.get("type") == "tool_hitl_required":
                    payloads.append(value)
        return payloads

    def _audit_hitl_required(
        self,
        payload: dict[str, Any],
        prep: _Prepared,
        req_ctx: RequestContext,
    ) -> None:
        """interrupt 命中后写一行 hitl_required 审计；与中间件的 response 审计配对。"""
        writer = PolicyAuditWriter(SnowflakeGenerator(settings.snowflake_worker_id))
        tool_id_raw = payload.get("tool_id")
        tool_id_int: int | None = None
        if tool_id_raw is not None:
            try:
                tool_id_int = int(tool_id_raw)
            except (TypeError, ValueError):
                tool_id_int = None
        matched_rule_raw = payload.get("matched_rule_id")
        matched_rule_int: int | None = None
        if matched_rule_raw is not None:
            try:
                matched_rule_int = int(matched_rule_raw)
            except (TypeError, ValueError):
                matched_rule_int = None
        conv_id = _thread_id_to_int(prep.thread_id)
        params = payload.get("parameters")
        if not isinstance(params, dict):
            params = {}
        db = SessionLocal()
        try:
            writer.write(
                db,
                event_type="hitl_required",
                tool_id=tool_id_int,
                conversation_id=conv_id,
                run_id=prep.thread_id,
                user_id=req_ctx.user_id,
                app_id=prep.app.id,
                parameters=params,
                decision_reason=payload.get("reason"),
                matched_rule_id=matched_rule_int,
            )
        except Exception:
            logger.exception(
                "hitl_required audit write failed: thread=%s tool_id=%s",
                prep.thread_id,
                tool_id_int,
            )
        finally:
            db.close()

    def _make_policy_middleware(
        self,
        *,
        tool_metadata: dict[str, Any],
        req: AgentRunRequest,
        req_ctx: RequestContext,
        app_id: int,
    ) -> PolicyMiddleware:
        """每次 agent 执行新建一份 PolicyMiddleware，绑定本次运行的上下文。

        主 agent 与每个技能 subagent 各自持有一份；tool_metadata 范围按调用方传入的工具子集。
        """
        return PolicyMiddleware(
            tool_id_by_name=tool_metadata["name_to_id"],
            risk_level_by_tool_id=tool_metadata["id_to_risk"],
            audit_writer=PolicyAuditWriter(SnowflakeGenerator(settings.snowflake_worker_id)),
            hitl_timeout_by_tool_id=tool_metadata.get("id_to_hitl_timeout") or {},
            default_hitl_timeout_seconds=settings.hitl_timeout_seconds,
            run_id=req.thread_id,
            conversation_id=_thread_id_to_int(req.thread_id),
            user_id=req_ctx.user_id,
            app_id=app_id,
            # user_role 暂未统一在 RequestContext 上挂载，留空；后续合规 PR 再补。
            user_role=None,
        )

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

        timeout_seconds = settings.mcp_tool_timeout_seconds

        def call_mcp_tool(**kwargs: Any) -> str:
            t0 = time.perf_counter()
            logger.info("mcp tool %s call start (timeout=%.0fs)", remote_tool_name, timeout_seconds)
            try:
                result = mcp_call_tool(
                    transport=transport,
                    url=endpoint_url,
                    tool_name=remote_tool_name,
                    arguments=kwargs,
                    headers=headers,
                    timeout=timeout_seconds,
                )
                logger.info(
                    "mcp tool %s call done elapsed=%.2fs",
                    remote_tool_name,
                    time.perf_counter() - t0,
                )
                return result
            except ServiceError:
                logger.exception(
                    "mcp tool %s raised ServiceError after %.2fs",
                    remote_tool_name,
                    time.perf_counter() - t0,
                )
                raise
            except Exception as exc:
                logger.exception(
                    "mcp tool %s invocation failed after %.2fs",
                    remote_tool_name,
                    time.perf_counter() - t0,
                )
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    f"mcp tool {remote_tool_name} invocation failed: "
                    f"{_describe_exception(exc)}",
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

        tool_name = tool.tool_name

        def call_api_tool(**kwargs: Any) -> str:
            t0 = time.perf_counter()
            logger.info("api tool %s call start", tool_name)
            try:
                final_url = self._render_template(url, kwargs)
                if not final_url:
                    raise ServiceError(ErrorCode.BAD_REQUEST, f"tool {tool_name} api url missing")

                headers: dict[str, str] = {}
                if isinstance(headers_config, list):
                    for item in headers_config:
                        if not isinstance(item, dict):
                            continue
                        key = item.get("key")
                        if not key:
                            continue
                        headers[str(key)] = self._render_template(
                            str(item.get("value") or ""), kwargs
                        )

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
                        f"tool {tool_name} request failed: "
                        f"status={response.status_code}, body={response.text}"
                    )
                    raise ServiceError(
                        ErrorCode.INTERNAL_ERROR,
                        error_detail,
                    )
                logger.info(
                    "api tool %s call done elapsed=%.2fs",
                    tool_name,
                    time.perf_counter() - t0,
                )
                return response.text
            except ServiceError:
                logger.exception(
                    "api tool %s raised ServiceError after %.2fs",
                    tool_name,
                    time.perf_counter() - t0,
                )
                raise
            except Exception as exc:
                logger.exception(
                    "api tool %s invocation failed after %.2fs",
                    tool_name,
                    time.perf_counter() - t0,
                )
                raise ServiceError(
                    ErrorCode.INTERNAL_ERROR,
                    f"api tool {tool_name} invocation failed: {_describe_exception(exc)}",
                ) from exc

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
