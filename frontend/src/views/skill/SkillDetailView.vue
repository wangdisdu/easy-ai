<template>
  <section class="skill-detail-page">
    <div class="detail-topbar">
      <a-button type="text" @click="router.push('/skill')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <div class="topbar-actions">
        <a-button @click="router.push(`/skill/${skillId}/edit`)">编辑技能</a-button>
        <a-button v-if="skill?.skill_status === 'enabled'" danger @click="onDisable">禁用</a-button>
        <a-button v-else type="primary" ghost @click="onEnable" style="color: #059669; border-color: #059669">启用</a-button>
        <a-popconfirm title="确定删除该技能？" @confirm="onDelete">
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
              <span v-if="skill.category" class="cat-tag">{{ skill.category }}</span>
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

const router = useRouter();
const route = useRoute();

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
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(139, 92, 246, 0.1), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.86) 100%);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.78);
  padding: 24px;
}

.detail-topbar { display: flex; align-items: center; justify-content: space-between; }
.topbar-actions { display: flex; gap: 8px; }

.hero-card { display: flex; gap: 18px; margin-top: 18px; padding: 24px; border: 1px solid rgba(226, 232, 240, 0.88); border-radius: 18px; background: rgba(255, 255, 255, 0.78); }
.hero-icon { width: 56px; height: 56px; border-radius: 14px; background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.1)); display: flex; align-items: center; justify-content: center; font-size: 28px; color: #7c3aed; flex-shrink: 0; }
.hero-body { flex: 1; min-width: 0; }
.hero-name-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hero-name { margin: 0; font-size: 20px; font-weight: 700; color: #0f172a; }
.hero-desc { margin: 8px 0 0; font-size: 14px; color: #64748b; line-height: 1.6; }
.hero-meta { display: flex; gap: 20px; margin-top: 12px; font-size: 12px; color: #94a3b8; }

.cat-tag { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 600; background: rgba(139, 92, 246, 0.08); color: #7c3aed; }

.status-badge { display: inline-flex; align-items: center; gap: 5px; height: 22px; padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.status-badge--enabled { background: rgba(16, 185, 129, 0.1); color: #059669; }
.status-badge--disabled { background: rgba(148, 163, 184, 0.1); color: #64748b; }
.status-badge--draft { background: rgba(245, 158, 11, 0.1); color: #d97706; }
.status-dot { width: 6px; height: 6px; border-radius: 999px; }
.status-dot--enabled { background: #10b981; }
.status-dot--disabled { background: #cbd5e1; }
.status-dot--draft { background: #f59e0b; }

.content-area { margin-top: 18px; }

.overview-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel-card { padding: 20px; border: 1px solid rgba(226, 232, 240, 0.88); border-radius: 18px; background: rgba(255, 255, 255, 0.78); }
.panel-title { margin: 0 0 14px; font-size: 14px; font-weight: 700; color: #334155; }
.panel-count { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #7c3aed; margin-left: 4px; }
.panel-empty { padding: 24px 0; }

.tool-list { display: flex; flex-direction: column; gap: 8px; }
.tool-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(226, 232, 240, 0.6); }
.tool-item-icon { font-size: 14px; color: #94a3b8; }
.tool-item-name { flex: 1; font-size: 13px; color: #0f172a; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.source-tag { display: inline-flex; align-items: center; height: 20px; padding: 0 6px; border-radius: 999px; font-size: 10px; font-weight: 700; }
.source-tag--builtin { background: rgba(16, 185, 129, 0.1); color: #059669; }
.source-tag--mcp { background: rgba(139, 92, 246, 0.1); color: #7c3aed; }
.source-tag--api { background: rgba(6, 182, 212, 0.1); color: #0891b2; }

.version-list { display: flex; flex-direction: column; gap: 10px; }
.version-item { display: flex; align-items: center; gap: 10px; }
.version-dot { width: 8px; height: 8px; border-radius: 999px; background: #cbd5e1; flex-shrink: 0; }
.version-dot--current { background: #7c3aed; }
.version-tag { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: #64748b; }
.version-tag--current { color: #7c3aed; font-weight: 600; }
.version-note { flex: 1; font-size: 12px; color: #94a3b8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.version-time { font-size: 11px; color: #cbd5e1; flex-shrink: 0; }

.instruction-content { margin-top: 16px; font-size: 14px; color: #334155; line-height: 1.8; }
.instruction-content :deep(h1) { font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(226, 232, 240, 0.6); }
.instruction-content :deep(h2) { font-size: 16px; font-weight: 700; color: #1e293b; margin: 20px 0 10px; }
.instruction-content :deep(h3) { font-size: 14px; font-weight: 700; color: #334155; margin: 16px 0 8px; }
.instruction-content :deep(p) { margin: 0 0 10px; }
.instruction-content :deep(ul), .instruction-content :deep(ol) { margin: 0 0 10px; padding-left: 20px; }
.instruction-content :deep(li) { margin: 4px 0; }
.instruction-content :deep(li::marker) { color: #94a3b8; }
.instruction-content :deep(code) { font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: rgba(139, 92, 246, 0.06); color: #7c3aed; padding: 2px 6px; border-radius: 4px; }
.instruction-content :deep(pre) { margin: 10px 0; padding: 14px; border-radius: 8px; background: #1e293b; overflow-x: auto; }
.instruction-content :deep(pre code) { background: none; color: #e2e8f0; padding: 0; font-size: 12px; line-height: 1.6; }
.instruction-content :deep(strong) { font-weight: 700; color: #0f172a; }
.instruction-content :deep(hr) { border: none; border-top: 1px solid rgba(226, 232, 240, 0.6); margin: 16px 0; }
.instruction-content :deep(blockquote) { margin: 10px 0; padding: 10px 16px; border-left: 3px solid #7c3aed; background: rgba(139, 92, 246, 0.04); color: #475569; border-radius: 0 8px 8px 0; }
.instruction-content :deep(table) { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
.instruction-content :deep(th) { text-align: left; padding: 8px 12px; background: rgba(241, 245, 249, 0.8); border: 1px solid rgba(226, 232, 240, 0.6); font-weight: 600; color: #334155; }
.instruction-content :deep(td) { padding: 8px 12px; border: 1px solid rgba(226, 232, 240, 0.6); }
.instruction-content :deep(a) { color: #7c3aed; text-decoration: none; }
.instruction-content :deep(a:hover) { text-decoration: underline; }
.instruction-content :deep(> :last-child) { margin-bottom: 0; }

@media (max-width: 960px) {
  .overview-grid { grid-template-columns: 1fr; }
  .detail-topbar { flex-direction: column; gap: 10px; align-items: flex-start; }
}
</style>
