<template>
  <div class="ai-infra">
    <div class="ai-infra-intro">
      <h3 class="ai-infra-title">AI 基础设施默认模型</h3>
      <p class="ai-infra-sub">
        选定的模型将作为创建知识库、RAG 检索、多模态等场景的默认值。
        模型本体在「大模型管理」中维护;此处仅指定默认指针。
        Embedding / Rerank 模型变更后会自动同步到 RAGFlow。
      </p>
    </div>

    <a-spin :spinning="loading">
      <a-form layout="vertical" class="ai-infra-form">
        <a-form-item v-for="row in rows" :key="row.key" :label="row.label">
          <a-select
            v-model:value="row.selected"
            :options="row.options"
            placeholder="未配置"
            allow-clear
            show-search
            option-filter-prop="label"
            style="max-width: 480px"
            @change="(v: unknown) => onSelectChange(row, v)"
          />
          <div v-if="row.hint" class="ai-infra-hint">{{ row.hint }}</div>
          <div v-if="row.updatedAt" class="ai-infra-meta">
            最近更新:{{ formatTime(row.updatedAt) }}
          </div>
        </a-form-item>
      </a-form>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { pageProvider } from "@/api/llm";
import type { LlmProviderResp } from "@/api/types";
import {
  AI_DEFAULT_EMBEDDING_KEY,
  AI_DEFAULT_RERANK_KEY,
  AI_DEFAULT_VISION_KEY,
  listSystemSettings,
  setSystemSetting,
} from "@/api/systemSetting";

interface Row {
  key: string;
  label: string;
  modelType: "Embedding" | "Rerank" | "Vision";
  selected: string | null;
  updatedAt: number | null;
  hint?: string;
  options: { label: string; value: string }[];
}

const loading = ref(false);
const providers = ref<LlmProviderResp[]>([]);
const settingMap = reactive<Record<string, { value: string | null; updatedAt: number | null }>>({});

const rows = computed<Row[]>(() => {
  const build = (
    key: string,
    label: string,
    modelType: Row["modelType"],
    hint?: string,
  ): Row => {
    const options: { label: string; value: string }[] = [];
    for (const p of providers.value) {
      for (const m of p.models || []) {
        if (m.model_type === modelType && m.status === "active") {
          options.push({
            label: `${p.name} / ${m.model}`,
            value: m.id,
          });
        }
      }
    }
    const setting = settingMap[key];
    return {
      key,
      label,
      modelType,
      hint,
      selected: setting?.value ?? null,
      updatedAt: setting?.updatedAt ?? null,
      options,
    };
  };
  return [
    build(
      AI_DEFAULT_EMBEDDING_KEY,
      "默认 Embedding 模型",
      "Embedding",
      "用于知识库向量化与检索。建议优先选择中文优化的 embedding 模型。",
    ),
    build(
      AI_DEFAULT_RERANK_KEY,
      "默认 Rerank 模型",
      "Rerank",
      "可选。配置后 RAG 检索默认走 rerank,提升 top-k 召回质量。",
    ),
    build(
      AI_DEFAULT_VISION_KEY,
      "默认 Vision 模型",
      "Vision",
      "用于多模态应用与 OCR 兜底。暂未联动 RAGFlow。",
    ),
  ];
});

async function load() {
  loading.value = true;
  try {
    const [providerResp, settingResp] = await Promise.all([
      pageProvider({ page_no: 1, page_size: 10000 }),
      listSystemSettings(),
    ]);
    providers.value = providerResp.data?.data || [];
    const list = settingResp.data?.data || [];
    // 清空 + 重新填,保证已被删除的 key 也被清理
    for (const k of Object.keys(settingMap)) delete settingMap[k];
    for (const s of list) {
      settingMap[s.key] = { value: s.value, updatedAt: s.update_time ?? null };
    }
  } catch (e) {
    message.error("加载失败:" + ((e as Error).message || "未知错误"));
  } finally {
    loading.value = false;
  }
}

async function onSelectChange(row: Row, raw: unknown) {
  const v = (raw as string) ?? null;
  try {
    const resp = await setSystemSetting(row.key, v);
    const data = resp.data?.data;
    settingMap[row.key] = { value: data?.value ?? null, updatedAt: data?.update_time ?? null };
    message.success("已保存");
  } catch (e) {
    message.error("保存失败:" + ((e as Error).message || "未知错误"));
    // 失败后回滚 selected
    await load();
  }
}

function formatTime(ts: number | null) {
  if (!ts) return "-";
  const d = new Date(ts);
  return d.toLocaleString();
}

onMounted(load);
</script>

<style scoped>
.ai-infra {
  max-width: 720px;
}
.ai-infra-intro {
  margin-bottom: 24px;
}
.ai-infra-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}
.ai-infra-sub {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-tertiary);
  line-height: 1.6;
}
.ai-infra-form :deep(.ant-form-item) {
  margin-bottom: 28px;
}
.ai-infra-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.ai-infra-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-quaternary, #999);
}
</style>
