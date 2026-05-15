<template>
  <section class="kb-page">
    <div class="kb-page-head">
      <div>
        <h2 class="kb-page-title">知识库管理</h2>
        <p class="kb-page-sub">管理 RAG 应用所需的知识库，文档解析与向量化由底层 RAGFlow 完成</p>
      </div>
      <a-button v-if="canEdit" type="primary" @click="openCreate">
        <template #icon><PlusOutlined /></template>
        新建知识库
      </a-button>
    </div>

    <div class="filter-bar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        placeholder="搜索编码或名称..."
        allow-clear
        @search="onSearch"
      />
      <a-select
        v-model:value="filterStatus"
        class="status-filter"
        placeholder="按状态筛选"
        allow-clear
        :options="statusOptions"
        @change="onSearch"
      />
    </div>

    <a-spin :spinning="loading">
      <div v-if="list.length" class="kb-grid">
        <article
          v-for="kb in list"
          :key="kb.id"
          class="kb-card"
          @click="router.push(`/knowledge/${kb.id}`)"
        >
          <div class="kb-card-top">
            <div class="kb-card-icon"><DatabaseOutlined /></div>
            <div class="kb-card-info">
              <h4 class="kb-card-name">{{ kb.name }}</h4>
              <span class="kb-card-code">{{ kb.code }}</span>
            </div>
            <span :class="['status-pill', `status-pill--${kb.status}`]">
              {{ statusLabel[kb.status] || kb.status }}
            </span>
          </div>

          <p class="kb-card-desc">{{ kb.description || "暂无描述" }}</p>

          <div class="kb-card-meta">
            <span class="meta-item">embedding: {{ kb.embedding_model }}</span>
            <span class="meta-item">chunk: {{ kb.chunk_method }}</span>
          </div>

          <div class="kb-card-footer">
            <span class="footer-item">📄 {{ kb.doc_count }} 文档</span>
            <span class="footer-item">🧩 {{ kb.chunk_count }} chunks</span>
            <span class="footer-time">{{ formatMs(kb.update_time) }}</span>
          </div>
        </article>
      </div>

      <a-empty
        v-else-if="!loading"
        :description="hasFilter ? '无匹配知识库' : '尚未创建任何知识库'"
        class="empty-block"
      >
        <a-button v-if="canEdit && !hasFilter" type="primary" @click="openCreate">
          创建第一个知识库
        </a-button>
      </a-empty>
    </a-spin>

    <div v-if="total > pageSize" class="kb-pagination">
      <a-pagination
        v-model:current="pageNo"
        :page-size="pageSize"
        :total="total"
        :show-total="(t: number) => `共 ${t} 条`"
        @change="loadList"
      />
    </div>

    <!-- 新建 KB 表单 -->
    <a-modal
      v-model:open="formOpen"
      title="新建知识库"
      :confirm-loading="submitting"
      destroy-on-close
      width="560px"
      @ok="submitForm"
    >
      <a-form
        ref="formRef"
        :model="formModel"
        :rules="formRules"
        layout="vertical"
        @keyup.enter="submitForm"
      >
        <a-form-item label="编码" name="code">
          <a-input
            v-model:value="formModel.code"
            placeholder="小写英文/数字/连字符，如 ops-runbook"
          />
        </a-form-item>
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formModel.name" placeholder="如 运维操作手册" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea
            v-model:value="formModel.description"
            :rows="2"
            placeholder="可选，描述知识库用途"
          />
        </a-form-item>
        <a-form-item label="Embedding 模型" name="embedding_model">
          <a-input
            v-model:value="formModel.embedding_model"
            placeholder="留空则使用系统设置中的默认 embedding"
            allow-clear
          />
          <div class="form-hint">
            留空时自动用「系统配置 → AI 基础设施」中的默认 Embedding；
            手动填写需对应 LLM 管理中已注册的模型，落库后不可修改
          </div>
        </a-form-item>
        <a-form-item label="分块策略" name="chunk_method">
          <a-select
            v-model:value="formModel.chunk_method"
            :options="chunkMethodOptions"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { DatabaseOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as kbApi from "@/api/kb";
import type { KbResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const router = useRouter();
const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.KB_EDIT));

const keyword = ref("");
const filterStatus = ref<string | undefined>(undefined);
const list = ref<KbResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);

const hasFilter = computed(() => !!keyword.value || !!filterStatus.value);

const statusLabel: Record<string, string> = {
  draft: "草稿",
  ready: "已就绪",
  syncing: "同步中",
  error: "异常",
};
const statusOptions = [
  { value: "ready", label: "已就绪" },
  { value: "syncing", label: "同步中" },
  { value: "error", label: "异常" },
  { value: "draft", label: "草稿" },
];
const chunkMethodOptions = [
  { value: "naive", label: "通用语义分块（naive）" },
  { value: "qa", label: "QA 问答对（qa）" },
  { value: "manual", label: "按标题层级（manual）" },
  { value: "book", label: "书籍（book）" },
  { value: "table", label: "表格（table）" },
  { value: "laws", label: "法律文档（laws）" },
];

async function loadList() {
  loading.value = true;
  try {
    const { data } = await kbApi.pageKb({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      status: filterStatus.value,
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pageNo.value = 1;
  loadList();
}

onMounted(loadList);

// ── 新建表单 ──
const formOpen = ref(false);
const submitting = ref(false);
const formRef = ref<FormInstance>();
const formModel = reactive({
  code: "",
  name: "",
  description: "",
  embedding_model: "",
  chunk_method: "naive",
});

const formRules: Record<string, Rule[]> = {
  code: [
    { required: true, message: "请输入编码" },
    { pattern: /^[a-z0-9][a-z0-9_-]*$/, message: "仅允许小写字母、数字、下划线和连字符" },
  ],
  name: [{ required: true, message: "请输入名称" }],
  // embedding_model 不再前端 required:留空时后端会从 system_setting 兜底,
  // 见 docs/knowledge-rag-impl-plan.md §4 Step 4
  chunk_method: [{ required: true, message: "请选择分块策略" }],
};

function openCreate() {
  formModel.code = "";
  formModel.name = "";
  formModel.description = "";
  formModel.embedding_model = "";
  formModel.chunk_method = "naive";
  formOpen.value = true;
}

async function submitForm() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  submitting.value = true;
  try {
    const { data } = await kbApi.createKb({
      code: formModel.code.trim(),
      name: formModel.name.trim(),
      description: formModel.description.trim() || undefined,
      embedding_model: formModel.embedding_model.trim() || undefined,
      chunk_method: formModel.chunk_method,
    });
    message.success("创建成功");
    formOpen.value = false;
    router.push(`/knowledge/${data.data.id}`);
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.kb-page {
  min-height: 100%;
}
.kb-page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}
.kb-page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}
.kb-page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}
.search-input {
  width: 320px;
}
.status-filter {
  width: 160px;
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.kb-card {
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 16px 18px;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.kb-card:hover {
  transform: translateY(-1px);
  border-color: var(--color-info-bg-strong);
  box-shadow: var(--shadow-info-drop);
}
.kb-card-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.kb-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--surface-info-soft);
  color: var(--color-info-strong);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
}
.kb-card-info {
  flex: 1;
  min-width: 0;
}
.kb-card-name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-card-code {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--color-text-tertiary);
}
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
.kb-card-desc {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.kb-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.meta-item {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--color-text-tertiary);
  background: var(--surface-soft);
  padding: 2px 8px;
  border-radius: 999px;
}
.kb-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-wrap: wrap;
  gap: 6px;
}
.footer-item {
  font-weight: 600;
}

.empty-block {
  padding: 60px 0;
}
.kb-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}
.form-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
</style>
