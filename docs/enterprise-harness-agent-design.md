# easy-ai 企业级 Harness Agent 系统设计

> 本文档汇总 `long-session-design.md`、`agent-memory-design.md`、`skill-evolution-design.md`、`tool-approval-and-acl-design.md` 四份详细设计，形成 easy-ai 企业级 harness agent 的系统级设计。本文关注系统边界、能力架构、治理模型、运行语义和演进路线，不展开代码开发细节。

---

## 1. 设计目标

easy-ai 的企业级 harness agent 目标不是只让大模型“能调用工具”，而是让 agent 在企业环境中具备可持续运行、可控、可审计、可演化的能力。

核心目标：

1. **长时间可靠执行**：会话可恢复，执行状态可持久化，复杂任务过程对用户透明。
2. **企业工具治理**：工具调用可按用户、应用、团队、参数、风险、时间和租户维度治理。
3. **长期记忆**：agent 能在合规前提下记住用户、团队、应用和组织知识。
4. **Skill 持续演化**：skill 不只是静态 prompt，而是可评估、可实验、可回滚、可协作的生产资产。
5. **可观测与可审计**：所有关键决策、审批、记忆、反馈和 skill 使用都能追溯。
6. **渐进式落地**：优先交付低风险高价值能力，避免一次性引入不可控复杂度。

非目标：

- 不把 deepagents 改造成企业治理平台。
- 不依赖模型自觉遵守企业策略。
- 不把 checkpoint 当业务事实表。
- 不把记忆、skill、审批设计成无法回滚的强耦合系统。
- 不新增数据库外键约束；只使用业务列、唯一约束和查询索引，跨表完整性由 service 层和审计保障。

---

## 2. 总体定位

系统分为三层：

| 层级 | 定位 | 主要职责 |
|---|---|---|
| deepagents / LangGraph 运行时层 | Agent runtime scaffold | agent 图、middleware 扩展点、StateBackend/files、skills progressive disclosure、todo、subagent、summarization、checkpointer 接入 |
| easy-ai Agent 编排层 | 运行时适配与企业边界 | `AgentRunContext`、工具 wrapper、SSE、checkpoint thread、memory/skill 注入、审批恢复、观测事件 |
| easy-ai 企业治理层 | 企业级能力系统 | 策略、审批链、审计、长期记忆、skill 生命周期、评估、A/B、合规、管理员工作台 |

关键原则：

- deepagents 负责“agent 怎么运行”。
- easy-ai 负责“企业允许 agent 怎么运行”。
- 企业治理不能只靠 prompt，必须在工具执行边界和服务层兜底。

---

## 3. 能力地图

| 能力域 | 用户价值 | 系统能力 | 来源文档 |
|---|---|---|---|
| 长会话 | 历史会话可恢复，复杂任务不中断 | Checkpointer、thread_id、消息输入协议、并发锁、checkpoint TTL | `long-session-design.md` |
| Todo 可视化 | 用户知道 agent 正在做什么 | deepagents TodoList + easy-ai SSE 事件投递 | `long-session-design.md` |
| 反馈闭环 | 用户反馈可进入评估和质量改进 | message feedback、Langfuse trace、管理看板 | `long-session-design.md` |
| 工具治理 | 高风险工具可阻断、审批、审计 | PolicyEngine、ToolPolicyMiddleware、tool wrapper、HITL、审批链 | `tool-approval-and-acl-design.md` |
| 长期记忆 | agent 跨会话记住偏好、事实和团队共识 | L1/L2/L3/L4/L5 记忆、注入、反思、确认、GDPR | `agent-memory-design.md` |
| Skill 演化 | skill 可测试、可灰度、可演进 | SkillCompiler、usage telemetry、eval、variant、proposal、marketplace | `skill-evolution-design.md` |
| 观测与审计 | 企业能追踪 agent 为什么这么做 | policy audit、memory audit、skill usage、feedback、Prometheus、Langfuse | 四份文档共同覆盖 |

---

## 4. 统一运行上下文

所有 agent 能力依赖统一的 `AgentRunContext` 概念。它不是普通 HTTP `RequestContext`，而是一次 agent 运行的企业上下文。

核心字段：

| 字段 | 含义 |
|---|---|
| `run_id` | 单次 agent run 幂等和追踪标识 |
| `app_id` | 当前运行所属应用 |
| `user_id` | 当前用户；开放 API 场景可为空但需受限 |
| `conversation_id` | 会话标识；长会话和 HITL 恢复依赖 |
| `thread_id` | LangGraph checkpoint thread |
| `request_type` | chat / openapi / eval / debug 等 |
| `tenant_id` | 租户标识；当前 P0/P1 可为空或归一化为默认租户 |
| `team_ids` | 团队、用户组上下文 |
| `role_codes` | 策略和后台治理用角色 |
| `trace_id` | 观测链路标识 |

运行上下文的职责：

- 统一连接会话、工具策略、记忆注入、skill 编译和观测事件。
- 避免各模块从 `RequestContext` 中自行推导不存在的字段。
- 作为审批、记忆、skill telemetry 的幂等和归因基础。

---

## 5. 系统运行架构

```
用户 / OpenAPI
    |
    v
入口层：认证、限流、创建 AgentRunContext
    |
    v
ConversationService / OpenAPI Service
    |
    |-- 长会话：解析 conversation_id / thread_id
    |-- 输入协议：checkpoint 模式只传本轮新消息
    |-- 并发锁：同 thread_id 串行或排队
    v
AgentApp Runtime
    |
    |-- 构建模型、工具、skill、memory、middleware
    |-- 注入 checkpointer
    |-- 注入 policy-aware tool wrapper
    |-- 注入 easy-ai enterprise middleware
    v
deepagents / LangGraph graph
    |
    |-- model call
    |-- tool call
    |-- todo update
    |-- subagent task
    |-- checkpoint write
    v
SSE / 审计 / Langfuse / Prometheus / 业务表
```

重要运行语义：

- checkpoint 开启时，业务消息表不再每轮完整喂给 agent；只传本轮新用户消息。
- checkpoint 是运行时 state 源，业务消息表是用户可见事实源。
- checkpoint 缺失、损坏或被清理时，可从业务消息表重建最小可运行 state，但不恢复 todos/files/scratch。
- HITL 审批依赖 checkpoint 恢复，但不使用 deepagents `interrupt_on`。
- 工具治理必须在 middleware 和 tool wrapper 两层生效，不能只依赖主 agent middleware。

---

## 6. deepagents 能力边界

本系统复用 deepagents，但不把 deepagents 视为企业治理平台。

### 6.1 直接复用

| deepagents 能力 | 使用方式 |
|---|---|
| `create_deep_agent` | 组装主 agent、middleware、subagents、checkpointer |
| `StateBackend` / `files` | 注入虚拟 skill、memory 和运行文件 |
| `SkillsMiddleware` | 基础 `SKILL.md` 扫描、frontmatter 解析、progressive disclosure |
| `TodoListMiddleware` | 提供 `write_todos` 和 `todos` state |
| `SubAgentMiddleware` | 提供 `task` 工具和声明式 subagent |
| 默认 SummarizationMiddleware | P0 接受 deepagents 默认摘要策略 |
| checkpointer 参数 | 接入 LangGraph Postgres checkpoint |

### 6.2 基于扩展实现

| 能力 | 设计方式 |
|---|---|
| Todo 前端可视化 | easy-ai 监听 `write_todos` 的 `Command.update["todos"]`，通过 SSE 推给前端 |
| Memory 注入 | easy-ai 自研 `MemoryInjectionMiddleware` 注入 DB 中的长期记忆 |
| Skill 编译 | easy-ai `SkillCompiler` 生成最终虚拟 `/skills/.../SKILL.md` |
| 工具审批 | easy-ai `ToolPolicyMiddleware.after_model` + LangGraph `interrupt()` |
| 审批恢复 | easy-ai `ApprovalResumeService` 基于 `thread_id` 恢复 graph |
| 观测 | easy-ai 将 run、tool、memory、skill、feedback 事件写入审计和 Langfuse |

### 6.3 不依赖 deepagents 原生支持

| 企业能力 | 原因 |
|---|---|
| 企业长期记忆写入 | deepagents `MemoryMiddleware` 会诱导 `edit_file` 写 StateBackend 虚拟文件，不会进入 DB、审批和 GDPR 流程 |
| Skill 依赖解析 | `SkillsMiddleware` 不递归解析依赖和版本约束 |
| Skill activation 归因 | deepagents 不产生 `skill_activated` 事件 |
| 企业工具 ACL | deepagents `_PermissionMiddleware` 不覆盖 easy-ai 的策略、审批链、审计和多租户语义 |
| app 级 summarization 配置 | 当前 `create_deep_agent` 没有公开替换默认 summarization 的参数 |
| 默认 general-purpose 企业治理 | deepagents 会自动插入默认 subagent，主 agent middleware 不会自动治理它 |

---

## 7. 长会话与过程透明

### 7.1 长会话

长会话能力由 LangGraph checkpointer 承接，核心是把 agent 运行时 state 按 `thread_id` 持久化。

运行原则：

- `TbConversation.thread_id` 是业务会话和 checkpoint thread 的桥。
- 同一 `thread_id` 同时只允许一个运行实例修改 state。
- checkpoint 写入失败时可降级为无持久化运行，但必须记录告警。
- checkpoint 清理不删除业务消息；业务消息仍用于展示、审计和最小 state 重建。

### 7.2 Todo 可视化

deepagents 原生维护 `todos` state，但不会直接满足前端可视化需求。easy-ai 负责：

- 捕获 `write_todos` 返回的 todo 快照。
- 通过 SSE 发送 `todos_updated`。
- 前端渲染当前步骤、待办、完成和失败状态。
- 历史会话从 checkpoint 的 `todos` 恢复；checkpoint 缺失时提示执行状态不可用。

### 7.3 反馈闭环

反馈闭环连接用户体验和后续演化：

- 用户可对 assistant message 点赞、点踩、选择原因、填写说明。
- feedback 与 conversation、message、app、Langfuse trace 关联。
- 管理员可查看差评样本、模型质量趋势和 app 质量指标。
- 负反馈可进入 eval 候选集和 skill 改进提案。

---

## 8. 工具治理与 HITL

### 8.1 治理目标

工具治理解决三个问题：

1. 哪些工具可以被谁调用。
2. 哪些调用参数需要阻断、审批或脱敏。
3. 出现风险调用后如何暂停、通知、审批、恢复和审计。

### 8.2 策略模型

策略按多维条件评估：

- 用户、团队、角色、租户
- app、工具、工具来源、MCP server
- 参数值、URL、域名、SQL 类型、金额等
- 时间窗口和环境
- 风险等级

策略决策：

| 决策 | 含义 |
|---|---|
| `allow` | 放行 |
| `deny` | 阻断，并把拒绝信息反馈给 agent |
| `approval` | 暂停 graph，创建审批单 |
| `dry_run` | 不阻断，只记录命中 |

### 8.3 HITL 执行语义

HITL 不通过工具执行阶段抛异常实现，也不使用 deepagents `interrupt_on`。执行语义为：

1. 模型产生 tool_call。
2. `ToolPolicyMiddleware.after_model` 在工具执行前评估策略。
3. `deny` 时移除 tool_call 并追加拒绝 ToolMessage。
4. `approval` 时创建 pending 审批单并调用 LangGraph `interrupt()`。
5. 前端显示等待审批。
6. 审批通过或拒绝后，`ApprovalResumeService` 通过 `thread_id` 恢复 graph。
7. 工具真正执行前仍由 policy-aware tool wrapper 兜底检查。

### 8.4 Subagent 治理

deepagents 的 `task` 工具可以启动 subagent。企业治理必须显式处理：

- 默认 `general-purpose` subagent 必须被显式覆盖为受治理版本，或禁用/限制 `task`。
- 声明式 subagent 必须注入 `ToolPolicyMiddleware`。
- compiled/async subagent 默认不信任，除非其自身服务具备同等治理。
- 底层工具 wrapper 是跨主 agent 和 subagent 的最终执行边界。

---

## 9. 长期记忆系统

### 9.1 记忆分层

| 层 | 名称 | 作用 |
|---|---|---|
| L1 | 静态文件记忆 | 组织、团队、应用、用户级固定上下文 |
| L2 | 结构化 KV 记忆 | 用户偏好、稳定事实、配置类信息 |
| L3 | 语义记忆 | 可检索的自由文本事实和经验 |
| L4 | 情景记忆 | 会话摘要、过去任务要点 |
| L5 | 反思记忆 | agent 自动发现但等待确认的候选记忆 |

### 9.2 写入原则

长期记忆写入必须走 easy-ai 自研工具和服务：

- `remember`
- `forget`
- `recall`
- `list_memories`

禁止把 deepagents 原生 `MemoryMiddleware` 的 `edit_file` 写入视为企业长期记忆写入。原因是它只会修改 StateBackend / checkpoint 中的虚拟文件，无法进入：

- DB 持久化
- pending/confirmed 审核
- PII 策略
- GDPR 删除
- 审计

### 9.3 注入原则

记忆注入应遵循：

- budget-aware，避免无限扩张 prompt。
- 按 User -> App -> Team -> Org 合并，低层覆盖高层。
- 高敏记忆默认不自动注入。
- L3/L4 embedding 召回超时或失败时跳过，不阻断对话。
- 注入事件需要聚合审计，不按每条记忆高频写爆审计表。

### 9.4 合规原则

- 高敏记忆不允许 agent 自动写入，需用户或管理员确认。
- 日志、审计、反馈和 Langfuse 只记录脱敏摘要。
- GDPR 删除要清内容、留审计元数据。
- 租户隔离必须在 MemoryService 查询层统一实现。

---

## 10. Skill 演化系统

### 10.1 Skill 定位

Memory 是“知道什么”，Skill 是“怎么做”。Skill 是 agent 的程序性知识资产，应具备生产系统特征：

- 生命周期
- 版本
- 评估
- 变体实验
- 遥测
- 依赖
- 回滚
- 审计

### 10.2 SkillCompiler

deepagents `SkillsMiddleware` 只负责基础注入和 progressive disclosure。easy-ai 需要 `SkillCompiler` 在调用 deepagents 前完成：

- app 绑定 skill 解析
- 团队、用户、locale 覆盖
- variant 选择
- 依赖展开
- 循环依赖检测
- 工具集合合并
- token 预算控制
- 编译缓存
- 生成最终虚拟 `SKILL.md` 文件
- 生成 run 级 skill snapshot

### 10.3 遥测与归因

Skill 使用不能依赖 deepagents 原生事件。easy-ai 需要自研归因：

- 注入了哪些 skill。
- 模型是否读取了某个 `SKILL.md`。
- 是否使用了 skill 独占工具。
- 是否调用了多个 skill 共享工具。
- 用户反馈和 Langfuse trace 是否关联该 skill。
- 当前运行使用了哪个 variant 和 hash。

遥测分层：

- activation 事件全量记录。
- injected-only 默认聚合或采样。
- 每次 agent run 保存 skill snapshot。
- 日聚合用于报表和 A/B 判断。

### 10.4 Eval 与演化

Skill 演化闭环：

1. 使用和反馈产生样本。
2. 失败样本进入 eval 候选集。
3. Eval Harness 运行断言和 LLM-as-Judge。
4. LLM 可生成改进提案。
5. 人工评审后进入 shadow/canary。
6. 指标达标后 active。
7. 失败可回滚。

---

## 11. 可观测、审计与治理

### 11.1 审计事件

| 审计域 | 典型事件 |
|---|---|
| 工具策略 | policy evaluated、tool denied、approval requested、approval decided、break glass |
| 记忆 | memory injected、remember requested、confirmed、forgotten、gdpr deleted |
| Skill | compiled、injected、activated、eval run、proposal created、promoted、rolled back |
| 长会话 | checkpoint created、restored、rebuilt、deleted、lock timeout |
| 反馈 | feedback submitted、updated、deleted、reported to Langfuse |

### 11.2 指标

关键指标：

- checkpoint restore/write latency
- active thread count
- approval pending count
- approval duration
- tool deny/approval rate
- memory injection latency
- semantic recall timeout rate
- skill activation rate
- skill eval pass rate
- feedback negative rate

### 11.3 管理工作台

企业管理员需要统一入口查看：

- agent 会话状态
- 待审批工具调用
- 策略命中和审计
- 记忆管理和 pending 记忆
- skill 健康度和评估结果
- 用户反馈和差评样本
- 风险告警和合规导出

---

## 12. 安全与合规原则

### 12.1 执行安全

- 所有高风险工具必须经过策略评估。
- 工具定义变更走 `update_tool` API，依赖 DB 写权限 + API 鉴权 + 审计保证不被旁路。
- 策略变更需要版本和审计。
- `task` 和 subagent 不得成为绕过策略的通道。

### 12.2 数据安全

- PII 输入脱敏。
- 工具输出 DLP 扫描。
- 高敏记忆默认不注入。
- 审批 UI 默认展示脱敏参数。
- 查看原文需要二次鉴权和审计。

### 12.3 租户隔离

- 当前项目 P0/P1 可按单租户运行。
- `tenant_id=None` 必须有统一查询语义，不能写出 `tenant_id = NULL` 这种永不命中的 SQL。
- 多租户正式启用前，需要统一 tenant 归一化、策略匹配和审计导出模型。

---

## 13. 数据原则

数据库设计遵循：

- 不新增数据库外键约束。
- 可以新增业务列、唯一约束和查询索引。
- 跨表完整性由 service 层校验。
- 关键业务动作写审计。
- 高频遥测必须聚合、采样或分区。
- checkpoint 表和业务表职责分离。
- 审计表不存高敏原文。

---

## 14. 分期路线

### P0：运行基础与可见性

目标：建立稳定运行底座，不引入复杂审批和自动演化。

范围：

- `AgentRunContext`
- `thread_id` 和 checkpointer 接入
- checkpoint 输入协议
- Todo SSE 可视化
- feedback API
- tool allow/deny 基础策略
- tool wrapper 兜底
- L1/L2 只读/显式记忆注入
- skill 生命周期状态可视化

### P1：治理和观测

目标：让企业能看到 agent 如何使用工具、记忆和 skill。

范围：

- 风险分级
- dry-run 策略
- PII mask 和基础 DLP
- memory audit
- skill usage telemetry
- Langfuse trace 关联
- Prometheus 指标
- 管理员看板

### P2：HITL 和质量闭环

目标：高风险动作可暂停审批，skill 质量可评估。

范围：

- HITL approval
- ApprovalResumeService
- 审批链
- 会话等待态
- Eval Harness
- semantic memory
- episodic summary
- feedback -> eval 候选集

### P3：企业协作和自动演化

目标：提升组织级协作效率。

范围：

- 审批升级、委托、预审批、破窗
- skill variant / canary
- 自动改进 proposal
- memory reflection pending
- team/org memory
- skill dependency 和 package

### P4：合规与规模化

目标：满足更严格的企业部署要求。

范围：

- 合规导出
- WORM 审计
- 高敏 KMS 加密
- 多租户正式启用
- 遥测分区和归档
- 外部工作流集成
- skill marketplace 治理

---

## 15. 关键风险

| 风险 | 影响 | 设计应对 |
|---|---|---|
| checkpoint 与业务消息重复输入 | state 膨胀、摘要异常 | checkpoint 开启时只传本轮新消息 |
| deepagents 默认 subagent 绕过治理 | 高风险工具失控 | 显式受治理 `general-purpose` + tool wrapper 兜底 |
| 原生 MemoryMiddleware 写虚拟文件 | DB 记忆与 checkpoint 分叉 | P0 用自研 memory 注入，写入只走 memory tools |
| Skill 归因不准确 | A/B 和自动演化失真 | run snapshot + tool mapping + trace 多信号归因 |
| 语义召回延迟高 | 首 token 延迟不可控 | L3/L4 超时跳过，L1/L2 先注入 |
| 审批恢复语义不清 | 用户等待态断裂 | ApprovalResumeService 明确恢复和 SSE 输出协议 |
| 高敏数据进入日志 | 合规风险 | 全链路脱敏、二次鉴权、审计 |
| 高频遥测爆表 | 存储和查询退化 | 分区、采样、聚合、归档 |

---

## 16. 成功指标

| 维度 | 指标 |
|---|---|
| 可靠性 | checkpoint 恢复成功率、同 thread 并发冲突率、运行失败率 |
| 透明度 | Todo 面板到达率、审批等待态准确率 |
| 安全 | 高风险工具审批覆盖率、策略误放率、DLP 命中处理率 |
| 质量 | 负反馈率、skill eval pass rate、skill rollback 次数 |
| 记忆 | 记忆确认率、错误记忆撤回率、注入延迟 |
| 运维 | 审批 SLA、审计查询延迟、遥测表增长率 |

---

## 17. 与四份详细设计的关系

本文档是系统级总设计，四份详细设计继续作为专项方案：

- `long-session-design.md`：长会话、Todo、反馈闭环的详细设计。
- `tool-approval-and-acl-design.md`：工具策略、HITL、审批链和审计详细设计。
- `agent-memory-design.md`：长期记忆、注入、反思、合规详细设计。
- `skill-evolution-design.md`：skill 生命周期、遥测、eval、A/B、演化详细设计。

当专项文档与本文档冲突时，以本文档的系统边界和 deepagents 能力边界为准，再回写专项文档修正。
