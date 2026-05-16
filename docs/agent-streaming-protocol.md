# Agent 流式通信协议（Agent Streaming Protocol）

> **本文档定位**：协议**说明**文档（specification），定义 easy-ai 服务端向前端推送 agent/对话执行过程的线上协议。不含落地实现与代码。
>
> **协议版本**：`1`（本系统首个、也是当前唯一的协议版本）。
>
> **适用范围**：智能助手对话（`/conversation/{id}/message/stream`）、应用测试（`/open/app/{id}/test/stream`）及其 HITL 续跑端点。三者共用本协议，差异仅在业务语义，不在协议本身。

---

## 0. 设计由来

### 0.1 我们参考了什么

设计前调研了三套业界标准 / 事实标准。结论：没有一套可原样采用，但各有可直接借鉴的部分。

| 参考对象 | 来源 | 借鉴了什么 | 为何不整体采用 |
|---|---|---|---|
| **Anthropic Messages 流式事件** | Anthropic API | "消息 → 内容块（content block）→ delta"的封装模型，块带 `index` | 是模型 API 层协议，非 Server↔UI 协议 |
| **AG-UI Protocol** | CopilotKit（开源） | 传输心智模型（`run.*` 生命周期 + interrupt/resume）、事件流形态 | 领域字段（RAG 引用、token usage）无标准位，仍需自管 |
| **ACP / Agent Client Protocol** | Zed（开源） | 字段命名与枚举：`plan`、工具 `status` 四态、`thought` 块、permission `options` | 传输是 JSON-RPC over stdio，面向"编辑器↔子进程"，与浏览器单向 SSE 不兼容 |

> ACP 缩写有歧义：本文指 Zed 的 **Agent Client Protocol**，非 IBM/Linux Foundation 的 *Agent Communication Protocol*（A2A，REST，agent↔agent）。后者不适用于本场景。

一个支撑性观察：三套标准在"内容块 + 工具调用 + 计划/todo + 权限/HITL"上**高度趋同**。这种独立收敛说明该抽象经得起推敲，照此设计风险很低。

### 0.2 设计原则

| 原则 | 说明 |
|---|---|
| 协议带版本号 | 预留 `v` 字段，使协议具备可演进性——将来新增能力或调整结构时，客户端可据 `v` 选择解析路径 |
| 内容块封装 | 消息 → 带 `block_index` 的块。使"思考与正文交错""并行工具""多模态""一轮多消息"在结构上天然可表达，而非靠堆事件类型 |
| 单一事实源 | 协议产生收口为服务端结构化事件对象，仅在 API 边界序列化一次；内部消费者（如落库）读结构化对象，不反解析线上文本 |
| 与后端语义同构 | 生命周期与 HITL 模型对齐后端 LangGraph 的 `interrupt()` + checkpoint 续跑，减少阻抗失配 |
| 领域字段受控隔离 | RAG 引用、token usage 等无业界标准归属的字段统一进 `ext` 命名空间并独立版本化，不散落进标准字段 |
| 错误分级 | 区分致命错误（终止流）与可恢复错误（流继续），不把所有错误压成终止态 |

### 0.3 关键决策记录

| 决策 | 选定 | 理由 |
|---|---|---|
| 传输层 | **SSE**（`text/event-stream`，POST + ReadableStream），事件类型置于 JSON 载荷 | 对齐 AG-UI 参考实现；事件信封与传输解耦（type 在 payload，非 SSE `event:` 行），将来可平移至 WebSocket 等而 schema 不变；ACP 的双向 RPC 模型需在 SSE 上重造反向通道，不划算 |
| 生命周期模型 | **AG-UI 的 `run.*` + interrupt/resume** | 与后端 LangGraph 续跑机制同构，阻抗最小 |
| 内容承载模型 | **Anthropic 式"消息→块→delta"** | 思考过程/并行工具/多模态都退化为"另一种块"，无需为每种能力新增事件 |
| 字段命名与枚举 | **抄 ACP**：`plan`、tool `status` 四态、`thought` 块、permission `options` | 命名与枚举最规整，可读性好 |
| 领域字段归属 | **统一进 `ext`，独立版本化** | RAG 引用、token usage、app_type 在三套标准里均无标准位；显式隔离并当正式契约维护 |
| HITL 建模 | **流自然停在 `hitl.required`，续跑为新的一段流** | interrupt 形状取 AG-UI（贴合 LangGraph），options 语义取 ACP（贴合 confirm/modify/reject） |
| token usage / 延迟 | **进 `ext`** | ACP、AG-UI 均未标准化 usage；计费/可观测需要，须显式承载 |

### 0.4 非目标（本版不做，但结构上预留扩展点）

断线重连 / `Last-Event-ID` 续传（仅占位 `seq`）；工具入参流式（预留 `tool.args.delta`）；多模态输入（块模型预留 `block_type`）；agent↔agent 通信（不在范围）。

---

## 1. 传输层

| 项 | 规定 |
|---|---|
| 承载 | HTTP `POST` 请求 + `text/event-stream` 响应体，客户端经 `ReadableStream` 读取（非 `EventSource`，因需 POST body） |
| 响应头 | `Content-Type: text/event-stream`；`Cache-Control: no-cache`；`Connection: keep-alive`；`X-Accel-Buffering: no` |
| 帧格式 | `data: <json>\n\n`（单行 JSON + 空行分隔）。**不使用 SSE `event:` 行**——事件类型由 JSON 载荷的 `type` 字段标识（见 §2） |
| 传输无关 | 事件信封不依赖 SSE 语义。SSE 仅为当前默认承载；同一事件流可原样平移至 WebSocket 等传输，schema 与解析逻辑不变 |
| 序号行 | 每帧可带 `id: <seq>\n`（为将来 `Last-Event-ID` 重连预留；本版客户端可忽略） |
| 终止哨兵 | 流末尾发 `data: [DONE]\n\n`；正式终止以 `run.finished` / `run.error` 为准 |
| 取消 | 客户端经 `AbortController` 中断；服务端据连接断开停止生成 |
| 编码 | UTF-8；`data` 为单行 JSON（`ensure_ascii=false`） |

---

## 2. 帧信封（Envelope）

所有事件的 `data` JSON 共享统一信封字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `type` | string | 是 | 事件类型（如 `run.started`、`block.delta`）。事件类型在载荷内,而非 SSE `event:` 行,使信封传输无关 |
| `v` | int | 是 | 协议版本，当前恒为 `1`。客户端校验；不认识则降级提示，不强行解析 |
| `seq` | int | 是 | 单调递增序号，自 0 起。用于排序与将来重连；本版不强制消费 |
| `run_id` | string | 是 | 一次执行的稳定 id。落库主键；HITL 续跑用 `parent_run_id` 关联 |
| *(其余)* | — | — | 事件专属载荷，见 §3 |

---

## 3. 事件集（Schema 定义）

事件分四组：**生命周期**、**消息与内容块**、**工具与计划**、**人在回路**；外加**受控扩展**。

字段表中 `?` 表示可选。所有事件隐含携带 §2 信封字段，下表不重复列出。

### 3.1 生命周期

#### `run.started`
流开始，每条流恰好一帧，`seq=0`。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `thread_id` | string? | 否 | 会话/线程 id（长会话有；无状态调用可空） |
| `parent_run_id` | string? | 否 | HITL 续跑时指向被中断的原 run |
| `ext` | object | 是 | 领域扩展，见 §3.5。典型含 `app_id`/`app_type`/`model`/`degraded` |

#### `run.finished`
正常终止，每条流至多一帧（与 `run.error` 互斥），位于 `[DONE]` 之前。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `stop_reason` | enum | 是 | `end_turn` \| `max_tokens` \| `hitl_interrupt` \| `cancelled` \| `error` |
| `ext` | object | 是 | 典型含 `usage{total_tokens,input_tokens,output_tokens}`、`latency_ms` |

> `run.finished` **不重发消息全文**。最终内容由客户端累积 `block.delta` 得到。

#### `run.error`
致命错误，终止流（与 `run.finished` 互斥）。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `code` | string | 是 | 机器可读错误码 |
| `message` | string | 是 | 人类可读说明 |
| `retriable` | bool | 是 | 客户端可否对同一输入重试 |

> **可恢复错误**不走此事件，走工具级 `tool.updated{status:"failed"}`，流继续。

### 3.2 消息与内容块

一条 assistant 消息由若干内容块组成，块按 `block_index` 编号，可交错流式（如 `thought` 块与 `text` 块并行推进）。

#### `message.started`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `message_id` | string | 是 | 消息稳定 id |
| `role` | enum | 是 | `assistant`（预留 `tool`） |

#### `block.started`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `message_id` | string | 是 | 所属消息 |
| `block_index` | int | 是 | 块序号，自 0 起 |
| `block_type` | enum | 是 | `text` \| `thought` \| `tool_use`（预留 `image`/`resource`） |

#### `block.delta`
增量内容片段。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `message_id` | string | 是 | 所属消息 |
| `block_index` | int | 是 | 所属块 |
| `delta` | string | 是 | 增量文本片段 |

#### `block.stopped`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `message_id` | string | 是 | 所属消息 |
| `block_index` | int | 是 | 结束的块 |

#### `message.completed`
消息结束标识，不带全文。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `message_id` | string | 是 | 结束的消息 |

> **思考过程**仅为 `block_type:"thought"` 的块，无需独立事件——借鉴 ACP `agent_thought_chunk` 的归类思路。

### 3.3 工具与计划

#### `tool.started`
工具调用开始。`block_type:"tool_use"` 的块对应一次工具调用。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `message_id` | string | 是 | 所属消息 |
| `block_index` | int | 是 | 所属块 |
| `tool_call_id` | string | 是 | 工具调用稳定 id |
| `name` | string | 是 | 工具名 |
| `status` | enum | 是 | 起始恒为 `pending` |
| `arguments` | object | 是 | 调用入参（本版一次性给；流式入参为预留扩展点） |

#### `tool.updated`
工具状态推进 / 结束。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `tool_call_id` | string | 是 | 关联的工具调用 |
| `status` | enum | 是 | `pending` \| `in_progress` \| `completed` \| `failed`（ACP 四态） |
| `result` | string? | 否 | `completed`/`failed` 时的结果或错误文本 |

#### `plan.updated`
计划/待办更新，全量快照（非增量）。结构抄 ACP `plan`。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `entries` | array | 是 | 计划项全量快照 |
| `entries[].content` | string | 是 | 任务描述 |
| `entries[].status` | enum | 是 | `pending` \| `in_progress` \| `completed`（ACP 三态） |
| `entries[].priority` | enum | 是 | `high` \| `medium` \| `low`（缺省 `medium`） |

### 3.4 人在回路（HITL）

#### `hitl.required`
agent 执行需人工裁决。**流在此自然停住**（语义等同 AG-UI `RunFinished(outcome=interrupt)`），不再继续产出，直至客户端经续跑端点应答。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `hitl_id` | string | 是 | 本次中断 id，续跑时回传 |
| `tool_call_id` | string | 是 | 触发中断的工具调用 |
| `tool_name` | string | 是 | 工具名 |
| `risk_level` | enum | 是 | `low` \| `medium` \| `high` |
| `options` | array | 是 | 可选裁决项（结构抄 ACP `PermissionOption`） |
| `options[].option_id` | string | 是 | 如 `confirm` / `modify` / `reject` |
| `options[].kind` | enum | 是 | `allow_once` \| `allow_always` \| `reject_once` \| `reject_always` |

**续跑请求体**（发往 HITL 续跑端点，对齐 ACP outcome 语义）：

```jsonc
{
  "hitl_id": "h_1",
  "outcome": {
    "selected": { "option_id": "modify", "parameters": { /* modify 时的改写入参 */ } }
  }
}
// 或取消：{ "hitl_id": "h_1", "outcome": { "cancelled": true } }
```

续跑响应是**新的一段 SSE 流**：新 `run_id`，`run.started.parent_run_id` 指向被中断的原 run。

### 3.5 受控扩展（`ext` 命名空间）

领域特有、无业界标准归属的字段，**一律置于 `ext`**，不得散落进标准字段。`ext` 内事件类型以 `ext.` 前缀并带独立 `ext_version`，在本文档中作为正式契约维护。

| 已定义扩展 | 形态 | 说明 |
|---|---|---|
| `run.started.ext` | `{app_id, app_type, model, degraded?}` | 应用元信息（无标准位） |
| `run.finished.ext` | `{usage:{...}, latency_ms}` | token 用量与延迟 |
| 事件 `ext.references` | `{ext_version:1, items:[{doc_ref, doc_name}]}` | RAG 检索引用，正文流之前推送 |

新增领域字段必须：① 进 `ext`；② 本文档登记；③ 自带 `ext_version`。

---

## 4. 完整事件序列示例

### 4.1 Agent 应用（含思考、工具、计划）

```
data: {"type":"run.started","v":1,"seq":0,"run_id":"r_1","thread_id":"c_8","ext":{"app_id":"456","app_type":"agent","model":"gpt-4o","degraded":false}}

data: {"type":"message.started","v":1,"seq":1,"run_id":"r_1","message_id":"m_1","role":"assistant"}

data: {"type":"block.started","v":1,"seq":2,"run_id":"r_1","message_id":"m_1","block_index":0,"block_type":"thought"}

data: {"type":"block.delta","v":1,"seq":3,"run_id":"r_1","message_id":"m_1","block_index":0,"delta":"用户想查最近新闻，先检索"}

data: {"type":"block.stopped","v":1,"seq":4,"run_id":"r_1","message_id":"m_1","block_index":0}

data: {"type":"plan.updated","v":1,"seq":5,"run_id":"r_1","entries":[{"content":"检索新闻","status":"in_progress","priority":"high"},{"content":"汇总回复","status":"pending","priority":"medium"}]}

data: {"type":"tool.started","v":1,"seq":6,"run_id":"r_1","message_id":"m_1","block_index":1,"tool_call_id":"tc_1","name":"search","status":"pending","arguments":{"q":"最新新闻"}}

data: {"type":"tool.updated","v":1,"seq":7,"run_id":"r_1","tool_call_id":"tc_1","status":"completed","result":"..."}

data: {"type":"block.started","v":1,"seq":8,"run_id":"r_1","message_id":"m_1","block_index":2,"block_type":"text"}

data: {"type":"block.delta","v":1,"seq":9,"run_id":"r_1","message_id":"m_1","block_index":2,"delta":"根据检索结果，"}

data: {"type":"block.stopped","v":1,"seq":10,"run_id":"r_1","message_id":"m_1","block_index":2}

data: {"type":"message.completed","v":1,"seq":11,"run_id":"r_1","message_id":"m_1"}

data: {"type":"run.finished","v":1,"seq":12,"run_id":"r_1","stop_reason":"end_turn","ext":{"usage":{"total_tokens":200,"input_tokens":80,"output_tokens":120},"latency_ms":5678}}

data: [DONE]
```

### 4.2 HITL 中断与续跑

```
... (run r_1 正常推进) ...

data: {"type":"hitl.required","v":1,"seq":7,"run_id":"r_1","hitl_id":"h_1","tool_call_id":"tc_2","tool_name":"send_email","risk_level":"high","options":[{"option_id":"confirm","kind":"allow_once"},{"option_id":"modify","kind":"allow_once"},{"option_id":"reject","kind":"reject_once"}]}

data: [DONE]      ← 流停止，等待客户端经续跑端点应答

--- 客户端 POST 续跑端点，body: {"hitl_id":"h_1","outcome":{"selected":{"option_id":"confirm"}}} ---

data: {"type":"run.started","v":1,"seq":0,"run_id":"r_2","thread_id":"c_8","parent_run_id":"r_1","ext":{...}}

... (续跑产出) ...

data: {"type":"run.finished","v":1,"seq":N,"run_id":"r_2","stop_reason":"end_turn","ext":{...}}

data: [DONE]
```

### 4.3 RAG 应用（引用走 `ext`）

```
data: {"type":"run.started","v":1,"seq":0,"run_id":"r_3","ext":{"app_id":"789","app_type":"rag","model":"gpt-4o"}}

data: {"type":"ext.references","v":1,"seq":1,"run_id":"r_3","ext_version":1,"items":[{"doc_ref":"abc","doc_name":"产品白皮书"}]}

data: {"type":"message.started","v":1,"seq":2,"run_id":"r_3","message_id":"m_1","role":"assistant"}

data: {"type":"block.started","v":1,"seq":3,"run_id":"r_3","message_id":"m_1","block_index":0,"block_type":"text"}

data: {"type":"block.delta","v":1,"seq":4,"run_id":"r_3","message_id":"m_1","block_index":0,"delta":"根据白皮书，"}

...

data: {"type":"run.finished","v":1,"seq":9,"run_id":"r_3","stop_reason":"end_turn","ext":{"usage":{...},"latency_ms":3000}}

data: [DONE]
```

---

## 5. 版本与约束

| 规则 | 说明 |
|---|---|
| 版本号 | 信封 `v` 当前恒为 `1`。结构性扩展递增 `v`；新增可选标准字段、`ext.*` 演进不动 `v` |
| 扩展演进 | `ext.*` 事件以各自 `ext_version` 独立演进，不占用 `v` |
| 未知项处理 | 客户端**必须忽略**未知事件类型与未知字段，不得报错——这使协议可持续追加新事件/字段而无需客户端同步改造 |
| 终止保证 | 每条流必以 `run.finished` 或 `run.error` 结束，其后跟 `[DONE]` 哨兵 |
| 互斥保证 | `run.finished` 与 `run.error` 互斥；`hitl.required` 后本段流不再有 `run.finished` |

---

## 6. 业务语义差异（协议无差异）

智能助手对话与应用测试**共用本协议**，线上字节序列在协议层完全一致。差异仅在业务语义，不由协议表达：

| 维度 | 智能助手对话 | 应用测试 |
|---|---|---|
| 状态 | 有状态长会话，`thread_id` 持久 | 一次性，`thread_id` 临时 |
| 消息持久化 | 服务端落库 | 不落库 |
| 用途 | 生产用户对话 | 开发调试 |

协议不为二者引入分支，前端可复用同一套事件处理。

---

## 附录 A：参考标准对照速查

| 关注点 | Anthropic Messages | AG-UI | ACP (Zed) | 本协议取舍 |
|---|---|---|---|---|
| 传输 | 模型 API SSE | 事件流 SSE/HTTP | JSON-RPC / stdio | **SSE 事件流**（同 AG-UI 形态） |
| 内容承载 | 消息→块→delta（`index`） | text/reasoning message | content_block | **抄 Anthropic 块模型** |
| 思考过程 | thinking block | reasoning message | `agent_thought_chunk` | **`block_type:"thought"`** |
| 工具状态 | tool_use/tool_result | tool call lifecycle | status 四态 | **抄 ACP 四态** |
| 计划/todo | 无 | state delta | `plan` + priority | **抄 ACP `plan`** |
| HITL | 无 | interrupt + resume run | `request_permission`+options | **AG-UI 形状 + ACP options** |
| token usage | message_delta.usage | 无标准 | 无标准 | **进 `ext`** |
| RAG 引用 | 无 | 无 | 无 | **`ext.references`（领域自管）** |

## 附录 B：参考链接

- Anthropic Messages streaming：https://docs.anthropic.com/en/api/messages-streaming
- AG-UI Protocol：https://docs.ag-ui.com
- Agent Client Protocol (Zed)：https://agentclientprotocol.com
