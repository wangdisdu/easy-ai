<template>
  <section class="app-page">
    <div class="app-page-head">
      <div>
        <h2 class="app-page-title">应用工厂</h2>
        <p class="app-page-sub">
          按应用类型分类管理 — 不同类型对应不同的能力与配置
        </p>
      </div>
      <a-button v-if="canEdit" type="primary" class="app-head-btn" @click="onCreate">
        <template #icon><PlusOutlined /></template>
        创建{{ activeTypeMeta.label }}
      </a-button>
    </div>

    <a-tabs v-model:activeKey="activeType" class="app-tabs" @change="onTabChange">
      <a-tab-pane v-for="t in typeTabs" :key="t.value">
        <template #tab>
          <span class="app-tab-label">
            <span :class="['app-tab-dot', `app-tab-dot--${t.value}`]" />
            <span>{{ t.label }}</span>
            <span class="app-tab-count">{{ t.count }}</span>
          </span>
        </template>
      </a-tab-pane>
    </a-tabs>

    <div class="filter-toolbar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        :placeholder="`搜索 ${activeTypeMeta.label} 应用...`"
        allow-clear
        @search="onSearch"
      />
      <a-select
        v-model:value="filterCategoryId"
        class="category-filter"
        placeholder="按分类筛选"
        allow-clear
        :options="categoryOptions"
        @change="onSearch"
      />
      <div class="filter-row">
        <button
          v-for="item in statusFilters"
          :key="item.value"
          type="button"
          class="filter-chip"
          :class="{ 'filter-chip--active': filterStatus === item.value }"
          @click="selectStatusFilter(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div v-if="list.length" class="app-grid">
        <article
          v-for="app in list"
          :key="app.id"
          class="app-card"
          @click="router.push(`/app/${app.id}`)"
        >
          <div class="app-card-top">
            <div class="app-card-status">
              <span :class="['app-status-dot', `app-status--${app.app_status}`]" />
              <span class="app-status-text">{{ statusLabel[app.app_status] || app.app_status }}</span>
            </div>
            <a-popconfirm v-if="canEdit" title="确定删除该应用？" @confirm="onDelete(app)">
              <a-button type="text" size="small" danger @click.stop>删除</a-button>
            </a-popconfirm>
          </div>

          <h4 class="app-card-name">{{ app.name }}</h4>
          <p class="app-card-desc">{{ app.description || "暂无描述" }}</p>

          <div v-if="app.categories && app.categories.length" class="app-card-tags">
            <a-tag v-for="c in app.categories" :key="c.id" size="small" color="blue">
              {{ c.name }}
            </a-tag>
          </div>

          <div class="app-card-meta">
            <span class="app-card-meta-item">模型 {{ app.model || "-" }}</span>
            <span class="app-card-meta-item">版本 {{ app.current_version || "草稿" }}</span>
          </div>

          <div class="app-card-footer">
            <span>创建于 {{ formatMs(app.create_time) }}</span>
          </div>
        </article>
      </div>

      <a-empty
        v-else-if="!loading"
        :description="`暂无 ${activeTypeMeta.label} 应用`"
        class="empty-block"
      >
        <a-button v-if="canEdit" type="primary" @click="onCreate">
          创建第一个 {{ activeTypeMeta.label }}
        </a-button>
      </a-empty>
    </a-spin>

    <div v-if="total > pageSize" class="app-pagination">
      <a-pagination
        v-model:current="pageNo"
        :page-size="pageSize"
        :total="total"
        show-size-changer
        :show-total="(t: number) => `共 ${t} 条`"
        @change="loadList"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as appApi from "@/api/app";
import * as categoryApi from "@/api/appCategory";
import type { AppCategoryResp, AppResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.APP_EDIT));

const router = useRouter();

type AppType = "agent" | "agent_flow" | "llm" | "rag" | "nl2sql";

const TYPE_META: Record<AppType, { label: string }> = {
  agent: { label: "Agent" },
  agent_flow: { label: "Agent Flow" },
  llm: { label: "LLM" },
  rag: { label: "RAG" },
  nl2sql: { label: "NL2SQL" },
};

const TYPE_ORDER: AppType[] = ["agent", "agent_flow", "llm", "rag", "nl2sql"];

const activeType = ref<AppType>("agent");
const keyword = ref("");
const filterStatus = ref("");
const filterCategoryId = ref<string | undefined>(undefined);
const list = ref<AppResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const countMap = ref<Record<string, number>>({});
const categories = ref<AppCategoryResp[]>([]);

const categoryOptions = computed(() =>
  categories.value.map((c) => ({ value: c.id, label: c.name }))
);

const statusLabel: Record<string, string> = {
  draft: "草稿",
  published: "已发布",
  offline: "已下线",
};

const typeTabs = computed(() =>
  TYPE_ORDER.map((value) => ({
    value,
    label: TYPE_META[value].label,
    count: countMap.value[value] ?? 0,
  }))
);

const activeTypeMeta = computed(() => TYPE_META[activeType.value]);

const statusFilters = computed(() => [
  { label: "全部状态", value: "" },
  { label: "已发布", value: "published" },
  { label: "草稿", value: "draft" },
  { label: "已下线", value: "offline" },
]);

async function loadSummary() {
  const { data } = await appApi.pageApp({ page_no: 1, page_size: 1000 });
  const counts: Record<string, number> = {};
  for (const item of data.data) {
    counts[item.app_type] = (counts[item.app_type] || 0) + 1;
  }
  countMap.value = counts;
}

async function loadList() {
  loading.value = true;
  try {
    const { data } = await appApi.pageApp({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      app_type: activeType.value,
      app_status: filterStatus.value || undefined,
      category_id: filterCategoryId.value || undefined,
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function loadCategories() {
  const { data } = await categoryApi.listAppCategory();
  categories.value = data.data;
}

function onSearch() {
  pageNo.value = 1;
  void loadList();
}

/** 切换 tab：重置分页和状态过滤，但保留搜索词。 */
function onTabChange() {
  pageNo.value = 1;
  filterStatus.value = "";
  filterCategoryId.value = undefined;
  void loadList();
}

function selectStatusFilter(value: string) {
  filterStatus.value = value;
  onSearch();
}

/** 把当前 tab 的 type 通过 query 传给创建页（create 页若不读这个参数也不会出错）。 */
function onCreate() {
  router.push({ path: "/app/create", query: { type: activeType.value } });
}

async function onDelete(app: AppResp) {
  await appApi.deleteApp(app.id);
  message.success("已删除");
  await Promise.all([loadList(), loadSummary()]);
}

onMounted(async () => {
  await Promise.all([loadList(), loadSummary(), loadCategories()]);
});
</script>

<style scoped>
.app-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-info-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.app-page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.app-page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}

.app-page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.app-head-btn {
  height: 40px;
  padding-inline: 16px;
  border-radius: 12px;
}

/* ── Tabs ── */
.app-tabs {
  margin-top: 16px;
}

.app-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 18px;
}

.app-tabs :deep(.ant-tabs-nav::before) {
  border-bottom-color: var(--surface-divider);
}

.app-tabs :deep(.ant-tabs-tab) {
  padding: 10px 4px 12px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.app-tabs :deep(.ant-tabs-tab:hover) {
  color: var(--color-text-secondary);
}

.app-tabs :deep(.ant-tabs-tab.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--color-text);
  font-weight: 600;
}

.app-tabs :deep(.ant-tabs-ink-bar) {
  height: 3px;
  border-radius: 999px;
  background: var(--gradient-brand-horizontal);
}

.app-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.app-tab-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.app-tab-dot--agent { background: var(--color-accent); }
.app-tab-dot--agent_flow { background: var(--color-warning); }
.app-tab-dot--llm { background: var(--color-success); }
.app-tab-dot--rag { background: var(--color-info); }
.app-tab-dot--nl2sql { background: var(--color-cyan-text); }

.app-tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--color-split);
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.app-tabs :deep(.ant-tabs-tab-active) .app-tab-count {
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

/* ── Filter ── */
.filter-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.search-input {
  width: 280px;
  min-width: 220px;
  flex: 0 1 280px;
}

.category-filter {
  width: 200px;
  min-width: 160px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.filter-chip {
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 8px 14px;
  background: var(--color-split);
  color: var(--color-text-tertiary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.filter-chip:hover,
.filter-chip--active {
  border-color: var(--color-info-bg-strong);
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

/* ── Grid & Cards ── */
.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.app-card {
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--surface-strong);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.app-card:hover {
  transform: translateY(-2px);
  border-color: var(--color-info-bg-strong);
  box-shadow: var(--shadow-info-drop);
}

.app-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.app-card-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.app-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.app-status--published {
  background: var(--color-success);
}

.app-status--draft {
  background: var(--color-text-quaternary);
}

.app-status--offline {
  background: var(--color-border-secondary);
}

.app-status-text {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.app-card-name {
  margin: 14px 0 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.app-card-desc {
  min-height: 44px;
  margin: 0;
  color: var(--color-text-tertiary);
  font-size: 13px;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.app-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 10px;
}

.app-card-meta {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.app-card-meta-item {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.app-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-text-quaternary);
}

.empty-block {
  padding: 56px 0;
}

.app-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

@media (max-width: 768px) {
  .filter-toolbar {
    align-items: stretch;
  }

  .search-input {
    width: 100%;
    flex-basis: 100%;
  }
}
</style>
