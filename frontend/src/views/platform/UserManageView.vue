<template>
  <a-card title="用户管理" :bordered="false">
    <a-space direction="vertical" size="middle">
      <a-row :gutter="16">
        <a-col flex="auto">
          <a-input-search
            v-model:value="keyword"
            placeholder="搜索（账号、姓名、邮箱、手机）"
            allow-clear
            enter-button="查询"
            @search="onSearch"
          />
        </a-col>
        <a-col>
          <a-button type="primary" @click="openCreate">新建用户</a-button>
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
              <a-popconfirm title="确定删除该用户？" @confirm="onDelete(record)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-space>

    <a-modal
      v-model:open="detailOpen"
      title="用户详情"
      :footer="null"
      destroy-on-close
      width="640px"
    >
      <a-descriptions v-if="detail" bordered :column="1" size="small">
        <a-descriptions-item label="ID">{{ detail.id }}</a-descriptions-item>
        <a-descriptions-item label="账号">{{ detail.account }}</a-descriptions-item>
        <a-descriptions-item label="姓名">{{ detail.name ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="手机">{{ detail.phone ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="邮箱">{{ detail.email ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="部门">{{ detail.department ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatMs(detail.create_time) }}</a-descriptions-item>
        <a-descriptions-item label="更新时间">{{ formatMs(detail.update_time) }}</a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <a-modal
      v-model:open="formOpen"
      :title="formMode === 'create' ? '新建用户' : '编辑用户'"
      :confirm-loading="submitting"
      destroy-on-close
      @ok="submitForm"
    >
      <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
        <a-form-item v-if="formMode === 'create'" label="账号" name="account">
          <a-input v-model:value="formModel.account" />
        </a-form-item>
        <a-form-item v-if="formMode === 'create'" label="密码" name="passwd">
          <a-input-password v-model:value="formModel.passwd" />
        </a-form-item>
        <a-form-item label="姓名" name="name">
          <a-input v-model:value="formModel.name" />
        </a-form-item>
        <a-form-item label="手机" name="phone">
          <a-input v-model:value="formModel.phone" />
        </a-form-item>
        <a-form-item label="邮箱" name="email">
          <a-input v-model:value="formModel.email" />
        </a-form-item>
        <a-form-item label="部门" name="department">
          <a-input v-model:value="formModel.department" />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as userApi from "@/api/user";
import type { UserResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const keyword = ref("");
const list = ref<UserResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);

const detailOpen = ref(false);
const detail = ref<UserResp | null>(null);

const formOpen = ref(false);
const formMode = ref<"create" | "edit">("create");
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);

const formModel = reactive({
  account: "",
  passwd: "",
  name: "",
  phone: "",
  email: "",
  department: "",
});

const formRules: Record<string, Rule[]> = {
  account: [{ required: true, message: "请输入账号" }],
  passwd: [{ required: true, message: "请输入密码" }],
};

const columns = [
  { title: "ID", dataIndex: "id", key: "id", ellipsis: true },
  { title: "账号", dataIndex: "account", key: "account" },
  { title: "姓名", dataIndex: "name", key: "name" },
  { title: "手机", dataIndex: "phone", key: "phone" },
  { title: "邮箱", dataIndex: "email", key: "email" },
  { title: "部门", dataIndex: "department", key: "department" },
  { title: "创建时间", key: "create_time" },
  { title: "操作", key: "action", width: 220 },
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
    const { data } = await userApi.pageUser({
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

async function openDetail(record: UserResp) {
  const { data } = await userApi.getUser(record.id);
  detail.value = data.data;
  detailOpen.value = true;
}

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  Object.assign(formModel, {
    account: "",
    passwd: "",
    name: "",
    phone: "",
    email: "",
    department: "",
  });
  formOpen.value = true;
}

function openEdit(record: UserResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  Object.assign(formModel, {
    account: record.account,
    passwd: "",
    name: record.name ?? "",
    phone: record.phone ?? "",
    email: record.email ?? "",
    department: record.department ?? "",
  });
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
      await userApi.createUser({
        account: formModel.account,
        passwd: formModel.passwd,
        name: formModel.name || undefined,
        phone: formModel.phone || undefined,
        email: formModel.email || undefined,
        department: formModel.department || undefined,
      });
      message.success("创建成功");
    } else if (editingId.value) {
      await userApi.updateUser(editingId.value, {
        name: formModel.name || undefined,
        phone: formModel.phone || undefined,
        email: formModel.email || undefined,
        department: formModel.department || undefined,
      });
      message.success("更新成功");
    }
    formOpen.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function onDelete(record: UserResp) {
  await userApi.deleteUser(record.id);
  message.success("已删除");
  await loadList();
}
</script>
