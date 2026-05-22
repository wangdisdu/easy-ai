<template>
  <div class="observability-page">
    <div class="observability-head">
      <div>
        <h2 class="observability-title">可观测性</h2>
        <p class="observability-sub">全局运营视角 · 告警规则与告警中心 · Langfuse 集成</p>
      </div>
    </div>

    <a-tabs
      :active-key="activeTab"
      size="large"
      class="observability-tabs"
      @change="onTabChange"
    >
      <a-tab-pane key="overview" tab="总览">
        <OverviewView />
      </a-tab-pane>
      <a-tab-pane key="alert" tab="告警中心">
        <AlertCenterView />
      </a-tab-pane>
      <a-tab-pane key="alert-rule" tab="告警规则">
        <AlertRuleListView />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import OverviewView from "./OverviewView.vue";
import AlertCenterView from "./AlertCenterView.vue";
import AlertRuleListView from "./AlertRuleListView.vue";

type TabKey = "overview" | "alert" | "alert-rule";

const route = useRoute();
const router = useRouter();
const tabKeys: TabKey[] = ["overview", "alert", "alert-rule"];

const activeTab = computed<TabKey>(() => {
  const tab = route.query.tab;
  if (typeof tab === "string" && tabKeys.includes(tab as TabKey)) {
    return tab as TabKey;
  }
  return "overview";
});

function onTabChange(tab: string) {
  router.replace({ path: route.path, query: { ...route.query, tab } });
}
</script>

<style scoped>
.observability-page {
  min-height: 100%;
}

.observability-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.observability-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}

.observability-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.observability-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 20px;
}

.observability-tabs :deep(.ant-tabs-nav::before) {
  border-bottom-color: var(--surface-divider);
}

.observability-tabs :deep(.ant-tabs-tab) {
  padding: 10px 4px 12px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.observability-tabs :deep(.ant-tabs-tab:hover) {
  color: var(--color-text-secondary);
}

.observability-tabs :deep(.ant-tabs-tab.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--color-primary);
}

.observability-tabs :deep(.ant-tabs-ink-bar) {
  height: 3px;
  border-radius: 999px;
  background: var(--gradient-brand-horizontal);
}

.observability-tabs :deep(.ant-tabs-content-holder) {
  min-height: 0;
}
</style>
