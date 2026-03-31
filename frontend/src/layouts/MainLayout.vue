<template>
  <a-layout class="app-layout-root" has-sider>
    <a-layout-sider
      v-model:collapsed="collapsed"
      collapsible
      :trigger="null"
      theme="light"
      :width="220"
      :collapsed-width="64"
      class="app-layout-sider"
    >
      <div class="sider-brand">
        <div class="sider-brand-main" @click="onBrandClick">
          <div v-if="!collapsed" class="sider-brand-copy">
            <div class="sider-brand-accent"></div>
            <div class="sider-brand-text">智瞻 AI</div>
            <div class="sider-brand-subtitle">Enterprise Platform</div>
          </div>
          <span class="sider-brand-icon" aria-hidden="true">
            <img :src="logoAi" alt="" class="sider-brand-icon-image" />
          </span>
        </div>
      </div>
      <a-menu
        v-model:selected-keys="selectedKeys"
        theme="light"
        mode="inline"
        class="app-side-menu"
        @click="onMenuClick"
      >
        <a-menu-item v-for="item in menuItems" :key="item.path">
          <template #icon><AppIcon :name="item.iconKey" /></template>
          {{ item.title }}
        </a-menu-item>
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
              <a-button type="text" class="header-user-trigger">
                <span class="header-user-avatar">{{ userInitial }}</span>
                <span class="header-user-meta">
                  <span class="header-user-name">{{ auth.user?.account ?? "用户" }}</span>
                  <span class="header-user-role">管理员</span>
                </span>
                <DownOutlined class="header-user-chevron" />
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
  DownOutlined,
  LeftOutlined,
  RightOutlined,
} from "@ant-design/icons-vue";
import { useAuthStore } from "@/stores/auth";
import AppIcon from "@/components/AppIcon.vue";
import logoAi from "@/assets/icons/logo-ai.svg";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

type IconKey =
  | "appstore"
  | "cluster"
  | "database"
  | "eye"
  | "robot"
  | "safety"
  | "setting"
  | "tool";
type MenuMeta = {
  title: string;
  icon: IconKey;
  order: number;
};
type MenuItem = {
  path: string;
  title: string;
  iconKey: IconKey;
};

const breadcrumbItems = computed(() => {
  const title = route.meta.title;
  return title ? [String(title)] : [];
});

const userInitial = computed(() => (auth.user?.account?.trim().charAt(0) ?? "用").toUpperCase());

const menuItems = computed<MenuItem[]>(() =>
  router
    .getRoutes()
    .filter((record: RouteRecordNormalized) => Boolean((record.meta as { menu?: MenuMeta }).menu))
    .sort((a, b) => {
      const aMenu = (a.meta as { menu: MenuMeta }).menu;
      const bMenu = (b.meta as { menu: MenuMeta }).menu;
      return aMenu.order - bMenu.order;
    })
    .map((record) => {
      const menu = (record.meta as { menu: MenuMeta }).menu;
      return {
        path: record.path,
        title: menu.title,
        iconKey: menu.icon,
      };
    }),
);

const collapsed = ref(false);
const selectedKeys = ref<string[]>([route.path]);

watch(
  () => route.path,
  (path) => {
    selectedKeys.value = [path];
  },
  { immediate: true },
);

function onMenuClick({ key }: { key: string | number }) {
  router.push(String(key));
}

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
.app-layout-root {
  --sider-pad-x: 10px;
  --menu-radius: 12px;
  --header-height: 56px;
  --content-pad: 24px;
}

.app-layout-root.ant-layout {
  min-height: 100vh;
}

.app-layout-sider {
  background:
    linear-gradient(180deg, rgba(241, 245, 255, 0.92) 0%, rgba(255, 255, 255, 1) 28%, rgba(248, 250, 255, 1) 100%) !important;
  border-right: 1px solid rgba(22, 119, 255, 0.08);
  box-shadow:
    inset -1px 0 0 rgba(255, 255, 255, 0.8),
    8px 0 24px rgba(15, 23, 42, 0.03);
}

.app-layout-sider :deep(.ant-layout-sider-children) {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.sider-brand {
  height: 80px;
  display: flex;
  align-items: flex-end;
  padding: 0 12px 12px;
}

.sider-brand-main {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-radius: 14px;
  padding: 0 4px;
  cursor: pointer;
  user-select: none;
  transition: transform 0.2s ease;
}

.sider-brand-main:hover {
  transform: translateY(-1px);
}

.sider-brand-copy {
  min-width: 0;
}

.sider-brand-accent {
  width: 34px;
  height: 3px;
  margin-bottom: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, #1677ff 0%, #7c3aed 100%);
}

.sider-brand-icon {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.sider-brand-icon-image {
  width: 32px;
  height: 32px;
  display: block;
}

.sider-brand-text {
  font-size: 15px;
  line-height: 1.2;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: 0.04em;
}

.sider-brand-subtitle {
  margin-top: 4px;
  font-size: 9px;
  line-height: 1.2;
  font-weight: 600;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: #64748b;
}

.app-side-menu {
  flex: 1;
  border-inline-end: 0 !important;
  background: transparent;
  padding: 10px var(--sider-pad-x) 0;
}

.app-side-menu :deep(.ant-menu-item) {
  position: relative;
  height: 42px;
  line-height: 42px;
  width: auto;
  margin: 2px 0;
  border-radius: var(--menu-radius);
  color: #64748b;
  transition:
    color 0.2s ease,
    background 0.2s ease,
    transform 0.2s ease;
}

.app-side-menu :deep(.ant-menu-item .ant-menu-title-content) {
  font-weight: 500;
  letter-spacing: 0.01em;
}

.app-side-menu :deep(.ant-menu-item .ant-menu-item-icon) {
  color: inherit;
  transition: color 0.2s ease;
}

.app-side-menu :deep(.ant-menu-item:hover) {
  color: #334155;
  background: rgba(22, 119, 255, 0.05) !important;
  transform: translateX(1px);
}

.app-side-menu :deep(.ant-menu-item-selected) {
  background: linear-gradient(90deg, rgba(22, 119, 255, 0.14) 0%, rgba(22, 119, 255, 0.05) 100%) !important;
  color: #0f172a !important;
  font-weight: 500;
  box-shadow: inset 0 0 0 1px rgba(22, 119, 255, 0.04);
}

.app-side-menu :deep(.ant-menu-item-selected)::after {
  display: none;
}

.app-side-menu :deep(.ant-menu-item-selected)::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  transform: translateY(-50%);
  background: linear-gradient(180deg, #1677ff 0%, #7c3aed 100%);
  box-shadow: 0 0 8px rgba(22, 119, 255, 0.28);
}

.app-side-menu :deep(.ant-menu-item-selected .ant-menu-item-icon) {
  color: #1677ff;
}

.app-side-menu :deep(.ant-menu-inline-collapsed > .ant-menu-item) {
  inset-inline-start: 0;
  padding-inline: calc(50% - 8px) !important;
}

.sider-footer {
  padding: 10px var(--sider-pad-x) 14px;
}

.sider-collapse-btn {
  width: 100%;
  height: 38px;
  border: 0;
  border-radius: var(--menu-radius);
  background: transparent;
  color: #64748b;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sider-collapse-btn:hover {
  color: #334155;
  background: rgba(22, 119, 255, 0.05);
}

.app-layout-main.ant-layout {
  flex: 1;
  min-width: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-layout-header.ant-layout-header,
.app-layout-content.ant-layout-content {
  padding-inline: var(--content-pad);
}

.app-layout-content.ant-layout-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-block: var(--content-pad);
  background:
    linear-gradient(rgba(59, 130, 246, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59, 130, 246, 0.04) 1px, transparent 1px),
    rgb(249 250 253);
  background-size: 48px 48px;
  background-position: 0 0;
}

.app-layout-header.ant-layout-header {
  height: var(--header-height);
  line-height: var(--header-height);
  padding-block: 0;
  background: rgba(255, 255, 255, 0.78) !important;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.header-row,
.header-left {
  display: flex;
  width: 100%;
  align-items: center;
}

.header-left {
  justify-content: flex-start;
  min-width: 0;
}

.header-user {
  flex-shrink: 0;
  padding-left: 18px;
  margin-left: 20px;
  border-left: 1px solid rgba(148, 163, 184, 0.16);
}

.header-breadcrumb { margin: 0; }

.header-breadcrumb :deep(ol) {
  justify-content: flex-start;
  gap: 8px;
  font-size: 12px;
}

.header-breadcrumb :deep(.ant-breadcrumb-link),
.header-breadcrumb :deep(.ant-breadcrumb-separator) {
  color: #64748b;
}

.header-breadcrumb :deep(li:last-child .ant-breadcrumb-link) {
  color: #0f172a;
  font-weight: 600;
}

.header-user-trigger {
  height: 40px;
  padding: 4px 8px 4px 4px;
  border-radius: 12px;
  color: #475569;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.46);
  border: 1px solid rgba(148, 163, 184, 0.14);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.header-user-trigger:hover {
  color: #0f172a !important;
  border-color: rgba(22, 119, 255, 0.24);
  background: rgba(255, 255, 255, 0.72) !important;
}

.header-user-trigger :deep(.ant-btn-icon) {
  display: none;
}

.header-user-avatar {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(22, 119, 255, 0.9) 0%, rgba(124, 58, 237, 0.8) 100%);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex: 0 0 30px;
}

.header-user-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  line-height: 1.15;
}

.header-user-name {
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
}

.header-user-role {
  font-size: 10px;
  color: #64748b;
}

.header-user-chevron {
  font-size: 11px;
  color: #94a3b8;
}
</style>
