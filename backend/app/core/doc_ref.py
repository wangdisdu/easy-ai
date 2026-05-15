"""Base36 编码/解码 Snowflake ID 为对外展示引用码。

设计:tb_kb_document.id(Snowflake BIGINT)保留为系统内部主键 + API 路由参数,
对外展示一个等价的 Base36 短串作为"引用码"(``ref``)。``ref`` 由 ``id`` 双
向无损派生,不需要 schema 加列,不需要存储。

12-13 字符,纯小写字母数字,URL/Markdown 安全。Python 内置 ``int(s, 36)`` 直接
反解;JavaScript 的 ``parseInt(s, 36)`` 同理(注意大于 2^53 时要用 BigInt)。
"""

from __future__ import annotations

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def encode_doc_ref(n: int) -> str:
    """正整数 → 小写 Base36 字符串。0 返回 "0"。"""
    if n < 0:
        raise ValueError(f"doc ref cannot encode negative: {n}")
    if n == 0:
        return "0"
    out: list[str] = []
    while n > 0:
        n, r = divmod(n, 36)
        out.append(_ALPHABET[r])
    return "".join(reversed(out))


def decode_doc_ref(s: str) -> int:
    """Base36 字符串(大小写均可)→ 正整数。
    无效输入抛 ``ValueError``。"""
    if not s:
        raise ValueError("doc ref cannot be empty")
    # int(s, 36) 自动接受大小写混合
    return int(s, 36)
