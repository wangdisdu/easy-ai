<template>
  <div class="mock-page">
    <a-card :bordered="false">
      <h2 class="mock-title">{{ pageTitle }}</h2>
      <p class="mock-desc">该页面用于菜单样式与层级效果预览，暂未接入具体业务功能。</p>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const pageTitle = computed(() => {
  if (route.meta.title) return String(route.meta.title);
  const raw = route.meta.breadcrumb;
  if (Array.isArray(raw) && raw.length > 0) return String(raw[raw.length - 1]);
  return "功能预览";
});
</script>

<style scoped>
.mock-page {
  padding: 0;
}

.mock-title {
  margin: 0 0 8px;
  font-size: 20px;
}

.mock-desc {
  margin: 0;
  color: rgba(0, 0, 0, 0.6);
}
</style>
