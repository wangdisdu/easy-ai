<template>
  <div class="intg-form-page">
    <div class="intg-form-header">
      <a-button type="link" @click="goBack">← 返回应用集成</a-button>
      <h2 class="intg-form-title">{{ isEdit ? "编辑集成应用" : "创建集成应用" }}</h2>
      <p class="intg-form-subtitle">
        注册一个外部系统,分配 API Key 并授权可调用的应用
      </p>
    </div>

    <a-row :gutter="24">
      <a-col :xs="24" :md="14">
        <a-card title="集成应用信息" :bordered="false" class="intg-form-card">
          <a-form ref="formRef" :model="formModel" :rules="formRules" layout="vertical">
            <a-form-item label="应用名称" name="name">
              <a-input
                v-model:value="formModel.name"
                placeholder="例如:风控工单系统"
                :max-length="64"
                show-count
              />
            </a-form-item>
            <a-form-item label="描述">
              <a-textarea
                v-model:value="formModel.description"
                :auto-size="{ minRows: 2, maxRows: 4 }"
                :max-length="500"
                show-count
                placeholder="描述该外部系统的用途和集成场景..."
              />
            </a-form-item>
          </a-form>
        </a-card>

        <a-card title="管控配置" :bordered="false" class="intg-form-card">
          <a-form layout="vertical">
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    日配额(次/天)
                    <a-tooltip title="留空 = 继承全局默认;填 0 = 显式不限额">
                      <span class="intg-form-hint">[?]</span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="formModel.quota"
                    :min="0"
                    placeholder="留空 = 全局默认"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    限流(次/分钟)
                    <a-tooltip title="留空 = 继承全局默认;填 0 = 显式不限速">
                      <span class="intg-form-hint">[?]</span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="formModel.rate_limit"
                    :min="0"
                    placeholder="留空 = 全局默认"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="16">
              <a-col :span="12">
                <a-form-item label="超时(秒)">
                  <a-input-number
                    v-model:value="formModel.timeout"
                    :min="1"
                    placeholder="留空 = 全局默认"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="过期时间">
                  <a-date-picker
                    v-model:value="formModel.expire_at"
                    value-format="YYYY-MM-DD"
                    placeholder="留空则永不过期"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-form-item label="白名单(可选,逗号分隔)">
              <a-input
                v-model:value="formModel.whitelist"
                placeholder="例如:10.1.2.3, 192.168.1.10"
              />
            </a-form-item>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :md="10">
        <a-card :bordered="false" class="intg-form-card intg-bind-card">
          <template #title>
            绑定应用权限
            <span class="intg-form-count">已选 {{ selectedCount }} 个应用</span>
          </template>
          <p class="intg-form-hint-block">
            选择该集成应用可调用的应用(P0 仅支持 智能体 / 对话 / 知识库 三类)
          </p>
          <a-spin :spinning="bindLoading">
            <div v-for="group in groups" :key="group.type" class="intg-bind-group">
              <div class="intg-bind-group__header">
                <span class="intg-bind-group__label">{{ group.label }}</span>
                <span class="intg-bind-group__count">{{ group.apps.length }}</span>
              </div>
              <div v-if="group.apps.length === 0" class="intg-bind-empty">
                暂无可绑定的应用,请先在应用工厂中发布应用
              </div>
              <div v-else class="intg-bind-list">
                <label
                  v-for="app in group.apps"
                  :key="`${group.type}-${app.id}`"
                  class="intg-bind-item"
                  :class="{ 'intg-bind-item--selected': isSelected(group.type, app.id) }"
                >
                  <a-checkbox
                    :checked="isSelected(group.type, app.id)"
                    @change="toggleBind(group.type, app.id)"
                  />
                  <div class="intg-bind-item__info">
                    <span class="intg-bind-item__name">{{ app.name }}</span>
                    <span class="intg-muted">{{ app.description || "" }}</span>
                  </div>
                </label>
              </div>
            </div>
          </a-spin>
        </a-card>
      </a-col>
    </a-row>

    <div class="intg-form-actions">
      <a-button @click="goBack">{{ isEdit ? "返回列表" : "取消" }}</a-button>
      <a-button type="primary" :loading="submitting" @click="onSubmit">
        {{ isEdit ? "保存修改" : "创建并生成 API Key" }}
      </a-button>
    </div>

    <!-- 创建成功 → 明文 Key 弹窗 -->
    <a-modal
      v-model:open="plainOpen"
      title="集成应用创建成功"
      :footer="null"
      :mask-closable="false"
      width="540px"
    >
      <a-alert
        type="success"
        show-icon
        message="已生成 API Key"
        class="intg-plain-alert"
      />
      <a-alert
        type="warning"
        show-icon
        message="请立即保存此 Key,关闭后将无法再次查看完整内容"
        class="intg-plain-alert"
      />
      <div class="intg-plain-box">
        <code>{{ plainKey }}</code>
        <a-button size="small" @click="copyPlain">复制</a-button>
      </div>
      <div class="intg-plain-footer">
        <a-button type="primary" @click="closePlainAndBack">返回列表</a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import * as api from "@/api/integration";
import { pageApp } from "@/api/app";
import type { AppResp, BoundAppItem } from "@/api/types";

const route = useRoute();
const router = useRouter();

const isEdit = computed(() => Boolean(route.params.id));
const editingId = computed(() => (route.params.id as string | undefined) ?? null);

const formRef = ref<FormInstance>();
const submitting = ref(false);
const bindLoading = ref(false);

interface FormModel {
  name: string;
  description: string;
  quota: number | null;
  rate_limit: number | null;
  timeout: number | null;
  expire_at: string | null;
  whitelist: string;
}

const formModel = reactive<FormModel>({
  name: "",
  description: "",
  quota: null,
  rate_limit: null,
  timeout: null,
  expire_at: null,
  whitelist: "",
});

const formRules: Record<string, Rule[]> = {
  name: [{ required: true, message: "请输入应用名称" }],
};

// 绑定应用:按类型分组
interface Group {
  type: "agent" | "llm" | "rag";
  label: string;
  apps: AppResp[];
}
const groups = ref<Group[]>([
  { type: "agent", label: "智能体应用", apps: [] },
  { type: "llm", label: "对话应用", apps: [] },
  { type: "rag", label: "知识库", apps: [] },
]);

const selected = ref<Set<string>>(new Set());

const selectedCount = computed(() => selected.value.size);

function makeKey(type: string, id: string) {
  return `${type}:${id}`;
}

function isSelected(type: string, id: string) {
  return selected.value.has(makeKey(type, id));
}

function toggleBind(type: string, id: string) {
  const k = makeKey(type, id);
  if (selected.value.has(k)) {
    selected.value.delete(k);
  } else {
    selected.value.add(k);
  }
  // trigger reactivity
  selected.value = new Set(selected.value);
}

async function loadBindableApps() {
  bindLoading.value = true;
  try {
    // 拉取已发布的应用;P0 数量级有限,一次性 1000 条;后续可按类型分次拉
    const { data } = await pageApp({
      page_no: 1,
      page_size: 1000,
      app_status: "published",
    });
    const buckets: Record<string, AppResp[]> = { agent: [], llm: [], rag: [] };
    for (const app of data.data as AppResp[]) {
      if (app.app_type in buckets) {
        buckets[app.app_type].push(app);
      }
    }
    for (const g of groups.value) {
      g.apps = buckets[g.type] ?? [];
    }
  } finally {
    bindLoading.value = false;
  }
}

async function loadIntegration(id: string) {
  const { data } = await api.getIntegration(id);
  const intg = data.data;
  formModel.name = intg.name;
  formModel.description = intg.description ?? "";
  formModel.quota = intg.quota;
  formModel.rate_limit = intg.rate_limit;
  formModel.timeout = intg.timeout;
  formModel.expire_at = intg.expire_at
    ? new Date(intg.expire_at).toISOString().slice(0, 10)
    : null;
  formModel.whitelist = intg.whitelist ?? "";
  selected.value = new Set(intg.bound_apps.map((b) => makeKey(b.app_type, b.app_id)));
}

function collectBoundApps(): BoundAppItem[] {
  return Array.from(selected.value).map((k) => {
    const [app_type, app_id] = k.split(":");
    return { app_type, app_id };
  });
}

function expireToMs(s: string | null): number | null {
  if (!s) return null;
  // 解析为当天 23:59:59 的本地时间,作为"当天有效"
  const d = new Date(`${s}T23:59:59`);
  return d.getTime();
}

async function onSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  submitting.value = true;
  try {
    const body = {
      name: formModel.name,
      description: formModel.description || null,
      quota: formModel.quota,
      rate_limit: formModel.rate_limit,
      timeout: formModel.timeout,
      whitelist: formModel.whitelist || null,
      expire_at: expireToMs(formModel.expire_at),
      bound_apps: collectBoundApps(),
    };
    if (isEdit.value && editingId.value) {
      await api.updateIntegration(editingId.value, body);
      message.success("已保存");
      router.push({ name: "integration" });
    } else {
      const { data } = await api.createIntegration(body);
      if (data.data.first_key) {
        plainKey.value = data.data.first_key.plaintext;
        plainOpen.value = true;
      } else {
        message.warning("集成应用已创建,但 API Key 生成失败,请手动创建");
        router.push({ name: "integration" });
      }
    }
  } finally {
    submitting.value = false;
  }
}

const plainOpen = ref(false);
const plainKey = ref("");

async function copyPlain() {
  try {
    await navigator.clipboard.writeText(plainKey.value);
    message.success("已复制到剪贴板");
  } catch {
    message.error("复制失败,请手动选择文本");
  }
}

function closePlainAndBack() {
  plainOpen.value = false;
  router.push({ name: "integration" });
}

function goBack() {
  router.push({ name: "integration" });
}

onMounted(async () => {
  await loadBindableApps();
  if (isEdit.value && editingId.value) {
    await loadIntegration(editingId.value);
  }
});
</script>

<style scoped>
.intg-form-page {
  min-height: 100%;
}

.intg-form-header {
  margin-bottom: 16px;
}

.intg-form-title {
  margin: 4px 0 0;
  font-size: 20px;
  font-weight: 600;
}

.intg-form-subtitle {
  margin: 4px 0 0;
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.intg-form-card {
  margin-bottom: 16px;
  background: var(--surface-base);
}

.intg-form-hint {
  margin-left: 4px;
  color: var(--color-text-tertiary);
  font-size: 12px;
  cursor: help;
}

.intg-form-hint-block {
  margin: -4px 0 12px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.intg-form-count {
  margin-left: 12px;
  font-size: 12px;
  font-weight: normal;
  color: var(--color-text-tertiary);
}

.intg-bind-card :deep(.ant-card-body) {
  max-height: 540px;
  overflow-y: auto;
}

.intg-bind-group {
  margin-bottom: 16px;
}

.intg-bind-group__header {
  display: flex;
  justify-content: space-between;
  font-weight: 500;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--color-border-secondary, #f0f0f0);
}

.intg-bind-group__count {
  color: var(--color-text-tertiary);
  font-weight: normal;
}

.intg-bind-empty {
  color: var(--color-text-tertiary);
  font-size: 12px;
  padding: 8px 0;
}

.intg-bind-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.intg-bind-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--color-border-secondary, #f0f0f0);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.intg-bind-item:hover {
  border-color: var(--color-primary, #1677ff);
}

.intg-bind-item--selected {
  border-color: var(--color-primary, #1677ff);
  background: var(--color-primary-bg, rgba(22, 119, 255, 0.06));
}

.intg-bind-item__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.intg-bind-item__name {
  font-weight: 500;
}

.intg-muted {
  color: var(--color-text-tertiary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.intg-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.intg-plain-alert {
  margin-bottom: 12px;
}

.intg-plain-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--color-fill-quaternary, rgba(0, 0, 0, 0.04));
  border-radius: 4px;
}

.intg-plain-box code {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 13px;
  word-break: break-all;
}

.intg-plain-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
