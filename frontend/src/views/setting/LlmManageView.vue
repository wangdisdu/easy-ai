<template>
  <div class="llm-page">
    <!-- Provider list -->
    <div class="llm-provider-list">
      <div v-for="provider in list" :key="provider.id" class="llm-provider-card">
        <!-- Header row (clickable) -->
        <div class="llm-provider-header" @click="toggleExpand(provider.id)">
          <span :class="['llm-status-dot', statusStyle[provider.status]?.dot]" />
          <div class="llm-provider-info">
            <div class="llm-provider-name-row">
              <span class="llm-provider-name">{{ provider.name }}</span>
              <a-tag :color="statusStyle[provider.status]?.color" size="small">
                {{ statusStyle[provider.status]?.label }}
              </a-tag>
              <a-tag size="small">{{ providerTypeLabel[provider.provider_type] || provider.provider_type }}</a-tag>
            </div>
            <span class="llm-provider-url">{{ provider.base_url }}</span>
          </div>
          <div class="llm-type-tags">
            <a-tag
              v-for="mt in modelTypeSummary(provider)"
              :key="mt.type"
              :color="modelTypeColor[mt.type]"
              size="small"
            >
              {{ mt.type }} {{ mt.count }}
            </a-tag>
          </div>
          <DownOutlined
            :class="['llm-expand-icon', expandedId === provider.id && 'llm-expand-icon--open']"
          />
        </div>

        <!-- Expanded detail -->
        <div v-if="expandedId === provider.id" class="llm-provider-detail">
          <!-- Provider settings (inline edit) -->
          <div class="llm-section-label">供应商信息</div>
          <a-form layout="vertical" class="llm-edit-form">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="供应商名称">
                  <a-input v-model:value="editForm.name" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="接口类型">
                  <a-select v-model:value="editForm.provider_type">
                    <a-select-option value="openai">OpenAI Compatible</a-select-option>
                    <a-select-option value="ollama">Ollama</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="Base URL">
                  <a-input v-model:value="editForm.base_url" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="API Key">
                  <a-input-password
                    v-model:value="editForm.api_key"
                    :visibility-toggle="true"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </a-form>

          <!-- Models table -->
          <div class="llm-section-label">
            <span>已注册模型</span>
            <a-button v-if="canEdit" type="link" size="small" @click="openAddModel(provider)">
              <template #icon><PlusOutlined /></template>
              添加模型
            </a-button>
          </div>
          <a-table
            :columns="modelColumns"
            :data-source="provider.models"
            :pagination="false"
            size="small"
            row-key="id"
            class="llm-model-table"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'model_type'">
                <a-tag :color="modelTypeColor[record.model_type]" size="small">
                  {{ record.model_type }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'max_input_tokens'">
                <span v-if="record.max_input_tokens" class="llm-tokens">
                  {{ record.max_input_tokens.toLocaleString() }}
                </span>
                <span v-else class="llm-tokens-unset">—</span>
              </template>
              <template v-else-if="column.key === 'status'">
                <a-tag :color="record.status === 'active' ? 'success' : 'default'" size="small">
                  {{ record.status === "active" ? "启用" : "禁用" }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'actions'">
                <a-space v-if="canEdit">
                  <a-button
                    v-if="record.status === 'active'"
                    type="link"
                    size="small"
                    @click="onToggleModelStatus(record, 'disable')"
                  >
                    禁用
                  </a-button>
                  <a-button
                    v-else
                    type="link"
                    size="small"
                    @click="onToggleModelStatus(record, 'enable')"
                  >
                    启用
                  </a-button>
                  <a-popconfirm title="确定删除该模型？" @confirm="onDeleteModel(record)">
                    <a-button type="link" size="small" danger>删除</a-button>
                  </a-popconfirm>
                </a-space>
                <span v-else class="llm-tokens-unset">—</span>
              </template>
            </template>
          </a-table>

          <!-- Actions -->
          <div v-if="canEdit" class="llm-detail-actions">
            <a-button type="primary" :loading="testing" ghost @click="onTestConnection(provider)">
              测试连接
            </a-button>
            <a-button type="primary" :loading="saving" @click="onSaveProvider(provider)">
              保存修改
            </a-button>
            <a-popconfirm title="确定删除该供应商及其所有模型？" @confirm="onDeleteProvider(provider)">
              <a-button danger class="llm-delete-btn">删除供应商</a-button>
            </a-popconfirm>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <a-empty v-if="!loading && !list.length" description="暂无模型供应商" />
    </div>

    <!-- Add provider button -->
    <a-button v-if="canEdit" type="dashed" block class="llm-add-provider-btn" @click="openCreateProvider">
      <template #icon><PlusOutlined /></template>
      添加模型供应商
    </a-button>

    <!-- Create provider modal -->
    <a-modal
      v-model:open="createOpen"
      title="添加模型供应商"
      :confirm-loading="submitting"
      destroy-on-close
      width="600px"
      @ok="submitCreateProvider"
    >
      <div class="llm-predefined-row">
        <span class="llm-predefined-label">快速选择：</span>
        <a-space wrap>
          <a-button
            v-for="(url, key) in predefinedProviders"
            :key="key"
            size="small"
            @click="onSelectPredefined(key, url)"
          >
            {{ key }}
          </a-button>
        </a-space>
      </div>
      <a-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        layout="vertical"
      >
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="供应商名称" name="name">
              <a-input v-model:value="createForm.name" placeholder="例如：通义千问、DeepSeek" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="接口类型" name="provider_type">
              <a-select v-model:value="createForm.provider_type">
                <a-select-option value="openai">OpenAI Compatible</a-select-option>
                <a-select-option value="ollama">Ollama</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="Base URL" name="base_url">
          <a-input v-model:value="createForm.base_url" placeholder="https://api.example.com/v1" />
        </a-form-item>
        <a-form-item label="API Key">
          <a-input-password v-model:value="createForm.api_key" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Add model modal -->
    <a-modal
      v-model:open="addModelOpen"
      title="添加模型"
      :confirm-loading="addModelSubmitting"
      destroy-on-close
      width="520px"
      @ok="submitAddModel"
    >
      <a-form
        ref="addModelFormRef"
        :model="addModelForm"
        :rules="addModelRules"
        layout="vertical"
      >
        <a-form-item label="模型" name="model">
          <a-auto-complete
            v-if="availableModelOptions.length"
            v-model:value="addModelForm.model"
            :options="availableModelOptions"
            placeholder="请选择或输入模型名称，例如：qwen-max"
          />
          <a-input
            v-else
            v-model:value="addModelForm.model"
            :placeholder="availableModelsLoading ? '正在获取模型列表...' : '例如：qwen-max'"
          />
        </a-form-item>
        <a-form-item label="模型类型" name="model_type">
          <a-select v-model:value="addModelForm.model_type">
            <a-select-option v-for="mt in modelTypes" :key="mt" :value="mt">
              {{ mt }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item
          v-if="addModelForm.model_type === 'LLM'"
          label="最大输入 token"
          name="max_input_tokens"
          extra="非必填。配上后摘要中间件按此值的 85% 触发；不填则走 170k 兜底"
        >
          <a-input-number
            v-model:value="addModelForm.max_input_tokens"
            :min="1"
            :step="1000"
            placeholder="例如 32000 / 128000 / 200000"
            style="width: 100%"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import { DownOutlined, PlusOutlined } from "@ant-design/icons-vue";
import * as api from "@/api/llm";
import type { LlmProviderResp, LlmModelResp } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.SYSTEM_LLM));

const modelTypes = ["LLM", "Embedding", "Rerank", "Vision", "OCR"];
const modelTypeColor: Record<string, string> = {
  LLM: "blue",
  Embedding: "cyan",
  Rerank: "purple",
  Vision: "orange",
  OCR: "red",
};

const statusStyle: Record<string, { dot: string; label: string; color: string }> = {
  connected: { dot: "llm-dot--connected", label: "已连接", color: "success" },
  error: { dot: "llm-dot--error", label: "连接失败", color: "error" },
  unconfigured: { dot: "llm-dot--unconfigured", label: "未配置", color: "default" },
};
const providerTypeLabel: Record<string, string> = {
  openai: "OpenAI Compatible",
  ollama: "Ollama",
  "OpenAI Compatible": "OpenAI Compatible",
  Ollama: "Ollama",
};
const providerTypeValueMap: Record<string, string> = {
  openai: "openai",
  ollama: "ollama",
  "OpenAI Compatible": "openai",
  Ollama: "ollama",
};

const modelColumns = [
  { title: "模型", dataIndex: "model", key: "model" },
  { title: "类型", key: "model_type", align: "center" as const, width: 100 },
  { title: "最大输入 token", key: "max_input_tokens", align: "right" as const, width: 130 },
  { title: "状态", key: "status", align: "center" as const, width: 80 },
  { title: "操作", key: "actions", align: "right" as const, width: 120 },
];

// ── State ──
const list = ref<LlmProviderResp[]>([]);
const loading = ref(false);
const expandedId = ref<string | null>(null);
const saving = ref(false);
const testing = ref(false);

// Edit form (populated when expanding)
const editForm = reactive({
  name: "",
  provider_type: "openai",
  base_url: "",
  api_key: "",
});

// Create provider
const createOpen = ref(false);
const submitting = ref(false);
const createFormRef = ref<FormInstance>();
const createForm = reactive({
  name: "",
  provider_type: "openai",
  base_url: "",
  api_key: "",
});
const createRules: Record<string, Rule[]> = {
  name: [{ required: true, message: "请输入供应商名称" }],
  provider_type: [{ required: true, message: "请选择接口类型" }],
  base_url: [{ required: true, message: "请输入 Base URL" }],
};

// Predefined providers
const predefinedProviders = ref<Record<string, string>>({});

// Add model
const addModelOpen = ref(false);
const addModelSubmitting = ref(false);
const addModelFormRef = ref<FormInstance>();
const addModelProviderId = ref("");
const availableModelsLoading = ref(false);
const availableModelOptions = ref<Array<{ label: string; value: string }>>([]);
const addModelForm = reactive<{
  model: string;
  model_type: string;
  max_input_tokens: number | null;
}>({
  model: "",
  model_type: "LLM",
  max_input_tokens: null,
});
const addModelRules: Record<string, Rule[]> = {
  model: [{ required: true, message: "请输入模型名称" }],
  model_type: [{ required: true, message: "请选择模型类型" }],
};

// ── Helpers ──
function modelTypeSummary(provider: LlmProviderResp) {
  const map: Record<string, number> = {};
  for (const m of provider.models) {
    map[m.model_type] = (map[m.model_type] || 0) + 1;
  }
  return modelTypes.filter((t) => map[t]).map((t) => ({ type: t, count: map[t] }));
}

function populateEditForm(provider: LlmProviderResp) {
  editForm.name = provider.name;
  editForm.provider_type = providerTypeValueMap[provider.provider_type] || provider.provider_type;
  editForm.base_url = provider.base_url;
  editForm.api_key = provider.api_key ?? "";
}

// ── Data loading ──
async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.pageProvider({ page_no: 1, page_size: 200 });
    list.value = data.data;
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadList();
  try {
    const { data } = await api.getPredefinedProviders();
    predefinedProviders.value = data.data;
  } catch {
    // ignore
  }
});

// ── Expand / Collapse ──
function toggleExpand(id: string) {
  if (expandedId.value === id) {
    expandedId.value = null;
    return;
  }
  expandedId.value = id;
  const provider = list.value.find((p) => p.id === id);
  if (provider) populateEditForm(provider);
}

// ── Provider CRUD ──
function onSelectPredefined(key: string, url: string) {
  createForm.name = key;
  createForm.provider_type = "openai";
  createForm.base_url = url;
}

function openCreateProvider() {
  createForm.name = "";
  createForm.provider_type = "openai";
  createForm.base_url = "";
  createForm.api_key = "";
  createOpen.value = true;
}

async function submitCreateProvider() {
  try {
    await createFormRef.value?.validate();
  } catch {
    return;
  }
  submitting.value = true;
  try {
    await api.createProvider({
      name: createForm.name,
      provider_type: createForm.provider_type,
      base_url: createForm.base_url,
      api_key: createForm.api_key || undefined,
    });
    message.success("添加成功");
    createOpen.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function onSaveProvider(provider: LlmProviderResp) {
  saving.value = true;
  try {
    await api.updateProvider(provider.id, {
      name: editForm.name,
      provider_type: editForm.provider_type,
      base_url: editForm.base_url,
      api_key: editForm.api_key,
    });
    message.success("保存成功");
    await loadList();
  } finally {
    saving.value = false;
  }
}

async function onDeleteProvider(provider: LlmProviderResp) {
  await api.deleteProvider(provider.id);
  message.success("已删除");
  expandedId.value = null;
  await loadList();
}

async function onTestConnection(provider: LlmProviderResp) {
  testing.value = true;
  try {
    const { data } = await api.testProviderConnection(provider.id);
    const result = data.data;
    if (result.status === "connected") {
      message.success("连接成功");
    } else {
      message.error("连接失败");
    }
    await loadList();
  } finally {
    testing.value = false;
  }
}

// ── Model CRUD ──
async function loadAvailableModels(providerId: string) {
  availableModelsLoading.value = true;
  availableModelOptions.value = [];
  try {
    const { data } = await api.getProviderAvailableModels(providerId);
    availableModelOptions.value = data.data.map((item) => ({
      label: item,
      value: item,
    }));
  } catch {
    availableModelOptions.value = [];
  } finally {
    availableModelsLoading.value = false;
  }
}

function openAddModel(provider: LlmProviderResp) {
  addModelProviderId.value = provider.id;
  addModelForm.model = "";
  addModelForm.model_type = "LLM";
  addModelForm.max_input_tokens = null;
  void loadAvailableModels(provider.id);
  addModelOpen.value = true;
}

async function submitAddModel() {
  try {
    await addModelFormRef.value?.validate();
  } catch {
    return;
  }
  addModelSubmitting.value = true;
  try {
    await api.createModel(addModelProviderId.value, {
      model: addModelForm.model,
      model_type: addModelForm.model_type,
      max_input_tokens:
        addModelForm.model_type === "LLM" ? addModelForm.max_input_tokens : null,
    });
    message.success("添加成功");
    addModelOpen.value = false;
    await loadList();
  } finally {
    addModelSubmitting.value = false;
  }
}

async function onToggleModelStatus(model: LlmModelResp, action: "enable" | "disable") {
  if (action === "enable") {
    await api.enableModel(model.id);
  } else {
    await api.disableModel(model.id);
  }
  await loadList();
}

async function onDeleteModel(model: LlmModelResp) {
  await api.deleteModel(model.id);
  message.success("已删除");
  await loadList();
}
</script>

<style scoped>
.llm-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.llm-provider-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.llm-provider-card {
  border: 1px solid var(--surface-card-border);
  border-radius: 16px;
  background: var(--surface-card-bg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

/* ── Header ── */
.llm-provider-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  cursor: pointer;
  transition: background 0.15s;
}

.llm-provider-header:hover {
  background: var(--surface-muted-hover);
}

.llm-status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.llm-dot--connected {
  background: var(--color-success);
  box-shadow: 0 0 6px var(--color-success-border);
}

.llm-dot--error {
  background: var(--color-error);
  box-shadow: 0 0 6px var(--color-error-border);
}

.llm-dot--unconfigured {
  background: var(--color-text-quaternary);
}

.llm-provider-info {
  flex: 1;
  min-width: 0;
}

.llm-provider-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.llm-provider-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.llm-provider-url {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-text-quaternary);
  font-family: "SF Mono", "Fira Code", monospace;
}

.llm-type-tags {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.llm-expand-icon {
  color: var(--color-text-quaternary);
  font-size: 12px;
  transition: transform 0.2s;
}

.llm-expand-icon--open {
  transform: rotate(180deg);
}

/* ── Detail ── */
.llm-provider-detail {
  border-top: 1px solid var(--color-border);
  padding: 20px;
}

.llm-section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 12px;
  margin-top: 20px;
}

.llm-section-label:first-child {
  margin-top: 0;
}

.llm-edit-form {
  margin-bottom: 4px;
}

.llm-model-table {
  margin-bottom: 16px;
}

.llm-model-table :deep(.ant-table) {
  border-radius: 10px;
}

.llm-detail-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 8px;
}

.llm-delete-btn {
  margin-left: auto;
}

.llm-predefined-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.llm-predefined-label {
  font-size: 13px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}

.llm-add-provider-btn {
  height: 48px;
  border-radius: 14px;
  font-size: 14px;
  color: var(--color-text-tertiary);
}
</style>
