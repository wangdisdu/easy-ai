<template>
  <div :class="['hitl-card', `hitl-card--${riskLevel}`]">
    <div class="hitl-card-head">
      <PauseCircleOutlined :class="['hitl-card-icon', `hitl-card-icon--${riskLevel}`]" />
      <span class="hitl-card-title">需要你的确认</span>
      <span :class="['hitl-card-risk', `hitl-card-risk--${riskLevel}`]">
        {{ riskLabel }}
      </span>
      <span
        v-if="countdownVisible"
        class="hitl-countdown"
        :title="`剩余 ${remainingSeconds}s`"
      >
        <ClockCircleOutlined />
        {{ remainingSeconds }}s
      </span>
    </div>

    <div class="hitl-card-body">
      <div class="hitl-row">
        <span class="hitl-label">工具</span>
        <span class="hitl-value hitl-mono">{{ payload.tool_name }}</span>
      </div>
      <div v-if="payload.reason" class="hitl-row">
        <span class="hitl-label">原因</span>
        <span class="hitl-value">{{ payload.reason }}</span>
      </div>
      <div v-if="hasParams || editing" class="hitl-row hitl-row--block">
        <div class="hitl-label-row">
          <span class="hitl-label">参数</span>
          <a-button
            v-if="!editing"
            size="small"
            type="link"
            :disabled="busy"
            @click="startEdit"
          >修改</a-button>
        </div>
        <pre v-if="!editing" class="hitl-params">{{ paramsText }}</pre>
        <a-textarea
          v-else
          v-model:value="paramsDraft"
          :auto-size="{ minRows: 4, maxRows: 12 }"
          class="hitl-params-edit"
          spellcheck="false"
          :disabled="busy"
        />
        <div v-if="editing && parseError" class="hitl-error">
          参数 JSON 解析失败：{{ parseError }}
        </div>
      </div>
    </div>

    <div class="hitl-card-footer">
      <a-button
        v-if="editing"
        size="small"
        :disabled="busy"
        @click="cancelEdit"
      >取消修改</a-button>
      <a-button
        v-if="editing"
        size="small"
        type="primary"
        :loading="busy && lastAction === 'modify'"
        :disabled="busy || !!parseError"
        @click="onAction('modify')"
      >按修改后参数执行</a-button>
      <template v-else>
        <a-button
          v-if="!hasParams"
          size="small"
          type="link"
          :disabled="busy"
          @click="startEdit"
        >添加参数</a-button>
        <a-button
          size="small"
          danger
          :loading="busy && lastAction === 'reject'"
          :disabled="busy"
          @click="onAction('reject')"
        >拒绝</a-button>
        <a-button
          size="small"
          type="primary"
          :loading="busy && lastAction === 'confirm'"
          :disabled="busy"
          @click="onAction('confirm')"
        >确认执行</a-button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ClockCircleOutlined, PauseCircleOutlined } from "@ant-design/icons-vue";
import type { HitlAction } from "@/api/conversation";

export interface HitlPayload {
  type?: string;
  hitl_id: string;
  tool_call_id: string;
  tool_id?: string | null;
  tool_name: string;
  parameters?: Record<string, unknown>;
  reason?: string | null;
  risk_level?: string;
  matched_rule_id?: string | null;
  timeout_seconds?: number;
  deadline_ms?: number;
}

const props = defineProps<{
  payload: HitlPayload;
  busy: boolean;
}>();

const emit = defineEmits<{
  (e: "respond", action: HitlAction, parameters?: Record<string, unknown>): void;
}>();

const editing = ref(false);
const paramsDraft = ref("");
const parseError = ref("");
const lastAction = ref<HitlAction | "">("");

const hasParams = computed(() => {
  const p = props.payload.parameters;
  return !!p && Object.keys(p).length > 0;
});

const paramsText = computed(() => {
  const p = props.payload.parameters ?? {};
  if (!Object.keys(p).length) return "{}";
  return JSON.stringify(p, null, 2);
});

const riskLevel = computed(() => (props.payload.risk_level || "low").toLowerCase());

const riskLabel = computed(() => {
  switch (riskLevel.value) {
    case "high":
      return "HIGH 风险";
    case "medium":
      return "MED 风险";
    default:
      return "LOW 风险";
  }
});

// 倒计时：仅在剩余 ≤ 10s 时显示，避免一直占视觉位
const now = ref(Date.now());
let timer: number | null = null;
onMounted(() => {
  if (props.payload.deadline_ms) {
    timer = window.setInterval(() => {
      now.value = Date.now();
    }, 1000);
  }
});
onBeforeUnmount(() => {
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
});

const remainingSeconds = computed(() => {
  if (!props.payload.deadline_ms) return null;
  const left = Math.ceil((props.payload.deadline_ms - now.value) / 1000);
  return left < 0 ? 0 : left;
});

const countdownVisible = computed(() => {
  if (remainingSeconds.value === null) return false;
  return remainingSeconds.value <= 10;
});

function startEdit() {
  paramsDraft.value = paramsText.value;
  parseError.value = "";
  editing.value = true;
}

function cancelEdit() {
  editing.value = false;
  paramsDraft.value = "";
  parseError.value = "";
}

function onAction(action: HitlAction) {
  if (props.busy) return;
  if (action === "modify") {
    let parsed: Record<string, unknown>;
    try {
      const obj = JSON.parse(paramsDraft.value || "{}");
      if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
        parseError.value = "参数必须是 JSON 对象";
        return;
      }
      parsed = obj as Record<string, unknown>;
    } catch (err) {
      parseError.value = err instanceof Error ? err.message : String(err);
      return;
    }
    parseError.value = "";
    lastAction.value = "modify";
    emit("respond", "modify", parsed);
    return;
  }
  lastAction.value = action;
  emit("respond", action);
}
</script>

<style scoped>
.hitl-card {
  border: 1px solid #fde68a;
  border-radius: 12px;
  background: #fffbeb;
  padding: 12px 14px;
  margin-top: 8px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  /* 入场：从上方轻微滑入 + 淡入；只放一次，不抢注意力 */
  animation:
    hitl-card-enter 320ms cubic-bezier(0.16, 1, 0.3, 1),
    hitl-card-glow 2.4s ease-in-out infinite;
}

.hitl-card--medium {
  border-color: #facc15;
  background: #fefce8;
  animation:
    hitl-card-enter 320ms cubic-bezier(0.16, 1, 0.3, 1),
    hitl-card-glow-medium 2.4s ease-in-out infinite;
}

.hitl-card--high {
  border-color: #ef4444;
  background: #fef2f2;
  animation:
    hitl-card-enter 320ms cubic-bezier(0.16, 1, 0.3, 1),
    hitl-card-glow-high 2s ease-in-out infinite;
}

@keyframes hitl-card-enter {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* low：淡淡的金色光晕，只是"我在等" */
@keyframes hitl-card-glow {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(250, 204, 21, 0);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(250, 204, 21, 0.18);
  }
}

@keyframes hitl-card-glow-medium {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(202, 138, 4, 0);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(202, 138, 4, 0.22);
  }
}

/* high：节奏更快、范围更大的红色脉冲，强引导决策 */
@keyframes hitl-card-glow-high {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.18);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.28);
  }
}

.hitl-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hitl-card-icon {
  font-size: 16px;
  /* 暂停图标"呼吸"：透明度 + 缩放轻微变化，告诉用户卡片仍在等待 */
  animation: hitl-icon-breath 1.8s ease-in-out infinite;
  transform-origin: center;
}

@keyframes hitl-icon-breath {
  0%,
  100% {
    opacity: 0.7;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.12);
  }
}

.hitl-card-icon--low {
  color: #047857;
}

.hitl-card-icon--medium {
  color: #ca8a04;
}

.hitl-card-icon--high {
  color: #dc2626;
}

.hitl-card-title {
  font-weight: 600;
  color: #1f2937;
}

.hitl-card--medium .hitl-card-title {
  color: #854d0e;
}

.hitl-card--high .hitl-card-title {
  color: #b91c1c;
}

.hitl-card-risk {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.hitl-card-risk--medium {
  background: #fef9c3;
  color: #854d0e;
}

.hitl-card-risk--high {
  background: #fee2e2;
  color: #b91c1c;
}

.hitl-card-risk--low {
  background: #d1fae5;
  color: #047857;
}

.hitl-countdown {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #fee2e2;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  /* 最后 10s 才出现的徽标，节奏快、对比强，迫使用户做决策 */
  animation: hitl-countdown-pulse 1s ease-in-out infinite;
}

@keyframes hitl-countdown-pulse {
  0%,
  100% {
    background: #fee2e2;
    transform: scale(1);
  }
  50% {
    background: #fecaca;
    transform: scale(1.08);
  }
}

/* 尊重系统"减少动效"：关闭所有非必需动画，避免眩晕用户 */
@media (prefers-reduced-motion: reduce) {
  .hitl-card,
  .hitl-card--medium,
  .hitl-card--high,
  .hitl-card-icon,
  .hitl-countdown {
    animation: none !important;
  }
}

.hitl-card-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hitl-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  line-height: 1.5;
}

.hitl-row--block {
  flex-direction: column;
  gap: 4px;
}

.hitl-label-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hitl-label {
  flex: 0 0 auto;
  color: #6b7280;
  font-size: 12px;
  min-width: 36px;
}

.hitl-value {
  color: #111827;
  word-break: break-word;
  flex: 1;
}

.hitl-mono {
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 12px;
}

.hitl-params {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 0;
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1f2937;
  max-height: 240px;
  overflow: auto;
}

.hitl-params-edit {
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
  font-size: 12px;
}

.hitl-error {
  color: #b91c1c;
  font-size: 12px;
}

.hitl-card-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
