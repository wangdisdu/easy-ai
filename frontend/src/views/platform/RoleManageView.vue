<template>
  <a-card title="角色管理" :bordered="false">
    <a-space direction="vertical" size="middle">
      <a-row :gutter="16">
        <a-col flex="auto">
          <a-input-search
            v-model:value="keyword"
            placeholder="搜索（编码、名称）"
            allow-clear
            enter-button="查询"
            @search="onSearch"
          />
        </a-col>
        <a-col>
          <a-button type="primary" @click="openCreate">新建角色</a-button>
        </a-col>
      </a-row>

      <a-table
        row-key="id"
        :columns="columns"
        :data-source="list"
        :loading="loading"
        :pagination="pagination"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'permissions'">
            {{ record.permissions?.join(", ") || "-" }}
          </template>
          <template v-else-if="column.key === 'create_time'">
            {{ formatMs(record.create_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openDetail(record)">详情</a-button>
              <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
              <a-popconfirm title="确定删除该角色？" @confirm="onDelete(record)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-space>

    <a-modal v-model:open="detailOpen" title="角色详情" :footer="null" destroy-on-close width="640px">
      <a-descriptions v-if="detail" bordered :column="1" size="small">
        <a-descriptions-item label="ID">{{ detail.id }}</a-descriptions-item>
        <a-descriptions-item label="编码">{{ detail.code }}</a-descriptions-item>
        <a-descriptions-item label="名称">{{ detail.name }}</a-descriptions-item>
        <a-descriptions-item label="权限码">{{ detail.permissions?.join(", ") || "-" }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatMs(detail.create_time) }}</a-descriptions-item>
        <a-descriptions-item label="更新时间">{{ formatMs(detail.update_time) }}</a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <a-modal
      v-model:open="formOpen"
      :title="formMode === 'create' ? '新建角色' : '编辑角色'"
      :confirm-loading="submitting"
      destroy-on-close
      width="640px"
      @ok="submitForm"
    >
      <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
        <a-form-item v-if="formMode === 'create'" label="编码" name="code">
          <a-input v-model:value="formModel.code" />
        </a-form-item>
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formModel.name" />
        </a-form-item>
        <a-form-item label="权限码" name="permissionsText">
          <a-textarea
            v-model:value="formModel.permissionsText"
            :rows="4"
            placeholder='JSON 数组，例如 ["user:read","user:write"]'
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as api from "@/api/role";
import type { RoleResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const keyword = ref("");
const list = ref<RoleResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);

const detailOpen = ref(false);
const detail = ref<RoleResp | null>(null);

const formOpen = ref(false);
const formMode = ref<"create" | "edit">("create");
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);

const formModel = reactive({
  code: "",
  name: "",
  permissionsText: "[]",
});

function parsePermissions(text: string): string[] {
  const t = text.trim();
  if (!t) return [];
  try {
    const v = JSON.parse(t) as unknown;
    if (!Array.isArray(v)) throw new Error("not array");
    return v.map(String);
  } catch {
    throw new Error("权限码需为 JSON 数组");
  }
}

const formRules: Record<string, Rule[]> = {
  code: [{ required: true, message: "请输入编码" }],
  name: [{ required: true, message: "请输入名称" }],
  permissionsText: [
    {
      validator: async (_rule, value: string) => {
        try {
          parsePermissions(value || "[]");
        } catch (e) {
          throw new Error(e instanceof Error ? e.message : "格式错误");
        }
      },
    },
  ],
};

const columns = [
  { title: "ID", dataIndex: "id", key: "id", ellipsis: true },
  { title: "编码", dataIndex: "code", key: "code" },
  { title: "名称", dataIndex: "name", key: "name" },
  { title: "权限码", key: "permissions", ellipsis: true },
  { title: "创建时间", key: "create_time" },
  { title: "操作", key: "action", width: 200 },
];

const pagination = computed(() => ({
  current: pageNo.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
}));

async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.pageRole({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
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

function onTableChange(pag: { current?: number; pageSize?: number }) {
  pageNo.value = pag.current ?? 1;
  pageSize.value = pag.pageSize ?? 20;
  loadList();
}

onMounted(() => loadList());

async function openDetail(record: RoleResp) {
  const { data } = await api.getRole(record.id);
  detail.value = data.data;
  detailOpen.value = true;
}

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  formModel.code = "";
  formModel.name = "";
  formModel.permissionsText = "[]";
  formOpen.value = true;
}

function openEdit(record: RoleResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  formModel.code = record.code;
  formModel.name = record.name;
  formModel.permissionsText = JSON.stringify(record.permissions ?? []);
  formOpen.value = true;
}

async function submitForm() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  let permissions: string[];
  try {
    permissions = parsePermissions(formModel.permissionsText);
  } catch (e) {
    message.error(e instanceof Error ? e.message : "权限码格式错误");
    return;
  }
  submitting.value = true;
  try {
    if (formMode.value === "create") {
      await api.createRole({
        code: formModel.code,
        name: formModel.name,
        permissions,
      });
      message.success("创建成功");
    } else if (editingId.value) {
      await api.updateRole(editingId.value, {
        name: formModel.name,
        permissions,
      });
      message.success("更新成功");
    }
    formOpen.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function onDelete(record: RoleResp) {
  await api.deleteRole(record.id);
  message.success("已删除");
  await loadList();
}
</script>
