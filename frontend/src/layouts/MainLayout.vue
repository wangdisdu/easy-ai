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
          <span v-else class="sider-brand-icon" aria-hidden="true">
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
            <a-tooltip :title="isDark ? '切换到浅色主题' : '切换到深色主题'">
              <a-button
                type="text"
                class="header-theme-toggle"
                :aria-label="isDark ? '切换到浅色主题' : '切换到深色主题'"
                @click="theme.toggle()"
              >
                <!-- 暗色主题下显示月亮（实心 / 圆润），亮色主题下显示太阳（线性 / 放射） -->
                <svg
                  v-if="isDark"
                  class="theme-icon"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  width="18"
                  height="18"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
                <svg
                  v-else
                  class="theme-icon"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  width="18"
                  height="18"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="12" cy="12" r="4" />
                  <line x1="12" y1="2" x2="12" y2="4" />
                  <line x1="12" y1="20" x2="12" y2="22" />
                  <line x1="4.93" y1="4.93" x2="6.34" y2="6.34" />
                  <line x1="17.66" y1="17.66" x2="19.07" y2="19.07" />
                  <line x1="2" y1="12" x2="4" y2="12" />
                  <line x1="20" y1="12" x2="22" y2="12" />
                  <line x1="4.93" y1="19.07" x2="6.34" y2="17.66" />
                  <line x1="17.66" y1="6.34" x2="19.07" y2="4.93" />
                </svg>
              </a-button>
            </a-tooltip>
            <AlertsBell />
            <a-dropdown>
              <a-button type="text" class="header-user-trigger">
                <span class="header-user-avatar">{{ userInitial }}</span>
                <span class="header-user-meta">
                  <span class="header-user-name">{{ auth.user?.account ?? "用户" }}</span>
                  <span class="header-user-role">{{ userRoleLabel }}</span>
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
import { useThemeStore } from "@/stores/theme";
import logoAi from "@/assets/icons/logo-ai.svg";
import AppIcon from "@/components/AppIcon.vue";
import AlertsBell from "@/components/AlertsBell.vue";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const theme = useThemeStore();
const isDark = computed(() => theme.mode === "dark");

type IconKey =
  | "appstore"
  | "bulb"
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
type RouteMetaExt = { menu?: MenuMeta; permissions?: string[] };
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

const userRoleLabel = computed(() => {
  if (auth.isSuperAdmin) return "超级管理员";
  const names = auth.user?.roles?.map((r) => r.name).filter(Boolean) ?? [];
  return names.length ? names.join(" / ") : "普通用户";
});

const menuItems = computed<MenuItem[]>(() =>
  router
    .getRoutes()
    .filter((record: RouteRecordNormalized) => {
      const meta = record.meta as RouteMetaExt;
      if (!meta.menu) return false;
      const required = meta.permissions ?? [];
      return required.length === 0 || auth.hasAnyPermission(required);
    })
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
  await auth.logout();
  await router.push("/login");
}
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
  background: var(--surface-sider-bg) !important;
  border-right: 1px solid var(--surface-sider-border);
  box-shadow: var(--surface-sider-shadow);
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
  background: var(--gradient-brand-horizontal);
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
  color: var(--color-text);
  letter-spacing: 0.04em;
}

.sider-brand-subtitle {
  margin-top: 4px;
  font-size: 9px;
  line-height: 1.2;
  font-weight: 600;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
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
  color: var(--color-text-tertiary);
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
  color: var(--color-text-secondary);
  background: var(--color-primary-bg-soft) !important;
  transform: translateX(1px);
}

.app-side-menu :deep(.ant-menu-item-selected) {
  background: linear-gradient(90deg, var(--color-primary-bg) 0%, var(--color-primary-bg-soft) 100%) !important;
  color: var(--color-text) !important;
  font-weight: 500;
  box-shadow: inset 0 0 0 1px var(--color-primary-bg-soft);
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
  background: var(--gradient-brand-vertical);
  box-shadow: 0 0 8px var(--color-primary-glow);
}

.app-side-menu :deep(.ant-menu-item-selected .ant-menu-item-icon) {
  color: var(--color-primary);
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
  color: var(--color-text-tertiary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sider-collapse-btn:hover {
  color: var(--color-text-secondary);
  background: var(--color-primary-bg-soft);
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
    linear-gradient(var(--surface-content-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--surface-content-grid) 1px, transparent 1px),
    var(--surface-content-bg);
  background-size: 48px 48px;
  background-position: 0 0;
}

.app-layout-header.ant-layout-header {
  height: var(--header-height);
  line-height: var(--header-height);
  padding-block: 0;
  background: var(--surface-header-bg) !important;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--surface-header-border);
  box-shadow: var(--surface-header-shadow);
}

/* Header row：拉伸到 header 全高，让 .header-user 的左分割线能贴顶贴底；
   .header-left 内部自己居中。 */
.header-row {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: stretch;
}

.header-left {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  justify-content: flex-start;
}

.header-user {
  flex-shrink: 0;
  position: relative;
  padding-left: 18px;
  margin-left: 20px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

/* Inset 分割线：短一截、纵向居中，比贯通的工业风更轻盈现代 */
.header-user::before {
  content: "";
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 1px;
  height: 22px;
  background: var(--surface-divider);
  border-radius: 1px;
}

/* 让 theme toggle 和 user trigger 高度/圆角一致，视觉 baseline 对齐 */
.header-theme-toggle {
  width: 40px;
  height: 40px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  color: var(--color-text-secondary);
  transition: color 0.2s ease, background-color 0.2s ease;
}

.header-theme-toggle:hover {
  color: var(--color-primary);
  background: var(--color-glass-bg);
}

/* SVG 图标继承按钮的 color，hover 时跟着变蓝 */
.theme-icon {
  display: block;
  color: inherit;
}

.header-breadcrumb { margin: 0; }

.header-breadcrumb :deep(ol) {
  justify-content: flex-start;
  gap: 8px;
  font-size: 12px;
}

.header-breadcrumb :deep(.ant-breadcrumb-link),
.header-breadcrumb :deep(.ant-breadcrumb-separator) {
  color: var(--color-text-tertiary);
}

.header-breadcrumb :deep(li:last-child .ant-breadcrumb-link) {
  color: var(--color-text);
  font-weight: 600;
}

.header-user-trigger {
  height: 40px;
  padding: 4px 8px 4px 4px;
  border-radius: 12px;
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: var(--surface-trigger-bg);
  border: 1px solid var(--surface-trigger-border);
  box-shadow: inset 0 1px 0 var(--surface-trigger-inset);
  transition:
    color 0.2s ease,
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.header-user-trigger:hover {
  color: var(--color-text) !important;
  border-color: var(--color-primary-bg-strong);
  background: var(--color-glass-bg) !important;
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
  background: var(--gradient-brand-corner);
  color: var(--color-text-inverse);
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
  color: var(--color-text);
}

.header-user-role {
  font-size: 10px;
  color: var(--color-text-tertiary);
}

.header-user-chevron {
  font-size: 11px;
  color: var(--color-text-quaternary);
}
</style>
