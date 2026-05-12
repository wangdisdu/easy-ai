<template>
  <div class="cat-page">
    <div class="cat-toolbar">
      <a-input-search
        v-model:value="keyword"
        placeholder="搜索编码或名称"
        allow-clear
        class="cat-search"
        @search="onSearch"
      />
      <a-button v-if="canEdit" type="primary" @click="openCreate">新建分类</a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="middle"
      class="cat-table"
      @change="onTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'description'">
          <span class="cat-desc">{{ record.description || "—" }}</span>
        </template>
        <template v-else-if="column.key === 'sort_order'">
          <span class="cat-sort">{{ record.sort_order }}</span>
        </template>
        <template v-else-if="column.key === 'update_time'">
          {{ formatTime(record.update_time) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button v-if="canEdit" type="link" size="small" @click="openEdit(record)">编辑</a-button>
          <a-popconfirm
            v-if="canEdit"
            title="确定删除该分类？被引用时无法删除。"
            @confirm="onDelete(record)"
          >
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
          <span v-if="!canEdit" class="cat-desc">—</span>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="formOpen"
      :title="formMode === 'create' ? '新建分类' : '编辑分类'"
      :confirm-loading="submitting"
      destroy-on-close
      @ok="submitForm"
    >
      <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
        <a-form-item label="编码" name="code">
          <a-input
            v-model:value="formModel.code"
            :disabled="formMode === 'edit'"
            placeholder="英文/数字/中划线，作为业务标识"
          />
        </a-form-item>
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formModel.name" placeholder="展示名" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea
            v-model:value="formModel.description"
            :auto-size="{ minRows: 2, maxRows: 4 }"
            placeholder="可选"
          />
        </a-form-item>
        <a-form-item label="排序权重" name="sort_order">
          <a-input-number v-model:value="formModel.sort_order" :min="0" :step="1" />
          <span class="cat-form-hint">数值越小越靠前</span>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as api from "@/api/appCategory";
import type { AppCategoryResp } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.SYSTEM_SETTING));

const columns = [
  { title: "编码", dataIndex: "code", key: "code", width: 200 },
  { title: "名称", dataIndex: "name", key: "name", width: 200 },
  { title: "描述", dataIndex: "description", key: "description" },
  { title: "排序", dataIndex: "sort_order", key: "sort_order", width: 90 },
  { title: "更新时间", dataIndex: "update_time", key: "update_time", width: 180 },
  { title: "操作", key: "action", width: 140 },
];

const keyword = ref("");
const list = ref<AppCategoryResp[]>([]);
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
  code: "",
  name: "",
  description: "",
  sort_order: 0,
});

const formRules: Record<string, Rule[]> = {
  code: [{ required: true, message: "请输入编码" }],
  name: [{ required: true, message: "请输入名称" }],
};

async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.pageAppCategory({
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

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  formModel.code = "";
  formModel.name = "";
  formModel.description = "";
  formModel.sort_order = 0;
  formOpen.value = true;
}

function openEdit(record: AppCategoryResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  formModel.code = record.code;
  formModel.name = record.name;
  formModel.description = record.description ?? "";
  formModel.sort_order = record.sort_order;
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
    if (formMode.value === "create") {
      await api.createAppCategory({
        code: formModel.code,
        name: formModel.name,
        description: formModel.description || null,
        sort_order: formModel.sort_order,
      });
      message.success("创建成功");
    } else if (editingId.value) {
      await api.updateAppCategory(editingId.value, {
        name: formModel.name,
        description: formModel.description || null,
        sort_order: formModel.sort_order,
      });
      message.success("更新成功");
    }
    formOpen.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function onDelete(record: AppCategoryResp) {
  await api.deleteAppCategory(record.id);
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
.cat-page {
  min-height: 100%;
}

.cat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.cat-search {
  max-width: 320px;
}

.cat-table {
  background: var(--surface-base);
}

.cat-desc {
  color: var(--color-text-secondary);
}

.cat-sort {
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.cat-form-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
</style>
