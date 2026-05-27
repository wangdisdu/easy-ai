<template>
  <section class="skill-form-page" v-loading="loading">
    <!-- ─── Header ─── -->
    <div class="form-header">
      <a-button type="text" @click="router.push('/skill')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <h2 class="form-title">
        {{ isEdit ? (parsedName || "编辑技能") : "新建技能" }}
      </h2>
      <div class="header-spacer" />
      <a-button @click="router.push('/skill')">取消</a-button>
      <a-button
        v-if="isEdit || createMode === 'manual'"
        type="primary"
        :loading="submitting"
        @click="onSubmit"
      >
        {{ isEdit ? "保存" : "创建" }}
      </a-button>
    </div>

    <!-- ─── 新建模式切换:手动 / 上传 .zip ─── -->
    <div v-if="!isEdit" class="create-mode">
      <button
        :class="['mode-tab', { 'mode-tab--active': createMode === 'manual' }]"
        @click="createMode = 'manual'"
      >
        手动创建
      </button>
      <button
        :class="['mode-tab', { 'mode-tab--active': createMode === 'upload' }]"
        @click="createMode = 'upload'"
      >
        上传技能包 (.zip)
      </button>
    </div>

    <!-- ─── 上传 .zip ─── -->
    <div v-if="!isEdit && createMode === 'upload'" class="upload-card">
      <a-upload-dragger
        v-model:file-list="uploadFileList"
        accept=".zip"
        :max-count="1"
        :before-upload="onPickZip"
        @remove="onRemoveZip"
      >
        <p class="upload-icon"><InboxOutlined /></p>
        <p class="upload-text">点击或拖拽 .zip 技能包到此处</p>
        <p class="upload-hint">
          压缩包根目录需含 <code>SKILL.md</code>（YAML frontmatter 提供 name/description）；
          其他文件按
          <code>references/</code> <code>scripts/</code> <code>templates/</code>
          <code>assets/</code> 四类目录归档。上限 10MB / 100 文件。
        </p>
      </a-upload-dragger>
      <div class="upload-actions">
        <a-button
          type="primary"
          :loading="uploading"
          :disabled="!uploadZip"
          @click="onUploadCreate"
        >
          上传并创建
        </a-button>
      </div>
    </div>

    <!-- ─── 双 Tab 主体 ─── -->
    <div v-show="isEdit || createMode === 'manual'" class="form-body">
      <a-tabs v-model:active-key="activeTab" class="detail-tabs">
        <!-- ════ Tab 1: 相关文档 ════ -->
        <a-tab-pane key="docs">
          <template #tab>
            <span>相关文档</span>
            <span class="tab-badge">{{ skillFiles.length + 1 }}</span>
          </template>

          <div class="docs-layout">
            <!-- 左:文档树 -->
            <div class="docs-tree">
              <div
                :class="['doc-node', 'doc-node--main', { 'doc-node--active': isMainActive }]"
                @click="selectMain"
              >
                <span class="doc-node__badge doc-node__badge--main">主</span>
                <span class="doc-node__path">SKILL.md</span>
              </div>

              <div v-for="g in fileGroups" :key="g.kind" class="doc-group">
                <div class="doc-group__head">
                  <span class="doc-group__name">{{ g.label }}</span>
                  <span v-if="g.files.length" class="doc-group__count">{{ g.files.length }}</span>
                  <button class="doc-group__add" @click="addFile(g.kind)">+ 新增</button>
                </div>
                <div v-if="!g.files.length" class="doc-group__empty">暂无</div>
                <div
                  v-for="f in g.files"
                  :key="f.uid"
                  :class="[
                    'doc-node',
                    { 'doc-node--active': !isMainActive && activeFile === f },
                  ]"
                  @click="selectFile(f)"
                >
                  <span class="doc-node__badge" :data-kind="g.kind">{{ g.short }}</span>
                  <span class="doc-node__path" :title="leafName(f.rel_path)">
                    {{ leafName(f.rel_path) || "(未命名)" }}
                  </span>
                  <button class="doc-node__del" title="删除" @click.stop="removeFile(f)">×</button>
                </div>
              </div>
            </div>

            <!-- 右:编辑器 -->
            <div class="docs-editor">
              <template v-if="isMainActive">
                <p class="docs-hint">
                  <strong>SKILL.md</strong> 是技能的唯一真相源:顶部 <code>---</code> 包裹的
                  YAML frontmatter 定义 <code>name</code> 与 <code>description</code>（模型据 description 判断<strong>何时</strong>调用该技能）；之后的正文是被调用时注入对话上下文的指令。
                </p>
                <a-textarea
                  v-model:value="mainDoc"
                  :rows="32"
                  class="mono-textarea"
                  :placeholder="DEFAULT_SKILL_MD"
                />
              </template>
              <template v-else-if="activeFile">
                <div class="docs-editor__meta">
                  <a-input
                    v-model:value="activeFile.rel_path"
                    size="small"
                    placeholder="相对路径,如 scripts/gen.py（首段目录决定类别）"
                  />
                </div>
                <a-textarea
                  v-model:value="activeFile.content"
                  :rows="29"
                  class="mono-textarea"
                  placeholder="文件内容(脚本代码 / 参考文档 / 模板 / 资源)"
                />
              </template>
            </div>
          </div>

          <p class="docs-foot-hint">
            <strong>references/</strong> 渐进披露,运行时按需 read,不进沙箱;
            <strong>scripts/</strong> / <strong>templates/</strong> / <strong>assets/</strong>
            被调用时物化进沙箱
            <code>/workspace/.skills/&lt;技能名&gt;/</code>，script 由模型 exec 运行。
            文件首段目录决定类别。
          </p>
        </a-tab-pane>

        <!-- ════ Tab 2: 关联工具 ════ -->
        <a-tab-pane key="tools">
          <template #tab>
            <span>关联工具</span>
            <span v-if="selectedTools.length" class="tab-badge">{{ selectedTools.length }}</span>
          </template>

          <!-- 工具来源 子 Tab -->
          <div class="impl-tabs">
            <button
              v-for="t in toolSourceFilters"
              :key="t.value"
              :class="['impl-tab', { 'impl-tab--active': toolSourceFilter === t.value }]"
              @click="toolSourceFilter = t.value"
            >
              <span>{{ t.label }}</span>
              <span class="impl-tab__meta">
                <template v-if="implTabSelectedCounts[t.value]">
                  <span class="impl-tab__sel">{{ implTabSelectedCounts[t.value] }}</span>
                  <span class="impl-tab__sep">/</span>
                </template>
                {{ implTabToolCounts[t.value] }}
              </span>
            </button>
          </div>

          <div class="tool-search">
            <a-input-search
              v-model:value="toolSearch"
              placeholder="搜索工具名称或描述..."
              allow-clear
              size="small"
            />
          </div>

          <div class="tool-list">
            <div
              v-for="t in filteredAvailableTools"
              :key="t.key"
              :class="['tool-row', { 'tool-row--on': isSelected(t) }]"
              @click="toggleTool(t)"
            >
              <a-checkbox :checked="isSelected(t)" class="tool-row__check" />
              <div class="tool-row__body">
                <div class="tool-row__top">
                  <span class="tool-row__name">{{ t.tool_name }}</span>
                  <span :class="['source-tag', 'source-tag--' + t.source]">
                    {{ sourceLabel[t.source] }}
                  </span>
                </div>
                <span class="tool-row__desc">{{ t.description }}</span>
              </div>
            </div>
            <div v-if="!filteredAvailableTools.length" class="tool-empty">
              当前分类暂无工具
            </div>
          </div>
        </a-tab-pane>

        <!-- ════ Tab 3: 基础信息(分类 / emoji) ════ -->
        <a-tab-pane key="meta">
          <template #tab>
            <span>基础信息</span>
          </template>
          <div class="meta-form">
            <div class="form-row">
              <label class="form-label">Emoji 图标</label>
              <div class="form-field">
                <a-input
                  v-model:value="form.emoji"
                  :maxlength="8"
                  placeholder="🛠"
                  class="emoji-input"
                />
                <p class="form-hint">可选,作为技能卡片图标</p>
              </div>
            </div>
            <div class="form-row">
              <label class="form-label">技能分类</label>
              <div class="form-field">
                <a-select
                  v-model:value="form.category_ids"
                  style="width: 100%"
                  placeholder="选择应用分类(可多选)"
                  mode="multiple"
                  :options="categoryOptions"
                  option-filter-prop="label"
                  allow-clear
                />
              </div>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, InboxOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import type { UploadFile } from "ant-design-vue";
import * as appApi from "@/api/app";
import * as categoryApi from "@/api/appCategory";
import * as skillApi from "@/api/skill";
import * as toolApi from "@/api/tool";
import type { AppResp, SkillFileItem, SkillToolItem, ToolResp } from "@/api/types";

const router = useRouter();
const route = useRoute();
const isEdit = computed(() => !!route.params.id);
const editId = computed(() => route.params.id as string);
const loading = ref(false);
const submitting = ref(false);
const activeTab = ref<string>("docs");
const categoryOptions = ref<Array<{ value: string; label: string }>>([]);

const sourceLabel: Record<string, string> = {
  builtin: "内置",
  mcp: "MCP",
  api: "API",
  app: "应用",
};

// ─── 新建模式 ───
const createMode = ref<"manual" | "upload">("manual");
const uploadZip = ref<File | null>(null);
const uploadFileList = ref<UploadFile[]>([]);
const uploading = ref(false);

function onPickZip(file: File) {
  uploadZip.value = file;
  // 阻止 antd 自动上传(我们点确认按钮再发)
  return false;
}
function onRemoveZip() {
  uploadZip.value = null;
}

async function onUploadCreate() {
  if (!uploadZip.value) {
    message.warning("请先选择一个 .zip 技能包");
    return;
  }
  uploading.value = true;
  try {
    const { data } = await skillApi.uploadSkillZip(uploadZip.value);
    message.success(`技能「${data.data.name}」已创建`);
    router.push(`/skill/${data.data.id}/edit`);
  } finally {
    uploading.value = false;
  }
}

// ─── 表单基础字段 ───
const form = reactive({
  emoji: "",
  category_ids: [] as string[],
});

// ─── SKILL.md 主文档 ───
const DEFAULT_SKILL_MD = `---
name: new-skill
description: 一句话说明该技能的用途与适用场景(模型据此判断何时调用)
---

# 技能指令

在此编写技能被调用时注入对话上下文的操作指令:
- 明确该技能完成什么任务、按什么流程执行
- 需要使用的工具名称及用途
- 若附带脚本,写清如何调用(如 \`python3 .../scripts/xxx.py\`)
`;
const mainDoc = ref(isEdit.value ? "" : DEFAULT_SKILL_MD);

interface ParsedMeta {
  name: string;
  description: string;
  body: string;
}

const FRONTMATTER_RE = /^﻿?---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/;

function parseFrontmatter(text: string): ParsedMeta {
  const m = FRONTMATTER_RE.exec(text || "");
  if (!m) return { name: "", description: "", body: (text || "").trim() };
  const fm = m[1];
  const body = m[2] || "";
  const meta: Record<string, string> = {};
  for (const raw of fm.split(/\r?\n/)) {
    if (!raw.trim() || /^\s/.test(raw) || raw.trim().startsWith("#")) continue;
    const i = raw.indexOf(":");
    if (i < 0) continue;
    const k = raw.slice(0, i).trim();
    let v = raw.slice(i + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    meta[k] = v;
  }
  return {
    name: meta.name || "",
    description: meta.description || "",
    body: body.trim(),
  };
}

const parsedName = computed(() => parseFrontmatter(mainDoc.value).name);

// ─── 工具绑定 ───
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
const toolSourceFilter = ref("mcp");

const toolSourceFilters = [
  { label: "MCP", value: "mcp" },
  { label: "API", value: "api" },
  { label: "应用", value: "app" },
];

// 可作为工具被技能调用的应用类型:LLM / RAG(无副作用、可幂等调用)
const APP_AS_TOOL_TYPES = new Set(["llm", "rag"]);

const filteredAvailableTools = computed(() => {
  let list = allAvailableTools.value.filter((t) => t.source === toolSourceFilter.value);
  const kw = toolSearch.value.trim().toLowerCase();
  if (kw) {
    list = list.filter(
      (t) => t.tool_name.toLowerCase().includes(kw) || t.description.toLowerCase().includes(kw),
    );
  }
  return list;
});

const implTabToolCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const def of toolSourceFilters) {
    counts[def.value] = allAvailableTools.value.filter((t) => t.source === def.value).length;
  }
  return counts;
});

const implTabSelectedCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const def of toolSourceFilters) {
    counts[def.value] = selectedTools.value.filter((s) => s.tool_source === def.value).length;
  }
  return counts;
});

function isSelected(t: AvailTool) {
  return selectedTools.value.some((s) => s.tool_source === t.source && s.tool_name === t.tool_name);
}

function toggleTool(t: AvailTool) {
  const idx = selectedTools.value.findIndex(
    (s) => s.tool_source === t.source && s.tool_name === t.tool_name,
  );
  if (idx >= 0) {
    selectedTools.value.splice(idx, 1);
  } else {
    selectedTools.value.push({
      tool_id: t.tool_id,
      tool_source: t.source,
      tool_name: t.tool_name,
    });
  }
}

async function loadAvailableTools() {
  const [toolsRes, appsRes] = await Promise.all([
    toolApi.pageTool({ page_no: 1, page_size: 1000 }),
    appApi.pageApp({ page_no: 1, page_size: 1000, app_status: "published" }),
  ]);
  const tools: AvailTool[] = toolsRes.data.data
    .filter((t: ToolResp) => t.tool_status === "enabled")
    .map((t: ToolResp) => ({
      key: `${t.source}:${t.tool_name}`,
      tool_id: t.id,
      tool_name: t.tool_name,
      source: t.source,
      description: t.description,
    }));
  const apps: AvailTool[] = appsRes.data.data
    .filter((a: AppResp) => APP_AS_TOOL_TYPES.has(a.app_type))
    .map((a: AppResp) => ({
      key: `app:${a.name}`,
      tool_id: a.id,
      tool_name: a.name,
      source: "app",
      description: a.description || `${a.app_type.toUpperCase()} 应用`,
    }));
  allAvailableTools.value = [...tools, ...apps];
}

// ─── SKILL 文件树 ───
interface EditFile {
  uid: number;
  rel_path: string;
  content: string;
}

interface KindDef {
  kind: string;
  label: string;
  short: string;
  dir: string;
  ext: string;
}

const KIND_DEFS: KindDef[] = [
  { kind: "reference", label: "参考文档", short: "参", dir: "references", ext: ".md" },
  { kind: "script", label: "脚本", short: "本", dir: "scripts", ext: ".py" },
  { kind: "template", label: "模板", short: "模", dir: "templates", ext: ".md" },
  { kind: "asset", label: "资源", short: "资", dir: "assets", ext: ".txt" },
];

let uidSeq = 0;
const skillFiles = ref<EditFile[]>([]);
const isMainActive = ref(true);
const activeFile = ref<EditFile | null>(null);

function kindOf(rel: string): string {
  const top = (rel || "").replace(/\\/g, "/").split("/")[0];
  return KIND_DEFS.find((d) => d.dir === top)?.kind ?? "script";
}
function leafName(rel: string): string {
  const parts = (rel || "").replace(/\\/g, "/").split("/");
  return parts.length > 1 ? parts.slice(1).join("/") : rel;
}

const fileGroups = computed(() =>
  KIND_DEFS.map((d) => ({
    ...d,
    files: skillFiles.value.filter((f) => kindOf(f.rel_path) === d.kind),
  })),
);

function selectMain() {
  isMainActive.value = true;
  activeFile.value = null;
}
function selectFile(f: EditFile) {
  isMainActive.value = false;
  activeFile.value = f;
}
function addFile(kind: string) {
  const d = KIND_DEFS.find((x) => x.kind === kind)!;
  const n = skillFiles.value.filter((f) => kindOf(f.rel_path) === kind).length + 1;
  const f: EditFile = {
    uid: ++uidSeq,
    rel_path: `${d.dir}/new_${n}${d.ext}`,
    content: "",
  };
  skillFiles.value.push(f);
  selectFile(f);
}
function removeFile(f: EditFile) {
  const idx = skillFiles.value.indexOf(f);
  if (idx >= 0) skillFiles.value.splice(idx, 1);
  if (activeFile.value === f) selectMain();
}

// ─── 加载 / 提交 ───
async function loadEditData() {
  if (!isEdit.value) return;
  const { data } = await skillApi.getSkill(editId.value);
  const s = data.data;
  form.emoji = s.emoji || "";
  form.category_ids = (s.category_ids || []).slice();
  selectedTools.value = [...s.tools];

  // 历史技能 instruction 可能不带 frontmatter:用元数据合成。
  if (FRONTMATTER_RE.test(s.instruction)) {
    mainDoc.value = s.instruction;
  } else {
    mainDoc.value =
      `---\n` +
      `name: ${s.name}\n` +
      (s.description ? `description: ${s.description}\n` : "") +
      `---\n\n` +
      (s.instruction || "");
  }

  skillFiles.value = (s.files || []).map((f) => ({
    uid: ++uidSeq,
    rel_path: f.rel_path,
    content: f.content,
  }));
}

const SKILL_NAME_PATTERN = /^[a-z0-9-]{1,64}$/;

async function onSubmit() {
  const parsed = parseFrontmatter(mainDoc.value);
  if (!parsed.name) {
    message.error("请在 SKILL.md frontmatter 中填写 name");
    activeTab.value = "docs";
    selectMain();
    return;
  }
  if (!SKILL_NAME_PATTERN.test(parsed.name)) {
    message.error("name 仅允许小写字母、数字、连字符,长度 1-64");
    activeTab.value = "docs";
    selectMain();
    return;
  }

  // 路径去重 + 非空校验
  const paths = skillFiles.value.map((f) => f.rel_path.trim());
  if (paths.some((p) => !p)) {
    message.error("文件路径不能为空");
    return;
  }
  if (new Set(paths).size !== paths.length) {
    message.error("文件路径重复");
    return;
  }

  const files: SkillFileItem[] = skillFiles.value.map((f) => ({
    rel_path: f.rel_path.trim(),
    content: f.content,
  }));

  submitting.value = true;
  try {
    if (isEdit.value) {
      await skillApi.updateSkill(editId.value, {
        name: parsed.name,
        description: parsed.description || undefined,
        emoji: form.emoji.trim() || "",
        category_ids: form.category_ids.slice(),
        instruction: mainDoc.value,
        tools: selectedTools.value,
        files,
      });
      message.success("已保存");
    } else {
      await skillApi.createSkill({
        name: parsed.name,
        description: parsed.description || undefined,
        emoji: form.emoji.trim() || undefined,
        category_ids: form.category_ids.slice(),
        instruction: mainDoc.value,
        tools: selectedTools.value,
        files,
      });
      message.success("技能已创建");
    }
    router.push("/skill");
  } finally {
    submitting.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    const { data } = await categoryApi.listAppCategory();
    categoryOptions.value = data.data.map((c) => ({ value: c.id, label: c.name }));
    await loadAvailableTools();
    if (isEdit.value) await loadEditData();
  } finally {
    loading.value = false;
  }
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

/* ─── Header ─── */
.form-header { display: flex; align-items: center; gap: 8px; }
.form-title { margin: 0; font-size: 20px; font-weight: 700; color: var(--color-text); }
.header-spacer { flex: 1; }

/* ─── 新建模式切换 ─── */
.create-mode { display: flex; gap: 0; margin: 18px 0 4px; }
.mode-tab {
  padding: 7px 18px; font-size: 13px; font-weight: 600;
  color: var(--color-text-tertiary); background: transparent;
  border: 1px solid var(--color-border); cursor: pointer;
  transition: all 0.15s ease;
}
.mode-tab:first-child { border-radius: 8px 0 0 8px; }
.mode-tab:last-child { border-radius: 0 8px 8px 0; border-left: none; }
.mode-tab:hover { color: var(--color-text); background: var(--surface-muted-hover); }
.mode-tab--active {
  color: var(--color-accent);
  background: var(--color-violet-bg);
  border-color: var(--color-violet-bg-strong);
}

/* ─── 上传 ─── */
.upload-card {
  margin-top: 12px;
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--surface-strong);
}
.upload-icon { font-size: 40px; color: var(--color-accent); }
.upload-text { font-size: 14px; color: var(--color-text); margin: 8px 0 4px; }
.upload-hint { font-size: 12px; color: var(--color-text-tertiary); line-height: 1.6; }
.upload-hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; padding: 1px 5px; border-radius: 4px;
  background: var(--color-split); color: var(--color-text);
}
.upload-actions { margin-top: 14px; display: flex; justify-content: flex-end; }

/* ─── Tabs 主体 ─── */
.form-body {
  margin-top: 18px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--surface-strong);
  overflow: hidden;
}
.detail-tabs { padding: 0 18px; }
.tab-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px; margin-left: 6px;
  font-size: 11px; font-weight: 700;
  color: var(--color-bg); background: var(--color-accent);
  border-radius: 9px; line-height: 1;
}

/* ─── Tab 1: 相关文档 ─── */
.docs-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 16px;
  padding: 4px 0 12px;
  align-items: start;
}
.docs-tree {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-bg);
  overflow: hidden;
}
.doc-group { border-top: 1px solid var(--color-border); }
.doc-group__head {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 10px;
  background: var(--color-split);
}
.doc-group__name { font-size: 12px; font-weight: 700; color: var(--color-text-secondary); letter-spacing: 0.3px; }
.doc-group__count {
  font-size: 11px; color: var(--color-text-quaternary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.doc-group__add {
  margin-left: auto;
  border: none; background: transparent;
  font-size: 12px; color: var(--color-accent);
  cursor: pointer; padding: 0 4px;
}
.doc-group__add:hover { text-decoration: underline; }
.doc-group__empty {
  padding: 6px 12px 8px; font-size: 12px;
  color: var(--color-text-quaternary);
}

.doc-node {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; cursor: pointer;
  border-top: 1px solid var(--color-border);
  transition: background 0.15s ease;
}
.doc-node:hover { background: var(--surface-muted-hover); }
.doc-node--active { background: var(--color-violet-bg); }
.doc-node--main { border-top: none; background: var(--color-split); }
.doc-node--main.doc-node--active { background: var(--color-violet-bg); }
.doc-node__badge {
  flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 4px;
  font-size: 10px; font-weight: 700;
  color: var(--color-text-secondary);
  background: var(--color-split);
}
.doc-node__badge--main { color: var(--color-bg); background: var(--color-accent); }
.doc-node__badge[data-kind="script"] { color: var(--color-warning-strong); background: var(--color-warning-bg); }
.doc-node__badge[data-kind="reference"] { color: var(--color-cyan-text); background: var(--color-cyan-bg); }
.doc-node__badge[data-kind="template"] { color: var(--color-accent); background: var(--color-violet-bg); }
.doc-node__badge[data-kind="asset"] { color: var(--color-success-strong); background: var(--color-success-bg); }
.doc-node__path {
  flex: 1; min-width: 0;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.doc-node--main .doc-node__path { font-weight: 700; }
.doc-node__del {
  opacity: 0; padding: 0 4px;
  border: none; background: transparent;
  color: var(--color-error); font-size: 14px; cursor: pointer;
  transition: opacity 0.15s ease;
}
.doc-node:hover .doc-node__del { opacity: 1; }

.docs-editor { min-width: 0; }
.docs-hint {
  font-size: 12px; color: var(--color-text-tertiary);
  line-height: 1.6; margin: 0 0 10px;
}
.docs-hint code, .docs-foot-hint code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; padding: 1px 5px; border-radius: 4px;
  background: var(--color-split); color: var(--color-text);
}
.docs-editor__meta { margin-bottom: 8px; }
.mono-textarea :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-size: 12.5px;
  line-height: 1.65;
  background: var(--color-bg) !important;
}
.docs-foot-hint {
  font-size: 12px; color: var(--color-text-tertiary);
  line-height: 1.7; margin: 0;
  padding: 12px 0 0;
  border-top: 1px solid var(--color-border);
}

/* ─── Tab 2: 关联工具 ─── */
.impl-tabs {
  display: flex; gap: 0;
  padding: 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 12px;
}
.impl-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px;
  border: none; background: none;
  font-size: 13px; font-weight: 600;
  color: var(--color-text-tertiary);
  cursor: pointer;
  position: relative;
  transition: color 0.15s ease;
}
.impl-tab:hover { color: var(--color-text-secondary); }
.impl-tab--active { color: var(--color-accent); }
.impl-tab--active::after {
  content: '';
  position: absolute;
  bottom: -1px; left: 12px; right: 12px;
  height: 2px;
  background: var(--color-accent);
  border-radius: 1px 1px 0 0;
}
.impl-tab__meta {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text-quaternary);
}
.impl-tab__sel { color: var(--color-accent); font-weight: 700; }
.impl-tab__sep { opacity: 0.5; }

.tool-search { margin-bottom: 10px; max-width: 360px; }
.tool-list { display: flex; flex-direction: column; gap: 4px; max-height: 420px; overflow-y: auto; padding-bottom: 12px; }
.tool-row {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 12px; border-radius: 10px;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.tool-row:hover { background: var(--surface-muted-hover); }
.tool-row--on { background: var(--color-violet-bg); border-color: var(--color-violet-bg-strong); }
.tool-row__check { pointer-events: none; margin-top: 2px; }
.tool-row__body { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.tool-row__top { display: flex; align-items: center; gap: 6px; }
.tool-row__name {
  font-size: 13px; font-weight: 600; color: var(--color-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.tool-row__desc {
  font-size: 12px; color: var(--color-text-tertiary);
  line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.tool-empty { text-align: center; padding: 40px 0; font-size: 13px; color: var(--color-text-quaternary); }

.source-tag {
  display: inline-flex; align-items: center;
  height: 18px; padding: 0 6px;
  border-radius: 999px;
  font-size: 10px; font-weight: 700;
}
.source-tag--builtin { background: var(--color-success-bg); color: var(--color-success-strong); }
.source-tag--mcp { background: var(--color-violet-bg); color: var(--color-accent); }
.source-tag--api { background: var(--color-cyan-bg); color: var(--color-cyan-text); }
.source-tag--app { background: var(--color-warning-bg); color: var(--color-warning-strong); }

/* ─── Tab 3: 基础信息 ─── */
.meta-form { padding: 8px 0 20px; max-width: 640px; }
.form-row { display: flex; gap: 16px; margin-bottom: 16px; align-items: flex-start; }
.form-label {
  flex-shrink: 0; width: 96px; text-align: right;
  font-size: 13px; color: var(--color-text-secondary);
  padding-top: 6px;
}
.form-field { flex: 1; }
.form-hint { margin: 4px 0 0; font-size: 12px; color: var(--color-text-quaternary); }
.emoji-input { width: 72px; }
.emoji-input :deep(input) { text-align: center; font-size: 18px; line-height: 1; }

@media (max-width: 960px) {
  .docs-layout { grid-template-columns: 1fr; }
  .form-row { flex-direction: column; gap: 6px; }
  .form-label { width: auto; text-align: left; padding-top: 0; }
}
</style>
