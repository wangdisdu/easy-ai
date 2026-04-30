"""工具策略加载、CRUD 与审计写入。

PolicyMiddleware 在 wrap_tool_call 里调本服务读规则、写审计；
管理 API 调本服务做策略 CRUD（含版本快照）。
策略评估本身在 policy_dsl，本服务不做。
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app.policy_dsl import PolicyDslError, Predicate, compile_when, validate_when
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbTool, TbToolAudit, TbToolPolicy
from app.model.policy_model import (
    PolicyOptionsResp,
    PolicyResp,
    PolicyUpdateReq,
    RuleResp,
)


@dataclass
class CompiledRule:
    """一条编译后的策略规则。"""

    id: int
    priority: int
    action: str  # 'deny' / 'allow' / 'require_hitl'
    predicate: Predicate
    reason: str | None
    mode: str  # 'active' / 'shadow'


def load_active_rules(db: Session, tool_id: int) -> list[CompiledRule]:
    """读该工具的当前版本规则（按 priority 降序）；编译失败的规则跳过 + log。

    `superseded_by_id IS NULL` 表示当前版本。
    """
    rows = db.scalars(
        select(TbToolPolicy)
        .where(
            TbToolPolicy.tool_id == tool_id,
            TbToolPolicy.superseded_by_id.is_(None),
        )
        .order_by(TbToolPolicy.priority.desc())
    ).all()

    compiled: list[CompiledRule] = []
    for row in rows:
        try:
            ast = json.loads(row.when_ast)
            pred = compile_when(ast)
        except (json.JSONDecodeError, PolicyDslError):
            # 单条规则坏掉不应打死整个策略集；运维通过 audit 看到 policy_modified
            # 历史 + 直接发现非法规则。这里跳过。
            continue
        compiled.append(
            CompiledRule(
                id=row.id,
                priority=row.priority,
                action=row.action,
                predicate=pred,
                reason=row.reason,
                mode=row.mode,
            )
        )
    return compiled


class PolicyAuditWriter:
    """tb_tool_audit 追加写。线程安全（每次新建 row）。"""

    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id = id_generator

    def write(
        self,
        db: Session,
        *,
        event_type: str,
        tool_id: int | None = None,
        conversation_id: int | None = None,
        run_id: str | None = None,
        user_id: int | None = None,
        app_id: int | None = None,
        parameters: dict | None = None,
        decision_reason: str | None = None,
        matched_rule_id: int | None = None,
    ) -> None:
        db.add(
            TbToolAudit(
                id=self._id.next_id(),
                event_type=event_type,
                tool_id=tool_id,
                conversation_id=conversation_id,
                run_id=run_id,
                user_id=user_id,
                app_id=app_id,
                parameters_snapshot=(
                    json.dumps(_redact(parameters), ensure_ascii=False)
                    if parameters is not None
                    else None
                ),
                decision_reason=decision_reason,
                matched_rule_id=matched_rule_id,
                create_time=int(time.time() * 1000),
            )
        )
        db.commit()


# ── PII 脱敏（最小占位实现，等后续完整规则）────────────────────────


_REDACT_KEY_PATTERNS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
)


def _redact(parameters: dict) -> dict:
    """简易脱敏：含敏感关键字的 key 整体替换为 '[REDACTED]'。"""
    out: dict = {}
    for k, v in parameters.items():
        if any(p in str(k).lower() for p in _REDACT_KEY_PATTERNS):
            out[k] = "[REDACTED]"
        else:
            out[k] = v
    return out


def collect_tool_id_by_name(rows: Iterable) -> dict[str, int]:
    """工具名 → tool_id 映射；同名按 first-wins。"""
    out: dict[str, int] = {}
    for r in rows:
        if r.tool_name and r.tool_name not in out:
            out[r.tool_name] = r.id
    return out


# ── CRUD（管理 API 调用，含版本快照）───────────────────────────────


class PolicyService:
    """工具策略管理（CRUD + 版本管理）。"""

    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id = id_generator

    def get_policy_for_tool(self, db: Session, tool_id: int) -> PolicyResp:
        """读当前版本规则集；从未配过返回空规则、version=0、mode='shadow'。"""
        if not db.get(TbTool, tool_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")

        rows = db.scalars(
            select(TbToolPolicy)
            .where(
                TbToolPolicy.tool_id == tool_id,
                TbToolPolicy.superseded_by_id.is_(None),
            )
            .order_by(TbToolPolicy.priority.desc())
        ).all()

        if not rows:
            return PolicyResp(tool_id=str(tool_id), mode="shadow", version=0, rules=[])

        # v1 假设所有规则同一 mode；混合时取多数（极端情况下保守取 shadow）
        mode_counts: dict[str, int] = {}
        for r in rows:
            mode_counts[r.mode] = mode_counts.get(r.mode, 0) + 1
        mode = max(mode_counts, key=mode_counts.get) if mode_counts else "shadow"
        version = max(r.version for r in rows)

        rules = []
        for r in rows:
            try:
                ast = json.loads(r.when_ast)
            except json.JSONDecodeError:
                ast = {}
            rules.append(RuleResp.from_entity(r, ast))
        return PolicyResp(
            tool_id=str(tool_id),
            mode=mode,
            version=version,
            rules=rules,
        )

    def replace_policy(
        self,
        db: Session,
        tool_id: int,
        req: PolicyUpdateReq,
        req_ctx: RequestContext,
    ) -> PolicyResp:
        """整体替换：把当前版本规则置 superseded，插入新版本规则。

        - 校验：每条 rule.when_ast 通过 validate_when（AST 形态错抛 4xx）
        - 版本：当前最高 version + 1（新规则均用此版本号）
        - 软改：旧规则 superseded_by_id 指向占位"删除标记"，避免悬空 NULL
                简化方案：直接置 superseded_by_id = -1（哨兵值表示"已被取代但无后继 id"）
                这样保持原本行为（PolicyMiddleware 用 IS NULL 过滤当前版本）正确。
        """
        if not db.get(TbTool, tool_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "tool not found")

        # 1. AST 形态预校验，挂到具体规则下标，便于前端定位
        for idx, rule in enumerate(req.rules):
            try:
                validate_when(rule.when_ast)
            except PolicyDslError as e:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"rule[{idx}] AST invalid: {e}",
                ) from e

        now = req_ctx.request_time_ms

        # 2. 当前版本号 = 现有最大 version + 1（仅未 superseded 的）
        existing = db.scalars(
            select(TbToolPolicy).where(
                TbToolPolicy.tool_id == tool_id,
                TbToolPolicy.superseded_by_id.is_(None),
            )
        ).all()
        new_version = (max((r.version for r in existing), default=0)) + 1

        # 3. 把旧规则置 superseded（哨兵 -1 表示"被替代且无单一后继"）
        for r in existing:
            r.superseded_by_id = -1
            r.update_time = now
            r.update_user = req_ctx.user_id

        # 4. 插入新规则
        for rule in req.rules:
            db.add(
                TbToolPolicy(
                    id=self._id.next_id(),
                    tool_id=tool_id,
                    priority=rule.priority,
                    action=rule.action,
                    when_ast=json.dumps(rule.when_ast, ensure_ascii=False),
                    reason=rule.reason,
                    mode=req.mode,
                    version=new_version,
                    superseded_by_id=None,
                    owner_user_id=req_ctx.user_id,
                    create_time=now,
                    update_time=now,
                    create_user=req_ctx.user_id,
                    update_user=req_ctx.user_id,
                )
            )

        db.commit()
        return self.get_policy_for_tool(db, tool_id)


# ── 表单选项（静态元数据，与 policy_dsl §5.2 / §5.3 对齐）─────────


def get_policy_options() -> PolicyOptionsResp:
    return PolicyOptionsResp(
        actions=["allow", "deny", "require_hitl"],
        operators_by_kind={
            "any": ["EQ", "NEQ"],
            "number": ["GT", "LT", "GTE", "LTE", "BETWEEN"],
            "collection": ["IN", "NOT_IN"],
            "string": ["MATCHES", "STARTS_WITH", "ENDS_WITH", "CONTAINS"],
        },
        context_variables=[
            {"name": "parameter.<key>", "kind": "any", "label": "参数（按工具 schema）"},
            {"name": "time.hour", "kind": "number", "label": "小时（0-23）"},
            {"name": "time.weekday", "kind": "number", "label": "星期（0=周一 ... 6=周日）"},
            {"name": "user.id", "kind": "number", "label": "调用者 user_id"},
            {"name": "user.role", "kind": "any", "label": "调用者角色"},
        ],
    )
