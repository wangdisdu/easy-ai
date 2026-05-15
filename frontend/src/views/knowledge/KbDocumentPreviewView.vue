<template>
  <div class="preview-page">
    <header class="preview-header">
      <a-button type="link" class="back" @click="goBack">
        <ArrowLeftOutlined />
        返回知识库
      </a-button>
      <h2 class="filename" :title="doc?.name">{{ doc?.name || "..." }}</h2>
      <div class="actions">
        <span v-if="doc" class="meta">{{ doc.format }} · {{ humanSize(doc.size_bytes) }}</span>
        <a-typography-text
          v-if="doc"
          code
          :copyable="{ text: doc.ref, tooltip: '复制引用码' }"
          class="ref-code"
        >
          {{ doc.ref }}
        </a-typography-text>
        <a-button
          v-if="doc"
          type="primary"
          :href="downloadUrl"
          :download="doc.name"
        >
          下载
        </a-button>
      </div>
    </header>

    <main class="preview-body">
      <a-spin :spinning="loading" tip="加载中...">
        <a-alert v-if="error" type="error" :message="error" show-icon />

        <div v-else-if="kind === 'markdown'" class="md-render" v-html="mdHtml" />

        <pre v-else-if="kind === 'text'" class="text-render">{{ textContent }}</pre>

        <iframe
          v-else-if="kind === 'pdf'"
          :src="downloadInlineUrl"
          class="pdf-frame"
          frameborder="0"
        />

        <div v-else-if="kind === 'image'" class="image-wrap">
          <img :src="downloadInlineUrl" :alt="doc?.name" />
        </div>

        <a-empty v-else-if="kind === 'unsupported'" description="该文件类型不支持内嵌预览,请点击右上角下载查看" />
      </a-spin>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import { marked } from "marked";
import * as kbApi from "@/api/kb";
import type { KbDocumentResp } from "@/api/types";

type PreviewKind = "markdown" | "text" | "pdf" | "image" | "unsupported" | "";

const route = useRoute();
const router = useRouter();
const kbId = computed(() => String(route.params.kbId));
const docId = computed(() => String(route.params.docId));

const doc = ref<KbDocumentResp | null>(null);
const loading = ref(true);
const error = ref<string>("");
const kind = ref<PreviewKind>("");
const mdHtml = ref("");
const textContent = ref("");

const downloadUrl = computed(
  () => `/api/v1/kb/${kbId.value}/document/${docId.value}/download`,
);
const downloadInlineUrl = computed(() => `${downloadUrl.value}?inline=true`);

function classifyByFormat(fmt: string, name: string): PreviewKind {
  const lower = (fmt || "").toLowerCase();
  if (lower === "md" || name.toLowerCase().endsWith(".markdown")) return "markdown";
  if (["txt", "csv", "json", "log"].includes(lower)) return "text";
  if (lower === "pdf") return "pdf";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "img"].includes(lower)) return "image";
  return "unsupported";
}

async function fetchTextContent() {
  // 用同一个 download 端点拿原始字节,这里 ASCII/UTF-8 文本直接 .text() 解析
  const resp = await fetch(downloadUrl.value, { credentials: "same-origin" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return await resp.text();
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    // 拉文档元信息(同详情接口),拿 format 决定渲染方式
    const { data } = await kbApi.getKbDocument(kbId.value, docId.value);
    doc.value = data.data;
    kind.value = classifyByFormat(data.data.format, data.data.name);

    if (kind.value === "markdown") {
      const raw = await fetchTextContent();
      mdHtml.value = await marked.parse(raw, { gfm: true, breaks: false });
    } else if (kind.value === "text") {
      textContent.value = await fetchTextContent();
    }
    // pdf/image 直接交给 iframe/img,不预拉
  } catch (e) {
    error.value = "加载失败: " + ((e as Error).message || "未知错误");
  } finally {
    loading.value = false;
  }
}

function goBack() {
  // 优先回上一页(详情抽屉打开的状态),没有 history 才回 KB 详情
  if (window.history.length > 1) router.back();
  else router.push(`/knowledge/${kbId.value}`);
}

function humanSize(n: number | null | undefined): string {
  if (!n || n < 0) return "-";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}

onMounted(load);
</script>

<style scoped>
.preview-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 100vh;
  background: var(--color-bg-layout, #f5f5f5);
}

.preview-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: var(--color-bg-container, #fff);
  border-bottom: 1px solid var(--surface-divider, #eee);
  position: sticky;
  top: 0;
  z-index: 10;
}

.back {
  padding: 0;
}

.filename {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.meta {
  color: var(--color-text-tertiary);
  font-size: 12px;
}
.ref-code {
  font-size: 12px;
}

.preview-body {
  flex: 1;
  padding: 24px;
  overflow: auto;
}

.md-render {
  max-width: 920px;
  margin: 0 auto;
  padding: 32px 40px;
  background: var(--color-bg-container, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  line-height: 1.7;
}
.md-render :deep(h1),
.md-render :deep(h2),
.md-render :deep(h3) {
  margin-top: 1.4em;
  margin-bottom: 0.6em;
  font-weight: 700;
}
.md-render :deep(p) {
  margin: 0.8em 0;
}
.md-render :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.92em;
}
.md-render :deep(pre) {
  background: #2d2d2d;
  color: #f5f5f5;
  padding: 14px 16px;
  border-radius: 6px;
  overflow-x: auto;
}
.md-render :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}
.md-render :deep(table) {
  border-collapse: collapse;
  margin: 1em 0;
  width: 100%;
}
.md-render :deep(table th),
.md-render :deep(table td) {
  border: 1px solid var(--surface-divider, #e5e5e5);
  padding: 6px 10px;
}
.md-render :deep(blockquote) {
  border-left: 4px solid var(--color-primary, #1677ff);
  margin: 0.8em 0;
  padding: 0.4em 1em;
  color: var(--color-text-secondary);
  background: rgba(0, 0, 0, 0.02);
}

.text-render {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  background: var(--color-bg-container, #fff);
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, "SFMono-Regular", Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
}

.pdf-frame {
  width: 100%;
  height: calc(100vh - 80px);
  background: #fff;
  border-radius: 8px;
}

.image-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
}
.image-wrap img {
  max-width: 100%;
  max-height: calc(100vh - 120px);
  background: #fff;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
</style>
