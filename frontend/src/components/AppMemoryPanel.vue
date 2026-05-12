<template>
  <section class="amp-panel">
    <div class="amp-head">
      <div class="amp-head-text">
        <h3 class="amp-title">长期记忆</h3>
        <p class="amp-sub">
          应用维度的共享记忆，所有访问该应用的用户在每次对话时都会自动读取。
        </p>
      </div>
      <div class="amp-head-actions">
        <a-button @click="openAuditDrawer">
          <template #icon><ClockCircleOutlined /></template>
          审计
        </a-button>
        <a-button type="primary" @click="openAdd">
          <template #icon><PlusOutlined /></template>
          添加记忆
        </a-button>
      </div>
    </div>

    <div v-if="list.length" class="amp-stats">
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

    <div class="amp-filterbar">
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
        class="amp-search"
        placeholder="按 key 或内容筛选"
        allow-clear
      />
      <a-select
        v-model:value="sortBy"
        :options="sortOptions"
        class="amp-sort"
        size="middle"
      />
      <a-button :loading="loading" @click="loadList()">
        <template #icon><ReloadOutlined /></template>
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <div class="amp-list">
        <div
          v-for="item in displayList"
          :key="item.id"
          :class="['amp-card', `amp-card--${item.source}`]"
        >
          <div class="amp-card-main">
            <div class="amp-value">{{ item.memory_value }}</div>
            <div class="amp-card-meta">
              <span class="amp-key" :title="item.memory_key">
                <span class="meta-icon">#</span>{{ item.memory_key }}
              </span>
              <span :class="['source-tag', `source-tag--${item.source}`]">
                {{ sourceLabel(item.source) }}
              </span>
              <span class="amp-time" :title="formatMs(item.update_time)">
                {{ relativeTime(item.update_time) }}
              </span>
            </div>
          </div>
          <div class="amp-card-actions">
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

        <div v-if="!displayList.length && !loading" class="amp-empty">
          <BulbOutlined class="empty-icon" />
          <div class="empty-title">
            {{ list.length ? "没有匹配的记忆" : "暂无记忆" }}
          </div>
          <div class="empty-desc">
            {{
              list.length
                ? "换个关键词或者切换筛选试试。"
                : "这个应用还没有任何共享记忆，可以手动添加，agent 在对话中也会自动写入。"
            }}
          </div>
          <a-button v-if="!list.length" type="primary" @click="openAdd">
            添加第一条
          </a-button>
          <a-button v-else @click="clearFilters">清除筛选</a-button>
        </div>
      </div>
    </a-spin>

    <a-modal
      v-model:open="editorOpen"
      :title="editing?.id ? '修改记忆' : '添加记忆'"
      :ok-text="editing?.id ? '保存' : '添加'"
      cancel-text="取消"
      :confirm-loading="saving"
      :width="520"
      @ok="onSave"
    >
      <a-form layout="vertical" class="amp-form">
        <a-form-item required>
          <template #label>
            key（唯一标识）
            <span class="form-hint">建议 dot 命名空间，如 brand.tone</span>
          </template>
          <a-input
            v-model:value="form.memory_key"
            :disabled="!!editing?.id"
            placeholder="例：brand.tone / faq.refund_policy"
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
            <span class="form-hint">纯文本，会被注入到 agent 的 system prompt</span>
          </template>
          <a-textarea
            v-model:value="form.memory_value"
            :auto-size="{ minRows: 4, maxRows: 12 }"
            placeholder="写成可执行的偏好/事实，如：回复语气友好简洁，避免营销话术"
            maxlength="300"
            show-count
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="auditDrawerOpen"
      :title="`${props.appName || '应用'} · 变更审计`"
      width="640"
      :destroy-on-close="false"
      @open="loadAudit"
    >
      <div v-if="auditLoading" class="audit-loading">
        <a-spin />
      </div>
      <div v-else-if="!auditList.length" class="amp-empty amp-empty--inline">
        <ClockCircleOutlined class="empty-icon" />
        <div class="empty-title">暂无审计记录</div>
        <div class="empty-desc">这个应用还没有写入或修改记忆的事件。</div>
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
              <span class="amp-key"><span class="meta-icon">#</span>{{ row.memory_key }}</span>
              <span class="amp-time" :title="formatMs(row.create_time)">
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
import { computed, reactive, ref, watch } from "vue";
import { message } from "ant-design-vue";
import {
  BulbOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from "@ant-design/icons-vue";
import * as memoryApi from "@/api/memory";
import type { MemoryAuditItem, MemoryItem } from "@/api/memory";
import { formatMs } from "@/utils/time";

const props = defineProps<{
  appId: string;
  appName?: string;
}>();

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
    arr = arr.filter(
      (item) =>
        item.memory_key.toLowerCase().includes(keyword) ||
        item.memory_value.toLowerCase().includes(keyword),
    );
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
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();
  if (same(d, today)) return "今天";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (same(d, yesterday)) return "昨天";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function clearFilters() {
  searchText.value = "";
  sourceFilter.value = "all";
}

async function loadList() {
  if (!props.appId) {
    list.value = [];
    return;
  }
  loading.value = true;
  try {
    const { data } = await memoryApi.listMemories({
      scope: "app",
      scope_id: props.appId,
    });
    list.value = data.data ?? [];
  } finally {
    loading.value = false;
  }
}

async function loadAudit() {
  if (!props.appId) {
    auditList.value = [];
    return;
  }
  auditLoading.value = true;
  try {
    const { data } = await memoryApi.listMemoryAudit({
      scope: "app",
      scope_id: props.appId,
    });
    auditList.value = data.data ?? [];
  } finally {
    auditLoading.value = false;
  }
}

function openAuditDrawer() {
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
  if (!form.memory_key.trim() || !form.memory_value.trim()) {
    message.warning("key 和 value 都必填");
    return;
  }
  saving.value = true;
  try {
    await memoryApi.upsertMemory({
      scope: "app",
      scope_id: props.appId,
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
      scope: "app",
      scope_id: props.appId,
      memory_key: item.memory_key,
    });
    message.success("已删除");
    loadList();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    message.error("删除失败：" + msg);
  }
}

watch(
  () => props.appId,
  (id) => {
    if (id) loadList();
  },
  { immediate: true },
);
</script>

<style scoped>
.amp-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.amp-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.amp-head-text {
  flex: 1;
  min-width: 0;
}

.amp-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text);
}

.amp-sub {
  margin: 4px 0 0;
  color: var(--color-text-tertiary);
  font-size: 13px;
  line-height: 1.6;
}

.amp-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.amp-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.stat-card {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--surface-strong);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.stat-label {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.stat-card--user {
  background: linear-gradient(135deg, var(--color-info-bg), var(--surface-strong));
  border-color: var(--color-info-bg-strong);
}
.stat-card--user .stat-num {
  color: var(--color-info-strong);
}

.stat-card--agent {
  background: linear-gradient(135deg, var(--color-violet-bg), var(--surface-strong));
  border-color: var(--color-violet-bg-strong);
}
.stat-card--agent .stat-num {
  color: var(--color-accent);
}

.stat-card--admin {
  background: linear-gradient(135deg, var(--color-success-bg), var(--surface-strong));
  border-color: var(--color-success-bg-strong);
}
.stat-card--admin .stat-num {
  color: var(--color-success-text);
}

.amp-filterbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.filter-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-chip {
  appearance: none;
  border: 1px solid var(--color-border);
  background: var(--surface-strong);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.12s ease;
}

.filter-chip:hover,
.filter-chip--active {
  border-color: var(--color-info-bg-strong);
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

.filter-chip-count {
  font-size: 10px;
  color: var(--color-text-quaternary);
  font-variant-numeric: tabular-nums;
}

.filter-chip--active .filter-chip-count {
  color: var(--color-info-strong);
  opacity: 0.7;
}

.amp-search {
  flex: 1;
  min-width: 200px;
  max-width: 360px;
}

.amp-sort {
  width: 160px;
}

.amp-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.amp-card {
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  align-items: stretch;
  gap: 12px;
  position: relative;
  transition: border-color 0.15s ease, background 0.15s ease;
  overflow: hidden;
}

.amp-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--color-text-quaternary);
}

.amp-card--user_explicit::before {
  background: var(--color-info);
}

.amp-card--agent_learned::before {
  background: var(--color-accent);
}

.amp-card--admin_set::before {
  background: var(--color-success);
}

.amp-card:hover {
  border-color: var(--color-info-bg-strong);
  background: var(--color-bg-elevated);
}

.amp-card-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.amp-value {
  color: var(--color-text);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.amp-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.amp-key {
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 2px;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-icon {
  color: var(--color-text-quaternary);
  font-weight: 600;
}

.amp-time {
  color: var(--color-text-quaternary);
  margin-left: auto;
  font-size: 12px;
  flex-shrink: 0;
}

.amp-card-actions {
  display: flex;
  gap: 4px;
  align-items: flex-start;
  opacity: 0.4;
  transition: opacity 0.15s ease;
}

.amp-card:hover .amp-card-actions {
  opacity: 1;
}

.amp-empty {
  border: 1px dashed var(--color-info-bg-strong);
  border-radius: 16px;
  background: var(--surface-muted);
  font-size: 13px;
  padding: 40px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.amp-empty--inline {
  border: none;
  background: transparent;
  padding: 32px 12px;
}

.empty-icon {
  font-size: 36px;
  color: var(--color-border-secondary);
}

.empty-title {
  color: var(--color-text-secondary);
  font-size: 15px;
  font-weight: 600;
}

.empty-desc {
  color: var(--color-text-tertiary);
  line-height: 1.6;
  max-width: 420px;
  margin-bottom: 4px;
}

.amp-form :deep(.ant-form-item-label > label) {
  font-weight: 500;
  color: var(--color-text);
  flex-direction: row;
  align-items: baseline;
  gap: 8px;
}

.form-hint {
  color: var(--color-text-quaternary);
  font-size: 12px;
  font-weight: 400;
}

.form-hint--note {
  margin-top: 4px;
  font-style: italic;
}

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
  background: var(--color-violet-bg);
  color: var(--color-accent);
}

.source-tag--user_explicit {
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

.source-tag--admin_set {
  background: var(--color-success-bg);
  color: var(--color-success-text);
}

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
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--color-border);
}

.audit-row {
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--surface-muted);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-left: 2px solid var(--color-text-quaternary);
}

.audit-row--remembered {
  border-left-color: var(--color-success);
}

.audit-row--updated {
  border-left-color: var(--color-info);
}

.audit-row--forgotten,
.audit-row--admin_purged {
  border-left-color: var(--color-error);
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
  background: var(--color-success-bg);
  color: var(--color-success-text);
}

.audit-event--updated {
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

.audit-event--forgotten,
.audit-event--admin_purged {
  background: var(--color-error-bg);
  color: var(--color-error-text);
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
  background: var(--color-error-bg);
  color: var(--color-error-text);
}

.audit-val--after .audit-label {
  background: var(--color-success-bg);
  color: var(--color-success-text);
}

.audit-content {
  color: var(--color-text-secondary);
  flex: 1;
  min-width: 0;
}

.audit-meta {
  display: flex;
  gap: 10px;
  color: var(--color-text-quaternary);
  font-size: 11px;
  flex-wrap: wrap;
  margin-top: 2px;
  align-items: center;
}
</style>
