<template>
  <div class="setting-page">
    <div class="setting-head">
      <div>
        <h2 class="setting-title">系统配置</h2>
        <p class="setting-sub">管理模型供应商接入、运行环境等基础设施配置。</p>
      </div>
    </div>

    <a-tabs :active-key="activeTab" size="large" class="setting-tabs" @change="onTabChange">
      <a-tab-pane v-if="canLlm" key="llm" tab="大模型管理">
        <LlmManageView />
      </a-tab-pane>
      <a-tab-pane v-if="canSetting" key="ai-infra" tab="AI 基础设施">
        <AiInfraView />
      </a-tab-pane>
      <a-tab-pane v-if="canSetting" key="category" tab="分类管理">
        <CategoryManageView />
      </a-tab-pane>
      <a-tab-pane v-if="canSetting" key="sandbox" tab="沙盒管理">
        <SandboxManageView />
      </a-tab-pane>
      <a-tab-pane v-if="canSetting" key="sandbox-instance" tab="沙盒实例">
        <SandboxInstanceView />
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import LlmManageView from "@/views/setting/LlmManageView.vue";
import CategoryManageView from "@/views/setting/CategoryManageView.vue";
import SandboxManageView from "@/views/setting/SandboxManageView.vue";
import SandboxInstanceView from "@/views/setting/SandboxInstanceView.vue";
import AiInfraView from "@/views/setting/AiInfraView.vue";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

type TabKey = "llm" | "ai-infra" | "category" | "sandbox" | "sandbox-instance";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const canLlm = computed(() => auth.hasPermission(PERM.SYSTEM_LLM));
const canSetting = computed(() => auth.hasPermission(PERM.SYSTEM_SETTING));
const tabKeys: TabKey[] = ["llm", "ai-infra", "category", "sandbox", "sandbox-instance"];

const activeTab = computed<TabKey>(() => {
  const tab = route.query.tab;
  if (typeof tab === "string" && tabKeys.includes(tab as TabKey)) {
    return tab as TabKey;
  }
  return canLlm.value ? "llm" : "ai-infra";
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
  color: var(--color-text);
}

.setting-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-text-tertiary);
}

.setting-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 20px;
}

.setting-tabs :deep(.ant-tabs-nav::before) {
  border-bottom-color: var(--surface-divider);
}

.setting-tabs :deep(.ant-tabs-tab) {
  padding: 10px 4px 12px;
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.setting-tabs :deep(.ant-tabs-tab:hover) {
  color: var(--color-text-secondary);
}

.setting-tabs :deep(.ant-tabs-tab.ant-tabs-tab-active .ant-tabs-tab-btn) {
  color: var(--color-primary);
}

.setting-tabs :deep(.ant-tabs-ink-bar) {
  height: 3px;
  border-radius: 999px;
  background: var(--gradient-brand-horizontal);
}
</style>
