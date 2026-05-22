"""知识库文档原文 blob 存储。

easy-ai 是文档真相源,原始文件落地到本地文件系统(后续可换 S3/MinIO)。
DB 中 ``tb_kb_document.storage_path`` 存相对路径,根目录由 ``settings.kb_storage_path``
决定 —— 根可整体迁移而不影响已落库记录。

相对路径布局: ``{kb_id}/{doc_id}{ext}``
"""

from __future__ import annotations

import contextlib
import os
import shutil

from app.core.config import settings


def _root() -> str:
    return os.path.abspath(settings.kb_storage_path)


def _sanitize_ext(ext: str) -> str:
    """归一化扩展名: 仅保留字母数字, 统一小写, 返回含点形式(无则空串)。"""
    cleaned = "".join(c for c in (ext or "").lstrip(".") if c.isalnum()).lower()
    return f".{cleaned}" if cleaned else ""


def build_relpath(kb_id: int, doc_id: int, ext: str) -> str:
    """构造文档相对存储路径。``ext`` 可含点也可不含。"""
    return f"{kb_id}/{doc_id}{_sanitize_ext(ext)}"


def abspath(relpath: str) -> str:
    """相对路径转绝对路径,并防止 ``..`` 越权逃出存储根。"""
    root = _root()
    path = os.path.normpath(os.path.join(root, relpath))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError(f"illegal storage path: {relpath}")
    return path


def save(relpath: str, data: bytes) -> None:
    """写入文件,自动创建上级目录。"""
    path = abspath(relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def load(relpath: str) -> bytes:
    """读取文件全部字节;不存在时抛 ``FileNotFoundError``。"""
    with open(abspath(relpath), "rb") as f:
        return f.read()


def exists(relpath: str | None) -> bool:
    if not relpath:
        return False
    return os.path.isfile(abspath(relpath))


def delete(relpath: str | None) -> None:
    """删除文件;不存在时静默。"""
    if not relpath:
        return
    with contextlib.suppress(FileNotFoundError):
        os.remove(abspath(relpath))


def delete_kb_dir(kb_id: int) -> None:
    """删除整个知识库的存储目录(知识库删除时调用)。"""
    shutil.rmtree(os.path.join(_root(), str(kb_id)), ignore_errors=True)
