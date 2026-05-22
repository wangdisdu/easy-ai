<template>
  <div class="vectorize-tab">
    <!-- 左:RAG 库列表 -->
    <aside class="ds-sidebar">
      <div class="sidebar-head">
        <span class="sidebar-title">RAG 库</span>
        <span class="sidebar-count">{{ datasets.length }}</span>
        <a-button v-if="canEdit" type="link" size="small" @click="openCreate">
          <PlusOutlined /> 新建
        </a-button>
      </div>
      <a-spin :spinning="loading">
        <div class="ds-list">
          <div
            v-for="ds in datasets"
            :key="ds.id"
            :class="['ds-item', { active: selectedId === ds.id }]"
            @click="selectDataset(ds.id)"
          >
            <div class="ds-item-top">
              <span class="ds-item-name">{{ ds.name }}</span>
              <span class="ds-item-docs">{{ ds.doc_count }} 篇</span>
            </div>
            <div class="ds-item-meta">
              <span>{{ chunkMethodLabel[ds.chunk_method] || ds.chunk_method }}</span>
              <span>{{ ds.chunk_count }} chunks</span>
            </div>
          </div>
          <a-empty
            v-if="!loading && !datasets.length"
            description="尚无 RAG 库"
            :image="emptyImage"
          />
        </div>
      </a-spin>
    </aside>

    <!-- 右:详情 + 映射 + 检索 -->
    <main class="ds-main">
      <a-empty
        v-if="!selectedDataset"
        class="main-empty"
        description="请选择左侧 RAG 库,或新建一个"
      />
      <template v-else>
        <!-- 详情 -->
        <a-card size="small" class="card">
          <div class="ds-detail-head">
            <h3 class="ds-detail-name">{{ selectedDataset.name }}</h3>
            <span :class="['ds-status', `ds-status--${selectedDataset.status}`]">
              {{ dsStatusLabel[selectedDataset.status] || selectedDataset.status }}
            </span>
            <div class="ds-detail-actions">
              <a-button v-if="canPublish" size="small" @click="onSync">同步</a-button>
              <a-popconfirm
                v-if="canEdit"
                title="删除该 RAG 库?关联分类将解绑,文档原文保留在知识库。"
                @confirm="onDelete"
              >
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <a-descriptions :column="4" size="small" bordered>
            <a-descriptions-item label="Embedding" :span="2">
              <span class="mono">{{ selectedDataset.embedding_model }}</span>
            </a-descriptions-item>
            <a-descriptions-item label="分块策略">
              {{ chunkMethodLabel[selectedDataset.chunk_method] || selectedDataset.chunk_method }}
            </a-descriptions-item>
            <a-descriptions-item label="文档 / 分块">
              {{ selectedDataset.doc_count }} / {{ selectedDataset.chunk_count }}
            </a-descriptions-item>
            <a-descriptions-item label="映射分类">
              {{ selectedDataset.mapped_category_count }}
            </a-descriptions-item>
            <a-descriptions-item label="最后同步" :span="3">
              {{ selectedDataset.last_synced_at ? formatMs(selectedDataset.last_synced_at) : "-" }}
            </a-descriptions-item>
          </a-descriptions>
        </a-card>

        <!-- 映射 -->
        <a-card size="small" class="card">
          <template #title>
            映射的本地分类
            <span class="card-sub">勾选要同步到此 RAG 库的分类,文档将进入向量化队列</span>
          </template>
          <template #extra>
            <a-button
              v-if="canEdit"
              type="primary"
              size="small"
              :loading="savingMapping"
              @click="saveMapping"
            >
              保存映射
            </a-button>
          </template>
          <a-spin :spinning="mappingLoading">
            <div v-for="group in groupedCategories" :key="group.kbId" class="map-group">
              <div class="map-group-title">{{ group.kbName }}</div>
              <div class="map-grid">
                <label
                  v-for="cat in group.items"
                  :key="cat.category_id"
                  :class="[
                    'map-item',
                    {
                      'map-item--checked': checkedCatIds.includes(cat.category_id),
                      'map-item--disabled': isOccupiedByOther(cat),
                    },
                  ]"
                >
                  <a-checkbox
                    :checked="checkedCatIds.includes(cat.category_id)"
                    :disabled="isOccupiedByOther(cat) || !canEdit"
                    @change="() => toggleCat(cat.category_id)"
                  />
                  <span class="map-item-name">{{ cat.category_name }}</span>
                  <span class="map-item-docs">{{ cat.doc_count }} 篇</span>
                  <span v-if="isOccupiedByOther(cat)" class="map-item-tag">已映射到其他库</span>
                </label>
              </div>
            </div>
            <a-empty
              v-if="!mappingLoading && !groupedCategories.length"
              description="暂无本地分类,请先在「知识库」Tab 建分类"
              :image="emptyImage"
            />
          </a-spin>
        </a-card>

        <!-- 检索测试 -->
        <a-card size="small" class="card">
          <template #title>检索测试</template>
          <a-form layout="vertical">
            <a-form-item label="问题">
              <a-textarea
                v-model:value="retrieveQuestion"
                :rows="2"
                placeholder="输入要在该 RAG 库中检索的问题..."
              />
            </a-form-item>
            <div class="retrieve-params">
              <a-form-item label="Top K">
                <a-input-number v-model:value="retrieveTopK" :min="1" :max="32" />
              </a-form-item>
              <a-form-item label="相似度阈值" class="threshold-item">
                <a-slider
                  v-model:value="retrieveThreshold"
                  :min="0"
                  :max="1"
                  :step="0.05"
                />
              </a-form-item>
              <a-button
                type="primary"
                :loading="retrieving"
                :disabled="!retrieveQuestion.trim()"
                @click="onRetrieve"
              >
                检索
              </a-button>
            </div>
          </a-form>
          <div v-if="retrieveHits.length" class="hit-list">
            <div v-for="(hit, i) in retrieveHits" :key="hit.chunk_id" class="hit-item">
              <div class="hit-head">
                <span class="hit-no">#{{ i + 1 }}</span>
                <span v-if="hit.similarity != null" class="hit-sim">
                  相似度 {{ (hit.similarity * 100).toFixed(1) }}%
                </span>
                <span v-if="hit.doc_name" class="hit-doc">来源: {{ hit.doc_name }}</span>
              </div>
              <div class="hit-body">{{ hit.content }}</div>
            </div>
          </div>
          <a-empty
            v-else-if="retrieveSearched && !retrieving"
            description="没有命中,可降低相似度阈值再试"
            :image="emptyImage"
          />
        </a-card>
      </template>
    </main>

    <!-- 新建 RAG 库 -->
    <a-modal
      v-model:open="createOpen"
      title="新建 RAG 库"
      :confirm-loading="creating"
      ok-text="创建"
      destroy-on-close
      width="520px"
      @ok="onCreate"
    >
      <a-form ref="createFormRef" :model="createForm" :rules="createRules" layout="vertical">
        <a-form-item label="名称" name="name">
          <a-input v-model:value="createForm.name" placeholder="如 运维向量库" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="createForm.description" :rows="2" placeholder="可选" />
        </a-form-item>
        <a-form-item label="Embedding 模型">
          <a-input
            v-model:value="createForm.embedding_model"
            placeholder="留空则用系统默认 Embedding"
            allow-clear
          />
          <div class="form-hint">落库后不可修改,需对应 LLM 管理中已注册的 Embedding 模型</div>
        </a-form-item>
        <a-form-item label="分块策略" name="chunk_method">
          <a-select v-model:value="createForm.chunk_method" :options="chunkMethodOptions" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Empty, message } from "ant-design-vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { PlusOutlined } from "@ant-design/icons-vue";
import * as kbApi from "@/api/kb";
import type { LocalCategoryItem, RagDatasetResp, RetrieveHit } from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.KB_EDIT));
const canPublish = computed(() => auth.hasPermission(PERM.KB_PUBLISH));
const emptyImage = Empty.PRESENTED_IMAGE_SIMPLE;

const chunkMethodLabel: Record<string, string> = {
  naive: "通用语义分块",
  qa: "QA 问答对",
  manual: "按标题层级",
  book: "书籍",
  table: "表格",
  laws: "法律文档",
};
const chunkMethodOptions = Object.entries(chunkMethodLabel).map(([value, label]) => ({
  value,
  label: `${label}（${value}）`,
}));
const dsStatusLabel: Record<string, string> = {
  creating: "创建中",
  ready: "就绪",
  syncing: "同步中",
  error: "异常",
};

// ── RAG 库列表 ──
const datasets = ref<RagDatasetResp[]>([]);
const loading = ref(false);
const selectedId = ref<string | null>(null);
const selectedDataset = computed(
  () => datasets.value.find((d) => d.id === selectedId.value) ?? null,
);

async function loadDatasets() {
  loading.value = true;
  try {
    const { data } = await kbApi.pageRagDatasets({ page_no: 1, page_size: 1000 });
    datasets.value = data.data;
    if (selectedId.value && !datasets.value.some((d) => d.id === selectedId.value)) {
      selectedId.value = null;
    }
  } finally {
    loading.value = false;
  }
}

async function selectDataset(id: string) {
  selectedId.value = id;
  retrieveHits.value = [];
  retrieveSearched.value = false;
  await loadMapping();
}

// ── 映射 ──
const localCategories = ref<LocalCategoryItem[]>([]);
const checkedCatIds = ref<string[]>([]);
const mappingLoading = ref(false);
const savingMapping = ref(false);

const groupedCategories = computed(() => {
  const map = new Map<string, { kbId: string; kbName: string; items: LocalCategoryItem[] }>();
  for (const c of localCategories.value) {
    if (!map.has(c.kb_id)) {
      map.set(c.kb_id, { kbId: c.kb_id, kbName: c.kb_name, items: [] });
    }
    map.get(c.kb_id)!.items.push(c);
  }
  return [...map.values()];
});

function isOccupiedByOther(cat: LocalCategoryItem): boolean {
  return !!cat.mapped_dataset_id && cat.mapped_dataset_id !== selectedId.value;
}

function toggleCat(catId: string) {
  const i = checkedCatIds.value.indexOf(catId);
  if (i >= 0) checkedCatIds.value.splice(i, 1);
  else checkedCatIds.value.push(catId);
}

async function loadMapping() {
  mappingLoading.value = true;
  try {
    const { data } = await kbApi.listLocalCategories();
    localCategories.value = data.data;
    checkedCatIds.value = data.data
      .filter((c) => c.mapped_dataset_id === selectedId.value)
      .map((c) => c.category_id);
  } finally {
    mappingLoading.value = false;
  }
}

async function saveMapping() {
  if (!selectedId.value) return;
  savingMapping.value = true;
  try {
    await kbApi.setRagDatasetMapping(selectedId.value, checkedCatIds.value);
    message.success("映射已保存,相关文档进入向量化队列");
    await Promise.all([loadMapping(), loadDatasets()]);
  } finally {
    savingMapping.value = false;
  }
}

// ── 同步 / 删除 ──
async function onSync() {
  if (!selectedId.value) return;
  const { data } = await kbApi.syncRagDataset(selectedId.value);
  message.success(`已重新提交 ${data.data} 篇文档向量化`);
  await loadDatasets();
}

async function onDelete() {
  if (!selectedId.value) return;
  await kbApi.deleteRagDataset(selectedId.value);
  message.success("RAG 库已删除");
  selectedId.value = null;
  await loadDatasets();
}

// ── 检索测试 ──
const retrieveQuestion = ref("");
const retrieveTopK = ref(8);
const retrieveThreshold = ref(0.2);
const retrieving = ref(false);
const retrieveSearched = ref(false);
const retrieveHits = ref<RetrieveHit[]>([]);

async function onRetrieve() {
  if (!selectedId.value || !retrieveQuestion.value.trim()) return;
  retrieving.value = true;
  try {
    const { data } = await kbApi.retrieveRag({
      dataset_ids: [selectedId.value],
      question: retrieveQuestion.value.trim(),
      top_k: retrieveTopK.value,
      similarity_threshold: retrieveThreshold.value,
    });
    retrieveHits.value = data.data.hits;
    retrieveSearched.value = true;
  } finally {
    retrieving.value = false;
  }
}

// ── 新建 RAG 库 ──
const createOpen = ref(false);
const creating = ref(false);
const createFormRef = ref<FormInstance>();
const createForm = reactive({
  name: "",
  description: "",
  embedding_model: "",
  chunk_method: "naive",
});
const createRules: Record<string, Rule[]> = {
  name: [{ required: true, message: "请输入名称" }],
  chunk_method: [{ required: true, message: "请选择分块策略" }],
};

function openCreate() {
  createForm.name = "";
  createForm.description = "";
  createForm.embedding_model = "";
  createForm.chunk_method = "naive";
  createOpen.value = true;
}

async function onCreate() {
  try {
    await createFormRef.value?.validate();
  } catch {
    return;
  }
  creating.value = true;
  try {
    const { data } = await kbApi.createRagDataset({
      name: createForm.name.trim(),
      description: createForm.description.trim() || undefined,
      embedding_model: createForm.embedding_model.trim() || undefined,
      chunk_method: createForm.chunk_method,
    });
    message.success("RAG 库已创建");
    createOpen.value = false;
    await loadDatasets();
    await selectDataset(data.data.id);
  } finally {
    creating.value = false;
  }
}

onMounted(loadDatasets);
</script>

<style scoped>
.vectorize-tab {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  min-height: calc(100vh - 240px);
}

/* 侧栏 */
.ds-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
}
.sidebar-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
}
.sidebar-title {
  font-size: 14px;
  font-weight: 700;
}
.sidebar-count {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.sidebar-head .ant-btn {
  margin-left: auto;
}
.ds-list {
  padding: 6px;
  max-height: calc(100vh - 300px);
  overflow-y: auto;
}
.ds-item {
  padding: 9px 11px;
  border-radius: 8px;
  cursor: pointer;
}
.ds-item:hover {
  background: var(--surface-soft);
}
.ds-item.active {
  background: var(--surface-info-soft);
}
.ds-item-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.ds-item-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ds-item-docs {
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}
.ds-item-meta {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 3px;
}

/* 主区 */
.ds-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.main-empty {
  padding: 80px 0;
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 12px;
}
.card {
  border-radius: 12px;
}
.card-sub {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-tertiary);
  margin-left: 8px;
}
.ds-detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.ds-detail-name {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.ds-detail-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.mono {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.ds-status {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-neutral-bg);
  color: var(--color-text-tertiary);
}
.ds-status--ready {
  background: var(--color-success-bg, #e6f7e6);
  color: var(--color-success-strong, #2c8a2c);
}
.ds-status--syncing {
  background: var(--color-info-bg, #e6f1ff);
  color: var(--color-info-strong);
}
.ds-status--error {
  background: var(--color-danger-bg, #ffeaea);
  color: var(--color-danger-strong, #d23030);
}

/* 映射 */
.map-group {
  margin-bottom: 12px;
}
.map-group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}
.map-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.map-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  background: var(--surface-soft);
}
.map-item--checked {
  border-color: var(--color-success-strong, #2c8a2c);
  background: var(--color-success-bg, #e6f7e6);
}
.map-item--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.map-item-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.map-item-docs {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.map-item-tag {
  font-size: 10px;
  color: var(--color-text-tertiary);
}

/* 检索 */
.retrieve-params {
  display: flex;
  align-items: flex-end;
  gap: 16px;
}
.threshold-item {
  flex: 1;
  max-width: 260px;
}
.hit-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}
.hit-item {
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--surface-soft);
  border: 1px solid var(--color-border);
}
.hit-head {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}
.hit-no {
  font-weight: 700;
  color: var(--color-info-strong);
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
.form-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
</style>
