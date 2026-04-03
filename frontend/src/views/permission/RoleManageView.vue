<template>
  <div>
    <section class="perm-layout">
      <div class="perm-card perm-sidebar">
        <div class="perm-card-head">
          <div>
            <h3 class="perm-card-title">角色列表</h3>
            <p class="perm-card-sub">按角色查看职责范围与权限配置。</p>
          </div>
          <a-button type="primary" class="perm-btn" @click="openCreate">新建角色</a-button>
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
            class="perm-list-item role-item"
            :class="{ 'role-item--active': selectedRoleId === item.id }"
            @click="selectedRoleId = item.id"
          >
            <div class="perm-list-item-top">
              <span class="perm-list-item-name">{{ item.name }}</span>
              <span class="perm-list-item-code role-code">{{ item.code }}</span>
            </div>
            <p class="perm-list-item-desc">{{ roleSummary(item) }}</p>
          </button>
        </div>
      </div>

      <div class="perm-detail">
        <template v-if="selectedRole">
          <section class="perm-card perm-detail-hero">
            <div class="perm-detail-hero-main">
              <div class="perm-detail-kicker">ROLE DETAIL</div>
              <div class="perm-detail-hero-top">
                <h3 class="perm-detail-title">{{ selectedRole.name }}</h3>
                <span class="perm-detail-pill role-pill">{{ selectedRole.code }}</span>
              </div>
              <p class="perm-detail-sub">{{ roleSummary(selectedRole) }}</p>
              <div class="role-meta-row">
                <div class="role-mini-card">
                  <span class="role-mini-label">权限配置</span>
                  <span class="role-mini-value">{{ selectedRole.permissions?.length ?? 0 }} 项</span>
                </div>
              </div>
            </div>
            <div class="perm-detail-actions">
              <a-button type="primary" @click="openEdit(selectedRole)">编辑角色</a-button>
              <a-popconfirm title="确定删除该角色？" @confirm="onDelete(selectedRole)">
                <a-button danger>删除角色</a-button>
              </a-popconfirm>
            </div>
          </section>

          <section class="perm-card perm-detail-panel">
            <div class="perm-card-head perm-card-head--compact">
              <div>
                <h4 class="perm-card-title">权限码</h4>
                <p class="perm-card-sub">以下为当前角色可配置的权限码。</p>
              </div>
            </div>
            <div class="perm-grid">
              <div
                v-for="permission in permissionOptions"
                :key="permission"
                class="perm-grid-item"
                :class="{ 'perm-grid-item--active': selectedRole.permissions?.includes(permission) }"
              >
                <span class="perm-grid-mark">
                  {{ selectedRole.permissions?.includes(permission) ? "已选" : "未选" }}
                </span>
                {{ permission }}
              </div>
            </div>
          </section>

          <section class="perm-card perm-detail-panel">
            <div class="perm-card-head perm-card-head--compact">
              <div>
                <h4 class="perm-card-title">人员列表</h4>
                <p class="perm-card-sub">当前已关联该角色的用户列表。</p>
              </div>
              <span class="perm-card-count">{{ roleUsers.length }} 人</span>
            </div>
            <div v-if="roleUsersLoading" class="perm-detail-placeholder">加载中...</div>
            <div v-else-if="roleUsers.length" class="perm-member-list">
              <div v-for="user in roleUsers" :key="user.id" class="perm-member-item">
                <div class="perm-member-main">
                  <span class="perm-member-avatar role-avatar">{{ (user.name || user.account).charAt(0).toUpperCase() }}</span>
                  <div class="perm-member-meta">
                    <span class="perm-member-name">{{ user.name || user.account }}</span>
                    <span class="perm-member-sub">{{ user.account }} · {{ user.department || "未分配部门" }}</span>
                  </div>
                </div>
                <span class="perm-member-contact">{{ user.phone || user.email || "-" }}</span>
              </div>
            </div>
            <div v-else class="perm-detail-placeholder">当前暂无用户关联该角色</div>
          </section>
        </template>

        <section v-else class="perm-card perm-detail-empty">
          请选择左侧角色查看详情
        </section>
      </div>
    </section>

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
        <a-form-item v-if="formMode === 'edit'" label="权限码" name="permissions">
          <a-checkbox-group v-model:value="formModel.permissions" class="perm-grid">
            <div v-for="permission in permissionOptions" :key="permission" class="perm-grid-item">
              <a-checkbox :value="permission">{{ permission }}</a-checkbox>
            </div>
          </a-checkbox-group>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as api from "@/api/role";
import type { RoleResp, UserResp } from "@/api/types";

const permissionOptions = [
  "应用工厂",
  "技能管理",
  "工具管理",
  "知识库管理",
  "系统配置",
  "权限管理",
];

const keyword = ref("");
const list = ref<RoleResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(50);
const selectedRoleId = ref<string>("");

const formOpen = ref(false);
const formMode = ref<"create" | "edit">("create");
const formRef = ref<FormInstance>();
const submitting = ref(false);
const editingId = ref<string | null>(null);
const roleUsers = ref<UserResp[]>([]);
const roleUsersLoading = ref(false);

const formModel = reactive({
  code: "",
  name: "",
  permissions: [] as string[],
});

const formRules: Record<string, Rule[]> = {
  code: [{ required: true, message: "请输入编码" }],
  name: [{ required: true, message: "请输入名称" }],
};

const selectedRole = computed(() => list.value.find((item) => item.id === selectedRoleId.value) ?? null);

watch(list, (items) => {
  if (!items.length) {
    selectedRoleId.value = "";
    return;
  }
  if (!items.some((item) => item.id === selectedRoleId.value)) {
    selectedRoleId.value = items[0].id;
  }
});

watch(selectedRoleId, (roleId) => {
  if (!roleId) {
    roleUsers.value = [];
    return;
  }
  loadRoleUsers(roleId);
}, { immediate: true });

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

async function loadRoleUsers(roleId: string) {
  roleUsersLoading.value = true;
  try {
    const { data } = await api.listRoleUsers(roleId);
    roleUsers.value = data.data;
  } finally {
    roleUsersLoading.value = false;
  }
}

function onSearch() {
  pageNo.value = 1;
  loadList();
}

onMounted(() => loadList());

function roleSummary(role: RoleResp) {
  const count = role.permissions?.length ?? 0;
  return count ? `已配置 ${count} 项权限码。` : "暂未配置权限码。";
}

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  formModel.code = "";
  formModel.name = "";
  formModel.permissions = [];
  formOpen.value = true;
}

function openEdit(record: RoleResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  formModel.code = record.code;
  formModel.name = record.name;
  formModel.permissions = [...(record.permissions ?? [])];
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
      await api.createRole({
        code: formModel.code,
        name: formModel.name,
        permissions: [],
      });
      message.success("创建成功");
    } else if (editingId.value) {
      await api.updateRole(editingId.value, {
        name: formModel.name,
        permissions: formModel.permissions,
      });
      message.success("更新成功");
    }
    formOpen.value = false;
    await loadList();
    if (selectedRoleId.value) {
      await loadRoleUsers(selectedRoleId.value);
    }
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

<style src="./perm-common.css" />

<style scoped>
.role-item:hover,
.role-item--active {
  border-color: rgba(59, 130, 246, 0.18);
  border-left-color: #2563eb;
  background: linear-gradient(90deg, rgba(219, 234, 254, 0.68) 0%, rgba(255, 255, 255, 0.7) 100%);
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.08);
}

.role-code {
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.1);
}

.role-pill {
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
}

.role-avatar {
  background: linear-gradient(135deg, #dbeafe 0%, #93c5fd 100%);
  color: #1d4ed8;
}

.role-meta-row {
  display: flex;
  gap: 12px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.role-mini-card {
  min-width: 132px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(191, 219, 254, 0.8);
}

.role-mini-label {
  font-size: 11px;
  color: #64748b;
}

.role-mini-value {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}
</style>
