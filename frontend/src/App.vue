<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { theme } from "ant-design-vue";

/** 亮色主题（登录页为独立样式，控制台与业务页统一走 Ant Design 常见后台风格） */
const themeConfig = {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#1677ff",
    borderRadius: 6,
    colorBgLayout: "#f0f2f5",
  },
  components: {
    Layout: {
      colorBgBody: "#f0f2f5",
      /** 顶栏背景；侧栏浅色主题由 `ant-layout-sider-light` 使用 colorBgContainer */
      colorBgHeader: "#ffffff",
    },
  },
};
</script>
