# Skill 演化与成长体系详细设计

> 本文档是 `skill-management-design.md` 的进阶篇。已有的 Skill 实现只覆盖"基础 CRUD + 工具绑定 + 版本快照"，本设计补齐 harness agent 所需的**长期演化成长能力**：使用遥测、评估闭环、变体实验、自动改进、市场协作、依赖组合、个性化、治理与观测。

---

## 1. 功能概述

### 1.1 为什么现有 Skill 不够

当前 `TbSkill` / `TbSkillVersion` / `TbSkillTool` / `TbAppSkill` 支持：
- 写 instruction + 绑定工具 + 发布版本
- 应用勾选使用
- 通过 deepagents `SkillsMiddleware` 以 `SKILL.md` 形式做基础注入和 progressive disclosure

缺的是：**Skill 一旦发布就静态不变**。企业级 harness agent 要求 skill 能像生产系统一样随使用**自己长出来**：

1. **看得见使用**：谁用、用在哪、效果如何
2. **测得出质量**：每次改动都过回归，坏改动拦在门口
3. **跑得起实验**：多变体并行、数据说话再晋升
4. **学得到教训**：失败自动成为下一版改进的线索
5. **可以继承和分化**：团队定制版、用户个性版、语言版
6. **敢交给业务方**：有评审 / 发布 / 回滚，不靠拍脑袋上线

### 1.2 目标

| 能力 | 本质 |
|---|---|
| 生命周期管理 | `draft → reviewing → shadow → canary → active → deprecated` |
| 使用遥测 | 每次调用落库，形成"这个 skill 好不好用"的数据 |
| 评估闭环 | 每个 skill 有 eval 集合，修改触发回归 |
| 变体实验 | 同名 skill 跑多个 variant，按流量比例分配 |
| 自动改进 | 基于失败分析自动产出下一版 instruction 草案 |
| 组合依赖 | skill A 引用 skill B；包级发布 |
| 个性化 | 团队/用户可 fork 覆盖 |
| 市场协作 | 发现、fork、评论、星标 |
| 安全治理 | 内容扫描、签名、审批、审计 |
| 性能观测 | token 成本、延迟、命中率大盘 |

### 1.3 与已有设计的边界

| 设计 | 关系 |
|---|---|
| `skill-management-design.md` | 基础 CRUD、页面结构、工具绑定 —— 保持不变，本设计增量 |
| `long-session-design.md` | 反馈闭环的 `tb_message_feedback` 是本设计的重要遥测源 |
| `tool-approval-and-acl-design.md` | Skill 使用受策略守护；发布 skill 可走 tool-policy 的审批模型 |
| `agent-memory-design.md` | Memory 是"知道什么"，Skill 是"怎么做"；本设计可借鉴 memory 的 pending/confirm 模式 |
| `observability-design.md` | Skill 遥测上报 Langfuse + Prometheus |

运行上下文约束：运行期编译 skill、记录 usage、做 activation 归因时，统一使用 `tool-approval-and-acl-design.md` 中定义的 `AgentRunContext`；不要假设现有 `RequestContext` 已包含 `conversation_id`、`tenant_id` 或团队信息。

deepagents 边界约束：原生 `SkillsMiddleware` 只负责扫描 source 下的 `SKILL.md`、解析 frontmatter、把 skill 名称/描述/path 注入 prompt，并让模型按需 `read_file`。依赖解析、版本约束、A/B 选择、个性化覆盖、activation 归因和遥测都不是 deepagents 原生能力，必须由 easy-ai 的 `SkillCompiler`、工具 wrapper 和观测层实现。

---

## 2. 核心抽象：Skill 成长飞轮

```
                        ┌─────────────────┐
                        │  Skill Author    │
                        │  / Team Admin    │
                        └─────────┬────────┘
                                  │ 创建 / 编辑
                                  ▼
        ┌──────────────────────────────────────────────┐
        │  生命周期：draft → reviewing → shadow →      │
        │           canary → active → deprecated       │
        └──────────┬────────────────────┬──────────────┘
                   │                    │
                   ▼                    │
        ┌──────────────────┐            │
        │  Eval Harness    │            │
        │  （§5）          │            │
        └────────┬─────────┘            │
                 │ 回归通过才能晋升      │
                 ▼                      ▼
        ┌──────────────────────────────────────────┐
        │        Agent 运行时调用 skill             │
        │  （SkillsMiddleware 注入 SKILL.md）      │
        └──────────┬───────────────────────────────┘
                   │
                   ▼
        ┌──────────────────────────────────────────┐
        │   Telemetry（§4）:                        │
        │   - tb_skill_usage                        │
        │   - 关联 tb_message_feedback              │
        │   - 关联 Langfuse trace                   │
        └──────────┬───────────────────────────────┘
                   │ 失败 / 差评样本聚合
                   ▼
        ┌──────────────────────────────────────────┐
        │   Evolution（§6）:                        │
        │   - LLM 分析失败 → 候选改进 proposal     │
        │   - A/B 变体（§7）跑对比实验             │
        │   - 胜出 → 晋升新版本                    │
        └──────────┬───────────────────────────────┘
                   └──────────────────→ 回到 Skill Author 审核
```

---

## 3. 数据模型

### 3.1 状态扩展 `tb_skill.lifecycle_status`

给现有 `TbSkill` 加列（状态机见 §4）：

数据库约束原则：本设计只新增业务列、唯一约束和查询索引，不新增数据库外键约束；依赖完整性由 service 层校验和审计保障。

```python
# 已有的 skill_status 保留（enabled/disabled 的粗粒度开关）
# 新增更细粒度的生命周期
lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
# 'draft' | 'reviewing' | 'shadow' | 'canary' | 'active' | 'deprecated'

# 所属空间：作者 / 团队 / 组织
owner_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
# 'user' | 'team' | 'org' | 'marketplace'
owner_id:   Mapped[int] = mapped_column(BigInteger, nullable=False)
tenant_id:  Mapped[int | None] = mapped_column(BigInteger, nullable=True)

# 市场 / 发现维度
tags:         Mapped[str | None] = mapped_column(String(512), nullable=True)  # JSON array
locale:       Mapped[str]        = mapped_column(String(16), nullable=False, default="zh-CN")
visibility:   Mapped[str]        = mapped_column(String(16), nullable=False, default="private")
# 'private' | 'team' | 'org' | 'public'
stars_count:  Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
usage_count:  Mapped[int]        = mapped_column(Integer, nullable=False, default=0)

# 签名（防篡改）：SHA256(instruction + tools_hash + version)
signature: Mapped[str | None] = mapped_column(String(64), nullable=True)

# 来源追溯
forked_from_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
forked_from_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
```

### 3.2 变体 `tb_skill_variant`（§7）

同一 skill 可以有多个并行变体参与 A/B：

```python
class TbSkillVariant(Base):
    __tablename__ = "tb_skill_variant"
    __table_args__ = (
        UniqueConstraint("skill_id", "variant_key",
                         name="uk_tb_skill_variant_skill_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 'control' | 'v1' | 'v2' 等
    variant_key: Mapped[str] = mapped_column(String(32), nullable=False)
    # 此变体的完整 instruction
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    # 绑定工具（可不同于主 skill）。JSON list of tool_id。null=继承主 skill
    tool_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 参与分流比例 0-100
    traffic_weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 'draft' | 'shadow' | 'canary' | 'winner' | 'archived'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    # 来源：'human'（人工写）| 'auto_proposal'（§6 自动产出）
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="human")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：`(skill_id, status)` / `(skill_id, traffic_weight)`。

### 3.3 使用遥测 `tb_skill_usage`（§4）

遥测分两层，避免高频 app 因 injected-only 记录爆表：
- `activated` 事件全量记录。
- `injected-only` 事件默认按 app/skill/run 聚合或采样（默认 10%），只有调试期可全量开启。
- 每次 `agent_run` 保存本次 skill snapshot（skill_id、version、variant_key、hash），用于追溯；不要求每个注入 skill 每轮都落明细。

明细表结构：

```python
class TbSkillUsage(Base):
    __tablename__ = "tb_skill_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    variant_key: Mapped[str] = mapped_column(String(32), nullable=False, default="control")
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 关联 AgentRunContext.run_id，用于按运行聚合、排重、以及和 snapshot 表关联
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 采样元数据：None=全量（activated 事件必填 None）；否则 sample_rate ∈ (0,1]，
    # sample_weight = 1 / sample_rate 用于无偏聚合
    sample_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # 'injected'（注入但 agent 没实际引用）| 'activated'（agent 实际用到 skill 里的工具/步骤）
    # 通过 prompt 注入 + 是否触发工具调用 + 是否关联 trace span 判断
    activation: Mapped[str] = mapped_column(String(16), nullable=False, default="injected")
    # 归因来源：'skill_ref'（模型引用）| 'exclusive_tool'（独占工具命中）|
    # 'shared_tool'（多 skill 共享工具，需要 multi attribution）| 'injected_only'
    activation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 同时命中多个 skill 时的候选 skill_ids（JSON list），主 skill_id 取最高权重
    candidate_skill_ids: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # SkillCompiler 注入时生成的 skill 内容 hash，便于追溯当时到底用的哪个变体
    skill_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0/1/null
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_injected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 出错时的简短摘要
    error_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

索引：
- `(skill_id, create_time)` — 按 skill 时间线
- `(skill_id, variant_key, create_time)` — 变体对比
- `(app_id, skill_id)` — 应用视角
- `(conversation_id)` — 会话级关联

**分区要求**：P1 上线即按 `create_time` 月度分区或提供等价归档机制；禁止在高频生产 app 上无分区全量写 injected-only 事件。

### 3.3.1 Agent 运行级 snapshot `tb_agent_run_skill_snapshot`

`tb_skill_usage` 是"事件明细（可能采样）"；要想无损追溯"某次运行具体注入了哪些 skill"，必须有一张**每运行一条**的 snapshot 表：

```python
class TbAgentRunSkillSnapshot(Base):
    __tablename__ = "tb_agent_run_skill_snapshot"
    __table_args__ = (
        UniqueConstraint("run_id", name="uk_tb_agent_run_skill_snapshot_run"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # JSON list: [{skill_id, variant_key, version, skill_hash, tool_ids, file_path}]
    skills_json: Mapped[str] = mapped_column(Text, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

运行时写入时机：`SkillCompiler.compile()` 返回后一次性落盘（一次 agent_run 一条）。A/B 归因、failure 聚类都**先查 snapshot 定位真实注入集合**，再关联 usage 明细。

### 3.3.2 日聚合 `tb_skill_usage_daily`

高频 app 按天滚动聚合，给健康度大盘和 A/B 指标用，避免每次查询全扫 `tb_skill_usage`：

```python
class TbSkillUsageDaily(Base):
    __tablename__ = "tb_skill_usage_daily"
    __table_args__ = (
        UniqueConstraint("skill_id", "variant_key", "app_id", "date_key",
                         name="uk_tb_skill_usage_daily_sk_var_app_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    variant_key: Mapped[str] = mapped_column(String(32), nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date_key: Mapped[int] = mapped_column(Integer, nullable=False)  # YYYYMMDD
    # 以下指标都用 sample_weight 加权求和，保证采样后依然无偏
    injected_weighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    activated_weighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    success_weighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fail_weighted: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tool_calls_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tokens_injected_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    latency_ms_sum: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    runs_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

由后台任务 `SkillUsageAggregator` 每小时增量 upsert（基于 snapshot + usage 明细）。

### 3.4 评估 `tb_skill_eval_case` / `tb_skill_eval_run`（§5）

```python
class TbSkillEvalCase(Base):
    __tablename__ = "tb_skill_eval_case"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 输入：用户消息 + 可选上下文
    input_messages: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    # 期望输出 / 断言
    assertions: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON：{
    #   "must_call_tools": ["search_db"],
    #   "must_not_call_tools": ["send_email"],
    #   "output_regex": ["^(是|否)"],
    #   "output_json_schema": {...},
    #   "llm_judge": {"criteria": "...", "model": "haiku", "threshold": 0.7}
    # }
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'unit'（单步） | 'integration'（多轮） | 'safety'（安全边界）
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    # 'low' | 'normal' | 'high' | 'critical'  —— critical 失败直接拦门
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    create_time/update_time/create_user/update_user
```

```python
class TbSkillEvalRun(Base):
    __tablename__ = "tb_skill_eval_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    variant_key: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'manual' | 'ci'（发布前自动）| 'scheduled'（每日定时）| 'regression'（改动触发）
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    # 聚合结果
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[int] = mapped_column(Integer, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)  # 每 case 结果
    cost_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 'running' | 'passed' | 'failed' | 'errored'
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：`(skill_id, create_time)` / `(skill_id, status)`。

### 3.5 示例（Few-shot）`tb_skill_example`（§6.3）

成功运行的样本保留为示例，用于 skill 精调或作为 prompt 里的 few-shot：

```python
class TbSkillExample(Base):
    __tablename__ = "tb_skill_example"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 'success'（正样本） | 'failure'（负样本，"不要这样做"）
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    input_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    # 完整对话 JSON
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    # 'auto'（从遥测抽） | 'curated'（人工精挑）
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'pending' | 'approved' | 'rejected'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    feedback_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time/update_time/create_user/update_user
```

### 3.6 改进提案 `tb_skill_proposal`（§6）

LLM 自动从失败样本生成的改进候选：

```python
class TbSkillProposal(Base):
    __tablename__ = "tb_skill_proposal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 'instruction_patch' | 'add_tool' | 'remove_tool' |
    # 'add_example' | 'split_skill' | 'merge_skills'
    proposal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 人可读的说明
    summary: Mapped[str] = mapped_column(String(512), nullable=False)
    # 变更内容：根据 type 结构化的 JSON
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    # 触发样本：哪些失败 usage 引发了这个提案
    evidence_usage_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM 自评置信度
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    # 'pending' | 'accepted' | 'rejected' | 'superseded'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 接受后生成的 variant id 或新版本 id
    resulted_variant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time/update_time
```

### 3.7 依赖与组合 `tb_skill_dependency`（§8）

```python
class TbSkillDependency(Base):
    __tablename__ = "tb_skill_dependency"
    __table_args__ = (
        UniqueConstraint("skill_id", "depends_on_id",
                         name="uk_tb_skill_dep_skill_dep"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    depends_on_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 'required' | 'optional' | 'suggests'
    dep_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # 允许的版本范围，如 ">=1.2.0,<2.0.0"
    version_constraint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    create_time/update_time
```

### 3.8 覆盖/个性化 `tb_skill_override`（§9）

```python
class TbSkillOverride(Base):
    __tablename__ = "tb_skill_override"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 'team' | 'app' | 'user'
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 覆盖字段（不填=继承）
    override_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_tool_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 'active' | 'disabled'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    create_time/update_time/create_user/update_user
```

### 3.9 生命周期事件 `tb_skill_promotion`（§4.3）

记录每次状态迁移，形成完整历史：

```python
class TbSkillPromotion(Base):
    __tablename__ = "tb_skill_promotion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    variant_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    from_status: Mapped[str] = mapped_column(String(16), nullable=False)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 决策依据快照：eval_run_id / a_b_metrics / reviewer_comment
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

### 3.10 收藏 / 社交 `tb_skill_star`（§10）

```python
class TbSkillStar(Base):
    __tablename__ = "tb_skill_star"
    __table_args__ = (UniqueConstraint("skill_id", "user_id",
                                        name="uk_tb_skill_star_skill_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

---

## 4. 生命周期管理

### 4.1 状态机

```
draft  ────┬── submit for review ──▶  reviewing
           │                                │
           │                                ├── reviewer approve ──▶  shadow
           │                                └── reviewer reject ──▶  draft
shadow   ──┬── eval pass ──────────▶  canary  ──┬── metrics pass ──▶  active
           └── eval fail ─────────▶  draft     └── metrics fail ──▶  draft

active   ──┬── new version released ─▶  deprecated（旧版本）
           └── manual archive       ─▶  deprecated
deprecated ── hard delete after N days（保留审计）
```

- **draft**：作者私有，仅自己可用
- **reviewing**：等待 reviewer（团队/应用管理员）审批
- **shadow**：发布但不分流，只做"影子运行"收集遥测 + 过 eval
- **canary**：分配小比例流量（如 10%），和老版本并行跑 A/B
- **active**：默认版本
- **deprecated**：不再分流，旧会话仍可读；N 天后硬删

### 4.2 晋升门禁（Promotion Gates）

每次 `shadow → canary`、`canary → active` 必须满足：

```python
@dataclass
class PromotionGate:
    min_eval_pass_rate: float = 0.95         # critical case 必须 100%
    min_shadow_runs: int = 50                # 足够样本量
    max_regression_vs_prev: float = 0.02     # 通过率不得比老版本低 2% 以上
    no_critical_failures_in: int = 100       # 近 100 次运行无 critical fail
    min_feedback_ratio: float = 0.7          # 👍 占比（如果有）
```

门禁由 `SkillPromotionPipeline` 服务自动校验：

```python
class SkillPromotionPipeline:
    def can_promote(self, skill_id, variant_key, target_status) -> GateResult:
        gate = self._load_gate(skill_id, target_status)
        eval_run = self._latest_eval(skill_id, variant_key)
        shadow_stats = self._shadow_stats(skill_id, variant_key)
        metrics = self._ab_metrics(skill_id, variant_key)
        reasons = []
        if eval_run.pass_rate < gate.min_eval_pass_rate:
            reasons.append(f"eval pass_rate {eval_run.pass_rate:.2%} < gate")
        # ... 其余规则 ...
        return GateResult(passed=not reasons, reasons=reasons)
```

不过门禁的晋升请求返回具体未达指标给前端。

### 4.3 生命周期审计

每次转移写 `tb_skill_promotion`，`evidence` 存：
- 对应的 `eval_run_id`
- A/B 指标快照
- Reviewer 意见

---

## 5. 评估闭环（Eval Harness）

### 5.1 断言类型

| 类型 | 说明 | 示例 |
|---|---|---|
| `must_call_tools` | 必须调用的工具集合 | `["search_db"]` |
| `must_not_call_tools` | 禁止调用 | `["send_email"]` |
| `output_regex` | 输出须匹配 | `["^(是\|否)"]` |
| `output_json_schema` | 结构化校验 | Pydantic schema |
| `output_contains_all/any` | 关键词 | `{"all": ["合规"]}` |
| `latency_ms_max` | 性能 | `15000` |
| `tokens_max` | 成本 | `3000` |
| `llm_judge` | LLM 判官 | `{"criteria": "回答是否礼貌", "model": "haiku", "threshold": 0.7}` |

### 5.2 运行器

`SkillEvalRunner`：

```python
async def run(self, skill_id: int, variant_key: str = "control",
              trigger: str = "manual") -> TbSkillEvalRun:
    cases = self._load_cases(skill_id)
    run = self._create_run(skill_id, variant_key, trigger, total=len(cases))

    # 沙盒：独立 agent 实例，不写业务数据
    sandbox = self._build_sandbox_agent(skill_id, variant_key)

    for case in cases:
        result = await self._run_case(sandbox, case)
        run.details.append(result)
        if result.failed and case.severity == "critical":
            run.critical_failed = True

    run.passed = sum(1 for r in run.details if r.status == "pass")
    run.failed = len(run.details) - run.passed - run.skipped
    run.pass_rate = run.passed / max(len(cases), 1)
    run.status = "passed" if run.pass_rate >= gate.min_eval_pass_rate and not run.critical_failed else "failed"
    self._save(run)
    return run
```

### 5.3 触发时机

| 触发 | 时机 |
|---|---|
| `manual` | 用户在 UI 点"立即评估" |
| `ci` | `skill.instruction` / `variant` / `tool_ids` 变化时自动触发 |
| `scheduled` | 每晚凌晨全量 skill 回归（捕获模型侧、工具侧漂移） |
| `regression` | 某条 usage 失败并被归类为 eval 候选时，auto-run 该条 |

### 5.4 沙盒隔离

- 独立 `AgentApp` 实例，但 `_build_tools` 时替换为**录制工具**：
  - API 工具：录制的 fixture 或 mock server
  - MCP 工具：mock transport
  - LLM 调用：真实 provider 或 `LangChainTestModel`（可注入期望响应）
- `conversation_id=null`，`TbAppLog` 标 `request_type="eval"`
- checkpointer 用内存版（`MemorySaver`），跑完即丢

### 5.5 LLM-as-Judge

对主观类断言（"回答礼貌"/"语气专业"），用便宜模型判：

```
PROMPT = """你是评估员。判断回答是否满足准则。
准则: {criteria}
用户问: {input}
助手答: {output}
只回复 JSON: {"pass": true/false, "reason": "..."}"""
```

`threshold` 可设为"多次采样中 > N 次通过"，减小单次抖动。

---

## 6. 自动演化（Auto-Evolution）

### 6.1 失败聚类

后台任务 `SkillFailureClusterer` 每日运行：

```python
def cluster_failures(self, skill_id: int) -> list[FailureCluster]:
    # 最近 7 天 tb_skill_usage 中 success=0 或有差评的样本
    failures = self._load_recent_failures(skill_id, days=7)
    # 用 embedding 聚类
    clusters = self._embed_and_cluster(failures, min_cluster_size=5)
    return clusters
```

聚类后每组代表一种失败模式（如"用户问日期，agent 漏调 search_db"）。

### 6.2 LLM 生成改进提案

对每个聚类 → 调用 `SkillProposalGenerator`：

```
PROMPT = """你是 prompt 工程师。下面是一个 skill 的定义和它最近失败的 {N} 个样本的摘要。
请提出一条具体的改进建议（只允许修改 instruction 或增删 few-shot 示例），输出 JSON：
{
  "type": "instruction_patch" | "add_example" | "add_tool" | ...,
  "summary": "...",
  "diff": "...",
  "confidence": 0.0-1.0
}

现有 skill.instruction:
---
{instruction}
---

失败样本摘要（N=5）:
{samples}
"""
```

输出写入 `tb_skill_proposal(status='pending')`。

### 6.3 人工评审

UI "提案工作台" 列出 pending proposal：

- 左侧 diff 显示
- 右侧失败证据（点击跳转原会话）
- 按钮：`接受为新 variant` / `拒绝` / `修改后接受`
- 接受后自动创建 `TbSkillVariant(source='auto_proposal', status='shadow')` 并排 eval

### 6.4 成功样本转示例

正向遥测（success=1 且 feedback=+1）达到一定量，后台候选进 `tb_skill_example(kind='success', status='pending')`，由维护者精挑后进 skill 的 few-shot 区。

Few-shot 注入时只拿 top-K 高置信样本，按 token budget 截断。

### 6.5 冷启动防护

- 仅当 usage ≥ 50 才启动自动演化（样本太少容易过拟合噪声）
- 每周每个 skill 至多接收 3 个 auto proposal
- Proposal 从**不**自动晋升到 active，必须过人工 + eval 门禁

---

## 7. 变体实验（A/B Variants）

### 7.1 分流策略

运行时 `SkillsInjectionResolver.pick_variant(skill_id, ctx)`:

```python
def pick_variant(self, skill_id, ctx) -> TbSkillVariant:
    variants = self._load_active_variants(skill_id)
    # 按 user_id 哈希一致性分流（同一用户稳定拿到同一 variant）
    bucket = hash(f"{skill_id}:{ctx.user_id}") % 100
    acc = 0
    for v in variants:
        acc += v.traffic_weight
        if bucket < acc:
            return v
    return variants[-1]  # fallback
```

分流维度可按 `user_id` 也可按 `conversation_id`；企业场景一般按 `user_id`，避免对话中途换 variant。

### 7.2 A/B 指标

`tb_skill_usage` 按 `variant_key` 聚合：

| 指标 | 含义 |
|---|---|
| `activation_rate` | `activated / injected`（skill 是否真被用上） |
| `success_rate` | `success=1 / total` |
| `avg_tool_calls` | 工具调用平均数 |
| `latency_p50/p95` | |
| `tokens_avg` | 注入 token 平均 |
| `👍 ratio` | 关联 `tb_message_feedback` |

统计显著性用双尾比例检验；达到置信度 95% 且样本 ≥ N（默认 200）才判胜负。

### 7.3 自动晋升

`SkillVariantExperimenter` 每日跑：

- 对每个含 `canary` 变体的 skill，跑 A/B 指标
- 胜出且过门禁 → 提示维护者一键 "promote to active"；若开启 **auto promote** 且指标差距显著 → 自动晋升并归档老版本

### 7.4 回滚

- 每次晋升都记录在 `tb_skill_promotion`；一键回滚重建上一状态
- 紧急回滚不走门禁，但强制写 `evidence.reason` 和审计通知

---

## 8. 组合与依赖

### 8.1 引用关系

Skill A 可以引用 Skill B：

```jsonc
// tb_skill.instruction 里或额外字段
{
  "uses_skills": ["/skills/util-date-parser/", "/skills/util-sql-lint/"]
}
```

依赖解析由 `SkillCompiler` 在调用 deepagents 前完成：
- 读取 `uses_skills` / `tb_skill_dependency`
- 解析 `version_constraint`
- 展开依赖图并去重
- 检测循环依赖
- 把最终 skill 集合渲染为 `/skills/.../SKILL.md` 虚拟文件

deepagents 原生 `SkillsMiddleware` 不做递归依赖解析；它只扫描已注入 source 下的 skill 目录。因此不能把依赖能力写成 deepagents 原生加载行为。

### 8.2 包（Package）

`tb_skill_package`（可选，与 skill 同概念）：由多个 skill 打包，版本统一发布。适合"财务分析套件"这类业务包。

### 8.3 循环依赖检测

发布时用 DAG 校验：

```python
def detect_cycle(skill_id) -> list[int] | None:
    visited, stack = set(), []
    def dfs(node):
        if node in stack:
            return stack[stack.index(node):] + [node]
        if node in visited:
            return None
        stack.append(node); visited.add(node)
        for dep in deps_of(node):
            found = dfs(dep)
            if found:
                return found
        stack.pop()
        return None
    return dfs(skill_id)
```

循环依赖拒绝发布。

### 8.4 冲突与工具合并

引用链上多个 skill 绑定了同一 tool_id → 去重；不同 skill 给同一 tool 设了不同 description → 采用引用链 DFS 先根后子的策略（根 skill 的描述优先）。

---

## 9. 变体与个性化（Override）

### 9.1 继承链

注入时解析优先级（从高到低）：

1. **用户 override**（`tb_skill_override(scope=user, scope_id=user_id)`）
2. **应用 override**（`tb_skill_override(scope=app)`）
3. **团队 override**（`tb_skill_override(scope=team)`，取用户所属团队交集）
4. **Skill 主版本**（来自 `tb_skill_variant` 的选中 variant）

每层可只覆盖部分字段（instruction / tool_ids / locale），未覆盖的字段继承下一层。

### 9.2 Locale

Skill 可以有多语言变体（`tb_skill.locale`），也可以由 override 覆盖：

- 用户语言偏好存在 `tb_memory_kv(key='language_preference')`
- 注入时匹配 locale 最接近的变体
- 未匹配 → fallback 到默认 locale

### 9.3 Fork

用户/团队想深度定制 → 一键 fork：

- 复制 skill 行 → 新 skill_id，`forked_from_id` 标记来源
- 复制 variant、eval_case（可选）
- 新 skill 在 fork 者自己的 owner_type/owner_id 下
- 后续上游更新，前端提醒 fork 者"上游有变，查看 diff"

---

## 10. 市场与协作

### 10.1 可见性层级

| visibility | 谁能发现 | 谁能使用 |
|---|---|---|
| `private` | 仅所有者 | 仅所有者 |
| `team` | 所属团队成员 | 所属团队 |
| `org` | 同租户所有用户 | 同租户所有用户 |
| `public` | 市场全站（跨租户） | 跨租户，按协议 |

### 10.2 发现与搜索

`GET /api/v1/skill/marketplace/search?q=...&tag=...&locale=...&sort=stars|usage|new`：

- 多字段 FTS（name / description / tags / instruction 摘要）
- 按 `stars_count` / `usage_count` / `create_time` 排序
- 筛选 tag / locale / owner_type

### 10.3 协作操作

- **Star**：`tb_skill_star`
- **Fork**：§9.3
- **Comment / Review**：新增 `tb_skill_comment(skill_id, user_id, content, rating 1-5)`
- **Issue**：用户对 skill 提问题，`tb_skill_issue(skill_id, title, content, status)`

### 10.4 跨租户安全

- `public` skill fork 时默认复制到本租户 owner 下，不直接引用原表（防上游恶意修改）
- 自动扫描 `instruction` 含 prompt injection / 外链 → 禁止发布为 public

---

## 11. 治理与安全

### 11.1 签名与完整性

`signature = SHA256(name || instruction || sorted(tool_ids) || version)`。每次发布重算；注入前校验；不匹配→禁用并告警（供应链防御）。

### 11.2 内容扫描

发布流水线阻断：

- **PII 扫描**：instruction 含明文身份证、手机号 → 警告
- **Prompt Injection**：instruction 含 "忽略以上"/"你现在是 system" 等模式 → 警告
- **外链扫描**：非白名单域名 → 警告
- **工具滥用**：绑定高风险工具（如 `delete_db`）→ 强制 reviewer 为管理员

### 11.3 权限模型

| 操作 | 所需角色 |
|---|---|
| 创建 draft | 普通用户（配额限制） |
| 提交 reviewing | 所有者 |
| 审批 reviewing → shadow | 团队管理员 |
| 晋升 canary/active | 应用管理员 + 过门禁 |
| 发布 public | 组织管理员 |
| 强制回滚 | 应用管理员 |

与 `tool-approval-and-acl-design.md` 的 RBAC 统一。

### 11.4 审计

所有 CRUD、晋升、回滚、签名、扫描事件 → 写 `tb_policy_audit`（复用 tool-approval 的审计表，event_type 扩充）或独立 `tb_skill_audit`。

---

## 12. 性能与观测

### 12.1 编译缓存

SKILL.md 拼装（含 override 继承链 + 依赖递归）每次注入都算成本高。缓存策略：

- key = `(skill_id, variant_key, scope_signature)` 其中 `scope_signature` 基于 override 链 hash
- LRU + TTL，不超过 5 min（便于热更生效）
- 缓存内容 = 最终 SKILL.md 字符串 + tool_ids 数组

### 12.2 Token 预算

每个 skill 有 `max_injected_tokens`（默认 2000）：

- 超限时按段落优先级截断（标题 > 步骤 > 背景 > 示例）
- 超限事件上报，提示维护者分拆 skill

### 12.3 观测指标（Prometheus）

| 指标 | 说明 |
|---|---|
| `skill_injection_total{skill,variant,app}` | 注入次数 |
| `skill_activation_rate{skill,variant}` | 实际用上的比例 |
| `skill_success_rate{skill,variant}` | 成功率 |
| `skill_latency_p95{skill,variant}` | |
| `skill_tokens_avg{skill,variant}` | 注入 token 平均 |
| `skill_eval_pass_rate{skill,variant}` | 评估通过率 |
| `skill_proposal_pending_total{skill}` | 积压 |
| `skill_promotion_total{from,to}` | |

### 12.4 大盘

Grafana 仪表板：

- 全局 skill 健康度排行（按 success_rate × usage_count）
- 今日失败 Top 10 skill + 样本跳转
- Eval 红屏（失败的 skill 一眼看见）
- 实验中 skill 的 A/B 指标

---

## 13. 运行时改造

### 13.1 `agent_app.py._prepare` 的 skill 注入扩展

现在是：

```python
skill_files = self._build_skill_files(db, req.app_id)
```

改为经过 `SkillCompiler` 的新管线：

```python
compiled = self._skill_compiler.compile(
    app_id=run_ctx.app_id,
    user_id=run_ctx.user_id,
    team_ids=run_ctx.team_ids,
    conversation_id=run_ctx.conversation_id,
)
# compiled: {
#   files: {"/skills/x/SKILL.md": FileData, ...},   # 注入 deepagents
#   usage_records: [SkillUsageStub(skill_id, variant_key), ...],  # 用于落 tb_skill_usage
#   required_tool_ids: [...],                       # 扩展 _build_tools 结果
# }

payload["files"] = compiled.files
tools.extend(compiled.extra_tools)

# 把 usage_records 透传到流式层，等 stream 结束时按激活情况批量写 tb_skill_usage
self._skill_usage_collector.attach(handler, compiled.usage_records)
```

### 13.2 Activation 判定

Skill 是否"真被用上"不能依赖 deepagents 原生事件；`SkillsMiddleware` 不会产生 `skill_activated` 事件，也不会把工具调用自动归属到 skill。采用 easy-ai 自研多信号归因：

1. `SkillCompiler` 为每个注入 skill 生成 `skill_hash`、`variant_key`、`tool_ids`、`file_path`，写入 `usage_records`。
2. LLM 输出里明确引用 skill（例如 `<skill-ref name="x">`） → strong activation。
3. 调用了该 skill 独占工具 → strong activation。
4. 调用了多个 skill 共享的工具 → multi attribution，记录所有候选 skill_id，`activation_reason="shared_tool"`。
5. 无引用、无相关工具调用 → injected only。
6. 运行结束后保存 `activation_reason`，避免后续 A/B 和自动演化建立在不可解释数据上。

`SkillUsageCollector` 监听 `on_tool_start` 事件，把本次 tool_call 的 tool_id 回查是否属于某 skill，若是则标记 `activated`。

### 13.3 `SkillCompiler` 伪代码

```python
@dataclass
class SkillCompileContext:
    """SkillCompiler 全链路共享的上下文对象，由 AgentRunContext 派生。
    不允许在 resolver / merger / dep-resolver 内部从全局或线程局部取其它字段。"""
    run_id: str
    app_id: int
    user_id: int | None
    team_ids: list[int]
    conversation_id: int | None
    tenant_id: int | None
    role_codes: list[str]

class SkillCompiler:
    def compile(self, ctx: SkillCompileContext) -> CompiledSkills:
        # 1. app 绑定的 skill 列表
        bindings = self._load_app_skills(ctx.app_id)
        compiled = {}
        for b in bindings:
            if not self._is_applicable(b, ctx):
                continue
            variant = self._resolver.pick_variant(b.skill_id, ctx)
            # override 合并
            merged = self._merge_overrides(variant, ctx)
            # 依赖递归
            all_skills = self._resolve_deps(merged)
            for s in all_skills:
                cached = self._compile_cache.get(s.cache_key)
                if not cached:
                    cached = self._render_skill_md(s)
                    self._compile_cache.put(s.cache_key, cached)
                compiled[s.file_path] = cached
        return CompiledSkills(files=compiled, usage_records=[...], extra_tools=[...])
```

---

## 14. API 设计

### 14.1 Skill CRUD 扩展（保留原有 + 新增）

```
# 生命周期
POST   /api/v1/skill/{id}/submit-review
POST   /api/v1/skill/{id}/approve                 # reviewer
POST   /api/v1/skill/{id}/reject                  # reviewer
POST   /api/v1/skill/{id}/promote                 # body: { to: 'canary'|'active' }
POST   /api/v1/skill/{id}/deprecate
POST   /api/v1/skill/{id}/rollback                # body: { to_version: N }

# 变体
GET    /api/v1/skill/{id}/variant
POST   /api/v1/skill/{id}/variant                 # 新变体
PUT    /api/v1/skill/{id}/variant/{key}
DELETE /api/v1/skill/{id}/variant/{key}
POST   /api/v1/skill/{id}/variant/{key}/traffic   # body: { weight: 0-100 }

# 评估
GET    /api/v1/skill/{id}/eval-case/page
POST   /api/v1/skill/{id}/eval-case
PUT    /api/v1/skill/{id}/eval-case/{case_id}
DELETE /api/v1/skill/{id}/eval-case/{case_id}
POST   /api/v1/skill/{id}/eval/run                # 触发评估
GET    /api/v1/skill/{id}/eval/run/page
GET    /api/v1/skill/{id}/eval/run/{run_id}

# 提案
GET    /api/v1/skill/{id}/proposal/page
POST   /api/v1/skill/{id}/proposal/{pid}/accept
POST   /api/v1/skill/{id}/proposal/{pid}/reject

# 示例
GET    /api/v1/skill/{id}/example/page
POST   /api/v1/skill/{id}/example/{eid}/approve
POST   /api/v1/skill/{id}/example/{eid}/reject

# 依赖
GET    /api/v1/skill/{id}/dependency/graph         # 可视化依赖图
POST   /api/v1/skill/{id}/dependency
DELETE /api/v1/skill/{id}/dependency/{dep_id}

# Override
GET    /api/v1/skill/{id}/override/page
POST   /api/v1/skill/{id}/override
PUT    /api/v1/skill/{id}/override/{ov_id}
DELETE /api/v1/skill/{id}/override/{ov_id}

# 市场
GET    /api/v1/skill/marketplace/search
POST   /api/v1/skill/{id}/fork                    # body: { to_owner_type, to_owner_id }
POST   /api/v1/skill/{id}/star
DELETE /api/v1/skill/{id}/star
POST   /api/v1/skill/{id}/comment

# 观测
GET    /api/v1/skill/{id}/usage/summary?period=7d
GET    /api/v1/skill/{id}/usage/page?variant=...
GET    /api/v1/skill/{id}/ab-metrics?variants=control,v1
```

### 14.2 批量与运维

```
POST /api/v1/skill/batch/run-eval                 # 全量夜跑
POST /api/v1/skill/batch/cluster-failures         # 手动触发聚类
GET  /api/v1/skill/health                         # 全局健康度
```

---

## 15. 前端 UX

### 15.1 Skill 详情页（重构）

Tab：

1. **概览** —— 当前 active 变体内容 + usage_count / success_rate / 👍 比例
2. **内容编辑**（markdown 实时预览 + lint：PII/注入警告）
3. **变体** —— 所有变体卡片 + A/B 流量拖动条 + "新增变体"
4. **评估** —— 评估用例列表 + "立即评估" + 历史 run 趋势图
5. **遥测** —— 近 7/30 天使用图表、失败 Top / 差评消息列表
6. **提案** —— 待审批 proposal，左 diff 右证据
7. **依赖** —— 依赖图（d3 力导图）
8. **Override** —— 按 scope 列出个性化覆盖
9. **历史** —— 生命周期迁移时间线

### 15.2 "Skill 健康度" 大盘

首页入口，组织视角：

- 红色：近 24h critical fail 的 skill
- 黄色：通过率下降的 skill
- 绿色：健康
- 未使用：> 30 天未被注入的 skill，提示归档

### 15.3 作者工作台

- 我维护的 skills 列表（按状态分组）
- 待办：
  - N 条 proposal 等我接受
  - N 条 example 等我审核
  - N 条 comment 未回
  - 评估失败待处理

---

## 16. 兼容与回滚

- 新表 / 新字段独立迁移，不动原 `tb_skill` 其他字段
- `lifecycle_status` 默认填 `active`（现存 skill 视为"已上线"）
- `owner_type/owner_id` 回填：对现存 skill 按 `create_user` 默认 `owner_type='user'`
- Feature flag：`settings.skill_evolution_enabled`（默认 false）
  - 关闭时：`_prepare` 走旧路径 `_build_skill_files`
  - 开启时：走 `SkillCompiler`
- 按 app 级开关：`app_config.skill_evolution.enabled=true` 才走新管线
- 紧急回滚：关 flag 即可；新写入的评估/遥测/提案数据留库不影响

---

## 17. 测试要点

| 场景 | 预期 |
|---|---|
| 新 skill 从 draft 走完全流程 | 经 reviewing → shadow → canary → active，每步门禁校验 |
| 晋升门禁不通过 | API 返回具体未达指标 |
| 评估含 critical 用例失败 | 阻断晋升 |
| Variant A/B 分流 | 同一 user 稳定拿到同变体 |
| 自动 proposal 生成 | 失败聚类产生 proposal，写 pending |
| 提案接受 | 自动创建 variant 并排 eval |
| 依赖递归 | 多层依赖正确合并、工具去重 |
| 循环依赖发布 | 阻断 |
| Override 继承链 | 用户 → 应用 → 团队顺序生效 |
| Fork | 新 skill 独立，上游更新不影响 |
| 市场搜索 | FTS 命中 name / tag / description |
| 跨租户 public | fork 到本租户 owner |
| 签名不匹配 | 禁用 + 告警 |
| 编译缓存 | 第二次注入命中缓存 |
| Token 超预算 | 按优先级截断 |
| 夜间 CI 跑全量 eval | 并发跑、失败报警 |
| 紧急回滚 | 一键恢复上一版本 |
| 冷启动防护 | usage < 50 不触发演化 |

---

## 18. 分期落地

| 阶段 | 范围 | 主要产出 |
|---|---|---|
| **P0** | 生命周期状态 + `TbSkillPromotion` + 迁移 + UI 状态可视 | 结构基础，不改行为 |
| **P1** | `TbSkillUsage` 遥测 + Langfuse 关联 + 观测大盘 | 看得见用量 |
| **P2** | Eval Harness（case CRUD + runner + 门禁） + 发布前 CI | 测得出质量 |
| **P3** | `TbSkillVariant` + A/B + 分流 + 指标对比 + 手动晋升 | 跑得起实验 |
| **P4** | 失败聚类 + Proposal + 人工审批 + 成功样本转示例 | 学得到教训 |
| **P5** | `TbSkillDependency` + 组合/包 + 循环检测；`TbSkillOverride` + 个性化 | 可以继承和分化 |
| **P6** | 市场 + Star/Fork/Comment + 公开可见性 + 跨租户安全 | 社区协作 |
| **P7** | 签名 + 内容扫描 + PII/注入防御 + 审计完善 | 敢交给业务方 |
| **P8** | 编译缓存 + Token 预算 + 性能大盘 | 跑得稳 |

P0-P1 是前提（没遥测就没有后续一切）。P2 是最大价值单项。P3-P4 合并为一个季度可上。P5-P8 按业务诉求排。

---

## 19. 风险与未决

1. **遥测规模**：高频 agent 每次注入都落 usage 会使表爆炸。缓解：按月分区 + 热表 30 天、冷表归档；或采样（activation 事件全量、injection-only 事件按 1/10 采样）。
2. **Eval 成本**：critical skill 每次 CI 跑 LLM-as-judge 会吃 token。缓解：只在 critical 用例跑 judge，普通用例用确定性断言。
3. **Auto Proposal 噪声**：LLM 可能产出低质 proposal 把维护者淹没。缓解：置信度阈值 + 每周配额 + 聚类最小样本量 + 用户打"无用"反馈回流优化 prompt。
4. **变体漂移**：A/B 长期不收敛（数据太少）。缓解：设最长实验期（30 天），到期强制决策或全归档。
5. **依赖更新风险**：底层 skill 改动传导到上游 skill。缓解：通过 `version_constraint` 锁定；上游 skill 需重新过 eval 才继承新版。
6. **Override 激增**：大组织可能产生数千 override，继承链解析成本高。缓解：必要时限制 override 层级深度；对热 app 做 scope_signature 预计算缓存。
7. **公开市场的治理**：`public` 可能被滥用为 prompt injection 攻击面。缓解：强制过扫描 + 双人评审 + 签名 + 定期回扫。
8. **与 Memory / Policy 的边界**：Skill 可引用 memory / 调 tool，但 skill 变化不应影响 memory 的治理。缓解：明确"skill 只能引用、不能改写 memory 治理配置"。

---

## 20. 相关文档

- `skill-management-design.md` — 基础 CRUD（本设计的前置）
- `long-session-design.md` — `tb_message_feedback` 为遥测源
- `tool-approval-and-acl-design.md` — skill 调用受策略守护；发布评审复用 RBAC
- `agent-memory-design.md` — skill 和 memory 在职责上互补
- `observability-design.md` — Langfuse + Prometheus 总体
