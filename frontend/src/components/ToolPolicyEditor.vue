<template>
  <div class="policy-editor">
    <header class="policy-header">
      <span class="policy-version" v-if="version > 0">v{{ version }}</span>
      <span class="policy-mode-label">模式</span>
      <a-radio-group v-model:value="mode" size="small" button-style="solid">
        <a-radio-button value="shadow">Shadow（仅记录）</a-radio-button>
        <a-radio-button value="active">Active（生效）</a-radio-button>
      </a-radio-group>
    </header>

    <p class="policy-hint">
      Shadow 模式下决策只入审计、不阻断；Active 模式下 deny / hitl 真正生效。
      建议新规则先在 Shadow 跑一段时间观察命中率，无误判后切 Active。
    </p>

    <ul class="rule-list">
      <li v-for="(rule, idx) in rules" :key="idx" class="rule-card">
        <header class="rule-card-header">
          <span class="rule-index">规则 {{ idx + 1 }}</span>
          <a-button size="small" type="text" danger @click="removeRule(idx)">删除</a-button>
        </header>
        <div class="rule-row">
          <span class="rule-label">优先级</span>
          <a-input-number v-model:value="rule.priority" :min="0" :max="10000" size="small" />
          <span class="rule-hint">数字越大越先匹配</span>
        </div>
        <div class="rule-row">
          <span class="rule-label">动作</span>
          <a-select v-model:value="rule.action" size="small" style="width: 180px">
            <a-select-option value="deny">deny（拒绝）</a-select-option>
            <a-select-option value="allow">allow（放行）</a-select-option>
            <a-select-option value="require_hitl">require_hitl（对话内确认）</a-select-option>
          </a-select>
        </div>
        <div class="rule-row">
          <span class="rule-label">条件变量</span>
          <a-select
            :value="rule._var_name"
            size="small"
            style="width: 280px"
            @change="(v: unknown) => onVarChange(rule, String(v))"
          >
            <a-select-opt-group label="工具参数">
              <a-select-option
                v-for="p in toolParameters"
                :key="`p:${p}`"
                :value="`parameter.${p}`"
              >parameter.{{ p }}</a-select-option>
            </a-select-opt-group>
            <a-select-opt-group label="内置变量">
              <a-select-option
                v-for="ctx in builtinVars"
                :key="`b:${ctx.name}`"
                :value="ctx.name"
              >{{ ctx.name }} — {{ ctx.label }}</a-select-option>
            </a-select-opt-group>
          </a-select>
        </div>
        <div class="rule-row">
          <span class="rule-label">算子</span>
          <a-select
            v-model:value="rule._op"
            size="small"
            style="width: 180px"
            @change="onOpChange(rule)"
          >
            <a-select-option v-for="op in opsForVar(rule)" :key="op" :value="op">
              {{ op }}
            </a-select-option>
          </a-select>
        </div>
        <div class="rule-row">
          <span class="rule-label">值</span>
          <a-input
            v-if="!isBetweenOp(rule._op) && !isCollectionOp(rule._op)"
            v-model:value="rule._value_text"
            size="small"
            style="width: 320px"
            :placeholder="valuePlaceholder(rule._op)"
          />
          <span v-if="isBetweenOp(rule._op)" class="rule-between-row">
            <a-input-number v-model:value="rule._between_low" size="small" placeholder="low" />
            <span class="rule-between-sep">~</span>
            <a-input-number v-model:value="rule._between_high" size="small" placeholder="high" />
          </span>
          <span v-if="isCollectionOp(rule._op)" class="rule-collection-row">
            <a-select
              v-model:value="rule._collection"
              mode="tags"
              size="small"
              style="width: 320px"
              placeholder="多个值，回车确认"
            />
          </span>
        </div>
        <div class="rule-row">
          <span class="rule-label">说明</span>
          <a-input
            v-model:value="rule.reason"
            size="small"
            style="width: 420px"
            placeholder="规则触发后给用户/审计看的文案"
          />
        </div>
      </li>
    </ul>

    <a-button block type="dashed" @click="addRule">
      <template #icon><PlusOutlined /></template>
      添加规则
    </a-button>

    <details class="advanced">
      <summary>高级模式：原始 AST（只读）</summary>
      <pre class="advanced-pre">{{ astPreview }}</pre>
    </details>

    <footer class="policy-footer">
      <a-button @click="$emit('cancel')">取消</a-button>
      <a-button type="primary" :loading="saving" @click="onSave">保存</a-button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as policyApi from "@/api/policy";
import type {
  PolicyAction,
  PolicyMode,
  PolicyOptionsResp,
  PolicyRuleReq,
  PolicyRuleResp,
  WhenNode,
} from "@/api/types";

interface RuleEditState {
  priority: number;
  action: PolicyAction;
  reason: string | null;
  _var_name: string;
  _var_kind: string;
  _op: string;
  _value_text: string;
  _between_low: number | null;
  _between_high: number | null;
  _collection: string[];
}

const props = defineProps<{
  toolId: string;
  toolParameters?: string[];
}>();
const emit = defineEmits<{ saved: [PolicyRuleResp[]]; cancel: [] }>();

const mode = ref<PolicyMode>("shadow");
const version = ref(0);
const rules = ref<RuleEditState[]>([]);
const saving = ref(false);
const options = ref<PolicyOptionsResp | null>(null);

const toolParameters = computed<string[]>(() => props.toolParameters ?? []);
const builtinVars = computed(() =>
  (options.value?.context_variables ?? []).filter((v) => !v.name.startsWith("parameter.")),
);

onMounted(async () => {
  const optsP = policyApi.getPolicyOptions();
  const polP = policyApi.getToolPolicy(props.toolId);
  const [optsR, polR] = await Promise.all([optsP, polP]);
  options.value = optsR.data.data;
  const pol = polR.data.data;
  mode.value = pol.mode;
  version.value = pol.version;
  rules.value = pol.rules.map(fromResp);
});

function fromResp(r: PolicyRuleResp): RuleEditState {
  // v1 仅支持 Compare 节点；If 是 And 节点暂时退化为只读（用户编辑会丢嵌套）
  const when = r.when_ast;
  if (when && when.type === "Compare") {
    const v = when.value;
    const opStr = String(when.op);
    return {
      priority: r.priority,
      action: r.action,
      reason: r.reason ?? "",
      _var_name: when.var,
      _var_kind: kindOfVar(when.var),
      _op: opStr,
      _value_text: typeof v === "string" || typeof v === "number" || typeof v === "boolean"
        ? String(v) : "",
      _between_low: opStr === "BETWEEN" && Array.isArray(v) ? Number(v[0]) : null,
      _between_high: opStr === "BETWEEN" && Array.isArray(v) ? Number(v[1]) : null,
      _collection: (opStr === "IN" || opStr === "NOT_IN") && Array.isArray(v)
        ? v.map((x) => String(x)) : [],
    };
  }
  // 非 Compare（And 等）转成默认占位，提示用户走 API
  return {
    priority: r.priority,
    action: r.action,
    reason: r.reason ?? "[此规则含复合条件，UI 不支持编辑，请走 API]",
    _var_name: "parameter.",
    _var_kind: "any",
    _op: "EQ",
    _value_text: "",
    _between_low: null,
    _between_high: null,
    _collection: [],
  };
}

function kindOfVar(name: string): string {
  if (name.startsWith("parameter.")) return "any";
  const ctx = options.value?.context_variables.find((v) => v.name === name);
  return ctx?.kind ?? "any";
}

function opsForVar(rule: RuleEditState): string[] {
  if (!options.value) return ["EQ"];
  const opMap = options.value.operators_by_kind;
  // 任意类型变量（参数 / user.role 等）暴露所有算子；强类型变量仅暴露其类型 + 通用 EQ/NEQ
  if (rule._var_kind === "any") {
    return [...opMap.any, ...opMap.string, ...opMap.number, ...opMap.collection];
  }
  return [...opMap.any, ...(opMap[rule._var_kind] ?? [])];
}

function onVarChange(rule: RuleEditState, name: string) {
  rule._var_name = name;
  rule._var_kind = kindOfVar(name);
  // 算子如果不再适用，重置成 EQ
  if (!opsForVar(rule).includes(rule._op)) {
    rule._op = "EQ";
  }
}

function onOpChange(rule: RuleEditState) {
  // 切换算子后清空可能不再适用的输入
  if (!isBetweenOp(rule._op)) {
    rule._between_low = null;
    rule._between_high = null;
  }
  if (!isCollectionOp(rule._op)) {
    rule._collection = [];
  }
}

function isBetweenOp(op: string): boolean {
  return op === "BETWEEN";
}

function isCollectionOp(op: string): boolean {
  return op === "IN" || op === "NOT_IN";
}

function valuePlaceholder(op: string): string {
  if (op === "MATCHES") return "正则字符串，例如 \\@x\\.com$";
  if (["GT", "LT", "GTE", "LTE"].includes(op)) return "数值";
  return "值";
}

function addRule() {
  rules.value.push({
    priority: 100,
    action: "deny",
    reason: "",
    _var_name: "parameter.",
    _var_kind: "any",
    _op: "EQ",
    _value_text: "",
    _between_low: null,
    _between_high: null,
    _collection: [],
  });
}

function removeRule(idx: number) {
  rules.value.splice(idx, 1);
}

function buildAst(rule: RuleEditState): WhenNode {
  const op = rule._op;
  let value: unknown;
  if (op === "BETWEEN") {
    value = [rule._between_low, rule._between_high];
  } else if (op === "IN" || op === "NOT_IN") {
    value = [...rule._collection];
  } else {
    // 数值算子尝试转 number
    const numericOps = ["GT", "LT", "GTE", "LTE"];
    if (numericOps.includes(op)) {
      const n = Number(rule._value_text);
      value = Number.isFinite(n) ? n : rule._value_text;
    } else {
      value = rule._value_text;
    }
  }
  return { type: "Compare", op, var: rule._var_name, value };
}

async function onSave() {
  // 简校验
  for (let i = 0; i < rules.value.length; i++) {
    const r = rules.value[i];
    if (!r._var_name || r._var_name === "parameter.") {
      message.error(`规则 ${i + 1}：请选择条件变量`);
      return;
    }
    if (isBetweenOp(r._op) && (r._between_low === null || r._between_high === null)) {
      message.error(`规则 ${i + 1}：BETWEEN 需要 low 和 high 两个数值`);
      return;
    }
  }
  saving.value = true;
  try {
    const payload = {
      mode: mode.value,
      rules: rules.value.map<PolicyRuleReq>((r) => ({
        priority: r.priority,
        action: r.action,
        when_ast: buildAst(r),
        reason: r.reason || null,
      })),
    };
    const { data } = await policyApi.putToolPolicy(props.toolId, payload);
    version.value = data.data.version;
    message.success(`策略已保存（版本 v${data.data.version}）`);
    emit("saved", data.data.rules);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    message.error("保存失败：" + msg);
  } finally {
    saving.value = false;
  }
}

const astPreview = computed(() => {
  const payload = {
    mode: mode.value,
    rules: rules.value.map((r) => ({
      priority: r.priority,
      action: r.action,
      when: buildAst(r),
      reason: r.reason || null,
    })),
  };
  return JSON.stringify(payload, null, 2);
});
</script>

<style scoped>
.policy-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.policy-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.policy-version {
  background: #e2e8f0;
  color: #475569;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.policy-mode-label {
  font-size: 13px;
  color: #475569;
}

.policy-hint {
  font-size: 12px;
  color: #64748b;
  margin: 0;
  line-height: 1.6;
}

.rule-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #fafafa;
}

.rule-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.rule-index {
  font-weight: 600;
  color: #1f2937;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rule-label {
  display: inline-block;
  width: 72px;
  color: #475569;
  font-size: 13px;
}

.rule-hint {
  font-size: 12px;
  color: #94a3b8;
}

.rule-between-row,
.rule-collection-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.rule-between-sep {
  color: #94a3b8;
}

.advanced {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 12px;
  background: #fff;
}

.advanced summary {
  cursor: pointer;
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}

.advanced-pre {
  margin: 8px 0 0;
  padding: 8px;
  background: #f8fafc;
  border-radius: 4px;
  font-size: 12px;
  max-height: 280px;
  overflow: auto;
  font-family: ui-monospace, "JetBrains Mono", monospace;
}

.policy-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid #e2e8f0;
}
</style>
