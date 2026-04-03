<template>
  <div class="form-page">
    <a-button type="link" class="back-btn" @click="goBack">
      <template #icon><ArrowLeftOutlined /></template>
      {{ isEdit ? "返回应用详情" : "返回应用列表" }}
    </a-button>

    <section class="form-shell">
      <div class="form-shell-head">
        <div>
          <h2 class="form-title">{{ isEdit ? "编辑应用" : "创建应用" }}</h2>
          <p class="form-sub">按应用类型完成基础信息、模型参数、业务配置和平台配置。</p>
        </div>
        <div v-if="!isEdit" class="step-pills">
          <span :class="['step-pill', { 'step-pill--active': step === 1 }]">1. 选择类型</span>
          <span :class="['step-pill', { 'step-pill--active': step === 2 }]">2. 配置应用</span>
        </div>
      </div>

      <div v-if="!isEdit && step === 1" class="type-grid">
        <button
          v-for="item in appTypeOptions"
          :key="item.value"
          type="button"
          :class="['type-card', { 'type-card--selected': formModel.app_type === item.value }]"
          @click="selectType(item.value)"
        >
          <span class="type-icon" :style="{ background: item.bg }">{{ item.emoji }}</span>
          <span class="type-name">{{ item.label }}</span>
          <span class="type-desc">{{ item.desc }}</span>
          <span class="type-features">{{ item.features.join(" / ") }}</span>
        </button>
      </div>

      <a-form
        v-if="isEdit || step === 2"
        ref="formRef"
        :model="formModel"
        :rules="formRules"
        layout="vertical"
        class="app-form"
      >
        <section class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">{{ currentTypeLabel }}</h3>
              <p class="section-sub">定义应用名称与基础说明。</p>
            </div>
          </div>
          <a-form-item label="应用名称" name="name">
            <a-input v-model:value="formModel.name" placeholder="请输入应用名称" />
          </a-form-item>
          <a-form-item label="应用描述" name="description">
            <a-textarea v-model:value="formModel.description" :rows="3" placeholder="请输入应用描述" />
          </a-form-item>
        </section>

        <section v-if="formModel.app_type !== 'agent_flow'" class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">模型与参数</h3>
              <p class="section-sub">选择供应商与模型，并配置通用推理参数。</p>
            </div>
          </div>
          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item label="模型供应商" name="provider_id">
                <a-select
                  v-model:value="formModel.provider_id"
                  placeholder="请选择供应商"
                  option-filter-prop="label"
                  show-search
                  @change="onProviderChange"
                >
                  <a-select-option
                    v-for="provider in providerOptions"
                    :key="provider.value"
                    :value="provider.value"
                    :label="provider.label"
                  >
                    {{ provider.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item label="模型" name="model_id">
                <a-select
                  v-model:value="formModel.model_id"
                  placeholder="请选择模型"
                  option-filter-prop="label"
                  show-search
                >
                  <a-select-option
                    v-for="model in currentModelOptions"
                    :key="model.value"
                    :value="model.value"
                    :label="model.label"
                  >
                    {{ model.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item label="Temperature">
                <a-input-number
                  v-model:value="modelSetting.temperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  class="full-width"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item label="Max Tokens">
                <a-input-number
                  v-model:value="modelSetting.max_tokens"
                  :min="128"
                  :max="32768"
                  :step="128"
                  class="full-width"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </section>

        <section v-if="formModel.app_type === 'llm'" class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">输入变量</h3>
              <p class="section-sub">定义用户侧输入字段，用于在 Prompt 中引用。</p>
            </div>
            <a-button type="dashed" @click="addInputVar">新增变量</a-button>
          </div>
          <div v-if="llmConfig.input_vars.length" class="config-list">
            <div v-for="(item, idx) in llmConfig.input_vars" :key="idx" class="config-list-item">
              <a-row :gutter="12">
                <a-col :span="6">
                  <a-input v-model:value="item.name" placeholder="变量名" />
                </a-col>
                <a-col :span="6">
                  <a-input v-model:value="item.label" placeholder="显示标签" />
                </a-col>
                <a-col :span="6">
                  <a-select v-model:value="item.type">
                    <a-select-option v-for="type in inputVarTypes" :key="type" :value="type">
                      {{ inputVarTypeLabel[type] }}
                    </a-select-option>
                  </a-select>
                </a-col>
                <a-col :span="4">
                  <a-switch v-model:checked="item.required" checked-children="必填" un-checked-children="可选" />
                </a-col>
                <a-col :span="2" class="config-action">
                  <a-button danger type="link" @click="removeInputVar(idx)">删除</a-button>
                </a-col>
              </a-row>
            </div>
          </div>
          <a-empty v-else :image="false" description="暂无输入变量" />

          <div class="section-head section-head--sub">
            <div>
              <h3 class="section-title">提示词配置</h3>
              <p class="section-sub">支持通过 <code v-pre>{{变量名}}</code> 引用输入变量。</p>
            </div>
          </div>
          <a-form-item label="System Prompt">
            <a-textarea v-model:value="llmConfig.system_prompt" :rows="6" />
          </a-form-item>
          <a-form-item label="User Prompt">
            <a-textarea v-model:value="llmConfig.user_prompt" :rows="6" />
          </a-form-item>

          <div class="section-head section-head--sub">
            <div>
              <h3 class="section-title">输出配置</h3>
              <p class="section-sub">定义输出格式和结构化返回约束。</p>
            </div>
            <a-button type="dashed" @click="addOutputVar">新增输出变量</a-button>
          </div>
          <a-form-item label="输出格式">
            <a-radio-group v-model:value="llmConfig.output_format">
              <a-radio value="text">Text</a-radio>
              <a-radio value="json">JSON</a-radio>
              <a-radio value="markdown">Markdown</a-radio>
            </a-radio-group>
          </a-form-item>
          <a-form-item v-if="llmConfig.output_format === 'json'" label="Output Schema">
            <a-textarea v-model:value="llmConfig.output_schema" :rows="6" placeholder='{"type":"object"}' />
          </a-form-item>
          <div v-if="llmConfig.output_vars.length" class="config-list">
            <div v-for="(item, idx) in llmConfig.output_vars" :key="idx" class="config-list-item">
              <a-row :gutter="12">
                <a-col :span="8">
                  <a-input v-model:value="item.name" placeholder="输出字段名" />
                </a-col>
                <a-col :span="6">
                  <a-select v-model:value="item.type">
                    <a-select-option v-for="type in outputVarTypes" :key="type" :value="type">
                      {{ type }}
                    </a-select-option>
                  </a-select>
                </a-col>
                <a-col :span="8">
                  <a-input v-model:value="item.desc" placeholder="说明" />
                </a-col>
                <a-col :span="2" class="config-action">
                  <a-button danger type="link" @click="removeOutputVar(idx)">删除</a-button>
                </a-col>
              </a-row>
            </div>
          </div>
        </section>

        <section v-if="formModel.app_type === 'rag'" class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">知识库与检索配置</h3>
              <p class="section-sub">当前阶段先通过知识库 ID 或名称进行绑定。</p>
            </div>
          </div>
          <a-form-item label="知识库">
            <a-select
              v-model:value="ragConfig.kb_ids"
              mode="tags"
              :token-separators="[',']"
              placeholder="输入知识库 ID 或名称后回车"
            />
          </a-form-item>
          <a-row :gutter="16">
            <a-col :xs="24" :md="8">
              <a-form-item label="相似度阈值">
                <a-input-number v-model:value="ragConfig.similarity_threshold" :min="0" :max="1" :step="0.05" class="full-width" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="向量权重">
                <a-input-number v-model:value="ragConfig.vector_weight" :min="0" :max="1" :step="0.1" class="full-width" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="Top N">
                <a-input-number v-model:value="ragConfig.top_n" :min="1" :max="50" class="full-width" />
              </a-form-item>
            </a-col>
          </a-row>
          <div class="switch-grid">
            <div class="switch-card">
              <div class="switch-head">
                <span class="switch-title">启用 Rerank</span>
                <a-switch v-model:checked="ragConfig.enable_rerank" />
              </div>
              <a-input v-if="ragConfig.enable_rerank" v-model:value="ragConfig.rerank_model" placeholder="Rerank 模型" />
            </div>
            <div class="switch-card">
              <div class="switch-head">
                <span class="switch-title">启用总结</span>
                <a-switch v-model:checked="ragConfig.enable_summary" />
              </div>
              <a-input v-if="ragConfig.enable_summary" v-model:value="ragConfig.summary_model" placeholder="总结模型" />
            </div>
          </div>
          <a-form-item v-if="ragConfig.enable_summary" label="总结 Prompt">
            <a-textarea v-model:value="ragConfig.summary_prompt" :rows="5" />
          </a-form-item>
        </section>

        <section v-if="formModel.app_type === 'nl2sql'" class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">数据源配置</h3>
              <p class="section-sub">定义数据库连接与 Schema 描述。</p>
            </div>
          </div>
          <a-form-item label="数据库连接">
            <a-input v-model:value="nl2sqlConfig.db_connection" placeholder="如 clickhouse-prod" />
          </a-form-item>
          <a-form-item label="Schema / DDL">
            <a-textarea v-model:value="nl2sqlConfig.db_schema" :rows="8" />
          </a-form-item>
        </section>

        <section v-if="formModel.app_type === 'agent'" class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">Agent 配置</h3>
              <p class="section-sub">配置系统提示词、工具、技能和智能体行为参数。</p>
            </div>
          </div>
          <a-form-item label="System Prompt">
            <a-textarea v-model:value="agentConfig.system_prompt" :rows="8" />
          </a-form-item>
          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item label="绑定工具">
                <a-select
                  v-model:value="agentBindings.tool_ids"
                  mode="multiple"
                  show-search
                  option-filter-prop="label"
                  :options="toolOptions"
                  placeholder="选择工具"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item label="绑定技能">
                <a-select
                  v-model:value="agentBindings.skill_ids"
                  mode="multiple"
                  show-search
                  option-filter-prop="label"
                  :options="skillOptions"
                  placeholder="选择技能"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :xs="24" :md="8">
              <a-form-item label="最大轮次">
                <a-input-number v-model:value="agentConfig.max_turns" :min="1" :max="100" class="full-width" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="超时时间（秒）">
                <a-input-number v-model:value="agentConfig.agent_timeout" :min="10" :max="600" class="full-width" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="自动执行">
                <a-switch v-model:checked="agentConfig.allow_auto_exec" />
              </a-form-item>
            </a-col>
          </a-row>

          <div class="section-head section-head--sub">
            <div>
              <h3 class="section-title">子智能体</h3>
              <p class="section-sub">作为扩展配置保留，支持后续多智能体协作。</p>
            </div>
            <a-button type="dashed" @click="addSubAgent">新增子智能体</a-button>
          </div>
          <div v-if="agentConfig.sub_agents.length" class="config-list">
            <div v-for="(item, idx) in agentConfig.sub_agents" :key="idx" class="config-list-item">
              <a-row :gutter="12">
                <a-col :span="6">
                  <a-input v-model:value="item.name" placeholder="名称" />
                </a-col>
                <a-col :span="6">
                  <a-input v-model:value="item.model" placeholder="模型" />
                </a-col>
                <a-col :span="10">
                  <a-input v-model:value="item.role" placeholder="职责描述" />
                </a-col>
                <a-col :span="2" class="config-action">
                  <a-button danger type="link" @click="removeSubAgent(idx)">删除</a-button>
                </a-col>
              </a-row>
            </div>
          </div>
        </section>

        <section v-if="formModel.app_type === 'agent_flow'" class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">Agent Flow 编排配置</h3>
              <p class="section-sub">当前阶段先维护流程元数据，完整可视化编排后续接入。</p>
            </div>
          </div>
          <a-alert
            type="info"
            show-icon
            message="当前系统先实现 Agent Flow 基础信息与流程标识配置，可视化编排器后续接入。"
            class="flow-alert"
          />
          <a-row :gutter="16">
            <a-col :xs="24" :md="8">
              <a-form-item label="流程实例">
                <a-input v-model:value="flowConfig.flow_instance" placeholder="如 flow-prod" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="流程 ID">
                <a-input v-model:value="flowConfig.flow_id" placeholder="Flowise 流程 ID" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="流程名称">
                <a-input v-model:value="flowConfig.flow_name" placeholder="流程名称" />
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="同步 Trace">
            <a-switch v-model:checked="flowConfig.flow_sync_trace" />
          </a-form-item>
        </section>

        <section class="form-section">
          <div class="section-head">
            <div>
              <h3 class="section-title">平台配置</h3>
              <p class="section-sub">控制访问方式、限流与日志保留策略。</p>
            </div>
          </div>
          <a-row :gutter="16">
            <a-col :xs="24" :md="8">
              <a-form-item label="访问范围">
                <a-select v-model:value="formModel.access_scope">
                  <a-select-option value="internal">企业内部</a-select-option>
                  <a-select-option value="api">API 开放</a-select-option>
                  <a-select-option value="embed">嵌入式</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="限流（次/分）">
                <a-input-number v-model:value="formModel.rate_limit" :min="1" :max="10000" class="full-width" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="8">
              <a-form-item label="调用日志">
                <a-switch v-model:checked="formModel.enable_log" />
              </a-form-item>
            </a-col>
          </a-row>
        </section>

        <div class="form-actions">
          <a-button @click="goBack">取消</a-button>
          <a-button v-if="!isEdit && step === 2" @click="step = 1">上一步</a-button>
          <a-button type="primary" :loading="submitting" @click="submitForm">
            {{ isEdit ? "保存" : "创建应用" }}
          </a-button>
        </div>
      </a-form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeftOutlined } from "@ant-design/icons-vue";
import type { FormInstance, Rule } from "ant-design-vue/es/form";
import { message } from "ant-design-vue";
import * as appApi from "@/api/app";
import * as llmApi from "@/api/llm";
import * as skillApi from "@/api/skill";
import * as toolApi from "@/api/tool";
import type { AppResp, LlmProviderResp } from "@/api/types";

type InputVarType = "text" | "textarea" | "number" | "select" | "file";
type OutputFormat = "text" | "json" | "markdown";
type AppType = "llm" | "rag" | "nl2sql" | "agent" | "agent_flow";

type InputVar = {
  name: string;
  label: string;
  type: InputVarType;
  required: boolean;
};

type OutputVar = {
  name: string;
  type: string;
  desc: string;
};

const route = useRoute();
const router = useRouter();

const isEdit = computed(() => route.name === "app-edit");
const editId = computed(() => (isEdit.value ? (route.params.id as string) : ""));
const step = ref(1);
const formRef = ref<FormInstance>();
const submitting = ref(false);
const providerList = ref<LlmProviderResp[]>([]);
const toolOptions = ref<Array<{ label: string; value: string }>>([]);
const skillOptions = ref<Array<{ label: string; value: string }>>([]);

const appTypeLabel: Record<AppType, string> = {
  llm: "LLM 应用",
  rag: "RAG 应用",
  nl2sql: "NL2SQL 应用",
  agent: "Agent 智能体应用",
  agent_flow: "Agent Flow 应用",
};

const appTypeOptions: Array<{
  value: AppType;
  label: string;
  desc: string;
  emoji: string;
  bg: string;
  features: string[];
}> = [
  {
    value: "agent",
    label: "Agent 智能体",
    desc: "具备自主决策能力的智能体，可调用工具与技能执行多步任务。",
    emoji: "🤖",
    bg: "rgba(139, 92, 246, 0.12)",
    features: ["多步推理", "工具调用", "技能编排", "自主决策"],
  },
  {
    value: "agent_flow",
    label: "Agent Flow 编排",
    desc: "可视化工作流编排，将平台能力组装成复杂业务流程。",
    emoji: "🔄",
    bg: "rgba(245, 158, 11, 0.12)",
    features: ["可视化编排", "节点拖拽", "条件分支", "并行执行"],
  },
  {
    value: "llm",
    label: "LLM 应用",
    desc: "基于大模型的通用应用，支持提示词编排与结构化输出。",
    emoji: "✨",
    bg: "rgba(16, 185, 129, 0.12)",
    features: ["多模型切换", "结构化输出", "Prompt 编排", "统一接口"],
  },
  {
    value: "rag",
    label: "RAG 知识库问答",
    desc: "基于知识库的智能问答，支持语义检索、重排和总结。",
    emoji: "📚",
    bg: "rgba(59, 130, 246, 0.12)",
    features: ["语义检索", "Rerank", "总结增强", "引用溯源"],
  },
  {
    value: "nl2sql",
    label: "NL2SQL 数据查询",
    desc: "自然语言查询数据库，自动生成 SQL 并返回结构化结果。",
    emoji: "🗄",
    bg: "rgba(6, 182, 212, 0.12)",
    features: ["Schema 检索", "SQL 生成", "自动执行", "结构化输出"],
  },
];

const inputVarTypes: InputVarType[] = ["text", "textarea", "number", "select", "file"];
const inputVarTypeLabel: Record<InputVarType, string> = {
  text: "单行文本",
  textarea: "多行文本",
  number: "数字",
  select: "下拉选择",
  file: "文件上传",
};
const outputVarTypes = ["string", "number", "boolean", "array", "object"];

const formModel = reactive({
  name: "",
  description: "",
  app_type: "" as AppType | "",
  provider_id: undefined as string | undefined,
  model_id: undefined as string | undefined,
  access_scope: "internal",
  rate_limit: 60,
  enable_log: true,
});

const modelSetting = reactive({
  temperature: 0.7,
  max_tokens: 2048,
});

const llmConfig = reactive({
  system_prompt: "",
  user_prompt: "",
  input_vars: [{ name: "user_input", label: "用户输入", type: "textarea", required: true }] as InputVar[],
  output_format: "text" as OutputFormat,
  output_schema: "",
  output_vars: [] as OutputVar[],
});

const ragConfig = reactive({
  kb_ids: [] as string[],
  similarity_threshold: 0.2,
  vector_weight: 0.3,
  top_n: 6,
  enable_rerank: false,
  rerank_model: "",
  rerank_top_n: 3,
  enable_summary: false,
  summary_model: "",
  summary_temperature: 0.3,
  summary_prompt: "",
});

const nl2sqlConfig = reactive({
  db_connection: "",
  db_schema: "",
});

const agentConfig = reactive({
  system_prompt: "",
  max_turns: 20,
  agent_timeout: 60,
  allow_auto_exec: false,
  sub_agents: [] as Array<{ name: string; model: string; role: string }>,
});

// agent 应用绑定的工具/技能 ID，作为顶层字段独立提交，不再通过 app_config
const agentBindings = reactive({
  tool_ids: [] as string[],
  skill_ids: [] as string[],
});

const flowConfig = reactive({
  flow_instance: "",
  flow_id: "",
  flow_name: "",
  flow_sync_trace: true,
});

const formRules = computed<Record<string, Rule[]>>(() => ({
  name: [{ required: true, message: "请输入应用名称" }],
  provider_id: formModel.app_type !== "agent_flow" ? [{ required: true, message: "请选择模型供应商" }] : [],
  model_id: formModel.app_type !== "agent_flow" ? [{ required: true, message: "请选择模型" }] : [],
}));

const currentTypeLabel = computed(() =>
  formModel.app_type ? appTypeLabel[formModel.app_type] || "应用" : "应用"
);

const providerOptions = computed(() =>
  providerList.value.map((provider) => ({
    label: provider.name,
    value: provider.id,
  }))
);

const currentModelOptions = computed(() => {
  const provider = providerList.value.find((item) => item.id === formModel.provider_id);
  if (!provider) return [];
  return provider.models
    .filter((item) => item.status === "active")
    .map((item) => ({
      label: `${item.model} (${item.model_type})`,
      value: item.id,
    }));
});

function selectType(type: AppType) {
  formModel.app_type = type;
  step.value = 2;
}

function onProviderChange() {
  formModel.model_id = undefined;
}

function addInputVar() {
  llmConfig.input_vars.push({ name: "", label: "", type: "text", required: false });
}

function removeInputVar(index: number) {
  llmConfig.input_vars.splice(index, 1);
}

function addOutputVar() {
  llmConfig.output_vars.push({ name: "", type: "string", desc: "" });
}

function removeOutputVar(index: number) {
  llmConfig.output_vars.splice(index, 1);
}

function addSubAgent() {
  agentConfig.sub_agents.push({ name: "", model: "", role: "" });
}

function removeSubAgent(index: number) {
  agentConfig.sub_agents.splice(index, 1);
}

function buildAppConfig() {
  switch (formModel.app_type) {
    case "llm":
      return { ...llmConfig };
    case "rag":
      return { ...ragConfig };
    case "nl2sql":
      return { ...nl2sqlConfig };
    case "agent":
      return { ...agentConfig };
    case "agent_flow":
      return { ...flowConfig };
    default:
      return {};
  }
}

function buildModelSetting() {
  if (formModel.app_type === "agent_flow") {
    return {};
  }
  return { ...modelSetting };
}

function fillFromApp(app: AppResp) {
  formModel.name = app.name;
  formModel.description = app.description || "";
  formModel.app_type = app.app_type as AppType;
  formModel.provider_id = app.provider_id || undefined;
  formModel.model_id = app.model_id || undefined;
  formModel.access_scope = app.access_scope || "internal";
  formModel.rate_limit = app.rate_limit ?? 60;
  formModel.enable_log = !!app.enable_log;
  modelSetting.temperature = Number(app.model_setting?.temperature ?? 0.7);
  modelSetting.max_tokens = Number(app.model_setting?.max_tokens ?? 2048);

  const config = app.app_config || {};
  if (app.app_type === "llm") {
    llmConfig.system_prompt = String(config.system_prompt ?? "");
    llmConfig.user_prompt = String(config.user_prompt ?? "");
    llmConfig.input_vars = ((config.input_vars as InputVar[]) || []).map((item) => ({ ...item }));
    llmConfig.output_format = (config.output_format as OutputFormat) || "text";
    llmConfig.output_schema = typeof config.output_schema === "string"
      ? config.output_schema
      : JSON.stringify(config.output_schema || {}, null, 2);
    llmConfig.output_vars = ((config.output_vars as OutputVar[]) || []).map((item) => ({ ...item }));
  }
  if (app.app_type === "rag") {
    Object.assign(ragConfig, {
      kb_ids: ((config.kb_ids as string[]) || []).slice(),
      similarity_threshold: config.similarity_threshold ?? 0.2,
      vector_weight: config.vector_weight ?? 0.3,
      top_n: config.top_n ?? 6,
      enable_rerank: !!config.enable_rerank,
      rerank_model: config.rerank_model ?? "",
      rerank_top_n: config.rerank_top_n ?? 3,
      enable_summary: !!config.enable_summary,
      summary_model: config.summary_model ?? "",
      summary_temperature: config.summary_temperature ?? 0.3,
      summary_prompt: config.summary_prompt ?? "",
    });
  }
  if (app.app_type === "nl2sql") {
    Object.assign(nl2sqlConfig, {
      db_connection: config.db_connection ?? "",
      db_schema: config.db_schema ?? "",
    });
  }
  if (app.app_type === "agent") {
    Object.assign(agentConfig, {
      system_prompt: config.system_prompt ?? "",
      max_turns: config.max_turns ?? 20,
      agent_timeout: config.agent_timeout ?? 60,
      allow_auto_exec: !!config.allow_auto_exec,
      sub_agents: ((config.sub_agents as Array<{ name: string; model: string; role: string }>) || []).map(
        (item) => ({ ...item })
      ),
    });
    agentBindings.tool_ids = (app.tool_ids ?? []).slice();
    agentBindings.skill_ids = (app.skill_ids ?? []).slice();
  }
  if (app.app_type === "agent_flow") {
    Object.assign(flowConfig, {
      flow_instance: config.flow_instance ?? "",
      flow_id: config.flow_id ?? "",
      flow_name: config.flow_name ?? "",
      flow_sync_trace: config.flow_sync_trace ?? true,
    });
  }
}

async function loadDependencies() {
  const [{ data: providerData }, { data: toolData }, { data: skillData }] = await Promise.all([
    llmApi.pageProvider({ page_no: 1, page_size: 200 }),
    toolApi.pageTool({ page_no: 1, page_size: 1000, tool_status: "enabled" }),
    skillApi.pageSkill({ page_no: 1, page_size: 1000, skill_status: "enabled" }),
  ]);
  providerList.value = providerData.data.filter((item) => item.models.length > 0);
  toolOptions.value = toolData.data.map((item) => ({
    label: `${item.tool_name} (${item.source})`,
    value: item.id,
  }));
  skillOptions.value = skillData.data.map((item) => ({
    label: item.name,
    value: item.id,
  }));
}

async function loadEditData() {
  if (!isEdit.value) return;
  const { data } = await appApi.getApp(editId.value);
  fillFromApp(data.data);
}

async function submitForm() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  if (!formModel.app_type) {
    message.error("请选择应用类型");
    return;
  }
  submitting.value = true;
  try {
    const isAgent = formModel.app_type === "agent";
    const payload = {
      name: formModel.name,
      description: formModel.description || undefined,
      app_type: formModel.app_type,
      provider_id: formModel.provider_id,
      model_id: formModel.model_id,
      model_setting: formModel.app_type !== "agent_flow" ? buildModelSetting() : undefined,
      app_config: buildAppConfig(),
      access_scope: formModel.access_scope,
      rate_limit: formModel.rate_limit,
      enable_log: formModel.enable_log,
      tool_ids: isAgent ? agentBindings.tool_ids.slice() : undefined,
      skill_ids: isAgent ? agentBindings.skill_ids.slice() : undefined,
    };

    if (isEdit.value) {
      await appApi.updateApp(editId.value, payload);
      message.success("保存成功");
      await router.push(`/app/${editId.value}`);
    } else {
      const { data } = await appApi.createApp(payload);
      message.success("创建成功");
      await router.push(`/app/${data.data.id}`);
    }
  } finally {
    submitting.value = false;
  }
}

async function goBack() {
  if (isEdit.value) {
    await router.push(`/app/${editId.value}`);
    return;
  }
  if (step.value === 2) {
    step.value = 1;
    return;
  }
  await router.push("/app");
}

onMounted(async () => {
  await loadDependencies();
  if (isEdit.value) {
    await loadEditData();
    step.value = 2;
  }
});
</script>

<style scoped>
.form-page {
  min-height: 0;
}

.back-btn {
  padding: 0;
  margin-bottom: 16px;
}

.form-shell {
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

.form-shell-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.form-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
}

.form-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.step-pills {
  display: flex;
  gap: 8px;
}

.step-pill {
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.92);
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  line-height: 30px;
}

.step-pill--active {
  background: rgba(37, 99, 235, 0.12);
  color: #2563eb;
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
  margin-top: 20px;
}

.type-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.type-card:hover,
.type-card--selected {
  transform: translateY(-2px);
  border-color: rgba(37, 99, 235, 0.22);
  box-shadow: 0 16px 36px rgba(37, 99, 235, 0.08);
}

.type-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.type-name {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.type-desc,
.type-features {
  font-size: 13px;
  color: #64748b;
  line-height: 1.7;
}

.type-features {
  color: #475569;
}

.app-form {
  margin-top: 20px;
}

.form-section {
  padding: 20px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  margin-bottom: 16px;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.section-head--sub {
  margin-top: 24px;
}

.section-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}

.section-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: #64748b;
}

.config-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.config-list-item {
  padding: 12px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(226, 232, 240, 0.8);
}


.config-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.switch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 8px;
}

.switch-card {
  padding: 14px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(226, 232, 240, 0.8);
}

.switch-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.switch-title {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.flow-alert {
  margin-bottom: 16px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.full-width {
  width: 100%;
}

@media (max-width: 960px) {
  .form-shell-head {
    flex-direction: column;
  }

  .switch-grid {
    grid-template-columns: 1fr;
  }
}
</style>
