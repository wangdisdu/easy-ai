<template>
  <section class="market-page">
    <!-- ─── Header ─── -->
    <div class="market-head">
      <a-button type="text" class="back-btn" @click="router.push('/skill')">
        <template #icon><ArrowLeftOutlined /></template>
        技能管理
      </a-button>
      <h2 class="market-title">技能市场</h2>
      <p class="market-sub">
        搜索并一键安装社区/官方技能 — 安装后会在「技能管理」生成一份可编辑副本,可绑定给智能体使用。
      </p>
    </div>

    <!-- ─── 未配置数据源的友好提示 ─── -->
    <a-alert
      v-if="searched && !configured"
      type="info"
      show-icon
      class="not-configured"
      :message="notConfiguredMsg || '技能市场数据源未配置'"
    >
      <template #description>
        管理员可在 backend 的 <code>.env</code> 设置 <code>SKILL_MARKET_URL</code> 指向一个技能注册中心
        (例如内部 S3 索引、GitHub 仓库)。当前可通过 <strong>技能管理 → 创建技能 → 上传技能包(.zip)</strong>
        手动导入技能。
      </template>
    </a-alert>

    <!-- ─── 工具栏 ─── -->
    <div class="market-toolbar">
      <a-input-search
        v-model:value="search"
        placeholder="搜索技能名称或描述..."
        allow-clear
        class="market-search"
        :disabled="!configured && searched"
        @search="onSearch"
      />
      <a-button :icon="h(ReloadOutlined)" @click="onSearch" />
    </div>

    <!-- ─── 标签 chips(预设 + 自定义,localStorage) ─── -->
    <div class="tag-bar">
      <span class="tag-label">标签</span>
      <span
        v-for="t in allTags"
        :key="t.query"
        class="tag-wrap"
        :class="{ 'tag-wrap--custom': isCustomTag(t.query) }"
      >
        <button
          :class="['tag-chip', { 'tag-chip--active': activeTag === t.query.toLowerCase() }]"
          @click="pickTag(t)"
        >
          {{ t.label }}
        </button>
        <button
          v-if="isCustomTag(t.query)"
          class="tag-remove"
          title="删除标签"
          @click.stop="removeCustomTag(t.query)"
        >
          ×
        </button>
      </span>
      <button class="tag-chip tag-chip--add" @click="addTagPrompt">+ 新增</button>
    </div>

    <!-- ─── 卡片网格 ─── -->
    <a-spin :spinning="loading">
      <div v-if="items.length" class="market-grid">
        <article
          v-for="it in items"
          :key="it.slug"
          class="market-card"
          @click="openDetail(it.slug)"
        >
          <div class="market-card__top">
            <span class="market-card__emoji">{{ it.emoji || "🌐" }}</span>
            <span class="market-card__source">市场</span>
          </div>
          <h4 class="market-card__name">{{ it.name }}</h4>
          <p class="market-card__desc">{{ it.description || "暂无描述" }}</p>
          <div class="market-card__footer">
            <span class="market-card__meta">
              <span v-if="it.version">v{{ it.version }}</span>
              <span v-if="it.author"> · {{ it.author }}</span>
            </span>
            <a-button size="small" @click.stop="openDetail(it.slug)">查看</a-button>
          </div>
        </article>
      </div>

      <div v-else-if="!loading && searched && configured" class="empty-state">
        <div class="empty-icon"><SearchOutlined /></div>
        <p class="empty-title">没有匹配的技能</p>
        <p class="empty-desc">换个关键词或分类试试</p>
      </div>

      <div v-else-if="!loading && searched && !configured" class="empty-state">
        <div class="empty-icon"><InboxOutlined /></div>
        <p class="empty-title">技能市场未配置</p>
        <p class="empty-desc">请联系管理员配置数据源后再使用</p>
      </div>

      <div v-else-if="!loading" class="empty-state">
        <div class="empty-icon"><SearchOutlined /></div>
        <p class="empty-title">搜索技能</p>
        <p class="empty-desc">输入关键词或点上方标签开始</p>
      </div>
    </a-spin>

    <!-- ─── 详情 Drawer ─── -->
    <a-drawer
      v-model:open="drawerOpen"
      :title="detail?.name || '技能详情'"
      width="560"
      :destroy-on-close="true"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detail">
          <div class="detail-head">
            <span class="detail-emoji">{{ detail.emoji || "🌐" }}</span>
            <div>
              <div class="detail-title">{{ detail.name }}</div>
              <div class="detail-meta">
                <span class="badge">市场</span>
                <span v-if="detail.version">v{{ detail.version }}</span>
                <span v-if="detail.author">by {{ detail.author }}</span>
                <span v-if="detail.stars != null">⭐ {{ detail.stars }}</span>
                <span v-if="detail.downloads != null">⬇ {{ detail.downloads.toLocaleString() }}</span>
              </div>
            </div>
          </div>

          <p class="detail-desc">{{ detail.description || "暂无简介" }}</p>

          <div v-if="detail.description" class="detail-actions">
            <a-button size="small" :loading="translating" @click="onTranslate">
              {{ translatedDesc ? "重新翻译" : "翻译成中文" }}
            </a-button>
          </div>
          <div v-if="translatedDesc" class="detail-translated">
            <div class="detail-translated__label">译文</div>
            <p class="detail-translated__text">{{ translatedDesc }}</p>
          </div>

          <div v-if="detail.platforms?.length" class="detail-section">
            <div class="detail-label">平台</div>
            <a-tag v-for="p in detail.platforms" :key="p" color="default">{{ p }}</a-tag>
          </div>

          <div v-if="detail.changelog" class="detail-section">
            <div class="detail-label">更新日志</div>
            <div class="md-preview" v-html="mdSafe(detail.changelog)" />
          </div>

          <div v-if="detail.instruction" class="detail-section">
            <div class="detail-label">操作手册</div>
            <div class="md-preview" v-html="mdSafe(detail.instruction)" />
          </div>

          <div v-if="detail.files?.length" class="detail-section">
            <div class="detail-label">捆绑文件 ({{ detail.files.length }})</div>
            <details v-for="f in detail.files" :key="f.rel_path" class="file-item">
              <summary class="file-summary">
                <span class="file-path">{{ f.rel_path }}</span>
                <span :class="['file-kind', 'file-kind--' + f.kind]">{{ fileKindLabel(f.kind) }}</span>
                <span class="file-size">{{ fmtSize(f.size) }}</span>
              </summary>
              <pre v-if="!f.binary && f.content" class="file-content">{{ f.content }}</pre>
              <div v-else class="file-binary">二进制文件,不展示内容</div>
            </details>
          </div>

          <div v-if="detail.content_loaded === false" class="warn-banner">
            完整内容(操作手册与脚本)加载失败 — 可能是网络或上游限流,稍后重试。
          </div>

          <a-alert
            type="info"
            show-icon
            class="install-hint"
            message="安装说明"
            description="点「安装」会把以上全部内容下载并按本地规范落库为一份可编辑技能,归属所选范围;安装后可在「技能管理」里继续编辑或绑定给智能体。"
          />
        </template>
      </a-spin>

      <template #footer>
        <div class="drawer-footer">
          <a
            v-if="detail?.homepage"
            :href="detail.homepage"
            target="_blank"
            rel="noopener noreferrer"
            class="drawer-link"
          >
            <LinkOutlined /> 查看源站
          </a>
          <div class="drawer-spacer" />
          <a-button @click="drawerOpen = false">关闭</a-button>
          <a-button type="primary" :disabled="!detail" @click="openInstall">安装</a-button>
        </div>
      </template>
    </a-drawer>

    <!-- ─── 安装 Modal ─── -->
    <a-modal
      v-model:open="installOpen"
      title="安装技能"
      :confirm-loading="installing"
      ok-text="确认安装"
      cancel-text="取消"
      @ok="onConfirmInstall"
    >
      <a-form layout="vertical">
        <a-form-item label="技能名称">
          <a-input v-model:value="installForm.skill_name" placeholder="留空使用包内 name" />
        </a-form-item>
        <a-form-item label="安装范围">
          <a-radio-group v-model:value="installForm.visibility">
            <a-radio value="group">我的用户组(同组可见)</a-radio>
            <a-radio value="system" :disabled="!isAdmin">全平台(所有人可用,仅管理员)</a-radio>
          </a-radio-group>
        </a-form-item>
        <p class="install-modal-hint">
          将从市场下载技能包并按本地规范落库为可编辑副本(含操作手册与脚本),归属所选范围。
        </p>
      </a-form>
    </a-modal>
  </section>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { message, Modal } from "ant-design-vue";
import {
  ArrowLeftOutlined,
  InboxOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import * as marketApi from "@/api/skillMarket";
import type { MarketSkill } from "@/api/types";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();
const isAdmin = computed(() => auth.isSuperAdmin);

// ─── 列表 ───
const loading = ref(false);
const items = ref<MarketSkill[]>([]);
const configured = ref(true);
const notConfiguredMsg = ref<string | null>(null);
const searched = ref(false);
const search = ref("");

async function load() {
  const q = search.value.trim();
  loading.value = true;
  searched.value = true;
  try {
    const { data } = await marketApi.searchMarket(q || undefined);
    items.value = data.data.items;
    configured.value = data.data.configured;
    notConfiguredMsg.value = data.data.message ?? null;
  } catch (e) {
    items.value = [];
    configured.value = false;
    notConfiguredMsg.value = (e as Error)?.message || "搜索失败";
  } finally {
    loading.value = false;
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null;
let suppressWatch = false;
watch(search, () => {
  if (suppressWatch) {
    suppressWatch = false;
    return;
  }
  if (searchTimer) clearTimeout(searchTimer);
  if (!search.value.trim()) {
    // 仍然 load 一次以拉到 configured 状态
    searchTimer = setTimeout(() => load(), 300);
    return;
  }
  searchTimer = setTimeout(() => load(), 400);
});

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  load();
}

// ─── 标签 chips ───
interface Tag {
  label: string;
  query: string;
}

const PRESET_TAGS: Tag[] = [
  { label: "文档写作", query: "document" },
  { label: "开发工具", query: "developer" },
  { label: "图像视觉", query: "image" },
  { label: "自动化", query: "automation" },
  { label: "网页浏览", query: "browser" },
  { label: "财经金融", query: "finance" },
];

const TAGS_LS_KEY = "skill-market-custom-tags";
function loadCustomTags(): Tag[] {
  try {
    const raw = localStorage.getItem(TAGS_LS_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.filter((t) => t?.label && t?.query) : [];
  } catch {
    return [];
  }
}
const customTags = ref<Tag[]>(loadCustomTags());
function saveCustomTags() {
  localStorage.setItem(TAGS_LS_KEY, JSON.stringify(customTags.value));
}

const allTags = computed(() => {
  const seen = new Set(PRESET_TAGS.map((t) => t.query.toLowerCase()));
  const extras = customTags.value.filter((t) => !seen.has(t.query.toLowerCase()));
  return [...PRESET_TAGS, ...extras];
});
function isCustomTag(query: string) {
  const q = query.toLowerCase();
  return (
    !PRESET_TAGS.some((t) => t.query.toLowerCase() === q) &&
    customTags.value.some((t) => t.query.toLowerCase() === q)
  );
}
const activeTag = computed(() => search.value.trim().toLowerCase());

function pickTag(tag: Tag) {
  if (searchTimer) clearTimeout(searchTimer);
  const same = activeTag.value === tag.query.toLowerCase();
  suppressWatch = true;
  search.value = same ? "" : tag.query;
  load();
}

function addTagPrompt() {
  Modal.confirm({
    title: "新增自定义标签",
    content: h("div", [
      h("p", "输入标签关键词(用于搜索):"),
      h("input", {
        id: "new-tag-input",
        type: "text",
        style:
          "width:100%;padding:6px 10px;border:1px solid var(--color-border);border-radius:6px;margin-top:4px;",
        placeholder: "如 testing / kubernetes",
      }),
    ]),
    onOk() {
      const el = document.getElementById("new-tag-input") as HTMLInputElement | null;
      const kw = el?.value?.trim() || "";
      if (!kw) {
        message.warning("关键词不能为空");
        return;
      }
      if (allTags.value.some((t) => t.query.toLowerCase() === kw.toLowerCase())) {
        message.info("该标签已存在");
        pickTag({ label: kw, query: kw });
        return;
      }
      customTags.value.push({ label: kw, query: kw });
      saveCustomTags();
      pickTag({ label: kw, query: kw });
    },
  });
}

function removeCustomTag(query: string) {
  customTags.value = customTags.value.filter((t) => t.query !== query);
  saveCustomTags();
  if (activeTag.value === query.toLowerCase()) {
    suppressWatch = true;
    search.value = "";
    load();
  }
}

// ─── 详情 Drawer ───
const drawerOpen = ref(false);
const detailLoading = ref(false);
const detail = ref<MarketSkill | null>(null);
const translating = ref(false);
const translatedDesc = ref("");

function fileKindLabel(kind: string) {
  return { reference: "参考", script: "脚本", template: "模板", asset: "资源" }[kind] || kind;
}
function fmtSize(n: number) {
  return n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`;
}
function mdSafe(text?: string | null) {
  return text ? DOMPurify.sanitize(marked.parse(text) as string) : "";
}

async function openDetail(slug: string) {
  drawerOpen.value = true;
  detailLoading.value = true;
  detail.value = null;
  translatedDesc.value = "";
  try {
    const { data } = await marketApi.inspectMarketSkill(slug);
    detail.value = data.data;
  } catch (e) {
    message.error((e as Error)?.message || "加载技能详情失败");
    drawerOpen.value = false;
  } finally {
    detailLoading.value = false;
  }
}

async function onTranslate() {
  const src = detail.value?.description;
  if (!src || translating.value) return;
  translating.value = true;
  try {
    const { data } = await marketApi.translateMarketText(src);
    translatedDesc.value = (data.data?.text || "").trim();
    if (!translatedDesc.value) message.warning("未获得翻译结果");
  } catch (e) {
    message.error((e as Error)?.message || "翻译失败");
  } finally {
    translating.value = false;
  }
}

// ─── 安装 ───
const installOpen = ref(false);
const installing = ref(false);
const installForm = reactive<{ skill_name: string; visibility: "group" | "system" }>({
  skill_name: "",
  visibility: "group",
});

function openInstall() {
  if (!detail.value) return;
  installForm.skill_name = detail.value.name;
  installForm.visibility = "group";
  installOpen.value = true;
}

async function onConfirmInstall() {
  if (!detail.value) return;
  installing.value = true;
  try {
    const { data } = await marketApi.installMarketSkill({
      slug: detail.value.slug,
      visibility: installForm.visibility,
      skill_name: installForm.skill_name.trim() || undefined,
    });
    installOpen.value = false;
    drawerOpen.value = false;
    message.success(`技能「${data.data.name}」已安装`);
    router.push("/skill");
  } catch (e) {
    message.error((e as Error)?.message || "安装失败");
  } finally {
    installing.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.market-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-violet-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.market-head { margin-bottom: 16px; }
.back-btn { padding: 0; color: var(--color-text-tertiary); }
.back-btn:hover { color: var(--color-accent); }
.market-title { margin: 6px 0 2px; font-size: 20px; font-weight: 700; color: var(--color-text); }
.market-sub { margin: 0; font-size: 13px; color: var(--color-text-tertiary); line-height: 1.6; }

.not-configured { margin-bottom: 16px; }
.not-configured code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; padding: 1px 5px; border-radius: 4px;
  background: var(--color-split); color: var(--color-text);
}

.market-toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.market-search { width: 320px; }

.tag-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  margin-bottom: 16px;
}
.tag-label { font-size: 12px; color: var(--color-text-tertiary); margin-right: 4px; }
.tag-wrap { position: relative; display: inline-flex; align-items: center; }
.tag-chip {
  padding: 5px 14px; font-size: 12px; font-weight: 600;
  color: var(--color-text-secondary); background: var(--color-split);
  border: 1px solid transparent; border-radius: 999px; cursor: pointer;
  transition: all 0.18s ease;
}
.tag-chip:hover { border-color: var(--color-violet-bg-strong); color: var(--color-accent); }
.tag-chip--active {
  border-color: var(--color-violet-bg-strong);
  background: var(--color-violet-bg);
  color: var(--color-accent);
}
.tag-chip--add { border: 1px dashed var(--color-border); background: transparent; color: var(--color-text-tertiary); }
.tag-chip--add:hover { border-color: var(--color-violet-bg-strong); color: var(--color-accent); }

.tag-remove {
  position: absolute; top: -4px; right: -4px;
  width: 16px; height: 16px; padding: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; line-height: 1; color: #fff;
  background: var(--color-error); border: 1px solid var(--color-bg);
  border-radius: 50%;
  cursor: pointer;
  opacity: 0; transform: scale(0.7); pointer-events: none;
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.tag-wrap--custom:hover .tag-remove { opacity: 1; transform: scale(1); pointer-events: auto; }

.market-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.market-card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 18px;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: var(--surface-strong);
  cursor: pointer;
  transition: all 0.18s ease;
}
.market-card:hover {
  border-color: var(--color-violet-bg-strong);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-sm);
}
.market-card__top { display: flex; align-items: center; justify-content: space-between; }
.market-card__emoji { font-size: 24px; line-height: 1; }
.market-card__source {
  display: inline-flex; align-items: center;
  height: 18px; padding: 0 8px;
  border-radius: 999px;
  font-size: 10px; font-weight: 700;
  background: var(--color-cyan-bg);
  color: var(--color-cyan-text);
}
.market-card__name { margin: 0; font-size: 15px; font-weight: 700; color: var(--color-text); }
.market-card__desc {
  margin: 0; min-height: 38px;
  font-size: 13px; color: var(--color-text-secondary); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.market-card__footer {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: auto; padding-top: 8px;
  border-top: 1px solid var(--color-border);
}
.market-card__meta { font-size: 11px; color: var(--color-text-quaternary); }

.empty-state {
  padding: 60px 0; text-align: center;
  color: var(--color-text-tertiary);
}
.empty-icon { font-size: 36px; opacity: 0.4; margin-bottom: 8px; }
.empty-title { font-size: 15px; color: var(--color-text-secondary); margin: 0 0 4px; }
.empty-desc { font-size: 12px; margin: 0; }

/* ── Drawer ── */
.detail-head { display: flex; gap: 14px; align-items: center; margin-bottom: 10px; }
.detail-emoji { font-size: 36px; line-height: 1; }
.detail-title { font-size: 18px; font-weight: 700; color: var(--color-text); }
.detail-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; font-size: 12px; color: var(--color-text-tertiary); }
.badge {
  display: inline-flex; align-items: center; height: 18px; padding: 0 8px;
  border-radius: 999px;
  font-size: 10px; font-weight: 700;
  background: var(--color-cyan-bg); color: var(--color-cyan-text);
}

.detail-desc { font-size: 13px; color: var(--color-text-secondary); line-height: 1.7; margin: 12px 0 6px; white-space: pre-line; }
.detail-actions { display: flex; gap: 8px; margin: 6px 0 10px; }
.detail-translated {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--color-split);
  border-left: 3px solid var(--color-accent);
  border-radius: 6px;
}
.detail-translated__label { font-size: 10px; font-weight: 700; color: var(--color-accent); margin-bottom: 4px; }
.detail-translated__text { font-size: 13px; color: var(--color-text-secondary); line-height: 1.6; margin: 0; white-space: pre-line; }

.detail-section { margin-top: 18px; }
.detail-label { font-size: 13px; font-weight: 700; color: var(--color-text); margin-bottom: 6px; }

.md-preview {
  font-size: 13px; color: var(--color-text-secondary); line-height: 1.65;
  background: var(--surface-strong);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 10px 14px;
  word-break: break-word;
}
.md-preview :deep(h1), .md-preview :deep(h2), .md-preview :deep(h3) {
  color: var(--color-text); font-weight: 700; margin: 10px 0 6px;
}
.md-preview :deep(h1) { font-size: 16px; }
.md-preview :deep(h2) { font-size: 14px; }
.md-preview :deep(h3) { font-size: 13px; }
.md-preview :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; padding: 1px 5px; border-radius: 4px;
  background: var(--color-split); color: var(--color-accent);
}
.md-preview :deep(pre) {
  background: var(--color-bg);
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
}
.md-preview :deep(pre code) { background: none; padding: 0; }

.file-item {
  margin-bottom: 6px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--surface-strong);
  overflow: hidden;
}
.file-summary {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; cursor: pointer; list-style: none;
  font-size: 12px; color: var(--color-text-secondary);
}
.file-summary::-webkit-details-marker { display: none; }
.file-summary::before { content: '▸'; color: var(--color-text-quaternary); }
.file-item[open] .file-summary::before { content: '▾'; }
.file-path {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text);
}
.file-kind {
  display: inline-flex; align-items: center;
  height: 18px; padding: 0 6px;
  border-radius: 999px; font-size: 10px; font-weight: 700;
  background: var(--color-split); color: var(--color-text-tertiary);
}
.file-kind--reference { background: var(--color-cyan-bg); color: var(--color-cyan-text); }
.file-kind--script { background: var(--color-warning-bg); color: var(--color-warning-strong); }
.file-kind--template { background: var(--color-violet-bg); color: var(--color-accent); }
.file-kind--asset { background: var(--color-success-bg); color: var(--color-success-strong); }
.file-size { font-size: 11px; color: var(--color-text-quaternary); }
.file-content {
  margin: 0; padding: 10px 12px;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; line-height: 1.55;
  color: var(--color-text-secondary);
  white-space: pre-wrap; word-break: break-word;
  max-height: 260px; overflow-y: auto;
}
.file-binary {
  padding: 10px 12px; border-top: 1px solid var(--color-border);
  font-size: 12px; color: var(--color-text-quaternary);
}

.warn-banner {
  margin-top: 12px; padding: 10px 14px;
  background: var(--color-warning-bg); color: var(--color-warning-strong);
  border-radius: 8px; font-size: 12px; line-height: 1.6;
}

.install-hint { margin-top: 16px; }

.drawer-footer { display: flex; align-items: center; gap: 8px; }
.drawer-link {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--color-accent);
}
.drawer-spacer { flex: 1; }

.install-modal-hint {
  font-size: 12px; color: var(--color-text-tertiary);
  line-height: 1.6; margin: 8px 0 0;
}
</style>
