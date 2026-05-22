"""知识向量化业务层。

把知识库文档(easy-ai blob 原文)推送到映射的 RAG 库(RAGFlow Dataset)并
跟踪解析进度。由向量化 worker(``app/app/vectorization_worker.py``)周期驱动
``run_once``;文档级手动重做走 ``revectorize``。

文档向量化状态机(``tb_kb_document.vectorize_status``):
    not_mapped ──(分类被映射)──▶ pending
    pending    ──(worker 推 RAGFlow)──▶ parsing
    parsing    ──(RAGFlow 解析完成)──▶ done / error

worker 处理 ``pending`` 时:已有 ``ragflow_doc_id`` 走重新解析,否则上传原文。
详见 ``docs/knowledge-v2-design.md`` §7 / §8。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbKbDocument, TbRagDataset
from app.integration import kb_storage, ragflow_client
from app.service.sync_log_service import SyncLogService

logger = logging.getLogger(__name__)

# 单轮 worker 处理的文档上限,避免一次占用过久
_BATCH_LIMIT = 100

# RAGFlow document.run → vectorize_status
_RUN_TO_STATUS = {
    "UNSTART": "pending",
    "RUNNING": "parsing",
    "DONE": "done",
    "FAIL": "error",
    "CANCEL": "error",
    "0": "pending",
    "1": "parsing",
    "2": "error",
    "3": "done",
    "4": "error",
}

# 扩展名 → MIME(RAGFlow upload multipart Content-Type)
_MIME_BY_EXT: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "md": "text/markdown",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def _mime_for(fmt: str) -> str:
    return _MIME_BY_EXT.get((fmt or "").lower(), "application/octet-stream")


def _normalize_run(run_value: object) -> str:
    return _RUN_TO_STATUS.get(str(run_value or "").upper(), "parsing")


def _parse_ts(v: object) -> int | None:
    """RAGFlow process_begin_at 可能是 unix 秒/毫秒/ISO 字符串,统一为 unix-ms。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v) if v > 1e12 else int(v * 1000)
    if isinstance(v, str):
        try:
            from datetime import datetime

            return int(datetime.fromisoformat(v.replace(" ", "T")).timestamp() * 1000)
        except ValueError:
            return None
    return None


class VectorizationService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._sync_log = SyncLogService(id_generator)

    # ── 手动重做 ──────────────────────────────────────────────────────

    def revectorize(
        self, db: Session, kb_id: int, doc_ids: list[int], req_ctx: RequestContext
    ) -> int:
        """把指定文档置为 pending,交给 worker 重新向量化。仅对已映射(有
        rag_dataset_id)的文档生效。"""
        if not doc_ids:
            return 0
        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.kb_id == kb_id, TbKbDocument.id.in_(doc_ids))
        ).all()
        now = req_ctx.request_time_ms
        affected = 0
        for row in rows:
            if not row.rag_dataset_id:
                continue
            row.vectorize_status = "pending"
            row.error_message = None
            row.parse_progress = 0.0
            row.parse_begin_at = None
            row.parse_duration_sec = None
            row.parse_progress_msg = None
            row.update_time = now
            row.update_user = req_ctx.user_id
            affected += 1
        db.commit()
        logger.info("[vectorize] action=revectorize kb_id=%s n=%d", kb_id, affected)
        return affected

    # ── worker 单轮 ──────────────────────────────────────────────────

    def run_once(self, db: Session) -> int:
        """worker 单次迭代:推送 pending 文档 + 回拉 parsing 文档进度。
        返回本轮触达的文档数。"""
        if not settings.ragflow_enabled:
            return 0
        touched = 0
        touched += self._process_pending(db)
        touched += self._sync_parsing(db)
        return touched

    def _process_pending(self, db: Session) -> int:
        rows = db.scalars(
            select(TbKbDocument)
            .where(
                TbKbDocument.vectorize_status == "pending",
                TbKbDocument.rag_dataset_id.is_not(None),
            )
            .limit(_BATCH_LIMIT)
        ).all()
        if not rows:
            return 0

        # 按 rag_dataset 分组
        by_dataset: dict[int, list[TbKbDocument]] = {}
        for r in rows:
            by_dataset.setdefault(r.rag_dataset_id, []).append(r)

        client = ragflow_client.get_client()
        now = int(time.time() * 1000)
        processed = 0
        for dataset_id, docs in by_dataset.items():
            dataset = db.get(TbRagDataset, dataset_id)
            if not dataset or not dataset.ragflow_dataset_id:
                logger.warning("[vectorize] dataset %s 未绑定 RAGFlow, 跳过", dataset_id)
                continue
            pushed = 0
            failed = 0
            for doc in docs:
                try:
                    self._push_one(client, dataset.ragflow_dataset_id, doc, now)
                    pushed += 1
                except Exception as e:  # noqa: BLE001 —— 单篇失败不阻断
                    logger.error("[vectorize] 推送文档 %s 失败: %s", doc.id, e)
                    doc.vectorize_status = "error"
                    doc.error_message = str(e)[:1024]
                    doc.update_time = now
                    failed += 1
                processed += 1
            db.commit()
            if pushed or failed:
                status = "processing" if not failed else ("partial" if pushed else "failed")
                self._sync_log.write(
                    db,
                    log_type="vectorization",
                    status=status,
                    source_type="vectorize",
                    source_name=dataset.name,
                    target_dataset_id=dataset_id,
                    docs_added=pushed,
                    detail=f"推送 {pushed} 篇文档进入向量化"
                    + (f", {failed} 篇失败" if failed else ""),
                )
        return processed

    def _push_one(self, client, ragflow_dataset_id: str, doc: TbKbDocument, now: int) -> None:
        """把单篇文档推进 RAGFlow:已有 ragflow_doc_id 走重新解析,否则上传原文。"""
        if doc.ragflow_doc_id:
            client.parse_documents(
                ragflow_dataset_id, [doc.ragflow_doc_id], user_id=doc.create_user
            )
        else:
            if not kb_storage.exists(doc.storage_path):
                raise ServiceError(ErrorCode.BAD_REQUEST, "原文缺失,无法向量化")
            blob = kb_storage.load(doc.storage_path)
            uploaded = client.upload_documents(
                ragflow_dataset_id,
                [(doc.name, blob, _mime_for(doc.format))],
                user_id=doc.create_user,
            )
            ragflow_doc_id = uploaded[0].get("id") if uploaded else None
            if not ragflow_doc_id:
                raise ServiceError(ErrorCode.UPSTREAM_RAGFLOW_ERROR, "RAGFlow 未返回文档 id")
            doc.ragflow_doc_id = ragflow_doc_id
            client.parse_documents(ragflow_dataset_id, [ragflow_doc_id], user_id=doc.create_user)
        doc.vectorize_status = "parsing"
        doc.error_message = None
        doc.parse_progress = 0.0
        doc.parse_begin_at = now
        doc.update_time = now

    def _sync_parsing(self, db: Session) -> int:
        rows = db.scalars(
            select(TbKbDocument).where(TbKbDocument.vectorize_status == "parsing")
        ).all()
        if not rows:
            return 0

        by_dataset: dict[int, list[TbKbDocument]] = {}
        for r in rows:
            if r.rag_dataset_id and r.ragflow_doc_id:
                by_dataset.setdefault(r.rag_dataset_id, []).append(r)

        client = ragflow_client.get_client()
        now = int(time.time() * 1000)
        synced = 0
        for dataset_id, docs in by_dataset.items():
            dataset = db.get(TbRagDataset, dataset_id)
            if not dataset or not dataset.ragflow_dataset_id:
                continue
            by_ragflow_id = {d.ragflow_doc_id: d for d in docs}
            try:
                data = client.list_documents(
                    dataset.ragflow_dataset_id,
                    user_id=None,
                    page=1,
                    page_size=max(len(by_ragflow_id), 30),
                )
            except ragflow_client.RagflowClientError as e:
                logger.warning("[vectorize] list_documents 失败 dataset=%s: %s", dataset_id, e)
                continue
            upstream = data.get("docs") if isinstance(data, dict) else None
            for d in upstream or []:
                entity = by_ragflow_id.get(d.get("id"))
                if entity and self._sync_doc_status(entity, d, now):
                    synced += 1
            dataset.last_synced_at = now
            db.commit()
        return synced

    def _sync_doc_status(self, entity: TbKbDocument, upstream: dict, now_ms: int) -> bool:
        """用 RAGFlow document 字段回填 vectorize_status / 进度,返回是否有变更。"""
        new_status = _normalize_run(upstream.get("run") or upstream.get("status"))
        new_chunks = int(
            upstream.get("chunk_num")
            or upstream.get("chunks_count")
            or upstream.get("chunk_count")
            or 0
        )
        progress_msg = upstream.get("progress_msg")
        err = upstream.get("error") or (progress_msg if new_status == "error" else None)
        try:
            new_progress = max(0.0, min(1.0, float(upstream.get("progress") or 0.0)))
        except (TypeError, ValueError):
            new_progress = 0.0
        try:
            new_duration = (
                float(upstream.get("process_duration"))
                if upstream.get("process_duration") is not None
                else None
            )
        except (TypeError, ValueError):
            new_duration = None

        changed = False
        if entity.vectorize_status != new_status:
            entity.vectorize_status = new_status
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
        if entity.parse_begin_at is None:
            begin = _parse_ts(upstream.get("process_begin_at"))
            if begin:
                entity.parse_begin_at = begin
                changed = True
        if new_duration is not None and entity.parse_duration_sec != new_duration:
            entity.parse_duration_sec = new_duration
            changed = True
        if changed:
            entity.update_time = now_ms
        return changed
