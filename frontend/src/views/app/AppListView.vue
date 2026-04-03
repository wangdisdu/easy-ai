<template>
  <section class="app-page">
    <div class="app-page-head">
      <div>
        <h2 class="app-page-title">应用工厂</h2>
        <p class="app-page-sub">基于模板快速创建 LLM / RAG / NL2SQL / Agent / Agent Flow 应用</p>
      </div>
      <a-button type="primary" class="app-head-btn" @click="router.push('/app/create')">
        <template #icon><PlusOutlined /></template>
        创建应用
      </a-button>
    </div>

    <div class="filter-toolbar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        placeholder="搜索应用名称或描述..."
        allow-clear
        @search="onSearch"
      />
      <div class="filter-row">
        <button
          v-for="item in typeFilters"
          :key="item.value"
          type="button"
          class="filter-chip"
          :class="{ 'filter-chip--active': filterType === item.value }"
          @click="selectTypeFilter(item.value)"
        >
          {{ item.label }} ({{ item.count }})
        </button>
      </div>

      <div class="filter-row">
        <button
          v-for="item in statusFilters"
          :key="item.value"
          type="button"
          class="filter-chip filter-chip--soft"
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
            <span :class="['app-type-tag', `app-type--${app.app_type}`]">
              {{ appTypeLabel[app.app_type] || app.app_type }}
            </span>
            <div class="app-card-top-right">
              <div class="app-card-status">
                <span :class="['app-status-dot', `app-status--${app.app_status}`]" />
                <span class="app-status-text">{{ statusLabel[app.app_status] || app.app_status }}</span>
              </div>
              <a-popconfirm title="确定删除该应用？" @confirm="onDelete(app)">
                <a-button type="text" size="small" danger @click.stop>删除</a-button>
              </a-popconfirm>
            </div>
          </div>

          <h4 class="app-card-name">{{ app.name }}</h4>
          <p class="app-card-desc">{{ app.description || "暂无描述" }}</p>

          <div class="app-card-meta">
            <span class="app-card-meta-item">模型 {{ app.model || "-" }}</span>
            <span class="app-card-meta-item">版本 {{ app.current_version || "草稿" }}</span>
          </div>

          <div class="app-card-footer">
            <span>创建于 {{ formatMs(app.create_time) }}</span>
            <span class="app-card-calls">{{ statusLabel[app.app_status] || app.app_status }}</span>
          </div>
        </article>
      </div>

      <a-empty v-else-if="!loading" description="没有找到匹配的应用" class="empty-block" />
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
import type { AppResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const router = useRouter();

const keyword = ref("");
const filterType = ref("");
const filterStatus = ref("");
const list = ref<AppResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const countMap = ref<Record<string, number>>({});

const appTypeLabel: Record<string, string> = {
  llm: "LLM",
  rag: "RAG",
  nl2sql: "NL2SQL",
  agent: "Agent",
  agent_flow: "Agent Flow",
};

const statusLabel: Record<string, string> = {
  draft: "草稿",
  published: "已发布",
  offline: "已下线",
};

const typeFilters = computed(() => [
  { label: "全部", value: "", count: total.value },
  { label: "RAG", value: "rag", count: countMap.value.rag ?? 0 },
  { label: "NL2SQL", value: "nl2sql", count: countMap.value.nl2sql ?? 0 },
  { label: "LLM", value: "llm", count: countMap.value.llm ?? 0 },
  { label: "Agent", value: "agent", count: countMap.value.agent ?? 0 },
  { label: "Agent Flow", value: "agent_flow", count: countMap.value.agent_flow ?? 0 },
]);

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
      app_type: filterType.value || undefined,
      app_status: filterStatus.value || undefined,
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pageNo.value = 1;
  void loadList();
}

function selectTypeFilter(value: string) {
  filterType.value = value;
  onSearch();
}

function selectStatusFilter(value: string) {
  filterStatus.value = value;
  onSearch();
}

async function onDelete(app: AppResp) {
  await appApi.deleteApp(app.id);
  message.success("已删除");
  await Promise.all([loadList(), loadSummary()]);
}

onMounted(async () => {
  await Promise.all([loadList(), loadSummary()]);
});
</script>

<style scoped>
.app-page {
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

.app-page-head,
.app-card-top,
.app-card-top-right,
.app-card-status,
.app-card-footer {
  display: flex;
  align-items: center;
}

.app-page-head,
.app-card-top,
.app-card-footer {
  justify-content: space-between;
}

.app-page-head {
  align-items: flex-start;
  gap: 16px;
}

.app-page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.app-page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.app-head-btn {
  height: 40px;
  padding-inline: 16px;
  border-radius: 12px;
}

.filter-toolbar {
  margin-top: 18px;
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

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.filter-chip {
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 8px 14px;
  background: rgba(241, 245, 249, 0.92);
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.filter-chip--soft {
  background: rgba(248, 250, 252, 0.92);
}

.filter-chip:hover,
.filter-chip--active {
  border-color: rgba(59, 130, 246, 0.18);
  background: rgba(219, 234, 254, 0.9);
  color: #2563eb;
}

.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-top: 18px;
}

.app-card {
  padding: 20px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.app-card:hover {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, 0.24);
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.08);
}

.app-card-top-right {
  gap: 8px;
}

.app-type-tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.app-type--rag {
  background: rgba(59, 130, 246, 0.1);
  color: #2563eb;
}

.app-type--nl2sql {
  background: rgba(6, 182, 212, 0.1);
  color: #0891b2;
}

.app-type--llm {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.app-type--agent {
  background: rgba(139, 92, 246, 0.1);
  color: #7c3aed;
}

.app-type--agent_flow {
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.app-card-status {
  gap: 6px;
}

.app-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.app-status--published {
  background: #10b981;
}

.app-status--draft {
  background: #94a3b8;
}

.app-status--offline {
  background: #cbd5e1;
}

.app-status-text {
  font-size: 12px;
  color: #64748b;
}

.app-card-name {
  margin: 14px 0 8px;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.app-card-desc {
  min-height: 44px;
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.app-card-meta {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.app-card-meta-item {
  font-size: 12px;
  color: #475569;
}

.app-card-footer {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(226, 232, 240, 0.76);
  font-size: 12px;
  color: #94a3b8;
}

.app-card-calls {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
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
