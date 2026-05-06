"""PolicyMiddleware：在 LangGraph wrap_tool_call hook 中执行 ACL 决策。

按设计文档 §4 流程：
  1. ACL 规则按 priority 求值，第一条命中决定动作
  2. 全部未命中 → 按工具默认 risk_level：LOW 放行；MED/HIGH require_hitl
  3. require_hitl 路径：调 langgraph.interrupt(payload) 暂停，等用户响应；
     shadow 模式下 require_hitl/deny 仅记审计、放行
  4. 全程结果落 tb_tool_audit
     - allow / deny → 中间件直接写
     - hitl_required 在 agent_app.stream 检测到 interrupt 时统一写一次（避免 LangGraph
       resume 重跑函数导致重复审计）
     - hitl_confirmed / hitl_modified / hitl_rejected → resume 后中间件写
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import interrupt

from app.app.policy_dsl import EvalContext
from app.db.session import SessionLocal
from app.service.policy_service import (
    CompiledRule,
    PolicyAuditWriter,
    load_active_rules,
)

logger = logging.getLogger(__name__)


# ── 决策载体 ────────────────────────────────────────────────────────


class _Decision:
    __slots__ = ("action", "reason", "matched_rule_id", "mode")

    def __init__(
        self,
        action: str,
        *,
        reason: str | None = None,
        matched_rule_id: int | None = None,
        mode: str = "active",
    ) -> None:
        # action: allow / deny / require_hitl
        self.action = action
        self.reason = reason
        self.matched_rule_id = matched_rule_id
        self.mode = mode


# ── 中间件 ──────────────────────────────────────────────────────────


class PolicyMiddleware(AgentMiddleware):
    """工具治理中间件，每次 agent 执行新建一个实例。"""

    def __init__(
        self,
        *,
        tool_id_by_name: dict[str, int],
        risk_level_by_tool_id: dict[int, str],
        audit_writer: PolicyAuditWriter,
        run_id: str | None = None,
        conversation_id: int | None = None,
        user_id: int | None = None,
        app_id: int | None = None,
        user_role: str | None = None,
        hitl_timeout_by_tool_id: dict[int, int | None] | None = None,
        default_hitl_timeout_seconds: int = 300,
    ) -> None:
        self._tool_id_by_name = tool_id_by_name
        self._risk_level_by_tool_id = risk_level_by_tool_id
        self._audit = audit_writer
        self._run_id = run_id
        self._conv_id = conversation_id
        self._user_id = user_id
        self._app_id = app_id
        self._user_role = user_role
        self._hitl_timeout_by_tool_id = hitl_timeout_by_tool_id or {}
        self._default_hitl_timeout = default_hitl_timeout_seconds

    # ── 同步路径 ──

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        decision, tool_id = self._decide(request)
        return self._apply_sync(decision, tool_id, request, handler)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        decision, tool_id = self._decide(request)
        return await self._apply_async(decision, tool_id, request, handler)

    # ── 共享决策逻辑 ──

    def _decide(self, request: ToolCallRequest) -> tuple[_Decision, int | None]:
        """按 §4 流程做决策；返回 (decision, tool_id)。"""
        tool_name = request.tool_call.get("name", "") if request.tool_call else ""
        tool_id = self._tool_id_by_name.get(tool_name)

        # 名字不在治理范围内的，多数是 DeepAgents 框架内置工具（task / todo / 文件系统等），
        # 不属于用户工具治理对象 → 透传，不阻断也不审计成 deny。
        if tool_id is None:
            return (
                _Decision("allow", reason=f"framework tool, not policy-governed: {tool_name}"),
                None,
            )

        # 1. 规则评估
        rules = self._load_rules(tool_id)
        params = (request.tool_call.get("args") or {}) if request.tool_call else {}
        ctx = EvalContext.from_runtime(
            parameters=params,
            user_id=self._user_id,
            user_role=self._user_role,
        )
        for rule in rules:
            if rule.predicate(ctx):
                return (
                    _Decision(
                        rule.action,
                        reason=rule.reason,
                        matched_rule_id=rule.id,
                        mode=rule.mode,
                    ),
                    tool_id,
                )

        # 全部未命中 → 按 risk_level 默认动作
        risk = (self._risk_level_by_tool_id.get(tool_id) or "low").lower()
        if risk in ("medium", "high"):
            return _Decision("require_hitl", reason=f"default by risk_level={risk}"), tool_id
        return _Decision("allow", reason="default by risk_level=low"), tool_id

    def _load_rules(self, tool_id: int) -> list[CompiledRule]:
        # 每次工具调用一份独立 session（短生命周期）
        db = SessionLocal()
        try:
            return load_active_rules(db, tool_id)
        finally:
            db.close()

    # ── 应用决策 ──

    def _apply_sync(
        self,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        # shadow：记审计、不阻断（即便 deny / require_hitl）
        if decision.mode == "shadow":
            self._audit_decision(decision, tool_id, request)
            return handler(request)

        if decision.action == "allow":
            self._audit_decision(decision, tool_id, request)
            return handler(request)

        if decision.action == "deny":
            self._audit_decision(decision, tool_id, request)
            return self._denied_message(decision, request)

        if decision.action == "require_hitl":
            return self._handle_hitl_sync(decision, tool_id, request, handler)

        # 未知动作保守 deny
        self._audit_decision(decision, tool_id, request)
        return self._denied_message(decision, request)

    async def _apply_async(
        self,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        if decision.mode == "shadow":
            self._audit_decision(decision, tool_id, request)
            return await handler(request)

        if decision.action == "allow":
            self._audit_decision(decision, tool_id, request)
            return await handler(request)

        if decision.action == "deny":
            self._audit_decision(decision, tool_id, request)
            return self._denied_message(decision, request)

        if decision.action == "require_hitl":
            return await self._handle_hitl_async(decision, tool_id, request, handler)

        self._audit_decision(decision, tool_id, request)
        return self._denied_message(decision, request)

    # ── HITL ──

    def _handle_hitl_sync(
        self,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        """active 模式 require_hitl：调 interrupt() 暂停。

        - 首次执行：interrupt(payload) 抛 GraphInterrupt，LangGraph 持久化 checkpoint，
          函数从此处中止（hitl_required 审计交由 agent_app.stream 在检测到 interrupt 时写）
        - resume 时 LangGraph 重新执行整个 wrap_tool_call → _decide 给出同一决策 → interrupt()
          直接返回缓存的 resume 值 → 走下面的 dispatch；本次代码路径只在 resume 后跑一次，
          因此这里再写 hitl_confirmed / hitl_modified / hitl_rejected 一行审计是安全的。
        """
        payload = self._build_hitl_payload(decision, tool_id, request)
        response = interrupt(payload)
        action, modified_params = self._parse_hitl_response(response)
        self._audit_hitl_response(action, decision, tool_id, request, modified_params)
        if action == "confirm":
            return handler(request)
        if action == "modify" and isinstance(modified_params, dict):
            self._mutate_request_args(request, modified_params)
            return handler(request)
        return self._reject_message(request)

    async def _handle_hitl_async(
        self,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        payload = self._build_hitl_payload(decision, tool_id, request)
        response = interrupt(payload)
        action, modified_params = self._parse_hitl_response(response)
        self._audit_hitl_response(action, decision, tool_id, request, modified_params)
        if action == "confirm":
            return await handler(request)
        if action == "modify" and isinstance(modified_params, dict):
            self._mutate_request_args(request, modified_params)
            return await handler(request)
        return self._reject_message(request)

    def _build_hitl_payload(
        self,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
    ) -> dict[str, Any]:
        tool_name = request.tool_call.get("name", "") if request.tool_call else ""
        tool_call_id = request.tool_call.get("id", "") if request.tool_call else ""
        params = (request.tool_call.get("args") or {}) if request.tool_call else {}
        risk = (self._risk_level_by_tool_id.get(tool_id) if tool_id else None) or "low"
        # 截止时间：tool 自己的 hitl_timeout_seconds 覆盖；否则取全局默认。
        timeout_s = self._default_hitl_timeout
        if tool_id is not None:
            override = self._hitl_timeout_by_tool_id.get(tool_id)
            if override is not None and override > 0:
                timeout_s = override
        deadline_ms = int(time.time() * 1000) + timeout_s * 1000
        risk_lower = str(risk).lower()
        # reason_code：给前端做展示映射用的枚举值，与 reason（调试/日志用）分离。
        if decision.matched_rule_id is not None:
            reason_code = "rule_match"
        elif risk_lower in ("high", "medium"):
            reason_code = f"default_risk_{risk_lower}"
        else:
            reason_code = "require_hitl"
        return {
            # type 字段是 SSE 推给前端的鉴别器；resume 端点也按它校验
            "type": "tool_hitl_required",
            # hitl_id 等同 tool_call_id，前端用作幂等键
            "hitl_id": tool_call_id,
            "tool_call_id": tool_call_id,
            "tool_id": str(tool_id) if tool_id is not None else None,
            "tool_name": tool_name,
            "parameters": params,
            "reason": decision.reason or "require_hitl",
            "reason_code": reason_code,
            "risk_level": risk_lower,
            "matched_rule_id": (
                str(decision.matched_rule_id) if decision.matched_rule_id else None
            ),
            "timeout_seconds": timeout_s,
            "deadline_ms": deadline_ms,
        }

    @staticmethod
    def _parse_hitl_response(response: Any) -> tuple[str, dict[str, Any] | None]:
        """归一化 resume 端送进来的 {action, parameters} 载荷。无法识别 → reject。"""
        if not isinstance(response, dict):
            return "reject", None
        action = str(response.get("action") or "").lower()
        if action not in ("confirm", "modify", "reject"):
            return "reject", None
        params = response.get("parameters")
        if action == "modify" and not isinstance(params, dict):
            return "reject", None
        return action, params if isinstance(params, dict) else None

    @staticmethod
    def _mutate_request_args(request: ToolCallRequest, params: dict[str, Any]) -> None:
        if request.tool_call is not None:
            request.tool_call["args"] = params

    def _audit_hitl_response(
        self,
        action: str,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
        modified_params: dict[str, Any] | None,
    ) -> None:
        event_type = {
            "confirm": "hitl_confirmed",
            "modify": "hitl_modified",
            "reject": "hitl_rejected",
        }.get(action, "hitl_rejected")

        params = (request.tool_call.get("args") or {}) if request.tool_call else {}
        if action == "modify" and isinstance(modified_params, dict):
            params = modified_params

        db = SessionLocal()
        try:
            self._audit.write(
                db,
                event_type=event_type,
                tool_id=tool_id,
                conversation_id=self._conv_id,
                run_id=self._run_id,
                user_id=self._user_id,
                app_id=self._app_id,
                parameters=params,
                decision_reason=decision.reason,
                matched_rule_id=decision.matched_rule_id,
            )
        except Exception:
            logger.exception(
                "policy audit (hitl response) failed event=%s tool_id=%s",
                event_type,
                tool_id,
            )
        finally:
            db.close()

    # ── 通用 ──

    def _audit_decision(
        self,
        decision: _Decision,
        tool_id: int | None,
        request: ToolCallRequest,
    ) -> None:
        # event_type 取决于 decision.action
        if decision.action == "allow":
            event_type = "tool_invoked"
        elif decision.action == "deny":
            event_type = "policy_denied"
        else:
            event_type = "policy_denied"

        params = (request.tool_call.get("args") or {}) if request.tool_call else {}
        db = SessionLocal()
        try:
            self._audit.write(
                db,
                event_type=event_type,
                tool_id=tool_id,
                conversation_id=self._conv_id,
                run_id=self._run_id,
                user_id=self._user_id,
                app_id=self._app_id,
                parameters=params,
                decision_reason=decision.reason,
                matched_rule_id=decision.matched_rule_id,
            )
        except Exception:
            # 审计失败不应影响业务流；记 log 即可。
            logger.exception(
                "policy audit write failed: event=%s tool_id=%s",
                event_type,
                tool_id,
            )
        finally:
            db.close()

    def _denied_message(
        self,
        decision: _Decision,
        request: ToolCallRequest,
    ) -> ToolMessage:
        tool_name = request.tool_call.get("name", "") if request.tool_call else ""
        tool_call_id = request.tool_call.get("id", "") if request.tool_call else ""
        reason = decision.reason or "policy denied"
        return ToolMessage(
            content=f"无权操作: {reason}",
            name=tool_name,
            tool_call_id=tool_call_id,
            status="error",
        )

    @staticmethod
    def _reject_message(request: ToolCallRequest) -> ToolMessage:
        tool_name = request.tool_call.get("name", "") if request.tool_call else ""
        tool_call_id = request.tool_call.get("id", "") if request.tool_call else ""
        return ToolMessage(
            content="用户已拒绝执行该工具",
            name=tool_name,
            tool_call_id=tool_call_id,
            status="error",
        )
