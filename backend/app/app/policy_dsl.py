"""ACL DSL 编译与求值。

输入：JSON AST（结构见 docs/tool-approval-and-acl-design.md §5.1）
输出：纯 Python 闭包，调用一次返回 bool；运行期不调 eval / exec。

错误分两类：
- **AST 形态错**（编译期）：未知 type / 未知 op / var 不是字符串 / And 缺 conditions
  抛 PolicyDslError，由 PolicyService 在保存策略前捕获并返回 4xx。
- **运行期取值错**（求值期）：参数缺失、类型不匹配、正则非法
  闭包内部捕获并返回 False，**永不抛出**。这样一条规则失败不会打死整个策略集。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ── 类型与异常 ─────────────────────────────────────────────────────────


class PolicyDslError(Exception):
    """AST 形态非法。"""


@dataclass
class EvalContext:
    """ACL DSL 求值上下文。

    每次工具调用从运行态构造一份；只读，闭包不修改它。
    """

    parameters: dict[str, Any] = field(default_factory=dict)
    user_id: int | None = None
    user_role: str | None = None
    # 时间字段：默认 UTC；后续若工具支持自定义 tz，构造时按 tz 计算后填入。
    time_hour: int = 0
    time_weekday: int = 0  # 0=Mon ... 6=Sun

    @classmethod
    def from_runtime(
        cls,
        *,
        parameters: dict[str, Any] | None = None,
        user_id: int | None = None,
        user_role: str | None = None,
        now_ms: int | None = None,
    ) -> EvalContext:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
        return cls(
            parameters=dict(parameters or {}),
            user_id=user_id,
            user_role=user_role,
            time_hour=dt.hour,
            time_weekday=dt.weekday(),
        )


Predicate = Callable[[EvalContext], bool]


# ── 算子集合 ───────────────────────────────────────────────────────────


_NUMERIC_OPS = {"GT", "LT", "GTE", "LTE", "BETWEEN"}
_STRING_OPS = {"MATCHES", "STARTS_WITH", "ENDS_WITH", "CONTAINS"}
_COLLECTION_OPS = {"IN", "NOT_IN"}
_GENERIC_OPS = {"EQ", "NEQ"}
_ALL_OPS = _NUMERIC_OPS | _STRING_OPS | _COLLECTION_OPS | _GENERIC_OPS


_MISSING = object()


def _resolve_var(name: str, ctx: EvalContext) -> Any:
    """按 §5.3 的变量名取上下文值；不存在返回 _MISSING 哨兵。"""
    if name.startswith("parameter."):
        key = name[len("parameter.") :]
        return ctx.parameters.get(key, _MISSING)
    if name == "time.hour":
        return ctx.time_hour
    if name == "time.weekday":
        return ctx.time_weekday
    if name == "user.id":
        return _MISSING if ctx.user_id is None else ctx.user_id
    if name == "user.role":
        return _MISSING if ctx.user_role is None else ctx.user_role
    return _MISSING


def _is_real_number(v: Any) -> bool:
    """排除 bool（在 Python 里 bool 是 int 子类，对数值算子不应当数值用）。"""
    return isinstance(v, int | float) and not isinstance(v, bool)


def _eval_compare(op: str, var_value: Any, target: Any) -> bool:  # noqa: PLR0911, PLR0912
    """单个 Compare 节点求值。任何取值/类型问题统一返回 False。"""
    if var_value is _MISSING:
        return False
    try:
        if op == "EQ":
            return var_value == target
        if op == "NEQ":
            return var_value != target
        if op in _NUMERIC_OPS:
            if not _is_real_number(var_value):
                return False
            if op == "GT":
                return var_value > target
            if op == "LT":
                return var_value < target
            if op == "GTE":
                return var_value >= target
            if op == "LTE":
                return var_value <= target
            # BETWEEN
            if not isinstance(target, list) or len(target) != 2:
                return False
            low, high = target
            return low <= var_value <= high
        if op == "IN":
            return isinstance(target, list) and var_value in target
        if op == "NOT_IN":
            return isinstance(target, list) and var_value not in target
        if op in _STRING_OPS:
            if not isinstance(var_value, str) or not isinstance(target, str):
                return False
            if op == "MATCHES":
                try:
                    return bool(re.search(target, var_value))
                except re.error:
                    return False
            if op == "STARTS_WITH":
                return var_value.startswith(target)
            if op == "ENDS_WITH":
                return var_value.endswith(target)
            # CONTAINS
            return target in var_value
    except (TypeError, ValueError):
        return False
    return False


# ── 公开 API ───────────────────────────────────────────────────────────


def compile_when(ast: Any) -> Predicate:
    """把 when AST 编译为闭包。AST 形态非法抛 PolicyDslError。"""
    if not isinstance(ast, dict):
        raise PolicyDslError(f"AST node must be dict, got {type(ast).__name__}")

    node_type = ast.get("type")

    if node_type == "Compare":
        op = ast.get("op")
        var = ast.get("var")
        value = ast.get("value")
        if op not in _ALL_OPS:
            raise PolicyDslError(f"unknown op: {op!r}")
        if not isinstance(var, str):
            raise PolicyDslError(f"Compare.var must be string, got {type(var).__name__}")

        def _compare_pred(ctx: EvalContext) -> bool:
            try:
                return _eval_compare(op, _resolve_var(var, ctx), value)
            except Exception:
                return False

        return _compare_pred

    if node_type == "And":
        conditions = ast.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise PolicyDslError("And requires non-empty 'conditions' list")
        children = [compile_when(c) for c in conditions]

        def _and_pred(ctx: EvalContext) -> bool:
            return all(child(ctx) for child in children)

        return _and_pred

    raise PolicyDslError(f"unknown node type: {node_type!r}")


def validate_when(ast: Any) -> None:
    """仅做形态校验，不返回闭包；用于 PolicyService 保存前的早期检查。"""
    compile_when(ast)
