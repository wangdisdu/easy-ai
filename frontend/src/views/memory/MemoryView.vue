<template>
  <section class="memory-page">
    <!-- 顶部 -->
    <div class="memory-head">
      <div class="memory-head-text">
        <h2 class="memory-title">长期记忆</h2>
        <p class="memory-sub">{{ currentScopeHint }}</p>
      </div>
      <div class="memory-head-actions">
        <a-button :disabled="!hasScope" @click="openAuditDrawer">
          <template #icon><ClockCircleOutlined /></template>
          审计
        </a-button>
        <a-popconfirm
          v-if="activeTab === 'user'"
          title="清空我的全部长期记忆？"
          description="不可撤销；agent 的 audit 痕迹保留。"
          ok-text="清空"
          cancel-text="取消"
          ok-type="danger"
          @confirm="onPurgeSelf"
        >
          <a-button danger :disabled="!list.length">
            <template #icon><DeleteOutlined /></template>
            清空全部
          </a-button>
        </a-popconfirm>
        <a-button type="primary" :disabled="!canAdd" @click="openAdd">
          <template #icon><PlusOutlined /></template>
          添加记忆
        </a-button>
      </div>
    </div>

    <!-- tab -->
    <div class="memory-tabs">
      <a-tabs v-model:activeKey="activeTab" size="small" @change="onTabChange">
        <a-tab-pane key="user">
          <template #tab>
            <span class="tab-label">
              <UserOutlined />
              我的记忆
              <span v-if="activeTab === 'user'" class="tab-count">{{ list.length }}</span>
            </span>
          </template>
        </a-tab-pane>
        <a-tab-pane key="app">
          <template #tab>
            <span class="tab-label">
              <AppstoreOutlined />
              应用记忆
              <span v-if="activeTab === 'app' && hasScope" class="tab-count">{{ list.length }}</span>
            </span>
          </template>
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- 应用记忆：选择面板 / 上下文 banner -->
    <template v-if="activeTab === 'app'">
      <!-- 未选中时：展示应用选择面板 -->
      <div v-if="!selectedAppId" class="app-picker-panel">
        <div v-if="appsLoading" class="app-picker-loading"><a-spin /></div>
        <div v-else-if="!myApps.length" class="memory-empty-state">
          <BulbOutlined class="empty-icon" />
          <div class="memory-empty-title">还没有可管理的应用记忆</div>
          <div class="memory-empty-desc">只有你创建的应用才会出现在这里。</div>
          <a-button type="primary" @click="router.push('/app/create')">去创建应用</a-button>
        </div>
        <template v-else>
          <div class="app-picker-prompt">
            <div class="app-picker-prompt-icon-wrap">
              <AppstoreOutlined />
            </div>
            <div>
              <div class="app-picker-prompt-title">选择一个应用来管理其记忆</div>
              <div class="app-picker-prompt-sub">
                应用记忆与智能体强绑定 — 选中应用后即可查看、编辑该应用所有用户对话时都会读到的共享记忆
              </div>
            </div>
          </div>
          <div class="app-picker-grid">
            <div
              v-for="app in myApps"
              :key="app.id"
              class="app-picker-card"
              @click="selectedAppId = app.id"
            >
              <div class="app-picker-avatar" :style="{ background: appAvatarColor(app.id) }">
                {{ app.name[0]?.toUpperCase() }}
              </div>
              <div class="app-picker-card-body">
                <div class="app-picker-card-name">{{ app.name }}</div>
                <span class="app-picker-card-type">{{ appTypeLabel(app.app_type) }}</span>
                <div v-if="app.description" class="app-picker-card-desc">{{ app.description }}</div>
              </div>
              <div class="app-picker-card-arrow">›</div>
            </div>
          </div>
        </template>
      </div>

      <!-- 已选中时：展示应用上下文 banner -->
      <div v-else-if="currentApp" class="memory-app-banner">
        <div class="app-banner-avatar" :style="{ background: appAvatarColor(currentApp.id) }">
          {{ currentApp.name[0]?.toUpperCase() }}
        </div>
        <div class="app-banner-body">
          <div class="app-banner-nameline">
            <span class="app-banner-name">{{ currentApp.name }}</span>
            <span class="app-banner-type">{{ appTypeLabel(currentApp.app_type) }}</span>
          </div>
          <div v-if="currentApp.description" class="app-banner-desc">{{ currentApp.description }}</div>
          <div class="app-banner-hint">
            <span class="app-banner-hint-dot" />
            以下记忆与此应用强绑定 — 所有访问该应用的用户在每次对话时都会自动读取这些记忆
          </div>
        </div>
        <a-button size="small" class="app-banner-switch" @click="switchApp">切换应用</a-button>
      </div>
    </template>

    <!-- 统计条 -->
    <div v-if="hasScope && list.length" class="memory-stats">
      <div class="stat-card">
        <div class="stat-num">{{ list.length }}</div>
        <div class="stat-label">总记录</div>
      </div>
      <div class="stat-card stat-card--user">
        <div class="stat-num">{{ counts.user_explicit }}</div>
        <div class="stat-label">用户写入</div>
      </div>
      <div class="stat-card stat-card--agent">
        <div class="stat-num">{{ counts.agent_learned }}</div>
        <div class="stat-label">agent 自学</div>
      </div>
      <div class="stat-card stat-card--admin">
        <div class="stat-num">{{ counts.admin_set }}</div>
        <div class="stat-label">管理员</div>
      </div>
    </div>

    <!-- 筛选行 -->
    <div v-if="hasScope" class="memory-filterbar">
      <div class="filter-chips">
        <button
          v-for="opt in sourceFilterOptions"
          :key="opt.value"
          type="button"
          class="filter-chip"
          :class="{ 'filter-chip--active': sourceFilter === opt.value }"
          @click="sourceFilter = opt.value"
        >
          {{ opt.label }}
          <span v-if="opt.value !== 'all'" class="filter-chip-count">
            {{ counts[opt.value as keyof typeof counts] || 0 }}
          </span>
        </button>
      </div>
      <a-input-search
        v-model:value="searchText"
        class="memory-search"
        placeholder="按 key 或内容筛选"
        allow-clear
      />
      <a-select
        v-model:value="sortBy"
        :options="sortOptions"
        class="memory-sort"
        size="middle"
      />
      <a-button :loading="loading" @click="loadList()">
        <template #icon><ReloadOutlined /></template>
      </a-button>
    </div>

    <!-- 列表 -->
    <a-spin v-if="hasScope" :spinning="loading">
      <div class="memory-list">
        <!-- 卡片列表 -->
        <div
          v-for="item in displayList"
          :key="item.id"
          :class="['memory-card', `memory-card--${item.source}`]"
        >
          <div class="memory-card-main">
            <div class="memory-value">{{ item.memory_value }}</div>
            <div class="memory-card-meta">
              <span class="memory-key" :title="item.memory_key">
                <span class="meta-icon">#</span>{{ item.memory_key }}
              </span>
              <span :class="['source-tag', `source-tag--${item.source}`]">
                {{ sourceLabel(item.source) }}
              </span>
              <span class="memory-time" :title="formatMs(item.update_time)">
                {{ relativeTime(item.update_time) }}
              </span>
            </div>
          </div>
          <div class="memory-card-actions">
            <a-tooltip title="修改">
              <a-button type="text" size="small" @click="openEdit(item)">
                <template #icon><EditOutlined /></template>
              </a-button>
            </a-tooltip>
            <a-popconfirm
              title="确定删除这条记忆？"
              ok-type="danger"
              @confirm="onDelete(item)"
            >
              <a-tooltip title="删除">
                <a-button type="text" size="small" danger>
                  <template #icon><DeleteOutlined /></template>
                </a-button>
              </a-tooltip>
            </a-popconfirm>
          </div>
        </div>

        <!-- 空态：当前 scope 内没有结果 -->
        <div
          v-if="!displayList.length && !loading"
          class="memory-empty-state"
        >
          <BulbOutlined class="empty-icon" />
          <div class="memory-empty-title">
            {{ list.length ? "没有匹配的记忆" : "暂无记忆" }}
          </div>
          <div class="memory-empty-desc">
            {{
              list.length
                ? "换个关键词或者切换筛选试试。"
                : activeTab === 'user'
                  ? '可以让 agent 帮你记下偏好（如说"记住我喜欢用中文"），或在这里手动添加。'
                  : '这个应用还没有任何共享知识，可以手动添加。'
            }}
          </div>
          <a-button v-if="!list.length && canAdd" type="primary" @click="openAdd">
            添加第一条
          </a-button>
          <a-button v-else-if="list.length" @click="clearFilters">清除筛选</a-button>
        </div>
      </div>
    </a-spin>

    <!-- 编辑 / 新增 -->
    <a-modal
      v-model:open="editorOpen"
      :title="editing?.id ? '修改记忆' : '添加记忆'"
      :ok-text="editing?.id ? '保存' : '添加'"
      cancel-text="取消"
      :confirm-loading="saving"
      :width="520"
      @ok="onSave"
    >
      <a-form layout="vertical" class="memory-form">
        <a-form-item required>
          <template #label>
            key（唯一标识）
            <span class="form-hint">建议 dot 命名空间，如 language.preference</span>
          </template>
          <a-input
            v-model:value="form.memory_key"
            :disabled="!!editing?.id"
            placeholder="例：language.preference / profile.email"
            maxlength="255"
            show-count
            allow-clear
          />
          <div v-if="editing?.id" class="form-hint form-hint--note">
            key 不可修改；如需重命名请删除后重新添加。
          </div>
        </a-form-item>
        <a-form-item required>
          <template #label>
            value（内容）
            <span class="form-hint">纯文本短句，会被注入到 agent 的 system prompt</span>
          </template>
          <a-textarea
            v-model:value="form.memory_value"
            :auto-size="{ minRows: 4, maxRows: 12 }"
            placeholder="写成可执行的偏好/事实，如：用户偏好中文回复"
            maxlength="300"
            show-count
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 审计 drawer -->
    <a-drawer
      v-model:open="auditDrawerOpen"
      :title="auditDrawerTitle"
      width="640"
      :destroy-on-close="false"
      @open="loadAudit"
    >
      <div v-if="auditLoading" class="audit-loading">
        <a-spin />
      </div>
      <div v-else-if="!auditList.length" class="memory-empty-state memory-empty-state--inline">
        <ClockCircleOutlined class="empty-icon" />
        <div class="memory-empty-title">暂无审计记录</div>
        <div class="memory-empty-desc">这个范围内还没有写入或修改记忆的事件。</div>
      </div>
      <div v-else class="audit-list">
        <div v-for="group in auditGroups" :key="group.label" class="audit-group">
          <div class="audit-group-label">{{ group.label }}</div>
          <div
            v-for="row in group.rows"
            :key="row.id"
            :class="['audit-row', `audit-row--${row.event_type}`]"
          >
            <div class="audit-row-head">
              <span :class="['audit-event', `audit-event--${row.event_type}`]">
                {{ eventLabel(row.event_type) }}
              </span>
              <span class="memory-key"><span class="meta-icon">#</span>{{ row.memory_key }}</span>
              <span class="memory-time" :title="formatMs(row.create_time)">
                {{ formatTime(row.create_time) }}
              </span>
            </div>
            <div v-if="row.memory_value_before" class="audit-val audit-val--before">
              <span class="audit-label">旧</span>
              <span class="audit-content">{{ row.memory_value_before }}</span>
            </div>
            <div v-if="row.memory_value_after" class="audit-val audit-val--after">
              <span class="audit-label">新</span>
              <span class="audit-content">{{ row.memory_value_after }}</span>
            </div>
            <div class="audit-meta">
              <span :class="['source-tag', 'source-tag--mini', `source-tag--${row.source}`]">
                {{ sourceLabel(row.source) }}
              </span>
              <span v-if="row.actor_user_id">操作人 user#{{ row.actor_user_id }}</span>
              <span v-if="row.conversation_id">会话 #{{ row.conversation_id }}</span>
            </div>
          </div>
        </div>
      </div>
    </a-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import {
  AppstoreOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import * as memoryApi from "@/api/memory";
import * as appApi from "@/api/app";
import type { AppResp } from "@/api/types";
import type { MemoryItem, MemoryAuditItem, MemoryScope } from "@/api/memory";
import { useAuthStore } from "@/stores/auth";
import { formatMs } from "@/utils/time";

const auth = useAuthStore();
const router = useRouter();

const activeTab = ref<MemoryScope>("user");
const loading = ref(false);
const list = ref<MemoryItem[]>([]);
const searchText = ref("");
const sourceFilter = ref<"all" | "user_explicit" | "agent_learned" | "admin_set">("all");
const sortBy = ref<"update_time_desc" | "create_time_desc" | "memory_key_asc">(
  "update_time_desc",
);

const sourceFilterOptions = [
  { label: "全部", value: "all" as const },
  { label: "用户写入", value: "user_explicit" as const },
  { label: "agent 自学", value: "agent_learned" as const },
  { label: "管理员", value: "admin_set" as const },
];

const sortOptions = [
  { label: "最近更新优先", value: "update_time_desc" },
  { label: "最近添加优先", value: "create_time_desc" },
  { label: "按 key 字母", value: "memory_key_asc" },
];

// app 选择器：仅展示当前用户创建的 app
const myApps = ref<AppResp[]>([]);
const selectedAppId = ref<string | null>(null);
const appsLoading = ref(false);

function appTypeLabel(type: string): string {
  switch (type) {
    case "deep_agent": return "Deep Agent";
    case "flowise": return "Flowise Agent";
    case "simple_chat": return "简单对话";
    default: return type || "应用";
  }
}

function appAvatarColor(id: string): string {
  const palette = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#06b6d4"];
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return palette[hash % palette.length];
}

function switchApp() {
  selectedAppId.value = null;
  list.value = [];
}

const canAdd = computed(() => {
  if (activeTab.value === "user") return !!auth.user;
  return !!selectedAppId.value;
});
const hasScope = computed(() => !!currentScopeId());
const currentApp = computed(
  () => myApps.value.find((item) => item.id === selectedAppId.value) ?? null,
);
const currentScopeHint = computed(() => {
  if (activeTab.value === "user") {
    const name = auth.user?.name || auth.user?.account || "你";
    return `${name} 的跨会话偏好与事实，会自动注入到 agent 的 system prompt`;
  }
  if (selectedAppId.value) return "应用维度的共享记忆，与智能体强绑定";
  return "选择一个应用，查看并管理其与智能体绑定的专属记忆";
});

const counts = computed(() => {
  const c = { user_explicit: 0, agent_learned: 0, admin_set: 0 };
  for (const item of list.value) {
    if (item.source === "user_explicit") c.user_explicit++;
    else if (item.source === "agent_learned") c.agent_learned++;
    else if (item.source === "admin_set") c.admin_set++;
  }
  return c;
});

const displayList = computed(() => {
  let arr = [...list.value];
  if (sourceFilter.value !== "all") {
    arr = arr.filter((item) => item.source === sourceFilter.value);
  }
  const keyword = searchText.value.trim().toLowerCase();
  if (keyword) {
    arr = arr.filter((item) => {
      return (
        item.memory_key.toLowerCase().includes(keyword)
        || item.memory_value.toLowerCase().includes(keyword)
      );
    });
  }
  arr.sort((a, b) => {
    switch (sortBy.value) {
      case "create_time_desc":
        return b.create_time - a.create_time;
      case "memory_key_asc":
        return a.memory_key.localeCompare(b.memory_key);
      default:
        return b.update_time - a.update_time;
    }
  });
  return arr;
});

const editorOpen = ref(false);
const saving = ref(false);
const editing = ref<MemoryItem | null>(null);
const form = reactive({ memory_key: "", memory_value: "" });

const auditDrawerOpen = ref(false);
const auditLoading = ref(false);
const auditList = ref<MemoryAuditItem[]>([]);
const auditDrawerTitle = computed(() => {
  if (activeTab.value === "user") return "我的记忆 · 变更审计";
  return `${currentApp.value?.name ?? "应用"} · 变更审计`;
});

interface AuditGroup {
  label: string;
  rows: MemoryAuditItem[];
}

const auditGroups = computed<AuditGroup[]>(() => {
  if (!auditList.value.length) return [];
  const groups: Record<string, MemoryAuditItem[]> = {};
  const order: string[] = [];
  for (const row of auditList.value) {
    const label = dayLabel(row.create_time);
    if (!groups[label]) {
      groups[label] = [];
      order.push(label);
    }
    groups[label].push(row);
  }
  return order.map((label) => ({ label, rows: groups[label] }));
});

function sourceLabel(source: string): string {
  switch (source) {
    case "agent_learned":
      return "agent 自学";
    case "user_explicit":
      return "用户写入";
    case "admin_set":
      return "管理员";
    default:
      return source;
  }
}

function eventLabel(event: string): string {
  switch (event) {
    case "remembered":
      return "新建";
    case "updated":
      return "更新";
    case "forgotten":
      return "删除";
    case "admin_purged":
      return "批量清空";
    default:
      return event;
  }
}

function relativeTime(ms: number): string {
  const diff = Date.now() - ms;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`;
  return formatMs(ms);
}

function formatTime(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

function dayLabel(ms: number): string {
  const d = new Date(ms);
  const today = new Date();
  const same = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
  if (same(d, today)) return "今天";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (same(d, yesterday)) return "昨天";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function currentScopeId(): string | null {
  if (activeTab.value === "user") return auth.user?.id ?? null;
  return selectedAppId.value;
}

function clearFilters() {
  searchText.value = "";
  sourceFilter.value = "all";
}

async function loadMyApps() {
  appsLoading.value = true;
  try {
    const { data } = await appApi.pageApp({ page_no: 1, page_size: 200 });
    const all = data.data ?? [];
    const me = auth.user?.id ?? "";
    myApps.value = all.filter(
      (a: AppResp & { create_user?: string | number | null }) =>
        String(a.create_user ?? "") === me,
    );
    if (
      activeTab.value === "app"
      && myApps.value.length
      && !myApps.value.some((item) => item.id === selectedAppId.value)
    ) {
      selectedAppId.value = null;
    }
  } catch {
    myApps.value = [];
  } finally {
    appsLoading.value = false;
  }
}

async function loadList(resetSearch = false) {
  if (resetSearch) {
    searchText.value = "";
    sourceFilter.value = "all";
  }
  const sid = currentScopeId();
  if (!sid) {
    list.value = [];
    return;
  }
  loading.value = true;
  try {
    const { data } = await memoryApi.listMemories({
      scope: activeTab.value,
      scope_id: sid,
    });
    list.value = data.data ?? [];
  } finally {
    loading.value = false;
  }
}

async function loadAudit() {
  const sid = currentScopeId();
  if (!sid) {
    auditList.value = [];
    return;
  }
  auditLoading.value = true;
  try {
    const { data } = await memoryApi.listMemoryAudit({
      scope: activeTab.value,
      scope_id: sid,
    });
    auditList.value = data.data ?? [];
  } finally {
    auditLoading.value = false;
  }
}

function onTabChange() {
  list.value = [];
  auditList.value = [];
  searchText.value = "";
  sourceFilter.value = "all";
  loadList();
}

function openAuditDrawer() {
  if (!hasScope.value) {
    message.warning(activeTab.value === "app" ? "请先选择应用" : "当前范围不可用");
    return;
  }
  auditDrawerOpen.value = true;
  void loadAudit();
}

function openAdd() {
  editing.value = null;
  form.memory_key = "";
  form.memory_value = "";
  editorOpen.value = true;
}

function openEdit(item: MemoryItem) {
  editing.value = item;
  form.memory_key = item.memory_key;
  form.memory_value = item.memory_value;
  editorOpen.value = true;
}

async function onSave() {
  const sid = currentScopeId();
  if (!sid) return;
  if (!form.memory_key.trim() || !form.memory_value.trim()) {
    message.warning("key 和 value 都必填");
    return;
  }
  saving.value = true;
  try {
    await memoryApi.upsertMemory({
      scope: activeTab.value,
      scope_id: sid,
      memory_key: form.memory_key.trim(),
      memory_value: form.memory_value.trim(),
      source: "user_explicit",
    });
    editorOpen.value = false;
    message.success(editing.value?.id ? "已更新" : "已添加");
    loadList();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    message.error("保存失败：" + msg);
  } finally {
    saving.value = false;
  }
}

async function onDelete(item: MemoryItem) {
  try {
    await memoryApi.deleteMemory({
      scope: item.scope as MemoryScope,
      scope_id: item.scope_id,
      memory_key: item.memory_key,
    });
    message.success("已删除");
    loadList();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    message.error("删除失败：" + msg);
  }
}

async function onPurgeSelf() {
  try {
    const { data } = await memoryApi.purgeSelfMemories();
    message.success(`已清空 ${data.data ?? 0} 条记忆`);
    loadList();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    message.error("清空失败：" + msg);
  }
}

watch(selectedAppId, () => {
  if (activeTab.value === "app") loadList();
});

watch([activeTab, selectedAppId], () => {
  if (auditDrawerOpen.value) void loadAudit();
});

onMounted(async () => {
  await loadMyApps();
  await loadList();
});
</script>

<style scoped>
.memory-page {
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.1), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.86) 100%);
  box-shadow:
    0 24px 48px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
  padding: 24px;
}

/* ── 头部 ── */
.memory-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.memory-head-text {
  flex: 1;
  min-width: 0;
}

.memory-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.memory-sub {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.memory-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── tabs + app 选择器 ── */
.memory-tabs {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.memory-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 0;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tab-count {
  background: rgba(15, 23, 42, 0.06);
  color: #475569;
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  font-weight: 500;
}

/* ── App 选择面板 ── */
.app-picker-panel {
  margin-top: 20px;
}

.app-picker-loading {
  text-align: center;
  padding: 40px 0;
}

.app-picker-prompt {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.06), rgba(139, 92, 246, 0.04));
  border: 1px solid rgba(147, 197, 253, 0.4);
  border-radius: 14px;
}

.app-picker-prompt-icon-wrap {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.app-picker-prompt-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.app-picker-prompt-sub {
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
}

.app-picker-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.app-picker-card {
  border: 1.5px solid rgba(226, 232, 240, 0.9);
  border-radius: 14px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  transition:
    border-color 0.15s ease,
    transform 0.15s ease,
    box-shadow 0.15s ease,
    background 0.15s ease;
  position: relative;
}

.app-picker-card:hover {
  border-color: #3b82f6;
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.14);
  background: rgba(255, 255, 255, 0.95);
}

.app-picker-avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.14);
}

.app-picker-card-body {
  flex: 1;
  min-width: 0;
}

.app-picker-card-name {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-picker-card-type {
  display: inline-block;
  font-size: 11px;
  color: #64748b;
  background: rgba(100, 116, 139, 0.08);
  border-radius: 999px;
  padding: 1px 8px;
  margin-bottom: 6px;
}

.app-picker-card-desc {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.app-picker-card-arrow {
  font-size: 20px;
  color: #cbd5e1;
  align-self: center;
  flex-shrink: 0;
  transition: color 0.15s, transform 0.15s;
  line-height: 1;
}

.app-picker-card:hover .app-picker-card-arrow {
  color: #3b82f6;
  transform: translateX(2px);
}

/* ── App 上下文 Banner ── */
.memory-app-banner {
  margin-top: 16px;
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.07) 0%, rgba(139, 92, 246, 0.05) 100%);
  border: 1.5px solid rgba(147, 197, 253, 0.5);
  border-radius: 16px;
  padding: 18px 20px;
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.app-banner-avatar {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 22px;
  font-weight: 700;
  flex-shrink: 0;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14);
}

.app-banner-body {
  flex: 1;
  min-width: 0;
}

.app-banner-nameline {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.app-banner-name {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.app-banner-type {
  font-size: 11px;
  font-weight: 500;
  color: #4f46e5;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 999px;
  padding: 2px 10px;
}

.app-banner-desc {
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
  margin-bottom: 8px;
}

.app-banner-hint {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: #64748b;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-radius: 8px;
  padding: 5px 10px;
}

.app-banner-hint-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #3b82f6;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.app-banner-switch {
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 2px;
}

/* ── 统计条 ── */
.memory-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.stat-card {
  border: 1px solid rgba(226, 232, 240, 0.85);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.65);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  transition: transform 0.15s ease;
}

.stat-card:hover {
  transform: translateY(-1px);
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.stat-label {
  color: #64748b;
  font-size: 12px;
}

.stat-card--user {
  background: linear-gradient(135deg, rgba(219, 234, 254, 0.6), rgba(255, 255, 255, 0.7));
  border-color: rgba(147, 197, 253, 0.5);
}
.stat-card--user .stat-num {
  color: #1d4ed8;
}

.stat-card--agent {
  background: linear-gradient(135deg, rgba(237, 233, 254, 0.6), rgba(255, 255, 255, 0.7));
  border-color: rgba(196, 181, 253, 0.5);
}
.stat-card--agent .stat-num {
  color: #6d28d9;
}

.stat-card--admin {
  background: linear-gradient(135deg, rgba(209, 250, 229, 0.6), rgba(255, 255, 255, 0.7));
  border-color: rgba(110, 231, 183, 0.5);
}
.stat-card--admin .stat-num {
  color: #047857;
}

/* ── 筛选行 ── */
.memory-filterbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 14px;
  flex-wrap: wrap;
}

.filter-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-chip {
  appearance: none;
  border: 1px solid rgba(226, 232, 240, 0.95);
  background: rgba(255, 255, 255, 0.7);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  color: #475569;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.12s ease;
}

.filter-chip:hover {
  border-color: rgba(147, 197, 253, 0.7);
  color: #1d4ed8;
}

.filter-chip--active {
  background: #1f2937;
  color: #fff;
  border-color: #1f2937;
}

.filter-chip--active .filter-chip-count {
  color: rgba(255, 255, 255, 0.7);
}

.filter-chip-count {
  font-size: 10px;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.memory-search {
  flex: 1;
  min-width: 200px;
  max-width: 360px;
}

.memory-sort {
  width: 160px;
}

/* ── 卡片 ── */
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.memory-card {
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.85);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  align-items: stretch;
  gap: 12px;
  position: relative;
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    transform 0.15s ease;
  overflow: hidden;
}

.memory-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: rgba(148, 163, 184, 0.4);
}

.memory-card--user_explicit::before {
  background: #3b82f6;
}

.memory-card--agent_learned::before {
  background: #8b5cf6;
}

.memory-card--admin_set::before {
  background: #10b981;
}

.memory-card:hover {
  border-color: rgba(147, 197, 253, 0.7);
  background: rgba(255, 255, 255, 0.95);
}

.memory-card-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-value {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.memory-key {
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 12px;
  color: #475569;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-icon {
  color: #94a3b8;
  font-weight: 600;
}

.memory-time {
  color: #94a3b8;
  margin-left: auto;
  font-size: 12px;
  flex-shrink: 0;
}

.memory-card-actions {
  display: flex;
  gap: 4px;
  align-items: flex-start;
  opacity: 0.4;
  transition: opacity 0.15s ease;
}

.memory-card:hover .memory-card-actions {
  opacity: 1;
}

/* ── 空态 ── */
.memory-empty-state {
  border: 1px dashed rgba(191, 219, 254, 0.9);
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.72);
  font-size: 13px;
  padding: 40px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.memory-empty-state--inline {
  border: none;
  background: transparent;
  padding: 32px 12px;
}

.empty-icon {
  font-size: 36px;
  color: #cbd5e1;
}

.memory-empty-title {
  color: #334155;
  font-size: 15px;
  font-weight: 600;
}

.memory-empty-desc {
  color: #64748b;
  line-height: 1.6;
  max-width: 420px;
  margin-bottom: 4px;
}

/* ── 编辑表单 ── */
.memory-form :deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: #1f2937;
  flex-direction: row;
  align-items: baseline;
  gap: 8px;
}

.form-hint {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 400;
}

.form-hint--note {
  margin-top: 4px;
  font-style: italic;
}

/* ── source tag ── */
.source-tag {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

.source-tag--mini {
  font-size: 10px;
  padding: 0 6px;
}

.source-tag--agent_learned {
  background: #ede9fe;
  color: #6d28d9;
}

.source-tag--user_explicit {
  background: #dbeafe;
  color: #1d4ed8;
}

.source-tag--admin_set {
  background: #d1fae5;
  color: #047857;
}

/* ── audit drawer ── */
.audit-loading {
  text-align: center;
  padding: 40px 0;
}

.audit-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.audit-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.audit-group-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
}

.audit-row {
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(248, 250, 252, 0.7);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-left: 2px solid rgba(148, 163, 184, 0.5);
}

.audit-row--remembered {
  border-left-color: #10b981;
}

.audit-row--updated {
  border-left-color: #3b82f6;
}

.audit-row--forgotten,
.audit-row--admin_purged {
  border-left-color: #ef4444;
}

.audit-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.audit-event {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.audit-event--remembered {
  background: #d1fae5;
  color: #047857;
}

.audit-event--updated {
  background: #dbeafe;
  color: #1d4ed8;
}

.audit-event--forgotten,
.audit-event--admin_purged {
  background: #fee2e2;
  color: #b91c1c;
}

.audit-val {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 4px 0;
  word-break: break-word;
}

.audit-label {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 18px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  margin-top: 1px;
}

.audit-val--before .audit-label {
  background: #fee2e2;
  color: #b91c1c;
}

.audit-val--after .audit-label {
  background: #d1fae5;
  color: #047857;
}

.audit-content {
  color: #334155;
  flex: 1;
  min-width: 0;
}

.audit-meta {
  display: flex;
  gap: 10px;
  color: #94a3b8;
  font-size: 11px;
  flex-wrap: wrap;
  margin-top: 2px;
  align-items: center;
}

@media (max-width: 768px) {
  .memory-head {
    flex-direction: column;
  }

  .memory-tabs {
    flex-direction: column;
    align-items: flex-start;
  }

  .memory-search,
  .memory-sort {
    width: 100%;
  }

  .memory-card-meta {
    width: 100%;
  }

  .memory-time {
    margin-left: 0;
  }

  .memory-card-actions {
    opacity: 1;
  }

  .app-picker-grid {
    grid-template-columns: 1fr;
  }

  .memory-app-banner {
    flex-wrap: wrap;
  }

  .app-banner-switch {
    width: 100%;
  }
}
</style>
