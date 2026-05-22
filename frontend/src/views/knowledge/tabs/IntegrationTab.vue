<template>
  <div class="integration-tab">
    <a-alert
      type="info"
      show-icon
      class="intro"
      message="知识集成"
      description="从外部数据源把知识导入到知识库。本期支持文件上传;Ones / API 拉取 / API 推送将在后续迭代接入。"
    />

    <div class="wizard">
      <!-- 数据源 -->
      <a-card title="① 选择数据源" size="small" class="card">
        <div class="source-grid">
          <div class="source-item source-item--active">
            <div class="source-name">文件上传</div>
            <div class="source-desc">上传本地 PDF / DOCX / XLSX / MD / TXT / CSV / JSON / 图片</div>
            <CheckCircleFilled class="source-check" />
          </div>
          <div class="source-item source-item--disabled">
            <div class="source-name">Ones 知识库</div>
            <div class="source-desc">后续迭代</div>
          </div>
          <div class="source-item source-item--disabled">
            <div class="source-name">API 主动拉取</div>
            <div class="source-desc">后续迭代</div>
          </div>
          <div class="source-item source-item--disabled">
            <div class="source-name">API 接收推送</div>
            <div class="source-desc">后续迭代</div>
          </div>
        </div>
      </a-card>

      <!-- 上传 + 目标 -->
      <a-card title="② 上传文件并选择目标" size="small" class="card">
        <a-upload-dragger
          v-model:file-list="fileList"
          :before-upload="beforeUpload"
          :multiple="true"
          :disabled="uploading"
        >
          <p class="upload-icon"><InboxOutlined /></p>
          <p class="upload-text">拖拽文件到此处或点击选择</p>
          <p class="upload-hint">单文件 ≤ 50MB,单次最多 20 个</p>
        </a-upload-dragger>

        <a-form layout="vertical" class="form">
          <a-form-item label="目标知识库" required>
            <a-select
              v-model:value="targetKb"
              :options="kbOptions"
              placeholder="选择知识库"
              :disabled="uploading"
              style="width: 100%"
              @change="onKbChange"
            />
          </a-form-item>
          <a-form-item label="目标分类">
            <a-tree-select
              v-model:value="targetCategory"
              :tree-data="categoryTreeData"
              :disabled="uploading || !targetKb"
              tree-default-expand-all
              placeholder="选择分类"
              style="width: 100%"
            />
            <div class="form-hint">分类已映射 RAG 库时,上传后自动进入向量化队列</div>
          </a-form-item>
        </a-form>

        <div class="actions">
          <a-button
            type="primary"
            :loading="uploading"
            :disabled="!fileList.length || !targetKb"
            @click="onSubmit"
          >
            开始导入（{{ fileList.length }}）
          </a-button>
        </div>

        <a-alert
          v-if="lastResult"
          :type="lastResult.ok ? 'success' : 'error'"
          :message="lastResult.msg"
          show-icon
          class="result"
        />
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import type { UploadFile, UploadProps } from "ant-design-vue";
import { CheckCircleFilled, InboxOutlined } from "@ant-design/icons-vue";
import * as kbApi from "@/api/kb";
import type { KbCategoryNode } from "@/api/types";

const fileList = ref<UploadFile[]>([]);
const kbOptions = ref<{ value: string; label: string }[]>([]);
const targetKb = ref<string | undefined>(undefined);
const targetCategory = ref<string>("0");
const categoryTreeData = ref<{ value: string; title: string }[]>([
  { value: "0", title: "未分类" },
]);
const uploading = ref(false);
const lastResult = ref<{ ok: boolean; msg: string } | null>(null);

const MAX_FILES = 20;
const MAX_SIZE = 50 * 1024 * 1024;

const beforeUpload: UploadProps["beforeUpload"] = (file) => {
  if (fileList.value.length >= MAX_FILES) {
    message.error(`最多 ${MAX_FILES} 个文件`);
    return false;
  }
  if (file.size > MAX_SIZE) {
    message.error(`${file.name} 超过 50MB`);
    return false;
  }
  return false;
};

async function onKbChange() {
  targetCategory.value = "0";
  categoryTreeData.value = [{ value: "0", title: "未分类" }];
  if (!targetKb.value) return;
  try {
    const { data } = await kbApi.getKbCategoryTree(targetKb.value);
    categoryTreeData.value = [
      { value: "0", title: "未分类" },
      ...data.data.map((c: KbCategoryNode) => ({ value: c.id, title: c.name })),
    ];
  } catch {
    /* 仅保留未分类 */
  }
}

async function onSubmit() {
  if (!targetKb.value || !fileList.value.length) return;
  uploading.value = true;
  lastResult.value = null;
  try {
    const raw = fileList.value
      .map((f) => (f.originFileObj ?? null) as File | null)
      .filter((f): f is File => f !== null);
    const { data } = await kbApi.uploadKbDocuments(
      targetKb.value,
      raw,
      targetCategory.value || "0",
    );
    lastResult.value = {
      ok: true,
      msg: `已导入 ${data.data.length} 篇文档,可到「知识库」Tab 查看`,
    };
    fileList.value = [];
    message.success(`已导入 ${data.data.length} 篇`);
  } catch (e) {
    lastResult.value = {
      ok: false,
      msg: `导入失败：${(e as Error)?.message ?? "未知错误"}`,
    };
  } finally {
    uploading.value = false;
  }
}

onMounted(async () => {
  const { data } = await kbApi.listKbOptions();
  kbOptions.value = data.data.map((k) => ({ value: k.id, label: k.name }));
});
</script>

<style scoped>
.integration-tab {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.intro {
  border-radius: 10px;
}
.wizard {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card {
  border-radius: 12px;
}
.source-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.source-item {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 12px 14px;
  background: var(--surface-soft);
}
.source-item--active {
  border-color: var(--color-info-strong);
  background: var(--surface-info-soft);
}
.source-item--disabled {
  opacity: 0.5;
}
.source-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}
.source-desc {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
.source-check {
  position: absolute;
  top: 12px;
  right: 12px;
  color: var(--color-info-strong);
}
.upload-icon {
  font-size: 38px;
  color: var(--color-info-strong);
}
.upload-text {
  font-size: 14px;
  margin: 6px 0 4px;
}
.upload-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.form {
  margin-top: 18px;
}
.form-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.result {
  margin-top: 14px;
}
</style>
