<template>
  <section class="obs-page">
    <div class="obs-head">
      <div class="obs-head-left">
        <h2 class="obs-title">可观测性</h2>
        <p class="obs-sub">全局运营视角 · 跨应用对比 · Langfuse 集成</p>
      </div>
      <div class="obs-head-right">
        <span class="obs-range-badge">
          <ClockCircleOutlined />
          今日 00:00 至今
        </span>
        <a-button @click="loadAll(true)" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
    </div>

    <div style="margin: 4px 0 18px">
      <ObsTabBar />
    </div>

    <a-spin :spinning="loading" wrapper-class-name="obs-spin">
      <!-- 1. 核心指标卡 -->
      <div class="stat-grid">
        <div v-for="card in statCards" :key="card.key" class="stat-card" :style="{ '--accent': card.color }">
          <div class="stat-icon">
            <component :is="card.icon" />
          </div>
          <div class="stat-body">
            <span class="stat-label">{{ card.label }}</span>
            <div class="stat-value">{{ card.value }}</div>
            <span class="stat-sub">{{ card.sub }}</span>
          </div>
        </div>
      </div>

      <!-- 2. 调用量趋势 + Token 按模型 -->
      <div class="dual-grid">
        <section class="panel-card panel-card--span2">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">全局调用量趋势 (24h)</h3>
              <p class="panel-sub">2 小时一桶 · Top {{ trend?.apps.length || 0 }} 应用</p>
            </div>
            <div class="panel-legend">
              <span v-for="a in trend?.apps || []" :key="a.app_id" class="legend-item">
                <span class="legend-dot" :style="{ background: a.color }" />
                <span>{{ a.app_name }}</span>
              </span>
            </div>
          </div>
          <AreaChart
            v-if="trend"
            :data="trend.total"
            :labels="trend.labels"
            color="#3B82F6"
            :height="180"
          />
          <a-empty v-else :image="false" description="暂无数据" />
          <div v-if="trend?.apps.length" class="trend-summary">
            <div v-for="a in trend.apps" :key="a.app_id" class="trend-summary-item">
              <div class="trend-summary-name">{{ a.app_name }}</div>
              <div class="trend-summary-val">{{ formatNumber(sumArray(a.data)) }}</div>
            </div>
          </div>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">Token 消耗 (按模型)</h3>
              <p class="panel-sub">费用 P0 阶段未启用</p>
            </div>
          </div>
          <div v-if="modelTokens.length" class="donut-wrap">
            <DonutChart :segments="modelSegments" :size="140" />
          </div>
          <a-empty v-else :image="false" description="暂无数据" />
          <div v-if="modelTokens.length" class="model-list">
            <div v-for="(m, i) in modelTokens" :key="m.model" class="model-row">
              <span class="legend-dot" :style="{ background: tokenColors[i % tokenColors.length] }" />
              <span class="model-name">{{ m.model }}</span>
              <span class="model-tokens">{{ formatTokens(m.total_tokens) }}</span>
              <span class="model-cost">{{ m.cost ?? "-" }}</span>
            </div>
          </div>
        </section>
      </div>

      <!-- 3. 应用健康度排行 + 错误率 -->
      <div class="dual-grid">
        <section class="panel-card panel-card--span2">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">应用健康度排行</h3>
              <p class="panel-sub">支持按调用量 / 成功率 / 好评率排序</p>
            </div>
            <div class="sort-tabs">
              <button
                v-for="s in healthSortOptions"
                :key="s.id"
                :class="['sort-tab', { 'sort-tab--active': healthSort === s.id }]"
                @click="healthSort = s.id"
              >
                {{ s.label }}
              </button>
            </div>
          </div>
          <a-table
            :columns="healthColumns"
            :data-source="sortedHealth"
            :pagination="false"
            row-key="app_id"
            size="small"
            :locale="{ emptyText: '暂无数据' }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'app_type'">
                <span :class="['type-tag', `type-tag--${record.app_type}`]">{{ record.app_type }}</span>
              </template>
              <template v-else-if="column.key === 'calls'">
                {{ formatNumber(record.calls) }}
              </template>
              <template v-else-if="column.key === 'success_rate'">
                <span :class="record.success_rate >= 99 ? 'val-good' : 'val-warn'">{{ record.success_rate }}%</span>
              </template>
              <template v-else-if="column.key === 'p95_latency_ms'">
                {{ record.p95_latency_ms !== null ? record.p95_latency_ms + "ms" : "-" }}
              </template>
              <template v-else-if="column.key === 'total_tokens'">
                {{ formatTokens(record.total_tokens) }}
              </template>
              <template v-else-if="column.key === 'feedback_rate'">
                <span class="val-muted">-</span>
              </template>
              <template v-else-if="column.key === 'trend'">
                <SparkLine :data="record.trend" :width="60" :height="20" color="#3B82F6" />
              </template>
            </template>
          </a-table>
        </section>

        <section class="panel-card">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">错误率排行</h3>
              <p class="panel-sub">按错误率降序</p>
            </div>
          </div>
          <div v-if="errors.length" class="error-list">
            <div v-for="e in errors" :key="e.app_id" class="error-row">
              <div class="error-row-head">
                <div>
                  <span class="error-app">{{ e.app_name }}</span>
                  <span :class="['type-tag', `type-tag--${e.app_type}`]">{{ e.app_type }}</span>
                </div>
                <span :class="errorRateClass(e.error_rate)">{{ e.error_rate }}%</span>
              </div>
              <div class="error-bar">
                <div
                  class="error-bar-fill"
                  :style="{
                    width: `${(e.error_rate / Math.max(...errors.map(x => x.error_rate), 0.001)) * 100}%`,
                    background: errorBarColor(e.error_rate),
                  }"
                />
              </div>
              <div class="error-row-foot">
                <span class="error-top">主要: {{ e.top_error || "-" }}</span>
                <span class="error-count">{{ e.errors }} 次</span>
              </div>
            </div>
          </div>
          <a-empty v-else :image="false" description="暂无错误" />
        </section>
      </div>

      <!-- 4. 最近请求 -->
      <section class="panel-card">
        <div class="panel-head">
          <div>
            <h3 class="panel-title">最近请求</h3>
            <p class="panel-sub">点击行查看 Trace（需启用 Langfuse）</p>
          </div>
        </div>
        <a-table
          :columns="recentColumns"
          :data-source="recents"
          :pagination="false"
          row-key="id"
          size="small"
          :custom-row="onRecentRowClick"
          :locale="{ emptyText: '暂无数据' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'create_time'">
              <span class="mono">{{ formatTime(record.create_time) }}</span>
            </template>
            <template v-else-if="column.key === 'app_type'">
              <span v-if="record.app_type" :class="['type-tag', `type-tag--${record.app_type}`]">{{ record.app_type }}</span>
              <span v-else>-</span>
            </template>
            <template v-else-if="column.key === 'preview'">
              <span class="preview-cell">{{ record.preview || "-" }}</span>
            </template>
            <template v-else-if="column.key === 'latency_ms'">
              {{ record.latency_ms !== null ? record.latency_ms + "ms" : "-" }}
            </template>
            <template v-else-if="column.key === 'total_tokens'">
              {{ record.total_tokens ?? "-" }}
            </template>
            <template v-else-if="column.key === 'success'">
              <span :class="record.success ? 'val-good' : 'val-error'">
                {{ record.success ? "成功" : "失败" }}
              </span>
            </template>
            <template v-else-if="column.key === 'feedback'">
              <span class="val-muted">-</span>
            </template>
          </template>
        </a-table>
      </section>
    </a-spin>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import {
  ClockCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
} from "@ant-design/icons-vue";
import AreaChart from "@/components/charts/AreaChart.vue";
import DonutChart from "@/components/charts/DonutChart.vue";
import SparkLine from "@/components/charts/SparkLine.vue";
import ObsTabBar from "./ObsTabBar.vue";
import * as obsApi from "@/api/observability";
import type {
  AppHealthRow,
  ErrorAppRow,
  ModelTokenRow,
  OverviewStats,
  RecentRequestRow,
  TrendResp,
} from "@/api/types";

const LANGFUSE_HOST = "http://localhost:3000";

const loading = ref(false);
const stats = ref<OverviewStats | null>(null);
const trend = ref<TrendResp | null>(null);
const modelTokens = ref<ModelTokenRow[]>([]);
const health = ref<AppHealthRow[]>([]);
const errors = ref<ErrorAppRow[]>([]);
const recents = ref<RecentRequestRow[]>([]);

const healthSort = ref<"calls" | "success_rate" | "feedback_rate">("calls");
const healthSortOptions = [
  { id: "calls" as const, label: "调用量" },
  { id: "success_rate" as const, label: "成功率↑" },
  { id: "feedback_rate" as const, label: "好评率" },
];

const tokenColors = ["#3B82F6", "#8B5CF6", "#06B6D4", "#10B981", "#F59E0B", "#EF4444"];

const statCards = computed(() => [
  {
    key: "requests",
    label: "今日总请求",
    color: "#3B82F6",
    icon: ThunderboltOutlined,
    value: formatNumber(stats.value?.total_requests.value),
    sub: stats.value?.total_requests.sub_label || "-",
  },
  {
    key: "success",
    label: "全局成功率",
    color: "#10B981",
    icon: CheckCircleOutlined,
    value:
      stats.value?.success_rate.value !== null && stats.value?.success_rate.value !== undefined
        ? stats.value.success_rate.value + "%"
        : "-",
    sub: stats.value?.success_rate.sub_label || "-",
  },
  {
    key: "latency",
    label: "P95 延迟",
    color: "#F59E0B",
    icon: DashboardOutlined,
    value:
      stats.value?.p95_latency_ms.value !== null && stats.value?.p95_latency_ms.value !== undefined
        ? stats.value.p95_latency_ms.value + "ms"
        : "-",
    sub: stats.value?.p95_latency_ms.sub_label || "-",
  },
  {
    key: "tokens",
    label: "Token 总消耗",
    color: "#8B5CF6",
    icon: DatabaseOutlined,
    value: formatTokens(stats.value?.total_tokens.value),
    sub: stats.value?.total_tokens.sub_label || "-",
  },
]);

const modelSegments = computed(() =>
  modelTokens.value.map((m, i) => ({
    value: m.total_tokens,
    color: tokenColors[i % tokenColors.length],
  }))
);

const sortedHealth = computed(() => {
  const list = [...health.value];
  if (healthSort.value === "calls") return list.sort((a, b) => b.calls - a.calls);
  if (healthSort.value === "success_rate") return list.sort((a, b) => a.success_rate - b.success_rate);
  return list;
});

const healthColumns = [
  { title: "应用", dataIndex: "app_name", key: "app_name" },
  { title: "类型", dataIndex: "app_type", key: "app_type" },
  { title: "调用量", dataIndex: "calls", key: "calls", align: "right" },
  { title: "成功率", dataIndex: "success_rate", key: "success_rate", align: "right" },
  { title: "P95", dataIndex: "p95_latency_ms", key: "p95_latency_ms", align: "right" },
  { title: "Token", dataIndex: "total_tokens", key: "total_tokens", align: "right" },
  { title: "好评率", dataIndex: "feedback_rate", key: "feedback_rate", align: "right" },
  { title: "趋势", dataIndex: "trend", key: "trend", align: "right", width: 80 },
];

const recentColumns = [
  { title: "时间", dataIndex: "create_time", key: "create_time", width: 160 },
  { title: "应用", dataIndex: "app_name", key: "app_name" },
  { title: "类型", dataIndex: "app_type", key: "app_type", width: 80 },
  { title: "查询内容", dataIndex: "preview", key: "preview", ellipsis: true },
  { title: "延迟", dataIndex: "latency_ms", key: "latency_ms", width: 90 },
  { title: "Tokens", dataIndex: "total_tokens", key: "total_tokens", width: 90 },
  { title: "状态", dataIndex: "success", key: "success", width: 70 },
  { title: "反馈", dataIndex: "feedback", key: "feedback", width: 60 },
];

function formatNumber(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return v.toLocaleString();
}

function formatTokens(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + "M";
  if (v >= 1_000) return (v / 1_000).toFixed(1) + "K";
  return String(v);
}

function formatTime(ms: number): string {
  const d = new Date(ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function sumArray(arr: number[]): number {
  return arr.reduce((s, v) => s + v, 0);
}

function errorRateClass(rate: number): string {
  if (rate >= 1) return "val-error";
  if (rate >= 0.5) return "val-warn";
  return "val-muted";
}

function errorBarColor(rate: number): string {
  if (rate >= 1) return "#EF4444";
  if (rate >= 0.5) return "#F59E0B";
  return "#94a3b8";
}

function onRecentRowClick(record: RecentRequestRow) {
  return {
    style: { cursor: record.langfuse_trace_id ? "pointer" : "default" },
    onClick: () => {
      if (!record.langfuse_trace_id) {
        message.info("未开启 Langfuse 追踪，无法查看完整 Trace");
        return;
      }
      window.open(`${LANGFUSE_HOST}/trace/${record.langfuse_trace_id}`, "_blank");
    },
  };
}

async function loadAll(showMsg = false) {
  loading.value = true;
  try {
    const [s, t, m, h, e, r] = await Promise.all([
      obsApi.getOverviewStats(),
      obsApi.getOverviewTrend({ top: 5 }),
      obsApi.getTokensByModel(),
      obsApi.getAppHealth({ sort: "calls", limit: 20 }),
      obsApi.getErrorsByApp({ limit: 10 }),
      obsApi.getRecentRequests({ limit: 20 }),
    ]);
    stats.value = s.data.data || null;
    trend.value = t.data.data || null;
    modelTokens.value = m.data.data || [];
    health.value = h.data.data || [];
    errors.value = e.data.data || [];
    recents.value = r.data.data || [];
    if (showMsg) message.success("已刷新");
  } catch (err) {
    message.error("数据加载失败");
    console.error(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadAll();
});
</script>

<style scoped>
.obs-page {
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  background: var(--surface-subtle);
  min-height: 100%;
}

.obs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.obs-head-left {
  display: flex;
  flex-direction: column;
}

.obs-head-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.obs-range-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-text-secondary);
  box-shadow: var(--shadow-card-sm);
}

.obs-range-badge :deep(svg) {
  color: var(--color-info);
}

.obs-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.obs-sub {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-text-quaternary);
}

/* 核心指标卡 */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px 22px;
  border-radius: 16px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card);
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--accent);
  opacity: 0.85;
}

.stat-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-elevated);
}

.stat-icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 12px;
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.stat-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-quaternary);
  font-weight: 500;
}

.stat-value {
  margin-top: 4px;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

.stat-sub {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-quaternary);
}

/* 双栏布局 */
.dual-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}

.panel-card {
  padding: 20px 22px;
  border-radius: 16px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.panel-sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--color-text-quaternary);
}

.panel-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

/* 趋势底部小结 */
.trend-summary {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.trend-summary-item {
  text-align: center;
}

.trend-summary-name {
  font-size: 11px;
  color: var(--color-text-quaternary);
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.trend-summary-val {
  font-size: 13px;
  color: var(--color-text);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* Token by 模型 */
.donut-wrap {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.model-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.model-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.model-name {
  flex: 1;
  color: var(--color-text);
}

.model-tokens {
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
  font-weight: 600;
}

.model-cost {
  font-variant-numeric: tabular-nums;
  color: var(--color-text-quaternary);
  font-size: 11px;
  width: 36px;
  text-align: right;
}

/* 类型标签 */
.type-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  background: var(--surface-divider);
  color: var(--color-text-secondary);
}

.type-tag--llm {
  background: var(--color-success-bg-strong);
  color: var(--color-success-text);
}

.type-tag--rag {
  background: var(--color-info-bg-strong);
  color: var(--color-info-strong);
}

.type-tag--nl2sql {
  background: var(--color-cyan-bg);
  color: var(--color-cyan-text);
}

.type-tag--agent {
  background: var(--color-violet-bg-strong);
  color: var(--color-accent);
}

.type-tag--agent_flow {
  background: var(--color-warning-bg-strong);
  color: var(--color-warning-text);
}

/* 排序按钮 */
.sort-tabs {
  display: flex;
  gap: 4px;
}

.sort-tab {
  padding: 4px 10px;
  font-size: 12px;
  color: var(--color-text-quaternary);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.sort-tab:hover {
  color: var(--color-text-secondary);
}

.sort-tab--active {
  background: var(--color-info-bg);
  color: var(--color-info-strong);
  font-weight: 600;
}

/* 错误率列表 */
.error-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.error-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
}

.error-app {
  color: var(--color-text);
  font-weight: 600;
  margin-right: 8px;
}

.error-bar {
  height: 6px;
  background: var(--color-border);
  border-radius: 999px;
  overflow: hidden;
}

.error-bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s;
}

.error-row-foot {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 11px;
}

.error-top {
  color: var(--color-text-tertiary);
}

.error-count {
  color: var(--color-text-quaternary);
  font-variant-numeric: tabular-nums;
}

/* 数值颜色 */
.val-good {
  color: var(--color-success-text);
  font-variant-numeric: tabular-nums;
}

.val-warn {
  color: var(--color-warning-text);
  font-variant-numeric: tabular-nums;
}

.val-error {
  color: var(--color-error-text);
  font-variant-numeric: tabular-nums;
}

.val-muted {
  color: var(--color-text-quaternary);
}

.mono {
  font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  font-size: 12px;
}

.preview-cell {
  color: var(--color-text-secondary);
  font-size: 12px;
}

:deep(.ant-table-tbody > tr.ant-table-row:hover > td) {
  background: var(--color-split);
}

:deep(.ant-table-thead > tr > th) {
  background: var(--surface-muted);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--color-border);
}

:deep(.ant-table-tbody > tr > td) {
  font-size: 13px;
  color: var(--color-text);
  border-bottom: 1px solid var(--color-split);
}

:deep(.ant-empty) {
  padding: 24px 0;
}

:deep(.obs-spin) > .ant-spin-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
