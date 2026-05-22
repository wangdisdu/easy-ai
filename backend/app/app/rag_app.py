"""RAG 应用运行时(2-stage + 多轮支持)。

链路:
    retrieve → [可选 summary 精炼] → 拼上下文 + 历史 → 调主 LLM → 返回

app_config(``tb_app.app_config`` JSON)期望的键:
- ``kb_ids: list[str]`` 必填,绑定的 KB id 列表(easy-ai 雪花)
- ``top_n / top_k: int`` 默认 5
- ``similarity_threshold: float`` 默认 0.2
- ``vector_weight: float`` 默认 0.3
- ``enable_rerank: bool`` / ``rerank_model: str``
- ``enable_summary: bool`` 启用 2-stage RAG;开启时下列三字段生效
- ``summary_model: str`` summary 阶段使用的模型名(在 LLM 管理已注册)
- ``summary_temperature: float`` 默认 0.3
- ``summary_prompt: str`` summary system prompt,占位符 ``{{chunks}}``
- ``system_prompt: str | None`` 可选,主 LLM 阶段 prepend
- ``rag_prompt_template: str | None`` 主 LLM 阶段 system prompt 模板,
  占位符 ``{{context}}`` / ``{{question}}``

请求支持:
- ``RagRunRequest.query`` 单轮
- ``RagRunRequest.messages`` 多轮(自动取最后一条 user 消息为 query)

返回字段:
- ``result.content``: LLM 回答正文
- ``references: list[ref_card]``:命中 chunks 的引用卡片
- ``retrieved_count`` / ``retrieve_latency_ms`` / ``summary_latency_ms``
  / ``llm_latency_ms`` / ``latency_ms`` / ``summary_used: bool``
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.orm import Session

from app.app.app_runtime import AppRuntime
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.sse import (
    ExtReferences,
    MessageStreamState,
    RunError,
    RunFinished,
    RunStarted,
    StreamEvent,
    new_run_id,
)
from app.db.session import SessionLocal
from app.model.open_model import (
    LiteLLMChatRequest,
    ModelGatewayChatMessage,
    RagRunRequest,
)
from app.model.rag_dataset_model import RetrieveHit, RetrieveReq
from app.service.kb_retrieve_service import KbRetrieveService
from app.service.model_gateway_service import ModelGatewayService

logger = logging.getLogger(__name__)


DEFAULT_RAG_PROMPT_TEMPLATE = """\
You are a helpful assistant. Answer the user's question based ONLY on the provided context. \
If the context doesn't contain enough information, say so honestly instead of guessing.

When citing a specific document, use the format `[[doc:REF]]` where REF is the ref code shown \
next to each context chunk.

Context:
{{context}}\
"""

DEFAULT_SUMMARY_PROMPT = """\
You are a context distiller for a downstream answering model. Read the chunks below and \
output ONLY the facts/passages relevant to the user's question, preserving the `[[doc:REF]]` \
ref codes so the downstream model can still cite. Be terse; do NOT answer the question yourself.

Chunks:
{{chunks}}\
"""

# 上下文里每条 chunk 文本截断阈值,避免单条过长爆 token
_CHUNK_TRUNCATE_CHARS = 1500


class RagApp:
    """RAG 运行时:检索 KB → (可选)总结 → 调主 LLM → 附引用列表返回。"""

    def __init__(
        self,
        app_runtime: AppRuntime | None = None,
        model_gateway_service: ModelGatewayService | None = None,
        kb_retrieve_service: KbRetrieveService | None = None,
    ) -> None:
        self._app_runtime = app_runtime or AppRuntime()
        self._model_gateway_service = model_gateway_service or ModelGatewayService()
        self._kb_retrieve_service = kb_retrieve_service or KbRetrieveService()

    def run(
        self,
        db: Session,
        req: RagRunRequest,
        req_ctx: RequestContext,
        *,
        request_type: str = "api",
    ) -> dict[str, Any]:
        app = self._app_runtime.get_app(db, req.app_id)
        if app.app_type != "rag":
            raise ServiceError(ErrorCode.BAD_REQUEST, "app is not rag type")
        app_config = self._app_runtime.get_app_config(db, req.app_id)
        kb_ids = self._extract_kb_ids(app_config)
        if not kb_ids:
            raise ServiceError(
                ErrorCode.BAD_REQUEST, "rag app must bind at least one knowledge base"
            )

        # 多轮:从 messages 末尾抽 user query;单轮:直接用 req.query
        query, history = self._resolve_query_and_history(req)
        if not query:
            raise ServiceError(ErrorCode.BAD_REQUEST, "rag run requires a user query")

        started_at = time.perf_counter()

        # 1. retrieve
        retrieve_req = self._build_retrieve_req(app_config, kb_ids, query)
        retrieved = self._kb_retrieve_service.retrieve(db, retrieve_req, req_ctx)
        retrieve_latency_ms = int((time.perf_counter() - started_at) * 1000)

        # 2. (可选)summary 阶段:把多 chunk 精炼为 condensed context
        summary_used = False
        summary_latency_ms = 0
        if app_config.get("enable_summary") and retrieved.hits:
            sum_started = time.perf_counter()
            condensed = self._run_summary_stage(
                db, app_config, retrieved.hits, query, req_ctx, request_type
            )
            summary_latency_ms = int((time.perf_counter() - sum_started) * 1000)
            if condensed:
                context_block = condensed
                summary_used = True
            else:
                # summary 失败兜底走原始 chunks
                context_block = self._format_context(retrieved.hits)
        else:
            context_block = (
                self._format_context(retrieved.hits)
                if retrieved.hits
                else "(no relevant documents found)"
            )

        # 3. 渲染主阶段 system prompt
        system_prompt = self._render_system_prompt(app_config, context_block, query)

        # 4. 调主 LLM gateway
        runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
        chat_messages: list[ModelGatewayChatMessage] = [
            ModelGatewayChatMessage(role="system", content=system_prompt)
        ]
        if history:
            chat_messages.extend(history)
        chat_messages.append(ModelGatewayChatMessage(role="user", content=query))

        gw_started = time.perf_counter()
        gw_resp = self._model_gateway_service.chat_completion(
            db=db,
            req=LiteLLMChatRequest(messages=chat_messages, runtime_config=runtime_config),
            req_ctx=req_ctx,
            app_id=req.app_id,
            app_type="rag",
            request_type=request_type,
        )
        llm_latency_ms = int((time.perf_counter() - gw_started) * 1000)
        total_latency_ms = int((time.perf_counter() - started_at) * 1000)

        # 5. 提取回答 + references
        content = self._extract_content(gw_resp.data or gw_resp.raw_response)
        references = [self._hit_to_reference(hit) for hit in retrieved.hits]

        logger.info(
            "[rag] action=run app_id=%s kb_ids=%s top_k=%d hits=%d "
            "summary=%s retrieve_ms=%d summary_ms=%d llm_ms=%d total_ms=%d",
            req.app_id,
            kb_ids,
            retrieve_req.top_k,
            len(retrieved.hits),
            summary_used,
            retrieve_latency_ms,
            summary_latency_ms,
            llm_latency_ms,
            total_latency_ms,
        )

        return {
            "app_id": str(req.app_id),
            "app_type": "rag",
            "model": runtime_config.model,
            "result": {"content": content},
            "references": references,
            "retrieved_count": len(retrieved.hits),
            "summary_used": summary_used,
            "latency_ms": total_latency_ms,
            "retrieve_latency_ms": retrieve_latency_ms,
            "summary_latency_ms": summary_latency_ms,
            "llm_latency_ms": llm_latency_ms,
        }

    async def stream(
        self,
        db: Session,
        req: RagRunRequest,
        req_ctx: RequestContext,
        *,
        request_type: str = "chat",
    ) -> AsyncGenerator[StreamEvent, None]:
        """真 token-level RAG 流，按协议 v1 产出 StreamEvent 对象。

        阶段:
        1. 在 worker thread 跑 ``_prepare_stream``(retrieve + 可选 summary +
           拼 prompt + 构 runtime_config),同步 DB 操作不阻塞 event loop
        2. run.started + ext.references
        3. 用 ``ModelGatewayService.chat_completion_stream`` 拉 LLM 流,
           逐 delta 转 block.delta（经块状态机）
        4. run.finished（usage / sources / latency 进 ext）
        """
        started_at = time.perf_counter()
        run_id = new_run_id()
        try:
            prep = await asyncio.to_thread(self._prepare_stream, req, req_ctx, request_type)
        except ServiceError as e:
            logger.warning(
                "[rag] stream prepare rejected: app_id=%s code=%s msg=%s",
                req.app_id,
                e.code,
                e.msg,
            )
            yield RunError(run_id=run_id, code=str(e.code), message=e.msg)
            return
        except Exception as e:
            logger.exception("[rag] stream prepare failed")
            yield RunError(run_id=run_id, code="INTERNAL_ERROR", message=str(e))
            return

        yield RunStarted(
            run_id=run_id,
            ext={
                "app_id": str(req.app_id),
                "app_type": "rag",
                "model": prep["runtime_config"].model,
                "retrieved_count": len(prep["references"]),
                "summary_used": prep["summary_used"],
            },
        )

        if prep["references"]:
            yield ExtReferences(run_id=run_id, ext_version=1, items=prep["references"])

        msg = MessageStreamState(run_id)
        # 真 token 流。日志由 model_gateway 内部聚合落地。
        usage: dict[str, Any] = {}
        stream_error: str | None = None
        log_db = SessionLocal()
        try:
            async for ev in self._model_gateway_service.chat_completion_stream(
                db=log_db,
                req=LiteLLMChatRequest(
                    messages=prep["chat_messages"],
                    runtime_config=prep["runtime_config"],
                ),
                req_ctx=req_ctx,
                app_id=req.app_id,
                app_type="rag",
                request_type=request_type,
            ):
                if "delta" in ev:
                    for out in msg.text(ev["delta"]):
                        yield out
                elif "usage" in ev:
                    usage = ev["usage"]
                elif "error" in ev:
                    stream_error = str(ev["error"])
        finally:
            log_db.close()

        for out in msg.finish():
            yield out

        if stream_error is not None:
            yield RunError(run_id=run_id, code="INTERNAL_ERROR", message=stream_error)
            return

        sources = self._references_to_sources(prep["references"])
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        yield RunFinished(
            run_id=run_id,
            stop_reason="end_turn",
            ext={"usage": usage, "sources": sources, "latency_ms": latency_ms},
        )

    def _prepare_stream(
        self,
        req: RagRunRequest,
        req_ctx: RequestContext,
        request_type: str,
    ) -> dict[str, Any]:
        """同步阶段:校验 app / retrieve / 可选 summary / 构建 chat messages +
        runtime_config。在 worker thread 跑,返回给 async stream 用。"""
        db = SessionLocal()
        try:
            app = self._app_runtime.get_app(db, req.app_id)
            if app.app_type != "rag":
                raise ServiceError(ErrorCode.BAD_REQUEST, "app is not rag type")
            app_config = self._app_runtime.get_app_config(db, req.app_id)
            kb_ids = self._extract_kb_ids(app_config)
            if not kb_ids:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    "rag app must bind at least one knowledge base",
                )
            query, history = self._resolve_query_and_history(req)
            if not query:
                raise ServiceError(ErrorCode.BAD_REQUEST, "rag run requires a user query")

            retrieve_req = self._build_retrieve_req(app_config, kb_ids, query)
            retrieved = self._kb_retrieve_service.retrieve(db, retrieve_req, req_ctx)

            summary_used = False
            if app_config.get("enable_summary") and retrieved.hits:
                condensed = self._run_summary_stage(
                    db, app_config, retrieved.hits, query, req_ctx, request_type
                )
                if condensed:
                    context_block = condensed
                    summary_used = True
                else:
                    context_block = self._format_context(retrieved.hits)
            else:
                context_block = (
                    self._format_context(retrieved.hits)
                    if retrieved.hits
                    else "(no relevant documents found)"
                )

            system_prompt = self._render_system_prompt(app_config, context_block, query)
            runtime_config = self._app_runtime.build_chat_runtime(db, req.app_id)
            chat_messages: list[ModelGatewayChatMessage] = [
                ModelGatewayChatMessage(role="system", content=system_prompt)
            ]
            if history:
                chat_messages.extend(history)
            chat_messages.append(ModelGatewayChatMessage(role="user", content=query))

            return {
                "runtime_config": runtime_config,
                "chat_messages": chat_messages,
                "references": [self._hit_to_reference(h) for h in retrieved.hits],
                "summary_used": summary_used,
            }
        finally:
            db.close()

    @staticmethod
    def _references_to_sources(refs: list[dict[str, Any]]) -> list[str]:
        """把 reference 富对象压缩为 chat UI 用的简短字符串。"""
        out: list[str] = []
        for r in refs:
            name = r.get("doc_name") or "untitled"
            ref = r.get("doc_ref") or ""
            label = f"{name} ({ref})" if ref else name
            if label not in out:  # 同文档多 chunk 合并显示
                out.append(label)
        return out

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_query_and_history(
        req: RagRunRequest,
    ) -> tuple[str, list[ModelGatewayChatMessage]]:
        """从 req.messages 抽最后一条 user 作为 query,前面作为 history。
        若 messages 为空,fallback 到 req.query。"""
        if req.messages:
            last_user_idx = -1
            for i in range(len(req.messages) - 1, -1, -1):
                if req.messages[i].role == "user":
                    last_user_idx = i
                    break
            if last_user_idx < 0:
                # 没有 user 消息但有 messages: 退回 req.query
                return req.query.strip(), []
            query = (req.messages[last_user_idx].content or "").strip()
            history = req.messages[:last_user_idx]
            return query, list(history)
        return req.query.strip(), []

    @staticmethod
    def _extract_kb_ids(app_config: dict[str, Any]) -> list[str]:
        # v2: RAG 应用检索面向 RAG 库; 兼容旧 kb_ids 键(P4 统一改造命名)
        raw = (
            app_config.get("dataset_ids")
            or app_config.get("datasetIds")
            or app_config.get("kb_ids")
            or app_config.get("kbIds")
        )
        if not isinstance(raw, list):
            return []
        return [str(x) for x in raw if x]

    @staticmethod
    def _build_retrieve_req(
        app_config: dict[str, Any], dataset_ids: list[str], query: str
    ) -> RetrieveReq:
        # UI 字段名:top_n / vector_weight / enable_rerank + rerank_model
        # 兼容旧字段:top_k / rerank_id
        rerank_id = None
        if app_config.get("enable_rerank"):
            rerank_id = app_config.get("rerank_model") or app_config.get("rerank_id") or None
        elif app_config.get("rerank_id"):
            rerank_id = app_config.get("rerank_id")
        return RetrieveReq(
            dataset_ids=dataset_ids,
            question=query,
            top_k=int(app_config.get("top_n") or app_config.get("top_k") or 5),
            similarity_threshold=float(app_config.get("similarity_threshold") or 0.2),
            vector_similarity_weight=float(
                app_config.get("vector_weight") or app_config.get("vector_similarity_weight") or 0.3
            ),
            rerank_id=rerank_id,
        )

    def _run_summary_stage(
        self,
        db: Session,
        app_config: dict[str, Any],
        hits: list[RetrieveHit],
        query: str,
        req_ctx: RequestContext,
        request_type: str,
    ) -> str | None:
        """启用 summary 时跑 condensation 阶段,返回精炼后的 context 文本。
        任何异常(模型未注册/调用失败)都吞掉返回 None,由 caller 退回 raw chunks。"""
        model_name = app_config.get("summary_model") or ""
        if not isinstance(model_name, str) or not model_name.strip():
            logger.warning("[rag] enable_summary=true but summary_model empty, skip summary stage")
            return None
        try:
            runtime_config = self._app_runtime.build_chat_runtime_by_model_name(
                db,
                model_name=model_name.strip(),
                model_setting={
                    "temperature": float(app_config.get("summary_temperature") or 0.3),
                },
            )
        except ServiceError as e:
            logger.warning("[rag] summary model %r unavailable: %s", model_name, e.msg)
            return None

        summary_prompt_tmpl = app_config.get("summary_prompt") or DEFAULT_SUMMARY_PROMPT
        chunks_block = self._format_context(hits)
        sys_prompt = summary_prompt_tmpl.replace("{{chunks}}", chunks_block)
        user_prompt = f"User question: {query}\n\n请输出精炼后的相关上下文。"
        try:
            resp = self._model_gateway_service.chat_completion(
                db=db,
                req=LiteLLMChatRequest(
                    messages=[
                        ModelGatewayChatMessage(role="system", content=sys_prompt),
                        ModelGatewayChatMessage(role="user", content=user_prompt),
                    ],
                    runtime_config=runtime_config,
                ),
                req_ctx=req_ctx,
                app_id=None,
                app_type="rag",
                request_type=f"{request_type}.summary",
            )
        except Exception as e:
            logger.warning("[rag] summary stage call failed: %s", e)
            return None

        return self._extract_content(resp.data or resp.raw_response) or None

    @classmethod
    def _render_system_prompt(
        cls, app_config: dict[str, Any], context_block: str, question: str
    ) -> str:
        template = app_config.get("rag_prompt_template") or DEFAULT_RAG_PROMPT_TEMPLATE
        rendered = template.replace("{{context}}", context_block).replace("{{question}}", question)
        base = app_config.get("system_prompt")
        if isinstance(base, str) and base.strip():
            return f"{base.strip()}\n\n{rendered}"
        return rendered

    @staticmethod
    def _format_context(hits: list[RetrieveHit]) -> str:
        parts: list[str] = []
        for i, hit in enumerate(hits, start=1):
            ref = hit.doc_ref or "?"
            name = hit.doc_name or "untitled"
            body = (hit.content or "").strip()
            if len(body) > _CHUNK_TRUNCATE_CHARS:
                body = body[:_CHUNK_TRUNCATE_CHARS] + "..."
            parts.append(f'[#{i}] [[doc:{ref}]] from "{name}":\n{body}')
        return "\n\n".join(parts)

    @staticmethod
    def _extract_content(payload: dict[str, Any] | None) -> str:
        """OpenAI 风格响应:choices[0].message.content。
        其它形态尽力 fallback,真没有就返回空串(让前端能渲染日志,不抛错)。"""
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    c = msg.get("content")
                    if isinstance(c, str):
                        return c
        if isinstance(payload.get("content"), str):
            return payload["content"]
        return ""

    @staticmethod
    def _hit_to_reference(hit: RetrieveHit) -> dict[str, Any]:
        snippet = (hit.content or "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        return {
            "doc_ref": hit.doc_ref,
            "doc_id": hit.easyai_doc_id,
            "doc_name": hit.doc_name,
            "kb_id": hit.kb_id,
            "chunk_id": hit.chunk_id,
            "similarity": hit.similarity,
            "snippet": snippet,
        }
