# 工具治理设计（Tool Governance）

## 1. 设计原则

智能体本质是自动执行的，**不在工具调用上叠加多级审批工单流**——审批工单把"出事追责"转嫁给审批人，与 agent 自治价值冲突。改用三层治理：声明式 ACL、原生 HITL、工具白名单。

## 2. 需求定义

### 2.1 声明式 ACL

按工具关联一组规则，运行期同步评估，毫秒级返回 `allow / deny / require_hitl`。

**支持的条件维度**：

| 维度 | 表达 | 示例 |
|---|---|---|
| 参数 | 等值、正则匹配、数值边界、字符串前后缀、枚举集合、长度边界 | `parameter.amount > 10000` / `parameter.email REGEX /@gmail\.com$/` |
| 时间窗 | 小时区间、星期几、节假日（按时区） | `time.hour BETWEEN 9 AND 18 IN_TZ 'Asia/Shanghai'` |
| 调用方 | user_id / 角色 / 用户组 | `user.role IN ['sales', 'support']` |
| 网络 | 出站 URL 白/黑名单、域名匹配 | `url.host ENDS_WITH '.internal'` |
| 上下文 | 同一对话内的前序工具调用链 | `prior_tools CONTAINS 'query_db'` |

**动作类型**：
- `deny`：直接拒绝；agent 拿到 `PermissionDenied` 作为 tool result，前端展示"无权操作: <规则原因>"
- `allow`：显式放行（覆盖默认 risk_level）
- `require_hitl`：升级为人在回路确认（即使 risk_level 是 LOW）

**评估顺序**：规则集按 `priority` 字段降序匹配，第一条命中决定结果；全部未命中时按工具默认风险等级（§2.4）走默认动作。

**模式**：
- `active`：决策生效
- `shadow`：决策只记录到 `tb_tool_audit`，实际放行（用于新规则上线前观察命中率）
- `dry-run`：全局开关，所有规则只记录不阻断

**版本与所有权**：规则修改保留版本快照（行级软改，新行 + 旧行标记 superseded）；所有权按 `tool.owner_user_id` / `app.admin_role` 鉴权，普通用户不能改。

### 2.2 原生 HITL

不是独立工单流，是 agent 执行链路里的对话内停顿。

**触发条件**（满足任一）：
- 工具默认 `risk_level ∈ {Med, High}`
- ACL 规则命中 `require_hitl`

**触发后行为**：
1. `PolicyMiddleware` 调用 LangGraph `interrupt()`，**当前 checkpoint 自动落盘**
2. SSE 推送 `tool_hitl_required` 事件，载荷含 tool_name、参数、规则触发原因、风险描述
3. 前端在对话主区直接渲染确认面板（**不弹窗、不工单**），用户视野不离开当前会话
4. 用户响应：`confirm`（按原参数执行）/ `modify`（修改参数后执行）/ `reject`（取消调用，agent 拿到 `UserRejected` tool result 自行规划下一步）
5. 服务端通过 LangGraph `astream_events` 续跑（thread_id 不变），状态机持续连贯

**超时处理**：超过 `tool.hitl_timeout_seconds`（默认 300s）未响应 → 视为 `reject`，agent 拿到超时错误。超时不视作"通过"，避免用户离开后被默认放行。

**用户操作记录**：每次 HITL 响应（含超时）都落 `tb_tool_audit`：tool_id、参数快照、决策、决策人、耗时、conversation_id、run_id。

**与 Checkpointer 强耦合**：依赖 Session Layer 长会话能力；**长会话开关关闭时不允许暴露 Med/High 工具**（启动期校验），避免出现"中断了但恢复不了"的死局。

### 2.3 工具白名单

**真正不可逆 + 高影响的操作不暴露为 agent 工具**——通过专属人工 UI 完成，不设审批流。

判定标准（满足任一就走人工 UI，不进 agent）：
- 操作不可逆且无 staging / undo 路径（删整张库、撤销已发邮件、转账已确认）
- 单次操作影响 > 1000 用户 / 实体（批量删用户、群发广告）
- 触发法律 / 合规义务（金融转账 ≥ 阈值、数据出境、生产配置变更）

**决策机制**：工具注册时由 `tool.owner_user_id` 或 `app.admin_role` 显式设置 `tool.exposed_to_agent: bool`。设计期决定，运行期不可改（改要走完整发布流程）。新工具默认 `exposed_to_agent = false`，主动开启。

**与风险分级的关系**：HIGH 工具**强烈建议** `exposed_to_agent = false`；非要暴露则强制 HITL + 强审计。

### 2.4 风险分级

**复用现有 `tb_tool.risk_level` 字段**（已存在的 VARCHAR），service 层校验枚举值 `LOW / MED / HIGH`。不新建列。

工具注册时按默认风险标注：

- **LOW**：纯读、查询、列表、健康检查类；自动放行
- **MED**：可逆写、可撤销、有 staging 中间态（保存草稿、加入队列待发）；HITL 触发对话内确认
- **HIGH**：不可逆、外发、有金额 / 凭证 / 生产副作用；建议不暴露给 agent；非要暴露强制 HITL + 强审计

**最终等级 = max(工具默认 risk_level, 策略命中时显式覆盖, 参数启发式)**

参数启发式示例：金额超阈值升 HIGH；SQL 含 `DROP / TRUNCATE / DELETE WHERE 1=1` 升 HIGH；外发域名不在白名单升 MED。具体启发规则在 ACL 里声明，不硬编码。

**工具变更防篡改**：靠基础设施层（DB 写权限、API 鉴权 + 审计）保证 `tb_tool` 不被绕开 `update_tool` API 的渠道改动；不在 agent 运行期做工具 schema 哈希校验（曾考虑过 fingerprint + 双人核准方案，操作成本高于实际收益，已废弃）。

### 2.5 审计流（`tb_tool_audit`）

**追加写**（append-only）；本表覆盖工具治理决策，与现有 `tb_session_audit`（会话生命周期事件，如 checkpoint 重建/清理）并列，互不替代。

**事件类型枚举**：

- `tool_invoked`：通过所有检查、实际执行
- `policy_denied`：ACL 命中 deny
- `hitl_required`：触发 HITL（含 SSE 推送时间）
- `hitl_confirmed` / `hitl_modified` / `hitl_rejected` / `hitl_timeout`：用户响应
- `policy_modified`：策略表变更（who、when、diff）

**字段**：event_type、tool_id、conversation_id、run_id、user_id、parameters_snapshot（JSON）、decision_reason、matched_rule_id、create_time。`parameters_snapshot` 进入前过 PII 脱敏（设计期定义脱敏规则）。

**保留期**：合规要求长期保留（默认 3 年）；不参与运行态清理。

## 3. 数据模型

新增表（snowflake id + 业务库通用 audit 列：`create_time / update_time / create_user / update_user`）：

| 表 | 关键字段 |
|---|---|
| `tb_tool_policy` | `tool_id`、`priority`(int)、`action`(deny/allow/require_hitl)、`when_ast`(TEXT, JSON)、`reason`、`mode`(active/shadow)、`version`、`superseded_by_id`(NULL=当前版本)、`owner_user_id` |
| `tb_tool_audit` | `event_type`、`tool_id`、`conversation_id`、`run_id`、`user_id`、`app_id`、`parameters_snapshot`(TEXT JSON, PII 脱敏)、`decision_reason`、`matched_rule_id` |

**复用现有字段**：`tb_tool.risk_level` —— 工具默认风险等级（不新建列）。

不新增审批单 / 工具指纹相关表。

## 4. 运行时

`PolicyMiddleware`（LangGraph `AgentMiddleware`）在 `before_tool` hook：

```
1. 跑该工具的 ACL 规则（按 priority），第一条命中决定动作
2. 全部未命中 → 按工具默认 risk_level 决定（LOW 放行 / Med, High 走 HITL）
3. require_hitl 路径：interrupt() 暂停 → checkpoint 落盘 → SSE 推 tool_hitl_required
   用户响应到达 → astream_events 续跑
4. 全程结果落 tb_tool_audit
```

## 5. ACL 规则形态（结构化 AST）

DSL 的**唯一存储与传输形态**是结构化 JSON AST。前端表单生成 AST，后端按 AST 直接评估，无字符串解析、无 eval。

### 5.1 节点类型

```jsonc
// 1. 比较节点（叶子）
{
  "type": "Compare",
  "op": "<算子>",                  // 见 §5.2
  "var": "<上下文变量>",            // 见 §5.3
  "value": <字面量 | 数组>          // 类型按算子要求
}

// 2. 逻辑节点（v1 仅 And；v2 加 Or / Not）
{
  "type": "And",
  "conditions": [<节点>, <节点>, ...]
}
```

### 5.2 算子表（P0 子集）

| 算子 | 适用变量类型 | value 类型 |
|---|---|---|
| `EQ` / `NEQ` | 任意 | 同变量类型 |
| `GT` / `LT` / `GTE` / `LTE` | number | number |
| `BETWEEN` | number | `[low, high]` 数组 |
| `IN` / `NOT_IN` | 任意 | 数组 |
| `MATCHES` | string | 正则字符串 |
| `STARTS_WITH` / `ENDS_WITH` / `CONTAINS` | string | string |

任一变量取值缺失 / 类型不匹配 → 该 `Compare` 节点返回 false（不抛异常）。

### 5.3 上下文变量表（P0 子集）

| 变量 | 含义 |
|---|---|
| `parameter.<key>` | 工具调用参数（按当前工具 parameters schema 暴露具体 key） |
| `time.hour` / `time.weekday` | 当前服务器时间（默认 UTC，工具可声明 `tz`） |
| `user.id` / `user.role` | 调用者身份 |

### 5.4 完整规则示例（一个工具的策略）

```jsonc
{
  "tool_id": "...",
  "mode": "active",
  "rules": [
    {
      "priority": 100,
      "action": "deny",
      "when": {
        "type": "Compare", "op": "ENDS_WITH",
        "var": "parameter.to", "value": "@competitor.com"
      },
      "reason": "不允许向竞品域发送邮件"
    },
    {
      "priority": 90,
      "action": "deny",
      "when": {
        "type": "Compare", "op": "MATCHES",
        "var": "parameter.body", "value": "信用卡号|身份证号"
      },
      "reason": "内容含 PII"
    },
    {
      "priority": 80,
      "action": "require_hitl",
      "when": {
        "type": "Compare", "op": "GT",
        "var": "parameter.amount", "value": 10000
      },
      "reason": "大额操作需用户确认"
    },
    {
      "priority": 50,
      "action": "allow",
      "when": {
        "type": "And",
        "conditions": [
          { "type": "Compare", "op": "BETWEEN", "var": "time.hour", "value": [9, 18] },
          { "type": "Compare", "op": "IN", "var": "user.role", "value": ["sales", "support"] }
        ]
      }
    }
  ]
}
```

### 5.5 编辑形态分工

- **UI 编辑**：form-based 表单（见 PR-G4），管理员看不到 AST
- **API 调用 / CI / 跨环境迁移**：直接传 JSON AST
- **管理员只读视图**：折叠展示 AST（PR-G4 高级模式）

## 6. 开发大纲

### 6.1 阶段总览

| 阶段 | 主题 | 前置依赖 | 预估工作量 |
|---|---|---|---|
| **P0** | 声明式 ACL 基础 | 无 | ~6.5 人日 |
| **P1** | 原生 HITL 对话内确认 | P0；Session 长会话已落地（已交付）| ~5 人日 |
| **合计** | | | **~11.5 人日（约 2 周冲刺）** |

### 6.2 P0 ACL 基础（生产前必须）

#### PR-G1：数据模型与 ORM（1 人日）

- alembic 迁移 `0005_tool_governance.py`：建 `tb_tool_policy` / `tb_tool_audit` 两张表（字段见 §3）
- `app/db/schema.py`：对应 ORM
- **复用现有 `tb_tool.risk_level`**：不新建风险列；service 层加枚举值校验（`LOW / MED / HIGH`）；批量回填存量为空的工具默认 `LOW`
- 索引：`tb_tool_policy (tool_id, version)`；`tb_tool_audit (tool_id, create_time)` / `(conversation_id, create_time)`

**出货门禁**：`make db-upgrade` 干净通过；ORM 导入冒烟；存量 `tb_tool.risk_level` 全量非空。

#### PR-G2：DSL 解析器（1.5 人日）

- 新模块 `app/app/policy_dsl.py`
- 支持算子见 §5.2，AST 节点见 §5.1
- 输入：JSON AST；输出：递归求值闭包，运行期纯 Python 调用，**不用 eval**
- 类型 / 缺失值容错：所有 Compare 失败一律返回 false，永不抛异常

**出货门禁**：100% 行覆盖；所有错误条件返回 false（不抛异常）。

#### PR-G3：PolicyMiddleware 骨架（1.5 人日）

- 新模块 `app/app/policy_middleware.py`，继承 LangGraph `AgentMiddleware`
- 实现 `before_tool` hook，按 §4 流程
- active 路径：deny → 抛 `PermissionDenied`，agent 拿到作为 tool result；allow → 透传
- shadow 模式：deny 决策只写 audit 不阻断
- 集成进 `agent_app.py._prepare`：`create_deep_agent(..., middleware=[PolicyMiddleware(...), ...])`
- 集成测：mock 工具 + 一组规则验证 deny / allow / shadow 三个路径

**出货门禁**：mock 工具下 deny 拒绝 / shadow 不拒绝 / allow 透传分别验证；audit 落库。

#### PR-G4：策略 CRUD API + 前端表单编辑（2.5 人日）

**后端**：
- API `/api/v1/tool/{id}/policy` GET/PUT；接收 JSON DSL（YAML 仅 API 调用方 / CI / 迁移脚本可用，UI 不暴露）
- 服务层 `PolicyService` 处理版本快照（行级软改）
- 鉴权：`tool.owner_user_id` 或 `app.admin_role`

**前端 form-based 编辑器**（不让管理员手写 YAML）：
- `ToolManageView.vue` 加策略编辑 tab
- 多规则增删 + 拖拽排序（按 priority）
- 每条规则的字段：
  - **动作**：下拉 `允许 / 拒绝 / 需要 HITL 确认`
  - **条件变量**：下拉，按当前工具的 parameters schema 自动列出 `parameter.<key>` + 内置变量（`time.hour`、`time.weekday`、`user.id`、`user.role`）
  - **算子**：按变量类型动态变（数值给 `>`/`<`/`BETWEEN`；字符串给 `==`/`MATCHES`/`STARTS_WITH`/`ENDS_WITH`/`CONTAINS`；集合给 `IN`）
  - **值**：单 input；集合算子时多输入 / 标签 chip
  - **原因**：纯文本，给运行期 deny 的前端提示用
- 多条件 v1 简化为隐式 AND；OR / 嵌套留 v2
- mode 切换（active ↔ shadow）独立按钮，避免误触发

**高级模式（可选展开）**：
- 给开发者一个折叠的 YAML 视图（只读 + 复制按钮），方便贴到 CI / 跨环境迁移
- 不开放手写编辑：表单 → DSL 是单向 source-of-truth

**出货门禁**：
- 保存非法 DSL 报错明确（指出是哪条规则哪个字段）
- 切 mode 立刻生效
- 版本切换 UI 可读，能 diff
- 表单生成的 DSL 和后端解析结果对账一致（自动化测试覆盖）

### 6.3 P1 原生 HITL（依赖 Session）

#### PR-G6：interrupt + SSE 协议（2 人日）

- `PolicyMiddleware` 第二、三步：`risk_level >= MED` → `langgraph.interrupt(reason=..., tool_input=...)`
- `agent_app.stream()` 检测 `__interrupt__` 事件 → SSE 推 `tool_hitl_required`，载荷含 tool_name / 参数 / 触发原因 / hitl_id（=tool_call_id）
- checkpoint 自动落盘（LangGraph 行为）；流主动结束
- 续跑端点 `POST /api/v1/conversation/{cid}/hitl/{hitl_id}/respond`：body = `{ action: confirm|modify|reject, parameters?: {...} }`
- 服务端调 `agent.astream_events(..., {"resume": ...})` 续跑，新流推剩余事件
- audit 写 `hitl_required` / `hitl_confirmed` / `hitl_modified` / `hitl_rejected`

**出货门禁**：完整 confirm 路径走通；modify 路径修改参数后调原工具；reject 路径 agent 拿到 `UserRejected` 错误。

#### PR-G7：前端 HITL 确认面板（2 人日）

- 新组件 `HitlConfirmCard.vue`：内嵌在聊天泡泡，**不弹窗**
- 展示：tool name、参数（可编辑）、触发规则原因、风险等级（颜色区分）
- 三个动作按钮：确认 / 修改后确认 / 拒绝；调对应 `respond` 端点
- 提交后展示等待状态，新 SSE 接续渲染

**出货门禁**：3 种用户响应 UI 走通；网络断线后续流恢复确认面板状态。

#### PR-G8：HITL 超时（1 人日）

- 入参 `tool.hitl_timeout_seconds`（默认 300）
- 服务端在创建 hitl 时记录 deadline；定时任务扫超时未响应的 hitl_id → 调用 `respond(reject)` 续跑
- audit 写 `hitl_timeout`
- 跨进程安全：用 `pg_try_advisory_lock(<hitl_id 的 hash>)` 互斥，避免多 worker 重复触发

**出货门禁**：手动设 timeout=10s，不响应 → 10s 后 agent 自动收到拒绝。

### 6.4 优先级与并行度

```
                  P0（必做）
                      │
              PR-G1 → G2 → G3 → G4
                            │
                            ▼
                    P1 原生 HITL
                  PR-G6 → G7 → G8
```

**关键路径**：PR-G1 → G2 → G3 → G6 → G7。
**并行机会**：G4（CRUD/UI）可与 G3 部分并行。
**预计**：单人 ~1.5 周完成 P0，~1 周完成 P1，合计 ~2.5 周。

### 6.5 灰度策略

| 阶段 | 策略 |
|---|---|
| P0 上线 | 全部新建策略 `mode=shadow`；命中数据收集 ≥ 2 周 |
| P0 → active | 按工具逐个切 active；每个工具切换后观察 ≥ 7 天，无误拒再下一个 |
| P1 上线 | 仅 1-2 个内部测试 app 启用 HITL；观察 2 周 |
| P1 全量 | 按 app 逐个开 |

**全局回滚**：PolicyMiddleware 默认始终挂载；如需紧急回滚，将所有现存策略改为 `mode=shadow`（仅记审计、不阻断），即可让所有工具调用按默认风险路径放行。代码级回滚需还原 PolicyMiddleware 挂载点。

## 7. 验收标准（出货门禁汇总）

每个 PR 进生产前必须满足：

- 单元测试覆盖率 ≥ 80%
- 关键路径有集成测试（mock 工具 + 模拟 agent.invoke）
- 有独立 feature flag（可单独关）
- 关键事件落 `tb_tool_audit`，可 SQL 自查
- 灰度方案写入 PR 描述

## 8. 风险

- **DSL 表达力不足** → 先 shadow 跑真实数据，按命中率迭代规则形态
- **HITL 中断打断 agent 体验** → 仅 Med/High 触发；LOW 自动放行
- **HITL 超时被默认放行** → 强制 timeout = reject，避免误放行
- **PolicyMiddleware 性能开销** → P0 阶段每次工具调用增加 < 20ms（含 DSL 解析 + DB 读 + audit 写），超出改异步审计

## 9. 与其他模块协作

- **Session 长会话**：HITL 暂停-恢复直接复用 Checkpointer；长会话开关关闭时禁止暴露 Med/High 工具
- **Memory**：记忆读写工具同样经过 PolicyMiddleware 治理
- **Skill**：高风险技能发布前过策略评审；技能内嵌工具按本设计统一治理
- **观测**：`tb_tool_audit` 数据上报观测平台，与 Langfuse trace 关联（同一 run_id）
