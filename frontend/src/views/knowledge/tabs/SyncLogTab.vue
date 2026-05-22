<template>
  <div class="synclog-tab">
    <div class="log-toolbar">
      <a-segmented v-model:value="logType" :options="typeOptions" @change="reload" />
      <a-select
        v-model:value="statusFilter"
        placeholder="按状态筛选"
        allow-clear
        :options="statusOptions"
        class="status-filter"
        @change="reload"
      />
      <a-button :loading="loading" @click="reload">刷新</a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="logs"
      :loading="loading"
      :pagination="false"
      row-key="id"
      size="middle"
      :scroll="{ x: 880 }"
      :expand-row-by-click="true"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'time'">
          {{ formatMs(record.create_time) }}
        </template>
        <template v-else-if="column.key === 'source'">
          {{ record.source_name || record.source_type || "-" }}
        </template>
        <template v-else-if="column.key === 'counts'">
          <span class="cnt cnt--add">+{{ record.docs_added }}</span>
          <span class="cnt cnt--upd">~{{ record.docs_updated }}</span>
          <span class="cnt cnt--del">-{{ record.docs_deleted }}</span>
          <span v-if="record.chunks_created" class="cnt cnt--chunk">
            {{ record.chunks_created }} chunks
          </span>
        </template>
        <template v-else-if="column.key === 'duration'">
          {{ record.duration_ms != null ? `${(record.duration_ms / 1000).toFixed(1)}s` : "-" }}
        </template>
        <template v-else-if="column.key === 'status'">
          <span :class="['log-status', `log-status--${record.status}`]">
            {{ statusLabel[record.status] || record.status }}
          </span>
        </template>
      </template>
      <template #expandedRowRender="{ record }">
        <span class="log-detail">{{ record.detail || "无详情" }}</span>
      </template>
    </a-table>

    <div v-if="total > pageSize" class="log-pagination">
      <a-pagination
        v-model:current="pageNo"
        :page-size="pageSize"
        :total="total"
        :show-total="(t: number) => `共 ${t} 条`"
        @change="loadLogs"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import * as kbApi from "@/api/kb";
import type { SyncLogResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const typeOptions = [
  { value: "integration", label: "知识集成日志" },
  { value: "vectorization", label: "知识向量化日志" },
];
const statusOptions = [
  { value: "success", label: "成功" },
  { value: "processing", label: "进行中" },
  { value: "partial", label: "部分成功" },
  { value: "failed", label: "失败" },
];
const statusLabel: Record<string, string> = {
  success: "成功",
  processing: "进行中",
  partial: "部分成功",
  failed: "失败",
};

const logType = ref("integration");
const statusFilter = ref<string | undefined>(undefined);
const logs = ref<SyncLogResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);

const columns = computed(() => [
  { title: "时间", key: "time", width: 170 },
  { title: "来源", key: "source", width: 180 },
  { title: "文档变更", key: "counts", width: 220 },
  { title: "耗时", key: "duration", width: 90 },
  { title: "状态", key: "status", width: 100 },
]);

async function loadLogs() {
  loading.value = true;
  try {
    const { data } = await kbApi.pageSyncLogs({
      page_no: pageNo.value,
      page_size: pageSize.value,
      log_type: logType.value,
      status: statusFilter.value,
    });
    logs.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function reload() {
  pageNo.value = 1;
  loadLogs();
}

onMounted(loadLogs);
</script>

<style scoped>
.synclog-tab {
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px 18px;
}
.log-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.status-filter {
  width: 150px;
}
.cnt {
  font-size: 12px;
  font-family: var(--font-mono, monospace);
  margin-right: 10px;
}
.cnt--add {
  color: var(--color-success-strong, #2c8a2c);
}
.cnt--upd {
  color: var(--color-info-strong);
}
.cnt--del {
  color: var(--color-danger-strong, #d23030);
}
.cnt--chunk {
  color: var(--color-text-tertiary);
}
.log-status {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-neutral-bg);
  color: var(--color-text-tertiary);
}
.log-status--success {
  background: var(--color-success-bg, #e6f7e6);
  color: var(--color-success-strong, #2c8a2c);
}
.log-status--processing {
  background: var(--color-info-bg, #e6f1ff);
  color: var(--color-info-strong);
}
.log-status--partial {
  background: var(--color-warning-bg, #fff7e6);
  color: var(--color-warning-strong, #c98a00);
}
.log-status--failed {
  background: var(--color-danger-bg, #ffeaea);
  color: var(--color-danger-strong, #d23030);
}
.log-detail {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.log-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
