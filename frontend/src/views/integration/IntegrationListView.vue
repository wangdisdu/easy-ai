<template>
  <div class="intg-page">
    <div class="intg-toolbar">
      <div class="intg-toolbar__left">
        <a-input-search
          v-model:value="keyword"
          placeholder="搜索集成名称或描述"
          allow-clear
          class="intg-search"
          @search="onSearch"
        />
        <a-radio-group v-model:value="statusFilter" button-style="solid" @change="onSearch">
          <a-radio-button value="">全部</a-radio-button>
          <a-radio-button value="active">运行中</a-radio-button>
          <a-radio-button value="disabled">已停用</a-radio-button>
        </a-radio-group>
      </div>
      <a-button type="primary" @click="goCreate">创建集成应用</a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="pagination"
      :expanded-row-keys="expandedKeys"
      row-key="id"
      size="middle"
      class="intg-table"
      @change="onTableChange"
      @expand="onExpandToggle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="intg-name">
            <span class="intg-name__text">{{ record.name }}</span>
            <span class="intg-muted">{{ record.description || "暂无描述" }}</span>
          </div>
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="record.status === 'active' ? 'green' : 'default'">
            {{ record.status === "active" ? "运行中" : "已停用" }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'bound_apps'">
          <span>{{ record.bound_apps.length }}</span>
        </template>
        <template v-else-if="column.key === 'limits'">
          <div class="intg-pills">
            <span class="intg-pill" :title="quotaTitle(record.quota)">
              配额 {{ formatLimit(record.quota) }}
            </span>
            <span class="intg-pill">限流 {{ formatLimit(record.rate_limit) }} /分钟</span>
          </div>
        </template>
        <template v-else-if="column.key === 'expire_at'">
          <span :class="{ 'intg-muted': !record.expire_at }">
            {{ record.expire_at ? formatDate(record.expire_at) : "永不过期" }}
          </span>
        </template>
        <template v-else-if="column.key === 'create_time'">
          {{ formatDateTime(record.create_time) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" size="small" @click="goEdit(record)">编辑</a-button>
          <a-button type="link" size="small" @click="toggleStatus(record)">
            {{ record.status === "active" ? "停用" : "启用" }}
          </a-button>
          <a-popconfirm
            title="确认删除该集成应用?此操作不可恢复。"
            ok-text="删除"
            ok-type="danger"
            @confirm="onDelete(record)"
          >
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>

      <template #expandedRowRender="{ record }">
        <div class="intg-detail">
          <div class="intg-detail__col">
            <div class="intg-detail__title">
              <span>API Key</span>
              <a-button type="primary" size="small" @click="onCreateKey(record)">
                生成新 Key
              </a-button>
            </div>
            <a-empty
              v-if="record.keys.length === 0"
              description="暂无 API Key"
              :image="undefined"
            />
            <div v-for="k in record.keys" :key="k.id" class="intg-key-row">
              <code class="intg-key-row__value">{{ k.masked }}</code>
              <a-tag :color="k.status === 'active' ? 'green' : 'default'">
                {{ k.status === "active" ? "有效" : "已禁用" }}
              </a-tag>
              <span class="intg-muted">
                限流 {{ k.rate_limit === null ? "默认" : `${k.rate_limit}/分钟` }}
              </span>
              <span class="intg-key-row__spacer" />
              <a-button type="link" size="small" @click="openEditKey(record, k)">修改</a-button>
              <a-button type="link" size="small" @click="toggleKeyStatus(record, k)">
                {{ k.status === "active" ? "停用" : "启用" }}
              </a-button>
              <a-popconfirm
                title="重置后旧 Key 将立即失效,请确认。"
                ok-text="重置"
                ok-type="danger"
                @confirm="onResetKey(record, k)"
              >
                <a-button type="link" size="small" danger>重置</a-button>
              </a-popconfirm>
              <a-popconfirm
                title="确认删除该 API Key?"
                ok-text="删除"
                ok-type="danger"
                @confirm="onDeleteKey(record, k)"
              >
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </div>
          </div>

          <div class="intg-detail__col">
            <div class="intg-detail__title">绑定应用 ({{ record.bound_apps.length }})</div>
            <a-empty
              v-if="record.bound_apps.length === 0"
              description="未绑定应用"
              :image="undefined"
            />
            <div v-for="b in record.bound_apps" :key="`${b.app_type}-${b.app_id}`" class="intg-bind-row">
              <a-tag :color="APP_TYPE_COLOR[b.app_type] ?? 'default'">
                {{ APP_TYPE_LABEL[b.app_type] ?? b.app_type }}
              </a-tag>
              <span>{{ resolveAppName(b) }}</span>
            </div>
          </div>
        </div>
      </template>
    </a-table>

    <!-- 修改 Key 限流 -->
    <a-modal
      v-model:open="keyEditOpen"
      title="修改 API Key 配置"
      :confirm-loading="keyEditSubmitting"
      destroy-on-close
      @ok="submitKeyEdit"
    >
      <a-form layout="vertical">
        <a-form-item label="每分钟最大请求次数">
          <a-input-number
            v-model:value="keyEditModel.rate_limit"
            :min="1"
            :max="100000"
            :disabled="keyEditModel.inherit"
            placeholder="1-100000"
            style="width: 100%"
          />
          <a-checkbox
            v-model:checked="keyEditModel.inherit"
            class="intg-form-checkbox"
          >
            使用全局默认(等同 Integration 级)
          </a-checkbox>
        </a-form-item>
        <a-form-item label="状态">
          <a-radio-group v-model:value="keyEditModel.status">
            <a-radio value="active">启用</a-radio>
            <a-radio value="disabled">停用</a-radio>
          </a-radio-group>
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 明文 Key 展示弹窗(创建/重置时使用) -->
    <a-modal
      v-model:open="plainOpen"
      :title="plainTitle"
      :footer="null"
      :mask-closable="false"
      width="540px"
    >
      <a-alert
        type="warning"
        show-icon
        message="请立即保存此 Key,关闭后将无法再次查看完整内容。"
        class="intg-plain-alert"
      />
      <div class="intg-plain-box">
        <code>{{ plainKey }}</code>
        <a-button size="small" @click="copyPlain">复制</a-button>
      </div>
      <div class="intg-plain-footer">
        <a-button type="primary" @click="plainOpen = false">我已保存</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import * as api from "@/api/integration";
import { pageApp } from "@/api/app";
import type { AppResp, IntegrationKeyResp, IntegrationResp } from "@/api/types";

const router = useRouter();

const APP_TYPE_LABEL: Record<string, string> = {
  agent: "智能体",
  llm: "对话",
  rag: "知识库",
};
const APP_TYPE_COLOR: Record<string, string> = {
  agent: "blue",
  llm: "purple",
  rag: "cyan",
};

const columns = [
  { title: "名称", key: "name", dataIndex: "name" },
  { title: "状态", key: "status", dataIndex: "status", width: 100 },
  { title: "绑定应用", key: "bound_apps", width: 110 },
  { title: "配额 / 限流", key: "limits", width: 230 },
  { title: "过期时间", key: "expire_at", width: 150 },
  { title: "创建时间", key: "create_time", width: 170 },
  { title: "操作", key: "action", width: 200 },
];

const keyword = ref("");
const statusFilter = ref<"" | "active" | "disabled">("");
const list = ref<IntegrationResp[]>([]);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const expandedKeys = ref<string[]>([]);
const appNameCache = ref<Record<string, string>>({});

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
});

// 修改 Key 弹窗状态
const keyEditOpen = ref(false);
const keyEditSubmitting = ref(false);
const keyEditCtx = ref<{ intg_id: string; key_id: string } | null>(null);
const keyEditModel = reactive<{
  rate_limit: number | null;
  inherit: boolean;
  status: "active" | "disabled";
}>({ rate_limit: null, inherit: false, status: "active" });

// 明文 Key 弹窗
const plainOpen = ref(false);
const plainTitle = ref("API Key 已生成");
const plainKey = ref("");

async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.pageIntegration({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      status: statusFilter.value || undefined,
    });
    list.value = data.data;
    pagination.current = pageNo.value;
    pagination.pageSize = pageSize.value;
    pagination.total = data.total;
    // 异步预取绑定应用名,失败不影响列表
    void prefetchAppNames(data.data);
  } finally {
    loading.value = false;
  }
}

async function prefetchAppNames(items: IntegrationResp[]) {
  const missing = new Set<string>();
  for (const intg of items) {
    for (const b of intg.bound_apps) {
      const k = `${b.app_type}:${b.app_id}`;
      if (!appNameCache.value[k]) missing.add(k);
    }
  }
  if (missing.size === 0) return;
  // 简化:一次拉全部 published 应用(P0 数量级有限);后续再优化为按 id 批量
  try {
    const { data } = await pageApp({ page_no: 1, page_size: 1000 });
    const updates: Record<string, string> = {};
    for (const app of data.data as AppResp[]) {
      updates[`${app.app_type}:${app.id}`] = app.name;
    }
    appNameCache.value = { ...appNameCache.value, ...updates };
  } catch {
    // 静默失败:展示原始 id
  }
}

function resolveAppName(b: { app_type: string; app_id: string }) {
  return appNameCache.value[`${b.app_type}:${b.app_id}`] ?? `#${b.app_id}`;
}

function onSearch() {
  pageNo.value = 1;
  loadList();
}

function onTableChange(p: { current?: number; pageSize?: number }) {
  pageNo.value = p.current ?? 1;
  pageSize.value = p.pageSize ?? 20;
  loadList();
}

function onExpandToggle(expanded: boolean, record: IntegrationResp) {
  if (expanded) {
    expandedKeys.value = [...expandedKeys.value, record.id];
  } else {
    expandedKeys.value = expandedKeys.value.filter((k) => k !== record.id);
  }
}

function goCreate() {
  router.push({ name: "integration-create" });
}

function goEdit(record: IntegrationResp) {
  router.push({ name: "integration-edit", params: { id: record.id } });
}

async function toggleStatus(record: IntegrationResp) {
  const next = record.status === "active" ? "disabled" : "active";
  await api.setIntegrationStatus(record.id, next);
  message.success(next === "active" ? "已启用" : "已停用");
  await loadList();
}

async function onDelete(record: IntegrationResp) {
  await api.deleteIntegration(record.id);
  message.success("已删除");
  await loadList();
}

async function onCreateKey(record: IntegrationResp) {
  const { data } = await api.createIntegrationKey(record.id);
  showPlain("API Key 已生成", data.data.plaintext);
  await loadList();
}

async function onResetKey(record: IntegrationResp, k: IntegrationKeyResp) {
  const { data } = await api.resetIntegrationKey(record.id, k.id);
  showPlain("API Key 已重置", data.data.plaintext);
  await loadList();
}

async function onDeleteKey(record: IntegrationResp, k: IntegrationKeyResp) {
  await api.deleteIntegrationKey(record.id, k.id);
  message.success("Key 已删除");
  await loadList();
}

async function toggleKeyStatus(record: IntegrationResp, k: IntegrationKeyResp) {
  const next = k.status === "active" ? "disabled" : "active";
  await api.updateIntegrationKey(record.id, k.id, { status: next });
  message.success(next === "active" ? "已启用" : "已停用");
  await loadList();
}

function openEditKey(record: IntegrationResp, k: IntegrationKeyResp) {
  keyEditCtx.value = { intg_id: record.id, key_id: k.id };
  keyEditModel.rate_limit = k.rate_limit;
  keyEditModel.inherit = k.rate_limit === null;
  keyEditModel.status = k.status === "active" ? "active" : "disabled";
  keyEditOpen.value = true;
}

async function submitKeyEdit() {
  const ctx = keyEditCtx.value;
  if (!ctx) return;
  keyEditSubmitting.value = true;
  try {
    await api.updateIntegrationKey(ctx.intg_id, ctx.key_id, {
      rate_limit_inherit: keyEditModel.inherit,
      rate_limit: keyEditModel.inherit ? null : keyEditModel.rate_limit,
      status: keyEditModel.status,
    });
    message.success("已更新");
    keyEditOpen.value = false;
    await loadList();
  } finally {
    keyEditSubmitting.value = false;
  }
}

function showPlain(title: string, plaintext: string) {
  plainTitle.value = title;
  plainKey.value = plaintext;
  plainOpen.value = true;
}

async function copyPlain() {
  try {
    await navigator.clipboard.writeText(plainKey.value);
    message.success("已复制到剪贴板");
  } catch {
    message.error("复制失败,请手动选择文本");
  }
}

function formatLimit(v: number | null) {
  if (v === null || v === undefined) return "默认";
  if (v === 0) return "不限";
  return String(v);
}

function quotaTitle(v: number | null) {
  if (v === null || v === undefined) return "继承全局默认";
  if (v === 0) return "显式不限额";
  return `${v} 次/天`;
}

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function formatDate(ts: number) {
  const d = new Date(ts);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatDateTime(ts: number) {
  const d = new Date(ts);
  return `${formatDate(ts)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

onMounted(loadList);
</script>

<style scoped>
.intg-page {
  min-height: 100%;
}

.intg-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.intg-toolbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.intg-search {
  width: 280px;
}

.intg-table {
  background: var(--surface-base);
}

.intg-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.intg-name__text {
  font-weight: 500;
}

.intg-muted {
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.intg-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.intg-pill {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--color-fill-quaternary, rgba(0, 0, 0, 0.04));
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.intg-detail {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 24px;
  padding: 8px 0;
}

.intg-detail__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 500;
  margin-bottom: 12px;
}

.intg-key-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--color-border-secondary, #f0f0f0);
}

.intg-key-row__value {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 13px;
}

.intg-key-row__spacer {
  flex: 1;
}

.intg-bind-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}

.intg-form-checkbox {
  display: block;
  margin-top: 8px;
}

.intg-plain-alert {
  margin-bottom: 12px;
}

.intg-plain-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--color-fill-quaternary, rgba(0, 0, 0, 0.04));
  border-radius: 4px;
}

.intg-plain-box code {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 13px;
  word-break: break-all;
}

.intg-plain-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
