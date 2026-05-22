"""RAG 库 / 分类映射 / 检索 模型(v2 向量化层)。

RAG 库对应一个 RAGFlow Dataset,持有 embedding / 分块配置。本地分类通过
``tb_kb_category_mapping`` 映射到 RAG 库(N:1 互斥)。详见
``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.core.doc_ref import encode_doc_ref
from app.db.schema import TbRagDataset

# RAGFlow 支持的 chunk_method
VALID_CHUNK_METHODS = {"naive", "qa", "manual", "book", "table", "laws"}


# ── RAG 库 CRUD ─────────────────────────────────────────────────────────


class RagDatasetCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    # 留空时 service 从 system_setting ai.default.embedding_model_id 反查
    embedding_model: str | None = Field(default=None, max_length=255)
    chunk_method: str = Field(default="naive")
    parser_config: dict | None = Field(default=None)


class RagDatasetUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    # embedding_model / chunk_method 不允许修改(RAGFlow 限制)


class RagDatasetPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=32)


class RagDatasetResp(BaseModel):
    id: str
    name: str
    description: str | None = None
    ragflow_dataset_id: str | None = None
    embedding_model: str
    chunk_method: str
    parser_config: dict | None = None
    doc_count: int = 0
    chunk_count: int = 0
    mapped_category_count: int = 0
    status: str
    last_synced_at: int | None = None
    create_user: str | None = None
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbRagDataset, mapped_category_count: int = 0) -> RagDatasetResp:
        parser_cfg: dict | None = None
        if entity.parser_config:
            try:
                parser_cfg = json.loads(entity.parser_config)
            except json.JSONDecodeError:
                parser_cfg = None
        return cls(
            id=str(entity.id),
            name=entity.name,
            description=entity.description,
            ragflow_dataset_id=entity.ragflow_dataset_id,
            embedding_model=entity.embedding_model,
            chunk_method=entity.chunk_method,
            parser_config=parser_cfg,
            doc_count=entity.doc_count,
            chunk_count=entity.chunk_count,
            mapped_category_count=mapped_category_count,
            status=entity.status,
            last_synced_at=entity.last_synced_at,
            create_user=str(entity.create_user) if entity.create_user else None,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class RagDatasetOption(BaseModel):
    """RAG 库下拉项,供 RAG 应用绑定检索源使用。"""

    id: str
    name: str
    embedding_model: str
    chunk_method: str
    doc_count: int = 0


# ── 分类 → RAG 库 映射 ──────────────────────────────────────────────────


class MappingSetReq(BaseModel):
    """整体设置某 RAG 库映射的分类集合(全量覆盖)。"""

    category_ids: list[str] = Field(default_factory=list)


class MappedCategory(BaseModel):
    """某 RAG 库已映射的一个本地分类。"""

    category_id: str
    category_name: str
    kb_id: str
    kb_name: str
    doc_count: int = 0


class LocalCategoryItem(BaseModel):
    """映射配置面板用 —— 全量本地分类 + 占用情况。
    ``mapped_dataset_id`` 非空表示该分类已被某 RAG 库占用。"""

    kb_id: str
    kb_name: str
    category_id: str
    category_name: str
    doc_count: int = 0
    mapped_dataset_id: str | None = None


# ── 检索 ────────────────────────────────────────────────────────────────


class RetrieveReq(BaseModel):
    # 检索面向 RAG 库(dataset),不再是知识库
    dataset_ids: list[str] = Field(min_length=1)
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=64)
    similarity_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    vector_similarity_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    document_ids: list[str] | None = Field(default=None)
    rerank_id: str | None = Field(default=None)
    keyword: bool = Field(default=False)


class RetrieveHit(BaseModel):
    """单条命中, 字段对齐引用溯源约定。"""

    chunk_id: str
    content: str
    similarity: float | None = None
    doc_id: str | None = None
    doc_name: str | None = None
    highlight: str | None = None
    easyai_doc_id: str | None = None
    doc_ref: str | None = None
    kb_id: str | None = None


class RetrieveResp(BaseModel):
    hits: list[RetrieveHit] = Field(default_factory=list)
    total: int = 0


def encode_ref(doc_id: int) -> str:
    """便捷封装, 给 service 层用。"""
    return encode_doc_ref(doc_id)
