<template>
  <section class="skill-page">
    <div class="skill-page-head">
      <div>
        <h2 class="skill-page-title">技能管理</h2>
        <p class="skill-page-sub">管理智能体可调用的技能模块，配置技能参数与工具绑定</p>
      </div>
      <a-button type="primary" class="skill-head-btn" @click="router.push('/skill/create')">
        <template #icon><PlusOutlined /></template>
        创建技能
      </a-button>
    </div>

    <!-- Search + Category Filter -->
    <div class="filter-bar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        placeholder="搜索技能名称或描述..."
        allow-clear
        @search="onSearch"
      />
      <div class="filter-chips">
        <button
          :class="['filter-chip', { 'filter-chip--active': filterCategory === '' }]"
          @click="selectCategory('')"
        >
          全部
        </button>
        <button
          v-for="cat in categories"
          :key="cat"
          :class="['filter-chip', { 'filter-chip--active': filterCategory === cat }]"
          @click="selectCategory(cat)"
        >
          {{ cat }}
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
            <div class="skill-card-icon">
              <ThunderboltOutlined />
            </div>
            <div class="skill-card-info">
              <h4 class="skill-card-name">{{ skill.name }}</h4>
              <span v-if="skill.category" class="cat-tag">{{ skill.category }}</span>
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
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { PlusOutlined, ThunderboltOutlined, ToolOutlined } from "@ant-design/icons-vue";
import * as skillApi from "@/api/skill";
import type { SkillResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const router = useRouter();

const keyword = ref("");
const filterCategory = ref("");
const list = ref<SkillResp[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(20);
const categories = ref<string[]>([]);

const statusLabel: Record<string, string> = {
  enabled: "已启用",
  disabled: "已禁用",
  draft: "草稿",
};

function selectCategory(cat: string) {
  filterCategory.value = cat;
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
      category: filterCategory.value || undefined,
    });
    list.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function loadCategories() {
  const { data } = await skillApi.listCategories();
  categories.value = data.data;
}

onMounted(() => {
  Promise.all([loadCategories(), loadList()]);
});
</script>

<style scoped>
.skill-page {
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(139, 92, 246, 0.1), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.86) 100%);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.78);
  padding: 24px;
}

.skill-page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.skill-page-title { margin: 0; font-size: 20px; font-weight: 700; color: #0f172a; }
.skill-page-sub { margin: 6px 0 0; font-size: 13px; color: #64748b; }
.skill-head-btn { height: 40px; padding-inline: 16px; border-radius: 12px; }

.filter-bar { display: flex; align-items: center; gap: 16px; margin-top: 18px; padding: 4px 0; }
.search-input { width: 280px; flex-shrink: 0; }
.filter-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.filter-chip { border: 1px solid transparent; border-radius: 999px; background: rgba(241, 245, 249, 0.72); padding: 8px 14px; color: #64748b; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.18s ease; }
.filter-chip:hover, .filter-chip--active { border-color: rgba(139, 92, 246, 0.18); background: rgba(237, 233, 254, 0.8); color: #7c3aed; }

.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-top: 18px; }

.skill-card { padding: 20px; border: 1px solid rgba(226, 232, 240, 0.88); border-radius: 18px; background: rgba(255, 255, 255, 0.78); cursor: pointer; transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease; }
.skill-card:hover { transform: translateY(-2px); border-color: rgba(139, 92, 246, 0.24); box-shadow: 0 18px 36px rgba(124, 58, 237, 0.08); }

.skill-card-top { display: flex; align-items: flex-start; gap: 12px; }
.skill-card-icon { width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, rgba(59, 130, 246, 0.15), rgba(139, 92, 246, 0.1)); display: flex; align-items: center; justify-content: center; font-size: 18px; color: #7c3aed; flex-shrink: 0; }
.skill-card-info { flex: 1; min-width: 0; }
.skill-card-name { margin: 0; font-size: 15px; font-weight: 700; color: #0f172a; }

.cat-tag { display: inline-flex; align-items: center; height: 20px; padding: 0 8px; border-radius: 999px; font-size: 10px; font-weight: 600; margin-top: 4px; background: rgba(139, 92, 246, 0.08); color: #7c3aed; }

.skill-card-status { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 999px; }
.status-dot--enabled { background: #10b981; }
.status-dot--disabled { background: #cbd5e1; }
.status-dot--draft { background: #f59e0b; }
.status-text { font-size: 12px; color: #64748b; }

.skill-card-desc { margin: 12px 0 0; min-height: 42px; color: #64748b; font-size: 13px; line-height: 1.7; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.skill-card-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(226, 232, 240, 0.76); font-size: 12px; color: #94a3b8; }
.footer-item { display: flex; align-items: center; gap: 4px; }
.footer-icon { font-size: 13px; }
.footer-time { color: #94a3b8; }

.empty-block { padding: 56px 0; }
.skill-pagination { display: flex; justify-content: flex-end; margin-top: 20px; }

@media (max-width: 960px) {
  .skill-page-head { flex-direction: column; }
  .filter-bar { flex-direction: column; align-items: flex-start; }
}
</style>
