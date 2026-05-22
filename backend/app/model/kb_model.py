"""知识库 / 分类 / 文档 模型(v2 组织层)。

知识库 v2 重构后,知识库退化为纯组织单元 —— 不再持有 embedding / 分块 /
RAGFlow dataset。向量化相关模型见 ``rag_dataset_model``,同步日志见
``sync_log_model``。详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.core.doc_ref import encode_doc_ref
from app.db.schema import TbKb, TbKbCategory, TbKbDocument

# 文档向量化状态(RAGFlow 侧)
VALID_VECTORIZE_STATUSES = {"not_mapped", "pending", "parsing", "done", "error"}

# code 命名规则
_CODE_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"


# ── 知识库 CRUD(纯组织层)──────────────────────────────────────────────


class KbCreateReq(BaseModel):
    code: str = Field(min_length=1, max_length=255, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)


class KbUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)


class KbPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)


class KbResp(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    doc_count: int = 0
    category_count: int = 0
    create_user: str | None = None
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbKb, doc_count: int = 0, category_count: int = 0) -> KbResp:
        return cls(
            id=str(entity.id),
            code=entity.code,
            name=entity.name,
            description=entity.description,
            doc_count=doc_count,
            category_count=category_count,
            create_user=str(entity.create_user) if entity.create_user else None,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class KbOption(BaseModel):
    """知识库下拉项。"""

    id: str
    code: str
    name: str
    doc_count: int = 0


# ── 分类(单层扁平, 纯 easy-ai 侧组织维度)──────────────────────────────


class KbCategoryCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # 父分类 id; "0"(默认)表示挂在知识库根下
    parent_id: str = Field(default="0")


class KbCategoryUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: str | None = Field(default=None)
    sort: int | None = Field(default=None)


class KbCategoryNode(BaseModel):
    """分类树节点。``doc_count`` 为直挂该节点(不含子树)的文档数;
    ``rag_dataset_*`` 为该分类映射到的 RAG 库(未映射时为空)。"""

    id: str
    kb_id: str
    name: str
    parent_id: str
    level: int
    sort: int
    doc_count: int = 0
    rag_dataset_id: str | None = None
    rag_dataset_name: str | None = None
    children: list[KbCategoryNode] = Field(default_factory=list)

    @classmethod
    def from_entity(
        cls,
        entity: TbKbCategory,
        doc_count: int = 0,
        rag_dataset_id: str | None = None,
        rag_dataset_name: str | None = None,
    ) -> KbCategoryNode:
        return cls(
            id=str(entity.id),
            kb_id=str(entity.kb_id),
            name=entity.name,
            parent_id=str(entity.parent_id),
            level=entity.level,
            sort=entity.sort,
            doc_count=doc_count,
            rag_dataset_id=rag_dataset_id,
            rag_dataset_name=rag_dataset_name,
        )


class KbCategoryDeletePreview(BaseModel):
    """删除分类的影响面。``deleted=False`` 表示这是一次 dry-run(未带 confirm)。"""

    deleted: bool
    category_count: int = 0
    document_count: int = 0


# ── 文档 ────────────────────────────────────────────────────────────────


class KbDocumentPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    # 分类节点 id; "0" 显式筛"未分类"; None 表示不按分类过滤
    category_id: str | None = Field(default=None)
    # True 时连同 category_id 子树下的文档一并返回
    recursive: bool = Field(default=False)
    vectorize_status: str | None = Field(default=None, max_length=32)


class KbDocumentMoveReq(BaseModel):
    ids: list[str] = Field(min_length=1)
    # 目标分类 id; "0"=移到未分类
    category_id: str = Field(default="0")


class KbDocumentResp(BaseModel):
    id: str
    # Base36 短串引用码, 由 id 双向无损派生; 前端展示 / 用户复制都用这个。
    ref: str
    kb_id: str
    name: str
    format: str
    size_bytes: int | None = None
    # 树形分类: "0"=未分类; category_name 由 service join 回填
    category_id: str = "0"
    category_name: str | None = None
    source_type: str
    source_meta: dict | None = None
    # 文档所属 RAG 库(由分类映射推导); 未映射时为空
    rag_dataset_id: str | None = None
    ragflow_doc_id: str | None = None
    # not_mapped / pending / parsing / done / error
    vectorize_status: str
    chunks_count: int = 0
    error_message: str | None = None
    # 向量化进度元数据, vectorize_status='parsing' 时前端渲染进度条 + 已耗时
    parse_progress: float = 0.0
    parse_begin_at: int | None = None
    parse_duration_sec: float | None = None
    parse_progress_msg: str | None = None
    # 原文是否已落 blob 存储(回填失败的历史文档为 False, 不能重新向量化)
    has_original: bool = False
    create_user: str | None = None
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbKbDocument, category_name: str | None = None) -> KbDocumentResp:
        source_meta: dict | None = None
        if entity.source_meta:
            try:
                source_meta = json.loads(entity.source_meta)
            except json.JSONDecodeError:
                source_meta = None
        return cls(
            id=str(entity.id),
            ref=encode_doc_ref(entity.id),
            kb_id=str(entity.kb_id),
            name=entity.name,
            format=entity.format,
            size_bytes=entity.size_bytes,
            category_id=str(entity.category_id),
            category_name=category_name,
            source_type=entity.source_type,
            source_meta=source_meta,
            rag_dataset_id=(str(entity.rag_dataset_id) if entity.rag_dataset_id else None),
            ragflow_doc_id=entity.ragflow_doc_id,
            vectorize_status=entity.vectorize_status,
            chunks_count=entity.chunks_count,
            error_message=entity.error_message,
            parse_progress=entity.parse_progress,
            parse_begin_at=entity.parse_begin_at,
            parse_duration_sec=entity.parse_duration_sec,
            parse_progress_msg=entity.parse_progress_msg,
            has_original=bool(entity.storage_path),
            create_user=str(entity.create_user) if entity.create_user else None,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class KbChunkResp(BaseModel):
    """RAGFlow chunk 透传; 字段宽松,以 RAGFlow 实际返回为准。"""

    id: str
    content: str
    document_id: str | None = None
    document_keyword: str | None = None
    important_keywords: list[str] = Field(default_factory=list)
