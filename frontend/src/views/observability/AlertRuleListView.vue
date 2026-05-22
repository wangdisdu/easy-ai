<template>
  <div class="alert-rule-view">
    <div class="filter-bar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        placeholder="搜索规则名称..."
        allow-clear
        @search="onSearch"
      />
      <a-select
        v-model:value="metricFilter"
        class="filter-select"
        placeholder="全部指标"
        allow-clear
        :options="METRIC_OPTIONS"
        :field-names="{ label: 'label', value: 'value' }"
        @change="onSearch"
      />
      <a-select
        v-model:value="enabledFilter"
        class="filter-select filter-select--sm"
        placeholder="全部状态"
        allow-clear
        :options="[
          { value: 'true', label: '已启用' },
          { value: 'false', label: '已停用' },
        ]"
        @change="onSearch"
      />
      <a-button
        type="primary"
        class="create-btn"
        @click="router.push('/observability/alert-rule/create')"
      >
        <template #icon><PlusOutlined /></template>
        新建规则
      </a-button>
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
        <template v-if="column.key === 'rule_name'">
          <div class="cell-name">{{ record.rule_name }}</div>
          <div v-if="record.description" class="cell-desc">{{ record.description }}</div>
        </template>

        <template v-else-if="column.key === 'metric'">
          {{ METRIC_LABEL[record.metric_type] || record.metric_type }}
          <span v-if="record.target_error_type" class="cell-muted">
            · {{ ERROR_TYPE_LABEL[record.target_error_type] || record.target_error_type }}
          </span>
        </template>

        <template v-else-if="column.key === 'condition'">
          <span class="cell-cond">
            {{ OPERATOR_SYMBOL[record.operator] || record.operator }}
            {{ record.threshold }}{{ record.threshold_unit || "" }}
          </span>
        </template>

        <template v-else-if="column.key === 'level'">
          <a-tag :color="LEVEL_COLOR[record.level]">{{ LEVEL_LABEL[record.level] || record.level }}</a-tag>
        </template>

        <template v-else-if="column.key === 'window'">
          {{ record.window_minutes }} / {{ record.cooldown_minutes }} 分钟
        </template>

        <template v-else-if="column.key === 'trigger'">
          <div>{{ record.trigger_count }} 次</div>
          <div class="cell-desc">
            {{ record.last_triggered_at ? formatMs(record.last_triggered_at) : "从未触发" }}
          </div>
        </template>

        <template v-else-if="column.key === 'enabled'">
          <a-switch
            :checked="record.enabled"
            :loading="togglingId === record.id"
            @change="onToggle(record)"
          />
        </template>

        <template v-else-if="column.key === 'action'">
          <a-button type="link" size="small" :loading="evaluatingId === record.id" @click="onEvaluate(record)">
            立即评估
          </a-button>
          <a-button type="link" size="small" @click="router.push(`/observability/alert-rule/${record.id}/edit`)">
            编辑
          </a-button>
          <a-popconfirm title="确定删除该规则?历史告警记录会保留。" @confirm="onDelete(record)">
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as alertApi from "@/api/alert";
import type { AlertRuleResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import {
  ERROR_TYPE_LABEL,
  LEVEL_LABEL,
  METRIC_LABEL,
  METRIC_OPTIONS,
  OPERATOR_SYMBOL,
} from "./alertMeta";

const router = useRouter();

const LEVEL_COLOR: Record<string, string> = {
  critical: "error",
  warning: "warning",
  info: "blue",
};

const columns = [
  { title: "规则名称", key: "rule_name", dataIndex: "rule_name" },
  { title: "监控指标", key: "metric", width: 160 },
  { title: "触发条件", key: "condition", width: 120 },
  { title: "级别", key: "level", width: 80 },
  { title: "窗口 / 冷却", key: "window", width: 130 },
  { title: "累计触发", key: "trigger", width: 150 },
  { title: "状态", key: "enabled", width: 70 },
  { title: "操作", key: "action", width: 200 },
];

const keyword = ref("");
const metricFilter = ref<string | undefined>(undefined);
const enabledFilter = ref<string | undefined>(undefined);
const list = ref<AlertRuleResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const togglingId = ref("");
const evaluatingId = ref("");

function onSearch() {
  pageNo.value = 1;
  loadList();
}

async function loadList() {
  loading.value = true;
  try {
    const { data } = await alertApi.pageAlertRule({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      metric_type: metricFilter.value || undefined,
      enabled: enabledFilter.value === undefined ? undefined : enabledFilter.value === "true",
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function onToggle(record: AlertRuleResp) {
  togglingId.value = record.id;
  try {
    if (record.enabled) {
      await alertApi.disableAlertRule(record.id);
      message.success("已停用");
    } else {
      await alertApi.enableAlertRule(record.id);
      message.success("已启用");
    }
    await loadList();
  } finally {
    togglingId.value = "";
  }
}

async function onEvaluate(record: AlertRuleResp) {
  evaluatingId.value = record.id;
  try {
    const { data } = await alertApi.evaluateAlertRule(record.id);
    const r = data.data;
    if (r.triggered) {
      message.warning(`已触发:${r.message}`);
    } else {
      message.success(r.message || "未触发");
    }
    await loadList();
  } finally {
    evaluatingId.value = "";
  }
}

async function onDelete(record: AlertRuleResp) {
  await alertApi.deleteAlertRule(record.id);
  message.success("规则已删除");
  await loadList();
}

onMounted(loadList);
</script>

<style scoped>
.create-btn { margin-left: auto; }

.filter-bar { display: flex; align-items: center; gap: 12px; margin: 16px 0 18px; }
.search-input { width: 260px; }
.filter-select { width: 180px; }
.filter-select--sm { width: 130px; }

.alert-table { margin-top: 4px; }
.cell-name { font-weight: 600; color: var(--color-text); }
.cell-desc { font-size: 12px; color: var(--color-text-quaternary); margin-top: 2px; }
.cell-muted { color: var(--color-text-quaternary); font-size: 12px; }
.cell-cond { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 600; color: var(--color-text); }

.alert-pagination { display: flex; justify-content: flex-end; margin-top: 20px; }

@media (max-width: 960px) {
  .alert-page-head { flex-direction: column; }
  .filter-bar { flex-wrap: wrap; }
}
</style>
