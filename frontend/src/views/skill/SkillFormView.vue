<template>
  <section class="skill-form-page">
    <div class="form-header">
      <a-button type="text" @click="router.push('/skill')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <h2 class="form-title">{{ isEdit ? "编辑技能" : "创建技能" }}</h2>
    </div>

    <div class="form-body">
      <!-- Left: Main Form -->
      <div class="form-main">
        <div class="form-card">
          <div class="form-row">
            <label class="form-label"><span class="required">*</span>技能名称</label>
            <div class="form-field">
              <a-input
                v-model:value="form.name"
                :maxlength="64"
                placeholder="仅小写字母、数字、连字符，如 web-search"
              />
            </div>
          </div>

          <div class="form-row form-row--top">
            <label class="form-label">技能描述</label>
            <div class="form-field">
              <a-textarea v-model:value="form.description" :rows="2" placeholder="一句话描述技能功能" />
            </div>
          </div>

          <div class="form-row form-row--top">
            <label class="form-label"><span class="required">*</span>技能说明</label>
            <div class="form-field">
              <a-textarea
                v-model:value="form.instruction"
                :rows="12"
                placeholder="Markdown 格式，定义执行步骤、输入输出、注意事项..."
              />
              <p class="form-hint">大模型根据此说明决定如何编排工具调用</p>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label">技能分类</label>
            <div class="form-field">
              <a-select
                v-model:value="form.category_ids"
                style="width: 100%"
                placeholder="选择应用分类（可多选）"
                mode="multiple"
                :options="categoryOptions"
                option-filter-prop="label"
                allow-clear
              />
              <p class="form-hint">
                分类由系统配置 → 分类管理统一维护
              </p>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <a-button @click="router.push('/skill')">取消</a-button>
          <a-button type="primary" :loading="submitting" @click="onSubmit">
            {{ isEdit ? "保存" : "创建" }}
          </a-button>
        </div>
      </div>

      <!-- Right: Tool Binding Panel -->
      <div class="tool-panel">
        <div class="tool-panel-card">
          <h3 class="panel-title">
            绑定工具
            <span class="panel-count">{{ selectedTools.length }}</span>
          </h3>

          <div v-if="selectedTools.length" class="selected-tools">
            <span v-for="t in selectedTools" :key="t.tool_name" class="selected-tag">
              {{ t.tool_name }}
              <CloseOutlined class="selected-tag-close" @click="removeTool(t)" />
            </span>
          </div>

          <a-input-search
            v-model:value="toolSearch"
            placeholder="搜索工具..."
            allow-clear
            size="small"
            class="tool-search"
          />
          <div class="tool-source-filter">
            <button
              v-for="f in toolSourceFilters"
              :key="f.value"
              :class="['tsf-btn', { 'tsf-btn--active': toolSourceFilter === f.value }]"
              @click="toolSourceFilter = f.value"
            >
              {{ f.label }}
            </button>
          </div>

          <div class="avail-tool-list">
            <div
              v-for="t in filteredAvailableTools"
              :key="t.key"
              :class="['avail-tool-item', { 'avail-tool-item--selected': isSelected(t) }]"
              @click="toggleTool(t)"
            >
              <a-checkbox :checked="isSelected(t)" class="avail-tool-check" />
              <div class="avail-tool-body">
                <span class="avail-tool-name">{{ t.tool_name }}</span>
                <span :class="['source-tag', 'source-tag--' + t.source]">{{ sourceLabel[t.source] }}</span>
              </div>
              <span class="avail-tool-desc">{{ t.description }}</span>
            </div>
            <div v-if="!filteredAvailableTools.length" class="avail-tool-empty">无匹配工具</div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, CloseOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as categoryApi from "@/api/appCategory";
import * as skillApi from "@/api/skill";
import * as toolApi from "@/api/tool";
import type { SkillToolItem, ToolResp } from "@/api/types";

const router = useRouter();
const route = useRoute();
const isEdit = computed(() => !!route.params.id);
const editId = computed(() => route.params.id as string);
const submitting = ref(false);
const categoryOptions = ref<Array<{ value: string; label: string }>>([]);

const sourceLabel: Record<string, string> = { builtin: "内置", mcp: "MCP", api: "API" };

const form = reactive({
  name: "",
  description: "",
  category_ids: [] as string[],
  instruction: "",
});

// ── Tool binding ──

interface AvailTool {
  key: string;
  tool_id: string;
  tool_name: string;
  source: string;
  description: string;
}

const allAvailableTools = ref<AvailTool[]>([]);
const selectedTools = ref<SkillToolItem[]>([]);
const toolSearch = ref("");
const toolSourceFilter = ref("all");

const toolSourceFilters = [
  { label: "全部", value: "all" },
  { label: "MCP", value: "mcp" },
  { label: "API", value: "api" },
];

const filteredAvailableTools = computed(() => {
  let list = allAvailableTools.value;
  if (toolSourceFilter.value !== "all") {
    list = list.filter((t) => t.source === toolSourceFilter.value);
  }
  const kw = toolSearch.value.trim().toLowerCase();
  if (kw) {
    list = list.filter(
      (t) => t.tool_name.toLowerCase().includes(kw) || t.description.toLowerCase().includes(kw)
    );
  }
  return list;
});

function isSelected(t: AvailTool) {
  return selectedTools.value.some((s) => s.tool_source === t.source && s.tool_name === t.tool_name);
}

function toggleTool(t: AvailTool) {
  const idx = selectedTools.value.findIndex(
    (s) => s.tool_source === t.source && s.tool_name === t.tool_name
  );
  if (idx >= 0) {
    selectedTools.value.splice(idx, 1);
  } else {
    selectedTools.value.push({ tool_id: t.tool_id, tool_source: t.source, tool_name: t.tool_name });
  }
}

function removeTool(t: SkillToolItem) {
  const idx = selectedTools.value.findIndex(
    (s) => s.tool_source === t.tool_source && s.tool_name === t.tool_name
  );
  if (idx >= 0) selectedTools.value.splice(idx, 1);
}

async function loadAvailableTools() {
  // 只列用户可绑定的 mcp/api 工具;内置工具由框架/computer_tools 运行时挂载,
  // 不走 binding 路径,不在此处列出(后端 page_tool 默认也排除 source='builtin')。
  const { data } = await toolApi.pageTool({ page_no: 1, page_size: 1000 });
  allAvailableTools.value = data.data
    .filter((t: ToolResp) => t.tool_status === "enabled")
    .map((t: ToolResp) => ({
      key: `${t.source}:${t.tool_name}`,
      tool_id: t.id,
      tool_name: t.tool_name,
      source: t.source,
      description: t.description,
    }));
}

async function loadEditData() {
  if (!isEdit.value) return;
  const { data } = await skillApi.getSkill(editId.value);
  const s = data.data;
  form.name = s.name;
  form.description = s.description || "";
  form.category_ids = (s.category_ids || []).slice();
  form.instruction = s.instruction;
  selectedTools.value = [...s.tools];
}

const SKILL_NAME_PATTERN = /^[a-z0-9-]{1,64}$/;

async function onSubmit() {
  const trimmedName = form.name.trim();
  if (!trimmedName) { message.error("请填写技能名称"); return; }
  if (!SKILL_NAME_PATTERN.test(trimmedName)) {
    message.error("名称只能包含小写字母、数字和连字符，长度 1-64");
    return;
  }
  if (!form.instruction.trim()) { message.error("请填写技能说明"); return; }

  submitting.value = true;
  try {
    if (isEdit.value) {
      await skillApi.updateSkill(editId.value, {
        name: form.name,
        description: form.description || undefined,
        category_ids: form.category_ids.slice(),
        instruction: form.instruction,
        tools: selectedTools.value,
      });
      message.success("已保存");
    } else {
      await skillApi.createSkill({
        name: form.name,
        description: form.description || undefined,
        category_ids: form.category_ids.slice(),
        instruction: form.instruction,
        tools: selectedTools.value,
      });
      message.success("技能已创建");
    }
    router.push("/skill");
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  const { data } = await categoryApi.listAppCategory();
  categoryOptions.value = data.data.map((c) => ({ value: c.id, label: c.name }));
  await loadAvailableTools();
  if (isEdit.value) await loadEditData();
});
</script>

<style scoped>
.skill-form-page {
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

.form-body { display: flex; gap: 20px; margin-top: 18px; }
.form-main { flex: 1; min-width: 0; }

.form-card { padding: 24px; border: 1px solid var(--color-border); border-radius: 18px; background: var(--surface-strong); }

.form-row { display: flex; gap: 16px; margin-bottom: 16px; }
.form-row--top { align-items: flex-start; }
.form-label { flex-shrink: 0; width: 80px; text-align: right; font-size: 13px; color: var(--color-text-secondary); padding-top: 6px; }
.required { color: var(--color-error); margin-right: 2px; }
.form-field { flex: 1; }
.form-hint { margin: 4px 0 0; font-size: 12px; color: var(--color-text-quaternary); }
.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 16px; }

/* Tool panel */
.tool-panel { width: 340px; flex-shrink: 0; }
.tool-panel-card { padding: 18px; border: 1px solid var(--color-border); border-radius: 18px; background: var(--surface-strong); position: sticky; top: 24px; }
.panel-title { margin: 0 0 12px; font-size: 14px; font-weight: 700; color: var(--color-text-secondary); }
.panel-count { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--color-accent); margin-left: 4px; }

.selected-tools { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.selected-tag { display: inline-flex; align-items: center; gap: 4px; height: 26px; padding: 0 8px; border-radius: 999px; background: var(--color-violet-bg); color: var(--color-accent); font-size: 11px; font-weight: 600; }
.selected-tag-close { font-size: 10px; cursor: pointer; opacity: 0.6; }
.selected-tag-close:hover { opacity: 1; }

.tool-search { margin-bottom: 10px; }

.tool-source-filter { display: flex; gap: 6px; margin-bottom: 10px; }
.tsf-btn { border: none; border-radius: 999px; background: var(--color-split); padding: 4px 10px; color: var(--color-text-tertiary); font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.15s ease; }
.tsf-btn:hover, .tsf-btn--active { background: var(--color-violet-bg); color: var(--color-accent); }

.avail-tool-list { max-height: 400px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.avail-tool-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; cursor: pointer; transition: background 0.15s ease; flex-wrap: wrap; }
.avail-tool-item:hover { background: var(--surface-muted-hover); }
.avail-tool-item--selected { background: var(--color-violet-bg); }
.avail-tool-check { pointer-events: none; }
.avail-tool-body { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.avail-tool-name { font-size: 12px; font-weight: 600; color: var(--color-text); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.avail-tool-desc { width: 100%; padding-left: 28px; font-size: 11px; color: var(--color-text-quaternary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.avail-tool-empty { text-align: center; padding: 24px 0; font-size: 12px; color: var(--color-text-quaternary); }

.source-tag { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 999px; font-size: 10px; font-weight: 700; }
.source-tag--builtin { background: var(--color-success-bg); color: var(--color-success-strong); }
.source-tag--mcp { background: var(--color-violet-bg); color: var(--color-accent); }
.source-tag--api { background: var(--color-cyan-bg); color: var(--color-cyan-text); }

@media (max-width: 960px) {
  .form-body { flex-direction: column; }
  .tool-panel { width: 100%; }
  .form-row { flex-direction: column; gap: 6px; }
  .form-label { width: auto; text-align: left; padding-top: 0; }
}
</style>
