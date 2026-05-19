from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.core.doc_ref import encode_doc_ref
from app.db.schema import TbKb, TbKbCategory, TbKbDocument

# RAGFlow 支持的 chunk_method,与 ragflow_client.create_dataset 的入参对齐
VALID_CHUNK_METHODS = {"naive", "qa", "manual", "book", "table", "laws"}

# 文档 parse_status, 与 RAGFlow run state 1:1 映射
VALID_PARSE_STATUSES = {"pending", "parsing", "done", "error", "cancelled"}

# KB 业务状态
VALID_KB_STATUSES = {"draft", "ready", "syncing", "error"}

# code 命名规则
_CODE_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"


# ── KB CRUD ─────────────────────────────────────────────────────────────


class KbCreateReq(BaseModel):
    code: str = Field(min_length=1, max_length=255, pattern=_CODE_PATTERN)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None)
    # 可选: 留空时 kb_service 从 system_setting ai.default.embedding_model_id 反查
    # 当系统设置也没配时抛 KB_EMBEDDING_NOT_CONFIGURED。落库前会被替换为
    # RAGFlow 认识的 "{model}@{factory}" 字符串,后续不可改。
    embedding_model: str | None = Field(default=None, max_length=255)
    chunk_method: str = Field(default="naive")
    # RAGFlow parser_config,按 chunk_method 不同 schema 不同(可选)
    parser_config: dict | None = Field(default=None)


class KbUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    # embedding_model / chunk_method 不允许在更新接口中修改(RAGFlow 限制)


class KbPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=32)


class KbResp(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    ragflow_dataset_id: str | None = None
    embedding_model: str
    chunk_method: str
    parser_config: dict | None = None
    doc_count: int = 0
    chunk_count: int = 0
    status: str
    last_synced_at: int | None = None
    create_user: str | None = None
    create_time: int
    update_time: int

    @classmethod
    def from_entity(cls, entity: TbKb) -> KbResp:
        parser_cfg: dict | None = None
        if entity.parser_config:
            try:
                parser_cfg = json.loads(entity.parser_config)
            except json.JSONDecodeError:
                parser_cfg = None
        return cls(
            id=str(entity.id),
            code=entity.code,
            name=entity.name,
            description=entity.description,
            ragflow_dataset_id=entity.ragflow_dataset_id,
            embedding_model=entity.embedding_model,
            chunk_method=entity.chunk_method,
            parser_config=parser_cfg,
            doc_count=entity.doc_count,
            chunk_count=entity.chunk_count,
            status=entity.status,
            last_synced_at=entity.last_synced_at,
            create_user=str(entity.create_user) if entity.create_user else None,
            create_time=entity.create_time,
            update_time=entity.update_time,
        )


class KbOption(BaseModel):
    """KB 下拉项,供应用工厂绑定 kb_ids 使用。"""

    id: str
    code: str
    name: str
    embedding_model: str
    chunk_method: str
    doc_count: int


# ── KB Category(树形, 单归属, 纯 easy-ai 侧组织维度)──────────────────────


class KbCategoryCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # 父分类 id; "0"(默认)表示挂在知识库根下
    parent_id: str = Field(default="0")


class KbCategoryUpdateReq(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # 传入则表示移动到新父节点("0"=移到根); 不传不改父
    parent_id: str | None = Field(default=None)
    sort: int | None = Field(default=None)


class KbCategoryNode(BaseModel):
    """分类树节点。``doc_count`` 为直挂该节点(不含子树)的文档数。"""

    id: str
    kb_id: str
    name: str
    parent_id: str
    level: int
    sort: int
    doc_count: int = 0
    children: list[KbCategoryNode] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, entity: TbKbCategory, doc_count: int = 0) -> KbCategoryNode:
        return cls(
            id=str(entity.id),
            kb_id=str(entity.kb_id),
            name=entity.name,
            parent_id=str(entity.parent_id),
            level=entity.level,
            sort=entity.sort,
            doc_count=doc_count,
        )


class KbCategoryDeletePreview(BaseModel):
    """删除分类的影响面。``deleted=False`` 表示这是一次 dry-run(未带 confirm)。"""

    deleted: bool
    category_count: int = 0
    document_count: int = 0


# ── KB Document ─────────────────────────────────────────────────────────


class KbDocumentPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    keyword: str | None = Field(default=None, max_length=255)
    # 旧字符串过滤, 暂保留向后兼容; 新前端用 category_id
    category: str | None = Field(default=None, max_length=255)
    # 分类节点 id; "0" 显式筛"未分类"; None 表示不按分类过滤
    category_id: str | None = Field(default=None)
    # True 时连同 category_id 子树下的文档一并返回
    recursive: bool = Field(default=False)
    parse_status: str | None = Field(default=None, max_length=32)


class KbDocumentMoveReq(BaseModel):
    ids: list[str] = Field(min_length=1)
    # 目标分类 id; "0"=移到未分类
    category_id: str = Field(default="0")


class KbDocumentResp(BaseModel):
    id: str
    # Base36 短串引用码, 由 id 双向无损派生; 前端展示 / 用户复制都用这个。
    # API 路由参数仍接受 id, ref 仅作展示与 RAG 引用语法用。
    ref: str
    kb_id: str
    name: str
    format: str
    size_bytes: int | None = None
    # 旧字符串分类, 暂保留只读
    category: str | None = None
    # 树形分类: "0"=未分类; category_name 由 service join 回填
    category_id: str = "0"
    category_name: str | None = None
    source_type: str
    source_meta: dict | None = None
    ragflow_doc_id: str | None = None
    parse_status: str
    chunks_count: int
    error_message: str | None = None
    # 解析进度元数据,parse_status='parsing' 时前端用来渲染进度条 + 已耗时
    parse_progress: float = 0.0
    parse_begin_at: int | None = None
    parse_duration_sec: float | None = None
    parse_progress_msg: str | None = None
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
            category=entity.category,
            category_id=str(entity.category_id),
            category_name=category_name,
            source_type=entity.source_type,
            source_meta=source_meta,
            ragflow_doc_id=entity.ragflow_doc_id,
            parse_status=entity.parse_status,
            chunks_count=entity.chunks_count,
            error_message=entity.error_message,
            parse_progress=entity.parse_progress,
            parse_begin_at=entity.parse_begin_at,
            parse_duration_sec=entity.parse_duration_sec,
            parse_progress_msg=entity.parse_progress_msg,
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


# ── Retrieval ───────────────────────────────────────────────────────────


class KbRetrieveReq(BaseModel):
    kb_ids: list[str] = Field(min_length=1)
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=64)
    similarity_threshold: float = Field(default=0.2, ge=0.0, le=1.0)
    # 向量相似度与关键词混合检索的权重, 0=纯关键词, 1=纯向量;默认 0.3
    # 偏关键词,对中文短查询更稳。对应 RAGFlow retrieve.vector_similarity_weight
    vector_similarity_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    document_ids: list[str] | None = Field(default=None)
    rerank_id: str | None = Field(default=None)
    keyword: bool = Field(default=False)


class KbRetrieveHit(BaseModel):
    """单条命中, 字段对齐 app-factory-design.md 引用溯源约定。"""

    chunk_id: str
    content: str
    similarity: float | None = None
    # ragflow 内部 doc id, 保留向后兼容
    doc_id: str | None = None
    doc_name: str | None = None
    highlight: str | None = None
    # easy-ai 侧字段, RAG 应用引用溯源用; 未找到映射时为 None
    easyai_doc_id: str | None = None
    doc_ref: str | None = None
    kb_id: str | None = None


class KbRetrieveResp(BaseModel):
    hits: list[KbRetrieveHit] = Field(default_factory=list)
    total: int = 0
