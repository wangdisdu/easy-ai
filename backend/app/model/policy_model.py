from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.schema import TbToolPolicy

# ── Rule 子结构 ─────────────────────────────────────────────


class RuleReq(BaseModel):
    priority: int = Field(ge=0, le=10000)
    action: Literal["allow", "deny", "require_hitl"]
    when_ast: dict[str, Any]
    reason: str | None = Field(default=None, max_length=1000)


class RuleResp(BaseModel):
    id: str
    priority: int
    action: str
    when_ast: dict[str, Any]
    reason: str | None = None

    @classmethod
    def from_entity(cls, entity: TbToolPolicy, when_ast: dict[str, Any]) -> RuleResp:
        return cls(
            id=str(entity.id),
            priority=entity.priority,
            action=entity.action,
            when_ast=when_ast,
            reason=entity.reason,
        )


# ── Policy 顶层 ─────────────────────────────────────────────


class PolicyUpdateReq(BaseModel):
    mode: Literal["active", "shadow"]
    rules: list[RuleReq] = Field(default_factory=list)


class PolicyResp(BaseModel):
    tool_id: str
    mode: str  # 当前所有规则的 mode（v1 假定整体一致；混合时按多数投票）
    version: int  # 当前活跃版本号；0 表示从未配过
    rules: list[RuleResp] = Field(default_factory=list)


# ── 表单选项（前端 form 初始化用）───────────────────────────


class PolicyOptionsResp(BaseModel):
    """前端 form 渲染需要的元数据；与 policy_dsl §5.2 / §5.3 对齐。"""

    actions: list[str]
    operators_by_kind: dict[str, list[str]]
    context_variables: list[dict[str, str]]
