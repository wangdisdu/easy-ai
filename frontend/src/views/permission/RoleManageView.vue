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
                  <span class="role-mini-value">{{ permissionSummary(selectedRole) }}</span>
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
                <p class="perm-card-sub">按模块分组，每个权限码覆盖一组同性质的操作。</p>
              </div>
              <span v-if="isWildcard(selectedRole)" class="perm-detail-pill role-pill">全部权限 *</span>
            </div>
            <div v-if="isWildcard(selectedRole)" class="perm-detail-placeholder">
              当前角色配置为通配符 *，自动拥有所有模块权限。
            </div>
            <template v-else>
              <div v-for="group in groupedOptions" :key="group.name" class="perm-group">
                <div class="perm-group-title">{{ group.name }}</div>
                <div class="perm-grid">
                  <div
                    v-for="opt in group.items"
                    :key="opt.code"
                    class="perm-grid-item perm-grid-item--detail"
                    :class="{ 'perm-grid-item--active': hasPermission(selectedRole, opt.code) }"
                  >
                    <div class="perm-grid-meta">
                      <span class="perm-grid-label">{{ opt.label }}</span>
                      <span class="perm-grid-desc">{{ opt.description }}</span>
                      <span class="perm-grid-code">{{ opt.code }}</span>
                    </div>
                    <span class="perm-grid-mark">
                      {{ hasPermission(selectedRole, opt.code) ? "已选" : "未选" }}
                    </span>
                  </div>
                </div>
              </div>
            </template>
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
      width="720px"
      @ok="submitForm"
    >
      <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
        <a-form-item v-if="formMode === 'create'" label="编码" name="code">
          <a-input v-model:value="formModel.code" />
        </a-form-item>
        <a-form-item label="名称" name="name">
          <a-input v-model:value="formModel.name" />
        </a-form-item>
        <a-form-item v-if="formMode === 'edit'" label="权限码">
          <a-checkbox v-model:checked="formModel.wildcard" class="perm-wildcard">
            授予全部权限（*，超级管理员）
          </a-checkbox>
          <div v-if="!formModel.wildcard" class="perm-form-groups">
            <div v-for="group in groupedOptions" :key="group.name" class="perm-group">
              <div class="perm-group-title">{{ group.name }}</div>
              <div class="perm-grid">
                <label
                  v-for="opt in group.items"
                  :key="opt.code"
                  class="perm-grid-item perm-grid-item--form"
                  :class="{ 'perm-grid-item--active': formModel.permissions.includes(opt.code) }"
                >
                  <a-checkbox
                    :checked="formModel.permissions.includes(opt.code)"
                    @change="togglePermission(opt.code)"
                  />
                  <div class="perm-grid-meta">
                    <span class="perm-grid-label">{{ opt.label }}</span>
                    <span class="perm-grid-desc">{{ opt.description }}</span>
                    <span class="perm-grid-code">{{ opt.code }}</span>
                  </div>
                </label>
              </div>
            </div>
          </div>
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
import { listPermissionOptions, type PermissionOption } from "@/api/permission";
import type { RoleResp, UserResp } from "@/api/types";

const WILDCARD = "*";

const permissionOptions = ref<PermissionOption[]>([]);

const groupedOptions = computed<{ name: string; items: PermissionOption[] }[]>(() => {
  const map = new Map<string, PermissionOption[]>();
  for (const opt of permissionOptions.value) {
    if (!map.has(opt.group)) map.set(opt.group, []);
    map.get(opt.group)!.push(opt);
  }
  return Array.from(map.entries()).map(([name, items]) => ({ name, items }));
});

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
  wildcard: false,
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

async function loadPermissionOptions() {
  const { data } = await listPermissionOptions();
  permissionOptions.value = data.data;
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

onMounted(() => {
  loadList();
  loadPermissionOptions();
});

function isWildcard(role: RoleResp) {
  return role.permissions?.includes(WILDCARD) ?? false;
}

function hasPermission(role: RoleResp, code: string) {
  if (!role.permissions) return false;
  return role.permissions.includes(WILDCARD) || role.permissions.includes(code);
}

function permissionSummary(role: RoleResp) {
  if (isWildcard(role)) return "全部权限";
  return `${role.permissions?.length ?? 0} 项`;
}

function roleSummary(role: RoleResp) {
  if (isWildcard(role)) return "拥有全部模块权限。";
  const count = role.permissions?.length ?? 0;
  return count ? `已配置 ${count} 项权限码。` : "暂未配置权限码。";
}

function togglePermission(code: string) {
  const idx = formModel.permissions.indexOf(code);
  if (idx >= 0) {
    formModel.permissions.splice(idx, 1);
  } else {
    formModel.permissions.push(code);
  }
}

function openCreate() {
  formMode.value = "create";
  editingId.value = null;
  formModel.code = "";
  formModel.name = "";
  formModel.permissions = [];
  formModel.wildcard = false;
  formOpen.value = true;
}

function openEdit(record: RoleResp) {
  formMode.value = "edit";
  editingId.value = record.id;
  formModel.code = record.code;
  formModel.name = record.name;
  const perms = record.permissions ?? [];
  formModel.wildcard = perms.includes(WILDCARD);
  formModel.permissions = formModel.wildcard ? [] : [...perms];
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
      const permissions = formModel.wildcard ? [WILDCARD] : formModel.permissions;
      await api.updateRole(editingId.value, {
        name: formModel.name,
        permissions,
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
  border-color: var(--color-info-bg-strong);
  border-left-color: var(--color-info-strong);
  background: var(--surface-info-side);
  box-shadow: var(--shadow-info-drop);
}

.role-code {
  color: var(--color-info-strong);
  background: var(--color-info-bg);
}

.role-pill {
  background: var(--color-info-bg);
  color: var(--color-info-strong);
}

.role-avatar {
  background: var(--gradient-info-corner);
  color: var(--color-info-strong);
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
  background: var(--surface-strong);
  border: 1px solid var(--color-info-bg-strong);
}

.role-mini-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
}

.role-mini-value {
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}

.perm-group + .perm-group {
  margin-top: 18px;
}

.perm-group-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  margin-bottom: 10px;
}

.perm-grid-item--detail,
.perm-grid-item--form {
  align-items: flex-start;
}

.perm-grid-item--form {
  cursor: pointer;
  gap: 10px;
}

.perm-grid-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.perm-grid-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
}

.perm-grid-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.perm-grid-code {
  font-size: 11px;
  font-family: var(--font-mono, monospace);
  color: var(--color-text-tertiary);
}

.perm-grid-item--active .perm-grid-label {
  color: var(--color-info-strong);
}

.perm-wildcard {
  margin-bottom: 12px;
}

.perm-form-groups {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
</style>
