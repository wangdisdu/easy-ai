"""知识库 v2 端到端冒烟测试。

跑通完整 v2 链路:
    建 RAG 库 → 建知识库 → 建分类 → 映射 → 上传文档 → 向量化 → 检索 → 清理

要求:
- ``ragflow`` / ``ragflow-mysql`` / ``ragflow-es`` 全部 healthy
- ``ragflow_shared_secret`` 与 ragflow 容器 ``EASYAI_SHARED_SECRET`` 一致
- ``--embedding`` 指定的 embedding 模型在 LLM 管理已注册

用法:
    cd backend
    uv run python scripts/kb_e2e_smoke.py [--embedding=BAAI/bge-large-zh-v1.5] [--keep]

退出码: 0 全过 / 1 任一步失败。
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import time
import uuid
from pathlib import Path

# 让 PYTHONPATH 包含 backend/, 这样 ``app.*`` import 可解析
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.core.request_context import RequestContext  # noqa: E402
from app.core.snowflake import SnowflakeGenerator  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.integration import ragflow_client  # noqa: E402
from app.model.kb_model import (  # noqa: E402
    KbCategoryCreateReq,
    KbCreateReq,
    KbDocumentPageReq,
)
from app.model.rag_dataset_model import RagDatasetCreateReq, RetrieveReq  # noqa: E402
from app.service.kb_category_service import KbCategoryService  # noqa: E402
from app.service.kb_document_service import KbDocumentService  # noqa: E402
from app.service.kb_retrieve_service import KbRetrieveService  # noqa: E402
from app.service.kb_service import KbService  # noqa: E402
from app.service.mapping_service import MappingService  # noqa: E402
from app.service.rag_dataset_service import RagDatasetService  # noqa: E402
from app.service.vectorization_service import VectorizationService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("kb-e2e")

SAMPLE_TEXT = """\
# KB Smoke Test Document

This is an end-to-end smoke test for the easy-ai knowledge base v2. It verifies:

- A RAG dataset gets a RAGFlow dataset_id assigned.
- A file uploaded to a mapped category is vectorized by the worker.
- The retrieval endpoint returns at least one chunk for an obvious keyword.

## Test marker

The unique marker is: SMOKE_MARKER_{uuid}.
"""


def _ctx() -> RequestContext:
    return RequestContext(
        user_id=None,
        client_ip="127.0.0.1",
        request_time_ms=int(time.time() * 1000),
    )


def _wait_vectorized(
    vec_service: VectorizationService,
    doc_service: KbDocumentService,
    kb_id: int,
    max_wait_sec: int,
) -> bool:
    """主动驱动向量化 worker(不依赖后台进程),轮询到全部文档 done/error。"""
    deadline = time.time() + max_wait_sec
    last = ""
    while time.time() < deadline:
        db = SessionLocal()
        try:
            vec_service.run_once(db)
        except Exception:
            logger.exception("run_once failed (continuing)")
        finally:
            db.close()

        db = SessionLocal()
        try:
            rows, _ = doc_service.page_documents(
                db, kb_id, KbDocumentPageReq(page_no=1, page_size=10)
            )
        finally:
            db.close()
        if rows:
            statuses = ",".join(f"{r.name}={r.vectorize_status}" for r in rows)
            if statuses != last:
                logger.info("vectorize status: %s", statuses)
                last = statuses
            if all(r.vectorize_status in ("done", "error") for r in rows):
                return all(r.vectorize_status == "done" for r in rows)
        time.sleep(3)
    return False


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--embedding",
        default=os.environ.get("KB_E2E_EMBEDDING", "BAAI/bge-large-zh-v1.5"),
        help="embedding model name registered in LLM management",
    )
    parser.add_argument(
        "--chunk-method", default="naive", choices=["naive", "qa", "manual", "book"]
    )
    parser.add_argument(
        "--wait-sec", type=int, default=180, help="max seconds to wait for vectorize"
    )
    parser.add_argument(
        "--keep", action="store_true", help="do not delete the kb / dataset at the end"
    )
    args = parser.parse_args()

    settings.ragflow_enabled = True
    logger.info("ragflow base_url=%s", settings.ragflow_base_url)
    client = ragflow_client.get_client()
    if not client.ping():
        logger.error("ragflow ping failed; container healthy and shared secret aligned?")
        return 1
    logger.info("ragflow ping ok")

    gen = SnowflakeGenerator(settings.snowflake_worker_id)
    doc_service = KbDocumentService(gen)
    kb_service = KbService(gen, doc_service)
    cat_service = KbCategoryService(gen, doc_service)
    ds_service = RagDatasetService(gen)
    mapping_service = MappingService(gen)
    vec_service = VectorizationService(gen)
    retrieve_service = KbRetrieveService()

    marker = uuid.uuid4().hex[:8]
    body = SAMPLE_TEXT.replace("{uuid}", marker).encode("utf-8")
    file_name = f"smoke-{marker}.md"

    kb_id = 0
    dataset_id = 0
    try:
        # ── 1. RAG 库 ──
        db = SessionLocal()
        try:
            ds = ds_service.create(
                db,
                RagDatasetCreateReq(
                    name=f"Smoke DS {marker}",
                    description=f"smoke run {marker}",
                    embedding_model=args.embedding,
                    chunk_method=args.chunk_method,
                ),
                _ctx(),
            )
        finally:
            db.close()
        dataset_id = int(ds.id)
        logger.info("rag dataset created: id=%s ragflow=%s", ds.id, ds.ragflow_dataset_id)

        # ── 2. 知识库 + 3. 分类 ──
        db = SessionLocal()
        try:
            kb = kb_service.create_kb(
                db,
                KbCreateReq(code=f"smoke-{marker}", name=f"Smoke KB {marker}", description="smoke"),
                _ctx(),
            )
            kb_id = int(kb.id)
            cat = cat_service.create_category(
                db, kb_id, KbCategoryCreateReq(name="smoke-cat"), _ctx()
            )
        finally:
            db.close()
        logger.info("kb created: id=%s, category id=%s", kb_id, cat.id)

        # ── 4. 映射 分类 → RAG 库 ──
        db = SessionLocal()
        try:
            mapping_service.set_mapping(db, dataset_id, [cat.id], _ctx())
        finally:
            db.close()
        logger.info("mapping set: category %s → dataset %s", cat.id, dataset_id)

        # ── 5. 上传文档 ──
        db = SessionLocal()
        try:
            docs = doc_service.upload_documents(
                db,
                kb_id=kb_id,
                files=[(file_name, body)],
                category_id=int(cat.id),
                req_ctx=_ctx(),
            )
            logger.info(
                "upload ok: %d doc(s), vectorize_status=%s",
                len(docs),
                docs[0].vectorize_status if docs else "-",
            )
        finally:
            db.close()

        # ── 6. 向量化 ──
        if not _wait_vectorized(vec_service, doc_service, kb_id, args.wait_sec):
            logger.error("vectorize did not finish within %ds", args.wait_sec)
            return 1
        logger.info("all documents vectorized")

        # ── 7. 检索 ──
        db = SessionLocal()
        try:
            result = retrieve_service.retrieve(
                db,
                RetrieveReq(
                    dataset_ids=[str(dataset_id)],
                    question=f"What is the unique marker SMOKE_MARKER_{marker}?",
                    top_k=5,
                    similarity_threshold=0.0,
                ),
                _ctx(),
            )
        finally:
            db.close()
        logger.info("retrieve hits=%d", len(result.hits))
        if not result.hits:
            logger.error("no chunks retrieved; expected at least 1 for marker %s", marker)
            return 1
        for i, hit in enumerate(result.hits[:3]):
            logger.info(
                "  hit %d sim=%s doc=%s chunk[:80]=%s",
                i,
                hit.similarity,
                hit.doc_name,
                (hit.content or "")[:80].replace("\n", " "),
            )
        return 0
    finally:
        if not args.keep:
            for label, fn in (
                ("kb", lambda db: kb_service.delete_kb(db, kb_id, _ctx())),
                ("dataset", lambda db: ds_service.delete(db, dataset_id, _ctx())),
            ):
                if (label == "kb" and not kb_id) or (label == "dataset" and not dataset_id):
                    continue
                db = SessionLocal()
                try:
                    fn(db)
                    logger.info("%s deleted", label)
                except Exception:
                    logger.exception("cleanup delete %s failed", label)
                finally:
                    with contextlib.suppress(Exception):
                        db.close()
        else:
            logger.info("kept (--keep): kb_id=%s dataset_id=%s", kb_id, dataset_id)


if __name__ == "__main__":
    sys.exit(main())
