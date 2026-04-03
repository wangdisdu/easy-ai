<template>
  <section class="tool-page">
    <div class="tool-page-head">
      <div>
        <h2 class="tool-page-title">工具管理</h2>
        <p class="tool-page-sub">管理智能体可调用的系统内置工具、MCP 工具和 API 集成工具</p>
      </div>
      <a-dropdown>
        <a-button type="primary" class="tool-head-btn">
          <template #icon><PlusOutlined /></template>
          添加工具
          <DownOutlined style="font-size: 10px; margin-left: 4px" />
        </a-button>
        <template #overlay>
          <a-menu>
            <a-menu-item key="mcp" @click="router.push('/tool/mcp-import')">
              <ApiOutlined style="margin-right: 6px" />从 MCP Server 导入
            </a-menu-item>
            <a-menu-item key="api" @click="router.push('/tool/api-tool')">
              <LinkOutlined style="margin-right: 6px" />集成外部 API 工具
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>

    <!-- Search + Source Filter -->
    <div class="filter-bar">
      <a-input-search
        v-model:value="keyword"
        class="search-input"
        placeholder="搜索工具名称或描述..."
        allow-clear
        @search="onSearch"
      />
      <div class="filter-chips">
        <button
          v-for="item in sourceFilters"
          :key="item.value"
          type="button"
          class="filter-chip"
          :class="{ 'filter-chip--active': filterSource === item.value }"
          @click="selectSourceFilter(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <!-- Builtin Tools -->
      <template v-if="showBuiltin && builtinFiltered.length">
        <div class="section-label">
          <span class="section-dot section-dot--builtin" />
          系统内置
        </div>
        <div class="tool-list">
          <div
            v-for="t in builtinFiltered"
            :key="t.tool_name"
            class="tool-card"
            @click="toggleExpand('builtin-' + t.tool_name)"
          >
            <div class="tool-card-row">
              <div class="tool-icon tool-icon--builtin">
                <SettingOutlined />
              </div>
              <div class="tool-card-body">
                <div class="tool-card-name-row">
                  <span class="tool-card-name">{{ t.tool_name }}</span>
                  <span class="source-tag source-tag--builtin">系统内置</span>
                </div>
                <p class="tool-card-desc">{{ t.description }}</p>
              </div>
              <DownOutlined
                class="expand-arrow"
                :class="{ 'expand-arrow--open': expandedId === 'builtin-' + t.tool_name }"
              />
            </div>
            <div v-if="expandedId === 'builtin-' + t.tool_name" class="tool-detail" @click.stop>
              <div class="detail-section">
                <span class="detail-label">参数定义（JSON Schema）</span>
                <pre class="detail-json">{{ JSON.stringify(t.parameters, null, 2) }}</pre>
              </div>
              <div class="detail-footer">
                <span class="detail-hint">系统内置工具，不可编辑</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- MCP Tools (grouped by server) -->
      <template v-if="showMcp && mcpTools.length">
        <div v-for="group in mcpServerGroups" :key="group.serverId" class="mcp-server-group">
          <div class="server-group-header">
            <span class="section-dot section-dot--mcp" />
            <span class="server-group-label">MCP</span>
            <span class="server-group-sep" />
            <span class="server-group-name">{{ group.server?.server_name || '未知 Server' }}</span>
            <span v-if="group.server" class="server-group-meta">{{ transportLabel[group.server.transport] || group.server.transport }}</span>
            <span v-if="group.server" class="server-group-meta detail-mono">{{ group.server.endpoint_url }}</span>
            <span v-if="group.server?.remark" class="server-group-meta">{{ group.server.remark }}</span>
            <span class="server-group-count">{{ group.tools.length }} 个工具</span>
          </div>
          <!-- Tools under this server -->
          <div class="tool-list">
            <div
              v-for="t in group.tools"
              :key="t.id"
              class="tool-card"
              @click="toggleExpand(t.id)"
            >
              <div class="tool-card-row">
                <div class="tool-icon tool-icon--mcp">
                  <ApiOutlined />
                </div>
                <div class="tool-card-body">
                  <div class="tool-card-name-row">
                    <span class="tool-card-name">{{ t.tool_name }}</span>
                    <span v-if="t.risk_level" :class="['risk-tag', 'risk-tag--' + t.risk_level]">
                      {{ t.risk_level }}
                    </span>
                    <span :class="['status-dot', 'status-dot--' + t.tool_status]" />
                  </div>
                  <p class="tool-card-desc">{{ t.description }}</p>
                </div>
                <DownOutlined
                  class="expand-arrow"
                  :class="{ 'expand-arrow--open': expandedId === t.id }"
                />
              </div>
              <div v-if="expandedId === t.id" class="tool-detail" @click.stop>
                <div class="detail-grid">
                  <div><span class="detail-label">工具分组</span><span class="detail-value">{{ t.tool_group || "-" }}</span></div>
                  <div><span class="detail-label">风险等级</span><span :class="['risk-tag', 'risk-tag--' + (t.risk_level || 'low')]">{{ t.risk_level || "low" }}</span></div>
                </div>
                <div class="detail-section">
                  <span class="detail-label">参数定义（JSON Schema）</span>
                  <pre class="detail-json">{{ JSON.stringify(t.parameters, null, 2) }}</pre>
                </div>
                <div class="detail-footer">
                  <a-button size="small" type="link" @click="router.push(`/tool/api-tool/${t.id}`)">编辑</a-button>
                  <a-button v-if="t.tool_status === 'enabled'" size="small" type="link" class="btn-warn" @click="onDisable(t)">停用</a-button>
                  <a-button v-else size="small" type="link" class="btn-green" @click="onEnable(t)">启用</a-button>
                  <span class="detail-spacer" />
                  <span class="detail-time">更新于 {{ formatMs(t.update_time) }}</span>
                  <a-popconfirm title="确定删除该工具？" @confirm="onDelete(t)">
                    <a-button size="small" type="link" danger>删除</a-button>
                  </a-popconfirm>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- API Tools -->
      <template v-if="showApi && apiTools.length">
        <div class="section-label">
          <span class="section-dot section-dot--api" />
          API 集成
        </div>
        <div class="tool-list">
          <div
            v-for="t in apiTools"
            :key="t.id"
            class="tool-card"
            @click="toggleExpand(t.id)"
          >
            <div class="tool-card-row">
              <div class="tool-icon tool-icon--api">
                <LinkOutlined />
              </div>
              <div class="tool-card-body">
                <div class="tool-card-name-row">
                  <span class="tool-card-name">{{ t.tool_name }}</span>
                  <span class="source-tag source-tag--api">API 集成</span>
                  <span v-if="t.risk_level" :class="['risk-tag', 'risk-tag--' + t.risk_level]">
                    {{ t.risk_level }}
                  </span>
                  <span :class="['status-dot', 'status-dot--' + t.tool_status]" />
                </div>
                <p class="tool-card-desc">{{ t.description }}</p>
              </div>
              <DownOutlined
                class="expand-arrow"
                :class="{ 'expand-arrow--open': expandedId === t.id }"
              />
            </div>
            <div v-if="expandedId === t.id" class="tool-detail" @click.stop>
              <!-- Tool Definition (LLM visible) -->
              <div class="detail-section-header">
                工具定义
                <span class="badge badge--visible">大模型可见</span>
              </div>
              <div class="detail-grid">
                <div><span class="detail-label">工具名称</span><span class="detail-value detail-mono">{{ t.tool_name }}</span></div>
                <div><span class="detail-label">工具分组</span><span class="detail-value">{{ t.tool_group || "-" }}</span></div>
                <div><span class="detail-label">风险等级</span><span :class="['risk-tag', 'risk-tag--' + (t.risk_level || 'low')]">{{ t.risk_level || "low" }}</span></div>
              </div>
              <div class="detail-section">
                <span class="detail-label">功能描述</span>
                <span class="detail-value">{{ t.description }}</span>
              </div>
              <div class="detail-section">
                <span class="detail-label">参数定义（JSON Schema）</span>
                <pre class="detail-json">{{ JSON.stringify(t.parameters, null, 2) }}</pre>
              </div>

              <!-- HTTP Config (LLM invisible) -->
              <template v-if="t.api_config">
                <div class="detail-section-header">
                  HTTP 请求配置
                  <span class="badge badge--hidden">大模型不可见</span>
                </div>
                <div class="detail-grid">
                  <div><span class="detail-label">Method</span><span class="detail-value detail-mono">{{ (t.api_config as any).method || "POST" }}</span></div>
                  <div class="detail-span-2"><span class="detail-label">URL</span><span class="detail-value detail-mono">{{ (t.api_config as any).url || (t.api_config as any).endpoint || "-" }}</span></div>
                </div>
                <div v-if="(t.api_config as any).headers?.length" class="detail-section">
                  <span class="detail-label">Headers</span>
                  <div class="detail-kv-list">
                    <div v-for="(h, i) in (t.api_config as any).headers" :key="i" class="detail-kv-row">
                      <span class="detail-kv-key">{{ h.key }}</span>
                      <span class="detail-kv-value">{{ h.value }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="(t.api_config as any).body" class="detail-section">
                  <span class="detail-label">Body</span>
                  <pre class="detail-json">{{ (t.api_config as any).body }}</pre>
                </div>
              </template>

              <div class="detail-footer">
                <a-button size="small" type="link" @click="router.push(`/tool/api-tool/${t.id}`)">编辑</a-button>
                <a-button v-if="t.tool_status === 'enabled'" size="small" type="link" class="btn-warn" @click="onDisable(t)">停用</a-button>
                <a-button v-else size="small" type="link" class="btn-green" @click="onEnable(t)">启用</a-button>
                <span class="detail-spacer" />
                <span class="detail-time">更新于 {{ formatMs(t.update_time) }}</span>
                <a-popconfirm title="确定删除该工具？" @confirm="onDelete(t)">
                  <a-button size="small" type="link" danger>删除</a-button>
                </a-popconfirm>
              </div>
            </div>
          </div>
        </div>
      </template>

      <a-empty
        v-if="!loading && !builtinFiltered.length && !mcpTools.length && !apiTools.length"
        description="暂无匹配的工具"
        class="empty-block"
      />
    </a-spin>

    <div v-if="total > pageSize" class="tool-pagination">
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
  PlusOutlined,
  SettingOutlined,
  ApiOutlined,
  LinkOutlined,
  DownOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as toolApi from "@/api/tool";
import type { BuiltinToolResp, McpServerResp, ToolResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const router = useRouter();

const keyword = ref("");
const filterSource = ref("all");
const loading = ref(false);
const pageNo = ref(1);
const pageSize = ref(100);
const total = ref(0);
const expandedId = ref<string | null>(null);

const builtinTools = ref<BuiltinToolResp[]>([]);
const dbTools = ref<ToolResp[]>([]);
const mcpServers = ref<McpServerResp[]>([]);

const sourceFilters = [
  { label: "全部", value: "all" },
  { label: "系统内置", value: "builtin" },
  { label: "MCP 工具", value: "mcp" },
  { label: "API 集成", value: "api" },
];

const showBuiltin = computed(() => filterSource.value === "all" || filterSource.value === "builtin");
const showMcp = computed(() => filterSource.value === "all" || filterSource.value === "mcp");
const showApi = computed(() => filterSource.value === "all" || filterSource.value === "api");

const builtinFiltered = computed(() => {
  if (!showBuiltin.value) return [];
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return builtinTools.value;
  return builtinTools.value.filter(
    (t) => t.tool_name.toLowerCase().includes(kw) || t.description.toLowerCase().includes(kw)
  );
});

const mcpTools = computed(() => dbTools.value.filter((t) => t.source === "mcp"));
const apiTools = computed(() => dbTools.value.filter((t) => t.source === "api"));

interface McpServerGroup {
  server: McpServerResp | null;
  serverId: string;
  tools: ToolResp[];
}

const mcpServerGroups = computed(() => {
  const groups: Record<string, ToolResp[]> = {};
  for (const t of mcpTools.value) {
    const sid = t.mcp_server_id || "_unknown";
    if (!groups[sid]) groups[sid] = [];
    groups[sid].push(t);
  }
  const result: McpServerGroup[] = [];
  for (const [sid, tools] of Object.entries(groups)) {
    result.push({
      server: sid !== "_unknown" ? serverMap.value[sid] || null : null,
      serverId: sid,
      tools,
    });
  }
  return result;
});

const serverMap = computed(() => {
  const m: Record<string, McpServerResp> = {};
  for (const s of mcpServers.value) m[s.id] = s;
  return m;
});

const transportLabel: Record<string, string> = {
  sse: "Server-Sent Events",
  streamable_http: "Streamable HTTP",
};

function toggleExpand(id: string) {
  expandedId.value = expandedId.value === id ? null : id;
}

function selectSourceFilter(value: string) {
  filterSource.value = value;
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
    const sourceParam = filterSource.value === "all" || filterSource.value === "builtin"
      ? undefined
      : filterSource.value;
    const { data } = await toolApi.pageTool({
      page_no: pageNo.value,
      page_size: pageSize.value,
      keyword: keyword.value || undefined,
      source: sourceParam,
    });
    dbTools.value = data.data;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function loadBuiltin() {
  const { data } = await toolApi.listBuiltinTools();
  builtinTools.value = data.data;
}

async function loadServers() {
  const { data } = await toolApi.listMcpServers();
  mcpServers.value = data.data;
}

async function onDelete(t: ToolResp) {
  await toolApi.deleteTool(t.id);
  message.success("已删除");
  expandedId.value = null;
  loadList();
}

async function onEnable(t: ToolResp) {
  await toolApi.enableTool(t.id);
  message.success("已启用");
  loadList();
}

async function onDisable(t: ToolResp) {
  await toolApi.disableTool(t.id);
  message.success("已停用");
  loadList();
}

onMounted(() => {
  Promise.all([loadBuiltin(), loadList(), loadServers()]);
});
</script>

<style scoped>
.tool-page {
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.1), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.86) 100%);
  box-shadow:
    0 24px 48px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
  padding: 24px;
}

.tool-page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.tool-page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.tool-page-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.tool-head-btn {
  height: 40px;
  padding-inline: 16px;
  border-radius: 12px;
}

/* Filter */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 18px;
  padding: 4px 0px;
}

.search-input {
  width: 280px;
  flex-shrink: 0;
}

.filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-chip {
  border: 1px solid transparent;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.72);
  padding: 8px 14px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}

.filter-chip:hover,
.filter-chip--active {
  border-color: rgba(59, 130, 246, 0.18);
  background: rgba(219, 234, 254, 0.8);
  color: #2563eb;
}

/* Section */
.section-label {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 22px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 700;
  color: #475569;
}

.section-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.section-dot--builtin { background: #10b981; }
.section-dot--mcp { background: #8b5cf6; }
.section-dot--api { background: #06b6d4; }

/* Tool Card */
.tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-card {
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.78);
  overflow: hidden;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.tool-card:hover {
  border-color: rgba(59, 130, 246, 0.2);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.06);
}

.tool-card-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  cursor: pointer;
}

.tool-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  font-size: 18px;
  flex-shrink: 0;
}

.tool-icon--builtin { background: rgba(16, 185, 129, 0.1); color: #059669; }
.tool-icon--mcp { background: rgba(139, 92, 246, 0.1); color: #7c3aed; }
.tool-icon--api { background: rgba(6, 182, 212, 0.1); color: #0891b2; }

.tool-card-body {
  flex: 1;
  min-width: 0;
}

.tool-card-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tool-card-name {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.tool-card-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.source-tag--builtin { background: rgba(16, 185, 129, 0.1); color: #059669; }
.source-tag--mcp { background: rgba(139, 92, 246, 0.1); color: #7c3aed; }
.source-tag--api { background: rgba(6, 182, 212, 0.1); color: #0891b2; }

.risk-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  text-transform: capitalize;
}

.risk-tag--low { background: rgba(16, 185, 129, 0.08); color: #059669; }
.risk-tag--medium { background: rgba(245, 158, 11, 0.08); color: #d97706; }
.risk-tag--high { background: rgba(239, 68, 68, 0.08); color: #dc2626; }

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.status-dot--enabled { background: #10b981; }
.status-dot--disabled { background: #cbd5e1; }

.expand-arrow {
  font-size: 12px;
  color: #94a3b8;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.expand-arrow--open {
  transform: rotate(180deg);
}

/* Detail */
.tool-detail {
  padding: 0 20px 18px;
  border-top: 1px solid rgba(226, 232, 240, 0.6);
}

.detail-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 700;
  color: #475569;
}

.badge {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}

.badge--visible {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.badge--hidden {
  background: rgba(148, 163, 184, 0.1);
  color: #64748b;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px 24px;
  margin-top: 12px;
}

.detail-span-2 {
  grid-column: span 2;
}

.detail-label {
  display: block;
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 4px;
}

.detail-value {
  font-size: 13px;
  color: #334155;
}

.detail-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}

/* MCP server group */
.mcp-server-group {
  margin-top: 22px;
}

.server-group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0px;
  margin-bottom: 10px;
}

.server-group-label {
  color: #7c3aed;
}

.server-group-sep {
  width: 1px;
  height: 14px;
  background: rgba(139, 92, 246, 0.2);
  flex-shrink: 0;
}

.server-group-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e1b4b;
}

.server-group-meta {
  font-size: 11px;
  color: #8b8fa3;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-group-count {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: #7c3aed;
  background: rgba(139, 92, 246, 0.08);
  padding: 2px 8px;
  border-radius: 999px;
  flex-shrink: 0;
}

.detail-kv-list {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-kv-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(248, 250, 252, 0.7);
}

.detail-kv-key {
  color: #475569;
  font-weight: 600;
  flex-shrink: 0;
}

.detail-kv-key::after {
  content: ":";
}

.detail-kv-value {
  color: #64748b;
  word-break: break-all;
}

.detail-section {
  margin-top: 12px;
}

.detail-json {
  margin: 6px 0 0;
  padding: 12px;
  border-radius: 10px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.6);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow-y: auto;
}

.detail-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(226, 232, 240, 0.6);
}

.detail-spacer {
  flex: 1;
}

.detail-time {
  font-size: 12px;
  color: #94a3b8;
}

.detail-hint {
  font-size: 12px;
  color: #94a3b8;
  font-style: italic;
}

.btn-warn {
  color: #d97706 !important;
}

.btn-green {
  color: #059669 !important;
}

.empty-block {
  padding: 56px 0;
}

.tool-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

@media (max-width: 960px) {
  .tool-page-head {
    flex-direction: column;
  }

  .detail-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
