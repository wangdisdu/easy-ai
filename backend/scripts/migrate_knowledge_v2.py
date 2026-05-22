"""知识库 v2 数据迁移: v1(KB ≡ Dataset 1:1) → v2(组织层 / 向量化层解耦)。

对每个既有 ``tb_kb``:
  1. 建一个 ``tb_rag_dataset``, 搬运 embedding / 分块 / RAGFlow dataset 等向量化字段
  2. 若有未分类文档(``category_id=0``), 建「默认分类」并把这些文档移入
  3. 该 KB 的每个分类 → 建 ``tb_kb_category_mapping`` 指向上面的 RAG 库
  4. 该 KB 的每篇文档 → 回填 ``rag_dataset_id``, 规整 ``vectorize_status``

然后回填 blob: 逐文档从 RAGFlow 下载原文存入 ``kb_storage``, 写回 ``storage_path``。
下载失败的文档 ``storage_path`` 留空 —— 即「原文缺失」标记, 仍可检索, 不能重新向量化。

前置: 已执行 ``make db-upgrade`` 到 ``0024_knowledge_v2``。

用法:
    cd backend
    uv run python scripts/migrate_knowledge_v2.py [选项]

选项:
    --backfill-only   跳过结构迁移, 只跑 blob 回填(可反复执行)
    --skip-backfill   只做结构迁移, 不下载原文
    --force           即使检测到已迁移仍重跑结构迁移
    --user-id N       RAGFlow 下载兜底用户 id(默认取每个 KB 的创建者)
    --dry-run         只打印将做的操作, 不写库 / 不落盘

退出码: 0 成功 / 1 失败。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

# 让 PYTHONPATH 包含 backend/, 这样 ``app.*`` import 可解析
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.snowflake import SnowflakeGenerator  # noqa: E402
from app.db.schema import (  # noqa: E402
    TbKbCategory,
    TbKbCategoryMapping,
    TbKbDocument,
    TbRagDataset,
)
from app.db.session import SessionLocal  # noqa: E402
from app.integration import kb_storage, ragflow_client  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_kb_v2")

_idgen = SnowflakeGenerator(settings.snowflake_worker_id)

# 旧 parse_status → 新 vectorize_status(cancelled 归为 error, 其余同名)
_VEC_STATUS = {
    "pending": "pending",
    "parsing": "parsing",
    "done": "done",
    "error": "error",
    "cancelled": "error",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _dataset_status(kb: SimpleNamespace) -> str:
    if not kb.ragflow_dataset_id:
        return "creating"
    return {"ready": "ready", "syncing": "syncing", "error": "error"}.get(kb.status or "", "ready")


# ── 结构迁移 ──────────────────────────────────────────────────────────


def migrate_structure(db, dry_run: bool) -> None:
    # tb_kb 的向量化旧列即将由 0025 删除,ORM 已去列,这里用原始 SQL 读取
    kbs = [
        SimpleNamespace(**dict(r))
        for r in db.execute(
            text(
                "SELECT id, name, description, ragflow_dataset_id, embedding_model, "
                "chunk_method, parser_config, doc_count, chunk_count, status, "
                "last_synced_at, create_user FROM tb_kb"
            )
        ).mappings()
    ]
    logger.info("结构迁移: 共 %d 个知识库", len(kbs))

    for kb in kbs:
        now = _now_ms()

        # 1. 建 RAG 库
        dataset = TbRagDataset(
            id=_idgen.next_id(),
            name=kb.name,
            description=kb.description,
            ragflow_dataset_id=kb.ragflow_dataset_id,
            embedding_model=kb.embedding_model or "",
            chunk_method=kb.chunk_method or "naive",
            parser_config=kb.parser_config,
            doc_count=kb.doc_count,
            chunk_count=kb.chunk_count,
            status=_dataset_status(kb),
            last_synced_at=kb.last_synced_at,
            create_time=now,
            update_time=now,
            create_user=kb.create_user,
            update_user=kb.create_user,
        )
        db.add(dataset)
        db.flush()

        # 2. 未分类文档 → 默认分类
        uncategorized = db.execute(
            select(func.count())
            .select_from(TbKbDocument)
            .where(TbKbDocument.kb_id == kb.id, TbKbDocument.category_id == 0)
        ).scalar_one()
        if uncategorized:
            default_cat = db.execute(
                select(TbKbCategory).where(
                    TbKbCategory.kb_id == kb.id,
                    TbKbCategory.parent_id == 0,
                    TbKbCategory.name == "默认分类",
                )
            ).scalar_one_or_none()
            if default_cat is None:
                cat_id = _idgen.next_id()
                default_cat = TbKbCategory(
                    id=cat_id,
                    kb_id=kb.id,
                    name="默认分类",
                    parent_id=0,
                    id_path=f"/{cat_id}/",
                    level=1,
                    sort=0,
                    create_time=now,
                    update_time=now,
                    create_user=kb.create_user,
                    update_user=kb.create_user,
                )
                db.add(default_cat)
                db.flush()
            db.execute(
                TbKbDocument.__table__.update()
                .where(TbKbDocument.kb_id == kb.id, TbKbDocument.category_id == 0)
                .values(category_id=default_cat.id, update_time=now)
            )

        # 3. 该 KB 全部分类 → 映射到 RAG 库
        cats = db.execute(select(TbKbCategory).where(TbKbCategory.kb_id == kb.id)).scalars().all()
        for cat in cats:
            db.add(
                TbKbCategoryMapping(
                    id=_idgen.next_id(),
                    category_id=cat.id,
                    rag_dataset_id=dataset.id,
                    status="active",
                    create_time=now,
                    update_time=now,
                    create_user=kb.create_user,
                    update_user=kb.create_user,
                )
            )

        # 4. 文档回填 rag_dataset_id + 规整 vectorize_status
        docs = db.execute(select(TbKbDocument).where(TbKbDocument.kb_id == kb.id)).scalars().all()
        for doc in docs:
            doc.rag_dataset_id = dataset.id
            doc.vectorize_status = _VEC_STATUS.get(doc.vectorize_status or "", "pending")
            doc.update_time = now

        logger.info(
            "  KB %s(%s): RAG库=%s, 分类=%d, 文档=%d, 未分类移入默认=%d",
            kb.id,
            kb.name,
            dataset.id,
            len(cats),
            len(docs),
            uncategorized,
        )

    if dry_run:
        db.rollback()
        logger.info("结构迁移: --dry-run, 已回滚")
    else:
        db.commit()
        logger.info("结构迁移: 已提交")


# ── blob 回填 ─────────────────────────────────────────────────────────


def backfill_blobs(db, fallback_user: int, dry_run: bool) -> bool:
    if not settings.ragflow_enabled:
        logger.warning("ragflow_enabled=False, 跳过 blob 回填")
        return True

    docs = (
        db.execute(select(TbKbDocument).where(TbKbDocument.ragflow_doc_id.is_not(None)))
        .scalars()
        .all()
    )
    logger.info("blob 回填: 共 %d 篇有 RAGFlow 文档的记录", len(docs))

    # RAG 库 id → ragflow_dataset_id
    ds_rows = db.execute(select(TbRagDataset.id, TbRagDataset.ragflow_dataset_id)).all()
    ds_map = {r[0]: r[1] for r in ds_rows}

    client = ragflow_client.get_client()
    done = skipped = failed = 0

    for doc in docs:
        if kb_storage.exists(doc.storage_path):
            skipped += 1
            continue
        ragflow_ds = ds_map.get(doc.rag_dataset_id)
        if not ragflow_ds:
            logger.warning("  文档 %s: RAG 库未绑定 RAGFlow dataset, 跳过", doc.id)
            failed += 1
            continue

        relpath = kb_storage.build_relpath(doc.kb_id, doc.id, doc.format)
        if dry_run:
            logger.info("  [dry-run] 将下载 %s → %s", doc.id, relpath)
            done += 1
            continue
        try:
            data = client.download_document(
                ragflow_ds,
                doc.ragflow_doc_id,
                user_id=doc.create_user or fallback_user,
            )
            kb_storage.save(relpath, data)
            doc.storage_path = relpath
            doc.update_time = _now_ms()
            db.commit()
            done += 1
        except Exception as e:  # noqa: BLE001 —— 单篇失败不阻断整体
            db.rollback()
            logger.error("  文档 %s 回填失败: %s", doc.id, e)
            failed += 1

    logger.info("blob 回填完成: 成功=%d, 已存在跳过=%d, 失败=%d", done, skipped, failed)
    return failed == 0


# ── 入口 ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="知识库 v2 数据迁移")
    parser.add_argument("--backfill-only", action="store_true")
    parser.add_argument("--skip-backfill", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if not args.backfill_only:
            already = db.execute(select(func.count()).select_from(TbRagDataset)).scalar_one()
            if already and not args.force:
                logger.warning(
                    "tb_rag_dataset 已有 %d 行, 疑似已迁移; 跳过结构迁移" "(--force 可强制重跑)",
                    already,
                )
            else:
                migrate_structure(db, args.dry_run)

        ok = True
        if not args.skip_backfill:
            ok = backfill_blobs(db, args.user_id, args.dry_run)
        return 0 if ok else 1
    except Exception:
        db.rollback()
        logger.exception("迁移失败")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
