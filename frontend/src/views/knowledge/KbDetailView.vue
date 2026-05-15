<template>
  <section v-if="kb" class="kb-detail">
    <a-button type="link" class="back-btn" @click="router.push('/knowledge')">
      <template #icon><ArrowLeftOutlined /></template>
      返回知识库列表
    </a-button>

    <!-- KB 头部信息 -->
    <section class="hero-card">
      <div class="hero-main">
        <div class="hero-icon"><DatabaseOutlined /></div>
        <div class="hero-body">
          <div class="hero-title-row">
            <h2 class="hero-title">{{ kb.name }}</h2>
            <span :class="['status-pill', `status-pill--${kb.status}`]">
              {{ statusLabel[kb.status] || kb.status }}
            </span>
          </div>
          <div class="hero-meta">
            <span><code>{{ kb.code }}</code></span>
            <span>embedding: {{ kb.embedding_model }}</span>
            <span>chunk: {{ kb.chunk_method }}</span>
            <span v-if="kb.ragflow_dataset_id" class="hero-meta-dim">
              dataset: {{ kb.ragflow_dataset_id.slice(0, 8) }}...
            </span>
          </div>
          <p v-if="kb.description" class="hero-desc">{{ kb.description }}</p>
        </div>
      </div>
      <div class="hero-stats">
        <div class="stat">
          <div class="stat-value">{{ kb.doc_count }}</div>
          <div class="stat-label">文档</div>
        </div>
        <div class="stat">
          <div class="stat-value">{{ kb.chunk_count }}</div>
          <div class="stat-label">chunks</div>
        </div>
        <div class="stat">
          <div class="stat-value">{{ kb.last_synced_at ? formatMs(kb.last_synced_at) : "-" }}</div>
          <div class="stat-label">最后同步</div>
        </div>
      </div>
      <div class="hero-actions">
        <a-button v-if="canEdit" type="primary" @click="goImport">
          <template #icon><PlusOutlined /></template>
          上传文档
        </a-button>
        <a-button @click="openRetrieve">
          <template #icon><SearchOutlined /></template>
          检索测试
        </a-button>
        <a-popconfirm v-if="canEdit" title="确定删除该知识库？关联文档与 RAGFlow Dataset 一并删除。" @confirm="onDelete">
          <a-button danger>删除</a-button>
        </a-popconfirm>
      </div>
    </section>

    <!-- 文档列表 -->
    <section class="docs-card">
      <div class="docs-head">
        <div>
          <h3 class="docs-title">文档</h3>
          <p class="docs-sub">{{ docTotal }} 篇文档，状态由后台每 30 秒回拉一次</p>
        </div>
        <div class="docs-tools">
          <a-input-search
            v-model:value="docKeyword"
            placeholder="搜索文档名称"
            allow-clear
            class="doc-search"
            @search="loadDocs"
          />
          <a-select
            v-model:value="docStatusFilter"
            placeholder="解析状态"
            allow-clear
            :options="parseStatusOptions"
            class="doc-status-select"
            @change="loadDocs"
          />
          <a-button
            v-if="canEdit && selectedDocIds.length"
            danger
            @click="onBatchDelete"
          >
            批量删除 ({{ selectedDocIds.length }})
          </a-button>
        </div>
      </div>

      <a-table
        :columns="docColumns"
        :data-source="docs"
        :loading="docsLoading"
        :pagination="false"
        row-key="id"
        size="middle"
        :row-selection="canEdit ? { selectedRowKeys: selectedDocIds, onChange: onSelectChange } : undefined"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a class="doc-name" @click.prevent="openDocDetail(record)">{{ record.name }}</a>
          </template>
          <template v-else-if="column.key === 'parse_status'">
            <template v-if="record.parse_status === 'parsing'">
              <a-tooltip :title="record.parse_progress_msg || '正在解析'">
                <div class="parse-progress">
                  <a-progress
                    :percent="parsePercent(record)"
                    size="small"
                    status="active"
                    :show-info="true"
                  />
                  <div class="parse-meta">已耗时 {{ elapsedLabel(record) }}</div>
                </div>
              </a-tooltip>
            </template>
            <template v-else>
              <span :class="['parse-pill', `parse-pill--${record.parse_status}`]">
                {{ parseStatusLabel[record.parse_status] || record.parse_status }}
              </span>
              <span
                v-if="record.parse_status === 'done' && record.parse_duration_sec"
                class="parse-meta"
              >
                耗时 {{ formatDuration(record.parse_duration_sec) }}
              </span>
              <span
                v-if="record.parse_status === 'error' && record.error_message"
                class="err-msg"
              >
                {{ record.error_message }}
              </span>
            </template>
          </template>
          <template v-else-if="column.key === 'size_bytes'">
            {{ humanSize(record.size_bytes) }}
          </template>
          <template v-else-if="column.key === 'update_time'">
            {{ formatMs(record.update_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-button type="link" size="small" @click="previewDoc(record)">预览</a-button>
            <a-button
              type="link"
              size="small"
              :href="docDownloadUrl(record.id, false)"
              :download="record.name"
            >
              下载
            </a-button>
            <a-dropdown :trigger="['click']">
              <a-button type="link" size="small">
                更多
                <DownOutlined />
              </a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item @click="openDocDetail(record)">详情</a-menu-item>
                  <a-menu-item
                    v-if="canPublish"
                    :disabled="record.parse_status === 'parsing'"
                    @click="onReparse(record)"
                  >
                    重新解析
                  </a-menu-item>
                  <a-menu-divider v-if="canEdit" />
                  <a-menu-item v-if="canEdit" danger @click="confirmDelete(record)">
                    删除
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </template>
      </a-table>

      <div v-if="docTotal > docPageSize" class="docs-pagination">
        <a-pagination
          v-model:current="docPageNo"
          :page-size="docPageSize"
          :total="docTotal"
          :show-total="(t: number) => `共 ${t} 条`"
          @change="loadDocs"
        />
      </div>
    </section>

    <!-- 文档详情 drawer -->
    <a-drawer
      v-model:open="docDrawerOpen"
      width="720"
      :title="activeDoc?.name ?? '文档详情'"
      destroy-on-close
    >
      <template #extra>
        <a-space v-if="activeDoc">
          <a-button size="small" @click="previewDoc(activeDoc)">预览</a-button>
          <a-button
            size="small"
            type="primary"
            :href="docDownloadUrl(activeDoc.id, false)"
            :download="activeDoc.name"
          >
            下载原文件
          </a-button>
        </a-space>
      </template>
      <template v-if="activeDoc">
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item label="引用码" :span="2">
            <a-typography-text
              code
              :copyable="{ text: activeDoc.ref, tooltip: '复制引用码' }"
            >
              {{ activeDoc.ref }}
            </a-typography-text>
            <span class="ref-hint">用于在 RAG 应用回答中引用该文档</span>
          </a-descriptions-item>
          <a-descriptions-item label="格式">{{ activeDoc.format }}</a-descriptions-item>
          <a-descriptions-item label="大小">{{ humanSize(activeDoc.size_bytes) }}</a-descriptions-item>
          <a-descriptions-item label="解析状态">
            <span :class="['parse-pill', `parse-pill--${activeDoc.parse_status}`]">
              {{ parseStatusLabel[activeDoc.parse_status] || activeDoc.parse_status }}
            </span>
          </a-descriptions-item>
          <a-descriptions-item label="chunks">{{ activeDoc.chunks_count }}</a-descriptions-item>
          <a-descriptions-item label="来源">{{ activeDoc.source_type }}</a-descriptions-item>
          <a-descriptions-item label="分类">{{ activeDoc.category || "-" }}</a-descriptions-item>
          <a-descriptions-item label="更新时间" :span="2">
            {{ formatMs(activeDoc.update_time) }}
          </a-descriptions-item>
          <a-descriptions-item v-if="activeDoc.error_message" label="错误信息" :span="2">
            <span class="err-msg">{{ activeDoc.error_message }}</span>
          </a-descriptions-item>
        </a-descriptions>

        <h4 class="drawer-section-title">
          chunks 预览
          <span class="drawer-sub">（RAGFlow 实时拉取，共 {{ chunkTotal }} 个）</span>
        </h4>
        <a-spin :spinning="chunksLoading">
          <a-empty
            v-if="!chunks.length && !chunksLoading"
            description="该文档尚未生成 chunks（可能仍在解析中或解析失败）"
          />
          <div v-else class="chunk-list">
            <div v-for="(c, i) in chunks" :key="c.id" class="chunk-item">
              <div class="chunk-no">#{{ (chunkPageNo - 1) * chunkPageSize + i + 1 }}</div>
              <div class="chunk-body">{{ c.content }}</div>
            </div>
          </div>
          <div v-if="chunkTotal > chunkPageSize" class="chunk-pagination">
            <a-pagination
              v-model:current="chunkPageNo"
              :page-size="chunkPageSize"
              :total="chunkTotal"
              size="small"
              @change="loadChunks"
            />
          </div>
        </a-spin>
      </template>
    </a-drawer>

    <!-- 检索测试 drawer -->
    <a-drawer v-model:open="retrieveDrawerOpen" width="640" title="检索测试" destroy-on-close>
      <a-form layout="vertical">
        <a-form-item label="问题">
          <a-textarea
            v-model:value="retrieveQuestion"
            :rows="3"
            placeholder="输入要在该知识库中搜索的问题..."
          />
        </a-form-item>
        <a-form-item label="Top K">
          <a-input-number v-model:value="retrieveTopK" :min="1" :max="32" />
        </a-form-item>
        <a-form-item label="相似度阈值">
          <a-slider
            v-model:value="retrieveThreshold"
            :min="0"
            :max="1"
            :step="0.05"
          />
        </a-form-item>
        <a-button
          type="primary"
          block
          :loading="retrieving"
          :disabled="!retrieveQuestion.trim()"
          @click="onRetrieve"
        >
          检索
        </a-button>
      </a-form>

      <h4 class="drawer-section-title">命中结果（{{ retrieveHits.length }}）</h4>
      <a-empty v-if="!retrieveHits.length && !retrieving" description="尚未检索" />
      <div v-else class="hit-list">
        <div v-for="(hit, i) in retrieveHits" :key="hit.chunk_id" class="hit-item">
          <div class="hit-head">
            <span class="hit-no">#{{ i + 1 }}</span>
            <span v-if="hit.similarity != null" class="hit-similarity">
              相似度 {{ (hit.similarity * 100).toFixed(1) }}%
            </span>
            <span v-if="hit.doc_name" class="hit-doc">来源: {{ hit.doc_name }}</span>
          </div>
          <div class="hit-body">{{ hit.content }}</div>
        </div>
      </div>
    </a-drawer>
  </section>
  <a-spin v-else class="kb-loading" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  DownOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import { Modal, message } from "ant-design-vue";
import * as kbApi from "@/api/kb";
import type {
  KbChunkResp,
  KbDocumentResp,
  KbResp,
  KbRetrieveHit,
} from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.KB_EDIT));
const canPublish = computed(() => auth.hasPermission(PERM.KB_PUBLISH));

const kbId = computed(() => String(route.params.id));
const kb = ref<KbResp | null>(null);

const statusLabel: Record<string, string> = {
  draft: "草稿",
  ready: "已就绪",
  syncing: "同步中",
  error: "异常",
};
const parseStatusLabel: Record<string, string> = {
  pending: "待解析",
  parsing: "解析中",
  done: "已完成",
  error: "失败",
  cancelled: "已取消",
};
const parseStatusOptions = Object.entries(parseStatusLabel).map(([value, label]) => ({
  value,
  label,
}));

const docColumns = [
  { title: "文档名称", dataIndex: "name", key: "name" },
  { title: "格式", dataIndex: "format", key: "format", width: 80 },
  { title: "大小", dataIndex: "size_bytes", key: "size_bytes", width: 100 },
  { title: "解析状态", dataIndex: "parse_status", key: "parse_status", width: 180 },
  { title: "chunks", dataIndex: "chunks_count", key: "chunks_count", width: 80 },
  { title: "更新时间", dataIndex: "update_time", key: "update_time", width: 160 },
  { title: "操作", key: "action", width: 200 },
];

// ── KB 数据 ──
async function loadKb() {
  const { data } = await kbApi.getKb(kbId.value);
  kb.value = data.data;
}


async function onDelete() {
  await kbApi.deleteKb(kbId.value);
  message.success("已删除");
  router.push("/knowledge");
}

function goImport() {
  router.push(`/knowledge/import/${kbId.value}`);
}

// ── 文档列表 + 轮询 ──
const docs = ref<KbDocumentResp[]>([]);
const docTotal = ref(0);
const docsLoading = ref(false);
const docPageNo = ref(1);
const docPageSize = ref(20);
const docKeyword = ref("");
const docStatusFilter = ref<string | undefined>(undefined);
const selectedDocIds = ref<string[]>([]);

let pollTimer: ReturnType<typeof setInterval> | null = null;

async function loadDocs(showSpin = true) {
  if (showSpin) docsLoading.value = true;
  try {
    const { data } = await kbApi.pageKbDocuments(kbId.value, {
      page_no: docPageNo.value,
      page_size: docPageSize.value,
      keyword: docKeyword.value || undefined,
      parse_status: docStatusFilter.value,
    });
    docs.value = data.data;
    docTotal.value = data.total;
  } finally {
    if (showSpin) docsLoading.value = false;
  }
}

function ensurePollingForParsing() {
  const hasParsing = docs.value.some(
    (d) => d.parse_status === "parsing" || d.parse_status === "pending",
  );
  if (hasParsing && !pollTimer) {
    pollTimer = setInterval(() => loadDocs(false), 5000);
  } else if (!hasParsing && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  // 解析中开"已耗时"全局秒级 tick;无解析行时停掉避免 idle 渲染
  if (hasParsing && !elapsedTimer) {
    elapsedTimer = setInterval(() => {
      nowMs.value = Date.now();
    }, 1000);
  } else if (!hasParsing && elapsedTimer) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
}

watch(docs, ensurePollingForParsing, { deep: true });
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (elapsedTimer) clearInterval(elapsedTimer);
});

const nowMs = ref(Date.now());
let elapsedTimer: ReturnType<typeof setInterval> | null = null;

function parsePercent(d: KbDocumentResp): number {
  // ant Progress 期望整数 0-100
  const p = d.parse_progress ?? 0;
  return Math.max(0, Math.min(100, Math.round(p * 100)));
}

function elapsedLabel(d: KbDocumentResp): string {
  // 首选 parse_begin_at;没有则退回 create_time(刚上传通常一致)
  const begin = d.parse_begin_at || d.create_time;
  const sec = Math.max(0, Math.floor((nowMs.value - begin) / 1000));
  return formatDuration(sec);
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  if (m < 60) return `${m}m${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h${(m % 60).toString().padStart(2, "0")}m`;
}

function onSelectChange(keys: (string | number)[]) {
  selectedDocIds.value = keys.map(String);
}

async function onBatchDelete() {
  await kbApi.deleteKbDocuments(kbId.value, selectedDocIds.value);
  message.success(`已删除 ${selectedDocIds.value.length} 篇`);
  selectedDocIds.value = [];
  await loadDocs();
}

async function onDeleteOne(record: KbDocumentResp) {
  await kbApi.deleteKbDocuments(kbId.value, [record.id]);
  message.success("已删除");
  await loadDocs();
}

async function onReparse(record: KbDocumentResp) {
  await kbApi.reparseKbDocument(kbId.value, record.id);
  message.success("已触发重新解析");
  await loadDocs();
}

// ── 文档详情 + chunks ──
const docDrawerOpen = ref(false);
const activeDoc = ref<KbDocumentResp | null>(null);
const chunks = ref<KbChunkResp[]>([]);
const chunkTotal = ref(0);
const chunksLoading = ref(false);
const chunkPageNo = ref(1);
const chunkPageSize = ref(20);

function docDownloadUrl(docId: string, inline: boolean): string {
  // 同源, 走 vite proxy 到 backend; 浏览器自动带 cookie 鉴权
  const base = `/api/v1/kb/${kbId.value}/document/${docId}/download`;
  return inline ? `${base}?inline=true` : base;
}

function previewDoc(record: KbDocumentResp) {
  // 跳独立预览路由,顶部带导航条 + 下载按钮,markdown 渲染,PDF iframe
  router.push(`/knowledge/${kbId.value}/document/${record.id}/preview`);
}

// menu-item 不能直接嵌 popconfirm, 用 Modal.confirm 做删除二次确认
function confirmDelete(record: KbDocumentResp) {
  Modal.confirm({
    title: "确定删除该文档?",
    content: `${record.name} 将从知识库与 RAGFlow 同步删除,且无法撤销。`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    onOk: () => onDeleteOne(record),
  });
}

async function openDocDetail(record: KbDocumentResp) {
  activeDoc.value = record;
  docDrawerOpen.value = true;
  // 拉最新详情
  try {
    const { data } = await kbApi.getKbDocument(kbId.value, record.id);
    activeDoc.value = data.data;
  } catch {
    /* 上游不可达时显示本地缓存 */
  }
  chunkPageNo.value = 1;
  await loadChunks();
}

async function loadChunks() {
  if (!activeDoc.value) return;
  chunksLoading.value = true;
  try {
    const { data } = await kbApi.listKbDocumentChunks(kbId.value, activeDoc.value.id, {
      page_no: chunkPageNo.value,
      page_size: chunkPageSize.value,
    });
    chunks.value = data.data;
    chunkTotal.value = data.total;
  } catch {
    chunks.value = [];
    chunkTotal.value = 0;
  } finally {
    chunksLoading.value = false;
  }
}

// ── 检索测试 ──
const retrieveDrawerOpen = ref(false);
const retrieveQuestion = ref("");
const retrieveTopK = ref(8);
const retrieveThreshold = ref(0.2);
const retrieving = ref(false);
const retrieveHits = ref<KbRetrieveHit[]>([]);

function openRetrieve() {
  retrieveDrawerOpen.value = true;
}

async function onRetrieve() {
  if (!retrieveQuestion.value.trim()) return;
  retrieving.value = true;
  try {
    const { data } = await kbApi.retrieveKb({
      kb_ids: [kbId.value],
      question: retrieveQuestion.value.trim(),
      top_k: retrieveTopK.value,
      similarity_threshold: retrieveThreshold.value,
    });
    retrieveHits.value = data.data.hits;
    if (!data.data.hits.length) message.info("没有命中 chunks，可降低相似度阈值再试");
  } finally {
    retrieving.value = false;
  }
}

// ── 辅助 ──
function humanSize(n: number | null | undefined): string {
  if (!n) return "-";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

onMounted(async () => {
  await loadKb();
  await loadDocs();
});
</script>

<style scoped>
.kb-detail {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.kb-loading {
  display: flex;
  justify-content: center;
  padding-top: 80px;
}
.back-btn {
  align-self: flex-start;
}

/* hero */
.hero-card {
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 20px 24px;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  gap: 20px;
}
.hero-main {
  display: flex;
  gap: 16px;
}
.hero-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--surface-info-soft);
  color: var(--color-info-strong);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}
.hero-body {
  flex: 1;
  min-width: 0;
}
.hero-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hero-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
}
.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 6px;
}
.hero-meta-dim {
  color: var(--color-text-tertiary);
}
.hero-desc {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.hero-stats {
  display: flex;
  gap: 18px;
  align-self: center;
}
.stat {
  text-align: center;
  min-width: 90px;
}
.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}
.stat-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
}
.hero-actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  border-top: 1px solid var(--color-border);
  padding-top: 14px;
}

/* status pills */
.status-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-neutral-bg);
  color: var(--color-text-tertiary);
}
.status-pill--ready {
  background: var(--color-success-bg, #e6f7e6);
  color: var(--color-success-strong, #2c8a2c);
}
.status-pill--syncing {
  background: var(--color-warning-bg, #fff7e6);
  color: var(--color-warning-strong, #c98a00);
}
.status-pill--error {
  background: var(--color-danger-bg, #ffeaea);
  color: var(--color-danger-strong, #d23030);
}
.parse-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-neutral-bg);
  color: var(--color-text-tertiary);
}
.parse-pill--parsing {
  background: var(--color-info-bg, #e6f1ff);
  color: var(--color-info-strong);
}
.parse-pill--done {
  background: var(--color-success-bg, #e6f7e6);
  color: var(--color-success-strong, #2c8a2c);
}
.parse-pill--error {
  background: var(--color-danger-bg, #ffeaea);
  color: var(--color-danger-strong, #d23030);
}
.parse-pill--cancelled {
  background: var(--surface-soft);
  color: var(--color-text-tertiary);
}
.err-msg {
  display: block;
  font-size: 11px;
  color: var(--color-danger-strong, #d23030);
  margin-top: 2px;
}
.parse-progress {
  min-width: 140px;
  max-width: 200px;
}
.parse-progress :deep(.ant-progress-text) {
  font-size: 11px;
}
.parse-meta {
  display: block;
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.ref-hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

/* docs */
.docs-card {
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 18px 20px;
}
.docs-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  gap: 14px;
  flex-wrap: wrap;
}
.docs-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.docs-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.docs-tools {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.doc-search {
  width: 240px;
}
.doc-status-select {
  width: 140px;
}
.doc-name {
  font-weight: 500;
  color: var(--color-info-strong);
  cursor: pointer;
}
.docs-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

/* drawer chunks */
.drawer-section-title {
  margin: 24px 0 12px;
  font-size: 14px;
  font-weight: 700;
}
.drawer-sub {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}
.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chunk-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  background: var(--surface-soft);
  border-radius: 10px;
}
.chunk-no {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono, monospace);
  flex-shrink: 0;
  padding-top: 2px;
}
.chunk-body {
  font-size: 12px;
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
.chunk-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

/* retrieve drawer */
.hit-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hit-item {
  padding: 12px 14px;
  border-radius: 10px;
  background: var(--surface-soft);
  border: 1px solid var(--color-border);
}
.hit-head {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}
.hit-no {
  font-weight: 700;
  color: var(--color-info-strong);
}
.hit-similarity {
  font-family: var(--font-mono, monospace);
}
.hit-doc {
  margin-left: auto;
}
.hit-body {
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  color: var(--color-text);
}
</style>
