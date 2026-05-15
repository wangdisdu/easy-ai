<template>
  <section class="kb-import" v-if="kb">
    <a-button type="link" class="back-btn" @click="router.push(`/knowledge/${kbId}`)">
      <template #icon><ArrowLeftOutlined /></template>
      返回 {{ kb.name }}
    </a-button>

    <div class="head">
      <h2 class="title">上传文档到 {{ kb.name }}</h2>
      <p class="sub">
        上传后由 RAGFlow 自动解析与向量化，前端可在文档列表里看到状态翻转。
        单文件 ≤ 50MB，单次最多 20 个文件。
      </p>
    </div>

    <a-card class="card" :body-style="{ padding: '24px' }">
      <a-upload-dragger
        v-model:file-list="fileList"
        :before-upload="onBeforeUpload"
        :multiple="true"
        :show-upload-list="true"
        :disabled="uploading"
      >
        <p class="upload-icon"><InboxOutlined /></p>
        <p class="upload-text">拖拽文件到此处或点击选择</p>
        <p class="upload-hint">
          支持 PDF / DOCX / XLSX / Markdown / TXT / CSV / JSON / 图片
        </p>
      </a-upload-dragger>

      <a-form layout="vertical" class="form">
        <a-form-item label="分类标签（可选）">
          <a-input
            v-model:value="category"
            placeholder="如 告警处置手册、操作指南"
            :disabled="uploading"
          />
          <div class="form-hint">用于前端按分类筛选；不影响 RAGFlow 解析</div>
        </a-form-item>
      </a-form>

      <div class="actions">
        <a-button @click="router.push(`/knowledge/${kbId}`)" :disabled="uploading">取消</a-button>
        <a-button
          type="primary"
          :disabled="!fileList.length"
          :loading="uploading"
          @click="onSubmit"
        >
          开始上传（{{ fileList.length }}）
        </a-button>
      </div>
    </a-card>

    <a-alert
      v-if="lastResult"
      :type="lastResult.success ? 'success' : 'error'"
      :message="lastResult.message"
      show-icon
      class="result"
    />
  </section>
  <a-spin v-else class="loading" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, InboxOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import type { UploadFile, UploadProps } from "ant-design-vue";
import * as kbApi from "@/api/kb";
import type { KbResp } from "@/api/types";

const router = useRouter();
const route = useRoute();
const kbId = computed(() => String(route.params.id));
const kb = ref<KbResp | null>(null);

const fileList = ref<UploadFile[]>([]);
const category = ref("");
const uploading = ref(false);
const lastResult = ref<{ success: boolean; message: string } | null>(null);

const MAX_FILES = 20;
const MAX_SIZE = 50 * 1024 * 1024;

const onBeforeUpload: UploadProps["beforeUpload"] = (file) => {
  if (fileList.value.length >= MAX_FILES) {
    message.error(`最多 ${MAX_FILES} 个文件`);
    return false;
  }
  if (file.size > MAX_SIZE) {
    message.error(`${file.name} 超过 50MB`);
    return false;
  }
  // 返回 false 阻止 antd 自己上传；我们走自己的 onSubmit 批量上传
  return false;
};

async function onSubmit() {
  if (!fileList.value.length) return;
  uploading.value = true;
  lastResult.value = null;
  try {
    const rawFiles: File[] = fileList.value
      .map((f) => (f.originFileObj ?? null) as File | null)
      .filter((f): f is File => f !== null);
    const { data } = await kbApi.uploadKbDocuments(
      kbId.value,
      rawFiles,
      category.value.trim() || undefined,
    );
    const n = data.data.length;
    lastResult.value = {
      success: true,
      message: `已上传 ${n} 篇文档，RAGFlow 解析中（可返回详情页轮询状态）`,
    };
    fileList.value = [];
    message.success(`已上传 ${n} 篇`);
  } catch (e) {
    lastResult.value = {
      success: false,
      message: `上传失败：${(e as Error)?.message ?? "未知错误"}`,
    };
  } finally {
    uploading.value = false;
  }
}

onMounted(async () => {
  const { data } = await kbApi.getKb(kbId.value);
  kb.value = data.data;
});
</script>

<style scoped>
.kb-import {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.back-btn {
  align-self: flex-start;
}
.head {
  margin-bottom: 6px;
}
.title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}
.sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.card {
  border-radius: 14px;
}
.upload-icon {
  font-size: 40px;
  color: var(--color-info-strong);
}
.upload-text {
  font-size: 14px;
  margin: 8px 0 4px;
}
.upload-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.form {
  margin-top: 20px;
}
.form-hint {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
.result {
  margin-top: 4px;
}
.loading {
  display: block;
  text-align: center;
  padding-top: 80px;
}
</style>
