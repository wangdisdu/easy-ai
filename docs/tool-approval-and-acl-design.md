# 工具审批与 ACL（企业守护）详细设计

> 本文档描述 easy-ai 作为**企业级 harness agent**的工具调用治理体系：复用 deepagents 的 agent runtime、middleware 扩展点和 LangGraph checkpointer，但 HITL、ACL、风险分级、审批链、策略治理、审计与可观测性均由 easy-ai 企业层自研。

---

## 1. 功能概述

### 1.1 目标

让 agent 调用工具（API/MCP/Filesystem/Shell）时具备**企业级可控性**：

1. **策略准入**：按"用户 / 组 / 工具 / 参数 / URL / 时间 / 租户"决定 allow/deny/approval
2. **风险分级**：按工具敏感度与参数值自动评估风险，低风险放行、高风险人工审批
3. **HITL 审批**：暂停-审批-恢复，带 SLA、升级、委托
4. **破窗应急**：超级管理员在紧急情况下可强行放行，加强审计
5. **策略治理**：策略版本化、dry-run、模板化、工具指纹防漂移
6. **审计与观测**：WORM 审计流、实时大盘、越权告警

### 1.2 与 deepagents 原生能力的映射

| deepagents 能力 | 本设计中的位置 |
|---|---|
| `FilesystemPermission` | 作为 Part 6 的"文件工具子协议"；如启用 FilesystemBackend 才生效 |
| `interrupt_on` / `HumanInTheLoopMiddleware` | **不使用**。HITL 完全由自研 `ToolPolicyMiddleware.after_model` 通过 `LangGraph.interrupt()` 实现（§6）。`create_deep_agent(..., interrupt_on=...)` 在本设计中**禁止传入**，以避免双 HITL 中间件语义冲突和重复审批 |
| `_PermissionMiddleware` | 不直接使用；自研 `ToolPolicyMiddleware` 治理主 agent 和显式声明式 subagent；底层工具 wrapper 必须做最终兜底 |
| `AnthropicPromptCachingMiddleware` | 与本设计无关，但策略检查不会破坏 prompt 缓存 |
| harness profile | 策略引擎感知 profile 的 `excluded_tools`，不对被排除工具生效 |
| 默认 general-purpose subagent | deepagents 会在调用方未声明同名 subagent 时自动插入默认 `general-purpose`。主 agent middleware 不会自动覆盖它。本设计必须显式提供同名 `general-purpose` subagent spec 并注入 `ToolPolicyMiddleware`，或禁用/严格限制 `task` 工具；同时把底层工具 wrapper 作为最终治理兜底 |

### 1.3 能力分层

```
┌─────────────────────────────────────────────────────┐
│  6. 可观测性与告警（§13）                            │
├─────────────────────────────────────────────────────┤
│  5. 治理层：版本、dry-run、模板、指纹（§11）          │
├─────────────────────────────────────────────────────┤
│  4. 审批层：SLA/升级/委托/破窗/通知（§7 §8 §9）      │
├─────────────────────────────────────────────────────┤
│  3. 风险分级：LOW/MED/HIGH 自动分流（§5）            │
├─────────────────────────────────────────────────────┤
│  2. 策略引擎：多维度条件评估（§4）                   │
├─────────────────────────────────────────────────────┤
│  1. 拦截层：ToolPolicyMiddleware（§3）               │
└─────────────────────────────────────────────────────┘
         ▲
         │
  LangGraph interrupt() + checkpointer (Part I of long-session-design.md)
  （不使用 deepagents 的 interrupt_on / HumanInTheLoopMiddleware）
```

---

## 2. 适用场景

| 场景 | 策略/流程 |
|---|---|
| 外发邮件到竞品域名 | `send_email` + `to_email` 正则命中 → `approval` |
| SQL DELETE 语句 | `execute_sql` + `sql` 含 `DELETE/DROP` → `approval`（director） |
| 创建工单到外部系统 | `create_ticket` + 金额 > ¥10000 → 二级审批 |
| 非工作时间调用财务接口 | `time_window` 外 + `finance` 标签 → `deny` |
| 被外部工具返回"执行 X"诱骗 | 输出内容 DLP 扫描 → 阻断后续 |
| 紧急定位生产故障需绕审批 | 破窗模式：SRE 带理由强行放行，审计单生成 |
| 新上线工具先灰度 | 策略 dry-run：记录命中但不阻断 |
| 审批人在休假 | 按委托链自动转交 |

---

## 3. 总体架构

### 3.0 前置运行上下文

本设计依赖统一 `AgentRunContext`，不能直接假设 `RequestContext` 自带会话和租户字段。运行时在 `ConversationService` / `OpenAPI` 入口组装：

```python
class AgentRunContext(BaseModel):
    run_id: str
    app_id: int
    user_id: int | None
    conversation_id: int | None
    request_type: str
    tenant_id: int | None = None
    team_ids: list[int] = []
    role_codes: list[str] = []
    trace_id: str | None = None
```

当前项目尚无完整 tenant/workspace 模型，P0/P1 中 `tenant_id=None`，所有策略按 app/user/team 维度生效；多租户能力单独灰度。

数据库约束原则：本设计只新增业务表、唯一约束和查询索引，不新增数据库外键约束；跨表完整性由 service 层校验。

### 3.1 请求路径

```
用户消息
  ↓
AgentApp._prepare（_build_tools 对每个工具包 wrapper）
  ↓
deepagents create_deep_agent（挂载 ToolPolicyMiddleware）
  ↓
LLM 决定调用工具 X, args=Y
  ↓
ToolPolicyMiddleware.after_model（工具执行前准入）
  │
  ├── A. 策略评估（PolicyEngine）
  │     → allow：保留 tool_call，进入工具执行阶段
  │     → deny：移除 tool_call，并追加拒绝 ToolMessage
  │     → approval：写 tb_tool_approval 后调用 LangGraph interrupt()
  │
  ├── B. HITL 恢复（Command(resume=...)）
  │     → approve：保留或按审批人编辑结果改写 tool_call
  │     → reject：移除 tool_call，并追加拒绝 ToolMessage
  │
  └── C. 输出修订后的 AIMessage / ToolMessage
        ↓
ToolPolicyMiddleware.wrap_tool_call（仅处理最终获准执行的工具）
  │
  ├── D. 工具指纹二次校验（FingerprintGuard）
  │     → 工具 schema 变了 → 返回错误 ToolMessage + 告警
  │
  ├── E. 输入脱敏（PIIMasker.mask_args）
  │
  ├── F. 执行工具（真正调 API/MCP）
  │
  └── G. 输出扫描（DLPScanner.scan_result）
        → 命中秘密/外发规则 → 截断或阻断
        → 输出回 LLM
```

关键约束：`interrupt_on` / `interrupt()` 的暂停点在 **模型产出 tool_call 后、工具真正执行前**。不要在 `wrap_tool_call` 中抛 `_ApprovalRequired` 并期待 deepagents 捕获；该阶段已经进入工具执行路径，异常只会变成运行失败。

### 3.2 组件清单

| 组件 | 位置 | 职责 |
|---|---|---|
| `ToolPolicyMiddleware` | `backend/app/app/middlewares/tool_policy.py` | 拦截当前 graph 内的 tool 调用，调用各子引擎；跨 subagent 必须显式注入或由工具 wrapper 兜底 |
| `PolicyEngine` | `backend/app/service/policy_engine.py` | 无状态策略求值 |
| `PolicyService` | `backend/app/service/policy_service.py` | 加载策略、缓存、CRUD |
| `ApprovalService` | `backend/app/service/approval_service.py` | 审批单生命周期 |
| `ApprovalOrchestrator` | `backend/app/service/approval_orchestrator.py` | SLA/升级/委托/破窗 |
| `FingerprintGuard` | `backend/app/service/tool_fingerprint.py` | 工具 schema 哈希校验 |
| `PIIMasker` | `backend/app/core/pii_masker.py` | 参数脱敏 |
| `DLPScanner` | `backend/app/core/dlp_scanner.py` | 输出扫描 |
| `NotificationDispatcher` | `backend/app/service/notifications.py` | 推送到 Slack/Email/Webhook |
| `AuditLog` | `backend/app/service/audit_log.py` | append-only 审计流 |

---

## 4. 核心数据模型

### 4.1 策略 `tb_app_tool_policy`

```python
class TbAppToolPolicy(Base):
    __tablename__ = "tb_app_tool_policy"
    __table_args__ = (
        UniqueConstraint("app_id", "tool_id", "priority",
                         name="uk_tb_app_tool_policy_app_tool_priority"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # null 表示适用所有工具
    # 'allow' | 'deny' | 'approval' | 'dry_run'
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # JSON：conditions schema 见 §4.5
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    # 'LOW' | 'MED' | 'HIGH' | null（null=依 risk scoring）
    risk_override: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # 'active' | 'shadow' | 'disabled'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # 关联 template_id（§11.3）
    template_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 策略版本号（§11.1）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 审计四列
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：
- `(app_id, tool_id, priority)` — 策略加载顺序
- `(app_id, status)` — 排除 disabled
- `(template_id)` — 模板同步影响面分析

### 4.2 策略版本 `tb_app_tool_policy_version`（§11.1）

```python
class TbAppToolPolicyVersion(Base):
    __tablename__ = "tb_app_tool_policy_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    policy_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)  # 整行 JSON
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

### 4.3 审批 `tb_tool_approval`

```python
class TbToolApproval(Base):
    __tablename__ = "tb_tool_approval"
    __table_args__ = (
        # 幂等键：同一 tool_call 在同一 run 和同一策略版本下至多一条 pending 审批单。
        # resume、客户端重试、LangGraph 恢复都会复用此约束，避免重复建单。
        UniqueConstraint("run_id", "tool_call_id", "policy_version",
                         name="uk_tb_tool_approval_run_call_policy"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 幂等来源
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 工具全限定名：'{source}:{mcp_server_id or "_"}:{tool_name}'，用于审计和前端显示
    qualified_tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments: Mapped[str] = mapped_column(Text, nullable=False)
    # 脱敏后的展示版本，给审批人看
    arguments_masked: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)  # LOW/MED/HIGH
    # 'pending' | 'approved' | 'rejected' | 'timeout' | 'cancelled' | 'escalated' | 'break_glass'
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requester_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 审批链当前层级
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 目标审批人列表（JSON array of user_id）
    current_approvers: Mapped[str] = mapped_column(Text, nullable=False)
    approver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approver_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 上下文快照：用户最近 N 条消息 + agent 当前 todo + skill 名，便于审批人判断
    context_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 预审批 token（§7.3）
    preapproval_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expire_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    escalated_from: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 前一级审批单 id
    # ApprovalResumeService 已 resume 时间戳；非空代表已恢复，幂等保护
    resumed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：`(status, expire_time)` / `(conversation_id, status)` / `(approver_id, status)` / `(preapproval_id)` / `(run_id, tool_call_id)`（幂等 lookup）。

### 4.4 预审批 `tb_tool_preapproval`（§7.3）

```python
class TbToolPreapproval(Base):
    __tablename__ = "tb_tool_preapproval"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tool_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 参数匹配模式 JSON：只有命中此模式的调用才走预审批
    arg_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'conversation' | 'user_day' | 'count'
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    remaining_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expire_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    granted_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    granted_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### 4.5 审批链配置 `tb_approval_chain`（§8.1）

```python
class TbApprovalChain(Base):
    __tablename__ = "tb_approval_chain"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # null=全局默认
    # 按风险等级触发不同链
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    # JSON array of {level, approver_type, approver_value, sla_seconds}
    # approver_type: 'user' | 'role' | 'user_group' | 'manager_of_requester'
    chain_config: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON：破窗规则
    break_glass_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

### 4.6 委托 `tb_approval_delegation`（§8.3）

```python
class TbApprovalDelegation(Base):
    __tablename__ = "tb_approval_delegation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    from_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    to_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # null=所有 app / 特定 app_id
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # active/revoked
```

### 4.7 工具指纹 `tb_tool_fingerprint`（§11.4）

```python
class TbToolFingerprint(Base):
    __tablename__ = "tb_tool_fingerprint"
    __table_args__ = (UniqueConstraint("tool_id", name="uk_tb_tool_fingerprint_tool"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tool_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # SHA256(tool_name + description + parameters_schema + api_config or mcp)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    last_reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_reviewed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 'trusted' | 'suspended' | 'pending_review'
    review_status: Mapped[str] = mapped_column(String(16), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

### 4.8 审计日志 `tb_policy_audit`（§13.1）

```python
class TbPolicyAudit(Base):
    __tablename__ = "tb_policy_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 'policy_evaluated' | 'approval_requested' | 'approval_decided' |
    # 'break_glass_used' | 'fingerprint_mismatch' | 'dlp_hit' | 'policy_changed'
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    app_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tool_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # decision / approval_id / policy_version etc.
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    # 前一条审计 id，形成链
    prev_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # HMAC(payload + prev_id)，append-only 防篡改
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

**约束**：
- 无 update，无 delete（触发器或应用层拒绝）
- 归档：超 90 天迁到冷存储
- 签名链让离线验证整条记录未被篡改

### 4.9 `app_config` 扩展

```jsonc
{
  "policy": {
    "enabled": true,
    "default_mode": "allow",          // 未命中策略时默认行为
    "approval_timeout_ms": 3600000,
    "risk_thresholds": {              // 风险分级阈值
      "auto_approve": "LOW",          // <= LOW 自动放行
      "require_approval": "MED"       // >= MED 需审批
    },
    "dry_run": false,                 // 全应用 dry-run
    "pii_masking": true,
    "dlp_scan": true
  }
}
```

---

## 5. 策略引擎（PolicyEngine）

### 5.1 Conditions Schema

```jsonc
{
  // 身份维度
  "user_groups":      ["7823...", "7824..."],
  "user_roles":       ["finance_admin"],
  "exclude_users":    ["9999..."],      // 黑名单

  // 参数维度
  "arg_match": {
    "to_email":  { "regex": ".*@external\\.com$" },
    "amount":    { "gt": 10000 },
    "sql":       { "contains_any": ["DELETE", "DROP", "TRUNCATE"] },
    "path":      { "glob": "/etc/**" }
  },

  // 网络维度（URL/域名）
  "url_match": {
    "host_allowlist": ["*.corp.com", "api.internal"],
    "host_denylist":  ["*.competitor.com"]
  },

  // 上下文维度
  "time_window": {
    "start_hour": 9, "end_hour": 18,
    "weekdays": [1, 2, 3, 4, 5],
    "timezone": "Asia/Shanghai"
  },
  "conversation_limit": {
    "max_calls_per_conversation": 5,
    "max_calls_per_user_day": 50
  },
  "tool_chain": {                       // 命中"危险工具组合"
    "preceded_by_any": ["export_data"]
  },

  // 工具输出维度（DLP）
  "output_contains_any_of_regex": ["SSN:\\d{3}-\\d{2}-\\d{4}"],

  // 租户 / 数据分类
  "tenant_id": "...",
  "data_classification_max": "confidential"
}
```

**匹配运算符**（`arg_match` / `url_match` 内）：

| 运算符 | 语义 | 示例 |
|---|---|---|
| `eq` / `ne` | 值相等 | `{"status": {"eq": "active"}}` |
| `gt` / `gte` / `lt` / `lte` | 数值 | `{"amount": {"gt": 10000}}` |
| `contains` / `contains_any` | 子串（单/多） | `{"sql": {"contains_any": ["DELETE"]}}` |
| `regex` | 正则 | `{"email": {"regex": ".*@ext\\.com"}}` |
| `glob` | wcmatch glob | `{"path": {"glob": "/etc/**"}}` |
| `in` / `not_in` | 列表 | `{"region": {"in": ["us", "eu"]}}` |
| `exists` | 字段存在 | `{"priority": {"exists": true}}` |

### 5.2 LLM 辅助策略（可选）

支持用自然语言表达策略，转为结构化求值：

```jsonc
{
  "llm_rule": {
    "prompt": "判断这封邮件是否在向竞争对手泄露客户信息",
    "model": "claude-haiku-4-5",
    "threshold": 0.7,       // LLM 返回 yes 概率阈值
    "timeout_ms": 2000
  }
}
```

运行时把 `tool_name` + `arguments` 渲染到模板，调 haiku/mini 模型。**默认关闭**（成本/延迟风险），仅对高风险工具启用。

### 5.3 求值算法

```python
def evaluate(
    self,
    policies: list[TbAppToolPolicy],
    ctx: PolicyContext,
) -> PolicyDecision:
    shadow_hits: list[PolicyDecision] = []
    for p in policies:
        if p.status == "disabled":
            continue
        cond = json.loads(p.conditions or "{}")
        if not self._match(cond, ctx):
            continue

        hit = PolicyDecision(
            mode=p.mode,
            policy_id=p.id,
            policy_version=p.version,
            reason=self._describe(cond),
            risk_level=p.risk_override,
        )

        if p.status == "shadow" or p.mode == "dry_run":
            shadow_hits.append(hit)
            continue  # shadow 不影响决策，仅记录审计

        # 命中即返回（优先级已经在 load 时按 priority 排序）
        self._audit.log_shadow_hits(shadow_hits)
        return hit

    self._audit.log_shadow_hits(shadow_hits)
    return PolicyDecision(mode=self._default_mode(ctx), policy_id=None,
                          reason="default", risk_level=None)
```

---

## 6. 风险分级（Risk Scoring）

### 6.1 分级来源

Risk 由**策略指定 `risk_override`**或**自动评分**得出，取 max：

```
risk_level(tool_call)
  = max(
      policy.risk_override if hit,
      tool.default_risk,               // 工具本身的风险标签（在 TbTool 新增 default_risk）
      arg_based_risk(arguments)        // 参数值启发式
    )
```

### 6.2 工具默认风险（`TbTool.default_risk`）

扩展现有 `TbTool` 表加一列 `default_risk: String(8)`，取值 `LOW/MED/HIGH`。例：

| 工具 | 建议默认风险 |
|---|---|
| `web_search` | LOW |
| `read_file` / `query_database_readonly` | LOW |
| `send_email_internal` | MED |
| `send_email_external` | HIGH |
| `execute_sql` | HIGH |
| `delete_file` / `drop_table` | HIGH |
| `call_payment_api` | HIGH |

### 6.3 参数启发式

简单规则（可扩展）：

```python
def arg_based_risk(tool_name: str, args: dict) -> str | None:
    if "amount" in args and args["amount"] > 10000:
        return "HIGH"
    sql = args.get("sql") or args.get("query") or ""
    if re.search(r"\b(DELETE|DROP|TRUNCATE|ALTER)\b", sql, re.I):
        return "HIGH"
    return None
```

### 6.4 阈值与模式映射

在 `app_config.policy.risk_thresholds` 里配置：

```
risk_level <= LOW  → allow（若无策略 deny 命中）
risk_level == MED  → approval（单级审批）
risk_level == HIGH → approval（多级审批链）
```

---

## 7. HITL 审批核心流程

### 7.1 生成调用-暂停-恢复

HITL 不通过工具执行阶段的异常触发，而是在 `after_model` 阶段检查 `AIMessage.tool_calls`：

1. LLM 产出一个或多个 `tool_call`。
2. `ToolPolicyMiddleware.after_model` 为每个 `tool_call` 构建 `PolicyContext` 并评估策略。
3. `deny`：从 `AIMessage.tool_calls` 移除该调用，并追加一条 `ToolMessage(status="error")` 告诉模型被拒绝。
4. `approval`：写入 `tb_tool_approval(status=pending)`，随后调用 LangGraph `interrupt()` 暂停 graph；checkpoint 保存暂停前 state。
5. 审批通过：`agent.invoke(Command(resume={"decisions": [...] }), config={"configurable": {"thread_id": ...}})`，middleware 保留或改写对应 `tool_call`。
6. 审批拒绝：middleware 移除对应 `tool_call`，追加拒绝 `ToolMessage`，工具不会执行。
7. `ApprovalOrchestrator` 独立负责 SLA 计时、通知派发、升级、委托，不参与同步工具执行。

`wrap_tool_call` 只处理已经通过 `after_model` 准入的工具调用，负责执行前审计、指纹二次校验、输出 DLP 扫描和执行后审计。

### 7.2 SSE 通信

审批过程中流事件：

| 事件 | 时机 |
|---|---|
| `tool_call_pending` | 写入审批单后 |
| `tool_call_escalated` | SLA 超时触发升级 |
| `tool_call_approved` | 审批通过（由后续流或新流送达） |
| `tool_call_rejected` | 审批拒绝 |
| `tool_call_timeout` | 最终超时 |
| `approval_pending`（流结束事件） | 原 SSE 在 interrupt 发生时结束，通知前端"此流已暂停、需等待审批" |

### 7.2.1 ApprovalResumeService（P2 执行语义闭环）

审批通过后**不要由审批 API 的 HTTP handler 同步调 `agent.astream(Command(resume=...))`**——长时工具执行、token 推送会阻塞审批 RESTful 返回。独立一个 `ApprovalResumeService`：

```
用户发消息 → ConversationService 启动 SSE 流
        │
        ├── ToolPolicyMiddleware.after_model 触发 interrupt()
        │     → 写 tb_tool_approval(status=pending)
        │     → 推 tool_call_pending / approval_pending 事件
        │     → 当前 SSE 流结束，HTTP 连接关闭
        │
审批人 approve / reject（REST）
        │
        ├── ApprovalService 更新 status + 触发 ApprovalResumeService.schedule(approval)
        │
ApprovalResumeService（工作队列 / 后台协程）
        │
        ├── 1. 按 thread_id 获取会话锁（见 long-session §I.8 的 advisory lock）
        ├── 2. 构造 Command(resume={"decisions": [...]})
        ├── 3. 用原 app 配置重建 agent（或从 _Prepared 缓存拿）
        ├── 4. agent.astream(Command(resume=...), config={"configurable": {"thread_id": ...}})
        ├── 5. 输出通道二选一：
        │       A. 写入 conversation message 表 +
        │          通过 WebSocket / SSE 新端点推给订阅此会话的前端（推荐，前端可关闭再重开）
        │       B. 仅落库，前端下次打开会话从历史消息读取
        └── 6. 写 `approval_resumed` 审计事件
```

**前端等待态协议**：

1. SSE 收到 `approval_pending` → 显示"审批中…"占位卡，原 SSE 端口可关
2. 前端订阅 `GET /api/v1/conversation/{id}/stream/subscribe`（WebSocket 或 SSE），只接收"审批恢复后"的后续 token
3. 用户可主动关闭再重开同会话，从消息历史恢复，不依赖 SSE 连接存活

**关键规则**：

- 绝不在审批 API 的请求生命周期内同步跑 agent；审批 API 只更新审批单 + 入队
- `ApprovalResumeService` 需要幂等：同一 approval_id 不能被恢复两次（数据库标记 `resumed_at` 非空即跳过）
- 进程重启：队列持久化（复用业务 DB 或 Redis），重启后 `SELECT ... WHERE status='approved' AND resumed_at IS NULL` 扫出继续跑
- 单会话同时只能有一个恢复任务在跑（按 thread_id 加锁）

### 7.3 预审批（Session Pre-approval）

**动机**：agent 执行一次"清理数据库旧记录"任务可能要 20 次 `delete_row` —— 审批 20 次不可行。

**方案**：审批通过时审批人勾选"approve for whole conversation" / "approve next 10 calls" / "approve for 1 hour"，写入 `tb_tool_preapproval`：

```python
class ApprovalScope(str, Enum):
    SINGLE = "single"              # 仅本次
    CONVERSATION = "conversation"  # 整个会话
    USER_DAY = "user_day"          # 本用户当天
    COUNT = "count"                # 未来 N 次（remaining_count）
```

下次同工具+同参数模式（`arg_pattern` 匹配，如 `{"table": "old_logs"}`）命中预审批 → 自动 allow，记审计日志但不再走 HITL。

**安全护栏**：
- 预审批仅能由**原本有权审批该调用**的审批人授予
- 最长有效期：`min(配置, 24h)`
- `scope=CONVERSATION` 随会话关闭失效
- 用户端可一键撤销自己会话内的所有预审批

### 7.4 破窗（Break-glass）

**动机**：生产事故，审批人不在；SRE 需要立即执行高风险操作。

**方案**：超级管理员角色 `break_glass_admin` 可在 UI "紧急放行" 按钮：

```
POST /api/v1/tool-approval/{id}/break-glass
body: { justification: "P0 incident INC-1234", ticket_url: "..." }
```

要求：
- 强制填写 `justification`（≥30 字）
- 关联工单 URL
- **双人确认**（实际实现可以要求另一个 break_glass_admin 30s 内二次点击确认）
- 事件以 `severity=critical` 推送到 §9 的所有通知渠道
- 审计日志 `event_type=break_glass_used`，管理员邮件自动接收
- 每周自动汇总破窗使用情况给合规审查

---

## 8. 审批人体系

### 8.1 审批链（Approval Chain）

单级（`LOW/MED`）或多级（`HIGH`）。配置示例（`tb_approval_chain.chain_config`）：

```jsonc
[
  {
    "level": 1,
    "approver_type": "manager_of_requester",  // 动态：发起人的直属经理
    "sla_seconds": 900                         // 15 分钟无响应升级
  },
  {
    "level": 2,
    "approver_type": "role",
    "approver_value": "finance_director",
    "sla_seconds": 1800
  },
  {
    "level": 3,
    "approver_type": "user_group",
    "approver_value": "cfo_office",
    "sla_seconds": 3600
  }
]
```

**approver_type** 支持：

| 类型 | 含义 |
|---|---|
| `user` | 指定用户 id |
| `role` | 指定角色 |
| `user_group` | 用户组（任一成员可批） |
| `manager_of_requester` | 发起人组织架构直属上级（依赖 `tb_user.manager_id`） |
| `app_admin` | 应用管理员 |

### 8.2 升级（Escalation）

`ApprovalOrchestrator` 定时扫：

```python
def tick(self) -> None:
    now = int(time.time() * 1000)
    pending = db.scalars(
        select(TbToolApproval)
        .where(TbToolApproval.status == "pending",
               TbToolApproval.expire_time < now)
    ).all()

    for approval in pending:
        chain = self._load_chain(approval.app_id, approval.risk_level)
        next_level = approval.current_level + 1
        next_step = next((s for s in chain if s["level"] == next_level), None)

        if next_step:
            # 升级：创建新审批单，旧单 status=escalated
            self._escalate(approval, next_step)
        else:
            # 终极 SLA 过 → timeout
            self._timeout(approval)
```

### 8.3 委托（Delegation）

审批人休假时：

```
POST /api/v1/approval-delegation
body: {
  "to_user_id": "...",
  "start_time": 1729500000000,
  "end_time": 1729700000000,
  "app_id": null,  // 或指定 app
  "reason": "年假"
}
```

`ApprovalService.resolve_approvers()` 判断：若在委托期内，把目标审批人替换为被委托人。委托链最多 1 跳（防环）。

### 8.4 防自审

- `requester_id != approver_id`（硬约束）
- `requester_id not in resolve_approvers()`（即使在组/角色里也被过滤）
- 委托场景下：若被委托人原本也是发起人（罕见），回退到下一级

---

## 9. 通知与外部集成

### 9.1 通知渠道

`NotificationDispatcher` 抽象：

```python
class NotificationBackend(Protocol):
    def send(self, event: NotificationEvent) -> None: ...

class SlackBackend(NotificationBackend): ...       # webhook
class EmailBackend(NotificationBackend): ...       # SMTP
class WebhookBackend(NotificationBackend): ...     # 通用 JSON POST
class EasyAIInboxBackend(NotificationBackend): ... # 站内消息
```

配置（`app_config.policy.notifications`）：

```jsonc
{
  "channels": [
    { "type": "slack", "webhook_url": "https://hooks.slack.com/...",
      "events": ["pending", "escalated", "break_glass"] },
    { "type": "email", "to": ["sec@corp.com"], "events": ["break_glass"] },
    { "type": "webhook", "url": "https://jira.corp.com/api/approval",
      "events": ["pending"], "secret_ref": "JIRA_WEBHOOK_SECRET" }
  ]
}
```

### 9.2 审批卡片示例（Slack Block Kit）

```
[工具审批请求]
请求人: 张三
应用:   客户运营助手
工具:   send_email_external
参数:   to=...@competitor.com (脱敏)
风险:   HIGH
发起:   3 分钟前 · 到期 12 分钟
[ 通过 ] [ 拒绝 ] [ 查看详情 ]
```

按钮通过 Slack Interactive Action → 回调 `/api/v1/tool-approval/{id}/slack-callback`（需 HMAC 验签）。

### 9.3 外部工作流集成

Webhook 出站后，外部系统（Jira/ServiceNow）可创建工单、走自己的审批流，完成后回调：

```
POST /api/v1/tool-approval/{id}/external-decision
headers: X-Signature: HMAC
body: { decision: "approved", approver_external_id: "...", evidence: "..." }
```

---

## 10. 输入输出安全

### 10.1 PIIMasker

调用前脱敏参数（仅用于展示给审批人 + 写审计），**实际工具执行仍用原文**。

```python
class PIIMasker:
    PATTERNS = {
        "email":  r"([\w.+-]+)@([\w-]+\.)+[\w-]{2,}",
        "phone":  r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "idcard": r"[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]",
        "ip":     r"\b(\d{1,3}\.){3}\d{1,3}\b",
    }
    def mask(self, text: str) -> str: ...
```

`tb_tool_approval.arguments_masked` 存脱敏版；审批 UI 默认显示脱敏版，点"查看原文"需二次鉴权（如输入密码）+ 审计。

### 10.2 DLP 输出扫描

工具返回后扫描 `result`，匹配以下模式触发动作：

| 类型 | 动作 |
|---|---|
| API Key / AWS Key 泄漏 | 截断并抛错，审计 `dlp_hit` |
| 客户名单 | 记录审计，允许继续（可配为阻断） |
| 含超出 `data_classification_max` 的分类标签 | 阻断 |

规则集可由安全团队在 `tb_dlp_rule` 维护（略，类似 policy 表结构）。

### 10.3 Prompt Injection 防御

工具返回的文本如果包含"忽略之前的指令..."之类指令 → 用分类器检测（轻量正则+LLM 判）→ 命中则包装成：

```
<tool_output>
[⚠️ 此工具返回被检测为可能包含指令注入，已隔离]
原始内容摘要（前 500 字）: ...
</tool_output>
```

避免 agent 被外部工具诱导。

---

## 11. 策略治理

### 11.1 版本与变更审计

- 每次 `UPDATE/INSERT/DELETE` 策略 → 原记录 snapshot 入 `tb_app_tool_policy_version`
- 策略详情页提供"历史变更"Tab，支持 diff 查看
- 可一键回滚到前一版本

### 11.2 Dry-run（影子模式）

- 新策略可发布为 `status=shadow`：匹配时**只记录不阻断**
- Dashboard 展示"shadow 命中数 / 预计阻断数 / 预计审批数"
- 评估符合预期后切 `status=active`
- 整 app `app_config.policy.dry_run=true` 全局影子（仅记录）

### 11.3 策略模板（`tb_policy_template`）

```python
class TbPolicyTemplate(Base):
    id: BigInteger PK
    name: String(255)           # "外发邮件必审"
    category: String(64)        # "email" / "sql" / "finance"
    conditions: Text            # JSON
    default_mode: String(16)
    default_risk: String(8)
    published_by: BigInteger
    usage_count: Integer        # 被应用次数
    create_*/update_*
```

应用管理员从模板库一键导入到本 app，后续模板更新时可选择"同步"。

### 11.4 工具指纹（FingerprintGuard）

**防护场景**：MCP 服务器被替换、API 工具的 schema 被偷改 → agent 调用变种工具但策略还以为是旧工具。

```python
def compute_fingerprint(tool: TbTool) -> str:
    payload = {
        "name": tool.tool_name,
        "desc": tool.description,
        "params": tool.parameters,
        "source": tool.source,
        "endpoint": tool.api_config or tool.mcp_server_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
```

运行时：
- 每次 `_build_tool` 计算指纹 → 查 `tb_tool_fingerprint`
- 不匹配且 `review_status != trusted` → 整个工具挂起（deny 全部调用）
- 管理员在"工具评审"页看到 diff，点"信任新版本"更新指纹

### 11.5 策略变更冷却

关键策略（`deny` 财务/安全相关）修改时：
- 要求 `change_reason`（非空）
- 二人核准（CR 式：另一个管理员点"Approve change"才生效）
- 生效前 10 分钟广播给订阅者

---

## 12. 多租户与隔离

- 所有表加 `tenant_id: BigInteger`（或通过 `app_id → tenant_id` 派生）
- `PolicyEngine.evaluate` 自动注入 `ctx.tenant_id`，策略的 `tenant_id` 条件匹配
- 审批人 / 破窗权限按租户隔离
- 审计日志按租户分区（方便合规导出）
- 跨租户调用（若存在）视为 HIGH 风险强制审批

---

## 13. 可观测性与告警

### 13.1 审计日志（WORM）

见 §4.8。所有策略相关事件都入 `tb_policy_audit`：

| event_type | 触发时机 |
|---|---|
| `policy_evaluated` | 每次 evaluate 调用 |
| `approval_requested` | 创建审批单 |
| `approval_decided` | approve/reject/timeout |
| `break_glass_used` | §7.4 |
| `fingerprint_mismatch` | §11.4 |
| `dlp_hit` | §10.2 |
| `policy_changed` | CRUD policy |
| `delegation_activated` | §8.3 |
| `preapproval_granted` | §7.3 |

### 13.2 指标（Prometheus）

| 指标 | 说明 |
|---|---|
| `policy_decision_total{app,mode,risk}` | 按模式分布 |
| `approval_duration_seconds{risk}` | histogram |
| `approval_pending_gauge` | 当前 pending 数（压力指标） |
| `approval_timeout_total` | 超时计数（SLA 问题信号） |
| `break_glass_total{app,actor}` | 破窗次数（合规看板） |
| `fingerprint_mismatch_total` | 越权/供应链风险信号 |
| `dlp_hit_total{rule_id,action}` | 数据泄漏拦截 |
| `policy_eval_latency_ms` | 评估延迟（性能） |

### 13.3 告警规则示例

- `break_glass_total > 5 in 1h` → PagerDuty
- `fingerprint_mismatch_total > 0 in 5m` → 安全团队即时告警
- `approval_pending_gauge > 50 AND approval_duration_p50 > 30min` → 审批人异常（休假未委托？）
- `dlp_hit_total{action=blocked} > 10 in 10m` → agent 可能在尝试泄漏

### 13.4 合规导出

按租户 / 时间段导出：

```
GET /api/v1/audit/export?tenant_id=...&start=...&end=...&format=csv
```

包含审计链签名，第三方审计可离线校验完整性。

---

## 14. API 设计

### 14.1 策略管理

```
GET    /api/v1/app/{app_id}/tool-policy/page
POST   /api/v1/app/{app_id}/tool-policy
PUT    /api/v1/app/{app_id}/tool-policy/{id}
DELETE /api/v1/app/{app_id}/tool-policy/{id}
POST   /api/v1/app/{app_id}/tool-policy/reorder
POST   /api/v1/app/{app_id}/tool-policy/{id}/shadow      # 切换 active/shadow/disabled
GET    /api/v1/app/{app_id}/tool-policy/{id}/versions
POST   /api/v1/app/{app_id}/tool-policy/{id}/rollback    # body: { to_version: N }
GET    /api/v1/policy-template/page
POST   /api/v1/app/{app_id}/tool-policy/from-template    # body: { template_id }
```

### 14.2 审批

```
GET    /api/v1/tool-approval/page                        # 待办/全部/已完成
GET    /api/v1/tool-approval/{id}
POST   /api/v1/tool-approval/{id}/approve
POST   /api/v1/tool-approval/{id}/reject
POST   /api/v1/tool-approval/{id}/cancel                 # 发起人取消
POST   /api/v1/tool-approval/{id}/break-glass            # 破窗
POST   /api/v1/tool-approval/{id}/escalate-now           # 发起人可请求立即升级
POST   /api/v1/tool-approval/{id}/slack-callback
POST   /api/v1/tool-approval/{id}/external-decision
```

审批请求体：

```python
class ApprovalDecisionReq(BaseModel):
    comment: str | None = None
    preapproval: PreapprovalReq | None = None   # 附带预审批

class PreapprovalReq(BaseModel):
    scope: Literal["single", "conversation", "user_day", "count"]
    remaining_count: int | None = None
    arg_pattern: dict[str, Any] | None = None
    duration_ms: int | None = None
```

### 14.3 委托与破窗

```
POST   /api/v1/approval-delegation
GET    /api/v1/approval-delegation/my
DELETE /api/v1/approval-delegation/{id}

GET    /api/v1/break-glass/audit?period=7d             # 合规看板
```

### 14.4 工具指纹

```
GET    /api/v1/tool-fingerprint/page                   # 待评审列表
POST   /api/v1/tool-fingerprint/{tool_id}/trust        # body: { reviewed_at_version }
POST   /api/v1/tool-fingerprint/{tool_id}/suspend
```

### 14.5 审计

```
GET    /api/v1/audit/page?event_type=...&tenant_id=...
GET    /api/v1/audit/export?format=csv|json
POST   /api/v1/audit/verify                            # 校验签名链完整性
```

---

## 15. 前端审批工作台

### 15.1 "我的待办"页

- 筛选：风险等级 / app / 时间
- 卡片内容：请求人头像、工具名+高亮、参数预览（脱敏）、风险标签、剩余 SLA 倒计时
- 快捷动作：通过 / 拒绝 / 查看详情

### 15.2 审批详情页

模块化展示：

1. **基本信息**：工具 / 参数 / 发起人 / 应用 / 风险等级 / 命中策略
2. **上下文快照**：用户最近 3 条消息 + agent 当前 todo（`context_snapshot` 反序列化）
3. **历史相似调用**：该用户近 7 天类似调用通过率
4. **参数原文**：默认脱敏，点"查看原文"二次鉴权 + 审计
5. **决定**：通过 / 拒绝，可附预审批、评论

### 15.3 会话中的等待态

Agent 暂停时前端显示：

```
⏸ 等待审批中…
  工具: send_email_external
  审批人: @李四（经理）
  预计: 15 分钟内
  [ 取消调用 ] [ 催促 ]
```

"催促" = 调 `/escalate-now`，把当前审批单立刻升级到下一级。

---

## 16. 运行时改造

### 16.1 `AgentApp._prepare` 新增

```python
def _prepare(self, db, req, request_type):
    # ... 现有逻辑 ...

    if self._policy_enabled(app_config):
        policy_middleware = ToolPolicyMiddleware(
            app_id=app.id,
            policy_service=self._policy_service,
            approval_service=self._approval_service,
            pii_masker=self._pii_masker,
            dlp_scanner=self._dlp_scanner,
            fingerprint_guard=self._fingerprint_guard,
            tool_registry=self._tool_registry,
            run_ctx=run_ctx,
        )
        agent_kwargs.setdefault("middleware", []).insert(0, policy_middleware)

        # 关键：主 agent middleware 不会自动覆盖 deepagents 自动创建的
        # general-purpose subagent。必须显式提供同名 spec，阻止 deepagents
        # 注入未治理的默认 general-purpose。
        subagents = self._build_policy_managed_subagents(
            app_config=app_config,
            policy_middleware=policy_middleware,
            tools=tools,
            model=model,
        )
        agent_kwargs["subagents"] = subagents

    # 本设计与 deepagents 原生 interrupt_on 互斥：
    # 不得设置 agent_kwargs["interrupt_on"]，HITL 全部由 ToolPolicyMiddleware.after_model 驱动。
    assert "interrupt_on" not in agent_kwargs

    # ... Part I 的 checkpointer 挂载也在这里 ...
```

`_build_policy_managed_subagents` 必须至少生成一个 `name="general-purpose"` 的声明式 subagent，并把 `ToolPolicyMiddleware` 放入该 subagent 的 `middleware`。这是为了覆盖 deepagents 的默认行为：如果调用方不提供同名 subagent，deepagents 会自动插入一个没有 easy-ai 企业治理的默认 `general-purpose`。

注：
- 对 `task` 工具本身的治理需要单独策略条目（`tool_source='builtin'`, `tool_name='task'`），避免 LLM 用 `task` 转调高权限工具绕过策略。
- `CompiledSubAgent` / `AsyncSubAgent` 不保证继承 easy-ai 的 middleware；默认禁止接入高权限工具，或要求其 runnable/远端服务自带同等治理。
- 所有 API/MCP/Shell/Filesystem 工具在 `_build_tools` 阶段还必须包一层 policy-aware wrapper，作为跨 agent 的最终兜底。middleware 是交互治理入口，wrapper 是执行边界。
- `ApprovalService.create_pending` 的 `run_id / tool_call_id` 由 `ToolCallRequest` 提供，是本设计幂等的核心依据（见 §4.3）。

### 16.2 `ToolPolicyMiddleware.wrap_tool_call`

`ToolPolicyMiddleware` 分两段实现：`after_model` 做准入与 HITL，`wrap_tool_call` 做最终执行治理。

### 16.2.1 `ToolPolicyMiddleware.after_model`

```python
def after_model(self, state, runtime):
    last_ai = self._latest_ai_message(state)
    if not last_ai or not last_ai.tool_calls:
        return None

    revised_tool_calls = []
    artificial_tool_messages = []
    approval_requests = []

    for tool_call in last_ai.tool_calls:
        ctx = self._build_policy_context(tool_call)
        decision = self._policy_service.evaluate(ctx)
        self._audit.log("policy_evaluated", ctx, decision)

        if decision.mode == "deny":
            artificial_tool_messages.append(self._denied_message(tool_call, decision))
            continue

        risk = self._risk_scorer.score(ctx, decision)
        if decision.mode == "approval" or risk >= self._risk_thresholds.require_approval:
            # 幂等键：(run_id, tool_call_id, policy_version)
            # LangGraph resume / 客户端重试会多次走到这里；必须复用已存在的 pending 审批单
            approval = self._approval_service.get_or_create_pending(
                run_id=self._run_ctx.run_id,
                tool_call_id=tool_call["id"],
                policy_version=decision.policy_version,
                ctx=ctx, decision=decision, risk=risk,
            )
            approval_requests.append(self._to_action_request(tool_call, approval))
            continue

        revised_tool_calls.append(tool_call)

    if approval_requests:
        decisions = interrupt({"type": "tool_approval", "actions": approval_requests})
        for decision in decisions["decisions"]:
            if decision["type"] == "approve":
                revised_tool_calls.append(self._approved_tool_call(decision))
            elif decision["type"] == "edit":
                revised_tool_calls.append(self._edited_tool_call(decision))
            else:
                artificial_tool_messages.append(self._rejected_message(decision))

    last_ai.tool_calls = revised_tool_calls
    return {"messages": [last_ai, *artificial_tool_messages]}
```

### 16.2.2 `ToolPolicyMiddleware.wrap_tool_call`

```python
async def awrap_tool_call(self, request, call_next):
    tool_name = request.tool.name
    args = request.args

    # 1. 指纹
    if not self._fingerprint_guard.verify(tool_name):
        return ToolMessage(content=f"tool {tool_name} suspended: fingerprint mismatch")

    # 2. 构建上下文。tool_name 不是全局唯一，必须带 source/server/tool_id。
    ctx = PolicyContext(
        user_id=self._run_ctx.user_id,
        user_groups=self._user_groups(),
        tool_id=self._tool_registry.id_for(request.tool),
        tool_source=self._tool_registry.source_for(request.tool),
        mcp_server_id=self._tool_registry.mcp_server_id_for(request.tool),
        tool_name=tool_name,
        qualified_tool_name=self._tool_registry.qualified_name_for(request.tool),
        arguments=args,
        now_ms=int(time.time() * 1000),
        conversation_id=self._run_ctx.conversation_id,
        tenant_id=self._run_ctx.tenant_id,
    )

    self._audit.log("tool_execution_started", ctx)
    result = await call_next(request)
    self._audit.log("tool_execution_finished", ctx, result)
    return self._scan_output(tool_name, result)
```

---

## 17. 兼容与回滚

- `app_config.policy.enabled=false`（默认） → 不挂 `ToolPolicyMiddleware`，不设 `interrupt_on`
- 策略表空 + 默认 allow → 行为与现状一致
- `dry_run=true` → 所有策略命中只审计不阻断
- 回滚：关 flag 即可；审批 / 审计记录保留

**灰度路径**：

1. 策略管理后端上线，全部 `dry_run`
2. 一两个低风险 app 开启 `active` 观察 1 周
3. 逐步在关键 app 开启
4. HITL 流程在 checkpointer 灰度完成后再接

---

## 18. 测试要点

| 场景 | 预期 |
|---|---|
| 无策略 | 默认 allow，行为与重构前一致 |
| `deny` 命中 | 抛 FORBIDDEN，agent 收到错误 ToolMessage |
| `approval` + 通过 | graph 恢复，继续流 |
| `approval` + 拒绝 | agent 收到拒绝 ToolMessage，可换策略 |
| `approval` + 超时 | 按链升级或最终 timeout |
| 升级链 level 2 通过 | graph 恢复 |
| 破窗 | 需 justification + 双人 + 审计 + 通知全渠道 |
| 破窗次数触发告警 | Prometheus 指标 + PagerDuty |
| 预审批 conversation scope | 同会话内再调无需再审 |
| 预审批跨会话 | 失效 |
| 委托期内 | 审批单自动指向被委托人 |
| 委托到期 | 回到原审批人 |
| 自审 | FORBIDDEN |
| 指纹不匹配 | 工具挂起，deny 全部调用 |
| 指纹确认信任 | 后续 allow |
| DLP 命中 | 截断输出 + 审计 |
| PII 脱敏 | 审批 UI 显示占位符，查看原文触发二次鉴权 |
| Dry-run 策略 | 命中仅记录，不阻断 |
| 策略回滚 | 新版本替换，审计链续上 |
| `arg_match` 各运算符 | 各覆盖 |
| `time_window` 跨时区 | 正确 |
| 多租户隔离 | 跨租户请求被 deny |
| 审计签名链 | 离线可验证完整性 |
| 并发同 thread_id | 按长会话锁排队 |
| LLM 辅助策略超时 | 降级为 `approval`（fail-safe） |

---

## 19. 分期落地

| 阶段 | 范围 | 依赖 |
|---|---|---|
| **P0** | 策略 CRUD + `deny`/`allow` + 指纹守护 + 审计日志（WORM） | 无 |
| **P1** | 风险分级 + 通知 + 脱敏 + DLP 输出扫描 + Dry-run | P0 |
| **P2** | HITL 审批（approval 模式）+ 审批链 + SSE 等待态 | long-session-design.md 的 checkpointer |
| **P3** | 升级 + 委托 + 预审批 + 破窗 | P2 |
| **P4** | 模板库 + 版本回滚 + 外部工作流集成（Webhook/Slack） | P2 |
| **P5** | LLM 辅助策略 + 合规导出 + Prometheus 大盘 + 告警 | P1-P4 |

P0/P1 可独立上线，纯同步决策不依赖长会话；P2 起依赖 checkpointer。

---

## 20. 风险与未决

1. **LLM 辅助策略的成本/延迟**：需在 P5 前做预算评估；默认关闭，明确白名单才启用。
2. **审批链配置的复杂度**：初期先提供 3-4 个预设模板（单级 / 两级 / 跨部门），避免自由 DSL 过度工程。
3. **破窗审计的组织响应**：需要与合规团队约定每周复盘机制，否则破窗会变成"默认路径"。
4. **指纹对合法升级的阻塞**：工具版本化升级时需管理员主动"信任新版本"，增加了运维步骤；文档和告警必须清晰，否则会误判为故障。
5. **跨服务一致性**：多副本部署下的 `ApprovalOrchestrator` 定时扫需要分布式锁（PG advisory lock 或 Redis SETNX），不能并行触发升级。
6. **预审批的滥用风险**：如用户批准"approve for conversation"后 agent 被诱导做大量破坏性调用 → 建议对每种 scope 设置硬上限（如 `count` 最大 20）。

---

**相关文档**

- `long-session-design.md` — checkpointer 与长会话（HITL 硬依赖）
- `skill-management-design.md` — 技能与工具的关系
- `tool-management-design.md` — 工具基础定义
- `observability-design.md` — 监控总体架构
