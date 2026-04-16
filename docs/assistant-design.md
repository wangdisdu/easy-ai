# 智能助手功能详细设计

> 基于原型页面 [ChatPage.vue](../eoitek-llm/vue-app/src/views/ChatPage.vue) 整理。智能助手的底层能力来自应用工厂中已发布的各类应用（LLM、Agent、RAG 等），通过对话形式向用户提供 AI 交互服务。

---

## 1. 功能概述

智能助手是平台的**核心用户入口**（`/assistant`，默认首页），将应用工厂中已发布的各类应用封装为统一的对话交互界面，让用户无需了解底层应用类型和配置细节，即可通过自然语言对话获取 AI 服务。

### 1.1 核心能力

| 能力 | 说明 |
|------|------|
| 多应用切换 | 在一个界面内切换不同已发布应用进行对话 |
| 流式输出 | 基于 SSE 协议逐 token 输出，实时展示 AI 生成过程 |
| 多轮对话 | 自动携带上下文，支持连续追问 |
| 会话管理 | 会话持久化，支持历史列表、新建、归档 |
| 工具调用可视化 | Agent 应用的工具调用过程实时展示 |
| Markdown 渲染 | 支持表格、代码块、列表、标题等富文本展示 |
| 引用来源 | RAG 应用展示检索引用的知识来源 |

### 1.2 与应用工厂的关系

```
应用工厂（创建、配置、发布）
    │
    │  发布后的应用
    ▼
智能助手（对话交互）──调用──→ /api/v1/open/app/{app_id}/stream
    │
    │  执行日志
    ▼
应用详情页（历史消息 Tab）
```

智能助手只展示 `app_status = 'published'` 的应用，通过现有的流式执行端点 `POST /api/v1/open/app/{app_id}/stream` 与后端交互。

---

## 2. 页面布局

### 2.1 整体结构

```
┌─ MainLayout ────────────────────────────────────────────┐
│ Sidebar │  智能助手页面                                   │
│         │ ┌──────────┬────────────────────────────────┐  │
│         │ │ 会话侧栏   │       对话主区                  │  │
│         │ │ (240px)   │                                │  │
│         │ │           │  顶部栏（应用选择器）              │  │
│         │ │ 新建对话   │ ──────────────────────────────  │  │
│         │ │           │                                │  │
│         │ │ 会话历史   │  消息列表（可滚动）               │  │
│         │ │  - 会话1  │   用户消息 → AI回复 → ...        │  │
│         │ │  - 会话2  │                                │  │
│         │ │  - ...    │                                │  │
│         │ │           │ ──────────────────────────────  │  │
│         │ │           │  输入区（底部固定）               │  │
│         │ └──────────┴────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 各区域职责

| 区域 | 职责 | 关键交互 |
|------|------|---------|
| 会话侧栏 | 展示历史会话列表，支持新建、切换、归档 | 点击切换会话；「新建对话」按钮 |
| 顶部栏 | 展示当前应用，切换应用 | 两级下拉菜单选择应用 |
| 消息列表 | 展示对话消息流，支持自动滚动到底部 | 滚动浏览；空状态展示快捷提问 |
| 输入区 | 用户输入消息并发送 | Enter 发送；Shift+Enter 换行 |

---

## 3. 会话侧栏设计

### 3.1 侧栏头部

- 「新建对话」按钮，主色调，图标 + 文字
- 点击后：清空当前消息区域，创建一个新会话（保持当前选中的应用不变）

### 3.2 会话列表

每条会话项展示：

```
┌──────────────────────────────────┐
│ [RAG] 运维知识库问答      今天 09:32 │  ← 应用类型标签 + 应用名 + 时间
│ Pod 重启排查流程                   │  ← 会话标题（取首条用户消息摘要）
│ 订单服务 Pod 频繁重启怎么排查？     │  ← 最新消息预览
└──────────────────────────────────┘
```

**字段说明**：

| 字段 | 来源 | 说明 |
|------|------|------|
| 应用类型标签 | `app.app_type` | 颜色区分：LLM 绿、RAG 蓝、Agent 紫、NL2SQL 青 |
| 应用名 | `app.name` | 截断显示 |
| 时间 | `conversation.update_time` | 智能格式：今天/昨天/日期 |
| 会话标题 | `conversation.title` | 取首条用户消息前 30 字 |
| 消息预览 | 最新一条消息的 `content` | 截断显示 |

**交互**：

- 点击切换到该会话，加载其消息列表
- 当前活跃会话高亮
- 会话按 `update_time` 倒序排列
- 右键或悬停出现操作菜单：归档、删除

### 3.3 会话筛选

侧栏头部下方可选加一个搜索框，按会话标题和消息内容模糊搜索。初期可不做，后续迭代。

---

## 4. 顶部栏设计

### 4.1 应用选择器

采用两级下拉菜单，与原型一致：

**第一级 — 选择应用类型**：

```
┌──────────────────────────┐
│ 选择应用类型               │
├──────────────────────────┤
│ ✨ LLM 应用              │
│    大模型通用应用          │
│ 📚 RAG 知识库问答         │
│    基于知识库的问答        │
│ 🤖 Agent 智能体           │
│    可调用工具的智能体      │
│ 🗄 NL2SQL 数据查询        │
│    自然语言查数据          │
└──────────────────────────┘
```

**第二级 — 选择具体应用**（仅展示该类型下 `app_status = 'published'` 的应用）：

```
┌──────────────────────────┐
│ ← RAG 知识库问答          │
├──────────────────────────┤
│ 运维知识库问答        ✓   │  ← 当前选中
│ 根因分析助手              │
└──────────────────────────┘
```

**切换应用的行为**：

- 切换应用后，如果目标应用在当前没有进行中的会话，则自动新建一个会话
- 如果目标应用有最近的会话，则切换到该会话
- 应用选择器左侧显示当前应用的类型标签 + 应用名

### 4.2 右侧辅助区

- 提示文案：「多轮对话 · 上下文自动携带」
- 全屏按钮：切换全屏模式（Escape 退出）

---

## 5. 消息列表设计

### 5.1 消息类型与渲染

#### 用户消息

```
┌──────────────────────────────────────────────┐
│                                  ┌─────────┐ │
│                                  │ 用户消息  │ │
│                                  │ 文本内容  │ │
│                                  └─────────┘ │
│                                    10:32     │
└──────────────────────────────────────────────┘
```

- 右对齐
- 主色调背景（蓝色半透明）
- 圆角气泡，右上角方角
- 底部显示时间（HH:MM）
- 纯文本渲染

#### AI 回复消息

```
┌──────────────────────────────────────────────┐
│ ┌──┐ ┌────────────────────────────────────┐  │
│ │AI│ │ 助手回复                            │  │
│ └──┘ │ Markdown 渲染的富文本内容            │  │
│      │ - 表格、代码块、列表、粗体等         │  │
│      └────────────────────────────────────┘  │
│      [引用来源1] [引用来源2]                   │
│      10:33                                   │
└──────────────────────────────────────────────┘
```

- 左对齐
- 左侧显示 AI 头像（渐变色圆角方块，内显「AI」）
- 消息体使用卡片样式，左上角方角
- 内容通过 Markdown 渲染引擎渲染为 HTML
- 引用来源标签（仅 RAG 应用有）展示在消息下方
- 底部显示时间

#### 工具调用消息（Agent 应用）

在 AI 回复之前，如果有工具调用，以折叠/展开形式展示：

```
┌──────────────────────────────────────────────┐
│ ┌──┐ ┌────────────────────────────────────┐  │
│ │🔧│ │ 调用工具：search_web               │  │
│ └──┘ │ 参数：{"query": "天气"}             │  │
│      │ 结果：北京今天晴，25°C     ✓ done   │  │
│      └────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

- 工具调用使用橙色边框标识
- 执行中状态显示 Spinner
- 完成后显示 `done` + 结果预览
- 参数和结果可折叠

#### 正在输入指示器

```
┌──────────────────────────────────────────────┐
│ ┌──┐ ┌────────┐                              │
│ │AI│ │ ● ● ●  │  ← 三点脉冲动画             │
│ └──┘ └────────┘                              │
└──────────────────────────────────────────────┘
```

- AI 头像 + 三点脉冲动画
- 仅在流式输出开始前、AI 尚未产出第一个 token 时显示
- 流式输出开始后替换为逐字渲染的消息气泡

#### 流式输出中的 AI 消息

- 与普通 AI 消息相同的气泡样式
- 末尾追加闪烁光标 `▍`
- 内容实时通过 Markdown 渲染
- 流结束后光标消失

### 5.2 空状态

当会话无消息时，展示引导界面：

```
        💬

  开始与 {应用名} 对话
  {应用描述}。输入你的问题开始交互。

  ┌──────────────┐  ┌──────────────┐
  │ 快捷提问 1    │  │ 快捷提问 2    │
  └──────────────┘  └──────────────┘
  ┌──────────────┐  ┌──────────────┐
  │ 快捷提问 3    │  │ 快捷提问 4    │
  └──────────────┘  └──────────────┘
```

- 快捷提问按钮点击后自动填入输入框并发送
- 快捷提问内容可由应用配置中的 `app_config.quick_prompts` 提供，若未配置则不显示

### 5.3 Markdown 渲染规则

所有 AI 回复消息通过 Markdown 渲染引擎处理，支持以下语法：

| 语法 | 渲染效果 |
|------|---------|
| `**text**` | **粗体** |
| `` `code` `` | 行内代码（带背景色） |
| ` ```lang\n...\n``` ` | 代码块（深色背景，等宽字体） |
| `\|表头\|...\|` | 表格（带边框、悬停高亮） |
| `## 标题` / `### 标题` | 二级/三级标题 |
| `- 项目` | 无序列表 |
| `1. 项目` | 有序列表 |
| 双换行 | 段落分隔 |

使用项目已有的 `marked` 库进行渲染，复用现有 `.msg-content :deep()` 样式规则。

---

## 6. 输入区设计

### 6.1 布局

```
┌──────────────────────────────────────────────────┐
│ ┌──────────────────────────────────────────────┐ │
│ │ 输入你的问题...                                │ │
│ │                                    [发送按钮] │ │
│ └──────────────────────────────────────────────┘ │
│   Enter 发送 · Shift+Enter 换行                   │
└──────────────────────────────────────────────────┘
```

- 底部固定，不随消息列表滚动
- 输入框居中，最大宽度限制
- 圆角卡片样式，带微妙边框
- 输入框自适应高度（`auto-size`，最小 2 行，最大 6 行）
- 发送按钮：有内容时高亮主色调，无内容时置灰禁用
- 底部提示文案

### 6.2 键盘交互

| 按键 | 行为 |
|------|------|
| `Enter` | 发送消息（非流式进行中时） |
| `Shift + Enter` | 换行 |
| `Escape` | 退出全屏模式 |

### 6.3 发送流程

1. 检查输入非空且当前非流式进行中
2. 将用户消息追加到当前会话的消息列表
3. 清空输入框
4. 滚动消息列表到底部
5. 显示「正在思考」指示器
6. 调用 `POST /api/v1/open/app/{app_id}/stream`，请求体中携带当前会话的消息历史
7. 接收 SSE 事件，逐步渲染 AI 回复
8. 流结束后，将完整的 AI 回复持久化到后端

---

## 7. 数据模型设计

### 7.1 数据库表

#### `tb_conversation` — 会话表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `BIGINT` | Snowflake ID，主键 |
| `user_id` | `BIGINT` | 所属用户（关联 `tb_user.id`） |
| `app_id` | `BIGINT` | 关联应用（关联 `tb_app.id`） |
| `title` | `VARCHAR(255)` | 会话标题（取首条用户消息前 30 字，可由用户编辑） |
| `status` | `VARCHAR(32)` | `active` / `archived` |
| `create_time` | `BIGINT` | 创建时间，Unix 毫秒 |
| `update_time` | `BIGINT` | 最近更新时间，Unix 毫秒 |
| `create_user` | `BIGINT` | 创建者 |
| `update_user` | `BIGINT` | 更新者 |

#### `tb_conversation_message` — 会话消息表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `BIGINT` | Snowflake ID，主键 |
| `conversation_id` | `BIGINT` | 所属会话 |
| `role` | `VARCHAR(32)` | `user` / `assistant` / `system` / `tool` |
| `content` | `TEXT` | 消息文本内容 |
| `metadata` | `TEXT` | JSON 字符串，存储扩展信息（见 7.2） |
| `create_time` | `BIGINT` | 消息创建时间，Unix 毫秒 |
| `create_user` | `BIGINT` | 创建者 |

**设计说明**：

- 遵循项目规范：表名 `tb_` 前缀，无外键约束，审计字段
- `metadata` 为 JSON 字符串，不同 `role` 对应不同结构
- 不存储 `token` 使用量等运行指标，这些已由 `tb_app_log` 记录

### 7.2 消息 metadata 结构

```jsonc
// role = "assistant" 时
{
  "model": "gpt-4o",                  // 使用的模型
  "latency_ms": 3200,                 // 生成耗时
  "sources": ["文档A §2.3", "文档B"],  // RAG 引用来源（可选）
  "total_tokens": 400,                // token 统计（可选）
  "input_tokens": 120,
  "output_tokens": 280
}

// role = "tool" 时
{
  "tool_name": "search_web",
  "arguments": {"query": "天气"},
  "result": "北京今天晴，25°C"
}
```

### 7.3 会话标题生成策略

1. 创建会话时 `title` 为空
2. 首条用户消息发送后，取消息内容前 30 个字符作为 `title`
3. 后续用户可手动编辑 `title`（侧栏双击编辑）

---

## 8. API 设计

### 8.1 会话管理 API

路径前缀：`/api/v1/conversation`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/page` | 分页查询当前用户的会话列表（按 `update_time` 倒序） |
| `POST` | `/` | 创建会话（指定 `app_id`） |
| `GET` | `/{id}` | 获取会话详情（含消息列表） |
| `PUT` | `/{id}` | 更新会话（标题、状态） |
| `DELETE` | `/{id}` | 删除会话及其消息 |

#### 创建会话

```
POST /api/v1/conversation
```

请求体：

```json
{
  "app_id": "1234567890"
}
```

响应：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "id": "9876543210",
    "app_id": "1234567890",
    "app_type": "agent",
    "app_name": "根因分析助手",
    "title": "",
    "status": "active",
    "create_time": 1713254400000,
    "update_time": 1713254400000
  }
}
```

#### 查询会话列表

```
GET /api/v1/conversation/page?page_no=1&page_size=50&status=active
```

响应：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "total": 12,
    "items": [
      {
        "id": "9876543210",
        "app_id": "1234567890",
        "app_type": "agent",
        "app_name": "根因分析助手",
        "title": "Pod 重启排查流程",
        "status": "active",
        "last_message": "根据运维手册，Pod 频繁重启排查步骤...",
        "create_time": 1713254400000,
        "update_time": 1713258000000
      }
    ]
  }
}
```

### 8.2 对话消息 API

路径前缀：`/api/v1/conversation/{conversation_id}/message`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | 获取会话的全部消息列表 |
| `POST` | `/` | 发送用户消息并触发 AI 流式回复 |
| `POST` | `/stream` | 发送用户消息并以 SSE 流式返回 AI 回复 |

#### 发送消息（流式）

```
POST /api/v1/conversation/{conversation_id}/message/stream
Content-Type: application/json
```

请求体：

```json
{
  "content": "Pod 频繁重启怎么排查？"
}
```

**处理逻辑**：

1. 将用户消息写入 `tb_conversation_message`
2. 从 `tb_conversation_message` 加载该会话的历史消息，构建 `messages` 数组
3. 如果是首条用户消息，自动更新 `conversation.title`
4. 调用应用执行引擎（复用 `LlmApp.stream()` / `AgentApp.stream()`）
5. 以 SSE 格式流式返回

**SSE 事件格式**（复用现有定义）：

```
event: metadata
data: {"app_id":"123","app_type":"agent","model":"gpt-4o","conversation_id":"456"}

event: token
data: {"content":"根据"}

event: token
data: {"content":"运维手册"}

event: tool_call_start
data: {"tool_call_id":"tc_1","name":"search_kb","arguments":{"query":"Pod重启"}}

event: tool_call_end
data: {"tool_call_id":"tc_1","name":"search_kb","result":"..."}

event: message_complete
data: {"content":"完整回复文本...","usage":{"total_tokens":400,"input_tokens":120,"output_tokens":280},"sources":["文档A"]}

event: done
data: {"latency_ms":3200}

data: [DONE]
```

6. 流结束后，将完整的 AI 回复写入 `tb_conversation_message`
7. 更新 `conversation.update_time`
8. 写入 `tb_app_log`（`request_type = 'chat'`，关联 `conversation_id`）

### 8.3 已发布应用列表 API

智能助手页面需要获取已发布的应用列表用于应用选择器：

```
GET /api/v1/app/page?page_no=1&page_size=200&app_status=published
```

此 API 已存在，无需新增。

---

## 9. 前端实现设计

### 9.1 路由

```typescript
// router/index.ts
{
  path: "assistant",
  name: "assistant",
  meta: { title: "智能助手", menu: { title: "智能助手", icon: "robot", order: 1 } },
  component: () => import("@/views/assistant/AssistantView.vue"),
}
```

替换现有的 `MockFeatureView`。

### 9.2 文件结构

```
frontend/src/
├── views/assistant/
│   └── AssistantView.vue        # 主页面（侧栏 + 对话主区）
├── api/
│   ├── conversation.ts          # 会话管理 API
│   ├── app.ts                   # 已有，复用 testAppStream
│   └── sse.ts                   # 已有，SSE 客户端
└── api/types.ts                 # 补充 Conversation / ConversationMessage 类型
```

### 9.3 核心类型定义

```typescript
// types.ts 补充

interface ConversationResp {
  id: string;
  app_id: string;
  app_type: string;
  app_name: string;
  title: string;
  status: "active" | "archived";
  last_message?: string;
  create_time: number;
  update_time: number;
}

interface ConversationMessageResp {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  metadata?: {
    model?: string;
    latency_ms?: number;
    sources?: string[];
    total_tokens?: number;
    input_tokens?: number;
    output_tokens?: number;
    tool_name?: string;
    arguments?: Record<string, unknown>;
    result?: string;
  };
  create_time: number;
}
```

### 9.4 API 函数

```typescript
// api/conversation.ts

export function pageConversation(params: {
  page_no: number; page_size: number; status?: string;
})

export function createConversation(body: { app_id: string })

export function getConversation(id: string)

export function updateConversation(id: string, body: { title?: string; status?: string })

export function deleteConversation(id: string)

export function listMessages(conversationId: string)

export function sendMessageStream(
  conversationId: string,
  body: { content: string },
  options: Omit<SSEOptions, "signal">,
): { abort: () => void }
```

### 9.5 前端状态管理

`AssistantView.vue` 使用组件本地状态（与原型一致，不引入 Pinia store）：

```typescript
// 会话数据
const conversations = ref<ConversationResp[]>([]);         // 侧栏列表
const currentConversation = ref<ConversationResp | null>(null);  // 当前选中
const messages = ref<ConversationMessageResp[]>([]);        // 当前会话消息

// 应用数据
const publishedApps = ref<AppResp[]>([]);                   // 已发布应用列表
const selectedApp = ref<AppResp | null>(null);              // 当前选中应用

// 输入状态
const inputText = ref("");
const isStreaming = ref(false);
const streamingContent = ref("");
const streamingToolCalls = ref<StreamingToolCall[]>([]);
const streamAbort = ref<{ abort: () => void } | null>(null);

// UI 状态
const showAppPicker = ref(false);
const isFullscreen = ref(false);
```

### 9.6 消息流式处理

复用现有 `fetchSSE` 工具和 SSE 事件处理模式（与 `AppDetailView.vue` 中的测试面板一致）：

```typescript
function sendMessage() {
  if (!inputText.value.trim() || isStreaming.value) return;

  // 1. 本地追加用户消息
  messages.value.push({
    id: "",  // 由后端返回
    conversation_id: currentConversation.value!.id,
    role: "user",
    content: inputText.value.trim(),
    create_time: Date.now(),
  });
  const userContent = inputText.value.trim();
  inputText.value = "";
  scrollToBottom();

  // 2. 启动流式请求
  isStreaming.value = true;
  streamingContent.value = "";
  streamingToolCalls.value = [];

  streamAbort.value = sendMessageStream(
    currentConversation.value!.id,
    { content: userContent },
    {
      onEvent(evt) {
        // 复用 handleStreamEvent 逻辑
        // token → streamingContent += content
        // tool_call_start → streamingToolCalls.push(...)
        // tool_call_end → 更新对应工具状态
        // message_complete → 提取 sources、usage
      },
      onDone() {
        // 将完整 AI 回复追加到 messages
        messages.value.push({
          role: "assistant",
          content: streamingContent.value,
          metadata: { sources, usage },
          create_time: Date.now(),
        });
        isStreaming.value = false;
        streamingContent.value = "";
        // 刷新侧栏（更新 last_message 和 update_time）
      },
      onError(err) {
        message.error(err.message);
        isStreaming.value = false;
      },
    },
  );
}
```

---

## 10. 后端实现设计

### 10.1 文件结构

```
backend/app/
├── api/
│   └── conversation_api.py       # 会话管理路由
├── service/
│   └── conversation_service.py   # 会话业务逻辑
├── model/
│   └── conversation_model.py     # 请求/响应 Pydantic 模型
└── db/
    └── schema.py                 # 新增 TbConversation / TbConversationMessage
```

### 10.2 路由注册

```python
# api/conversation_api.py
router = APIRouter(prefix="/conversation", tags=["conversation"])
```

在 `api/router.py` 中注册到 `api_router`。

### 10.3 Service 层关键逻辑

#### `send_message_stream()`

```python
async def send_message_stream(
    db: Session,
    conversation_id: int,
    content: str,
    req_ctx: RequestContext,
) -> AsyncGenerator[str, None]:
    """
    1. 校验会话存在且属于当前用户
    2. 保存用户消息到 tb_conversation_message
    3. 如果是首条用户消息，更新 conversation.title
    4. 从 tb_conversation_message 加载历史消息，构建 messages 列表
    5. 获取会话关联的 app，构建执行请求
    6. 调用 LlmApp.stream() / AgentApp.stream()（复用现有能力）
    7. 透传 SSE 事件给前端
    8. 流结束后保存 AI 回复到 tb_conversation_message
    9. 更新 conversation.update_time
    """
```

**上下文构建规则**：

```python
# 加载历史消息，转为 ModelGatewayChatMessage 列表
history = db.scalars(
    select(TbConversationMessage)
    .where(TbConversationMessage.conversation_id == conversation_id)
    .where(TbConversationMessage.role.in_(["user", "assistant"]))
    .order_by(TbConversationMessage.create_time)
).all()

messages = [
    ModelGatewayChatMessage(role=msg.role, content=msg.content)
    for msg in history
]
```

**上下文窗口限制**：

- 默认携带最近 20 轮（40 条）消息
- 可通过应用配置 `app_config.max_context_turns` 自定义
- 超出限制时截断最早的消息，但始终保留 system prompt

### 10.4 Alembic 迁移

新增两张表的 Alembic migration，确保字段与 7.1 节定义一致。

---

## 11. 交互细节

### 11.1 新建对话

1. 点击侧栏「新建对话」按钮
2. 调用 `POST /api/v1/conversation` 创建会话（关联当前选中的 `app_id`）
3. 清空消息列表，展示空状态
4. 将新会话插入侧栏列表顶部并选中

### 11.2 切换会话

1. 点击侧栏某个历史会话
2. 更新 `currentConversation`
3. 如果该会话关联的 `app_id` 与当前 `selectedApp` 不同，同步切换 `selectedApp`
4. 调用 `GET /api/v1/conversation/{id}/message` 加载消息
5. 渲染消息列表，滚动到底部

### 11.3 切换应用

1. 通过顶部应用选择器选中新应用
2. 查找侧栏中是否有该应用的最近活跃会话
   - 有 → 切换到该会话
   - 无 → 自动创建新会话

### 11.4 流式中断

1. 用户在流式进行中点击「停止」按钮或切换会话
2. 调用 `streamAbort.abort()` 取消请求
3. 将已接收的部分内容作为 AI 回复保存（标记为 incomplete）
4. 恢复输入区为可用状态

### 11.5 错误处理

| 场景 | 处理 |
|------|------|
| 网络断开 | 显示错误提示，消息标记为发送失败，支持重试 |
| 应用执行超时 | SSE error 事件 → 显示错误消息气泡 |
| 应用已下线 | 创建会话时校验 app_status，返回错误提示 |
| 会话已归档 | 只读展示消息列表，输入区禁用 |

### 11.6 自动滚动

- 发送消息后自动滚动到底部
- 流式输出过程中持续滚动到底部
- 如果用户手动向上滚动浏览历史，暂停自动滚动
- 用户滚回底部附近时恢复自动滚动

---

## 12. 与现有模块的集成

### 12.1 复用清单

| 现有组件/模块 | 在智能助手中的复用方式 |
|-------------|---------------------|
| `fetchSSE()` (`api/sse.ts`) | 直接复用，用于流式消息接收 |
| SSE 事件格式 (`core/sse.py`) | 直接复用，`conversation/message/stream` 返回相同的事件类型 |
| `LlmApp.stream()` / `AgentApp.stream()` | 在 `ConversationService` 中调用，传入历史消息上下文 |
| `AppRuntime` | 复用应用配置加载和模型构建 |
| `AppLogService` | 为 `request_type = 'chat'` 的请求写入日志 |
| `renderMarkdown()` | 前端复用 `marked` 库渲染 AI 回复 |
| `msg-card` 样式 | 可参考 `AppDetailView.vue` 中的消息卡片样式 |
| `tl-item` 时间轴 | 可参考 `AppDetailView.vue` 中的时间轴结构 |

### 12.2 TbAppLog 扩展

在 `tb_app_log` 表中新增一个可选字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `BIGINT` | 关联会话（仅 `request_type = 'chat'` 时有值） |

这样在应用详情的「历史消息」Tab 中可以展示来自智能助手的对话日志，并链接到具体会话。

---

## 13. 实施计划

### 阶段一：基础对话（MVP）

**目标**：可选择应用、发送消息、流式接收回复、会话持久化

| 任务 | 范围 | 关键文件 |
|------|------|---------|
| 1. 数据库表创建 | 后端 | `schema.py`, Alembic migration |
| 2. 会话管理 API | 后端 | `conversation_api.py`, `conversation_service.py`, `conversation_model.py` |
| 3. 对话消息流式 API | 后端 | `conversation_api.py` 中的 `/message/stream` |
| 4. 前端会话 API 层 | 前端 | `api/conversation.ts`, `api/types.ts` |
| 5. AssistantView 主页面 | 前端 | `views/assistant/AssistantView.vue` |
| 6. 路由替换 | 前端 | `router/index.ts` |

### 阶段二：交互增强

| 任务 | 说明 |
|------|------|
| 会话标题编辑 | 侧栏双击编辑标题 |
| 会话归档/删除 | 右键菜单操作 |
| 消息重试 | 失败消息支持重新发送 |
| 全屏模式 | 支持全屏对话 |
| 快捷提问 | 空状态展示应用配置的快捷提问按钮 |

### 阶段三：高级功能

| 任务 | 说明 |
|------|------|
| RAG 引用来源展示 | AI 回复下方展示知识来源标签 |
| 上下文窗口配置 | 应用配置中设置最大上下文轮次 |
| 消息搜索 | 侧栏搜索历史会话和消息内容 |
| 会话分享 | 生成只读分享链接 |
