<template>
  <div class="kb-tab">
    <!-- 左:知识库 + 分类 -->
    <aside class="kb-sidebar">
      <div class="sidebar-head">
        <span class="sidebar-title">知识库</span>
        <span class="sidebar-count">{{ kbList.length }}</span>
        <a-button v-if="canEdit" type="link" size="small" @click="openCreateKb">
          <PlusOutlined /> 新建
        </a-button>
      </div>
      <a-spin :spinning="kbLoading">
        <div class="kb-list">
          <template v-for="kb in kbList" :key="kb.id">
            <div
              :class="['kb-item', { active: selectedKbId === kb.id && !selectedCatId }]"
              @click="selectKb(kb.id)"
            >
              <DatabaseOutlined class="kb-item-icon" />
              <span class="kb-item-name">{{ kb.name }}</span>
              <span class="kb-item-count">{{ kb.doc_count }}</span>
            </div>
            <div v-if="selectedKbId === kb.id" class="cat-list">
              <div
                v-for="cat in categoryTree"
                :key="cat.id"
                :class="['cat-item', { active: selectedCatId === cat.id }]"
                @click="selectCat(cat.id)"
              >
                <span class="cat-name">{{ cat.name }}</span>
                <a-tooltip v-if="cat.rag_dataset_name" :title="`已映射: ${cat.rag_dataset_name}`">
                  <LinkOutlined class="cat-mapped" />
                </a-tooltip>
                <span class="cat-count">{{ cat.doc_count }}</span>
                <a-dropdown v-if="canEdit" :trigger="['click']">
                  <MoreOutlined class="cat-more" @click.stop />
                  <template #overlay>
                    <a-menu @click="(e: any) => onCatMenu(e.key, cat)">
                      <a-menu-item key="rename">重命名</a-menu-item>
                      <a-menu-item key="delete" danger>删除</a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
              </div>
              <div v-if="canEdit" class="cat-item cat-add" @click="openCreateCategory">
                <PlusOutlined /> 添加分类
              </div>
            </div>
          </template>
          <a-empty
            v-if="!kbLoading && !kbList.length"
            description="尚无知识库"
            :image="emptyImage"
          />
        </div>
      </a-spin>
    </aside>

    <!-- 右:文档列表 / 文档详情 -->
    <main class="kb-main">
      <a-empty
        v-if="!selectedKbId"
        class="main-empty"
        description="请选择左侧知识库查看文档"
      />

      <!-- 文档详情(页内内嵌)-->
      <div v-else-if="selectedDoc" class="doc-detail">
        <div class="detail-head">
          <a-button type="link" class="detail-back" @click="closeDoc">
            <ArrowLeftOutlined /> 返回文档列表
          </a-button>
          <span class="detail-name">{{ selectedDoc.name }}</span>
          <a-tag>{{ selectedDoc.format }}</a-tag>
          <span :class="['vec-pill', `vec-pill--${selectedDoc.vectorize_status}`]">
            {{ vecLabel[selectedDoc.vectorize_status] || selectedDoc.vectorize_status }}
          </span>
          <div class="detail-actions">
            <a-button size="small" @click="previewDoc(selectedDoc)">预览</a-button>
            <a-button
              size="small"
              type="primary"
              :href="docDownloadUrl(selectedDoc)"
              :download="selectedDoc.name"
            >
              下载原文件
            </a-button>
          </div>
        </div>
        <a-descriptions :column="2" size="small" bordered class="detail-desc">
          <a-descriptions-item label="格式">{{ selectedDoc.format }}</a-descriptions-item>
          <a-descriptions-item label="大小">
            {{ humanSize(selectedDoc.size_bytes) }}
          </a-descriptions-item>
          <a-descriptions-item label="分类">
            {{ selectedDoc.category_name || "未分类" }}
          </a-descriptions-item>
          <a-descriptions-item label="来源">{{ selectedDoc.source_type }}</a-descriptions-item>
          <a-descriptions-item label="chunks">{{ selectedDoc.chunks_count }}</a-descriptions-item>
          <a-descriptions-item label="更新时间">
            {{ formatMs(selectedDoc.update_time) }}
          </a-descriptions-item>
          <a-descriptions-item label="引用码" :span="2">
            <a-typography-text
              code
              :copyable="{ text: selectedDoc.ref, tooltip: '复制引用码' }"
            >
              {{ selectedDoc.ref }}
            </a-typography-text>
          </a-descriptions-item>
          <a-descriptions-item
            v-if="selectedDoc.error_message"
            label="错误信息"
            :span="2"
          >
            <span class="err-text">{{ selectedDoc.error_message }}</span>
          </a-descriptions-item>
        </a-descriptions>

        <h4 class="detail-section">
          chunks 预览
          <span class="detail-sub">（RAGFlow 实时拉取，共 {{ chunkTotal }} 个）</span>
        </h4>
        <a-spin :spinning="chunksLoading">
          <a-empty
            v-if="!chunks.length && !chunksLoading"
            description="该文档尚未生成 chunks（未映射 RAG 库 / 向量化中 / 失败）"
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
      </div>

      <!-- 文档列表 -->
      <template v-else>
        <div class="kb-info-bar">
          <div>
            <h3 class="info-title">{{ selectedTitle }}</h3>
            <p class="info-sub">{{ docTotal }} 篇文档，状态由向量化 worker 周期回拉</p>
          </div>
          <div class="info-tools">
            <a-input-search
              v-model:value="docKeyword"
              placeholder="搜索文档名称"
              allow-clear
              class="doc-search"
              @search="reloadDocs"
            />
            <a-select
              v-model:value="docStatusFilter"
              placeholder="向量化状态"
              allow-clear
              :options="vecStatusOptions"
              class="doc-status-select"
              @change="reloadDocs"
            />
            <a-button v-if="canEdit && selectedDocIds.length" @click="openMoveDocs">
              移动 ({{ selectedDocIds.length }})
            </a-button>
            <a-button
              v-if="canEdit && selectedDocIds.length"
              danger
              @click="onBatchDelete"
            >
              删除 ({{ selectedDocIds.length }})
            </a-button>
            <a-button v-if="canEdit" type="primary" @click="openUpload">
              <template #icon><PlusOutlined /></template>
              上传文档
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
          :scroll="{ x: 720 }"
          :row-selection="
            canEdit ? { selectedRowKeys: selectedDocIds, onChange: onSelectChange } : undefined
          "
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'doc'">
              <div class="doc-cell">
                <a class="doc-name" @click.prevent="openDoc(record)">{{ record.name }}</a>
                <div class="doc-meta">
                  <template v-if="record.vectorize_status === 'parsing'">
                    <a-progress
                      :percent="parsePercent(record)"
                      size="small"
                      status="active"
                      class="doc-progress"
                    />
                  </template>
                  <span
                    v-else
                    :class="['vec-pill', `vec-pill--${record.vectorize_status}`]"
                  >
                    {{ vecLabel[record.vectorize_status] || record.vectorize_status }}
                  </span>
                  <span class="doc-dim">{{ record.format }}</span>
                  <span class="doc-dim">{{ humanSize(record.size_bytes) }}</span>
                  <span class="doc-dim">{{ formatMs(record.update_time) }}</span>
                  <span
                    v-if="record.vectorize_status === 'error' && record.error_message"
                    class="err-text"
                  >
                    {{ record.error_message }}
                  </span>
                </div>
              </div>
            </template>
            <template v-else-if="column.key === 'category'">
              <span class="cat-tag">{{ record.category_name || "未分类" }}</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <a-button type="link" size="small" @click="previewDoc(record)">预览</a-button>
              <a-button type="link" size="small" @click="openDoc(record)">详情</a-button>
              <a-dropdown :trigger="['click']">
                <a-button type="link" size="small">更多 <DownOutlined /></a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item
                      v-if="canPublish"
                      :disabled="!record.rag_dataset_id || record.vectorize_status === 'parsing'"
                      @click="onRevectorize(record)"
                    >
                      重新向量化
                    </a-menu-item>
                    <a-menu-divider v-if="canEdit" />
                    <a-menu-item v-if="canEdit" danger @click="confirmDeleteDoc(record)">
                      删除
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </template>
          </template>
        </a-table>

        <div v-if="docTotal > docPageSize" class="doc-pagination">
          <a-pagination
            v-model:current="docPageNo"
            :page-size="docPageSize"
            :total="docTotal"
            :show-total="(t: number) => `共 ${t} 条`"
            @change="loadDocs"
          />
        </div>
      </template>
    </main>

    <!-- 新建知识库 -->
    <a-modal
      v-model:open="kbModalOpen"
      title="新建知识库"
      :confirm-loading="kbSaving"
      ok-text="创建"
      destroy-on-close
      @ok="onCreateKb"
    >
      <a-form ref="kbFormRef" :model="kbForm" :rules="kbRules" layout="vertical">
        <a-form-item label="编码" name="code">
          <a-input v-model:value="kbForm.code" placeholder="小写英文/数字/连字符，如 ops-runbook" />
        </a-form-item>
        <a-form-item label="名称" name="name">
          <a-input v-model:value="kbForm.name" placeholder="如 运维知识库" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="kbForm.description" :rows="2" placeholder="可选" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 新建 / 重命名分类 -->
    <a-modal
      v-model:open="catModalOpen"
      :title="catModalMode === 'rename' ? '重命名分类' : '添加分类'"
      :confirm-loading="catSaving"
      ok-text="保存"
      destroy-on-close
      @ok="onSaveCategory"
    >
      <a-input
        v-model:value="catModalName"
        placeholder="分类名称"
        :maxlength="255"
        @press-enter="onSaveCategory"
      />
    </a-modal>

    <!-- 移动文档 -->
    <a-modal
      v-model:open="moveModalOpen"
      title="移动到分类"
      :confirm-loading="moving"
      ok-text="移动"
      destroy-on-close
      @ok="onMoveDocs"
    >
      <p class="move-tip">
        将选中的 {{ selectedDocIds.length }} 篇文档移动到。跨 RAG 库时会重新向量化。
      </p>
      <a-tree-select
        v-model:value="moveTargetCat"
        :tree-data="catTreeSelectData"
        tree-default-expand-all
        placeholder="选择目标分类"
        style="width: 100%"
      />
    </a-modal>

    <!-- 上传文档 -->
    <a-modal
      v-model:open="uploadModalOpen"
      :title="`上传文档到 ${selectedKb?.name ?? ''}`"
      :confirm-loading="uploading"
      ok-text="开始上传"
      :ok-button-props="{ disabled: !uploadFiles.length }"
      destroy-on-close
      @ok="onUpload"
    >
      <a-upload-dragger
        v-model:file-list="uploadFiles"
        :before-upload="beforeUpload"
        :multiple="true"
        :disabled="uploading"
      >
        <p class="upload-icon"><InboxOutlined /></p>
        <p class="upload-text">拖拽文件到此处或点击选择</p>
        <p class="upload-hint">支持 PDF / DOCX / XLSX / Markdown / TXT / CSV / JSON / 图片</p>
      </a-upload-dragger>
      <a-form layout="vertical" class="upload-form">
        <a-form-item label="目标分类">
          <a-tree-select
            v-model:value="uploadCategory"
            :tree-data="catTreeSelectData"
            tree-default-expand-all
            placeholder="选择分类"
            style="width: 100%"
          />
          <div class="upload-form-hint">
            分类已映射 RAG 库时,上传后自动进入向量化队列
          </div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Empty, Modal, message } from "ant-design-vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import type { UploadFile, UploadProps } from "ant-design-vue";
import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  DownOutlined,
  InboxOutlined,
  LinkOutlined,
  MoreOutlined,
  PlusOutlined,
} from "@ant-design/icons-vue";
import * as kbApi from "@/api/kb";
import type { KbCategoryNode, KbChunkResp, KbDocumentResp, KbResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const router = useRouter();
const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.KB_EDIT));
const canPublish = computed(() => auth.hasPermission(PERM.KB_PUBLISH));
const emptyImage = Empty.PRESENTED_IMAGE_SIMPLE;

const vecLabel: Record<string, string> = {
  not_mapped: "未映射",
  pending: "待向量化",
  parsing: "向量化中",
  done: "已完成",
  error: "失败",
};
const vecStatusOptions = Object.entries(vecLabel).map(([value, label]) => ({
  value,
  label,
}));

const docColumns = [
  { title: "文档", key: "doc" },
  { title: "分类", key: "category", width: 150 },
  { title: "操作", key: "action", width: 200, fixed: "right" as const },
];

// ── 知识库列表 ──
const kbList = ref<KbResp[]>([]);
const kbLoading = ref(false);
const selectedKbId = ref<string | null>(null);
const selectedKb = computed(() => kbList.value.find((k) => k.id === selectedKbId.value) ?? null);

async function loadKbList() {
  kbLoading.value = true;
  try {
    const { data } = await kbApi.pageKb({ page_no: 1, page_size: 1000 });
    kbList.value = data.data;
  } finally {
    kbLoading.value = false;
  }
}

// ── 分类 ──
const categoryTree = ref<KbCategoryNode[]>([]);
const selectedCatId = ref<string | null>(null);

const selectedTitle = computed(() => {
  if (selectedCatId.value) {
    const c = categoryTree.value.find((x) => x.id === selectedCatId.value);
    return c ? c.name : "文档";
  }
  return selectedKb.value ? `${selectedKb.value.name} · 全部文档` : "文档";
});

const catTreeSelectData = computed(() => [
  { value: "0", title: "未分类" },
  ...categoryTree.value.map((c) => ({ value: c.id, title: c.name })),
]);

async function loadCategoryTree() {
  if (!selectedKbId.value) {
    categoryTree.value = [];
    return;
  }
  try {
    const { data } = await kbApi.getKbCategoryTree(selectedKbId.value);
    categoryTree.value = data.data;
  } catch {
    categoryTree.value = [];
  }
}

async function selectKb(id: string) {
  selectedKbId.value = id;
  selectedCatId.value = null;
  selectedDoc.value = null;
  selectedDocIds.value = [];
  docPageNo.value = 1;
  await loadCategoryTree();
  await loadDocs();
}

async function selectCat(id: string) {
  selectedCatId.value = id;
  selectedDoc.value = null;
  selectedDocIds.value = [];
  docPageNo.value = 1;
  await loadDocs();
}

// ── 文档列表 ──
const docs = ref<KbDocumentResp[]>([]);
const docTotal = ref(0);
const docsLoading = ref(false);
const docPageNo = ref(1);
const docPageSize = ref(20);
const docKeyword = ref("");
const docStatusFilter = ref<string | undefined>(undefined);
const selectedDocIds = ref<string[]>([]);

async function loadDocs(showSpin = true) {
  if (!selectedKbId.value) return;
  if (showSpin) docsLoading.value = true;
  try {
    const { data } = await kbApi.pageKbDocuments(selectedKbId.value, {
      page_no: docPageNo.value,
      page_size: docPageSize.value,
      keyword: docKeyword.value || undefined,
      category_id: selectedCatId.value ?? undefined,
      vectorize_status: docStatusFilter.value,
    });
    docs.value = data.data;
    docTotal.value = data.total;
  } finally {
    if (showSpin) docsLoading.value = false;
  }
}

function reloadDocs() {
  docPageNo.value = 1;
  loadDocs();
}

function onSelectChange(keys: (string | number)[]) {
  selectedDocIds.value = keys.map(String);
}

function parsePercent(d: KbDocumentResp): number {
  return Math.max(0, Math.min(100, Math.round((d.parse_progress ?? 0) * 100)));
}

// ── 轮询(向量化中)──
let pollTimer: ReturnType<typeof setInterval> | null = null;
function ensurePolling() {
  const active = docs.value.some(
    (d) => d.vectorize_status === "pending" || d.vectorize_status === "parsing",
  );
  if (active && !pollTimer) {
    pollTimer = setInterval(() => loadDocs(false), 5000);
  } else if (!active && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}
watch(docs, ensurePolling, { deep: true });
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});

// ── 文档详情 ──
const selectedDoc = ref<KbDocumentResp | null>(null);
const chunks = ref<KbChunkResp[]>([]);
const chunkTotal = ref(0);
const chunksLoading = ref(false);
const chunkPageNo = ref(1);
const chunkPageSize = ref(20);

async function openDoc(record: KbDocumentResp) {
  selectedDoc.value = record;
  chunkPageNo.value = 1;
  try {
    const { data } = await kbApi.getKbDocument(record.kb_id, record.id);
    selectedDoc.value = data.data;
  } catch {
    /* 保留列表里的缓存 */
  }
  await loadChunks();
}

function closeDoc() {
  selectedDoc.value = null;
  chunks.value = [];
}

async function loadChunks() {
  if (!selectedDoc.value) return;
  chunksLoading.value = true;
  try {
    const { data } = await kbApi.listKbDocumentChunks(
      selectedDoc.value.kb_id,
      selectedDoc.value.id,
      { page_no: chunkPageNo.value, page_size: chunkPageSize.value },
    );
    chunks.value = data.data;
    chunkTotal.value = data.total;
  } catch {
    chunks.value = [];
    chunkTotal.value = 0;
  } finally {
    chunksLoading.value = false;
  }
}

function previewDoc(record: KbDocumentResp) {
  router.push(`/knowledge/${record.kb_id}/document/${record.id}/preview`);
}

function docDownloadUrl(record: KbDocumentResp): string {
  return kbApi.kbDocumentDownloadUrl(record.kb_id, record.id);
}

// ── 文档操作 ──
async function onRevectorize(record: KbDocumentResp) {
  await kbApi.revectorizeKbDocument(record.kb_id, record.id);
  message.success("已触发重新向量化");
  await loadDocs();
}

function confirmDeleteDoc(record: KbDocumentResp) {
  Modal.confirm({
    title: "确定删除该文档?",
    content: `${record.name} 的原文与 RAGFlow 向量将一并删除,无法撤销。`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      await kbApi.deleteKbDocuments(record.kb_id, [record.id]);
      message.success("已删除");
      await refreshAfterMutation();
    },
  });
}

async function onBatchDelete() {
  Modal.confirm({
    title: `确定删除选中的 ${selectedDocIds.value.length} 篇文档?`,
    content: "原文与 RAGFlow 向量一并删除,无法撤销。",
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      if (!selectedKbId.value) return;
      await kbApi.deleteKbDocuments(selectedKbId.value, selectedDocIds.value);
      message.success(`已删除 ${selectedDocIds.value.length} 篇`);
      selectedDocIds.value = [];
      await refreshAfterMutation();
    },
  });
}

async function refreshAfterMutation() {
  await Promise.all([loadDocs(), loadCategoryTree(), loadKbList()]);
}

// ── 移动 ──
const moveModalOpen = ref(false);
const moveTargetCat = ref<string>("0");
const moving = ref(false);

function openMoveDocs() {
  moveTargetCat.value = "0";
  moveModalOpen.value = true;
}

async function onMoveDocs() {
  if (!selectedKbId.value) return;
  moving.value = true;
  try {
    await kbApi.moveKbDocuments(selectedKbId.value, selectedDocIds.value, moveTargetCat.value);
    message.success(`已移动 ${selectedDocIds.value.length} 篇`);
    moveModalOpen.value = false;
    selectedDocIds.value = [];
    await refreshAfterMutation();
  } finally {
    moving.value = false;
  }
}

// ── 新建知识库 ──
const kbModalOpen = ref(false);
const kbSaving = ref(false);
const kbFormRef = ref<FormInstance>();
const kbForm = reactive({ code: "", name: "", description: "" });
const kbRules: Record<string, Rule[]> = {
  code: [
    { required: true, message: "请输入编码" },
    { pattern: /^[a-z0-9][a-z0-9_-]*$/, message: "仅允许小写字母、数字、下划线和连字符" },
  ],
  name: [{ required: true, message: "请输入名称" }],
};

function openCreateKb() {
  kbForm.code = "";
  kbForm.name = "";
  kbForm.description = "";
  kbModalOpen.value = true;
}

async function onCreateKb() {
  try {
    await kbFormRef.value?.validate();
  } catch {
    return;
  }
  kbSaving.value = true;
  try {
    const { data } = await kbApi.createKb({
      code: kbForm.code.trim(),
      name: kbForm.name.trim(),
      description: kbForm.description.trim() || undefined,
    });
    message.success("知识库已创建");
    kbModalOpen.value = false;
    await loadKbList();
    await selectKb(data.data.id);
  } finally {
    kbSaving.value = false;
  }
}

// ── 分类增删改 ──
const catModalOpen = ref(false);
const catModalMode = ref<"create" | "rename">("create");
const catModalName = ref("");
const catModalTarget = ref<string>("");
const catSaving = ref(false);

function openCreateCategory() {
  catModalMode.value = "create";
  catModalName.value = "";
  catModalOpen.value = true;
}

function onCatMenu(action: string, cat: KbCategoryNode) {
  if (action === "rename") {
    catModalMode.value = "rename";
    catModalName.value = cat.name;
    catModalTarget.value = cat.id;
    catModalOpen.value = true;
  } else if (action === "delete") {
    confirmDeleteCategory(cat);
  }
}

async function onSaveCategory() {
  const name = catModalName.value.trim();
  if (!name || !selectedKbId.value) {
    message.warning("请输入分类名称");
    return;
  }
  catSaving.value = true;
  try {
    if (catModalMode.value === "create") {
      await kbApi.createKbCategory(selectedKbId.value, { name, parent_id: "0" });
      message.success("分类已创建");
    } else {
      await kbApi.updateKbCategory(selectedKbId.value, catModalTarget.value, { name });
      message.success("已重命名");
    }
    catModalOpen.value = false;
    await loadCategoryTree();
  } finally {
    catSaving.value = false;
  }
}

async function confirmDeleteCategory(cat: KbCategoryNode) {
  if (!selectedKbId.value) return;
  const { data } = await kbApi.deleteKbCategory(selectedKbId.value, cat.id, false);
  Modal.confirm({
    title: "确定删除该分类?",
    content: `将删除该分类及其下 ${data.data.document_count} 篇文档,文档同步从 RAGFlow 移除,无法撤销。`,
    okText: "删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      if (!selectedKbId.value) return;
      await kbApi.deleteKbCategory(selectedKbId.value, cat.id, true);
      message.success("分类已删除");
      if (selectedCatId.value === cat.id) selectedCatId.value = null;
      await refreshAfterMutation();
    },
  });
}

// ── 上传 ──
const uploadModalOpen = ref(false);
const uploadFiles = ref<UploadFile[]>([]);
const uploadCategory = ref<string>("0");
const uploading = ref(false);
const MAX_FILES = 20;
const MAX_SIZE = 50 * 1024 * 1024;

function openUpload() {
  uploadFiles.value = [];
  uploadCategory.value = selectedCatId.value ?? "0";
  uploadModalOpen.value = true;
}

const beforeUpload: UploadProps["beforeUpload"] = (file) => {
  if (uploadFiles.value.length >= MAX_FILES) {
    message.error(`最多 ${MAX_FILES} 个文件`);
    return false;
  }
  if (file.size > MAX_SIZE) {
    message.error(`${file.name} 超过 50MB`);
    return false;
  }
  return false;
};

async function onUpload() {
  if (!selectedKbId.value || !uploadFiles.value.length) return;
  uploading.value = true;
  try {
    const raw = uploadFiles.value
      .map((f) => (f.originFileObj ?? null) as File | null)
      .filter((f): f is File => f !== null);
    const { data } = await kbApi.uploadKbDocuments(
      selectedKbId.value,
      raw,
      uploadCategory.value || "0",
    );
    message.success(`已上传 ${data.data.length} 篇`);
    uploadModalOpen.value = false;
    await refreshAfterMutation();
  } finally {
    uploading.value = false;
  }
}

// ── 辅助 ──
function humanSize(n: number | null | undefined): string {
  if (!n || n < 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

loadKbList();
</script>

<style scoped>
.kb-tab {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  min-height: calc(100vh - 240px);
}

/* 侧栏 */
.kb-sidebar {
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
  color: var(--color-text);
}
.sidebar-count {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.sidebar-head .ant-btn {
  margin-left: auto;
}
.kb-list {
  padding: 6px;
  max-height: calc(100vh - 300px);
  overflow-y: auto;
}
.kb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.kb-item:hover {
  background: var(--surface-soft);
}
.kb-item.active {
  background: var(--surface-info-soft);
  color: var(--color-info-strong);
}
.kb-item-icon {
  font-size: 14px;
}
.kb-item-name {
  flex: 1;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-item-count {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.cat-list {
  margin: 2px 0 4px 16px;
}
.cat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.cat-item:hover {
  background: var(--surface-soft);
}
.cat-item.active {
  background: var(--surface-info-soft);
  color: var(--color-info-strong);
}
.cat-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cat-mapped {
  font-size: 11px;
  color: var(--color-success-strong, #2c8a2c);
}
.cat-count {
  font-size: 11px;
}
.cat-more {
  padding: 0 2px;
}
.cat-add {
  color: var(--color-info-strong);
}

/* 主区 */
.kb-main {
  flex: 1;
  min-width: 0;
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px 18px;
}
.main-empty {
  padding: 80px 0;
}

.kb-info-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.info-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.info-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.info-tools {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.doc-search {
  width: 200px;
}
.doc-status-select {
  width: 140px;
}

/* 文档单元格 */
.doc-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.doc-name {
  font-weight: 500;
  color: var(--color-info-strong);
  cursor: pointer;
}
.doc-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 11px;
}
.doc-dim {
  color: var(--color-text-tertiary);
}
.doc-progress {
  width: 130px;
}
.cat-tag {
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* 状态药丸 */
.vec-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--color-neutral-bg);
  color: var(--color-text-tertiary);
}
.vec-pill--pending {
  background: var(--color-warning-bg, #fff7e6);
  color: var(--color-warning-strong, #c98a00);
}
.vec-pill--parsing {
  background: var(--color-info-bg, #e6f1ff);
  color: var(--color-info-strong);
}
.vec-pill--done {
  background: var(--color-success-bg, #e6f7e6);
  color: var(--color-success-strong, #2c8a2c);
}
.vec-pill--error {
  background: var(--color-danger-bg, #ffeaea);
  color: var(--color-danger-strong, #d23030);
}
.err-text {
  font-size: 11px;
  color: var(--color-danger-strong, #d23030);
}

.doc-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

/* 文档详情 */
.doc-detail {
  display: flex;
  flex-direction: column;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.detail-back {
  padding: 0;
}
.detail-name {
  font-size: 16px;
  font-weight: 700;
}
.detail-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.detail-desc {
  margin-bottom: 8px;
}
.detail-section {
  margin: 20px 0 12px;
  font-size: 14px;
  font-weight: 700;
}
.detail-sub {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-tertiary);
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
}
.chunk-body {
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  color: var(--color-text);
}
.chunk-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

/* 弹窗 */
.move-tip {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.upload-icon {
  font-size: 38px;
  color: var(--color-info-strong);
}
.upload-text {
  font-size: 14px;
  margin: 6px 0 4px;
}
.upload-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.upload-form {
  margin-top: 16px;
}
.upload-form-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
</style>
