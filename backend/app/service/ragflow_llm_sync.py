"""把 easy-ai LLM 管理的 Embedding/Rerank 单向同步到 RAGFlow tenant_llm。

设计参考 docs/knowledge-rag-impl-plan.md §4 Step 3:
- 单向写:RAGFlow 是从库,easy-ai 是主库
- fire-and-forget:同步走 daemon thread,失败仅 warn 不阻塞 LLM 管理写操作
- 仅 Embedding/Rerank 触发同步(Vision/OCR/LLM 暂不同步,RAG 链路不直接用)

调用入口三个:
- ``schedule_sync_model_to_ragflow``: 异步触发 add
- ``schedule_unsync_model_from_ragflow``: 异步触发 delete
- ``resync_model_blocking``: 同步阻塞版,给手动 resync API 用

整个模块不依赖 SQLAlchemy session,只接受朴素字段——这样调用方不用考虑
事务/会话状态在异步线程里的安全性。
"""

from __future__ import annotations

import logging
import threading

from app.core.config import settings
from app.integration import ragflow_client
from app.integration.ragflow_client import (
    RagflowClientError,
    resolve_ragflow_factory,
    resolve_ragflow_model_type,
)

logger = logging.getLogger(__name__)

# 仅这两种类型同步到 RAGFlow;LLM/Vision/OCR 暂不入 RAGFlow tenant_llm
# (RAGFlow 的 chat / image2text 在 easy-ai 现行 RAG 链路里不被引用)
_SYNCABLE_MODEL_TYPES = {"Embedding", "Rerank"}


def _should_sync(model_type: str) -> bool:
    return settings.ragflow_enabled and model_type in _SYNCABLE_MODEL_TYPES


def _add_llm_blocking(
    *,
    provider_type: str,
    base_url: str,
    api_key: str | None,
    model_name: str,
    model_type: str,
    user_id: int | None,
    max_tokens: int | None = None,
) -> None:
    factory = resolve_ragflow_factory(provider_type)
    rf_type = resolve_ragflow_model_type(model_type)
    client = ragflow_client.get_client()
    # RAGFlow tenant_llm.max_tokens 字段 NOT NULL;easy-ai 侧 LLM 类型有
    # max_input_tokens 字段,Embedding/Rerank 一般没设,这里兜底 8192。
    # 这只是 RAGFlow 内部元数据,实际推理上限由对方厂商接口决定,8192 是
    # 主流 embedding/rerank 厂商的安全下限。
    client.add_llm(
        user_id=user_id,
        llm_factory=factory,
        model_type=rf_type,
        llm_name=model_name,
        api_base=base_url,
        api_key=api_key or "",
        max_tokens=max_tokens or 8192,
    )


def _delete_llm_blocking(
    *,
    provider_type: str,
    model_name: str,
    user_id: int | None,
) -> None:
    factory = resolve_ragflow_factory(provider_type)
    client = ragflow_client.get_client()
    client.delete_llm(
        user_id=user_id,
        llm_factory=factory,
        llm_name=model_name,
    )


def _run_async(fn, label: str, **kwargs) -> None:
    def _wrapped() -> None:
        try:
            fn(**kwargs)
            logger.info("[ragflow-sync] %s ok model=%s", label, kwargs.get("model_name"))
        except (RagflowClientError, ValueError, RuntimeError) as e:
            # ValueError = unsupported provider_type/model_type 映射缺失
            # RagflowClientError = 网络 / 上游报错
            logger.warning(
                "[ragflow-sync] %s failed model=%s: %s",
                label,
                kwargs.get("model_name"),
                e,
            )

    threading.Thread(target=_wrapped, name=f"ragflow-sync-{label}", daemon=True).start()


# ── 公开 API ────────────────────────────────────────────────────────────


def schedule_sync_model_to_ragflow(
    *,
    provider_type: str,
    base_url: str,
    api_key: str | None,
    model_name: str,
    model_type: str,
    user_id: int | None = None,
    max_tokens: int | None = None,
) -> None:
    """如果模型类型可同步,异步将其注册到 RAGFlow tenant_llm。"""
    if not _should_sync(model_type):
        return
    _run_async(
        _add_llm_blocking,
        "add",
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        model_type=model_type,
        user_id=user_id,
        max_tokens=max_tokens,
    )


def schedule_unsync_model_from_ragflow(
    *,
    provider_type: str,
    model_name: str,
    model_type: str,
    user_id: int | None = None,
) -> None:
    """如果模型类型可同步,异步从 RAGFlow tenant_llm 删除。"""
    if not _should_sync(model_type):
        return
    _run_async(
        _delete_llm_blocking,
        "delete",
        provider_type=provider_type,
        model_name=model_name,
        user_id=user_id,
    )


def resync_model_blocking(
    *,
    provider_type: str,
    base_url: str,
    api_key: str | None,
    model_name: str,
    model_type: str,
    user_id: int | None = None,
    max_tokens: int | None = None,
) -> None:
    """同步阻塞版本:先 delete-best-effort 再 add,失败抛出。

    用于手动 ``POST /llm/model/{id}/resync``——用户主动触发,需要拿到失败原因,
    所以不吞异常,直接传递 RagflowClientError / ValueError。"""
    if not _should_sync(model_type):
        raise ValueError(
            f"model_type {model_type!r} is not syncable to ragflow "
            f"(only Embedding/Rerank are supported)"
        )
    try:
        _delete_llm_blocking(
            provider_type=provider_type, model_name=model_name, user_id=user_id
        )
    except RagflowClientError as e:
        # delete 失败一般是"不存在",add 仍可继续;仅 log
        logger.info("[ragflow-sync] resync pre-delete skipped: %s", e)
    _add_llm_blocking(
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        model_type=model_type,
        user_id=user_id,
        max_tokens=max_tokens,
    )
