# Todo 实时面板实施计划

> Q1 长会话能力交付后的扩展：把 agent 的任务清单（DeepAgents/LangChain `TodoListMiddleware` 维护的 `state.todos`）实时镜像到 UI 右侧栏，让用户随时看到 agent 正在做什么、还剩几步。

---

## 1. 范围与目标

**做什么**：
- agent 调 `write_todos` 工具时，实时把最新 todos 列表推到前端
- 前端右侧栏显示当前状态（pending / in_progress / completed）
- 重新打开历史会话并发消息时，恢复 panel 状态

**不做**：
- 用户编辑 / 删除 todos（agent 自治，UI 只读）
- todos 历史快照 / 时间轴（直接看聊天泡泡里的 `write_todos` 工具调用即可）
- 嵌套 todos（子代理的 todos）—— DeepAgents 设计上子代理 state 不冒泡到主 state，初版接受
- 跨会话 todo 看板

---

## 2. 决策记录

| # | 决策点 | 选定方案 |
|---|---|---|
| 1 | UI 布局 | **B 右侧栏**：`chat-main` 改 grid 两列；280-320px；可折叠成 40px 窄条 |
| 2 | 实时变更触发源 | **监听 `write_todos` 工具调用**（不走 LangGraph state diff，简单稳） |
| 3 | 历史 API | **不实现 GET 端点**。改为：流启动时若 checkpoint 有 todos，发一条初始快照 SSE |
| 4 | 工具调用展示 | 聊天泡泡里 `write_todos` 工具条**保持不变**——继续作为时间序"修改日志"；右栏与之**并存**，是"状态镜像" |
| 5 | 折叠态持久化 | **localStorage**：`todoPanelCollapsed` 布尔值 |
| 6 | 移动端 | 窄屏（< 768px）改为**底部抽屉**，不挤压聊天区 |
| 7 | 节流 | 50ms `requestAnimationFrame` 节流避免 burst 闪烁 |

---

## 3. 数据流

```
[用户发消息]
    ↓
stream() 启动
    ↓
emit metadata 事件
    ↓
若 checkpoint 存在且 state.todos 非空
    └─→ emit todo_update {todos: [...]}    ← 初始快照
    ↓
astream_events 循环
    ├─ on_tool_start (write_todos) → 仍走 SSE_EVENT_TOOL_CALL_START（保留泡泡内显示）
    ├─ on_tool_end   (write_todos) → 走原有 SSE_EVENT_TOOL_CALL_END（泡泡内）
    │                              + emit todo_update {todos: <从 input 取>}  ← 实时
    └─ ... 继续 token / 其他工具 ...
    ↓
done

[用户切到这个会话]
    ↓
selectConversation(): TodoPanel 状态清空
    ↓
[用户发消息后]
    ↓
SSE 中的初始快照 + 实时 update 把 panel 重新填满
```

**关键点**：纯阅读历史会话（打开但不发消息）时 panel 留空——这是设计文档第 3 条决策的妥协，避免 GET API 带来的复杂度。

---

## 4. 后端改造

### 4.1 新增 SSE 事件常量

`app/core/sse.py` 增加：

```python
SSE_EVENT_TODO_UPDATE = "todo_update"
```

### 4.2 `agent_app.stream` 改造

**A. 启动初始快照**（在 `metadata` 事件之后、astream_events 循环之前）：

```python
if prep.use_checkpoint and prep.thread_id:
    saver = self._checkpointer_factory.get()
    ckpt = await saver.aget_tuple({"configurable": {"thread_id": prep.thread_id}})
    if ckpt:
        cv = ckpt.checkpoint.get("channel_values", {})
        existing_todos = cv.get("todos") or []
        if existing_todos:
            yield format_sse_event(
                SSE_EVENT_TODO_UPDATE,
                {"todos": _serialize_todos(existing_todos)},
            )
```

**B. 实时变更**（在 astream_events 循环内，`on_tool_end` 分支）：

```python
elif kind == "on_tool_end":
    # ... 现有 SSE_EVENT_TOOL_CALL_END 推送保持不变 ...

    # 新增：write_todos 工具的入参就是新 todos 全量
    if event.get("name") == "write_todos":
        tool_input = data.get("input") or {}
        new_todos = tool_input.get("todos") or []
        yield format_sse_event(
            SSE_EVENT_TODO_UPDATE,
            {"todos": _serialize_todos(new_todos)},
        )
```

**C. `_serialize_todos` 辅助**：

```python
def _serialize_todos(todos: list) -> list[dict]:
    """把 LangChain Todo TypedDict 列表归一化成纯 JSON。"""
    out = []
    for t in todos or []:
        if isinstance(t, dict):
            out.append({
                "content": str(t.get("content") or ""),
                "status": str(t.get("status") or "pending"),
            })
    return out
```

### 4.3 `run()` 不改

非流式 `run()` 不发 SSE，todos 只在流式场景有意义；最终结果 `result["todos"]` 已自然包含在 LangGraph state，调用方需要可自取。

### 4.4 失败兜底

- 初始快照读 saver 失败 → log warning，不发初始事件，**不阻塞主流**
- write_todos 解析 input 失败 → 跳过这次推送（panel 暂时不更新），不影响泡泡里的工具调用展示

---

## 5. 前端改造

### 5.1 新增组件 `TodoPanel.vue`

`frontend/src/components/TodoPanel.vue`：

```vue
<template>
  <aside :class="['todo-panel', collapsed ? 'todo-panel--collapsed' : '']">
    <header class="todo-panel-header">
      <span class="todo-panel-title">任务清单</span>
      <span class="todo-panel-progress">{{ doneCount }}/{{ todos.length }}</span>
      <button class="todo-panel-toggle" @click="toggle"> {{ collapsed ? '▶' : '▼' }} </button>
    </header>
    <ul v-if="!collapsed" class="todo-panel-list">
      <li v-for="(t, i) in todos" :key="i" :class="['todo-item', `todo-item--${t.status}`]">
        <span class="todo-item-icon">{{ statusIcon(t.status) }}</span>
        <span class="todo-item-content">{{ t.content }}</span>
      </li>
    </ul>
  </aside>
</template>
```

**Props**：`todos: Todo[]`
**Local state**：`collapsed`（从 localStorage 初始化）
**事件**：`@toggle` 时写 localStorage

**视觉**：

| 状态 | 图标 | 颜色 |
|---|---|---|
| pending | `○` | 灰 #94a3b8 |
| in_progress | `⠋` 转圈 spinner | 主色 #2563eb |
| completed | `✓` | 绿 #16a34a |

### 5.2 `AssistantView.vue` 集成

新增类型 + ref：

```ts
interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}
const todos = ref<Todo[]>([]);
```

SSE 事件处理新增 case：

```ts
case "todo_update":
  todos.value = (evt.data.todos as Todo[]) || [];
  break;
```

切会话清空：`selectConversation` / `createNewChat` 里 `todos.value = []`。

显示规则：

```ts
const showTodoPanel = computed(
  () =>
    selectedApp.value?.app_type === "agent" && todos.value.length > 0,
);
```

布局：把 chat-main 从单列改 grid：

```css
.chat-main {
  display: grid;
  grid-template-columns: 1fr auto;  /* 主区 + 右栏 */
}
.todo-panel {
  width: 320px;
  border-left: 1px solid #e2e8f0;
}
.todo-panel--collapsed {
  width: 40px;
}
@media (max-width: 768px) {
  .chat-main { grid-template-columns: 1fr; }
  .todo-panel {
    position: fixed; bottom: 0; left: 0; right: 0;
    width: 100%; max-height: 50vh;
  }
}
```

### 5.3 节流

`todo_update` 高频时（agent 在一轮里多次刷）用 RAF 节流：

```ts
let pendingTodos: Todo[] | null = null;
let raf: number | null = null;
function applyTodoUpdate(next: Todo[]) {
  pendingTodos = next;
  if (raf !== null) return;
  raf = requestAnimationFrame(() => {
    todos.value = pendingTodos!;
    pendingTodos = null;
    raf = null;
  });
}
```

---

## 6. 与现有功能交互

| 现有功能 | 影响 |
|---|---|
| `use_checkpoint=False` 一次性调用 | 流启动时无 checkpoint → 不发初始快照；流期间仍正常推 todo_update；流结束后下次回来 panel 空（合理） |
| 降级路径（checkpoint 缺失 + 业务消息）| 业务消息没存 todos，初始快照不发；agent 后续若调 write_todos 重建 |
| reset / delete 会话 | checkpoint 删 → 下次 panel 空，符合预期 |
| 技能 subagent 调 write_todos | 子代理 state 独立，主 state.todos 不受影响——主 panel 不会刷新；初版接受 |
| 多轮对话 | 跨轮 panel 状态保留（取决于长会话开关）|
| 切到 LLM/RAG 应用 | `showTodoPanel` 为 false，整个右栏 `display: none`，不挤压聊天区 |
| 折叠状态 | localStorage 持久化，跨刷新保持 |

---

## 7. 风险与边界

| 风险 | 处理 |
|---|---|
| `write_todos` 一轮内被多次调用 | RAF 节流（5.3） |
| 初始快照 saver 读取失败 | log warning + 不阻塞主流 |
| Todo 数量极多（>50）导致面板过长 | 列表内 `max-height: calc(100vh - 200px); overflow-y: auto` 自带滚动 |
| 历史会话纯阅读不发消息 | panel 空（设计接受）|
| 子代理 todos 不可见 | 文档明示，未来支持嵌套时单独 PR |
| SSE 中途断开重连 | 不重发已发送事件；下次刷新会从 checkpoint 拉初始快照（前提 long-session ON）|

---

## 8. 工作量拆分

| PR | 工作量 | 内容 |
|---|---|---|
| **PR-T1 后端 SSE** | 1 天 | `SSE_EVENT_TODO_UPDATE` 常量；`stream()` 改造（初始快照 + 工具监听）；`_serialize_todos` 辅助；冒烟测试 |
| **PR-T2 前端面板 + 集成** | 2 天 | `TodoPanel.vue` 组件；`AssistantView.vue` SSE handler + 状态 + 切换清空；CSS grid + 移动端 + localStorage；节流 |
| **PR-T3 联调** | 0.5 天 | 切会话 / 切应用 / 长会话开关切换 / 历史会话重开 / 折叠态恢复 等场景手测 |
| **合计** | **~3.5 人日** | 不含设计评审 |

---

## 9. 测试矩阵

| 场景 | 期望 |
|---|---|
| agent 应用 + 长会话 ON + 首轮触发 write_todos | 右栏出现，按 todo 状态显示 |
| 同会话第二轮再次 write_todos | 右栏内容刷新，无闪烁（节流生效）|
| 切到 LLM/RAG 应用 | 右栏整体消失（不只是清空）|
| 切回原 agent 会话 | 发消息后 SSE 初始快照恢复 panel |
| 长会话 OFF | 流期间面板正常；流结束后切回，面板空 |
| 折叠后刷新页面 | 折叠态保留 |
| 移动端 | 右栏变成底部抽屉 |
| `write_todos` 工具调用 | 聊天泡泡里**仍然显示**该工具条，可点开看参数（与右栏并存）|
| reset 会话后再发消息 | 右栏从空开始重建 |
| Todo 50+ | 面板内自带滚动，不溢出页面 |

---

## 10. 不做（明确划走）

- 用户编辑 / 删除 / 排序 todos
- todos 历史时间轴（看泡泡里 write_todos 工具调用）
- 跨会话 todo 全局看板
- 子代理 todos 嵌套显示
- todos 关联到具体消息 anchor
- todos 导出 / 分享

需要时单独立项。
