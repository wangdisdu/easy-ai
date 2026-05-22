<template>
  <nav class="obs-tabbar">
    <RouterLink
      v-for="t in tabs"
      :key="t.to"
      :to="t.to"
      :class="['obs-tab', { 'obs-tab--active': t.active }]"
    >
      {{ t.label }}
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();

const tabs = computed(() => {
  const p = route.path;
  return [
    { label: "总览", to: "/observability", active: p === "/observability" },
    {
      label: "告警中心",
      to: "/observability/alert",
      active: p === "/observability/alert" || p.startsWith("/observability/alert/"),
    },
    {
      label: "告警规则",
      to: "/observability/alert-rule",
      active: p.startsWith("/observability/alert-rule"),
    },
  ];
});
</script>

<style scoped>
.obs-tabbar {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-split);
}
.obs-tab {
  padding: 6px 16px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  transition: all 0.15s ease;
}
.obs-tab:hover {
  color: var(--color-accent);
}
.obs-tab--active {
  background: var(--surface-card-bg);
  color: var(--color-accent);
  box-shadow: var(--shadow-card-sm);
}
</style>
