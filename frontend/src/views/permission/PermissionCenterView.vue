<template>
  <div class="permission-center-page">
    <div class="permission-center-head">
      <div>
        <h2 class="permission-center-title">权限中心</h2>
        <p class="permission-center-sub">企业级 RBAC 权限管理，统一管理用户、角色与用户组访问边界。</p>
      </div>
    </div>

    <a-tabs
      :active-key="activeTab"
      size="large"
      class="permission-center-tabs"
      @change="onTabChange"
    >
      <a-tab-pane key="users" tab="用户管理">
        <UserManageView />
      </a-tab-pane>
      <a-tab-pane key="roles" tab="角色管理">
        <RoleManageView />
      </a-tab-pane>
      <a-tab-pane key="user-groups" tab="用户组">
        <UserGroupManageView />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import UserManageView from "@/views/permission/UserManageView.vue";
import RoleManageView from "@/views/permission/RoleManageView.vue";
import UserGroupManageView from "@/views/permission/UserGroupManageView.vue";

type TabKey = "users" | "roles" | "user-groups";

const route = useRoute();
const router = useRouter();
const tabKeys: TabKey[] = ["users", "roles", "user-groups"];

const activeTab = computed<TabKey>(() => {
  const tab = route.query.tab;
  if (typeof tab === "string" && tabKeys.includes(tab as TabKey)) {
    return tab as TabKey;
  }
  return "users";
});

function onTabChange(tab: string) {
  router.replace({
    path: route.path,
    query: { ...route.query, tab },
  });
}
</script>

<style scoped>
.permission-center-page {
  min-height: 100%;
}

.permission-center-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.permission-center-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.permission-center-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.permission-center-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 20px;
}

.permission-center-tabs :deep(.ant-tabs-nav::before) {
  border-bottom-color: rgba(148, 163, 184, 0.16);
}

.permission-center-tabs :deep(.ant-tabs-tab) {
  padding: 10px 4px 12px;
  color: #64748b;
  font-weight: 500;
}

.permission-center-tabs :deep(.ant-tabs-tab:hover) {
  color: #334155;
}

.permission-center-tabs :deep(.ant-tabs-tab.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: #1677ff;
}

.permission-center-tabs :deep(.ant-tabs-ink-bar) {
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, #1677ff 0%, #7c3aed 100%);
}

.permission-center-tabs :deep(.ant-tabs-content-holder) {
  min-height: 0;
}
</style>
