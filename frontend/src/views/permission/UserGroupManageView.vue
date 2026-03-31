<template>
  <div>
    <section class="perm-layout">
      <div class="perm-card perm-sidebar">
        <div class="perm-card-head">
          <div>
            <h3 class="perm-card-title">用户组列表</h3>
            <p class="perm-card-sub">按用户组组织企业成员的访问边界。</p>
          </div>
          <a-button type="primary" class="perm-btn" @click="openCreate">新建用户组</a-button>
        </div>
        <a-input-search
          v-model:value="keyword"
          placeholder="搜索编码或名称"
          allow-clear
          class="perm-search"
          @search="onSearch"
        />
        <div class="perm-list">
          <button
            v-for="item in list"
            :key="item.id"
            type="button"
            class="perm-list-item group-item"
            :class="{ 'group-item--active': selectedGroupId === item.id }"
            @click="selectedGroupId = item.id"
          >
            <div class="perm-list-item-top">
              <span class="perm-list-item-name">{{ item.name }}</span>
              <span class="perm-list-item-code group-code">{{ item.code }}</span>
            </div>
            <p class="perm-list-item-desc">{{ groupSummary(item) }}</p>
          </button>
        </div>
      </div>

      <div class="perm-detail">
        <template v-if="selectedGroup">
          <section class="perm-card perm-detail-hero">
            <div class="perm-detail-hero-main">
              <div class="perm-detail-kicker">GROUP DETAIL</div>
              <div class="perm-detail-hero-top">
                <h3 class="perm-detail-title">{{ selectedGroup.name }}</h3>
                <span class="perm-detail-pill group-pill">{{ selectedGroup.code }}</span>
              </div>
              <p class="perm-detail-sub">{{ groupSummary(selectedGroup) }}</p>
            </div>
            <div class="perm-detail-actions">
              <a-button @click="openAddMember">增加成员</a-button>
              <a-button type="primary" @click="openEdit(selectedGroup)">编辑用户组</a-button>
              <a-popconfirm title="确定删除该用户组？" @confirm="onDelete(selectedGroup)">
                <a-button danger>删除用户组</a-button>
              </a-popconfirm>
            </div>
          </section>

          <section class="perm-card perm-detail-panel">
            <div class="perm-card-head perm-card-head--compact">
              <div>
                <h4 class="perm-card-title">成员列表</h4>
                <p class="perm-card-sub">当前选中用户组的人员列表。</p>
              </div>
              <span class="perm-card-count">{{ groupMembers.length }} 人</span>
            </div>
            <div v-if="groupMembersLoading" class="perm-detail-placeholder">加载中...</div>
            <div v-else-if="groupMembers.length" class="perm-member-list">
              <div v-for="user in groupMembers" :key="user.id" class="perm-member-item">
                <div class="perm-member-main">
                  <span class="perm-member-avatar group-avatar">{{ (user.name || user.account).charAt(0).toUpperCase() }}</span>
                  <div class="perm-member-meta">
                    <span class="perm-member-name">{{ user.name || user.account }}</span>
                    <span class="perm-member-sub">{{ user.account }} · {{ user.department || "未分配部门" }}</span>
                  </div>
                </div>
                <div class="perm-member-actions">
                  <span class="perm-member-contact">{{ user.phone || user.email || "-" }}</span>
                  <a-popconfirm title="确定移除该成员？" @confirm="onRemoveMember(user.id)">
                    <a-button type="link" danger size="small">移除</a-button>
                  </a-popconfirm>
                </div>
              </div>
            </div>
            <div v-else class="perm-detail-placeholder">当前用户组暂无成员</div>
          </section>
        </template>

        <section v-else class="perm-card perm-detail-empty">
          请选择左侧用户组查看详情
        </section>
      </div>
    </section>

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

    <a-modal
      v-model:open="memberOpen"
      title="增加成员"
      :confirm-loading="memberSubmitting"
      destroy-on-close
      @ok="submitAddMember"
    >
      <a-form layout="vertical">
        <a-form-item label="选择用户">
          <a-select
            v-model:value="pendingUserId"
            show-search
            :options="availableUserOptions"
            :loading="userOptionsLoading"
            placeholder="请选择要加入当前用户组的用户"
            option-filter-prop="label"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as userApi from "@/api/user";
import * as api from "@/api/userGroup";
import type { UserGroupResp, UserResp } from "@/api/types";

const keyword = ref("");
const list = ref<UserGroupResp[]>([]);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(50);
const selectedGroupId = ref<string>("");

const formOpen = ref(false);
const formMode = ref<"create" | "edit">("create");
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);
const memberOpen = ref(false);
const memberSubmitting = ref(false);
const pendingUserId = ref<string>();
const userOptionsLoading = ref(false);
const groupMembers = ref<UserResp[]>([]);
const groupMembersLoading = ref(false);
const allUsers = ref<UserResp[]>([]);

const formModel = reactive({ code: "", name: "" });

const formRules: Record<string, Rule[]> = {
  code: [{ required: true, message: "请输入编码" }],
  name: [{ required: true, message: "请输入名称" }],
};

const selectedGroup = computed(() => list.value.find((item) => item.id === selectedGroupId.value) ?? null);
const availableUserOptions = computed(() => {
  const memberIds = new Set(groupMembers.value.map((item) => item.id));
  return allUsers.value
    .filter((user) => !memberIds.has(user.id))
    .map((user) => ({
      label: `${user.name || user.account} (${user.account})`,
      value: user.id,
    }));
});

watch(list, (items) => {
  if (!items.length) {
    selectedGroupId.value = "";
    return;
  }
  if (!items.some((item) => item.id === selectedGroupId.value)) {
    selectedGroupId.value = items[0].id;
  }
});

watch(selectedGroupId, (groupId) => {
  if (!groupId) {
    groupMembers.value = [];
    return;
  }
  loadGroupMembers(groupId);
}, { immediate: true });

async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.pageUserGroup({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
    });
    list.value = data.data;
  } finally {
    loading.value = false;
  }
}

async function loadAllUsers() {
  userOptionsLoading.value = true;
  try {
    const { data } = await userApi.pageUser({
      page_no: 1,
      page_size: 1000,
      keyword: undefined,
    });
    allUsers.value = data.data;
  } finally {
    userOptionsLoading.value = false;
  }
}

async function loadGroupMembers(groupId: string) {
  groupMembersLoading.value = true;
  try {
    const { data } = await api.listUserGroupMembers(groupId);
    groupMembers.value = data.data;
  } finally {
    groupMembersLoading.value = false;
  }
}

function onSearch() {
  pageNo.value = 1;
  loadList();
}

onMounted(async () => {
  await Promise.all([loadList(), loadAllUsers()]);
});

function groupSummary(group: UserGroupResp) {
  return `编码 ${group.code}，用于统一管理成员归属与访问范围。`;
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

function openAddMember() {
  pendingUserId.value = undefined;
  memberOpen.value = true;
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

async function submitAddMember() {
  if (!selectedGroupId.value || !pendingUserId.value) {
    message.warning("请选择用户");
    return;
  }
  memberSubmitting.value = true;
  try {
    await api.addUserGroupMember(selectedGroupId.value, { user_id: pendingUserId.value });
    message.success("添加成功");
    memberOpen.value = false;
    await loadGroupMembers(selectedGroupId.value);
  } finally {
    memberSubmitting.value = false;
  }
}

async function onRemoveMember(userId: string) {
  if (!selectedGroupId.value) return;
  await api.removeUserGroupMember(selectedGroupId.value, userId);
  message.success("已移除");
  await loadGroupMembers(selectedGroupId.value);
}

async function onDelete(record: UserGroupResp) {
  await api.deleteUserGroup(record.id);
  message.success("已删除");
  await loadList();
}
</script>

<style src="./perm-common.css" />

<style scoped>
.group-item:hover,
.group-item--active {
  border-color: rgba(13, 148, 136, 0.18);
  border-left-color: #0f766e;
  background: linear-gradient(90deg, rgba(204, 251, 241, 0.68) 0%, rgba(255, 255, 255, 0.7) 100%);
  box-shadow: 0 14px 28px rgba(13, 148, 136, 0.08);
}

.group-code {
  color: #0f766e;
  background: rgba(20, 184, 166, 0.1);
}

.group-pill {
  background: rgba(20, 184, 166, 0.12);
  color: #0f766e;
}

.group-avatar {
  background: linear-gradient(135deg, #ccfbf1 0%, #5eead4 100%);
  color: #0f766e;
}
</style>
