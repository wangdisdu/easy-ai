"""KB 文档业务层。

每个 ``tb_kb_document`` 与 RAGFlow Document 1:1 映射:
- upload_documents: 调 RAGFlow ``upload_documents`` + ``parse_documents`` 触发异步解析,
  本地立即记录 ``parse_status='parsing'``,前端可轮询
- list_documents: 纯读本地; refresh=True 时强制按 dataset 拉 RAGFlow 对账
- get_document_detail: 本地 + RAGFlow ``get_document`` 拿最新解析状态
- get_document_chunks: 透传 RAGFlow ``list_chunks``
- delete_documents / reparse_documents: 先调上游,本地状态同步

详见 ``docs/knowledge-rag-integration-design.md`` §5.4。
"""

from __future__ import annotations

import json
import logging
import os

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbKb, TbKbDocument
from app.integration import ragflow_client
from app.model.kb_model import KbChunkResp, KbDocumentPageReq, KbDocumentResp
from app.service.kb_errors import to_service_error

logger = logging.getLogger(__name__)

# 上传约束(与 §5.4 重要约束一致)
MAX_UPLOAD_FILES = 20
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

# 扩展名 → format 标签(纯展示用,RAGFlow 自己用 MIME 推断真实解析器)
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

# 扩展名 → MIME(RAGFlow upload 接受 multipart; mime 给 multipart Content-Type)
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

# RAGFlow `document.run` → easy-ai `parse_status` 映射
_RAGFLOW_RUN_TO_STATUS = {
    "UNSTART": "pending",
    "RUNNING": "parsing",
    "DONE": "done",
    "FAIL": "error",
    "CANCEL": "cancelled",
    # 兼容数字版本(SDK 文档里 "run": "0"/"1"/...)
    "0": "pending",
    "1": "parsing",
    "2": "cancelled",
    "3": "done",
    "4": "error",
}


def _infer_format(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _FORMAT_BY_EXT.get(ext, "BIN")


def _infer_mime(filename: str) -> str | None:
    ext = os.path.splitext(filename)[1].lower()
    return _MIME_BY_EXT.get(ext)


def _normalize_status(run_value: object) -> str:
    return _RAGFLOW_RUN_TO_STATUS.get(str(run_value or "").upper(), "parsing")


def _parse_ragflow_timestamp(v: object) -> int | None:
    """RAGFlow process_begin_at 可能是 unix 秒(float)/ 毫秒 / ISO 字符串。
    统一规整为 unix-ms;无法识别返回 None。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        # 经验阈值:>1e12 视作 ms,否则 s
        return int(v) if v > 1e12 else int(v * 1000)
    if isinstance(v, str):
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(v.replace(" ", "T")).timestamp() * 1000)
        except ValueError:
            return None
    return None


class KbDocumentService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    # ── 写操作 ────────────────────────────────────────────────────────

    def upload_documents(
        self,
        db: Session,
        kb_id: int,
        files: list[tuple[str, bytes]],
        category: str | None,
        req_ctx: RequestContext,
    ) -> list[KbDocumentResp]:
        """``files`` 为 (filename, blob) 列表。
        - 单次上传 ≤ ``MAX_UPLOAD_FILES`` 件
        - 单文件 ≤ ``MAX_FILE_SIZE_BYTES``
        """
        if not files:
            raise ServiceError(ErrorCode.BAD_REQUEST, "no files to upload")
        if len(files) > MAX_UPLOAD_FILES:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"too many files: {len(files)} > {MAX_UPLOAD_FILES}",
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
        if not kb.ragflow_dataset_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"kb {kb_id} not linked to ragflow dataset")

        # 1. 调 RAGFlow upload + parse(失败抛 ServiceError, 不写本地)
        self._require_ragflow_enabled()
        client = ragflow_client.get_client()
        upload_payload: list[tuple[str, bytes, str | None]] = [
            (name, blob, _infer_mime(name)) for name, blob in files
        ]
        try:
            uploaded = client.upload_documents(
                kb.ragflow_dataset_id, upload_payload, user_id=req_ctx.user_id
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[kb] upload_documents failed kb_id=%s err=%s", kb_id, e)
            raise to_service_error(e, "upload_documents") from e

        ragflow_doc_ids = [d.get("id") for d in uploaded if d.get("id")]
        if ragflow_doc_ids:
            try:
                client.parse_documents(
                    kb.ragflow_dataset_id, ragflow_doc_ids, user_id=req_ctx.user_id
                )
            except ragflow_client.RagflowClientError as e:
                # 解析触发失败不阻断: 文档已经入 RAGFlow,只是没开始解析;
                # 后台 poller 30s 内不会看到状态翻转,运维可手动 reparse。
                logger.warning(
                    "[kb] parse_documents trigger failed kb_id=%s docs=%s err=%s",
                    kb_id,
                    ragflow_doc_ids,
                    e,
                )

        # 2. 落本地(逐条 insert; 已存在同名则更新 ragflow_doc_id + 状态)
        now = req_ctx.request_time_ms
        result: list[TbKbDocument] = []
        for src, doc in zip(files, uploaded, strict=False):
            display_name = src[0]
            blob = src[1]
            entity = db.scalar(
                select(TbKbDocument).where(
                    TbKbDocument.kb_id == kb_id,
                    TbKbDocument.name == display_name,
                )
            )
            if entity is None:
                entity = TbKbDocument(
                    id=self._id_generator.next_id(),
                    kb_id=kb_id,
                    name=display_name,
                    format=_infer_format(display_name),
                    size_bytes=len(blob),
                    category=category,
                    source_type="file",
                    source_meta=json.dumps({"display_name": display_name}, ensure_ascii=False),
                    ragflow_doc_id=doc.get("id"),
                    parse_status="parsing",
                    chunks_count=0,
                    error_message=None,
                    create_time=now,
                    update_time=now,
                    create_user=req_ctx.user_id,
                    update_user=req_ctx.user_id,
                )
                db.add(entity)
            else:
                # 同名覆盖: 更新映射 + 重置状态
                entity.ragflow_doc_id = doc.get("id")
                entity.size_bytes = len(blob)
                entity.parse_status = "parsing"
                entity.chunks_count = 0
                entity.error_message = None
                entity.category = category
                entity.update_time = now
                entity.update_user = req_ctx.user_id
            result.append(entity)

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(
                "[kb] document insert failed kb_id=%s ragflow_docs=%s err=%s",
                kb_id,
                ragflow_doc_ids,
                e,
            )
            raise ServiceError(ErrorCode.INTERNAL_ERROR, f"kb_document insert failed: {e}") from e
        for r in result:
            db.refresh(r)
        logger.info(
            "[kb] action=upload kb_id=%s n=%d ragflow_docs=%s",
            kb_id,
            len(result),
            ragflow_doc_ids,
        )
        return [KbDocumentResp.from_entity(r) for r in result]

    def delete_documents(
        self, db: Session, kb_id: int, doc_ids: list[int], req_ctx: RequestContext
    ) -> int:
        if not doc_ids:
            return 0
        kb = self._get_kb_or_raise(db, kb_id)
        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.kb_id == kb_id, TbKbDocument.id.in_(doc_ids))
        ).all()
        if not rows:
            return 0

        ragflow_doc_ids = [r.ragflow_doc_id for r in rows if r.ragflow_doc_id]
        if ragflow_doc_ids and kb.ragflow_dataset_id:
            self._require_ragflow_enabled()
            client = ragflow_client.get_client()
            try:
                client.delete_documents(
                    kb.ragflow_dataset_id, ragflow_doc_ids, user_id=req_ctx.user_id
                )
            except ragflow_client.RagflowClientError as e:
                logger.error(
                    "[kb] delete_documents upstream failed kb_id=%s ids=%s err=%s",
                    kb_id,
                    ragflow_doc_ids,
                    e,
                )
                raise to_service_error(e, "delete_documents") from e

        for row in rows:
            db.delete(row)
        db.commit()
        logger.info("[kb] action=delete_docs kb_id=%s deleted=%d", kb_id, len(rows))
        return len(rows)

    def reparse_documents(
        self, db: Session, kb_id: int, doc_ids: list[int], req_ctx: RequestContext
    ) -> int:
        if not doc_ids:
            return 0
        kb = self._get_kb_or_raise(db, kb_id)
        if not kb.ragflow_dataset_id:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"kb {kb_id} not linked to ragflow dataset")
        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.kb_id == kb_id, TbKbDocument.id.in_(doc_ids))
        ).all()
        ragflow_doc_ids = [r.ragflow_doc_id for r in rows if r.ragflow_doc_id]
        if not ragflow_doc_ids:
            return 0

        self._require_ragflow_enabled()
        client = ragflow_client.get_client()
        try:
            client.parse_documents(kb.ragflow_dataset_id, ragflow_doc_ids, user_id=req_ctx.user_id)
        except ragflow_client.RagflowClientError as e:
            logger.error("[kb] reparse failed kb_id=%s err=%s", kb_id, e)
            raise to_service_error(e, "parse_documents") from e

        now = req_ctx.request_time_ms
        for row in rows:
            if row.ragflow_doc_id:
                row.parse_status = "parsing"
                row.error_message = None
                row.update_time = now
                row.update_user = req_ctx.user_id
        db.commit()
        logger.info("[kb] action=reparse kb_id=%s n=%d", kb_id, len(ragflow_doc_ids))
        return len(ragflow_doc_ids)

    # ── 读操作 ────────────────────────────────────────────────────────

    def page_documents(
        self,
        db: Session,
        kb_id: int,
        req: KbDocumentPageReq,
    ) -> tuple[list[KbDocumentResp], int]:
        # 校验 kb 存在(404 体验)
        self._get_kb_or_raise(db, kb_id)

        stmt = select(TbKbDocument).where(TbKbDocument.kb_id == kb_id)
        count_stmt = select(func.count(TbKbDocument.id)).where(TbKbDocument.kb_id == kb_id)
        conditions = []
        if req.keyword:
            keyword = f"%{req.keyword}%"
            conditions.append(or_(TbKbDocument.name.like(keyword)))
        if req.category:
            conditions.append(TbKbDocument.category == req.category)
        if req.parse_status:
            conditions.append(TbKbDocument.parse_status == req.parse_status)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = db.scalar(count_stmt) or 0
        rows = db.scalars(
            stmt.order_by(TbKbDocument.create_time.desc())
            .offset((req.page_no - 1) * req.page_size)
            .limit(req.page_size)
        ).all()
        return [KbDocumentResp.from_entity(r) for r in rows], total

    def get_document_detail(
        self, db: Session, kb_id: int, doc_id: int, req_ctx: RequestContext
    ) -> KbDocumentResp:
        """读本地 + 强制按 RAGFlow 拉一次最新状态(打开详情时使用)。"""
        kb = self._get_kb_or_raise(db, kb_id)
        entity = self._get_doc_or_raise(db, kb_id, doc_id)

        if entity.ragflow_doc_id and kb.ragflow_dataset_id and settings.ragflow_enabled:
            client = ragflow_client.get_client()
            try:
                doc = client.get_document(
                    kb.ragflow_dataset_id, entity.ragflow_doc_id, user_id=req_ctx.user_id
                )
            except ragflow_client.RagflowClientError as e:
                logger.warning(
                    "[kb] get_document upstream failed kb_id=%s doc_id=%s err=%s",
                    kb_id,
                    doc_id,
                    e,
                )
                doc = None
            if doc is not None:
                updated = self._sync_doc_status(entity, doc, req_ctx.request_time_ms)
                if updated:
                    db.commit()
                    db.refresh(entity)
        return KbDocumentResp.from_entity(entity)

    def download_document(
        self, db: Session, kb_id: int, doc_id: int, req_ctx: RequestContext
    ) -> tuple[bytes, str, str]:
        """返回 (raw_bytes, mime_type, filename),供 API 层 streaming 转发。

        RAGFlow 那边没存原始文件名,直接用 tb_kb_document.name(就是上传时
        的展示名,format/size 一并存的),保持与列表一致。
        """
        kb = self._get_kb_or_raise(db, kb_id)
        entity = self._get_doc_or_raise(db, kb_id, doc_id)
        if not entity.ragflow_doc_id or not kb.ragflow_dataset_id:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"document {doc_id} not yet bound to ragflow",
            )
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

        client = ragflow_client.get_client()
        try:
            blob = client.download_document(
                kb.ragflow_dataset_id, entity.ragflow_doc_id, user_id=req_ctx.user_id
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[kb] download upstream failed kb_id=%s doc_id=%s err=%s",
                         kb_id, doc_id, e)
            raise to_service_error(e, "download_document") from e
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
        kb = self._get_kb_or_raise(db, kb_id)
        entity = self._get_doc_or_raise(db, kb_id, doc_id)
        if not entity.ragflow_doc_id or not kb.ragflow_dataset_id:
            return [], 0
        self._require_ragflow_enabled()
        client = ragflow_client.get_client()
        try:
            data = client.list_chunks(
                kb.ragflow_dataset_id,
                entity.ragflow_doc_id,
                user_id=req_ctx.user_id,
                page=page,
                page_size=page_size,
                keywords=keywords,
            )
        except ragflow_client.RagflowClientError as e:
            logger.error("[kb] list_chunks failed kb_id=%s doc_id=%s err=%s", kb_id, doc_id, e)
            raise to_service_error(e, "list_chunks") from e

        chunks_raw = data.get("chunks") if isinstance(data, dict) else None
        total = int(data.get("total") or 0) if isinstance(data, dict) else 0
        chunks: list[KbChunkResp] = []
        for c in chunks_raw or []:
            chunks.append(
                KbChunkResp(
                    id=str(c.get("id") or c.get("chunk_id") or ""),
                    content=str(c.get("content") or c.get("content_with_weight") or ""),
                    document_id=c.get("document_id") or c.get("doc_id"),
                    document_keyword=c.get("document_keyword") or c.get("docnm_kwd"),
                    important_keywords=c.get("important_keywords") or [],
                )
            )
        return chunks, total

    # ── 后台 poller 用 ────────────────────────────────────────────────

    def batch_sync_status(
        self,
        db: Session,
        kb_id: int,
        ragflow_dataset_id: str,
        request_time_ms: int,
    ) -> int:
        """后台 poller 单次回拉: 把指定 KB 下 pending/parsing 的文档与 RAGFlow 对账。
        返回更新条数。具体调度由 ``app/app/kb_status_poller.py`` 负责(Step 4)。
        """
        rows = db.scalars(
            select(TbKbDocument).where(
                TbKbDocument.kb_id == kb_id,
                TbKbDocument.parse_status.in_(("pending", "parsing")),
            )
        ).all()
        if not rows:
            return 0

        self._require_ragflow_enabled()
        client = ragflow_client.get_client()
        ragflow_id_to_local = {r.ragflow_doc_id: r for r in rows if r.ragflow_doc_id}
        if not ragflow_id_to_local:
            return 0

        try:
            data = client.list_documents(
                ragflow_dataset_id,
                user_id=None,
                page=1,
                page_size=max(len(ragflow_id_to_local), 30),
            )
        except ragflow_client.RagflowClientError as e:
            logger.warning("[kb] poller list_documents failed kb_id=%s err=%s", kb_id, e)
            return 0

        upstream_docs = data.get("docs") if isinstance(data, dict) else None
        updated = 0
        for d in upstream_docs or []:
            doc_id = d.get("id")
            entity = ragflow_id_to_local.get(doc_id)
            if entity is None:
                continue
            if self._sync_doc_status(entity, d, request_time_ms):
                updated += 1

        if updated:
            db.commit()
        return updated

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _sync_doc_status(self, entity: TbKbDocument, upstream: dict, now_ms: int) -> bool:
        run_value = upstream.get("run") or upstream.get("status")
        new_status = _normalize_status(run_value)
        # chunk_num / chunks_count: RAGFlow 不同接口字段名略有差异
        new_chunks = int(
            upstream.get("chunk_num")
            or upstream.get("chunks_count")
            or upstream.get("chunk_count")
            or 0
        )
        progress_msg = upstream.get("progress_msg")
        err = upstream.get("error") or (progress_msg if new_status == "error" else None)
        # RAGFlow document.progress 是 0-1 float;某些情况下解析失败 progress=-1,
        # 这里 clamp 到 0,前端只在 parsing 状态用它,error/done 走 status pill
        try:
            new_progress = float(upstream.get("progress") or 0.0)
        except (TypeError, ValueError):
            new_progress = 0.0
        new_progress = max(0.0, min(1.0, new_progress))
        new_begin = upstream.get("process_begin_at")
        try:
            new_duration = (
                float(upstream.get("process_duration"))
                if upstream.get("process_duration") is not None
                else None
            )
        except (TypeError, ValueError):
            new_duration = None
        changed = False
        if entity.parse_status != new_status:
            entity.parse_status = new_status
            changed = True
        if entity.chunks_count != new_chunks:
            entity.chunks_count = new_chunks
            changed = True
        if new_status == "error" and err and entity.error_message != err:
            entity.error_message = str(err)[:1024]
            changed = True
        if entity.parse_progress != new_progress:
            entity.parse_progress = new_progress
            changed = True
        if progress_msg is not None and entity.parse_progress_msg != progress_msg:
            entity.parse_progress_msg = str(progress_msg)[:1024]
            changed = True
        # 仅首次拿到 process_begin_at 时记录,避免 RAGFlow 后续返回飘动
        if entity.parse_begin_at is None:
            parsed_begin = _parse_ragflow_timestamp(new_begin)
            if parsed_begin:
                entity.parse_begin_at = parsed_begin
                changed = True
        if new_duration is not None and entity.parse_duration_sec != new_duration:
            entity.parse_duration_sec = new_duration
            changed = True
        if changed:
            entity.update_time = now_ms
        return changed

    def _require_ragflow_enabled(self) -> None:
        if not settings.ragflow_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "ragflow integration disabled")

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
