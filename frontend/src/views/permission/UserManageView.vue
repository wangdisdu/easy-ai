<template>
  <div>
    <section class="perm-card user-card">
      <div class="perm-card-head">
        <div>
          <h3 class="perm-card-title">用户列表</h3>
          <p class="perm-card-sub">统一查看用户账号、角色、归属部门与基础身份信息。</p>
        </div>
        <div class="user-toolbar">
          <a-input-search
            v-model:value="keyword"
            placeholder="搜索账号、姓名、邮箱、手机"
            allow-clear
            style="width: 320px"
            @search="onSearch"
          />
          <a-button type="primary" class="perm-btn" @click="openCreateForm">新建用户</a-button>
        </div>
      </div>

      <a-table
        row-key="id"
        class="perm-table"
        :columns="columns"
        :data-source="list"
        :loading="loading"
        :pagination="pagination"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'account'">
            <div class="user-cell">
              <span class="user-avatar">{{ (record.name || record.account).charAt(0).toUpperCase() }}</span>
              <div class="user-meta">
                <span class="user-name">{{ record.name || "未命名用户" }}</span>
                <span class="user-sub">{{ record.account }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'contact'">
            <div class="user-meta">
              <span>{{ record.email || "-" }}</span>
              <span class="user-sub">{{ record.phone || "-" }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'roles'">
            <div class="user-chips">
              <span v-for="role in record.roles || []" :key="role.id" class="user-chip">
                {{ role.name }}
              </span>
              <span v-if="!(record.roles || []).length" class="user-sub">未关联角色</span>
            </div>
          </template>
          <template v-else-if="column.key === 'department'">
            <span class="user-chip">{{ record.department || "未分配部门" }}</span>
          </template>
          <template v-else-if="column.key === 'create_time'">
            {{ formatMs(record.create_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <a-space :size="4">
              <a-button type="link" size="small" @click="openDetail(record)">详情</a-button>
              <a-button type="link" size="small" @click="openEditForm(record)">编辑</a-button>
              <a-popconfirm title="确定删除该用户？" @confirm="onDelete(record)">
                <a-button type="link" size="small" danger>删除</a-button>
              </a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </section>

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
        <a-descriptions-item label="角色">{{ detail.roles?.map((item) => item.name).join("、") || "-" }}</a-descriptions-item>
        <a-descriptions-item label="手机">{{ detail.phone ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="邮箱">{{ detail.email ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="部门">{{ detail.department ?? "-" }}</a-descriptions-item>
        <a-descriptions-item label="创建时间">{{ formatMs(detail.create_time) }}</a-descriptions-item>
        <a-descriptions-item label="更新时间">{{ formatMs(detail.update_time) }}</a-descriptions-item>
      </a-descriptions>
    </a-modal>

    <a-modal
      v-model:open="formOpen"
      :title="isEdit ? '编辑用户' : '新建用户'"
      :confirm-loading="submitting"
      destroy-on-close
      :force-render="true"
      @ok="submitForm"
    >
      <a-form
        ref="formRef"
        :model="formModel"
        :rules="formRules"
        layout="vertical"
      >
        <a-form-item v-if="!isEdit" label="账号" name="account">
          <a-input v-model:value="formModel.account" />
        </a-form-item>
        <a-form-item v-if="!isEdit" label="密码" name="passwd">
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
        <a-form-item label="关联角色" name="roleIds">
          <a-select
            v-model:value="formModel.roleIds"
            mode="multiple"
            :options="roleOptions"
            :loading="roleLoading"
            placeholder="请选择角色"
            option-filter-prop="label"
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
import * as roleApi from "@/api/role";
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
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);
const isEdit = computed(() => editingId.value !== null);

const roleLoading = ref(false);
const roleOptions = ref<{ label: string; value: string }[]>([]);

const emptyForm = () => ({
  account: "",
  passwd: "",
  name: "",
  phone: "",
  email: "",
  department: "",
  roleIds: [] as string[],
});

const formModel = reactive(emptyForm());

const formRules = computed<Record<string, Rule[]>>(() => ({
  account: isEdit.value ? [] : [{ required: true, message: "请输入账号" }],
  passwd: isEdit.value ? [] : [{ required: true, message: "请输入密码" }],
  name: [{ required: true, message: "请输入姓名" }],
}));

const columns = [
  { title: "用户", key: "account", width: 220 },
  { title: "联系方式", key: "contact", width: 220 },
  { title: "关联角色", key: "roles", width: 240 },
  { title: "部门", key: "department", width: 180 },
  { title: "创建时间", key: "create_time", width: 180 },
  { title: "操作", key: "action", width: 180, fixed: "right" },
];

const pagination = computed(() => ({
  current: pageNo.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
  showLessItems: true,
}));

async function loadRoles() {
  roleLoading.value = true;
  try {
    const { data } = await roleApi.listRole();
    roleOptions.value = data.data.map((item) => ({
      label: `${item.name} (${item.code})`,
      value: item.id,
    }));
  } finally {
    roleLoading.value = false;
  }
}

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

onMounted(async () => {
  await Promise.all([loadList(), loadRoles()]);
});

async function openDetail(record: UserResp) {
  const { data } = await userApi.getUser(record.id);
  detail.value = data.data;
  detailOpen.value = true;
}

function openCreateForm() {
  editingId.value = null;
  Object.assign(formModel, emptyForm());
  formOpen.value = true;
}

async function openEditForm(record: UserResp) {
  editingId.value = record.id;
  const { data } = await userApi.getUser(record.id);
  const user = data.data;
  Object.assign(formModel, emptyForm(), {
    account: user.account,
    name: user.name ?? "",
    phone: user.phone ?? "",
    email: user.email ?? "",
    department: user.department ?? "",
    roleIds: (user.roles ?? []).map((r) => r.id),
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
    const payload = {
      name: formModel.name || undefined,
      phone: formModel.phone || undefined,
      email: formModel.email || undefined,
      department: formModel.department || undefined,
      role_ids: formModel.roleIds,
    };

    if (isEdit.value) {
      await userApi.updateUser(editingId.value!, payload);
      message.success("更新成功");
    } else {
      await userApi.createUser({
        account: formModel.account,
        passwd: formModel.passwd,
        ...payload,
      });
      message.success("创建成功");
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

<style src="./perm-common.css" />

<style scoped>
.user-card {
  background:
    radial-gradient(circle at top right, var(--color-info-bg), transparent 26%),
    var(--surface-card-bg);
  padding: 20px;
}

.perm-card-head { margin-bottom: 18px; }

.user-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: var(--gradient-info-corner);
  color: var(--color-info-strong);
  font-size: 14px;
  font-weight: 700;
  box-shadow: inset 0 1px 0 var(--surface-trigger-inset);
}

.user-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.user-name {
  font-weight: 600;
  color: var(--color-text);
}

.user-sub {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.user-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-bg-strong);
  color: var(--color-info-strong);
  font-size: 12px;
  font-weight: 600;
}

@media (max-width: 960px) {
  .perm-card-head { flex-direction: column; }
  .user-toolbar {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }
  .user-toolbar :deep(.ant-input-search) { width: 100% !important; }
}
</style>
