<template>
  <section class="alert-page">
    <div class="alert-page-head">
      <div>
        <h2 class="alert-page-title">告警中心</h2>
        <p class="alert-page-sub">查看、确认与恢复由告警规则产生的告警记录</p>
      </div>
      <a-button class="head-btn" :loading="loading" @click="refreshAll">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
    </div>

    <ObsTabBar />

    <!-- 活跃告警概览 -->
    <div class="active-strip">
      <div v-if="active && active.total === 0" class="active-ok">
        <CheckCircleOutlined class="ok-icon" />
        系统运行良好,当前无活跃告警
      </div>
      <template v-else-if="active">
        <div class="active-card active-card--critical">
          <span class="ac-num">{{ active.critical }}</span>
          <span class="ac-label">严重</span>
        </div>
        <div class="active-card active-card--warning">
          <span class="ac-num">{{ active.warning }}</span>
          <span class="ac-label">警告</span>
        </div>
        <div class="active-card active-card--info">
          <span class="ac-num">{{ active.info }}</span>
          <span class="ac-label">通知</span>
        </div>
        <div class="active-hint">共 {{ active.total }} 条触发中告警待处理</div>
      </template>
    </div>

    <div class="filter-bar">
      <a-select
        v-model:value="levelFilter"
        class="filter-select"
        placeholder="全部级别"
        allow-clear
        :options="LEVEL_OPTIONS"
        :field-names="{ label: 'label', value: 'value' }"
        @change="onSearch"
      />
      <a-select
        v-model:value="statusFilter"
        class="filter-select"
        placeholder="全部状态"
        allow-clear
        :options="STATUS_OPTIONS"
        @change="onSearch"
      />
      <a-select
        v-model:value="rangeKey"
        class="filter-select"
        :options="RANGE_OPTIONS"
        @change="onSearch"
      />
    </div>

    <a-table
      class="alert-table"
      row-key="id"
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="false"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'level'">
          <a-tag :color="LEVEL_COLOR[record.level]">{{ LEVEL_LABEL[record.level] || record.level }}</a-tag>
        </template>

        <template v-else-if="column.key === 'message'">
          <div class="cell-name">{{ record.rule_name }}</div>
          <div class="cell-desc">{{ record.message }}</div>
        </template>

        <template v-else-if="column.key === 'observed'">
          <span class="cell-cond">{{ fmtNum(record.observed_value) }}</span>
          <span class="cell-muted"> / 阈值 {{ fmtNum(record.threshold) }}</span>
        </template>

        <template v-else-if="column.key === 'triggered_at'">
          {{ formatMs(record.triggered_at) }}
        </template>

        <template v-else-if="column.key === 'duration'">
          {{ formatDuration(record.duration_ms) }}
        </template>

        <template v-else-if="column.key === 'status'">
          <a-tag :color="STATUS_COLOR[record.status]">
            {{ STATUS_LABEL[record.status] || record.status }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'action'">
          <a-button type="link" size="small" @click="openDetail(record)">详情</a-button>
          <a-button
            v-if="record.status === 'firing'"
            type="link"
            size="small"
            @click="onAcknowledge(record)"
          >
            确认
          </a-button>
          <a-button
            v-if="record.status !== 'resolved'"
            type="link"
            size="small"
            @click="onResolve(record)"
          >
            恢复
          </a-button>
        </template>
      </template>
    </a-table>

    <div v-if="total > pageSize" class="alert-pagination">
      <a-pagination
        v-model:current="pageNo"
        :page-size="pageSize"
        :total="total"
        :show-total="(t: number) => `共 ${t} 条`"
        @change="loadList"
      />
    </div>

    <!-- 详情抽屉 -->
    <a-drawer
      v-model:open="detailOpen"
      title="告警详情"
      width="640"
      :body-style="{ paddingBottom: '80px' }"
    >
      <template v-if="detail">
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="规则名称" :span="2">{{ detail.rule_name }}</a-descriptions-item>
          <a-descriptions-item label="级别">
            <a-tag :color="LEVEL_COLOR[detail.level]">{{ LEVEL_LABEL[detail.level] }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="STATUS_COLOR[detail.status]">{{ STATUS_LABEL[detail.status] }}</a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="监控指标">{{ METRIC_LABEL[detail.metric_type] || detail.metric_type }}</a-descriptions-item>
          <a-descriptions-item label="当前值 / 阈值">
            {{ fmtNum(detail.observed_value) }} / {{ fmtNum(detail.threshold) }}
          </a-descriptions-item>
          <a-descriptions-item label="触发时间">{{ formatMs(detail.triggered_at) }}</a-descriptions-item>
          <a-descriptions-item label="持续时长">{{ formatDuration(detail.duration_ms) }}</a-descriptions-item>
          <a-descriptions-item label="确认时间">
            {{ detail.acknowledged_at ? formatMs(detail.acknowledged_at) : "-" }}
          </a-descriptions-item>
          <a-descriptions-item label="恢复时间">
            {{ detail.resolved_at ? formatMs(detail.resolved_at) : "-" }}
          </a-descriptions-item>
          <a-descriptions-item label="告警内容" :span="2">{{ detail.message }}</a-descriptions-item>
        </a-descriptions>

        <h4 class="trace-title">告警溯源曲线</h4>
        <a-spin :spinning="traceLoading">
          <AlertTraceChart
            v-if="trace"
            :points="trace.points"
            :threshold="trace.threshold"
            :triggered-at="trace.triggered_at"
          />
        </a-spin>
      </template>

      <template #footer>
        <div v-if="detail" class="drawer-footer">
          <a-button
            v-if="detail.status === 'firing'"
            @click="onAcknowledge(detail, true)"
          >
            确认告警
          </a-button>
          <a-button
            v-if="detail.status !== 'resolved'"
            type="primary"
            @click="onResolve(detail, true)"
          >
            恢复告警
          </a-button>
        </div>
      </template>
    </a-drawer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { CheckCircleOutlined, ReloadOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as alertApi from "@/api/alert";
import type { AlertActiveResp, AlertRecordResp, AlertTraceResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import ObsTabBar from "./ObsTabBar.vue";
import AlertTraceChart from "./AlertTraceChart.vue";
import { LEVEL_LABEL, LEVEL_OPTIONS, METRIC_LABEL, STATUS_LABEL, formatDuration } from "./alertMeta";

const LEVEL_COLOR: Record<string, string> = { critical: "error", warning: "warning", info: "blue" };
const STATUS_COLOR: Record<string, string> = {
  firing: "error",
  acknowledged: "blue",
  resolved: "success",
};
const STATUS_OPTIONS = [
  { value: "firing", label: "触发中" },
  { value: "acknowledged", label: "已确认" },
  { value: "resolved", label: "已恢复" },
];
const RANGE_OPTIONS = [
  { value: "24h", label: "近 24 小时" },
  { value: "7d", label: "近 7 天" },
  { value: "30d", label: "近 30 天" },
  { value: "all", label: "全部" },
];

const columns = [
  { title: "级别", key: "level", width: 80 },
  { title: "告警", key: "message", dataIndex: "message" },
  { title: "当前值", key: "observed", width: 170 },
  { title: "触发时间", key: "triggered_at", width: 170 },
  { title: "持续", key: "duration", width: 90 },
  { title: "状态", key: "status", width: 90 },
  { title: "操作", key: "action", width: 170 },
];

const list = ref<AlertRecordResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const levelFilter = ref<string | undefined>(undefined);
const statusFilter = ref<string | undefined>(undefined);
const rangeKey = ref("7d");
const active = ref<AlertActiveResp | null>(null);

const detailOpen = ref(false);
const detail = ref<AlertRecordResp | null>(null);
const trace = ref<AlertTraceResp | null>(null);
const traceLoading = ref(false);

function fmtNum(v: number): string {
  return Number.isInteger(v) ? String(v) : String(v);
}

function computeRange(): { from?: number; to?: number } {
  const now = Date.now();
  if (rangeKey.value === "all") return {};
  const span: Record<string, number> = {
    "24h": 24 * 3600_000,
    "7d": 7 * 24 * 3600_000,
    "30d": 30 * 24 * 3600_000,
  };
  return { from: now - span[rangeKey.value], to: now };
}

function onSearch() {
  pageNo.value = 1;
  loadList();
}

async function loadList() {
  loading.value = true;
  try {
    const range = computeRange();
    const { data } = await alertApi.pageAlertRecord({
      page_no: pageNo.value,
      page_size: pageSize.value,
      level: levelFilter.value || undefined,
      status: statusFilter.value || undefined,
      from: range.from,
      to: range.to,
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function loadActive() {
  const { data } = await alertApi.getActiveAlerts();
  active.value = data.data;
}

function refreshAll() {
  loadList();
  loadActive();
}

async function openDetail(record: AlertRecordResp) {
  detail.value = record;
  detailOpen.value = true;
  trace.value = null;
  traceLoading.value = true;
  try {
    const { data } = await alertApi.getAlertTrace(record.id);
    trace.value = data.data;
  } finally {
    traceLoading.value = false;
  }
}

async function onAcknowledge(record: AlertRecordResp, fromDrawer = false) {
  const { data } = await alertApi.acknowledgeAlert(record.id);
  message.success("已确认告警");
  if (fromDrawer) detail.value = data.data;
  refreshAll();
}

async function onResolve(record: AlertRecordResp, fromDrawer = false) {
  const { data } = await alertApi.resolveAlert(record.id);
  message.success("已恢复告警");
  if (fromDrawer) detail.value = data.data;
  refreshAll();
}

onMounted(refreshAll);
</script>

<style scoped>
.alert-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-violet-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.alert-page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.alert-page-title { margin: 0; font-size: 20px; font-weight: 700; color: var(--color-text); }
.alert-page-sub { margin: 6px 0 0; font-size: 13px; color: var(--color-text-tertiary); }
.head-btn { height: 40px; padding-inline: 16px; border-radius: 12px; }

.active-strip { display: flex; align-items: center; gap: 12px; margin: 16px 0; }
.active-ok { display: flex; align-items: center; gap: 8px; padding: 12px 18px; border-radius: 14px; background: var(--color-success-bg); color: var(--color-success-strong); font-size: 13px; font-weight: 600; }
.ok-icon { font-size: 16px; }
.active-card { display: flex; flex-direction: column; align-items: center; min-width: 84px; padding: 10px 16px; border-radius: 14px; border: 1px solid var(--color-border); }
.active-card--critical { background: var(--color-error-bg); }
.active-card--warning { background: var(--color-warning-bg); }
.active-card--info { background: var(--color-info-bg); }
.ac-num { font-size: 22px; font-weight: 800; color: var(--color-text); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.ac-label { font-size: 12px; color: var(--color-text-tertiary); }
.active-hint { font-size: 13px; color: var(--color-text-tertiary); }

.filter-bar { display: flex; align-items: center; gap: 12px; margin: 8px 0 18px; }
.filter-select { width: 150px; }

.alert-table { margin-top: 4px; }
.cell-name { font-weight: 600; color: var(--color-text); }
.cell-desc { font-size: 12px; color: var(--color-text-quaternary); margin-top: 2px; }
.cell-muted { color: var(--color-text-quaternary); font-size: 12px; }
.cell-cond { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; color: var(--color-text); }

.alert-pagination { display: flex; justify-content: flex-end; margin-top: 20px; }

.trace-title { margin: 22px 0 10px; font-size: 14px; font-weight: 700; color: var(--color-text-secondary); }
.drawer-footer { display: flex; justify-content: flex-end; gap: 12px; }

@media (max-width: 960px) {
  .alert-page-head { flex-direction: column; }
  .filter-bar, .active-strip { flex-wrap: wrap; }
}
</style>
