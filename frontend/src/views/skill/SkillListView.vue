<template>
  <section class="skill-page">
    <div class="skill-page-head">
      <div>
        <h2 class="skill-page-title">技能管理</h2>
        <p class="skill-page-sub">管理智能体可调用的技能模块，配置技能参数与工具绑定</p>
      </div>
      <div class="skill-head-actions">
        <a-button class="skill-head-btn" @click="router.push('/skill-market')">
          <template #icon><AppstoreOutlined /></template>
          从市场安装
        </a-button>
        <a-button v-if="canEdit" type="primary" class="skill-head-btn" @click="router.push('/skill/create')">
          <template #icon><PlusOutlined /></template>
          创建技能
        </a-button>
      </div>
    </div>

    <!-- Search + Status + Category Filter -->
    <div class="filter-bar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        placeholder="搜索技能名称或描述..."
        allow-clear
        @search="onSearch"
      />
      <div class="status-chips">
        <button
          v-for="s in statusFilters"
          :key="s.value"
          :class="['status-chip', { 'status-chip--active': filterStatus === s.value }]"
          @click="selectStatus(s.value)"
        >
          {{ s.label }}
        </button>
      </div>
      <div class="filter-chips">
        <button
          :class="['filter-chip', { 'filter-chip--active': filterCategoryId === '' }]"
          @click="selectCategory('')"
        >
          全部分类
        </button>
        <button
          v-for="cat in categories"
          :key="cat.id"
          :class="['filter-chip', { 'filter-chip--active': filterCategoryId === cat.id }]"
          @click="selectCategory(cat.id)"
        >
          {{ cat.name }}
        </button>
      </div>
    </div>

    <!-- Grid -->
    <a-spin :spinning="loading">
      <div v-if="list.length" class="skill-grid">
        <article
          v-for="skill in list"
          :key="skill.id"
          class="skill-card"
          @click="router.push(`/skill/${skill.id}`)"
        >
          <div class="skill-card-top">
            <div class="skill-card-icon" :class="{ 'skill-card-icon--emoji': !!skill.emoji }">
              <span v-if="skill.emoji" class="skill-card-emoji">{{ skill.emoji }}</span>
              <ThunderboltOutlined v-else />
            </div>
            <div class="skill-card-info">
              <h4 class="skill-card-name">{{ skill.name }}</h4>
              <div v-if="skill.categories && skill.categories.length" class="cat-tags">
                <span v-for="c in skill.categories" :key="c.id" class="cat-tag">
                  {{ c.name }}
                </span>
              </div>
            </div>
            <span class="skill-card-status">
              <span :class="['status-dot', 'status-dot--' + skill.skill_status]" />
              <span class="status-text">{{ statusLabel[skill.skill_status] || skill.skill_status }}</span>
            </span>
          </div>

          <p class="skill-card-desc">{{ skill.description || "暂无描述" }}</p>

          <div class="skill-card-footer">
            <span class="footer-item">
              <ToolOutlined class="footer-icon" />
              {{ skill.tools.length }} 个工具
            </span>
            <span class="footer-time">更新于 {{ formatMs(skill.update_time) }}</span>
          </div>
        </article>
      </div>

      <a-empty v-else-if="!loading" description="暂无匹配的技能" class="empty-block" />
    </a-spin>

    <div v-if="total > pageSize" class="skill-pagination">
      <a-pagination
        v-model:current="pageNo"
        :page-size="pageSize"
        :total="total"
        show-size-changer
        :show-total="(t: number) => `共 ${t} 条`"
        @change="loadList"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  AppstoreOutlined,
  PlusOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from "@ant-design/icons-vue";
import * as categoryApi from "@/api/appCategory";
import * as skillApi from "@/api/skill";
import type { AppCategoryResp, SkillResp } from "@/api/types";
import { formatMs } from "@/utils/time";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const router = useRouter();
const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.SKILL_EDIT));

const keyword = ref("");
const filterCategoryId = ref("");
const filterStatus = ref("");
const list = ref<SkillResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const categories = ref<AppCategoryResp[]>([]);

const statusLabel: Record<string, string> = {
  enabled: "已启用",
  disabled: "已禁用",
  draft: "草稿",
};

const statusFilters: Array<{ label: string; value: string }> = [
  { label: "全部", value: "" },
  { label: "已启用", value: "enabled" },
  { label: "已禁用", value: "disabled" },
  { label: "草稿", value: "draft" },
];

function selectCategory(id: string) {
  filterCategoryId.value = id;
  pageNo.value = 1;
  loadList();
}

function selectStatus(value: string) {
  filterStatus.value = value;
  pageNo.value = 1;
  loadList();
}

function onSearch() {
  pageNo.value = 1;
  loadList();
}

async function loadList() {
  loading.value = true;
  try {
    const { data } = await skillApi.pageSkill({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      category_id: filterCategoryId.value || undefined,
      skill_status: filterStatus.value || undefined,
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function loadCategories() {
  const { data } = await categoryApi.listAppCategory();
  categories.value = data.data;
}

onMounted(() => {
  Promise.all([loadCategories(), loadList()]);
});
</script>

<style scoped>
.skill-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-violet-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.skill-page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.skill-page-title { margin: 0; font-size: 20px; font-weight: 700; color: var(--color-text); }
.skill-page-sub { margin: 6px 0 0; font-size: 13px; color: var(--color-text-tertiary); }
.skill-head-btn { height: 40px; padding-inline: 16px; border-radius: 12px; }
.skill-head-actions { display: flex; gap: 8px; flex-shrink: 0; }

.filter-bar { display: flex; align-items: center; gap: 16px; margin-top: 18px; padding: 4px 0; flex-wrap: wrap; }
.search-input { width: 280px; flex-shrink: 0; }
.status-chips { display: flex; gap: 0; flex-shrink: 0; }
.status-chip { border: 1px solid var(--color-border); background: transparent; padding: 7px 14px; color: var(--color-text-tertiary); font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s ease; }
.status-chip:first-child { border-radius: 8px 0 0 8px; }
.status-chip:last-child { border-radius: 0 8px 8px 0; }
.status-chip:not(:first-child) { border-left: none; }
.status-chip:hover { color: var(--color-text); background: var(--surface-muted-hover); }
.status-chip--active { color: var(--color-accent); background: var(--color-violet-bg); border-color: var(--color-violet-bg-strong); }
.status-chip--active + .status-chip { border-left: none; }
.filter-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.filter-chip { border: 1px solid transparent; border-radius: 999px; background: var(--color-split); padding: 8px 14px; color: var(--color-text-tertiary); font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.18s ease; }
.filter-chip:hover, .filter-chip--active { border-color: var(--color-violet-bg-strong); background: var(--color-violet-bg); color: var(--color-accent); }

.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-top: 18px; }

.skill-card { padding: 20px; border: 1px solid var(--color-border); border-radius: 18px; background: var(--surface-strong); cursor: pointer; transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease; }
.skill-card:hover { transform: translateY(-2px); border-color: var(--color-violet-bg-strong); box-shadow: var(--shadow-card-sm); }

.skill-card-top { display: flex; align-items: flex-start; gap: 12px; }
.skill-card-icon { width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, var(--color-info-bg-strong), var(--color-violet-bg)); display: flex; align-items: center; justify-content: center; font-size: 18px; color: var(--color-accent); flex-shrink: 0; }
.skill-card-icon--emoji { background: var(--color-split); }
.skill-card-emoji { font-size: 20px; line-height: 1; }
.skill-card-info { flex: 1; min-width: 0; }
.skill-card-name { margin: 0; font-size: 15px; font-weight: 700; color: var(--color-text); }

.cat-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.cat-tag { display: inline-flex; align-items: center; height: 20px; padding: 0 8px; border-radius: 999px; font-size: 10px; font-weight: 600; background: var(--color-violet-bg); color: var(--color-accent); }

.skill-card-status { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 999px; }
.status-dot--enabled { background: var(--color-success); }
.status-dot--disabled { background: var(--color-border-secondary); }
.status-dot--draft { background: var(--color-warning); }
.status-text { font-size: 12px; color: var(--color-text-tertiary); }

.skill-card-desc { margin: 12px 0 0; min-height: 42px; color: var(--color-text-tertiary); font-size: 13px; line-height: 1.7; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.skill-card-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--color-border); font-size: 12px; color: var(--color-text-quaternary); }
.footer-item { display: flex; align-items: center; gap: 4px; }
.footer-icon { font-size: 13px; }
.footer-time { color: var(--color-text-quaternary); }

.empty-block { padding: 56px 0; }
.skill-pagination { display: flex; justify-content: flex-end; margin-top: 20px; }

@media (max-width: 960px) {
  .skill-page-head { flex-direction: column; }
  .filter-bar { flex-direction: column; align-items: flex-start; }
}
</style>
