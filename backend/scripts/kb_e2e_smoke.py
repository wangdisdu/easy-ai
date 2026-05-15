"""KB 端到端冒烟测试。

跑通: create KB → upload PDF → 轮询解析完成 → retrieve → delete。
要求:
- ``ragflow`` / ``ragflow-mysql`` / ``ragflow-es`` 全部 healthy
- ``ragflow_shared_secret`` 与 ragflow 容器 ``EASYAI_SHARED_SECRET`` 一致
- LLM 管理已经注册了 ``--embedding`` 指定的 embedding 模型;
  或 RAGFlow 默认 embedding 可用

用法:
    cd backend
    uv run python scripts/kb_e2e_smoke.py [--embedding=bge-large-zh-v1.5] [--keep]

退出码: 0 全过 / 1 任一步失败。
"""

from __future__ import annotations

import argparse
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
    KbCreateReq,
    KbDocumentPageReq,
    KbRetrieveReq,
)
from app.service.kb_document_service import KbDocumentService  # noqa: E402
from app.service.kb_retrieve_service import KbRetrieveService  # noqa: E402
from app.service.kb_service import KbService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("kb-e2e")

SAMPLE_TEXT = """\
# KB Smoke Test Document

This is an end-to-end smoke test for the easy-ai knowledge base. It exists to
verify that:

- A new tb_kb row gets a RAGFlow dataset_id assigned.
- A small file uploaded via /api/v1/kb/{id}/document is parsed by RAGFlow.
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


def _wait_parsed(
    doc_service: KbDocumentService,
    kb_id: int,
    max_wait_sec: int,
) -> bool:
    deadline = time.time() + max_wait_sec
    last_status = ""
    while time.time() < deadline:
        db = SessionLocal()
        try:
            rows, _ = doc_service.page_documents(
                db, kb_id, KbDocumentPageReq(page_no=1, page_size=10)
            )
        finally:
            db.close()
        if not rows:
            logger.info("waiting: no documents yet")
        else:
            statuses = ",".join(f"{r.name}={r.parse_status}" for r in rows)
            if statuses != last_status:
                logger.info("parse status: %s", statuses)
                last_status = statuses
            if all(r.parse_status in ("done", "error", "cancelled") for r in rows):
                return all(r.parse_status == "done" for r in rows)
        # 主动触发一次回拉(避免依赖 backend 后台 poller)
        db = SessionLocal()
        try:
            from app.db.schema import TbKb

            kb = db.get(TbKb, kb_id)
            if kb and kb.ragflow_dataset_id:
                doc_service.batch_sync_status(
                    db, kb_id, kb.ragflow_dataset_id, int(time.time() * 1000)
                )
        except Exception:
            logger.exception("batch_sync_status failed (continuing)")
        finally:
            db.close()
        time.sleep(3)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--embedding",
        default=os.environ.get("KB_E2E_EMBEDDING", "BAAI/bge-large-zh-v1.5"),
        help="embedding model name registered in RAGFlow",
    )
    parser.add_argument(
        "--chunk-method", default="naive", choices=["naive", "qa", "manual", "book"]
    )
    parser.add_argument(
        "--wait-sec", type=int, default=180, help="max seconds to wait for parse"
    )
    parser.add_argument(
        "--keep", action="store_true", help="do not delete the KB at the end"
    )
    args = parser.parse_args()

    settings.ragflow_enabled = True
    logger.info("ragflow base_url=%s", settings.ragflow_base_url)
    logger.info("ping ragflow ...")
    client = ragflow_client.get_client()
    if not client.ping():
        logger.error(
            "ragflow ping failed; is the container healthy and EASYAI_SHARED_SECRET aligned?"
        )
        return 1
    logger.info("ragflow ping ok")

    gen = SnowflakeGenerator(settings.snowflake_worker_id)
    kb_service = KbService(gen)
    doc_service = KbDocumentService(gen)
    retrieve_service = KbRetrieveService()

    marker = uuid.uuid4().hex[:8]
    code = f"smoke-{marker}"
    name = f"Smoke {marker}"
    body = SAMPLE_TEXT.replace("{uuid}", marker).encode("utf-8")
    file_name = f"smoke-{marker}.md"

    db = SessionLocal()
    try:
        logger.info("create kb code=%s", code)
        kb_resp = kb_service.create_kb(
            db,
            KbCreateReq(
                code=code,
                name=name,
                description=f"smoke run {marker}",
                embedding_model=args.embedding,
                chunk_method=args.chunk_method,
            ),
            _ctx(),
        )
        logger.info("kb created: id=%s dataset_id=%s", kb_resp.id, kb_resp.ragflow_dataset_id)
        kb_id = int(kb_resp.id)
    finally:
        db.close()

    try:
        # ── upload ──
        db = SessionLocal()
        try:
            logger.info("upload %s (%d bytes)", file_name, len(body))
            docs = doc_service.upload_documents(
                db,
                kb_id=kb_id,
                files=[(file_name, body)],
                category="smoke",
                req_ctx=_ctx(),
            )
            logger.info("upload ok: %d doc(s)", len(docs))
        finally:
            db.close()

        # ── wait parse ──
        ok = _wait_parsed(doc_service, kb_id, args.wait_sec)
        if not ok:
            logger.error("parse did not finish within %ds", args.wait_sec)
            return 1
        logger.info("all documents parsed")

        # ── retrieve ──
        db = SessionLocal()
        try:
            req = KbRetrieveReq(
                kb_ids=[str(kb_id)],
                question=f"What is the unique marker SMOKE_MARKER_{marker}?",
                top_k=5,
                similarity_threshold=0.0,
            )
            result = retrieve_service.retrieve(db, req, _ctx())
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
        if not any(marker in (h.content or "") for h in result.hits):
            logger.warning(
                "marker %s not found in any hit; chunking may be too coarse but parse + retrieve "
                "still worked",
                marker,
            )

        return 0
    finally:
        if not args.keep:
            try:
                db = SessionLocal()
                kb_service.delete_kb(db, kb_id, _ctx())
                logger.info("kb deleted")
            except Exception:
                logger.exception("cleanup delete_kb failed")
            finally:
                with __import__("contextlib").suppress(Exception):
                    db.close()
        else:
            logger.info("kb kept (--keep): id=%s code=%s", kb_id, code)


if __name__ == "__main__":
    sys.exit(main())
