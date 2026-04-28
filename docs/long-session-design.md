# Q1 Agent 能力增强：长会话 + Todo 可视化 + 反馈闭环

> 文件名 `long-session-design.md` 沿用原命名，实际涵盖 Q1 三项 agent 能力。
>
> **本文档定位**：高层次概览 + 实施状态记录。详细落地方案见各分项文档：
> - `checkpointer-impl-plan.md` — 长会话 4 个 PR 的实施细节
> - `todo-panel-design.md` — Todo 面板的设计方案
> - `checkpoint-monitoring.md` — 运维监控 SQL

---

## 0. 背景

Q1 要交付 3 项能力，本质都是**让用户建立对 agent 执行过程的信任**：

| 能力 | 解决的痛点 | 当前状态 |
|---|---|---|
| 长会话（Checkpointer + 上下文压缩） | "对话历史/agent 思路丢了" / "长对话变慢变贵" | ✅ 已落地 |
| Todo 可视化 | "agent 现在在干什么？还剩几步？" | ✅ 已落地（第一阶段） |
| 反馈闭环 | "答得不好想反馈" / 团队"哪些 app 差评集中" | ❌ 未实现 |

---

## 1. 实施状态汇总

### 已落地

| 模块 | 内容 | PR |
|---|---|---|
| Checkpointer 基础设施 | `AsyncPostgresSaver` + `AsyncConnectionPool` + lifespan | PR-A |
| 数据模型 | `tb_app.enable_long_session`、`tb_conversation.thread_id/checkpoint_status`、`tb_session_audit`、`lg_checkpoint` schema | PR-A |
| Agent 接入 | `AgentApp.run/stream` 接 saver + run() 改 async | PR-B |
| 输入协议 | "只传新消息"切换 + 降级重建路径 + SSE `degraded` 提示 | PR-C |
| 清理路径 | DELETE 级联 + reset API + admin purge + 被遗忘权 | PR-D |
| 进程内 purge 调度 | `CheckpointPurger` + pg advisory lock 多 worker 互斥 | 后续 |
| `max_input_tokens` 注入 | `tb_llm_model.max_input_tokens` → `model.profile` → 摘要按真实窗口比例触发（不再走 170k 兜底） | 后续 |
| MCP tool 超时修复 | `asyncio.timeout` 强制超时（修了 `_run_sync` 静默失效的 bug） | 后续 |
| 卡顿诊断日志 | `[stream] chat_model_*/tool_*` + tool wrapper start/done timing | 后续 |
| Todo 实时面板 | 右侧 panel + 监听 `write_todos` + 启动初始快照 + localStorage 折叠态 | PR-T1/T2 |

### 未落地

详见 §5 未实现项清单。最显眼的：**Part III 反馈闭环整个未做**。

---

## Part I — 长会话（Checkpointer + 上下文压缩）

### I.1 关键决策记录

| 决策 | 选定 |
|---|---|
| Saver 类型 | **`AsyncPostgresSaver`** 唯一（不混用 sync） |
| DB 位置 | **共业务库**，独立 schema `lg_checkpoint`；连接 kwargs `options=-c search_path=lg_checkpoint` 隔离 |
| 表管理 | alembic 只 `CREATE SCHEMA IF NOT EXISTS`；4 张 LangGraph 表由 `saver.setup()` 在 lifespan 启动时幂等创建 |
| 启用粒度 | `tb_app.enable_long_session: int`（默认 0）；**不用** `app_config` JSON |
| `thread_id` 来源 | 会话**首次真实调用**时落地 `str(conversation_id)`，之后永不变；`tb_conversation.thread_id` 字段，唯一索引 |
| 输入协议 | 启用后**只传本轮新消息**；checkpoint 缺失 + 业务消息存在 → 降级重建 + audit |
| `run()` 同步性 | 改 `async def`，上游 `open_api.py` 路由同步改 async |
| Checkpoint 保留 | 默认 30 天 inactivity 后清；后台进程内调度（pg advisory lock 多 worker 互斥） |

### I.2 数据模型

**LangGraph 自带表**（`AsyncPostgresSaver.setup()` 在 `lg_checkpoint` schema 下创建）：

| 表 | 作用 |
|---|---|
| `checkpoints` | 每个 thread 的状态快照（增量） |
| `checkpoint_blobs` | 大对象（消息、文件内容） |
| `checkpoint_writes` | 未提交的写操作 |
| `checkpoint_migrations` | LangGraph 内部迁移版本号 |

**业务侧增量**（alembic `0003_long_session.py`）：

```sql
ALTER TABLE tb_app          ADD COLUMN enable_long_session INT NOT NULL DEFAULT 0;
ALTER TABLE tb_conversation ADD COLUMN thread_id           VARCHAR(64);
ALTER TABLE tb_conversation ADD COLUMN checkpoint_status   VARCHAR(32) NOT NULL DEFAULT 'active';
CREATE UNIQUE INDEX uk_tb_conversation_thread_id ON tb_conversation(thread_id);

CREATE TABLE tb_session_audit (
  id BIGINT PRIMARY KEY,
  conversation_id BIGINT NOT NULL,
  event_type VARCHAR(64) NOT NULL,    -- checkpoint_rebuilt_from_messages / checkpoint_purged / checkpoint_reset
  payload TEXT,
  create_time BIGINT NOT NULL
);
```

**LLM 模型扩展**（alembic `0004_llm_model_max_input_tokens.py`）：

```sql
ALTER TABLE tb_llm_model ADD COLUMN max_input_tokens INTEGER;
```

`checkpoint_status` 状态：
- `active`：正常运行
- `degraded`：曾经历 checkpoint 缺失重建
- `purged`：定时清理已清掉运行态，业务消息保留

### I.3 运行时架构

**`CheckpointerFactory`**（`backend/app/app/checkpointer_factory.py`，进程级单例）：
- `async start()`：开池 + `saver.setup()`
- `def get() -> AsyncPostgresSaver`（同步获取已启动 saver）
- `async close()`
- 模块级 `get_checkpointer_factory()` 提供全局单例

**FastAPI lifespan**（`backend/app/core/lifespan.py`）：启动时调 `factory.start()`、关闭时 `factory.close()`。

**`AgentApp._prepare`** 三方约束生效：
```python
use_checkpoint = bool(req.use_checkpoint and app.enable_long_session and req.thread_id)
if use_checkpoint:
    agent_kwargs["checkpointer"] = self._checkpointer_factory.get()
```

**`thread_id` 透传**：通过 `AgentRunRequest` 直接携带（不引入 `AgentRunContext` 抽象，YAGNI）：

```python
class AgentRunRequest(BaseModel):
    app_id: int = 0
    messages: list[ModelGatewayChatMessage] = []
    variables: dict[str, Any] = {}
    thread_id: str | None = None
    use_checkpoint: bool = False
    degraded: bool = False    # 仅 SSE 提示信号，agent 运行时无视
```

**LangGraph config 装配**：

```python
config = {"callbacks": [handler]}
if use_checkpoint and thread_id:
    config["configurable"] = {"thread_id": thread_id}
```

### I.4 输入协议（关键）

`ConversationService.send_message_stream` 内三分支：

```
长会话开关关:
  messages = 全量历史（_load_history_rows）   ← 老行为，零变更

长会话开关开 + checkpoint 命中:
  messages = [本轮新一句]                     ← LangGraph 从 saver 恢复历史

长会话开关开 + checkpoint 缺失:
  if prior_count <= 1:
      messages = [本轮新一句]                 ← 首次调用
  else:
      messages = 全量历史                     ← 真正降级重建
      conv.checkpoint_status = 'degraded'
      tb_session_audit += 'checkpoint_rebuilt_from_messages'
      SSE metadata.degraded = true
```

### I.5 Summarization

**默认就开着**——`create_deep_agent` 自动挂 `SummarizationMiddleware`。

策略（DeepAgents 默认值）：
- 模型有 `profile.max_input_tokens` → `trigger=("fraction", 0.85)`、`keep=("fraction", 0.10)`
- 没 profile → `trigger=("tokens", 170000)`（兜底）

**关键改进**：`tb_llm_model.max_input_tokens` 字段 + `LangChainUtil.build_chat_model` 注入到 `model.profile`，让私有/国产模型（LangChain 内置注册表里没有的）也能走"按真实窗口百分比触发"路径，不再走 170k 兜底导致小窗模型先抛 `ContextOverflowError` 才 fallback。

**当前不可调**：阈值 0.85 写死在 DeepAgents `compute_summarization_defaults`。可调要 monkey-patch 或上游支持，未做。

### I.6 清理路径

| 操作 | 业务消息 | 反馈 | Checkpoint | 审计事件 |
|---|---|---|---|---|
| `DELETE /conversation/{id}` | 删 | 删 | 删 | 跟会话一起删 |
| `POST /conversation/{id}/reset` | 留 | 留 | 删 | `checkpoint_reset` |
| `POST /conversation/admin/purge` | 留 | 留 | 删 | `checkpoint_purged` |
| `DELETE /user/{id}` | 留（合规决定） | 留 | 删 | 不写 |

**删除顺序**：先删 checkpoint，再删业务行。失败整事务作废，避免出现"业务行没了 / checkpoint 残留无主"的孤儿状态。

### I.7 进程内 purge 调度

`CheckpointPurger`（`backend/app/app/checkpoint_purger.py`）：
- 启动后延迟 60 秒 → 每 24 小时跑一次（`PURGE_INTERVAL_SECONDS`）
- `pg_try_advisory_lock(0xEA51A1C0DE)` 多 worker 互斥
- 触发条件：`update_time < now - PURGE_TTL_DAYS * 86400000` AND `thread_id IS NOT NULL` AND `checkpoint_status != 'purged'`
- HTTP `/admin/purge` 端点保留（运维手动触发，不抢锁）

### I.8 配置项

`backend/.env.example`：

```
# Checkpoint 后台清理
PURGE_ENABLED=true
PURGE_INTERVAL_SECONDS=86400
PURGE_TTL_DAYS=30

# MCP 工具单次调用超时（asyncio.timeout 强制切断）
MCP_TOOL_TIMEOUT_SECONDS=300
```

### I.9 测试矩阵覆盖度

| 场景 | 状态 |
|---|---|
| 开关关：行为不变 | ✅ |
| 开关开：跨轮记忆 | ✅ |
| 跨进程重启 | ✅ |
| Checkpoint 损坏走降级 | ✅ |
| 同会话并发 | ⬜ 依赖 LangGraph thread 锁，未特意验 |
| DELETE 级联 | ✅ |
| 归档 +30 天 purge | ✅ |
| 技能 subagent 持久化 | ✅ |
| 超长对话 summarization | ✅（已通过 max_input_tokens 调小窗模型验证）|
| 被遗忘权（删用户级联）| ✅ |

---

## Part II — Todo 可视化

### II.1 关键决策记录

| 决策 | 选定 |
|---|---|
| 数据来源 | LangGraph state.todos —— `TodoListMiddleware` 维护，由 `write_todos` 工具更新 |
| 实时变更触发 | **监听 `write_todos` 工具的 `on_tool_end` 事件**（不走 LangGraph state diff，简单稳） |
| 历史恢复 | **不实现 GET 端点**；流启动时探测 checkpoint，有 todos 则发一条初始快照 SSE |
| 工具调用展示 | 聊天泡泡里 `write_todos` 工具条**保持原样**——继续作为时间序"修改日志" |
| UI 布局 | **右侧栏**（不是上方/底部/弹层）；可折叠成 40px 窄条 |
| 折叠态持久化 | localStorage `todoPanelCollapsed` |
| 节流 | RAF 合帧避免 burst 闪烁 |
| 显示条件 | 仅 agent 应用 + todos 非空时显示 |

### II.2 后端

**SSE 事件**：`event: todo_update` / `data: {"todos": [...]}`，全量快照（不做 diff）。

**触发点**（`agent_app.stream`）：
- 流启动时若 checkpoint 有 todos → 发初始快照
- `on_tool_end` 分支检测 `name == "write_todos"` → 取入参 `todos` 全量发送

**辅助函数** `_serialize_todos(todos)`：把 LangChain `Todo` TypedDict 列表归一化为 `[{content, status}]`。

### II.3 前端

**新组件 `TodoPanel.vue`**（`frontend/src/components/`）：
- 状态图标：`○` (pending) / `⠋` (in_progress, 旋转) / `✓` (completed)
- 进度数字 `已完成/总数`
- 折叠 → 40px 窄条仅显示图标 + 数字
- localStorage 持久化折叠态
- 移动端（<768px）改为底部抽屉，最大 50vh

**`AssistantView.vue` 集成**：
- 局部 `todos` ref（不引入 Pinia store，YAGNI）
- `showTodoPanel` computed：`agent` 类型 + 非空
- RAF 节流 `applyTodoUpdate`
- SSE 处理新增 `case "todo_update"`
- 切会话 / 新建 / 删除时清空 `todos.value = []`
- CSS：`chat-main` 改 flex row，新增 `chat-content` 列容器，TodoPanel 作为右侧 sibling

### II.4 Status 范围

只支持 `pending | in_progress | completed`。`failed` 状态在原设计里有提，**未实现**——LangChain 的 `Todo` TypedDict 本身只有这三个值，没有 `failed`。

### II.5 测试

| 场景 | 状态 |
|---|---|
| agent 应用 + 长会话 ON 首次触发 write_todos | 联调中 |
| 同会话第二轮 write_todos | 联调中 |
| 切到 LLM/RAG 应用 | 联调中 |
| 切回原会话 + 发消息恢复 panel | 联调中 |
| 长会话 OFF + write_todos | 联调中（流期间显示，结束清空） |
| 折叠后刷新页面 | 联调中 |
| 移动端底部抽屉 | 联调中 |
| `write_todos` 工具调用泡泡仍显示 | 联调中（独立于右栏）|

---

## Part III — 反馈闭环（**未实现**）

整章保留原设计供后续 PR 参考，但当前**未实现任何代码**：

- ❌ `tb_message_feedback` 表
- ❌ `tb_conversation_message.langfuse_trace_id` 字段
- ❌ `POST /conversation/{cid}/message/{mid}/feedback` 端点
- ❌ 管理员看板 API
- ❌ Langfuse score 上报
- ❌ 前端 👍/👎 按钮 + reason_tags 表单

原设计参考文档 git 历史（commit 之前的版本），不在本文档展开。后续如果做反馈闭环，重新立项写新设计。

---

## 5. 未实现项清单（按 Part 分组）

### Part I 未实现

| 项 | 说明 | 影响 |
|---|---|---|
| 自定义 summarization 阈值 | DeepAgents 写死 0.85，可调要 monkey-patch；未做 | 当前默认值够用，灰度数据观察后再说 |
| Summarization 监控指标接入（Langfuse callback） | 仅日志，没有结构化指标 | 通过 hang 诊断日志能看到 chat_model_end 的 elapsed |
| 同 thread_id 并发显式锁 | 依赖 LangGraph 内部 thread 锁；未在 service 层加 PG advisory / Redis lock | 框架级保证已够用；高并发场景出问题再加 |
| Checkpoint 表分库 | 业务库共用 | 当前数据量足够；上量后再评估 |
| `GET /conversation/{id}/agent-state` 调试端点 | 设计中有，**未实现** | 调试靠 `lg_checkpoint.*` SQL + 日志即可 |
| 自定义压缩模型（cheap summary model）| 仍用主 agent 同模型摘要 | 长会话用贵模型时成本可见，目前可接受 |

### Part II 未实现

| 项 | 说明 |
|---|---|
| `failed` 状态 | LangChain `Todo` 不支持，agent 不会写 `failed` |
| 嵌套 todos（subagent）| 子代理 state 独立，主面板不显示子代理任务 |
| Pinia store 全局管理 | 当前 `AssistantView` 局部 ref；多 view 复用时再考虑 |
| 历史时间轴 / 修改日志 | 看聊天泡泡里 `write_todos` 工具调用即可，不另做 |
| 跨会话 todo 全局看板 | 不在范围 |
| `agent-state` 端点恢复历史 | 改用流启动时 SSE 初始快照；纯阅读不发消息时面板留空（接受） |

### Part III 整体未实现

详见 §Part III 列表。

---

## 6. 后续联动

- **工具审批 / ACL**（`tool-approval-and-acl-design.md`）：审批暂停/恢复直接建立在 Checkpointer 之上——中断 = 暂停后保存 checkpoint；恢复 = 按 thread_id 拉起继续跑。Q2 工作。
- **Memory 层情景摘要（L4）**：会话归档时由本层触发后台摘要任务，依赖会话归档状态机（**当前未实现**，purge 暂用 inactivity 代替）。
- **Eval harness**：差评消息进 eval 候选集，前置依赖反馈闭环。
- **OpenSandbox 沙盒接入**：技能脚本执行环境，已规划设计，待实施。

---

## 7. 关键文件索引

后端：
- `app/app/checkpointer_factory.py` — Saver 工厂
- `app/app/checkpoint_purger.py` — 进程内定时清理
- `app/app/agent_app.py` — Agent 主体（含 `_serialize_todos`、SSE 推送、hang 诊断日志）
- `app/app/langchain_util.py` — `build_chat_model` 注入 `max_input_tokens` 到 profile
- `app/service/conversation_service.py` — 输入协议分支 + 降级重建 + 清理 API
- `app/core/lifespan.py` — 启动 saver + purger
- `app/core/sse.py` — `SSE_EVENT_TODO_UPDATE` 等常量
- `app/core/mcp_client.py` — 真生效的工具超时
- `alembic/versions/0003_long_session.py` — 长会话基础表
- `alembic/versions/0004_llm_model_max_input_tokens.py` — 模型窗口字段

前端：
- `src/components/TodoPanel.vue` — Todo 右栏
- `src/views/assistant/AssistantView.vue` — chat 主页（含右栏集成）
- `src/views/setting/LlmManageView.vue` — `max_input_tokens` 编辑入口

文档：
- `docs/checkpointer-impl-plan.md` — 长会话 4 个 PR 的实施细节
- `docs/todo-panel-design.md` — Todo 面板的设计方案
- `docs/checkpoint-monitoring.md` — 运维监控 SQL
