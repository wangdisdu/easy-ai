<template>
  <section class="skill-detail-page">
    <div class="detail-topbar">
      <a-button type="text" @click="router.push('/skill')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <div class="topbar-actions">
        <a-button v-if="canEdit" @click="router.push(`/skill/${skillId}/edit`)">编辑技能</a-button>
        <a-button v-if="canPublish && skill?.skill_status === 'enabled'" danger @click="onDisable">禁用</a-button>
        <a-button v-else-if="canPublish" type="primary" ghost class="enable-btn" @click="onEnable">启用</a-button>
        <a-popconfirm v-if="canEdit" title="确定删除该技能？" @confirm="onDelete">
          <a-button danger>删除</a-button>
        </a-popconfirm>
      </div>
    </div>

    <a-spin :spinning="loading">
      <template v-if="skill">
        <!-- Header Card -->
        <div class="hero-card">
          <div class="hero-icon">
            <ThunderboltOutlined />
          </div>
          <div class="hero-body">
            <div class="hero-name-row">
              <h2 class="hero-name">{{ skill.name }}</h2>
              <template v-if="skill.categories && skill.categories.length">
                <span v-for="c in skill.categories" :key="c.id" class="cat-tag">
                  {{ c.name }}
                </span>
              </template>
              <span :class="['status-badge', 'status-badge--' + skill.skill_status]">
                <span :class="['status-dot', 'status-dot--' + skill.skill_status]" />
                {{ statusLabel[skill.skill_status] }}
              </span>
            </div>
            <p class="hero-desc">{{ skill.description || "暂无描述" }}</p>
            <div class="hero-meta">
              <span v-if="skill.current_version">版本 {{ skill.current_version }}</span>
              <span>{{ skill.tools.length }} 个工具</span>
              <span>创建于 {{ formatMs(skill.create_time) }}</span>
              <span>更新于 {{ formatMs(skill.update_time) }}</span>
            </div>
          </div>
        </div>

        <!-- Content -->
        <div class="content-area">
          <div class="overview-grid">
            <!-- Bound Tools -->
            <div class="panel-card">
              <h3 class="panel-title">绑定工具 <span class="panel-count">{{ skill.tools.length }}</span></h3>
              <div v-if="skill.tools.length" class="tool-list">
                <div v-for="t in skill.tools" :key="t.tool_name" class="tool-item">
                  <ToolOutlined class="tool-item-icon" />
                  <span class="tool-item-name">{{ t.tool_name }}</span>
                  <span :class="['source-tag', 'source-tag--' + t.tool_source]">{{ sourceLabel[t.tool_source] }}</span>
                </div>
              </div>
              <a-empty v-else description="未配置工具" :image="false" class="panel-empty" />
            </div>

            <!-- Versions -->
            <div class="panel-card">
              <h3 class="panel-title">版本历史 <span class="panel-count">{{ versions.length }}</span></h3>
              <div v-if="versions.length" class="version-list">
                <div v-for="(v, i) in versions.slice(0, 5)" :key="v.id" class="version-item">
                  <span :class="['version-dot', { 'version-dot--current': i === 0 }]" />
                  <span :class="['version-tag', { 'version-tag--current': i === 0 }]">{{ v.version }}</span>
                  <span class="version-note">{{ v.version_note || "-" }}</span>
                  <span class="version-time">{{ formatMs(v.published_time) }}</span>
                </div>
              </div>
              <a-empty v-else description="暂无版本" :image="false" class="panel-empty" />
            </div>
          </div>

          <!-- Instruction -->
          <div class="instruction-content" v-html="renderedInstruction" />
        </div>
      </template>
    </a-spin>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { marked } from "marked";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, ThunderboltOutlined, ToolOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as skillApi from "@/api/skill";
import type { SkillResp, SkillVersionResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.SKILL_EDIT));
const canPublish = computed(() => auth.hasPermission(PERM.SKILL_PUBLISH));

const skill = ref<SkillResp | null>(null);
const versions = ref<SkillVersionResp[]>([]);
const loading = ref(false);

const statusLabel: Record<string, string> = { enabled: "已启用", disabled: "已禁用", draft: "草稿" };
const sourceLabel: Record<string, string> = { builtin: "内置", mcp: "MCP", api: "API" };

const renderedInstruction = computed(() => {
  if (!skill.value?.instruction) return "";
  return marked(skill.value.instruction) as string;
});

const skillId = ref(route.params.id as string);

// watch for route param changes
watch(() => route.params.id, (newId) => {
  if (newId && typeof newId === "string") {
    skillId.value = newId;
    load();
  }
});

async function load() {
  loading.value = true;
  try {
    const [{ data: sd }, { data: vd }] = await Promise.all([
      skillApi.getSkill(skillId.value),
      skillApi.listSkillVersions(skillId.value),
    ]);
    skill.value = sd.data;
    versions.value = vd.data;
  } catch {
    message.error("加载技能失败");
  } finally {
    loading.value = false;
  }
}

async function onEnable() {
  await skillApi.enableSkill(skillId.value);
  message.success("已启用");
  load();
}

async function onDisable() {
  await skillApi.disableSkill(skillId.value);
  message.success("已禁用");
  load();
}

async function onDelete() {
  await skillApi.deleteSkill(skillId.value);
  message.success("已删除");
  router.push("/skill");
}

onMounted(load);
</script>

<style scoped>
.skill-detail-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-violet-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.detail-topbar { display: flex; align-items: center; justify-content: space-between; }
.topbar-actions { display: flex; gap: 8px; }
.enable-btn { color: var(--color-success-strong); border-color: var(--color-success-strong); }

.hero-card { display: flex; gap: 18px; margin-top: 18px; padding: 24px; border: 1px solid var(--color-border); border-radius: 18px; background: var(--surface-strong); }
.hero-icon { width: 56px; height: 56px; border-radius: 14px; background: linear-gradient(135deg, var(--color-info-bg-strong), var(--color-violet-bg)); display: flex; align-items: center; justify-content: center; font-size: 28px; color: var(--color-accent); flex-shrink: 0; }
.hero-body { flex: 1; min-width: 0; }
.hero-name-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-name { margin: 0; font-size: 20px; font-weight: 700; color: var(--color-text); }
.hero-desc { margin: 8px 0 0; font-size: 14px; color: var(--color-text-tertiary); line-height: 1.6; }
.hero-meta { display: flex; gap: 20px; margin-top: 12px; font-size: 12px; color: var(--color-text-quaternary); }

.cat-tag { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 600; background: var(--color-violet-bg); color: var(--color-accent); }

.status-badge { display: inline-flex; align-items: center; gap: 5px; height: 22px; padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.status-badge--enabled { background: var(--color-success-bg); color: var(--color-success-strong); }
.status-badge--disabled { background: var(--color-neutral-bg); color: var(--color-text-tertiary); }
.status-badge--draft { background: var(--color-warning-bg); color: var(--color-warning-strong); }
.status-dot { width: 6px; height: 6px; border-radius: 999px; }
.status-dot--enabled { background: var(--color-success); }
.status-dot--disabled { background: var(--color-border-secondary); }
.status-dot--draft { background: var(--color-warning); }

.content-area { margin-top: 18px; }

.overview-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel-card { padding: 20px; border: 1px solid var(--color-border); border-radius: 18px; background: var(--surface-strong); }
.panel-title { margin: 0 0 14px; font-size: 14px; font-weight: 700; color: var(--color-text-secondary); }
.panel-count { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--color-accent); margin-left: 4px; }
.panel-empty { padding: 24px 0; }

.tool-list { display: flex; flex-direction: column; gap: 8px; }
.tool-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--color-border); }
.tool-item-icon { font-size: 14px; color: var(--color-text-quaternary); }
.tool-item-name { flex: 1; font-size: 13px; color: var(--color-text); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.source-tag { display: inline-flex; align-items: center; height: 20px; padding: 0 6px; border-radius: 999px; font-size: 10px; font-weight: 700; }
.source-tag--builtin { background: var(--color-success-bg); color: var(--color-success-strong); }
.source-tag--mcp { background: var(--color-violet-bg); color: var(--color-accent); }
.source-tag--api { background: var(--color-cyan-bg); color: var(--color-cyan-text); }

.version-list { display: flex; flex-direction: column; gap: 10px; }
.version-item { display: flex; align-items: center; gap: 10px; }
.version-dot { width: 8px; height: 8px; border-radius: 999px; background: var(--color-border-secondary); flex-shrink: 0; }
.version-dot--current { background: var(--color-accent); }
.version-tag { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--color-text-tertiary); }
.version-tag--current { color: var(--color-accent); font-weight: 600; }
.version-note { flex: 1; font-size: 12px; color: var(--color-text-quaternary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.version-time { font-size: 11px; color: var(--color-border-secondary); flex-shrink: 0; }

.instruction-content { margin-top: 16px; font-size: 14px; color: var(--color-text-secondary); line-height: 1.8; }
.instruction-content :deep(h1) { font-size: 20px; font-weight: 700; color: var(--color-text); margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border); }
.instruction-content :deep(h2) { font-size: 16px; font-weight: 700; color: var(--color-text); margin: 20px 0 10px; }
.instruction-content :deep(h3) { font-size: 14px; font-weight: 700; color: var(--color-text-secondary); margin: 16px 0 8px; }
.instruction-content :deep(p) { margin: 0 0 10px; }
.instruction-content :deep(ul), .instruction-content :deep(ol) { margin: 0 0 10px; padding-left: 20px; }
.instruction-content :deep(li) { margin: 4px 0; }
.instruction-content :deep(li::marker) { color: var(--color-text-quaternary); }
.instruction-content :deep(code) { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--color-violet-bg); color: var(--color-accent); padding: 2px 6px; border-radius: 4px; }
.instruction-content :deep(pre) { margin: 10px 0; padding: 14px; border-radius: 8px; background: var(--surface-code); overflow-x: auto; }
.instruction-content :deep(pre code) { background: none; color: var(--color-code-text); padding: 0; font-size: 12px; line-height: 1.6; }
.instruction-content :deep(strong) { font-weight: 700; color: var(--color-text); }
.instruction-content :deep(hr) { border: none; border-top: 1px solid var(--color-border); margin: 16px 0; }
.instruction-content :deep(blockquote) { margin: 10px 0; padding: 10px 16px; border-left: 3px solid var(--color-accent); background: var(--color-violet-bg); color: var(--color-text-secondary); border-radius: 0 8px 8px 0; }
.instruction-content :deep(table) { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
.instruction-content :deep(th) { text-align: left; padding: 8px 12px; background: var(--color-split); border: 1px solid var(--color-border); font-weight: 600; color: var(--color-text-secondary); }
.instruction-content :deep(td) { padding: 8px 12px; border: 1px solid var(--color-border); }
.instruction-content :deep(a) { color: var(--color-accent); text-decoration: none; }
.instruction-content :deep(a:hover) { text-decoration: underline; }
.instruction-content :deep(> :last-child) { margin-bottom: 0; }

@media (max-width: 960px) {
  .overview-grid { grid-template-columns: 1fr; }
  .detail-topbar { flex-direction: column; gap: 10px; align-items: flex-start; }
}
</style>
