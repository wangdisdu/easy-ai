<template>
  <a-card title="用户组管理" :bordered="false">
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
          <a-button type="primary" @click="openCreate">新建用户组</a-button>
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
          <template v-if="column.key === 'create_time'">
            {{ formatMs(record.create_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openDetail(record)">详情</a-button>
              <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
              <a-popconfirm title="确定删除该用户组？" @confirm="onDelete(record)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-space>

    <a-modal v-model:open="detailOpen" title="用户组详情" :footer="null" destroy-on-close width="560px">
      <a-descriptions v-if="detail" bordered :column="1" size="small">
        <a-descriptions-item label="ID">{{ detail.id }}</a-descriptions-item>
        <a-descriptions-item label="编码">{{ detail.code }}</a-descriptions-item>
        <a-descriptions-item label="名称">{{ detail.name }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatMs(detail.create_time) }}</a-descriptions-item>
        <a-descriptions-item label="更新时间">{{ formatMs(detail.update_time) }}</a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <a-modal
      v-model:open="formOpen"
      :title="formMode === 'create' ? '新建用户组' : '编辑用户组'"
      :confirm-loading="submitting"
      destroy-on-close
      @ok="submitForm"
    >
      <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
        <a-form-item v-if="formMode === 'create'" label="编码" name="code">
          <a-input v-model:value="formModel.code" />
        </a-form-item>
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formModel.name" />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as api from "@/api/userGroup";
import type { UserGroupResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const keyword = ref("");
const list = ref<UserGroupResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);

const detailOpen = ref(false);
const detail = ref<UserGroupResp | null>(null);

const formOpen = ref(false);
const formMode = ref<"create" | "edit">("create");
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);

const formModel = reactive({ code: "", name: "" });

const formRules: Record<string, Rule[]> = {
  code: [{ required: true, message: "请输入编码" }],
  name: [{ required: true, message: "请输入名称" }],
};

const columns = [
  { title: "ID", dataIndex: "id", key: "id", ellipsis: true },
  { title: "编码", dataIndex: "code", key: "code" },
  { title: "名称", dataIndex: "name", key: "name" },
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
    const { data } = await api.pageUserGroup({
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

async function openDetail(record: UserGroupResp) {
  const { data } = await api.getUserGroup(record.id);
  detail.value = data.data;
  detailOpen.value = true;
}

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  formModel.code = "";
  formModel.name = "";
  formOpen.value = true;
}

function openEdit(record: UserGroupResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  formModel.code = record.code;
  formModel.name = record.name;
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
      await api.createUserGroup({ code: formModel.code, name: formModel.name });
      message.success("创建成功");
    } else if (editingId.value) {
      await api.updateUserGroup(editingId.value, { name: formModel.name });
      message.success("更新成功");
    }
    formOpen.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function onDelete(record: UserGroupResp) {
  await api.deleteUserGroup(record.id);
  message.success("已删除");
  await loadList();
}
</script>
