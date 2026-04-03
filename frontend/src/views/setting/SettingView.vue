<template>
  <div class="setting-page">
    <div class="setting-head">
      <div>
        <h2 class="setting-title">系统配置</h2>
        <p class="setting-sub">管理模型供应商接入、运行环境等基础设施配置。</p>
      </div>
    </div>

    <a-tabs :active-key="activeTab" size="large" class="setting-tabs" @change="onTabChange">
      <a-tab-pane key="llm" tab="大模型管理">
        <LlmManageView />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import LlmManageView from "@/views/setting/LlmManageView.vue";

type TabKey = "llm";

const route = useRoute();
const router = useRouter();
const tabKeys: TabKey[] = ["llm"];

const activeTab = computed<TabKey>(() => {
  const tab = route.query.tab;
  if (typeof tab === "string" && tabKeys.includes(tab as TabKey)) {
    return tab as TabKey;
  }
  return "llm";
});

function onTabChange(tab: string) {
  router.replace({ path: route.path, query: { ...route.query, tab } });
}
</script>

<style scoped>
.setting-page {
  min-height: 100%;
}

.setting-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.setting-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.setting-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.setting-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 20px;
}

.setting-tabs :deep(.ant-tabs-nav::before) {
  border-bottom-color: rgba(148, 163, 184, 0.16);
}

.setting-tabs :deep(.ant-tabs-tab) {
  padding: 10px 4px 12px;
  color: #64748b;
  font-weight: 500;
}

.setting-tabs :deep(.ant-tabs-tab:hover) {
  color: #334155;
}

.setting-tabs :deep(.ant-tabs-tab.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: #1677ff;
}

.setting-tabs :deep(.ant-tabs-ink-bar) {
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, #1677ff 0%, #7c3aed 100%);
}
</style>
