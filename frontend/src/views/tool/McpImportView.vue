<template>
  <section class="mcp-import-page">
    <div class="form-header">
      <a-button type="text" @click="router.push('/tool')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <h2 class="form-title">从 MCP Server 导入</h2>
    </div>

    <!-- MCP Server Config -->
    <div class="form-card">
      <div class="form-section-title">MCP Server 配置</div>

      <div class="form-row">
        <label class="form-label"><span class="required">*</span>服务名称</label>
        <div class="form-field">
          <a-input v-model:value="serverForm.server_name" placeholder="如 deepwiki、jira-server" />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label"><span class="required">*</span>服务类型</label>
        <div class="form-field">
          <a-select v-model:value="serverForm.transport" style="width: 100%">
            <a-select-option value="streamable_http">Streamable HTTP</a-select-option>
            <a-select-option value="sse">Server-Sent Events (SSE)</a-select-option>
          </a-select>
        </div>
      </div>

      <div class="form-row">
        <label class="form-label"><span class="required">*</span>URL 地址</label>
        <div class="form-field">
          <a-input v-model:value="serverForm.endpoint_url" placeholder="https://mcp-server.example.com/mcp" />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">请求头</label>
        <div class="form-field">
          <a-textarea v-model:value="headersStr" :rows="2" placeholder='{"Authorization": "Bearer xxx"}' />
          <p class="form-hint">JSON 格式，用于传递认证信息</p>
        </div>
      </div>

      <div class="form-row">
        <label class="form-label">备注</label>
        <div class="form-field">
          <a-textarea v-model:value="serverForm.remark" :rows="2" placeholder="备注信息" />
        </div>
      </div>

      <div class="form-row">
        <label class="form-label" />
        <div class="form-field">
          <a-button type="primary" :loading="discovering" @click="onDiscover">
            <template #icon><SearchOutlined /></template>
            验证并获取工具列表
          </a-button>
          <span v-if="discoverError" class="discover-error">{{ discoverError }}</span>
          <span v-if="discoverSuccess" class="discover-success">
            验证成功，发现 {{ discoveredTools.length }} 个工具
          </span>
        </div>
      </div>
    </div>

    <!-- Discovered Tools -->
    <div v-if="discoverSuccess" class="form-card tool-list-card">
      <div class="form-section-title">
        工具列表
        <span class="tool-count">{{ selectedNames.size }} / {{ discoveredTools.length }} 已选</span>
        <span class="select-actions">
          <a-button size="small" type="link" @click="selectAll">全选</a-button>
          <a-button size="small" type="link" @click="selectNone">全不选</a-button>
        </span>
      </div>

      <div class="discovered-list">
        <div
          v-for="t in discoveredTools"
          :key="t.name"
          :class="['discovered-item', { 'discovered-item--selected': selectedNames.has(t.name) }]"
          @click="toggleSelect(t.name)"
        >
          <div class="discovered-row">
            <a-checkbox :checked="selectedNames.has(t.name)" class="discovered-check" />
            <div class="discovered-body">
              <div class="discovered-name">{{ t.name }}</div>
              <div class="discovered-desc">{{ t.description || "无描述" }}</div>
            </div>
            <a-button
              size="small"
              type="text"
              class="discovered-schema-btn"
              @click.stop="toggleSchema(t.name)"
            >
              {{ expandedSchema === t.name ? "收起" : "参数" }}
            </a-button>
          </div>
          <div v-if="expandedSchema === t.name" class="schema-panel" @click.stop>
            <div class="schema-title">参数定义（JSON Schema）</div>
            <pre class="schema-json">{{ JSON.stringify(t.parameters, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <div class="import-actions">
        <a-button @click="router.push('/tool')">取消</a-button>
        <a-button
          type="primary"
          :loading="importing"
          :disabled="selectedNames.size === 0"
          @click="onImport"
        >
          导入 {{ selectedNames.size }} 个工具
        </a-button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ArrowLeftOutlined, SearchOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as toolApi from "@/api/tool";
import type { McpDiscoveredTool } from "@/api/types";

const router = useRouter();

const serverForm = reactive({
  server_name: "",
  transport: "streamable_http",
  endpoint_url: "",
  remark: "",
});
const headersStr = ref("");

const discovering = ref(false);
const discoverError = ref("");
const discoverSuccess = ref(false);
const discoveredTools = ref<McpDiscoveredTool[]>([]);
const selectedNames = ref<Set<string>>(new Set());
const expandedSchema = ref<string | null>(null);
const importing = ref(false);

function toggleSchema(name: string) {
  expandedSchema.value = expandedSchema.value === name ? null : name;
}

function toggleSelect(name: string) {
  const s = new Set(selectedNames.value);
  if (s.has(name)) s.delete(name);
  else s.add(name);
  selectedNames.value = s;
}

function selectAll() {
  selectedNames.value = new Set(discoveredTools.value.map((t) => t.name));
}

function selectNone() {
  selectedNames.value = new Set();
}

async function onDiscover() {
  if (!serverForm.endpoint_url.trim()) {
    message.error("请填写 URL 地址");
    return;
  }

  let headers: Record<string, unknown> | undefined;
  if (headersStr.value.trim()) {
    try {
      headers = JSON.parse(headersStr.value);
    } catch {
      message.error("请求头 JSON 格式无效");
      return;
    }
  }

  discovering.value = true;
  discoverError.value = "";
  discoverSuccess.value = false;

  try {
    const { data } = await toolApi.discoverMcpTools({
      transport: serverForm.transport,
      endpoint_url: serverForm.endpoint_url,
      headers,
    });
    discoveredTools.value = data.data;
    selectedNames.value = new Set(data.data.map((t) => t.name));
    discoverSuccess.value = true;
  } catch (e: unknown) {
    discoverError.value = "验证失败，请检查配置";
    discoverSuccess.value = false;
  } finally {
    discovering.value = false;
  }
}

async function onImport() {
  if (!serverForm.server_name.trim()) {
    message.error("请填写服务名称");
    return;
  }

  let headers: Record<string, unknown> | undefined;
  if (headersStr.value.trim()) {
    try {
      headers = JSON.parse(headersStr.value);
    } catch {
      message.error("请求头 JSON 格式无效");
      return;
    }
  }

  importing.value = true;
  try {
    // 1. Create MCP Server
    const { data: serverData } = await toolApi.createMcpServer({
      server_name: serverForm.server_name,
      transport: serverForm.transport,
      endpoint_url: serverForm.endpoint_url,
      headers,
      remark: serverForm.remark || undefined,
    });
    const serverId = serverData.data.id;

    // 2. Create selected tools
    const selected = discoveredTools.value.filter((t) => selectedNames.value.has(t.name));
    for (const t of selected) {
      await toolApi.createTool({
        source: "mcp",
        tool_name: t.name,
        description: t.description,
        parameters: t.parameters,
        risk_level: "low",
        mcp_server_id: serverId,
      });
    }

    message.success(`已导入 ${selected.length} 个工具`);
    router.push("/tool");
  } finally {
    importing.value = false;
  }
}
</script>

<style scoped>
.mcp-import-page {
  border: 1px solid var(--surface-card-border);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, var(--color-info-bg), transparent 28%),
    var(--surface-card-bg);
  box-shadow: var(--surface-card-shadow);
  padding: 24px;
}

.form-header { display: flex; align-items: center; gap: 8px; }
.form-title { margin: 0; font-size: 20px; font-weight: 700; color: var(--color-text); }

.form-card { padding: 24px; border: 1px solid var(--color-border); border-radius: 18px; background: var(--surface-strong); margin-top: 18px; }
.form-section-title { display: flex; align-items: center; gap: 10px; font-size: 14px; font-weight: 700; color: var(--color-text-secondary); margin-bottom: 18px; }

.form-row { display: flex; gap: 16px; margin-bottom: 16px; }
.form-label { flex-shrink: 0; width: 80px; text-align: right; font-size: 13px; color: var(--color-text-secondary); padding-top: 6px; }
.required { color: var(--color-error); margin-right: 2px; }
.form-field { flex: 1; max-width: 560px; }
.form-hint { margin: 4px 0 0; font-size: 12px; color: var(--color-text-quaternary); }

.discover-error { margin-left: 12px; font-size: 13px; color: var(--color-error-strong); }
.discover-success { margin-left: 12px; font-size: 13px; color: var(--color-success-strong); }

/* Tool list card */
.tool-list-card { margin-top: 16px; }
.tool-count { font-size: 12px; font-weight: 400; color: var(--color-text-quaternary); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.select-actions { margin-left: auto; }

.discovered-list { display: flex; flex-direction: column; gap: 6px; max-height: 480px; overflow-y: auto; }
.discovered-item { padding: 0; border-radius: 12px; border: 1px solid var(--color-border); cursor: pointer; transition: all 0.15s ease; overflow: hidden; }
.discovered-item:hover { border-color: var(--color-info-bg-strong); background: var(--surface-muted); }
.discovered-item--selected { border-color: var(--color-info-bg-strong); background: var(--color-info-bg); }
.discovered-row { display: flex; align-items: center; gap: 12px; padding: 12px 14px; }
.discovered-check { pointer-events: none; }
.discovered-body { flex: 1; min-width: 0; }
.discovered-name { font-size: 14px; font-weight: 600; color: var(--color-text); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.discovered-desc { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.discovered-schema-btn { font-size: 12px; color: var(--color-text-tertiary) !important; flex-shrink: 0; }

.schema-panel { padding: 12px 14px; border-top: 1px solid var(--color-border); background: var(--surface-muted); cursor: default; }
.schema-title { font-size: 12px; font-weight: 600; color: var(--color-text-secondary); margin-bottom: 8px; }
.schema-json { margin: 0; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--color-text-secondary); white-space: pre-wrap; word-break: break-all; max-height: 240px; overflow-y: auto; }

.import-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--color-border); }

@media (max-width: 960px) {
  .form-row { flex-direction: column; gap: 6px; }
  .form-label { width: auto; text-align: left; padding-top: 0; }
  .form-field { max-width: 100%; }
}
</style>
