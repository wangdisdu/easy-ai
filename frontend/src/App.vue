<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { theme } from "ant-design-vue";
import { storeToRefs } from "pinia";
import { useThemeStore } from "@/stores/theme";

const themeStore = useThemeStore();
const { mode } = storeToRefs(themeStore);

/**
 * 控制台与业务页统一走 Ant Design 后台风格，亮/暗两套通过 algorithm 切换。
 *
 * 这里需要显式对齐 AntD 的容器 / 边框 / 文本 token 到 src/styles/tokens.css 的调色板，
 * 否则 darkAlgorithm 默认从 colorBgBase: #000 派生 colorBgContainer: #141414，
 * 输入框 / 默认按钮 / Table 等组件会渲染成近黑色，与我们的 slate-800 (#1e293b) 体系脱节。
 *
 * 这些值与 tokens.css 里的 --color-bg-container / --color-bg-elevated / --color-border /
 * --color-text* 保持完全一致——任何一边变更都要同步另一边。
 *
 * 自定义 .vue 样式应使用 src/styles/tokens.css 中的 CSS 变量，而非在此扩展更多 token。
 */
const themeConfig = computed(() => {
  const isDark = mode.value === "dark";
  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      // ===== Brand =====
      colorPrimary: isDark ? "#4096ff" : "#1677ff",
      borderRadius: 6,

      // ===== Surface（关键：让输入框/按钮/Table 用我们的 slate 调色板） =====
      colorBgLayout: isDark ? "#0f172a" : "#f0f2f5",
      colorBgContainer: isDark ? "#1e293b" : "#ffffff",
      colorBgElevated: isDark ? "#334155" : "#ffffff",
      colorBgSpotlight: isDark ? "#475569" : "rgba(0, 0, 0, 0.85)",

      // ===== Border =====
      colorBorder: isDark ? "#334155" : "#e2e8f0",
      colorBorderSecondary: isDark ? "#1e293b" : "#f0f0f0",

      // ===== Text =====
      colorText: isDark ? "#f1f5f9" : "#0f172a",
      colorTextSecondary: isDark ? "#cbd5e1" : "#475569",
      colorTextTertiary: isDark ? "#94a3b8" : "#64748b",
      colorTextQuaternary: isDark ? "#64748b" : "#94a3b8",

      // ===== Status =====
      colorSuccess: isDark ? "#34d399" : "#10b981",
      colorWarning: isDark ? "#fbbf24" : "#f59e0b",
      colorError: isDark ? "#f87171" : "#ef4444",
      colorInfo: isDark ? "#60a5fa" : "#3b82f6",
    },
    components: {
      Layout: {
        colorBgBody: isDark ? "#0f172a" : "#f0f2f5",
        colorBgHeader: isDark ? "#1e293b" : "#ffffff",
      },
    },
  };
});
</script>
