<template>
  <section class="tool-form-page">
    <div class="form-header">
      <a-button type="text" @click="router.push('/tool')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <h2 class="form-title">{{ isEdit ? "编辑工具" : "集成外部 API 工具" }}</h2>
    </div>

    <div v-if="isEdit && editSource === 'mcp'" class="source-label">
      <span class="source-badge source-badge--mcp">MCP 工具</span>
    </div>

    <div class="form-body">
      <div class="form-main">
        <!-- Tool Definition -->
        <div class="form-card">
          <div class="form-section-title">
            工具定义
            <span class="badge badge--visible">大模型可见</span>
          </div>
          <p class="form-section-hint">以下信息会发送给大模型，大模型根据这些信息决定何时调用、传什么参数。</p>

          <div class="form-row">
            <label class="form-label"><span class="required">*</span>工具名称</label>
            <div class="form-field">
              <a-input v-model:value="form.tool_name" placeholder="英文下划线命名，如 wechat_notify" />
              <p class="form-hint">大模型调用时引用的标识</p>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label"><span class="required">*</span>工具描述</label>
            <div class="form-field">
              <a-textarea v-model:value="form.description" :rows="3" placeholder="做什么 + 输入什么 + 返回什么" />
            </div>
          </div>

          <div class="form-row">
            <label class="form-label"><span class="required">*</span>工具参数</label>
            <div class="form-field">
              <a-textarea v-model:value="form.parametersStr" :rows="6" placeholder='{"type":"object","properties":{...},"required":[...]}' />
              <p class="form-hint">JSON Schema 格式。定义的参数可在下方 URL、Headers、Body 中通过 <code>{<!-- -->{参数名}}</code> 引用</p>
            </div>
          </div>
        </div>

        <!-- API Config -->
        <div class="form-card" v-if="editSource !== 'mcp'">
          <div class="form-section-title">
            HTTP 请求配置
            <span class="badge badge--hidden">大模型不可见</span>
          </div>
          <p class="form-section-hint">
            平台根据以下配置构建实际的 HTTP 请求。URL、Headers、Body 中可使用
            <code>{<!-- -->{参数名}}</code> 引用工具参数，调用时自动替换为大模型传入的值。
          </p>

          <div class="form-row">
            <label class="form-label"><span class="required">*</span>URL 地址</label>
            <div class="form-field">
              <a-input v-model:value="form.url" placeholder="https://api.example.com/v1/{{resource_type}}/search" />
              <p class="form-hint">支持 <code>{<!-- -->{参数名}}</code> 引用，如路径参数、查询参数拼接</p>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label"><span class="required">*</span>Http Method</label>
            <div class="form-field">
              <a-select v-model:value="form.method" style="width: 200px">
                <a-select-option v-for="m in httpMethods" :key="m" :value="m">{{ m }}</a-select-option>
              </a-select>
            </div>
          </div>

          <div class="form-row form-row--top">
            <label class="form-label">Http Headers</label>
            <div class="form-field">
              <div class="kv-list">
                <div v-for="(h, idx) in form.headers" :key="idx" class="kv-row">
                  <a-input v-model:value="h.key" placeholder="Header 名称" class="kv-key" />
                  <a-input v-model:value="h.value" placeholder="Header 值，支持 {{参数名}}" class="kv-value" />
                  <a-button type="text" size="small" danger @click="form.headers.splice(idx, 1)">
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </div>
              </div>
              <a-button type="dashed" size="small" class="kv-add-btn" @click="form.headers.push({ key: '', value: '' })">
                <template #icon><PlusOutlined /></template>
                添加 Header
              </a-button>
              <p class="form-hint">键值对格式，value 支持 <code>{<!-- -->{参数名}}</code> 引用</p>
            </div>
          </div>

          <div class="form-row form-row--top">
            <label class="form-label">Http Body</label>
            <div class="form-field">
              <a-textarea v-model:value="form.body" :rows="6" placeholder='{"touser": "{{touser}}", "msgtype": "{{msgtype}}", "text": {"content": "{{content}}"}}' />
              <p class="form-hint">请求体字符串，支持 <code>{<!-- -->{参数名}}</code> 引用。GET 请求通常留空</p>
            </div>
          </div>
        </div>

        <div class="form-actions">
          <a-button @click="router.push('/tool')">取消</a-button>
          <a-button type="primary" :loading="submitting" @click="onSubmit">
            {{ isEdit ? "保存" : "创建" }}
          </a-button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined, DeleteOutlined, PlusOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import * as toolApi from "@/api/tool";

const router = useRouter();
const route = useRoute();
const isEdit = computed(() => !!route.params.id);
const editId = computed(() => route.params.id as string);
const editSource = ref("api");
const submitting = ref(false);
const httpMethods = ["GET", "POST", "PUT", "DELETE"];

const form = reactive({
  tool_name: "",
  description: "",
  parametersStr: '{\n  "type": "object",\n  "properties": {},\n  "required": []\n}',
  tool_group: "",
  risk_level: "low",
  url: "",
  method: "POST",
  headers: [{ key: "Content-Type", value: "application/json" }] as Array<{ key: string; value: string }>,
  body: "",
});

async function loadEditData() {
  if (!isEdit.value) return;
  const { data } = await toolApi.getTool(editId.value);
  const t = data.data;
  editSource.value = t.source;
  form.tool_name = t.tool_name;
  form.description = t.description;
  form.parametersStr = JSON.stringify(t.parameters, null, 2);
  form.tool_group = t.tool_group || "";
  form.risk_level = t.risk_level || "low";
  if (t.api_config) {
    const c = t.api_config as Record<string, unknown>;
    form.url = (c.url as string) || "";
    form.method = (c.method as string) || "POST";
    form.body = (c.body as string) || "";
    if (Array.isArray(c.headers)) {
      form.headers = (c.headers as Array<{ key: string; value: string }>).map((h) => ({ ...h }));
    } else {
      form.headers = [];
    }
  }
}

function buildApiConfig() {
  return {
    url: form.url,
    method: form.method,
    headers: form.headers.filter((h) => h.key.trim()),
    body: form.body || undefined,
  };
}

async function onSubmit() {
  if (!form.tool_name.trim()) { message.error("请填写工具名称"); return; }
  if (!form.description.trim()) { message.error("请填写工具描述"); return; }
  let parameters: Record<string, unknown>;
  try { parameters = JSON.parse(form.parametersStr); } catch { message.error("工具参数 JSON 格式无效"); return; }

  const isMcpEdit = isEdit.value && editSource.value === "mcp";

  if (!isMcpEdit && !form.url.trim()) { message.error("请填写 URL 地址"); return; }

  const apiConfig = isMcpEdit ? undefined : buildApiConfig();

  submitting.value = true;
  try {
    if (isEdit.value) {
      await toolApi.updateTool(editId.value, {
        tool_name: form.tool_name,
        description: form.description,
        parameters,
        tool_group: form.tool_group || undefined,
        risk_level: form.risk_level,
        api_config: apiConfig,
      });
      message.success("已保存");
    } else {
      await toolApi.createTool({
        source: "api",
        tool_name: form.tool_name,
        description: form.description,
        parameters,
        tool_group: form.tool_group || undefined,
        risk_level: form.risk_level,
        api_config: apiConfig!,
      });
      message.success("工具已创建");
    }
    router.push("/tool");
  } finally {
    submitting.value = false;
  }
}

onMounted(() => {
  if (isEdit.value) loadEditData();
});
</script>

<style scoped>
.tool-form-page {
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 24px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.1), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.86) 100%);
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.78);
  padding: 24px;
}

.form-header { display: flex; align-items: center; gap: 8px; }
.form-title { margin: 0; font-size: 20px; font-weight: 700; color: #0f172a; }

.source-label { margin-top: 14px; }
.source-badge { display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.source-badge--mcp { background: rgba(139, 92, 246, 0.1); color: #7c3aed; }

.form-body { margin-top: 18px; }
.form-main { max-width: 780px; }
.form-card { padding: 24px; border: 1px solid rgba(226, 232, 240, 0.88); border-radius: 18px; background: rgba(255, 255, 255, 0.78); margin-bottom: 16px; }
.form-section-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 700; color: #334155; margin-bottom: 6px; }
.form-section-hint { font-size: 12px; color: #94a3b8; margin-bottom: 18px; line-height: 1.6; }
.form-section-hint code { font-size: 11px; background: rgba(139, 92, 246, 0.08); color: #7c3aed; padding: 1px 5px; border-radius: 3px; }

.badge { display: inline-flex; align-items: center; height: 20px; padding: 0 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }
.badge--visible { background: rgba(245, 158, 11, 0.1); color: #d97706; border: 1px solid rgba(245, 158, 11, 0.2); }
.badge--hidden { background: rgba(148, 163, 184, 0.1); color: #64748b; border: 1px solid rgba(148, 163, 184, 0.2); }

.form-row { display: flex; gap: 16px; margin-bottom: 18px; }
.form-row--top { align-items: flex-start; }
.form-label { flex-shrink: 0; width: 100px; text-align: right; font-size: 13px; color: #475569; padding-top: 6px; }
.required { color: #ef4444; margin-right: 2px; }
.form-field { flex: 1; }
.form-hint { margin: 5px 0 0; font-size: 12px; color: #94a3b8; line-height: 1.5; }
.form-hint code { font-size: 11px; background: rgba(139, 92, 246, 0.08); color: #7c3aed; padding: 1px 5px; border-radius: 3px; }
.form-actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 8px; }

/* Key-Value list for headers */
.kv-list { display: flex; flex-direction: column; gap: 8px; }
.kv-row { display: flex; align-items: center; gap: 8px; }
.kv-key { width: 200px; flex-shrink: 0; }
.kv-value { flex: 1; }
.kv-add-btn { margin-top: 8px; }

@media (max-width: 960px) {
  .form-row { flex-direction: column; gap: 6px; }
  .form-label { width: auto; text-align: left; padding-top: 0; }
  .kv-row { flex-wrap: wrap; }
  .kv-key { width: 100%; }
}
</style>
