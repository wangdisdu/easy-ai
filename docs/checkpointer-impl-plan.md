# P0-1 实施计划：LangGraph Checkpointer 接入

> 本文档是 Q1 长会话（见 `long-session-design.md`）交付拆分后的第一步实施计划，只覆盖 Checkpointer 基础接入，不涉及 Todo 可视化和反馈闭环。

---

## 1. 目标与范围

**目标**：让启用长会话的应用从第二轮起**只传本轮新消息**，agent 运行态（messages、todos、虚拟文件、工具中间态）跨轮持久化在 Postgres，存量应用默认行为不变。

**范围内**：
- AsyncPostgresSaver 接入、连接池管理、lifespan 管理
- `tb_app.enable_long_session` 开关
- `tb_conversation.thread_id` 字段
- `AgentApp._prepare` / `run` / `stream` 的 checkpointer 接线
- `conversation_service.send_message_stream` 输入协议切换 + 降级重建
- `run()` 由 sync 改 async（含上游 API 路由）
- Checkpoint 清理与删除策略

**范围外**（后续 PR 处理）：
- Todo SSE 实时同步（独立 PR）
- 反馈中心
- 会话生命周期状态机细化
- 上下文压缩策略替换

---

## 2. 决策记录

| # | 决策点 | 选定方案 |
|---|---|---|
| 1 | Saver 类型 | `AsyncPostgresSaver`（唯一）|
| 2 | 数据库位置 | 和业务库共库，建独立 schema `lg_checkpoint` |
| 3 | Checkpoint 表管理 | alembic 迁移贴 `SETUP_QUERIES`，不跑 `setup()` |
| 4 | `thread_id` 字段 | `tb_conversation` 新增 `thread_id VARCHAR(64) NULL`，**会话第一次被真正调用时**落地 `str(conversation_id)`，之后永不变；有唯一索引 |
| 5 | 开关粒度 | `tb_app.enable_long_session INT NOT NULL DEFAULT 0` |
| 6 | Message 输入协议 | 开关开 + checkpoint 存在 → 只传本轮新消息；checkpoint 缺失 → 从业务消息表降级重建，发 audit + SSE 标 `degraded:true` |
| 7 | Checkpoint 保留期 | 会话归档日 +30 天后清 checkpoint；业务消息与反馈不受影响；被遗忘权立即清 |
| 8 | `run()` sync→async | 改 async，上游 `open_api.py` 对应路由也改 async |

---

## 3. 数据模型变更（一条 alembic 迁移）

**业务库变更**：

```sql
ALTER TABLE tb_app ADD COLUMN enable_long_session INT NOT NULL DEFAULT 0;

ALTER TABLE tb_conversation ADD COLUMN thread_id VARCHAR(64) NULL;
ALTER TABLE tb_conversation ADD COLUMN checkpoint_status VARCHAR(32) NOT NULL DEFAULT 'active';
-- checkpoint_status: active / degraded / purged
CREATE UNIQUE INDEX uk_tb_conversation_thread_id ON tb_conversation(thread_id);
```

**Checkpoint schema（仅建 schema，表由 `setup()` 在启动时建）**：

```sql
CREATE SCHEMA IF NOT EXISTS lg_checkpoint;
-- 4 张 LangGraph 内部表（checkpoints / checkpoint_blobs /
-- checkpoint_writes / checkpoint_migrations）不在 alembic 里 DDL，
-- 改由 AsyncPostgresSaver.setup() 在 lifespan 启动时幂等创建。
```

**为什么不贴 `SETUP_QUERIES` 进 alembic**（一处刻意偏离原计划）：

- `setup()` 内部用 `checkpoint_migrations` 版本表做迁移管理，**幂等且跨版本自动升级**
- 若把 DDL 抠出来放到 alembic，每次升级 `langgraph-checkpoint-postgres` 都得手工同步，脆
- LangGraph 官方文档也是推荐 `setup()` 路径

实施层面：alembic 只 `CREATE SCHEMA IF NOT EXISTS`；`CheckpointerFactory.start()` 第一次调用时 `await saver.setup()`（落在 FastAPI lifespan 里），后续重启 setup 仍幂等。

**新表 `tb_session_audit`**（为后续 Policy 层审计复用留好位置）：

```sql
CREATE TABLE tb_session_audit (
  id BIGINT PRIMARY KEY,
  conversation_id BIGINT NOT NULL,
  event_type VARCHAR(64) NOT NULL,   -- checkpoint_rebuilt_from_messages / checkpoint_purged / ...
  payload TEXT NULL,                  -- JSON
  create_time BIGINT NOT NULL
);
CREATE INDEX idx_tb_session_audit_conv ON tb_session_audit(conversation_id, create_time);
```

---

## 4. 代码结构变更

### 4.1 新增模块

- `backend/app/app/checkpointer_factory.py`
  - `CheckpointerFactory`：进程级单例，持有 `AsyncConnectionPool` + `AsyncPostgresSaver`
  - 接口：
    - `async def start()`：开池 + 调 `saver.setup()`（幂等建 4 张 LangGraph 表）
    - `def get() -> AsyncPostgresSaver`：同步取已就绪 saver；未 start 时抛 `RuntimeError`
    - `async def close()`：关池
  - 连接串取自 `settings.database_url`（剥掉 `+psycopg` 后缀），`options=-c search_path=lg_checkpoint`
  - 模块级访问器 `get_checkpointer_factory()` 提供共享单例，AgentApp 默认从这里取

- `backend/app/core/lifespan.py`（FastAPI `lifespan` context）
  - 启动时调 `await factory.start()`（含 `setup()` 建表）；同时保留原 `ensure_default_admin()` 种子
  - 关闭时调 `await factory.close()`

### 4.2 改造模块

- `backend/app/app/agent_app.py`
  - `AgentApp.__init__` 增加 `checkpointer_factory: CheckpointerFactory | None`
  - `_prepare` 签名增加 `thread_id: str | None`、`use_checkpoint: bool`
  - `run` 改为 `async def`；通过 `factory.get()` 拿 saver（同步），用 `agent.ainvoke` 跑
  - `create_deep_agent(..., checkpointer=saver if use_checkpoint else None)`
  - 调 agent 时 `config={"configurable": {"thread_id": thread_id}, "callbacks": [...]}`

- `backend/app/service/conversation_service.py`
  - `send_message_stream` 内按 `app.enable_long_session` 分支：
    - 开：首次调用时为 `TbConversation.thread_id` 赋值（`str(conversation_id)`）；探测 checkpoint，存在则 messages 只带一条新消息，不存在走降级重建并写 audit
    - 关：沿用今天的全量历史组装
  - `delete_conversation` 级联删 checkpoint（`await saver.adelete_thread(thread_id)`）

- `backend/app/api/open_api.py`
  - `/api/v1/open/agent/run` 路由改 `async def`，`AgentApp.run` 的调用点加 `await`
  - 其他已经是 async 的路由（`stream` 相关）只调整参数透传

- `backend/app/model/open_model.py`
  - `AgentRunRequest` 增加：
    - `thread_id: str | None = None`
    - `use_checkpoint: bool = False`
    - `degraded: bool = False`（仅作 SSE metadata 提示信号，agent 运行时无视）
  - 保持默认值向后兼容

### 4.3 清理路径（统一在 `ConversationService` 里，未起独立后台任务进程）

- `delete_conversation`（async）：先 `adelete_thread`，再删业务行（含 `tb_session_audit`）；checkpoint 删失败整事务作废
- `reset_conversation`（async）：清 checkpoint，置 `checkpoint_status='active'`，业务消息保留，写 audit `checkpoint_reset`
- `purge_expired_checkpoints(ttl_days=30)`（async）：暴露为 `POST /api/v1/conversation/admin/purge` 端点
  - **当前用 `update_time` 不活跃为代理条件**（会话归档状态机未落地，待后续 PR 切换为 archived + ttl_days）
  - 写 audit `checkpoint_purged`
- `cascade_delete_user_checkpoints(user_id)`（async）：被遗忘权触发点，由 `user_service.delete_user` 级联调用
- 后台调度（cron / k8s CronJob 调 `/admin/purge`）由 ops 层负责，不在 backend 进程内

---

## 5. 关键流程

### 5.1 正常路径（开关开 + checkpoint 存在）

```
用户发消息
  → send_message_stream
  → TbConversation 没 thread_id 则赋值
  → saver.aget_tuple({thread_id}) 命中
  → payload.messages = [new_user_msg]
  → AgentApp.stream(..., thread_id=tid, use_checkpoint=True)
  → create_deep_agent(..., checkpointer=saver)
  → agent.astream_events(payload, config={configurable:{thread_id:tid}, callbacks:[...]})
  → 每个 node 后 saver 自动落盘；SSE 推 token/tool
```

### 5.2 降级路径（开关开 + checkpoint 缺失）

```
saver.aget_tuple({thread_id}) = None
  → 从 tb_conversation_message 取最近 N 条 role in (user, assistant)
  → payload.messages = rebuilt_history + [new_user_msg]
  → SSE metadata 带 degraded:true
  → tb_session_audit 写 checkpoint_rebuilt_from_messages
  → 正常 astream_events 之后，saver 从新基线继续写
```

### 5.3 清理路径

```
当前实现（会话归档状态机未落地的临时方案）：
  ops 配置的 cron / k8s CronJob 定时调 POST /api/v1/conversation/admin/purge
  → 服务方法扫 update_time < now - ttl_days * 86400000 且 thread_id 非空
  → 对每条 saver.adelete_thread(thread_id)
  → checkpoint_status='purged'，写 audit checkpoint_purged
  → 业务消息、反馈不动

未来（会话状态机交付后切换条件为）：
  status='archived' AND update_time < archived_at + ttl_days
```

---

## 6. 协议契约变更

| 位置 | 变更 | 兼容性 |
|---|---|---|
| `AgentRunRequest` | `+ thread_id`、`+ use_checkpoint`、`+ degraded` | 默认值兼容老调用方 |
| `tb_app.enable_long_session` | 新字段默认 0 | 存量应用完全不受影响 |
| SSE `metadata` 事件 | `+ thread_id: str`、`+ degraded: bool` | 前端忽略未知字段即可 |
| `DELETE /api/v1/conversation/{id}` | 行为扩展：同时删 checkpoint | 对外行为更彻底，不破契约 |
| 新 API `POST /api/v1/conversation/{id}/reset` | 清该会话 checkpoint，不删业务消息 | 新 API |

---

## 7. 测试矩阵

| 场景 | 期望 |
|---|---|
| 开关关：两轮对话 | 行为和今天完全一致 |
| 开关开：两轮对话 | 第二轮 payload 只含 1 条；回复能引用第一轮 |
| 开关开：进程重启后续轮 | 从 checkpoint 恢复，能接上 |
| 开关开：手动清空 `lg_checkpoint.checkpoints` | 走降级路径；SSE `degraded:true`；audit 一条 |
| 同会话并发两请求 | thread_id 级锁序列化，不串话 |
| DELETE 会话 | checkpoint 行清零、业务消息也清 |
| 归档 +31 天 | 定时任务清 checkpoint，business 不动 |
| 技能 subagent 调用 | subagent 的 state 随父 checkpoint 持久化 |
| 超长对话 | `SummarizationMiddleware` 触发，token 不爆 |
| 被遗忘权 | 该用户所有 thread 的 checkpoint 立即清 |

---

## 8. 灰度与回滚

- 上线默认 `enable_long_session = 0`，所有应用不受影响
- 先挑 1 个内部测试 app 开启，观察 2 周
- 每个 app 开关独立，出问题只关该 app
- 代码级回滚：把 `use_checkpoint` 常量化为 False 即可退回旧行为
- 数据级回滚：checkpoint 数据保留，不影响下次重开；污染场景提供运维脚本批量 `adelete_thread`

---

## 9. 里程碑

按一个熟练后端工程师全职估算：

| PR | 工作量 | 内容 |
|---|---|---|
| PR-A | 1.5 天 | `CheckpointerFactory` + lifespan + alembic 迁移 |
| PR-B | 3 天 | `AgentApp` 接 saver + `run` async 化 + 上游 API 改造 + 单元测试 |
| PR-C | 3 天 | `conversation_service` 输入协议切换 + 降级重建 + 集成测试 |
| PR-D | 2 天 | DELETE / reset / 后台清理任务 + 被遗忘权级联 |
| 联调灰度 | 3 天 | 内部 app 启用 + 观测 + 边界修复 |
| **合计** | **~12.5 人日（约 2.5 周）** | 不含前端约 2-3 人日 |

---

## 10. 风险

| 风险 | 缓解 |
|---|---|
| LangGraph 升级破坏 checkpoint schema | 固定 `langgraph-checkpoint-postgres` 版本；升级前测试环境 dump/restore 验证 |
| 多 worker 下 `AsyncPostgresSaver` 连接池竞争 | 每 worker 独立实例；压测观察 p99；连接池上限配置化 |
| state.messages 持续增长 → checkpoint 膨胀 | 接 checkpoint 行大小监控（>10MB 告警）；后续考虑自研压缩策略（文档 §14.2 未决 3） |
| 降级重建时业务消息里混入过 tool 调用 | 降级只拿 role in (user, assistant) |
| `SummarizationMiddleware` 用主模型做摘要成本高 | 先观察生产数据；高成本场景后续配独立 cheap summary model |
| 会话第一次调用并发 → 两次写 thread_id | 用数据库唯一索引 + `INSERT ... ON CONFLICT` / SELECT FOR UPDATE 保证幂等 |

---

## 11. 后续依赖本次交付的工作

- Todo 实时同步（复用 checkpoint 里的 `todos` state key）
- 反馈闭环（需要稳定的 thread_id 作为 trace 聚合键）
- Policy 审批层的暂停/恢复（直接依赖 checkpoint）
- Memory L4 情景摘要（依赖会话归档信号）
