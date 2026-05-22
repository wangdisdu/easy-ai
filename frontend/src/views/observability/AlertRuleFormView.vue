<template>
  <section class="alert-form-page">
    <div class="form-header">
      <a-button type="text" @click="router.push('/observability/alert-rule')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <h2 class="form-title">{{ isEdit ? "编辑告警规则" : "新建告警规则" }}</h2>
    </div>

    <div class="form-card">
      <div class="form-row">
        <label class="form-label"><span class="required">*</span>规则名称</label>
        <div class="form-field">
          <a-input v-model:value="form.rule_name" :maxlength="255" placeholder="如:全局成功率过低" />
        </div>
      </div>

      <div class="form-row form-row--top">
        <label class="form-label">规则描述</label>
        <div class="form-field">
          <a-textarea v-model:value="form.description" :rows="2" placeholder="一句话说明这条规则监控什么" />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label"><span class="required">*</span>监控指标</label>
        <div class="form-field">
          <a-select
            v-model:value="form.metric_type"
            style="width: 260px"
            :options="METRIC_OPTIONS"
            :field-names="{ label: 'label', value: 'value' }"
            @change="onMetricChange"
          />
        </div>
      </div>

      <div v-if="form.metric_type === 'llm_error_count_by_type'" class="form-row">
        <label class="form-label">目标错误类型</label>
        <div class="form-field">
          <a-select
            v-model:value="form.target_error_type"
            style="width: 260px"
            placeholder="留空 = 任意 LLM 错误"
            allow-clear
            :options="ERROR_TYPE_OPTIONS"
            :field-names="{ label: 'label', value: 'value' }"
          />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label"><span class="required">*</span>触发条件</label>
        <div class="form-field cond-field">
          <span class="cond-metric">{{ METRIC_LABEL[form.metric_type] }}</span>
          <a-select
            v-model:value="form.operator"
            style="width: 130px"
            :options="OPERATOR_OPTIONS"
            :field-names="{ label: 'label', value: 'value' }"
          />
          <a-input-number v-model:value="form.threshold" style="width: 140px" :addon-after="unitLabel" />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">告警级别</label>
        <div class="form-field">
          <a-select
            v-model:value="form.level"
            style="width: 160px"
            :options="LEVEL_OPTIONS"
            :field-names="{ label: 'label', value: 'value' }"
          />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">监控范围</label>
        <div class="form-field">
          <a-select
            v-model:value="form.scope"
            style="width: 200px"
            :options="SCOPE_OPTIONS"
            :field-names="{ label: 'label', value: 'value' }"
          />
          <p class="form-hint">P1 阶段按全局汇总评估;per_app / per_request 为后续迭代</p>
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">监控窗口</label>
        <div class="form-field inline-field">
          <a-input-number v-model:value="form.window_minutes" :min="1" :max="1440" /> 分钟
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">冷却时间</label>
        <div class="form-field inline-field">
          <a-input-number v-model:value="form.cooldown_minutes" :min="0" :max="1440" /> 分钟
          <span class="form-hint form-hint--inline">命中后此时长内不重复产生告警</span>
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">通知方式</label>
        <div class="form-field">
          <a-checkbox :checked="true" disabled>站内通知</a-checkbox>
          <p class="form-hint">P1 仅支持站内通知,后续扩展邮件 / Webhook</p>
        </div>
      </div>

      <div class="form-row form-row--top">
        <label class="form-label">告警内容</label>
        <div class="form-field">
          <a-textarea
            v-model:value="form.message_template"
            :rows="2"
            placeholder="留空使用默认模板"
          />
          <p class="form-hint">{{ placeholderHint }}</p>
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">启用</label>
        <div class="form-field">
          <a-switch v-model:checked="form.enabled" />
        </div>
      </div>
    </div>

    <div class="form-actions">
      <a-button @click="router.push('/observability/alert-rule')">取消</a-button>
      <a-button type="primary" :loading="submitting" @click="onSubmit">
        {{ isEdit ? "保存" : "创建" }}
      </a-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as alertApi from "@/api/alert";
import {
  ERROR_TYPE_OPTIONS,
  LEVEL_OPTIONS,
  METRIC_LABEL,
  METRIC_OPTIONS,
  OPERATOR_OPTIONS,
  SCOPE_OPTIONS,
  metricUnit,
} from "./alertMeta";

const router = useRouter();
const route = useRoute();
const isEdit = computed(() => !!route.params.id);
const editId = computed(() => route.params.id as string);
const submitting = ref(false);

// 占位符提示。放在 JS 字符串里,避免 Vue 模板把 {{...}} 当成插值表达式。
const placeholderHint =
  "支持占位符 {{level}} {{metric}} {{value}} {{threshold}} {{time}},留空使用默认模板";

const form = reactive({
  rule_name: "",
  description: "",
  metric_type: "success_rate",
  target_error_type: undefined as string | undefined,
  operator: "lt",
  threshold: 99,
  threshold_unit: "%",
  scope: "global",
  level: "warning",
  window_minutes: 5,
  cooldown_minutes: 10,
  message_template: "",
  enabled: true,
});

const unitLabel = computed(() => form.threshold_unit || "次");

function onMetricChange() {
  form.threshold_unit = metricUnit(form.metric_type);
  if (form.metric_type !== "llm_error_count_by_type") {
    form.target_error_type = undefined;
  }
}

async function loadEditData() {
  const { data } = await alertApi.getAlertRule(editId.value);
  const r = data.data;
  form.rule_name = r.rule_name;
  form.description = r.description || "";
  form.metric_type = r.metric_type;
  form.target_error_type = r.target_error_type || undefined;
  form.operator = r.operator;
  form.threshold = r.threshold;
  form.threshold_unit = r.threshold_unit || "";
  form.scope = r.scope;
  form.level = r.level;
  form.window_minutes = r.window_minutes;
  form.cooldown_minutes = r.cooldown_minutes;
  form.message_template = r.message_template || "";
  form.enabled = r.enabled;
}

async function onSubmit() {
  if (!form.rule_name.trim()) {
    message.error("请填写规则名称");
    return;
  }
  if (form.threshold === null || form.threshold === undefined) {
    message.error("请填写阈值");
    return;
  }
  const body = {
    rule_name: form.rule_name.trim(),
    description: form.description || undefined,
    metric_type: form.metric_type,
    target_error_type:
      form.metric_type === "llm_error_count_by_type" ? form.target_error_type ?? null : null,
    operator: form.operator,
    threshold: form.threshold,
    threshold_unit: form.threshold_unit || null,
    scope: form.scope,
    level: form.level,
    window_minutes: form.window_minutes,
    cooldown_minutes: form.cooldown_minutes,
    notify_channels: ["inbox"],
    message_template: form.message_template || null,
    enabled: form.enabled,
  };
  submitting.value = true;
  try {
    if (isEdit.value) {
      await alertApi.updateAlertRule(editId.value, body);
      message.success("已保存");
    } else {
      await alertApi.createAlertRule(body);
      message.success("规则已创建");
    }
    router.push("/observability/alert-rule");
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  if (isEdit.value) await loadEditData();
});
</script>

<style scoped>
.alert-form-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-violet-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.form-header { display: flex; align-items: center; gap: 8px; }
.form-title { margin: 0; font-size: 20px; font-weight: 700; color: var(--color-text); }

.form-card {
  margin-top: 18px;
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--surface-strong);
}

.form-row { display: flex; gap: 16px; margin-bottom: 16px; }
.form-row--top { align-items: flex-start; }
.form-label { flex-shrink: 0; width: 88px; text-align: right; font-size: 13px; color: var(--color-text-secondary); padding-top: 6px; }
.required { color: var(--color-error); margin-right: 2px; }
.form-field { flex: 1; }
.inline-field { display: flex; align-items: center; gap: 8px; }
.cond-field { display: flex; align-items: center; gap: 10px; }
.cond-metric { font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.form-hint { margin: 4px 0 0; font-size: 12px; color: var(--color-text-quaternary); }
.form-hint--inline { margin: 0; }

.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px; }

@media (max-width: 960px) {
  .form-row { flex-direction: column; gap: 6px; }
  .form-label { width: auto; text-align: left; padding-top: 0; }
  .cond-field { flex-wrap: wrap; }
}
</style>
