<template>
  <div class="sbx-page">
    <div class="sbx-toolbar">
      <a-input-search
        v-model:value="keyword"
        placeholder="搜索名称或镜像"
        allow-clear
        class="sbx-search"
        @search="onSearch"
      />
      <a-button v-if="canEdit" type="primary" @click="openCreate">新建镜像</a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="middle"
      class="sbx-table"
      @change="onTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'image'">
          <code class="sbx-image">{{ record.image }}</code>
        </template>
        <template v-else-if="column.key === 'resource'">
          <span v-if="record.cpu || record.memory" class="sbx-muted">
            {{ [record.cpu ? `${record.cpu} CPU` : "", record.memory].filter(Boolean).join(" / ") }}
          </span>
          <span v-else class="sbx-muted">不限</span>
        </template>
        <template v-else-if="column.key === 'is_default'">
          <a-tag v-if="record.is_default" color="blue">默认</a-tag>
          <span v-else class="sbx-muted">—</span>
        </template>
        <template v-else-if="column.key === 'enabled'">
          <a-tag :color="record.enabled ? 'green' : 'default'">
            {{ record.enabled ? "启用" : "停用" }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'description'">
          <span class="sbx-muted">{{ record.description || "—" }}</span>
        </template>
        <template v-else-if="column.key === 'update_time'">
          {{ formatTime(record.update_time) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button v-if="canEdit" type="link" size="small" @click="openEdit(record)">编辑</a-button>
          <a-popconfirm
            v-if="canEdit"
            title="确定删除该沙盒镜像？应用若已选用会回退到默认镜像。"
            @confirm="onDelete(record)"
          >
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
          <span v-if="!canEdit" class="sbx-muted">—</span>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="formOpen"
      :title="formMode === 'create' ? '新建沙盒镜像' : '编辑沙盒镜像'"
      :confirm-loading="submitting"
      destroy-on-close
      @ok="submitForm"
    >
      <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formModel.name" placeholder="展示名,如 Python 3.11" />
        </a-form-item>
        <a-form-item label="镜像" name="image">
          <a-input
            v-model:value="formModel.image"
            placeholder="容器镜像引用,如 python:3.11-slim 或私有仓库路径"
          />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea
            v-model:value="formModel.description"
            :auto-size="{ minRows: 2, maxRows: 4 }"
            placeholder="可选"
          />
        </a-form-item>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="CPU">
              <a-input v-model:value="formModel.cpu" placeholder="如 1 或 0.5;留空=不限" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="内存">
              <a-input v-model:value="formModel.memory" placeholder="如 512Mi / 2Gi;留空=不限" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="设为默认">
              <a-switch v-model:checked="formModel.is_default" />
              <span class="sbx-form-hint">应用未选时兜底,全局仅一条</span>
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="启用">
              <a-switch v-model:checked="formModel.enabled" />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as api from "@/api/sandboxImage";
import type { SandboxImageResp } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.SYSTEM_SETTING));

const columns = [
  { title: "名称", dataIndex: "name", key: "name", width: 180 },
  { title: "镜像", dataIndex: "image", key: "image" },
  { title: "资源", key: "resource", width: 150 },
  { title: "默认", dataIndex: "is_default", key: "is_default", width: 80 },
  { title: "状态", dataIndex: "enabled", key: "enabled", width: 90 },
  { title: "描述", dataIndex: "description", key: "description" },
  { title: "更新时间", dataIndex: "update_time", key: "update_time", width: 170 },
  { title: "操作", key: "action", width: 140 },
];

const keyword = ref("");
const list = ref<SandboxImageResp[]>([]);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const total = ref(0);

const pagination = reactive({
  current: pageNo.value,
  pageSize: pageSize.value,
  total: 0,
  showSizeChanger: true,
});

const formOpen = ref(false);
const formMode = ref<"create" | "edit">("create");
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);

const formModel = reactive({
  name: "",
  image: "",
  description: "",
  cpu: "",
  memory: "",
  is_default: false,
  enabled: true,
});

const formRules: Record<string, Rule[]> = {
  name: [{ required: true, message: "请输入名称" }],
  image: [{ required: true, message: "请输入镜像引用" }],
};

async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.pageSandboxImage({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    });
    list.value = data.data;
    total.value = data.total;
    pagination.current = pageNo.value;
    pagination.pageSize = pageSize.value;
    pagination.total = data.total;
  } finally {
    loading.value = false;
  }
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

function resetForm() {
  formModel.name = "";
  formModel.image = "";
  formModel.description = "";
  formModel.cpu = "";
  formModel.memory = "";
  formModel.is_default = false;
  formModel.enabled = true;
}

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  resetForm();
  formOpen.value = true;
}

function openEdit(record: SandboxImageResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  formModel.name = record.name;
  formModel.image = record.image;
  formModel.description = record.description ?? "";
  formModel.cpu = record.cpu ?? "";
  formModel.memory = record.memory ?? "";
  formModel.is_default = record.is_default;
  formModel.enabled = record.enabled;
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
    const body = {
      name: formModel.name,
      image: formModel.image,
      description: formModel.description || null,
      cpu: formModel.cpu || null,
      memory: formModel.memory || null,
      is_default: formModel.is_default,
      enabled: formModel.enabled,
    };
    if (formMode.value === "create") {
      await api.createSandboxImage(body);
      message.success("创建成功");
    } else if (editingId.value) {
      await api.updateSandboxImage(editingId.value, body);
      message.success("更新成功");
    }
    formOpen.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function onDelete(record: SandboxImageResp) {
  await api.deleteSandboxImage(record.id);
  message.success("已删除");
  await loadList();
}

function formatTime(ts: number) {
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

onMounted(() => {
  loadList();
});
</script>

<style scoped>
.sbx-page {
  min-height: 100%;
}

.sbx-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.sbx-search {
  max-width: 320px;
}

.sbx-table {
  background: var(--surface-base);
}

.sbx-image {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.sbx-muted {
  color: var(--color-text-tertiary);
}

.sbx-form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>
