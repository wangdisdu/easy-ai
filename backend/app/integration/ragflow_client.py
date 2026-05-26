"""Server-to-server RAGFlow API client.

走 RAGFlow fork 内置的 trusted-header 鉴权（与 Flowise 同形态，详见
``ragflow/api/apps/easyai/trusted_header.py`` 以及 easy-ai 设计文档
``docs/knowledge-rag-integration-design.md`` §3）。

每次请求附带:
    X-EasyAI-User  - 业务侧真实 user_id (snowflake 字符串), 仅作审计
    X-EasyAI-Ts    - unix-ms 时间戳
    X-EasyAI-Sign  - hex(hmac_sha256(ragflow_shared_secret, f"{user}.{ts}"))

无 Token、无 Session、无 RSA 密码加密：fork 后的 RAGFlow 看到合法签名即把
请求绑定到默认管理员账户 ``admin@easyai.com``，下游 ``@login_required`` /
``@token_required`` 一律放行。

只暴露 KB 业务联动需要的最小接口；签名工具单独抽出便于单测。
sync 风格,与 ``flowise_client.py`` 一致,便于在同步 service 中直接调用。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class RagflowClientError(RuntimeError):
    """Generic upstream error (network failure or non-2xx response)."""


class RagflowAuthError(RagflowClientError):
    """Trusted-header rejected (401). Usually means SHARED_SECRET mismatch
    or RAGFlow easyai_bootstrap failed; not transient."""


# ── easy-ai → RAGFlow 字典映射 ────────────────────────────────────────
# 把 easy-ai LLM 管理的标识翻译成 RAGFlow stock v0.25.2 的常量。
# 这里只覆盖 easy-ai 现在认可的 VALID_PROVIDER_TYPES / VALID_MODEL_TYPES。
# 新加 provider_type 时必须在这里同步,否则同步到 RAGFlow 会抛 ValueError。
#
# RAGFlow factory 取值参考 ragflow/api/db/init_data.py 中 LLMFactories 表的 name 列。
# "OpenAI-API-Compatible" 是 RAGFlow 内置的"通用 openai 风格 endpoint"工厂,
# 支持自定义 api_base+api_key,因此阿里百炼(compatible-mode)、智谱、火山等都
# 走这个 factory,无需在 RAGFlow 里单独注册供应商。
_PROVIDER_TYPE_TO_RAGFLOW_FACTORY: dict[str, str] = {
    "openai": "OpenAI",
    "openai_compatible": "OpenAI-API-Compatible",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "azure": "Azure-OpenAI",
    "ollama": "Ollama",
    # dashscope 原生(RAGFlow QWenRerank/QWenEmbed 用 dashscope SDK 调原生 API,
    # 不走 OpenAI-compatible mode)。base_url 字段会被 RAGFlow 侧忽略。
    "tongyi": "Tongyi-Qianwen",
}

# easy-ai 的 model_type 用首字母大写(LLM/Embedding/Rerank/Vision/OCR),
# RAGFlow 内部 tenant_llm.model_type 用小写,且 Vision/OCR 都归到 image2text。
_EASYAI_MODEL_TYPE_TO_RAGFLOW: dict[str, str] = {
    "LLM": "chat",
    "Embedding": "embedding",
    "Rerank": "rerank",
    "Vision": "image2text",
    "OCR": "image2text",
}


def resolve_ragflow_factory(provider_type: str) -> str:
    """easy-ai provider_type → RAGFlow llm_factory。未知值抛 ValueError,
    上层应当捕获并 warn,而不是静默回落到 OpenAI(否则 api_base 配错也跑不通)。"""
    factory = _PROVIDER_TYPE_TO_RAGFLOW_FACTORY.get(provider_type)
    if not factory:
        raise ValueError(f"unsupported provider_type for ragflow sync: {provider_type}")
    return factory


def resolve_ragflow_model_type(model_type: str) -> str:
    """easy-ai model_type → RAGFlow model_type。未知值抛 ValueError。"""
    rf = _EASYAI_MODEL_TYPE_TO_RAGFLOW.get(model_type)
    if not rf:
        raise ValueError(f"unsupported model_type for ragflow sync: {model_type}")
    return rf


def build_ragflow_model_ref(model: str, provider_type: str) -> str:
    """拼装 RAGFlow API(create_dataset 的 embedding_model、retrieve 的 rerank_id 等)
    需要的 ``"{model}@{factory}"`` 引用串。"""
    return f"{model}@{resolve_ragflow_factory(provider_type)}"


def _sign(secret: str, user_id: str, ts_ms: int) -> str:
    return hmac.new(
        secret.encode(),
        f"{user_id}.{ts_ms}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _headers(user_id: int | str | None) -> dict[str, str]:
    ts_ms = int(time.time() * 1000)
    uid = str(user_id if user_id is not None else 0)
    return {
        "X-EasyAI-User": uid,
        "X-EasyAI-Ts": str(ts_ms),
        "X-EasyAI-Sign": _sign(settings.ragflow_shared_secret, uid, ts_ms),
    }


class RagflowClient:
    """同步 RAGFlow 客户端。进程内单例使用; 通过 ``get_client()`` 获取。"""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._root = base_url.rstrip("/")
        self._base = self._root + "/api/v1"
        # 老 web-only 蓝图(llm_app / user_app 等)挂在 /v1,不带 /api 前缀
        # 详见 ragflow/api/apps/__init__.py:302 的 register_page 路径分支
        self._legacy_base = self._root + "/v1"
        self._client = httpx.Client(timeout=httpx.Timeout(timeout))

    def close(self) -> None:
        self._client.close()

    # ── 低层请求 ──────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        user_id: int | str | None,
        *,
        json: Any = None,
        params: dict | None = None,
        files: list | None = None,
        legacy: bool = False,
    ) -> dict:
        url = f"{self._legacy_base if legacy else self._base}{path}"
        headers = _headers(user_id)
        if files is None and json is not None:
            headers["Content-Type"] = "application/json"
        try:
            resp = self._client.request(
                method, url, headers=headers, json=json, params=params, files=files
            )
        except httpx.TimeoutException as e:
            raise RagflowClientError(f"ragflow timeout: {method} {path}") from e
        except httpx.HTTPError as e:
            raise RagflowClientError(f"ragflow unreachable: {method} {path}: {e}") from e

        if resp.status_code == 401:
            raise RagflowAuthError(f"ragflow auth failed ({method} {path}): {resp.text[:200]}")
        if resp.status_code >= 400:
            raise RagflowClientError(
                f"ragflow {method} {path} failed: {resp.status_code} {resp.text[:300]}"
            )

        data = resp.json()
        if data.get("code", 0) not in (0, 200):
            # RAGFlow 业务错误码(200 OK 但 body.code != 0)
            raise RagflowClientError(
                f"ragflow {method} {path} returned code={data.get('code')}: {data.get('message')}"
            )
        return data

    # ── Dataset ──────────────────────────────────────────────────────

    def create_dataset(
        self,
        name: str,
        *,
        user_id: int | str | None,
        embedding_model: str,
        chunk_method: str = "naive",
        description: str | None = None,
        parser_config: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "name": name,
            "embedding_model": embedding_model,
            "chunk_method": chunk_method,
        }
        if description is not None:
            body["description"] = description
        if parser_config is not None:
            body["parser_config"] = parser_config
        data = self._request("POST", "/datasets", user_id, json=body)
        return data["data"]

    def list_datasets(
        self,
        *,
        user_id: int | str | None,
        page: int = 1,
        page_size: int = 30,
        name: str | None = None,
        ds_id: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if name:
            params["name"] = name
        if ds_id:
            params["id"] = ds_id
        data = self._request("GET", "/datasets", user_id, params=params)
        return data.get("data") or []

    def get_dataset(self, dataset_id: str, *, user_id: int | str | None) -> dict | None:
        rows = self.list_datasets(user_id=user_id, ds_id=dataset_id, page=1, page_size=1)
        return rows[0] if rows else None

    def update_dataset(self, dataset_id: str, *, user_id: int | str | None, **fields: Any) -> None:
        self._request("PUT", f"/datasets/{dataset_id}", user_id, json=fields)

    def delete_datasets(self, ids: list[str], *, user_id: int | str | None) -> None:
        self._request("DELETE", "/datasets", user_id, json={"ids": ids})

    # ── Document ─────────────────────────────────────────────────────

    def upload_documents(
        self,
        dataset_id: str,
        files: list[tuple[str, bytes, str | None]],
        *,
        user_id: int | str | None,
    ) -> list[dict]:
        """``files`` 元组形如 (display_name, blob, content_type | None)。"""
        multipart = [
            ("file", (name, blob, content_type or "application/octet-stream"))
            for name, blob, content_type in files
        ]
        data = self._request("POST", f"/datasets/{dataset_id}/documents", user_id, files=multipart)
        return data.get("data") or []

    def list_documents(
        self,
        dataset_id: str,
        *,
        user_id: int | str | None,
        page: int = 1,
        page_size: int = 30,
        keywords: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if keywords:
            params["keywords"] = keywords
        data = self._request("GET", f"/datasets/{dataset_id}/documents", user_id, params=params)
        return data.get("data") or {}

    def download_document(
        self, dataset_id: str, document_id: str, *, user_id: int | str | None
    ) -> bytes:
        """获取原始文件二进制。RAGFlow 的 SDK ``GET /datasets/<id>/documents/<id>``
        本质是文件下载端点(``application/octet-stream``),走 token_required;
        fork 后的 trusted-header 短路已覆盖这条路径。"""
        url = f"{self._base}/datasets/{dataset_id}/documents/{document_id}"
        headers = _headers(user_id)
        try:
            resp = self._client.get(url, headers=headers)
        except httpx.TimeoutException as e:
            raise RagflowClientError(f"ragflow timeout: download {dataset_id}/{document_id}") from e
        except httpx.HTTPError as e:
            raise RagflowClientError(
                f"ragflow unreachable: download {dataset_id}/{document_id}: {e}"
            ) from e
        if resp.status_code == 401:
            raise RagflowAuthError(
                f"ragflow auth failed (download {dataset_id}/{document_id}): " f"{resp.text[:200]}"
            )
        if resp.status_code >= 400:
            raise RagflowClientError(
                f"ragflow download {dataset_id}/{document_id} failed: "
                f"{resp.status_code} {resp.text[:300]}"
            )
        return resp.content

    def get_document(
        self, dataset_id: str, document_id: str, *, user_id: int | str | None
    ) -> dict | None:
        # 注意: SDK 的 GET /datasets/<id>/documents/<id> 是文件下载端点,
        # 返回原始文件二进制,不是 JSON 元数据。要单条元数据走 list 接口的
        # ?id= 过滤(restful_apis/document_api.py:812)。
        data = self._request(
            "GET",
            f"/datasets/{dataset_id}/documents",
            user_id,
            params={"id": document_id, "page_size": 1},
        )
        payload = data.get("data") or {}
        docs = payload.get("docs") or []
        return docs[0] if docs else None

    def delete_documents(
        self, dataset_id: str, ids: list[str], *, user_id: int | str | None
    ) -> None:
        self._request("DELETE", f"/datasets/{dataset_id}/documents", user_id, json={"ids": ids})

    def parse_documents(
        self, dataset_id: str, ids: list[str], *, user_id: int | str | None
    ) -> None:
        # RAGFlow v0.25.2: SDK 的 POST /datasets/<id>/chunks 走 @token_required(需 Bearer),
        # 用 restful_apis 的等价端点 @login_required, 走 _load_user → trusted-header 生效。
        self._request(
            "POST",
            f"/datasets/{dataset_id}/documents/parse",
            user_id,
            json={"document_ids": ids},
        )

    def stop_parse(self, dataset_id: str, ids: list[str], *, user_id: int | str | None) -> None:
        self._request(
            "POST",
            f"/datasets/{dataset_id}/documents/stop",
            user_id,
            json={"document_ids": ids},
        )

    # ── Chunk ────────────────────────────────────────────────────────

    def list_chunks(
        self,
        dataset_id: str,
        document_id: str,
        *,
        user_id: int | str | None,
        page: int = 1,
        page_size: int = 30,
        keywords: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if keywords:
            params["keywords"] = keywords
        data = self._request(
            "GET",
            f"/datasets/{dataset_id}/documents/{document_id}/chunks",
            user_id,
            params=params,
        )
        return data.get("data") or {}

    # ── Retrieval ────────────────────────────────────────────────────

    def retrieve(
        self,
        *,
        user_id: int | str | None,
        dataset_ids: list[str],
        question: str,
        document_ids: list[str] | None = None,
        top_k: int = 8,
        similarity_threshold: float = 0.2,
        vector_similarity_weight: float = 0.3,
        rerank_id: str | None = None,
        keyword: bool = False,
    ) -> dict:
        body: dict[str, Any] = {
            "dataset_ids": dataset_ids,
            "question": question,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "vector_similarity_weight": vector_similarity_weight,
            "keyword": keyword,
        }
        if document_ids:
            body["document_ids"] = document_ids
        if rerank_id:
            body["rerank_id"] = rerank_id
        data = self._request("POST", "/retrieval", user_id, json=body)
        return data.get("data") or {}

    # ── LLM 管理(用于 §5.7 双向同步) ────────────────────────────────

    def list_my_llms(self, *, user_id: int | str | None) -> dict:
        # llm_app 蓝图挂在 /v1 不带 /api 前缀,详见 _legacy_base 注释
        data = self._request("GET", "/llm/my_llms", user_id, legacy=True)
        return data.get("data") or {}

    def add_llm(
        self,
        *,
        user_id: int | str | None,
        llm_factory: str,
        model_type: str,
        llm_name: str,
        api_base: str,
        api_key: str,
        max_tokens: int | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "llm_factory": llm_factory,
            "model_type": model_type,
            "llm_name": llm_name,
            "api_base": api_base,
            "api_key": api_key,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        self._request("POST", "/llm/add_llm", user_id, json=body, legacy=True)

    def delete_llm(self, *, user_id: int | str | None, llm_factory: str, llm_name: str) -> None:
        self._request(
            "POST",
            "/llm/delete_llm",
            user_id,
            json={"llm_factory": llm_factory, "llm_name": llm_name},
            legacy=True,
        )

    # ── 健康检查 ─────────────────────────────────────────────────────

    def ping(self, *, user_id: int | str | None = None) -> bool:
        """探活;任何 2xx 视作通。"""
        try:
            self._request("GET", "/system/version", user_id)
            return True
        except RagflowClientError:
            return False


# ── 进程内单例 ──────────────────────────────────────────────────────────

_singleton: RagflowClient | None = None


def get_client() -> RagflowClient:
    """获取/初始化进程级 RagflowClient。必须在 ``settings.ragflow_enabled`` 为 True
    时才调用,否则抛 ``RagflowClientError``。"""
    global _singleton
    if not settings.ragflow_enabled:
        raise RagflowClientError("ragflow integration disabled (settings.ragflow_enabled=False)")
    if _singleton is None:
        _singleton = RagflowClient(
            base_url=settings.ragflow_base_url,
            timeout=settings.ragflow_timeout_sec,
        )
        logger.info("[ragflow] client initialized: base_url=%s", settings.ragflow_base_url)
    return _singleton


def close_client() -> None:
    """供 lifespan shutdown 时调用,关闭 httpx 连接池。"""
    global _singleton
    if _singleton is not None:
        _singleton.close()
        _singleton = None
