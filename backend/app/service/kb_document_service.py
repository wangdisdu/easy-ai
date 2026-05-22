"""KB 文档业务层(v2)。

easy-ai 是文档真相源:上传 = 存 blob + 写记录 + 写集成日志,**不触达 RAGFlow**。
文档的向量化由向量化 worker 异步完成(见 ``vectorization_service``)。

- upload_documents: 存原文到 blob;分类已映射 RAG 库则置 ``pending`` 等 worker
- move_documents: 改分类;跨 RAG 库时解绑旧绑定 + 重新置 pending
- delete_documents: 删 blob + 删 RAGFlow 文档 + 删记录
- download_document: 从 blob 读原文
- list_document_chunks: 透传 RAGFlow(仅已向量化文档)

详见 ``docs/knowledge-v2-design.md`` §6 / §8。
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.doc_ref import decode_doc_ref
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import (
    TbKb,
    TbKbCategory,
    TbKbCategoryMapping,
    TbKbDocument,
    TbRagDataset,
)
from app.integration import kb_storage, ragflow_client
from app.model.kb_model import KbChunkResp, KbDocumentPageReq, KbDocumentResp
from app.service.kb_errors import to_service_error
from app.service.sync_log_service import SyncLogService

logger = logging.getLogger(__name__)

MAX_UPLOAD_FILES = 20
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

_FORMAT_BY_EXT: dict[str, str] = {
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".doc": "DOC",
    ".xlsx": "XLSX",
    ".xls": "XLS",
    ".md": "MD",
    ".markdown": "MD",
    ".txt": "TXT",
    ".csv": "CSV",
    ".json": "JSON",
    ".png": "IMG",
    ".jpg": "IMG",
    ".jpeg": "IMG",
    ".webp": "IMG",
    ".gif": "IMG",
}

_MIME_BY_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _infer_format(filename: str) -> str:
    return _FORMAT_BY_EXT.get(os.path.splitext(filename)[1].lower(), "BIN")


def _infer_mime(filename: str) -> str | None:
    return _MIME_BY_EXT.get(os.path.splitext(filename)[1].lower())


class KbDocumentService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._sync_log = SyncLogService(id_generator)

    # ── 写操作 ────────────────────────────────────────────────────────

    def upload_documents(
        self,
        db: Session,
        kb_id: int,
        files: list[tuple[str, bytes]],
        category_id: int,
        req_ctx: RequestContext,
    ) -> list[KbDocumentResp]:
        """``files`` 为 (filename, blob) 列表。存原文到 blob,不触达 RAGFlow。"""
        if not files:
            raise ServiceError(ErrorCode.BAD_REQUEST, "no files to upload")
        if len(files) > MAX_UPLOAD_FILES:
            raise ServiceError(
                ErrorCode.BAD_REQUEST, f"too many files: {len(files)} > {MAX_UPLOAD_FILES}"
            )
        for name, blob in files:
            if not name or not blob:
                raise ServiceError(ErrorCode.BAD_REQUEST, "empty filename or content")
            if len(blob) > MAX_FILE_SIZE_BYTES:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"file too large: {name} {len(blob)} > {MAX_FILE_SIZE_BYTES}",
                )

        kb = self._get_kb_or_raise(db, kb_id)
        self._assert_category_in_kb(db, kb_id, category_id)
        rag_dataset_id = self._mapping_for_category(db, category_id)
        vectorize_status = "pending" if rag_dataset_id else "not_mapped"

        now = req_ctx.request_time_ms
        saved_paths: list[str] = []
        result: list[TbKbDocument] = []
        orphan_ragflow: dict[int, list[str]] = {}
        new_count = overwrite_count = 0

        try:
            for display_name, blob in files:
                ext = os.path.splitext(display_name)[1]
                entity = db.scalar(
                    select(TbKbDocument).where(
                        TbKbDocument.kb_id == kb_id,
                        TbKbDocument.name == display_name,
                    )
                )
                if entity is None:
                    doc_id = self._id_generator.next_id()
                    relpath = kb_storage.build_relpath(kb_id, doc_id, ext)
                    kb_storage.save(relpath, blob)
                    saved_paths.append(relpath)
                    entity = TbKbDocument(
                        id=doc_id,
                        kb_id=kb_id,
                        name=display_name,
                        format=_infer_format(display_name),
                        size_bytes=len(blob),
                        storage_path=relpath,
                        category_id=category_id,
                        source_type="file",
                        source_meta=json.dumps(
                            {"original_filename": display_name}, ensure_ascii=False
                        ),
                        rag_dataset_id=rag_dataset_id,
                        ragflow_doc_id=None,
                        vectorize_status=vectorize_status,
                        chunks_count=0,
                        error_message=None,
                        parse_progress=0.0,
                        create_time=now,
                        update_time=now,
                        create_user=req_ctx.user_id,
                        update_user=req_ctx.user_id,
                    )
                    db.add(entity)
                    new_count += 1
                else:
                    # 同名覆盖: 旧 RAGFlow 文档需清理
                    if entity.ragflow_doc_id and entity.rag_dataset_id:
                        orphan_ragflow.setdefault(entity.rag_dataset_id, []).append(
                            entity.ragflow_doc_id
                        )
                    relpath = entity.storage_path or kb_storage.build_relpath(kb_id, entity.id, ext)
                    kb_storage.save(relpath, blob)
                    saved_paths.append(relpath)
                    entity.format = _infer_format(display_name)
                    entity.size_bytes = len(blob)
                    entity.storage_path = relpath
                    entity.category_id = category_id
                    entity.rag_dataset_id = rag_dataset_id
                    entity.ragflow_doc_id = None
                    entity.vectorize_status = vectorize_status
                    entity.chunks_count = 0
                    entity.error_message = None
                    entity.parse_progress = 0.0
                    entity.parse_begin_at = None
                    entity.parse_duration_sec = None
                    entity.parse_progress_msg = None
                    entity.update_time = now
                    entity.update_user = req_ctx.user_id
                    overwrite_count += 1
                result.append(entity)
            db.commit()
        except Exception as e:
            db.rollback()
            for p in saved_paths:
                kb_storage.delete(p)
            if isinstance(e, ServiceError):
                raise
            logger.error("[kb] upload failed kb_id=%s err=%s", kb_id, e)
            raise ServiceError(ErrorCode.INTERNAL_ERROR, f"kb upload failed: {e}") from e

        for r in result:
            db.refresh(r)
        # 同名覆盖产生的孤儿 RAGFlow 文档, 尽力清理
        self._cleanup_ragflow_docs(db, orphan_ragflow, req_ctx.user_id)

        self._sync_log.write(
            db,
            log_type="integration",
            status="success",
            source_type="file",
            source_name="文件上传",
            target_kb_id=kb_id,
            docs_added=new_count,
            docs_updated=overwrite_count,
            detail=f"上传 {len(result)} 篇文档到「{kb.name}」",
            create_user=req_ctx.user_id,
        )
        logger.info(
            "[kb] action=upload kb_id=%s new=%d overwrite=%d", kb_id, new_count, overwrite_count
        )
        name_map = self._category_name_map(db, kb_id)
        return [KbDocumentResp.from_entity(r, name_map.get(r.category_id)) for r in result]

    def move_documents(
        self,
        db: Session,
        kb_id: int,
        doc_ids: list[int],
        category_id: int,
        req_ctx: RequestContext,
    ) -> int:
        """把文档移动到目标分类。跨 RAG 库时解绑旧绑定并重新置 pending。"""
        if not doc_ids:
            return 0
        self._get_kb_or_raise(db, kb_id)
        self._assert_category_in_kb(db, kb_id, category_id)
        target_dataset = self._mapping_for_category(db, category_id)

        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.kb_id == kb_id, TbKbDocument.id.in_(doc_ids))
        ).all()
        now = req_ctx.request_time_ms
        cleanup: dict[int, list[str]] = {}
        for row in rows:
            row.category_id = category_id
            if row.rag_dataset_id != target_dataset:
                if row.ragflow_doc_id and row.rag_dataset_id:
                    cleanup.setdefault(row.rag_dataset_id, []).append(row.ragflow_doc_id)
                row.rag_dataset_id = target_dataset
                row.ragflow_doc_id = None
                row.vectorize_status = "pending" if target_dataset else "not_mapped"
                row.error_message = None
                row.parse_progress = 0.0
                row.parse_begin_at = None
                row.parse_duration_sec = None
                row.parse_progress_msg = None
            row.update_time = now
            row.update_user = req_ctx.user_id
        db.commit()
        self._cleanup_ragflow_docs(db, cleanup, req_ctx.user_id)
        logger.info("[kb] action=move_docs kb_id=%s n=%d cat=%s", kb_id, len(rows), category_id)
        return len(rows)

    def delete_documents(
        self, db: Session, kb_id: int, doc_ids: list[int], req_ctx: RequestContext
    ) -> int:
        if not doc_ids:
            return 0
        self._get_kb_or_raise(db, kb_id)
        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.kb_id == kb_id, TbKbDocument.id.in_(doc_ids))
        ).all()
        if not rows:
            return 0

        cleanup: dict[int, list[str]] = {}
        for row in rows:
            if row.ragflow_doc_id and row.rag_dataset_id:
                cleanup.setdefault(row.rag_dataset_id, []).append(row.ragflow_doc_id)
        self._cleanup_ragflow_docs(db, cleanup, req_ctx.user_id)

        for row in rows:
            kb_storage.delete(row.storage_path)
            db.delete(row)
        db.commit()
        logger.info("[kb] action=delete_docs kb_id=%s deleted=%d", kb_id, len(rows))
        return len(rows)

    # ── 读操作 ────────────────────────────────────────────────────────

    def page_documents(
        self, db: Session, kb_id: int, req: KbDocumentPageReq
    ) -> tuple[list[KbDocumentResp], int]:
        self._get_kb_or_raise(db, kb_id)
        stmt = select(TbKbDocument).where(TbKbDocument.kb_id == kb_id)
        count_stmt = select(func.count(TbKbDocument.id)).where(TbKbDocument.kb_id == kb_id)
        conditions = []
        if req.keyword:
            conditions.append(TbKbDocument.name.like(f"%{req.keyword}%"))
        if req.category_id is not None:
            cid = int(req.category_id)
            if req.recursive and cid > 0:
                conditions.append(
                    TbKbDocument.category_id.in_(self._subtree_category_ids(db, kb_id, cid))
                )
            else:
                conditions.append(TbKbDocument.category_id == cid)
        if req.vectorize_status:
            conditions.append(TbKbDocument.vectorize_status == req.vectorize_status)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = db.scalar(count_stmt) or 0
        rows = db.scalars(
            stmt.order_by(TbKbDocument.create_time.desc())
            .offset((req.page_no - 1) * req.page_size)
            .limit(req.page_size)
        ).all()
        name_map = self._category_name_map(db, kb_id)
        return [KbDocumentResp.from_entity(r, name_map.get(r.category_id)) for r in rows], total

    def get_document_detail(self, db: Session, kb_id: int, doc_id: int) -> KbDocumentResp:
        entity = self._get_doc_or_raise(db, kb_id, doc_id)
        return KbDocumentResp.from_entity(entity, self._one_category_name(db, entity))

    def get_document_by_ref(self, db: Session, ref: str) -> KbDocumentResp:
        try:
            doc_id = decode_doc_ref(ref)
        except ValueError as e:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid doc ref: {ref}") from e
        entity = db.get(TbKbDocument, doc_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"document not found for ref={ref}")
        return KbDocumentResp.from_entity(entity, self._one_category_name(db, entity))

    def download_document(self, db: Session, kb_id: int, doc_id: int) -> tuple[bytes, str, str]:
        """返回 (raw_bytes, mime_type, filename),原文从 blob 存储读取。"""
        entity = self._get_doc_or_raise(db, kb_id, doc_id)
        if not kb_storage.exists(entity.storage_path):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"document {doc_id} original file missing")
        blob = kb_storage.load(entity.storage_path)
        mime = _infer_mime(entity.name) or "application/octet-stream"
        return blob, mime, entity.name

    def list_document_chunks(
        self,
        db: Session,
        kb_id: int,
        doc_id: int,
        req_ctx: RequestContext,
        *,
        page: int = 1,
        page_size: int = 30,
        keywords: str | None = None,
    ) -> tuple[list[KbChunkResp], int]:
        entity = self._get_doc_or_raise(db, kb_id, doc_id)
        if not entity.ragflow_doc_id or not entity.rag_dataset_id:
            return [], 0
        dataset = db.get(TbRagDataset, entity.rag_dataset_id)
        if not dataset or not dataset.ragflow_dataset_id:
            return [], 0
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

        client = ragflow_client.get_client()
        try:
            data = client.list_chunks(
                dataset.ragflow_dataset_id,
                entity.ragflow_doc_id,
                user_id=req_ctx.user_id,
                page=page,
                page_size=page_size,
                keywords=keywords,
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[kb] list_chunks failed doc_id=%s err=%s", doc_id, e)
            raise to_service_error(e, "list_chunks") from e

        chunks_raw = data.get("chunks") if isinstance(data, dict) else None
        total = int(data.get("total") or 0) if isinstance(data, dict) else 0
        chunks = [
            KbChunkResp(
                id=str(c.get("id") or c.get("chunk_id") or ""),
                content=str(c.get("content") or c.get("content_with_weight") or ""),
                document_id=c.get("document_id") or c.get("doc_id"),
                document_keyword=c.get("document_keyword") or c.get("docnm_kwd"),
                important_keywords=c.get("important_keywords") or [],
            )
            for c in (chunks_raw or [])
        ]
        return chunks, total

    # ── 内部 ──────────────────────────────────────────────────────────

    def _cleanup_ragflow_docs(
        self, db: Session, by_dataset: dict[int, list[str]], user_id: int | None
    ) -> None:
        """尽力从 RAGFlow 删除文档(解绑/覆盖/删除场景);失败仅日志。"""
        if not by_dataset or not settings.ragflow_enabled:
            return
        client = ragflow_client.get_client()
        for dataset_id, ragflow_doc_ids in by_dataset.items():
            dataset = db.get(TbRagDataset, dataset_id)
            if not dataset or not dataset.ragflow_dataset_id or not ragflow_doc_ids:
                continue
            try:
                client.delete_documents(
                    dataset.ragflow_dataset_id, ragflow_doc_ids, user_id=user_id
                )
            except ragflow_client.RagflowClientError as e:
                logger.warning(
                    "[kb] best-effort delete ragflow docs failed dataset=%s err=%s",
                    dataset_id,
                    e,
                )

    def _mapping_for_category(self, db: Session, category_id: int) -> int | None:
        if category_id <= 0:
            return None
        ds = db.scalar(
            select(TbKbCategoryMapping.rag_dataset_id).where(
                TbKbCategoryMapping.category_id == category_id
            )
        )
        return int(ds) if ds else None

    def _category_name_map(self, db: Session, kb_id: int) -> dict[int, str]:
        rows = db.execute(
            select(TbKbCategory.id, TbKbCategory.name).where(TbKbCategory.kb_id == kb_id)
        ).all()
        return {cid: name for cid, name in rows}

    def _subtree_category_ids(self, db: Session, kb_id: int, category_id: int) -> list[int]:
        node = db.get(TbKbCategory, category_id)
        if not node or node.kb_id != kb_id:
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND,
                f"kb_category not found: kb={kb_id} cat={category_id}",
            )
        return list(
            db.scalars(
                select(TbKbCategory.id).where(
                    TbKbCategory.kb_id == kb_id,
                    TbKbCategory.id_path.like(f"{node.id_path}%"),
                )
            ).all()
        )

    def _one_category_name(self, db: Session, entity: TbKbDocument) -> str | None:
        if entity.category_id <= 0:
            return None
        node = db.get(TbKbCategory, entity.category_id)
        return node.name if node else None

    def _assert_category_in_kb(self, db: Session, kb_id: int, category_id: int) -> None:
        if category_id <= 0:
            return
        node = db.get(TbKbCategory, category_id)
        if not node or node.kb_id != kb_id:
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND,
                f"kb_category not found: kb={kb_id} cat={category_id}",
            )

    def _get_kb_or_raise(self, db: Session, kb_id: int) -> TbKb:
        entity = db.get(TbKb, kb_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, f"kb not found: {kb_id}")
        return entity

    def _get_doc_or_raise(self, db: Session, kb_id: int, doc_id: int) -> TbKbDocument:
        entity = db.get(TbKbDocument, doc_id)
        if not entity or entity.kb_id != kb_id:
            raise ServiceError(
                ErrorCode.DATA_NOT_FOUND, f"kb_document not found: kb={kb_id} doc={doc_id}"
            )
        return entity
