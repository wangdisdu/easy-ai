<template>
  <a-layout class="app-layout-root" has-sider>
    <a-layout-sider
      v-model:collapsed="collapsed"
      collapsible
      :trigger="null"
      theme="light"
      :width="220"
      :collapsed-width="56"
      class="app-layout-sider"
    >
      <div class="sider-brand">
        <div class="sider-brand-main" @click="onBrandClick">
          <span class="sider-brand-icon">
            <ThunderboltOutlined />
          </span>
          <span v-if="!collapsed" class="sider-brand-text">easy-ai</span>
        </div>
      </div>
      <a-menu
        v-model:selected-keys="selectedKeys"
        v-model:open-keys="openKeys"
        theme="light"
        mode="inline"
        class="app-side-menu"
        :get-popup-container="menuPopupContainer"
        @click="onMenuClick"
      >
        <a-sub-menu v-for="group in menuGroups" :key="group.key">
          <template #icon><component :is="resolveIcon(group.iconKey)" /></template>
          <template #title>{{ group.title }}</template>
          <a-menu-item v-for="item in group.items" :key="item.path">
            <template #icon><component :is="resolveIcon(item.iconKey)" /></template>
            {{ item.title }}
          </a-menu-item>
        </a-sub-menu>
      </a-menu>

      <div class="sider-footer">
        <button
          type="button"
          class="sider-collapse-btn"
          @click.stop="collapsed = !collapsed"
        >
          <RightOutlined v-if="collapsed" />
          <LeftOutlined v-else />
          <span v-if="!collapsed">收起菜单</span>
        </button>
      </div>
    </a-layout-sider>
    <a-layout class="app-layout-main">
      <a-layout-header class="app-layout-header">
        <a-row align="middle" justify="space-between" :wrap="false" class="header-row">
          <a-col flex="auto" class="header-left">
            <a-breadcrumb v-if="breadcrumbItems.length" class="header-breadcrumb">
              <a-breadcrumb-item v-for="(t, i) in breadcrumbItems" :key="i">
                {{ t }}
              </a-breadcrumb-item>
            </a-breadcrumb>
          </a-col>
          <a-col flex="none" class="header-user">
            <a-dropdown>
              <a-button type="text">
                {{ auth.user?.account ?? "用户" }}
                <DownOutlined />
              </a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="logout" @click="onLogout">退出登录</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </a-col>
        </a-row>
      </a-layout-header>
      <a-layout-content class="app-layout-content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter, type RouteRecordNormalized } from "vue-router";
import {
  AppstoreOutlined,
  DownOutlined,
  LeftOutlined,
  RightOutlined,
  SafetyOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons-vue";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

type IconKey = "appstore" | "user" | "team" | "safety";
type MenuMeta = {
  groupKey: string;
  groupTitle: string;
  groupIcon: IconKey;
  itemTitle: string;
  itemIcon: IconKey;
};
type MenuItem = {
  path: string;
  title: string;
  iconKey: IconKey;
};
type MenuGroup = {
  key: string;
  title: string;
  iconKey: IconKey;
  items: MenuItem[];
};

const iconMap: Record<IconKey, unknown> = {
  appstore: AppstoreOutlined,
  user: UserOutlined,
  team: TeamOutlined,
  safety: SafetyOutlined,
};

function resolveIcon(iconKey: IconKey) {
  return iconMap[iconKey];
}

const breadcrumbItems = computed(() => {
  const raw = route.meta.breadcrumb;
  return Array.isArray(raw) ? (raw as string[]) : [];
});

const menuGroups = computed<MenuGroup[]>(() => {
  const groups = new Map<string, MenuGroup>();
  const records = router
    .getRoutes()
    .filter((r: RouteRecordNormalized) => Boolean((r.meta as { menu?: MenuMeta }).menu));

  for (const record of records) {
    const menu = (record.meta as { menu?: MenuMeta }).menu;
    if (!menu) continue;

    if (!groups.has(menu.groupKey)) {
      groups.set(menu.groupKey, {
        key: menu.groupKey,
        title: menu.groupTitle,
        iconKey: menu.groupIcon,
        items: [],
      });
    }

    groups.get(menu.groupKey)?.items.push({
      path: record.path,
      title: menu.itemTitle,
      iconKey: menu.itemIcon,
    });
  }

  return [...groups.values()];
});

function getGroupKeyByPath(path: string): string | undefined {
  for (const group of menuGroups.value) {
    if (group.items.some((item) => item.path === path)) {
      return group.key;
    }
  }
  return undefined;
}

const collapsed = ref(false);
const selectedKeys = ref<string[]>([route.path]);
const initialOpenKey = getGroupKeyByPath(route.path);
const openKeys = ref<string[]>(initialOpenKey ? [initialOpenKey] : []);
/** 侧栏折叠时收起 openKeys，避免受控 openKeys 与弹出子菜单冲突 */
const openKeysWhenExpanded = ref<string[]>(initialOpenKey ? [initialOpenKey] : []);

function menuPopupContainer() {
  return document.body;
}

watch(collapsed, (isCollapsed) => {
  if (isCollapsed) {
    openKeysWhenExpanded.value = [...openKeys.value];
    openKeys.value = [];
  } else {
    openKeys.value = [...openKeysWhenExpanded.value];
  }
});

watch(
  () => route.path,
  (p) => {
    selectedKeys.value = [p];
    if (!collapsed.value) {
      const key = getGroupKeyByPath(p);
      if (key) {
        openKeys.value = [key];
      }
    }
  },
  { immediate: true },
);

watch(openKeys, (keys) => {
  if (!collapsed.value) {
    openKeysWhenExpanded.value = [...keys];
  }
});

function onMenuClick({ key }: { key: string | number }) {
  router.push(String(key));
}

/** 顶部 Logo 点击：展开/收起侧栏 */
function onBrandClick() {
  collapsed.value = !collapsed.value;
}

async function onLogout() {
  auth.logout();
  await router.push("/login");
}

auth.loadProfile().catch(async () => {
  auth.logout();
  await router.replace({ path: "/login", query: { redirect: route.fullPath } });
});
</script>

<style scoped>
/* ===================== App Menu ===================== */

/* ===================== App Layout ===================== */
.app-layout-root.ant-layout {
  min-height: 100vh;
}

.app-layout-sider {
  border-right: 1px solid rgba(5, 5, 5, 0.06);
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.55);
}

.app-layout-sider :deep(.ant-layout-sider-children) {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.sider-brand {
  height: 50px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  background: linear-gradient(90deg, rgba(22, 119, 255, 0.2), rgba(22, 119, 255, 0.01));
}

.sider-brand-main {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 10px;
  padding: 6px 8px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s ease;
}

.sider-brand-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #1677ff;
  background: rgba(22, 119, 255, 0.12);
}

.sider-brand-text {
  font-size: 14px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.88);
  letter-spacing: 0.01em;
}

.app-side-menu {
  flex: 1;
  border-inline-end: 0 !important;
  background: transparent;
  padding: 6px 0;
}

.app-side-menu :deep(.ant-menu-submenu-title) {
  height: 38px;
  line-height: 38px;
  font-weight: 600;
}

.app-side-menu :deep(.ant-menu-submenu-title .ant-menu-title-content) {
  letter-spacing: 0.01em;
}

.app-side-menu :deep(.ant-menu-submenu-title:hover),
.app-side-menu :deep(.ant-menu-item:hover) {
  background: rgba(22, 119, 255, 0.08) !important;
}

.app-side-menu :deep(.ant-menu-sub.ant-menu-inline) {
  margin-top: 4px;
  margin-bottom: 6px;
  margin-left: 10px;
  padding: 4px 0 4px 10px;
  background: transparent !important;
}

.app-side-menu :deep(.ant-menu-sub),
.app-side-menu :deep(.ant-menu-inline .ant-menu-submenu),
.app-side-menu :deep(.ant-menu-submenu .ant-menu) {
  background: transparent !important;
}

.app-side-menu :deep(.ant-menu-sub .ant-menu-item) {
  height: 34px;
  line-height: 34px;
  margin: 2px 0;
  font-weight: 400;
  color: rgba(0, 0, 0, 0.72);
  border-radius: 8px;
  background: transparent;
  padding-left: 24px !important;
}

.app-side-menu :deep(.ant-menu-sub .ant-menu-item .ant-menu-title-content) {
  font-size: 13px;
}

.app-side-menu :deep(.ant-menu-item-selected) {
  background: linear-gradient(90deg, rgba(22, 119, 255, 0.2), rgba(22, 119, 255, 0.07)) !important;
  color: #1677ff !important;
  font-weight: 500;
}

.app-side-menu :deep(.ant-menu-item-selected)::after {
  border-inline-end: 3px solid #1677ff !important;
}

.app-side-menu :deep(.ant-menu-sub .ant-menu-item-selected) {
  background: linear-gradient(90deg, rgba(22, 119, 255, 0.18), rgba(22, 119, 255, 0.04)) !important;
  box-shadow: inset 0 0 0 1px rgba(22, 119, 255, 0.01);
}

.app-side-menu :deep(.ant-menu-sub .ant-menu-item-selected)::after {
  border-inline-end: 0 !important;
}

.app-side-menu :deep(.ant-menu-sub .ant-menu-item-selected)::before {
  content: "";
  position: absolute;
  left: 0;
  top: 7px;
  width: 3px;
  height: 20px;
  border-radius: 0 2px 2px 0;
  background: #1677ff;
}

.sider-footer {
  padding: 8px;
}

.sider-collapse-btn {
  width: 100%;
  height: 34px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: rgba(0, 0, 0, 0.72);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sider-collapse-btn:hover {
  color: #1677ff;
  background: rgba(22, 119, 255, 0.1);
}

.app-layout-main.ant-layout {
  flex: 1;
  min-width: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-layout-content.ant-layout-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px;
  background-color: rgb(249 250 253);
  background-image: linear-gradient(rgba(59, 130, 246, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.04) 1px, transparent 1px);
  background-size: 48px 48px;
  background-position: 0 0;
}

/* ===================== Header ===================== */
.app-layout-header.ant-layout-header {
  height: 50px;
  line-height: 50px;
  padding-block: 0;
  padding-inline: 24px;
  background: #fff !important;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.06);
}

.header-row {
  width: 100%;
}

.header-left {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-width: 0;
}

.header-user {
  flex-shrink: 0;
}

.header-breadcrumb {
  margin: 0;
}

.header-breadcrumb :deep(ol) {
  justify-content: flex-start;
}
</style>
