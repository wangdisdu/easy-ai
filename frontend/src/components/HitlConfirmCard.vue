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

    <div v-if="timedOut" class="hitl-timeout-banner">
      <a-spin size="small" />
      <span>等待超时，已自动取消并继续 agent…</span>
    </div>
    <div v-else class="hitl-card-footer">
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

    <!-- 卡片底部进度条：剩余时间占总等待时长的比例。
         数值通过 transition 平滑过渡；颜色随风险等级走。
         没有 deadline 数据时整条隐藏，不占视觉。 -->
    <div v-if="progressVisible" class="hitl-progress">
      <div
        :class="['hitl-progress-fill', `hitl-progress-fill--${riskLevel}`]"
        :style="{ width: progressPercent + '%' }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
  (e: "timeout"): void;
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

// 进度条 / 倒计时共用一份心跳；500ms 让进度条肉眼平滑，倒计时只用秒粒度
const now = ref(Date.now());
let timer: number | null = null;
onMounted(() => {
  if (props.payload.deadline_ms) {
    timer = window.setInterval(() => {
      now.value = Date.now();
    }, 500);
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

const progressVisible = computed(() => {
  return !!props.payload.deadline_ms && !!props.payload.timeout_seconds;
});

const progressPercent = computed(() => {
  const total = props.payload.timeout_seconds ?? 0;
  const deadline = props.payload.deadline_ms ?? 0;
  if (!total || !deadline) return 0;
  const remainingMs = deadline - now.value;
  if (remainingMs <= 0) return 0;
  const pct = (remainingMs / (total * 1000)) * 100;
  if (pct > 100) return 100;
  return pct;
});

// 到点自动 reject：避免用户面前卡片"无人响应、agent 后台还在跑"的怪象。
// 触发时同时通知父组件 onTimeout，让它走标准 respond 通道——SSE 续跑能把
// agent 后续输出实时推回到当前对话。worker 仍是关闭页面/失焦场景的兜底。
const autoFired = ref(false);
watch(remainingSeconds, (value) => {
  if (value === null || value > 0) return;
  if (autoFired.value || props.busy) return;
  autoFired.value = true;
  emit("timeout");
  emit("respond", "reject");
});

const timedOut = computed(() => remainingSeconds.value === 0);

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
  position: relative;
  overflow: hidden;
}

.hitl-card--medium {
  border-color: #facc15;
  background: #fefce8;
}

.hitl-card--high {
  border-color: #ef4444;
  background: #fef2f2;
}

.hitl-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hitl-card-icon {
  font-size: 16px;
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

.hitl-timeout-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 500;
}

/* 进度条：贴卡片底部内沿，不挤压内容。
   宽度由 :style 驱动；transition 让 500ms 心跳之间也是平滑下滑。 */
.hitl-progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 3px;
  background: rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.hitl-progress-fill {
  height: 100%;
  transition: width 500ms linear;
}

.hitl-progress-fill--low {
  background: #10b981;
}

.hitl-progress-fill--medium {
  background: #ca8a04;
}

.hitl-progress-fill--high {
  background: #dc2626;
}
</style>
