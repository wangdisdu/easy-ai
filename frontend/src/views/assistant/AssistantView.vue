<template>
  <div class="assistant-page">
    <!-- 会话侧栏 -->
    <aside class="conv-sidebar">
      <div class="conv-sidebar-header">
        <a-button type="primary" block @click="createNewChat">
          <template #icon><PlusOutlined /></template>
          新建对话
        </a-button>
      </div>
      <div class="conv-list">
        <div
          v-for="conv in conversations"
          :key="conv.id"
          :class="['conv-item', currentConversation?.id === conv.id ? 'conv-item--active' : '']"
          @click="selectConversation(conv)"
        >
          <div class="conv-item-head">
            <span :class="['conv-type-tag', `conv-type--${conv.app_type}`]">{{ appTypeShort[conv.app_type] || conv.app_type }}</span>
            <span class="conv-app-name">{{ conv.app_name }}</span>
            <span class="conv-time">{{ formatRelativeTime(conv.update_time) }}</span>
          </div>
          <div class="conv-title">{{ conv.title || "新对话" }}</div>
          <div v-if="conv.last_message" class="conv-preview">{{ conv.last_message }}</div>
          <a-popconfirm
            title="删除该会话？"
            description="消息历史和运行态都会被清掉，无法恢复。"
            ok-text="删除"
            cancel-text="取消"
            ok-type="danger"
            @confirm="deleteConv(conv)"
          >
            <DeleteOutlined class="conv-item-delete" :title="'删除会话'" @click.stop />
          </a-popconfirm>
        </div>
        <a-empty v-if="!conversations.length" :image="false" description="暂无对话" class="conv-empty" />
      </div>
    </aside>

    <!-- 对话主区 -->
    <main class="chat-main">
      <!-- 顶部栏 -->
      <div class="chat-topbar">
        <div class="chat-app-selector" @click.stop>
          <a-button class="app-picker-btn" @click="togglePicker">
            <span v-if="selectedApp" :class="['conv-type-tag', `conv-type--${selectedApp.app_type}`]">{{ appTypeShort[selectedApp.app_type] || selectedApp.app_type }}</span>
            <span class="app-picker-name">{{ selectedApp?.name || "选择应用" }}</span>
            <DownOutlined class="app-picker-arrow" />
          </a-button>

          <!-- 两级下拉菜单 -->
          <div v-if="showAppPicker" v-click-outside="closePicker" class="app-picker-dropdown">
            <template v-if="!pickerType">
              <div class="picker-section-title">选择应用类型</div>
              <div
                v-for="t in appTypeList"
                :key="t.id"
                class="picker-option"
                @click="pickerType = t.id"
              >
                <span class="picker-option-icon">{{ t.icon }}</span>
                <div class="picker-option-text">
                  <div class="picker-option-label">{{ t.label }}</div>
                  <div class="picker-option-desc">{{ t.desc }}</div>
                </div>
                <RightOutlined class="picker-option-arrow" />
              </div>
            </template>
            <template v-else>
              <div class="picker-section-title picker-section-back" @click="pickerType = null">
                <LeftOutlined /> {{ appTypeList.find((t) => t.id === pickerType)?.label }}
              </div>
              <div
                v-for="a in filteredApps"
                :key="a.id"
                :class="['picker-option', selectedApp?.id === a.id ? 'picker-option--active' : '']"
                @click="selectApp(a)"
              >
                <div class="picker-option-text">
                  <div class="picker-option-label">{{ a.name }}</div>
                  <div class="picker-option-desc">{{ a.description || "" }}</div>
                </div>
                <CheckOutlined v-if="selectedApp?.id === a.id" class="picker-check" />
              </div>
              <a-empty v-if="!filteredApps.length" :image="false" description="暂无该类型的已发布应用" />
            </template>
          </div>
        </div>
        <span class="chat-topbar-hint">多轮对话 · 上下文自动携带</span>
      </div>

      <!-- 消息列表 -->
      <div ref="chatContainer" class="chat-messages">
        <!-- 空状态 -->
        <div v-if="!messages.length && !isStreaming" class="chat-empty">
          <div class="chat-empty-icon">{{ selectedApp?.app_type === 'agent' ? '🤖' : '✨' }}</div>
          <h3 class="chat-empty-title">开始与 {{ selectedApp?.name || "AI" }} 对话</h3>
          <p class="chat-empty-desc">{{ selectedApp?.description || "输入你的问题开始交互" }}</p>
        </div>

        <!-- 按轮次展示消息 -->
        <template v-for="(turn, ti) in messageTurns" :key="ti">
          <!-- 用户消息 -->
          <div class="chat-msg chat-msg--user">
            <div class="chat-bubble chat-bubble--user">{{ turn.user.content }}</div>
            <div class="chat-msg-time chat-msg-time--right">{{ formatMsgTime(turn.user.create_time) }}</div>
          </div>

          <!-- AI 回复（工具 + 文本合并为一个气泡） -->
          <div v-if="turn.replies.length" class="chat-msg chat-msg--assistant">
            <div class="chat-avatar">AI</div>
            <div class="chat-bubble-wrap">
              <div class="chat-bubble chat-bubble--ai">
                <!-- 工具调用（紧凑行，点击展开） -->
                <div
                  v-for="(tool, tIdx) in turn.tools"
                  :key="'t-' + tIdx"
                  class="chat-tool-inline"
                >
                  <div class="chat-tool-row" @click="toggleToolExpand(tool.id || `${ti}-${tIdx}`)">
                    <span class="chat-tool-icon">🔧</span>
                    <span class="chat-tool-name">{{ (tool.metadata as Record<string, unknown>)?.tool_name || "工具调用" }}</span>
                    <span :class="[(tool.metadata as Record<string, unknown>)?.status === 'error' ? 'chat-tool-error' : 'chat-tool-done']">
                      {{ (tool.metadata as Record<string, unknown>)?.status === 'error' ? 'error' : 'done' }}
                    </span>
                    <RightOutlined :class="['chat-tool-chevron', expandedTools.has(tool.id || `${ti}-${tIdx}`) ? 'chat-tool-chevron--open' : '']" />
                  </div>
                  <div v-if="expandedTools.has(tool.id || `${ti}-${tIdx}`)" class="chat-tool-detail">
                    <pre v-if="(tool.metadata as Record<string, unknown>)?.arguments" class="chat-tool-args">{{ JSON.stringify((tool.metadata as Record<string, unknown>).arguments, null, 2) }}</pre>
                    <div v-if="tool.content" class="chat-tool-result">{{ tool.content }}</div>
                  </div>
                </div>

                <!-- AI 文本内容 -->
                <template v-for="(ai, aIdx) in turn.assistants" :key="'a-' + aIdx">
                  <div v-if="ai.content" class="msg-content" v-html="renderMarkdown(ai.content)"></div>
                </template>
              </div>

              <!-- 引用来源 -->
              <div v-if="getTurnSources(turn).length" class="chat-sources">
                <span v-for="s in getTurnSources(turn)" :key="s" class="chat-source-tag">{{ s }}</span>
              </div>
              <div class="chat-msg-time">{{ formatMsgTime(turn.replies[turn.replies.length - 1].create_time) }}</div>
            </div>
          </div>
        </template>

        <!-- 流式 AI 回复（工具 + 文本合并为一个气泡） -->
        <div v-if="isStreaming || streamingContent || streamingToolCalls.length" class="chat-msg chat-msg--assistant">
          <div class="chat-avatar">AI</div>
          <div class="chat-bubble-wrap">
            <div class="chat-bubble chat-bubble--ai">
              <!-- 流式工具调用 -->
              <div
                v-for="(tc, idx) in streamingToolCalls"
                :key="'stc-' + idx"
                class="chat-tool-inline"
              >
                <div class="chat-tool-row" @click="tc._expanded = !tc._expanded">
                  <span class="chat-tool-icon">🔧</span>
                  <span class="chat-tool-name">{{ tc.name }}</span>
                  <a-spin v-if="tc.status === 'running'" size="small" />
                  <template v-else>
                    <span :class="tc.status === 'error' ? 'chat-tool-error' : 'chat-tool-done'">{{ tc.status === 'error' ? 'error' : 'done' }}</span>
                    <RightOutlined :class="['chat-tool-chevron', tc._expanded ? 'chat-tool-chevron--open' : '']" />
                  </template>
                </div>
                <div v-if="tc._expanded" class="chat-tool-detail">
                  <pre v-if="tc.arguments && Object.keys(tc.arguments).length" class="chat-tool-args">{{ JSON.stringify(tc.arguments, null, 2) }}</pre>
                  <div v-if="tc.result" class="chat-tool-result">{{ tc.result.length > 500 ? tc.result.slice(0, 500) + '...' : tc.result }}</div>
                </div>
              </div>

              <!-- 流式文本 -->
              <div v-if="streamingContent" class="msg-content" v-html="renderMarkdown(streamingContent + '▍')"></div>
              <!-- 处理中指示器：只要仍在流式且没有文本内容，就显示思考动画 -->
              <div v-if="isStreaming && !streamingContent" class="chat-thinking">
                <span class="dot" /><span class="dot" /><span class="dot" />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-area">
        <div class="chat-composer">
          <a-textarea
            v-model:value="inputText"
            :auto-size="{ minRows: 1, maxRows: 6 }"
            :disabled="isStreaming"
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
            class="chat-textarea"
            @pressEnter="onEnter"
          />
          <div class="chat-composer-bar">
            <span v-if="streamMeta.model" class="chat-meta-tag">{{ streamMeta.model }}</span>
            <span class="chat-composer-spacer" />
            <a-button v-if="isStreaming" size="small" danger @click="stopStream">停止</a-button>
            <a-button
              type="primary"
              size="small"
              :disabled="!inputText.trim() || isStreaming"
              @click="sendMessage"
            >
              发送
            </a-button>
          </div>
        </div>
        <div class="chat-input-hint">Enter 发送 · Shift+Enter 换行 · 内容由 AI 生成，请注意甄别</div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, reactive } from "vue";
import {
  PlusOutlined,
  DownOutlined,
  RightOutlined,
  LeftOutlined,
  CheckOutlined,
  DeleteOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { marked } from "marked";
import * as convApi from "@/api/conversation";
import * as appApi from "@/api/app";
import type { AppResp, ConversationResp, ConversationMessageResp } from "@/api/types";
import type { SSEEvent } from "@/api/sse";

// ── 状态 ──

const conversations = ref<ConversationResp[]>([]);
const currentConversation = ref<ConversationResp | null>(null);
const messages = ref<ConversationMessageResp[]>([]);
const publishedApps = ref<AppResp[]>([]);
const selectedApp = ref<AppResp | null>(null);
const inputText = ref("");
const chatContainer = ref<HTMLElement | null>(null);

// 流式状态
interface StreamingToolCall {
  tool_call_id: string;
  name: string;
  status: "running" | "success" | "error";
  arguments?: Record<string, unknown>;
  result?: string;
  _expanded?: boolean;
}

// 消息轮次（一条用户消息 + 后续所有 AI/tool 回复）
interface MessageTurn {
  user: ConversationMessageResp;
  replies: ConversationMessageResp[];
  tools: ConversationMessageResp[];
  assistants: ConversationMessageResp[];
}
const isStreaming = ref(false);
const streamingContent = ref("");
const streamingToolCalls = ref<StreamingToolCall[]>([]);
const streamAbort = ref<{ abort: () => void } | null>(null);
const streamMeta = reactive<{ model: string; sources: string[]; usage: Record<string, unknown> | null; latency_ms: number | null }>({
  model: "",
  sources: [],
  usage: null,
  latency_ms: null,
});

// 应用选择器
const showAppPicker = ref(false);
const pickerType = ref<string | null>(null);

const appTypeShort: Record<string, string> = {
  llm: "LLM",
  rag: "RAG",
  agent: "Agent",
  nl2sql: "NL2SQL",
  agent_flow: "Flow",
};

const appTypeList = [
  { id: "llm", label: "LLM 应用", desc: "大模型通用应用", icon: "✨" },
  { id: "rag", label: "RAG 知识库问答", desc: "基于知识库的问答", icon: "📚" },
  { id: "agent", label: "Agent 智能体", desc: "可调用工具的智能体", icon: "🤖" },
  { id: "nl2sql", label: "NL2SQL 数据查询", desc: "自然语言查数据", icon: "🗄" },
];

const filteredApps = computed(() =>
  pickerType.value
    ? publishedApps.value.filter((a) => a.app_type === pickerType.value)
    : [],
);


// 展开状态独立管理（不放在 computed 内，避免重算时重置）
const expandedTools = reactive<Set<string>>(new Set());

function toggleToolExpand(key: string) {
  if (expandedTools.has(key)) {
    expandedTools.delete(key);
  } else {
    expandedTools.add(key);
  }
}

// 将消息列表按轮次分组
const messageTurns = computed<MessageTurn[]>(() => {
  const turns: MessageTurn[] = [];
  let current: MessageTurn | null = null;
  for (const msg of messages.value) {
    if (msg.role === "user") {
      current = { user: msg, replies: [], tools: [], assistants: [] };
      turns.push(current);
    } else if (current) {
      current.replies.push(msg);
      if (msg.role === "tool") {
        current.tools.push(msg);
      } else {
        current.assistants.push(msg);
      }
    }
  }
  return turns;
});

// ── 工具函数 ──

function renderMarkdown(text: string): string {
  return marked(text) as string;
}

function formatRelativeTime(ms: number): string {
  const now = Date.now();
  const diff = now - ms;
  if (diff < 86400000) {
    const d = new Date(ms);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  if (diff < 172800000) return "昨天";
  const d = new Date(ms);
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

function formatMsgTime(ms: number): string {
  const d = new Date(ms);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function getMsgSources(msg: ConversationMessageResp): string[] {
  const meta = msg.metadata as Record<string, unknown> | null;
  if (!meta) return [];
  const sources = meta.sources;
  return Array.isArray(sources) ? (sources as string[]) : [];
}

function getTurnSources(turn: MessageTurn): string[] {
  const all: string[] = [];
  for (const msg of turn.assistants) {
    all.push(...getMsgSources(msg));
  }
  return [...new Set(all)];
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
    }
  });
}

// ── 会话管理 ──

async function loadConversations() {
  const { data } = await convApi.pageConversation({ page_no: 1, page_size: 200 });
  conversations.value = data.data ?? [];
}

async function loadApps() {
  const { data } = await appApi.pageApp({ page_no: 1, page_size: 200, app_status: "published" });
  publishedApps.value = data.data ?? [];
}

async function selectConversation(conv: ConversationResp) {
  currentConversation.value = conv;
  // 同步应用
  const app = publishedApps.value.find((a) => a.id === conv.app_id);
  if (app) selectedApp.value = app;
  // 加载消息
  const { data } = await convApi.listMessages(conv.id);
  messages.value = data.data ?? [];
  scrollToBottom();
}

async function createNewChat() {
  if (!selectedApp.value) {
    message.warning("请先选择一个应用");
    return;
  }
  const { data } = await convApi.createConversation({ app_id: selectedApp.value.id });
  const conv = data.data;
  conversations.value.unshift(conv);
  currentConversation.value = conv;
  messages.value = [];
}

async function deleteConv(conv: ConversationResp) {
  try {
    await convApi.deleteConversation(conv.id);
    conversations.value = conversations.value.filter((c) => c.id !== conv.id);
    // 删的就是当前会话，清掉主区状态
    if (currentConversation.value?.id === conv.id) {
      currentConversation.value = null;
      messages.value = [];
    }
    message.success("会话已删除");
  } catch (err) {
    message.error("删除失败：" + (err instanceof Error ? err.message : String(err)));
  }
}

async function selectApp(app: AppResp) {
  selectedApp.value = app;
  showAppPicker.value = false;
  pickerType.value = null;

  // 查找该 app 最近的会话
  const existing = conversations.value.find((c) => c.app_id === app.id);
  if (existing) {
    await selectConversation(existing);
  } else {
    await createNewChat();
  }
}

function togglePicker() {
  showAppPicker.value = !showAppPicker.value;
  pickerType.value = null;
}

function closePicker() {
  showAppPicker.value = false;
  pickerType.value = null;
}

// ── 消息发送 ──

function onEnter(e: KeyboardEvent) {
  if (e.shiftKey) return;
  e.preventDefault();
  sendMessage();
}

function sendMessage() {
  const text = inputText.value.trim();
  if (!text || isStreaming.value || !currentConversation.value) return;

  // 本地追加用户消息
  messages.value.push({
    id: "",
    conversation_id: currentConversation.value.id,
    role: "user",
    content: text,
    create_time: Date.now(),
  });
  inputText.value = "";
  scrollToBottom();

  // 流式请求
  isStreaming.value = true;
  streamingContent.value = "";
  streamingToolCalls.value = [];
  streamMeta.model = "";
  streamMeta.sources = [];
  streamMeta.usage = null;
  streamMeta.latency_ms = null;

  streamAbort.value = convApi.sendMessageStream(
    currentConversation.value.id,
    { content: text },
    {
      onEvent(evt: SSEEvent) {
        switch (evt.event) {
          case "metadata":
            streamMeta.model = (evt.data.model as string) || "";
            if (evt.data.degraded) {
              message.warning(
                "历史已降级恢复：消息保留，但 agent 的待办、虚拟工作文件、工具中间态丢失",
                6,
              );
            }
            break;
          case "token":
            streamingContent.value += (evt.data.content as string) || "";
            scrollToBottom();
            break;
          case "tool_call_start":
            streamingToolCalls.value.push({
              tool_call_id: (evt.data.tool_call_id as string) || "",
              name: (evt.data.name as string) || "",
              status: "running",
              arguments: evt.data.arguments as Record<string, unknown> | undefined,
            });
            scrollToBottom();
            break;
          case "tool_call_end": {
            const id = evt.data.tool_call_id as string;
            const tc = streamingToolCalls.value.find((t) => t.tool_call_id === id);
            if (tc) {
              tc.status = (evt.data.status as string) === "error" ? "error" : "success";
              tc.result = (evt.data.result as string) || "";
            }
            break;
          }
          case "message_complete":
            streamMeta.usage = (evt.data.usage as Record<string, unknown>) ?? null;
            streamMeta.sources = (evt.data.sources as string[]) ?? [];
            break;
          case "done":
            streamMeta.latency_ms = (evt.data.latency_ms as number) ?? null;
            break;
          case "error":
            message.error((evt.data.message as string) || "执行出错");
            break;
        }
      },
      onDone() {
        isStreaming.value = false;
        streamingContent.value = "";
        streamingToolCalls.value = [];

        // 从后端重新加载完整消息列表（包含工具调用记录）
        if (currentConversation.value) {
          convApi.listMessages(currentConversation.value.id).then(({ data }) => {
            messages.value = data.data ?? [];
            scrollToBottom();
          });
        }
        loadConversations();
      },
      onError(err: Error) {
        message.error(err.message || "请求失败");
        isStreaming.value = false;
      },
    },
  );
}

function stopStream() {
  streamAbort.value?.abort();
  streamAbort.value = null;
  isStreaming.value = false;
}

// ── v-click-outside 指令 ──
const vClickOutside = {
  mounted(el: HTMLElement, binding: { value: () => void }) {
    (el as HTMLElement & { _clickOutside: (e: Event) => void })._clickOutside = (e: Event) => {
      if (!el.contains(e.target as Node)) binding.value();
    };
    document.addEventListener("click", (el as HTMLElement & { _clickOutside: (e: Event) => void })._clickOutside);
  },
  unmounted(el: HTMLElement) {
    document.removeEventListener("click", (el as HTMLElement & { _clickOutside: (e: Event) => void })._clickOutside);
  },
};

// ── 初始化 ──

onMounted(async () => {
  await Promise.all([loadApps(), loadConversations()]);
  // 选中第一个会话
  if (conversations.value.length) {
    await selectConversation(conversations.value[0]);
  } else if (publishedApps.value.length) {
    selectedApp.value = publishedApps.value[0];
  }
});
</script>

<style scoped>
.assistant-page {
  display: flex;
  height: 100%;
  margin: -24px;
  overflow: hidden;
}

/* ── 会话侧栏 ── */
.conv-sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(248, 250, 252, 0.5);
}

.conv-sidebar-header {
  padding: 12px;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.conv-item {
  position: relative;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  margin-bottom: 4px;
  border: 1px solid rgba(226, 232, 240, 0.7);
}

.conv-item:hover {
  background: rgba(226, 232, 240, 0.5);
  border-color: rgba(203, 213, 225, 0.9);
}

.conv-item-delete {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px;
  font-size: 14px;
  color: #94a3b8;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}

.conv-item:hover .conv-item-delete {
  opacity: 1;
}

.conv-item-delete:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.08);
}

.conv-item--active {
  background: rgba(37, 99, 235, 0.06);
  border-color: rgba(37, 99, 235, 0.2);
}

.conv-item-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.conv-type-tag {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
}

.conv-type--llm { background: rgba(16, 185, 129, 0.1); color: #059669; }
.conv-type--rag { background: rgba(59, 130, 246, 0.1); color: #2563eb; }
.conv-type--agent { background: rgba(139, 92, 246, 0.1); color: #7c3aed; }
.conv-type--nl2sql { background: rgba(6, 182, 212, 0.1); color: #0891b2; }
.conv-type--agent_flow { background: rgba(245, 158, 11, 0.1); color: #d97706; }

.conv-app-name {
  font-size: 11px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.conv-time {
  font-size: 10px;
  color: #94a3b8;
  flex-shrink: 0;
}

.conv-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-preview {
  font-size: 11px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.conv-empty {
  margin-top: 40px;
}

/* ── 对话主区 ── */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* 顶部栏 */
.chat-topbar {
  height: 48px;
  padding: 0 20px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.chat-app-selector {
  position: relative;
}

.app-picker-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 8px;
}

.app-picker-name {
  font-weight: 600;
  font-size: 13px;
}

.app-picker-arrow {
  font-size: 10px;
  color: #94a3b8;
}

.app-picker-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  width: 280px;
  background: #fff;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.1);
  z-index: 50;
  overflow: hidden;
}

.picker-section-title {
  padding: 8px 16px;
  font-size: 11px;
  color: #94a3b8;
  font-weight: 600;
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
}

.picker-section-back {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}

.picker-section-back:hover {
  color: #475569;
}

.picker-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.1s;
}

.picker-option:hover {
  background: rgba(248, 250, 252, 0.8);
}

.picker-option--active {
  background: rgba(37, 99, 235, 0.04);
}

.picker-option-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.picker-option-text {
  flex: 1;
  min-width: 0;
}

.picker-option-label {
  font-size: 13px;
  font-weight: 500;
  color: #0f172a;
}

.picker-option-desc {
  font-size: 11px;
  color: #94a3b8;
}

.picker-option-arrow {
  font-size: 10px;
  color: #cbd5e1;
}

.picker-check {
  color: #2563eb;
  font-size: 12px;
}

.chat-topbar-hint {
  font-size: 11px;
  color: #94a3b8;
}

/* 消息列表 */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.chat-empty-icon { font-size: 40px; opacity: 0.4; }
.chat-empty-title { font-size: 14px; font-weight: 600; color: #0f172a; margin: 0; }
.chat-empty-desc { font-size: 12px; color: #94a3b8; margin: 0; }

/* 消息气泡 */
.chat-msg {
  display: flex;
  gap: 10px;
  max-width: 80%;
}

.chat-msg--user {
  flex-direction: column;
  align-items: flex-end;
  align-self: flex-end;
}

.chat-msg--assistant {
  align-self: flex-start;
}

.chat-avatar {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.2), rgba(139, 92, 246, 0.2));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: #475569;
  flex-shrink: 0;
  margin-top: 2px;
}

.chat-bubble-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.chat-bubble {
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.7;
  word-break: break-word;
}

.chat-bubble--user {
  background: rgba(37, 99, 235, 0.1);
  border: 1px solid rgba(37, 99, 235, 0.15);
  border-radius: 14px 14px 4px 14px;
  color: #0f172a;
}

.chat-bubble--ai {
  background: #fff;
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-radius: 14px 14px 14px 4px;
  color: #334155;
}

/* 工具调用 — 紧凑行 + 点击展开 */
.chat-tool-inline {
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
  padding-bottom: 8px;
  margin-bottom: 8px;
}

.chat-tool-inline:last-of-type {
  border-bottom: none;
  padding-bottom: 0;
  margin-bottom: 4px;
}

.chat-tool-row {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 2px 0;
  user-select: none;
}

.chat-tool-row:hover {
  opacity: 0.8;
}

.chat-tool-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.chat-tool-name {
  font-size: 12px;
  font-weight: 600;
  color: #b45309;
}

.chat-tool-done {
  font-size: 10px;
  color: #15803d;
  font-weight: 600;
  margin-left: 2px;
}

.chat-tool-error {
  font-size: 10px;
  color: #b91c1c;
  font-weight: 600;
  margin-left: 2px;
}

.chat-tool-chevron {
  font-size: 9px;
  color: #94a3b8;
  transition: transform 0.15s;
  margin-left: auto;
}

.chat-tool-chevron--open {
  transform: rotate(90deg);
}

.chat-tool-detail {
  margin-top: 6px;
  padding-left: 20px;
}

.chat-tool-args {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: #475569;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(248, 250, 252, 0.8);
  border-radius: 6px;
  padding: 6px 10px;
}

.chat-tool-result {
  margin-top: 4px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(16, 185, 129, 0.06);
  font-size: 11px;
  color: #334155;
  line-height: 1.5;
  word-break: break-word;
}

.chat-msg-time {
  font-size: 10px;
  color: #94a3b8;
}

.chat-msg-time--right {
  text-align: right;
}

.chat-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.chat-source-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(37, 99, 235, 0.06);
  border: 1px solid rgba(37, 99, 235, 0.1);
  font-size: 10px;
  color: #2563eb;
}

/* 正在思考动画 */
.chat-thinking {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
}

.chat-thinking .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.chat-thinking .dot:nth-child(2) { animation-delay: 0.2s; }
.chat-thinking .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* Markdown 渲染 */
.chat-bubble--ai :deep(.msg-content p) { margin: 0 0 8px; }
.chat-bubble--ai :deep(.msg-content p:last-child) { margin-bottom: 0; }
.chat-bubble--ai :deep(.msg-content h1),
.chat-bubble--ai :deep(.msg-content h2),
.chat-bubble--ai :deep(.msg-content h3) { margin: 12px 0 6px; font-size: 14px; font-weight: 700; color: #1e293b; }
.chat-bubble--ai :deep(.msg-content ul),
.chat-bubble--ai :deep(.msg-content ol) { margin: 4px 0 8px; padding-left: 20px; }
.chat-bubble--ai :deep(.msg-content code) { padding: 1px 5px; border-radius: 4px; background: rgba(15, 23, 42, 0.06); font-size: 12px; font-family: "SF Mono", "Fira Code", "Consolas", monospace; }
.chat-bubble--ai :deep(.msg-content pre) { margin: 8px 0; padding: 12px; border-radius: 10px; background: #0f172a; color: #e2e8f0; font-size: 12px; line-height: 1.6; overflow-x: auto; }
.chat-bubble--ai :deep(.msg-content pre code) { padding: 0; background: transparent; color: inherit; }
.chat-bubble--ai :deep(.msg-content table) { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }
.chat-bubble--ai :deep(.msg-content th) { text-align: left; padding: 6px 10px; border-bottom: 1px solid rgba(226, 232, 240, 0.8); font-weight: 600; color: #0f172a; }
.chat-bubble--ai :deep(.msg-content td) { padding: 5px 10px; border-bottom: 1px solid rgba(226, 232, 240, 0.5); color: #475569; }
.chat-bubble--ai :deep(.msg-content tr:hover td) { background: rgba(248, 250, 252, 0.8); }

/* 输入区 */
.chat-input-area {
  flex-shrink: 0;
  padding: 8px 24px 16px;
}

.chat-composer {
  max-width: 720px;
  margin: 0 auto;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.chat-textarea {
  border: none !important;
  box-shadow: none !important;
  resize: none;
  padding: 14px 16px 6px;
  font-size: 14px;
  line-height: 1.6;
}

.chat-textarea:focus {
  box-shadow: none !important;
}

.chat-composer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px 10px;
}

.chat-composer-spacer {
  flex: 1;
}

.chat-meta-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(139, 92, 246, 0.06);
  color: #7c3aed;
  font-size: 10px;
  font-weight: 600;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-input-hint {
  text-align: center;
  margin-top: 8px;
  font-size: 10px;
  color: #cbd5e1;
}
</style>
