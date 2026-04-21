# Q1 Agent 能力增强详细设计：长会话 + Todo 可视化 + 反馈闭环

> 文件名 `long-session-design.md` 沿用原命名，实际涵盖 Q1 三项共同落地的 agent 能力。

---

## 0. 背景

Q1 要同时交付 3 项能力，本质都是**让用户建立对 agent 执行过程的信任**：

| 能力 | 解决的用户痛点 |
|---|---|
| 长会话（Checkpointer + 上下文压缩） | "昨天的对话历史/agent 思路丢了" / "对话变慢变贵" |
| Todo 可视化 | "agent 现在在干什么？还剩几步？" |
| 反馈闭环 | "这次答的不好，想告诉团队" / 团队："哪些 app / skill 差评集中？" |

三者合一交付而非分散交付的原因：
- Todo 的 state 存在 LangGraph checkpoint 里，Todo 持久化依赖长会话
- 反馈闭环要绑定 Langfuse trace，trace 在长会话的多轮里必须稳定 → 会话恢复同一 trace thread
- 前端改造集中一次完成（新增 todo 面板 + 消息反馈按钮 + 历史会话恢复）

---

# Part I — 长会话（Checkpointer + 上下文压缩）

## I.1 功能概述

基于两项 LangGraph / deepagents 能力：

- **Checkpointer（`langgraph.checkpoint.postgres.PostgresSaver`）**：每个 graph node 执行后落盘 state，下一次按 `thread_id` 拉起。
- **SummarizationMiddleware**：消息 token 超阈值时用 LLM 压缩历史为摘要，保留近期原文。

前置依赖（当前项目需新增）：
- `langgraph-checkpoint-postgres`：提供 `langgraph.checkpoint.postgres.PostgresSaver`
- `psycopg-pool`：提供独立 checkpoint 连接池
- 与当前 `langgraph` / `deepagents` 版本做兼容测试后锁版本

数据库约束原则：本系列迁移只新增列、唯一约束和查询索引，不新增数据库外键约束。

### 为什么现有的 `TbConversationMessage` 不够

业务层保留了可见消息，但 LangGraph 运行时 state 还包含：

- `todos`（agent 自管待办）——Part II 直接依赖
- `files`（虚拟文件系统，含 skills 注入的 `SKILL.md`）
- `scratch`（工具调用中间结果、reasoning 轨迹）
- 未结束的 `tool_call` / `tool_result` 配对

这些都是 agent 决策链的组成部分，不落盘就无法恢复；且 `TbConversationMessage` 只在**流结束时**写一次，中途崩溃无法接着跑。

## I.2 数据模型

### I.2.1 Checkpointer 自带表（`PostgresSaver.setup()` 创建）

| 表 | 作用 |
|---|---|
| `checkpoints` | 每个 thread 的状态快照（增量） |
| `checkpoint_blobs` | 大对象（消息、文件内容） |
| `checkpoint_writes` | 未提交的写操作 |

属于 LangGraph 协议，不走 Alembic，避免跨版本冲突。

### I.2.2 业务侧增量：`TbConversation.thread_id`

```python
class TbConversation(Base):
    # ... 原字段不变 ...
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- 新建会话：`thread_id = str(conversation.id)`
- 唯一索引 `uk_tb_conversation_thread_id`
- 历史会话由迁移脚本批量回填

### I.2.3 `app_config` 扩展（JSON，无 schema 改动）

```jsonc
{
  "checkpoint": {
    "enabled": true
  }
}
```

默认 `enabled=false`。

deepagents 边界约束：`create_deep_agent()` 当前会默认挂载自己的 `SummarizationMiddleware`，但没有公开参数让 app 直接设置 `trigger/keep/model`。P0 只接入默认 summarization；自定义摘要策略必须等 fork/包装 `create_deep_agent` 或上游支持替换默认 middleware 后再做。

### I.2.4 Alembic 迁移 `0003_add_conversation_thread_id.py`

```python
def upgrade() -> None:
    op.add_column(
        "tb_conversation",
        sa.Column("thread_id", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE tb_conversation SET thread_id = CAST(id AS VARCHAR)")
    op.create_unique_constraint(
        "uk_tb_conversation_thread_id", "tb_conversation", ["thread_id"]
    )
```

## I.3 运行时架构

### I.3.1 Checkpointer 单例（进程级）

`PostgresSaver` 需要独立的 psycopg 连接池（不复用 SQLAlchemy）。在 `backend/app/app/app_runtime.py`：

```python
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres import PostgresSaver

_pool: ConnectionPool | None = None
_saver: PostgresSaver | None = None

def get_checkpointer() -> PostgresSaver:
    global _pool, _saver
    if _saver is not None:
        return _saver
    _pool = ConnectionPool(
        conninfo=settings.checkpoint_pg_dsn,
        max_size=settings.checkpoint_pool_max_size,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )
    _saver = PostgresSaver(_pool)
    _saver.setup()
    return _saver

def shutdown_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        _pool.close()
    _pool = None
    _saver = None
```

FastAPI 生命周期：

```python
@app.on_event("startup")
def _startup() -> None:
    if settings.checkpoint_enabled:
        get_checkpointer()

@app.on_event("shutdown")
def _shutdown() -> None:
    shutdown_checkpointer()
```

### I.3.2 配置项（`backend/app/core/config.py`）

```python
class Settings(BaseSettings):
    checkpoint_enabled: bool = False
    checkpoint_pg_dsn: str = ""
    checkpoint_pool_max_size: int = 10
```

推荐把 checkpoint 表分库（独立 DSN），避免热点写入影响业务事务。

### I.3.3 `_prepare` 注入

`backend/app/app/agent_app.py`（`llm_app.py` 同理）：

```python
def _prepare(self, db, req, request_type):
    # ... 现有逻辑 ...

    checkpoint_cfg = app_config.get("checkpoint") or {}
    if checkpoint_cfg.get("enabled") and settings.checkpoint_enabled:
        agent_kwargs["checkpointer"] = get_checkpointer()

    # deepagents 默认已经挂载 SummarizationMiddleware。
    # P0 不重复追加 summarization，避免双重压缩。
    # 如需自定义 trigger/keep/model，必须通过可验证的替换机制替换默认 middleware，
    # 不允许简单 append 第二个 summarization middleware。
    middleware = []
    if app_config.get("todo", {}).get("enabled"):
        middleware.append(TodoBroadcastMiddleware())
    if middleware:
        agent_kwargs["middleware"] = middleware

    agent = create_deep_agent(**agent_kwargs)
```

### I.3.4 `thread_id` 的传递路径（不挂 `AgentRunRequest`）

当前 `AgentRunRequest` 只有 `app_id / messages / variables`，不新增字段。`thread_id` / `conversation_id` / `run_id` 走统一的 `AgentRunContext`（详见 `tool-approval-and-acl-design.md` §3.0），由入口层构造、`_Prepared` 携带、`_prepare` 写入 LangGraph config：

```python
# ConversationService 入口：
run_ctx = AgentRunContext(
    run_id=self._id_gen.next_snowflake_str(),
    app_id=app.id,
    user_id=req_ctx.user_id,
    conversation_id=conv.id,
    thread_id=conv.thread_id,           # str(conv.id)
    request_type="chat",
    tenant_id=..., team_ids=[...], role_codes=[...],
    trace_id=handler.last_trace_id,
)

# AgentApp._prepare 内部：
prep = _Prepared(..., config={
    "callbacks": [handler],
    "configurable": {"thread_id": run_ctx.thread_id, "run_id": run_ctx.run_id},
})

# invoke / astream_events 统一用 prep.config
result = prep.agent.invoke(prep.payload, config=prep.config)
```

`thread_id` 来源：

| 入口 | 来源 |
|---|---|
| `ConversationService`（正常路径） | `TbConversation.thread_id`（建会话时 `= str(id)`） |
| `/app/{id}/run`（无会话临时调用） | checkpoint 关闭时 `thread_id=None`（不走 checkpointer）；checkpoint 开启时拒绝无会话调用，或由入口层自动创建一次性 `TbConversation` 并落 `thread_id` |

**`AgentRunContext` 必须贯穿四份设计**：memory / policy / skill telemetry 都从这里取 `conversation_id / tenant_id / run_id / trace_id`，不再从 `RequestContext` 生造。

### I.3.5 checkpoint 开启后的消息输入协议（重要）

当前 `ConversationService` 会从 `TbConversationMessage` 加载整段历史，组装进 `AgentRunRequest.messages` 作为 agent 输入。这套语义**不能原样带到 checkpoint 模式下**：LangGraph checkpointer 已经把上一轮全量 `messages` 恢复到 state，若再传整段历史作为输入，`messages` 会被重复 append，导致：

- 上下文膨胀、token 成本翻倍
- SummarizationMiddleware 触发异常（看到重复的 `tool_call` 配对）
- tool_call id 配对错乱

**输入协议差异**：

| `checkpoint.enabled` | ConversationService 传给 agent 的 `messages` |
|---|---|
| `false`（默认/旧路径） | 整段历史（当前行为） |
| `true` | **仅本轮新 user message**；历史由 checkpointer 从 state 恢复 |
| `true` 且 checkpoint 缺失 / 损坏（rebuild 路径） | 用业务表最近 N 条消息重建最小 state，再 append 本轮 user message；走 `LangGraph.update_state()` 一次性写入，而非当作正常输入传 |

`ConversationService.send_message / send_message_stream` 必须按 `checkpoint.enabled` 分支组装输入；rebuild 路径写入一条 `checkpoint_rebuilt_from_messages` 审计事件。

## I.4 业务表 vs. Checkpointer 职责切分

| 维度 | `TbConversationMessage` | LangGraph Checkpoint |
|---|---|---|
| 面向 | 业务展示、审计、搜索 | Agent 运行时 state |
| 写入时机 | 流结束后一次性 | 每个 node 执行都写 |
| 内容 | 用户/助手可见消息 | messages + todos + files + scratch + tool pairs |
| 生命周期 | 跟随会话软删 | 独立 TTL 清理 |

两张表职责独立，但不是互不兜底：
- 正常路径：checkpoint 是运行时状态源，业务表是用户可见事实源。
- checkpoint 存在时：优先恢复 LangGraph state，保留 todos/files/tool pairs。
- checkpoint 不存在、损坏或被清理时：从 `TbConversationMessage` 最近 N 条消息重建最小可运行 state，并记录 `checkpoint_rebuilt_from_messages` 审计事件。
- 重建路径只恢复可见消息，不恢复 todos/files/scratch；前端需提示“已从消息历史恢复，执行中间状态不可用”。

## I.5 Summarization 策略

### I.5.1 P0：使用 deepagents 默认策略

deepagents 默认已经在主 agent 和默认 subagent 中挂载 `SummarizationMiddleware`。P0 不额外追加第二个 summarization middleware，避免双重压缩。

### I.5.2 P1+：自定义策略

以下配置只能在具备“替换默认 summarization middleware”的机制后启用：
- `trigger=("fraction", 0.85)`：模型上下文 85% 触发
- `trigger=("tokens", N)`：绝对 token 数（非 Anthropic 模型更稳）
- `trigger=("messages", N)`：消息条数兜底
- `keep=("fraction", 0.10)`
- `keep=("messages", 8)`：至少保留 8 条

### I.5.3 压缩模型

必须用便宜模型（`gpt-4o-mini` / `claude-haiku-4-5`），否则长会话成本失控。

### I.5.4 已知坑

1. **tool_call id 断链**：被压缩进摘要的 tool_call 与 tool_result 分离。`PatchToolCallsMiddleware` 部分处理；跨版本回归测试必做。
2. **敏感信息泄漏**：摘要模型会看到完整历史，PII 需合规通道。
3. **压缩不可逆**：原始 state 被替换；要追溯看业务表 `TbConversationMessage`。

## I.6 会话恢复语义

- **首条消息**：thread_id 对应 checkpoint 不存在 → 新图初始化
- **后续消息**：拉起 state，messages append；todos/files 保留
- **新建会话**：`TbConversation.id` 新生 → thread_id 新生 → checkpoint 天然不存在
- **历史会话但 checkpoint 缺失**：从业务消息表最近 N 条重建最小 messages state，todos/files 不恢复
- **用户清理**：`POST /api/v1/conversation/{id}/reset` 调 `checkpointer.delete_thread(thread_id)`
- **会话分叉（future）**：`checkpointer.get_state_history(thread_id)` 选某点 fork

## I.7 API 变更

### I.7.1 无侵入改动

- `ConversationService.send_message/send_message_stream`：内部取 `conv.thread_id` 传入 `configurable`
- `create_conversation` 时落 `thread_id=str(id)`

### I.7.2 新增端点

```
POST /api/v1/conversation/{id}/reset
GET  /api/v1/conversation/{id}/agent-state    # 调试：todos/files 摘要
```

`agent-state` 响应：

```jsonc
{
  "thread_id": "7823...",
  "messages_count": 42,
  "todos": [{ "content": "...", "status": "in_progress" }],
  "files": ["/skills/x/SKILL.md", "/workspace/notes.md"],
  "last_checkpoint_time": 1729500000000
}
```

## I.8 并发与一致性

- **同 thread_id 并发**：ConversationService 层用 Redis / PG advisory lock，key=`lock:conv:{id}`。锁获取失败返回 `429` 或排队。
- **Checkpointer 写入冲突**：`PostgresSaver` 用 `ON CONFLICT` 兜底，外层锁保证语义完整。
- **连接池调优**：`checkpoint_pool_max_size` 按业务峰值 QPS × 平均节点数；监控 `pool.get_stats()`。

## I.9 监控与运维

### I.9.1 指标

| 指标 | 来源 |
|---|---|
| `checkpoint_write_latency_p95` | saver 外层埋点 |
| `summarization_triggered_total` | middleware callback |
| `summarization_cost_tokens` | 压缩调用 usage |
| `thread_active_count` | checkpointer SQL 聚合 |
| `checkpoint_table_size` | `pg_total_relation_size` |

### I.9.2 清理策略

```python
def sweep_archived_checkpoints() -> None:
    cutoff = int(time.time() * 1000) - 30 * 86400 * 1000
    rows = db.scalars(
        select(TbConversation.thread_id)
        .where(TbConversation.status == "archived",
               TbConversation.update_time < cutoff)
    ).all()
    for thread_id in rows:
        checkpointer.delete_thread(thread_id)
```

每日凌晨跑，单节点加锁。

## I.10 兼容与回滚

- **全局开关** `settings.checkpoint_enabled=false`：不初始化池，行为与现状一致
- **按 app 开关** `app_config.checkpoint.enabled=true`：灰度
- **回滚**：关 flag，已有 checkpoint 数据留 PG，不影响新流量

## I.11 测试要点

| 场景 | 预期 |
|---|---|
| 首次对话 | checkpoint 新建 |
| 二次同 thread | todos/files 继续可见 |
| 不同 thread | 互不干扰 |
| 用户 reset | `delete_thread` 后等同首次 |
| 跨进程恢复 | 重启后 thread 恢复 |
| 触发压缩 | 历史摘要替换，后续能引用原信息 |
| 并发同 thread | 排队或拒绝 |
| checkpointer 断连 | 降级：agent 跑但不保存，WARN 日志 |

---

# Part II — Todo 可视化

## II.1 目标

把 agent 规划过程实时可视化给用户，类似 Claude Code 的 todo 面板：
- 用户看到"agent 正在做第 2/5 步"
- 失败的 todo 高亮，完成的打勾
- 建立执行进度的透明度，对长任务尤其重要

## II.2 能力来源

`deepagents` 的 `TodoListMiddleware` 已在默认栈（`graph.py` 的 `GENERAL_PURPOSE_SUBAGENT` 和 `_prepare` 都会加），注入 `write_todos` 工具 + 维护 state 里的 `todos` 字段。**当前所缺的只是把 state 变更推给前端**。

## II.3 数据流

```
Agent LLM → write_todos tool → TodoListMiddleware 更新 state.todos
                                                │
                                                ▼
                       TodoBroadcastMiddleware（自研，拦截 wrap_tool_call）
                                                │
                                                ▼
                       LangGraph custom event: "todos_updated"
                                                │
                                                ▼
                       SSE event: event=todos_updated
                                                │
                                                ▼
                       前端 Pinia store → TodoPanel 组件
```

Todos 不落业务库，状态存在 checkpoint 里（Part I 已持久化）。

## II.4 运行时改造

### II.4.1 自研中间件

`backend/app/app/middlewares/todo_broadcast.py`：

```python
from langchain.agents.middleware.types import AgentMiddleware
from langgraph.config import get_stream_writer

class TodoBroadcastMiddleware(AgentMiddleware):
    """在 write_todos 工具成功执行后，发自定义事件把 todos 快照推给 SSE。"""

    async def awrap_tool_call(self, request, call_next):
        result = await call_next(request)
        if request.tool.name == "write_todos" and not isinstance(result, Exception):
            # write_todos 返回 Command(update={"todos": ...})。
            # LangGraph 会在节点边界合并 state；此时 request.state 仍可能是旧值，
            # 因此 SSE 快照必须优先从 result.update 读取。
            todos = self._extract_todos_from_command(result)
            if todos is None:
                return result
            writer = get_stream_writer()
            writer({"event": "todos_updated", "todos": self._serialize(todos)})
        return result

    def _extract_todos_from_command(self, result):
        update = getattr(result, "update", None)
        if isinstance(update, dict):
            return update.get("todos")
        return None

    def _serialize(self, todos):
        return [
            {
                "id": t.get("id") or f"todo-{i}",
                "content": t["content"],
                "status": t.get("status", "pending"),
            }
            for i, t in enumerate(todos)
        ]
```

### II.4.2 挂载位置

在 `agent_app.py._prepare` 的 `middleware` 列表里（Part I 代码已留位置）：

```python
middleware = agent_kwargs.setdefault("middleware", [])
middleware.append(TodoBroadcastMiddleware())
```

### II.4.3 `stream()` 识别事件

在 `astream_events` 循环里新增 `on_custom_event` 分支：

```python
elif kind == "on_custom_event" and event.get("name") == "todos_updated":
    yield format_sse_event(
        SSE_EVENT_TODOS_UPDATED,
        {"todos": event.get("data", {}).get("todos", [])},
    )
```

新增常量 `SSE_EVENT_TODOS_UPDATED = "todos_updated"` 到 `app/core/sse.py`。

## II.5 SSE 事件契约

```
event: todos_updated
data: {
  "todos": [
    {"id": "todo-0", "content": "读取用户订单数据", "status": "completed"},
    {"id": "todo-1", "content": "生成对账报表",     "status": "in_progress"},
    {"id": "todo-2", "content": "发送邮件通知",     "status": "pending"}
  ]
}
```

`status`: `pending | in_progress | completed | failed`（`failed` 由 agent 自行判定写回）。

**协议特点**：
- **全量推送**（不做 diff）：简单，且 todo 列表通常小（<20 条）
- **幂等**：前端直接替换 store 里的 todos，不累加

## II.6 前端设计

### II.6.1 组件

`frontend/src/components/agent/TodoPanel.vue`：

- 对话右侧抽屉（默认展开）或左侧浮动面板
- 使用 Ant Design Vue 的 `Timeline` + 自定义 icon
- 状态映射：
  - `pending`：灰圆圈
  - `in_progress`：蓝色旋转 icon（脉动动画）
  - `completed`：绿色勾
  - `failed`：红色叉
- 空列表时显示"暂无计划"占位

### II.6.2 Pinia store

`frontend/src/stores/agentTodos.ts`：

```ts
export const useAgentTodosStore = defineStore('agentTodos', {
  state: () => ({
    todosByConversation: {} as Record<string, Todo[]>,
  }),
  actions: {
    updateTodos(conversationId: string, todos: Todo[]) {
      this.todosByConversation[conversationId] = todos
    },
    resetTodos(conversationId: string) {
      delete this.todosByConversation[conversationId]
    },
  },
})
```

SSE 解析器识别 `event: todos_updated` 时调 `updateTodos`。

### II.6.3 历史会话加载

用户切换到历史会话时，前端调 `GET /api/v1/conversation/{id}/agent-state`（Part I 提供），把 `todos` 字段灌入 store。

## II.7 回滚与兼容

- `TodoBroadcastMiddleware` 注册失败（deepagents 版本不兼容）→ catch 后 log + 跳过挂载；流仍正常
- 前端收不到 `todos_updated` 事件 → 面板保持"暂无计划"，不影响对话
- `app_config.checkpoint.enabled=false` 时，每次对话 todos 归零（无持久化），仍能实时显示当轮 todo

## II.8 测试要点

| 场景 | 预期 |
|---|---|
| Agent 首次 write_todos | 前端立即渲染 |
| 更新单条 status | 前端替换整列表 |
| Agent 不用 todo | 面板保持空，不抛错 |
| 长会话恢复 | 切回历史会话，todos 从 agent-state 恢复 |
| 工具失败 | 若 agent 写 `status=failed`，UI 红色叉 |
| 并发消息 | 每次替换整列表（最后一条 SSE 胜出） |

---

# Part III — 反馈闭环

## III.1 目标

收集每条 assistant message 的用户反馈，作为：

1. **即时质量信号**：管理员发现某个 app 差评集中 → 快速定位回归
2. **Langfuse score 上报**：trace 自动带 `user_thumb` 分数，Langfuse UI 直接聚合
3. **Eval 数据源**：差评消息进入下一步 eval 集合（Q2 规划）
4. **RLHF / Prompt tuning 数据**：长期积累

## III.2 数据模型

新增 `tb_message_feedback`：

```python
class TbMessageFeedback(Base):
    __tablename__ = "tb_message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id",
                         name="uk_tb_message_feedback_msg_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # +1 / -1 / 0（0 代表"撤回反馈"）
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON array：["inaccurate","hallucination","wrong_tool","off_topic","too_verbose",...]
    reason_tags: Mapped[str | None] = mapped_column(String(512), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：
- `(message_id, user_id)` 唯一（一人一条）
- `(app_id, score, create_time)` 管理员看板查询
- `(conversation_id)` 会话详情级联

`reason_tags` 使用受控枚举，前端下拉多选：

```
inaccurate         不准确
hallucination      编造
wrong_tool         工具选错
off_topic          偏题
too_verbose        过于冗长
too_terse          过于简短
format_bad         格式混乱
safety             安全/合规问题
other              其他
```

## III.3 Alembic 迁移 `0004_add_message_feedback.py`

```python
def upgrade() -> None:
    op.create_table(
        "tb_message_feedback",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("message_id", sa.BigInteger, nullable=False),
        sa.Column("conversation_id", sa.BigInteger, nullable=False),
        sa.Column("app_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("reason_tags", sa.String(512), nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("langfuse_trace_id", sa.String(128), nullable=True),
        sa.Column("create_time", sa.BigInteger, nullable=False),
        sa.Column("update_time", sa.BigInteger, nullable=False),
        sa.Column("create_user", sa.BigInteger, nullable=True),
        sa.Column("update_user", sa.BigInteger, nullable=True),
        sa.UniqueConstraint("message_id", "user_id",
                            name="uk_tb_message_feedback_msg_user"),
    )
    op.create_index("ix_tb_message_feedback_app_score_time",
                    "tb_message_feedback", ["app_id", "score", "create_time"])
    op.create_index("ix_tb_message_feedback_conversation",
                    "tb_message_feedback", ["conversation_id"])
```

## III.4 数据补充：在 `TbConversationMessage` 上关联 trace

为了反馈能精准上报 Langfuse，需要在 `TbConversationMessage` 加一列：

```python
langfuse_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
```

写消息时取 `handler.last_trace_id` 一起落库。迁移 `0005_add_message_trace_id.py`。

## III.5 API 设计

### III.5.1 用户侧

```
POST   /api/v1/conversation/{cid}/message/{mid}/feedback
GET    /api/v1/conversation/{cid}/message/{mid}/feedback    # 查自己的
DELETE /api/v1/conversation/{cid}/message/{mid}/feedback    # 撤回
```

POST 请求：

```python
class FeedbackReq(BaseModel):
    score: Literal[-1, 1]
    reason_tags: list[str] = []
    comment: str | None = None
```

服务端逻辑（`FeedbackService.submit`）：

```python
def submit(self, db, *, message_id, user_id, req, req_ctx):
    # 校验 message 归属：该消息所在 conversation 的 user_id 必须 == req_ctx.user_id
    msg = db.get(TbConversationMessage, message_id)
    if not msg:
        raise ServiceError(ErrorCode.DATA_NOT_FOUND, "message not found")
    conv = db.get(TbConversation, msg.conversation_id)
    if conv.user_id != user_id:
        raise ServiceError(ErrorCode.FORBIDDEN, "feedback only from owner")
    if msg.role != "assistant":
        raise ServiceError(ErrorCode.BAD_REQUEST, "only assistant messages")

    # Upsert：存在则更新
    existing = db.scalar(
        select(TbMessageFeedback)
        .where(TbMessageFeedback.message_id == message_id,
               TbMessageFeedback.user_id == user_id)
    )
    if existing:
        existing.score = req.score
        existing.reason_tags = json.dumps(req.reason_tags) if req.reason_tags else None
        existing.comment = req.comment
        existing.update_time = req_ctx.request_time_ms
        existing.update_user = user_id
    else:
        db.add(TbMessageFeedback(
            id=self._id_gen.next_id(),
            message_id=message_id,
            conversation_id=msg.conversation_id,
            app_id=conv.app_id,
            user_id=user_id,
            score=req.score,
            reason_tags=json.dumps(req.reason_tags) if req.reason_tags else None,
            comment=req.comment,
            langfuse_trace_id=msg.langfuse_trace_id,
            create_time=req_ctx.request_time_ms,
            update_time=req_ctx.request_time_ms,
            create_user=user_id,
            update_user=user_id,
        ))
    db.commit()

    # 异步上报 Langfuse（不阻塞用户）
    if msg.langfuse_trace_id:
        self._langfuse_reporter.enqueue(
            trace_id=msg.langfuse_trace_id,
            score_name="user_thumb",
            score_value=req.score,
            comment=req.comment,
        )
```

### III.5.2 管理员看板

```
GET /api/v1/app/{app_id}/feedback/summary?period=7d
GET /api/v1/app/{app_id}/feedback/page?score=-1&tag=hallucination
```

summary 响应：

```jsonc
{
  "period": "7d",
  "total_messages": 1234,
  "feedback_count": 342,
  "thumbs_up": 298,
  "thumbs_down": 44,
  "down_rate": 0.128,
  "top_reason_tags": [
    { "tag": "inaccurate", "count": 18 },
    { "tag": "hallucination", "count": 12 }
  ],
  "trend": [
    { "date": "2026-04-15", "up": 40, "down": 5 },
    { "date": "2026-04-16", "up": 38, "down": 8 }
  ]
}
```

`page` 用于差评下钻：返回差评消息列表 + 每条可跳到原 conversation。

## III.6 Langfuse 联动

### III.6.1 SDK 上报

用现有的 langfuse SDK（后端已集成），异步提交分数：

```python
class LangfuseFeedbackReporter:
    def __init__(self, client: Langfuse):
        self._client = client
        self._queue: asyncio.Queue | None = None  # 简单版直接同步

    def enqueue(self, *, trace_id, score_name, score_value, comment):
        try:
            self._client.score(
                trace_id=trace_id,
                name=score_name,
                value=score_value,
                comment=comment,
            )
        except Exception:
            logger.exception("langfuse score upload failed")
```

失败不影响用户反馈落库。

### III.6.2 Langfuse UI 价值

- Trace 详情页直接看到 `user_thumb` 分数
- 按 app 过滤聚合差评 trace
- 支持导出到外部 eval 工具

## III.7 前端交互

### III.7.1 消息右下角按钮

每条 assistant message 显示：

```
👍 👎  <- 默认状态，hover 显示
```

点击 👎 后展开表单：
- 多选 reason_tags（chip 样式）
- 可选 comment 输入框（textarea，200 字内）
- 提交按钮
- 取消按钮关闭表单但不撤回已点的 👎

点击 👍 直接上报，不弹表单（也不允许撤回 tag）。

### III.7.2 已评状态

已评反馈的消息：
- 👍 或 👎 高亮色
- hover 显示"已反馈 · 点击修改"
- 二次点击打开表单（预填已有 tag/comment）

### III.7.3 Pinia store

```ts
export const useFeedbackStore = defineStore('feedback', {
  state: () => ({
    byMessageId: {} as Record<string, { score: 1 | -1, tags: string[], comment?: string }>,
  }),
  actions: {
    async submit(messageId: string, payload) {
      await api.post(`/conversation/${cid}/message/${messageId}/feedback`, payload)
      this.byMessageId[messageId] = payload
    },
  },
})
```

会话加载时批量拉 `GET /api/v1/conversation/{cid}/feedback/batch` 灌入 store。

## III.8 权限与隐私

- 只有 conversation 的 owner 可以对消息反馈
- 管理员看板需要 `app.admin` 角色
- `comment` 字段可能含业务敏感信息 → 管理员导出前过 PII 脱敏
- 用户可 `DELETE` 自己的反馈（软删保留 row `score=0` 标记）

## III.9 测试要点

| 场景 | 预期 |
|---|---|
| 首次 👍 | 新行落库，Langfuse 上报 |
| 同消息二次 👎 | upsert，updated_time 变，Langfuse 上报新 score |
| 他人会话的消息 | 403 |
| 给 user 消息打分 | 400（only assistant） |
| DELETE | soft delete，后续 GET 返回空 |
| Langfuse 不可用 | 本地落库成功，日志 WARN |
| summary 查询 | 聚合数据正确，trend 按天 |
| 管理员下钻 | 能跳转到原 conversation |

---

# Part IV — 交付计划与依赖

## IV.1 依赖关系

```
            ┌─ Part II (Todo) ────────┐
Part I ─────┤                          ├─→ Q1 上线
            └─ Part III (Feedback) ───┘
```

- **Part II 依赖 Part I**：Todo 要跨会话保留必须有 checkpoint；但**一次性 Todo 显示不依赖**（当轮有效也能发 SSE）→ 可并行开发，集成时才绑定持久化
- **Part III 独立**：只用到 trace_id 和业务表，可完全独立交付
- **前端统一一次发版**：todo 面板 + feedback 按钮 + 历史会话恢复

## IV.2 里程碑

| 周 | Part I | Part II | Part III |
|---|---|---|---|
| W1 | checkpointer 封装 + `_prepare` 注入 | `TodoBroadcastMiddleware` 骨架 | `tb_message_feedback` 迁移 |
| W2 | `thread_id` 透传 + 迁移回填 | SSE 事件接入 + 前端 store | `FeedbackService` + user API |
| W3 | summarization 配置 + 监控埋点 | 前端 TodoPanel 组件 | Langfuse 上报 + 看板 API |
| W4 | 灰度开关 + 并发锁 | 历史会话 todo 恢复 | 前端按钮 + 表单 |
| W5 | 联调 + 观测 | 联调 + 动画打磨 | 联调 + 权限 |
| W6 | 小流量灰度（1-2 个 app） |||
| W7 | 监控观察 + 修边界问题 |||
| W8 | 按 app 渐进全量 |||

## IV.3 成功指标

| 指标 | 目标 |
|---|---|
| 长会话启用 app 的 p95 首 token 延迟增加 | < 200ms |
| Summarization 节省总 token | > 30%（在超 4K 消息的长会话上） |
| Todo 面板 SSE 到达率 | > 99% |
| 消息反馈覆盖率（`feedback_count / assistant_messages`） | > 15% |
| 差评定位到 trace 的准确率 | 100%（只要有 trace_id） |

## IV.4 回滚策略

三件事各自有独立 flag：
- `settings.checkpoint_enabled`
- `app_config.checkpoint.enabled`（per-app）
- Todo 面板：前端 feature flag 可关
- Feedback：后端 API 保留，前端按钮 flag 可关

任一部分出问题 → 独立关闭，不影响其他。

## IV.5 后续联动（Q2）

- **工具审批 / ACL**（`tool-approval-and-acl-design.md`）：自研 `ToolPolicyMiddleware.after_model` 通过 LangGraph `interrupt()` 暂停，恢复依赖本文档的 checkpointer；不使用 deepagents `interrupt_on`
- **Eval harness**：差评消息自动进 eval 候选集
- **模型路由**：按 feedback 差评率自动切换默认模型
