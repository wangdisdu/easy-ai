<template>
  <section class="kb-page">
    <div class="kb-page-head">
      <h2 class="kb-page-title">知识库管理</h2>
      <p class="kb-page-sub">
        组织层(知识库 / 分类 / 文档)与向量化层(RAG 库)解耦,文档原文由 easy-ai
        留存,向量化与检索由底层 RAGFlow 完成
      </p>
    </div>

    <a-tabs v-model:active-key="activeTab" class="kb-tabs" @change="onTabChange">
      <a-tab-pane key="kb" tab="知识库">
        <KbTab />
      </a-tab-pane>
      <a-tab-pane key="integration" tab="知识集成">
        <IntegrationTab />
      </a-tab-pane>
      <a-tab-pane key="vectorize" tab="知识向量化">
        <VectorizeTab />
      </a-tab-pane>
      <a-tab-pane key="synclog" tab="同步日志">
        <SyncLogTab />
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import KbTab from "./tabs/KbTab.vue";
import IntegrationTab from "./tabs/IntegrationTab.vue";
import VectorizeTab from "./tabs/VectorizeTab.vue";
import SyncLogTab from "./tabs/SyncLogTab.vue";

const route = useRoute();
const router = useRouter();

const VALID_TABS = ["kb", "integration", "vectorize", "synclog"];
const activeTab = ref(
  VALID_TABS.includes(String(route.query.tab)) ? String(route.query.tab) : "kb",
);

function onTabChange(key: string | number) {
  router.replace({ query: { ...route.query, tab: String(key) } });
}
</script>

<style scoped>
.kb-page {
  min-height: 100%;
}
.kb-page-head {
  margin-bottom: 8px;
}
.kb-page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
}
.kb-page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--color-text-tertiary);
}
.kb-tabs :deep(.ant-tabs-content) {
  padding-top: 4px;
}
</style>
