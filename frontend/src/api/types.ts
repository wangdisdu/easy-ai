export interface ApiResp<T> {
  code: number;
  msg: string;
  data: T;
}

export interface ApiPageResp<T> {
  code: number;
  msg: string;
  data: T[];
  total: number;
}

export interface UserResp {
  id: string;
  account: string;
  email?: string | null;
  name?: string | null;
  phone?: string | null;
  department?: string | null;
  roles?: Array<{
    id: string;
    code: string;
    name: string;
  }>;
  create_time: number;
  update_time: number;
}

export interface UserLoginResp {
  access_token: string;
  token_type: string;
  user: UserResp;
}

export interface UserGroupResp {
  id: string;
  code: string;
  name: string;
  create_time: number;
  update_time: number;
}

export interface RoleResp {
  id: string;
  code: string;
  name: string;
  permissions: string[];
  create_time: number;
  update_time: number;
}

export interface AppCategoryResp {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  sort_order: number;
  create_time: number;
  update_time: number;
}

export interface AppCategoryRef {
  id: string;
  name: string;
}

export interface AppResp {
  id: string;
  name: string;
  description?: string | null;
  app_type: string;
  app_status: string;
  provider_id?: string | null;
  model_id?: string | null;
  model?: string | null;
  model_setting?: Record<string, unknown> | null;
  app_config?: Record<string, unknown> | null;
  access_scope?: string | null;
  rate_limit?: number | null;
  enable_log?: boolean | null;
  version_id?: string | null;
  current_version?: string | null;
  flowise_chatflow_id?: string | null;
  tool_ids?: string[];
  skill_ids?: string[];
  category_ids?: string[];
  categories?: AppCategoryRef[];
  create_user?: string | null;
  create_time: number;
  update_time: number;
}

export interface AppVersionResp {
  id: string;
  app_id: string;
  version: string;
  version_note?: string | null;
  published_time: number;
  create_time: number;
}

export interface AppRunResp {
  app_id?: string | null;
  app_type: string;
  model: string;
  latency_ms?: number | null;
  result: Record<string, unknown>;
  // RAG 应用专属:命中 chunk 列表,前端用来渲染参考文档卡片
  references?: AppRunReference[];
  retrieved_count?: number;
  retrieve_latency_ms?: number;
  llm_latency_ms?: number;
}

export interface AppRunReference {
  doc_ref?: string | null;
  doc_id?: string | null;
  doc_name?: string | null;
  kb_id?: string | null;
  chunk_id?: string | null;
  similarity?: number | null;
  snippet?: string | null;
}

export interface AppLogResp {
  id: string;
  app_id?: string | null;
  app_type?: string | null;
  provider_id?: string | null;
  model_id?: string | null;
  model?: string | null;
  request_type: string;
  success: boolean;
  response_status?: number | null;
  latency_ms?: number | null;
  error_message?: string | null;
  langfuse_trace_id?: string | null;
  total_tokens?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  request_payload?: unknown;
  response_payload?: unknown;
  create_time: number;
}

export interface StatDelta {
  value: number | null;
  compare: number | null;
  delta_pct: number | null;
  sub_label: string | null;
}

export interface OverviewStats {
  total_requests: StatDelta;
  success_rate: StatDelta;
  p95_latency_ms: StatDelta;
  total_tokens: StatDelta;
}

export interface AppTrendSeries {
  app_id: string;
  app_name: string;
  color: string;
  data: number[];
}

export interface TrendResp {
  labels: string[];
  total: number[];
  apps: AppTrendSeries[];
}

export interface ModelTokenRow {
  model: string;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost: number | null;
}

export interface AppHealthRow {
  app_id: string;
  app_name: string;
  app_type: string;
  calls: number;
  success_rate: number;
  p95_latency_ms: number | null;
  avg_latency_ms: number | null;
  total_tokens: number;
  feedback_rate: number | null;
  trend: number[];
}

export interface ErrorAppRow {
  app_id: string;
  app_name: string;
  app_type: string;
  errors: number;
  error_rate: number;
  top_error: string | null;
}

export interface RecentRequestRow {
  id: string;
  app_id: string | null;
  app_name: string | null;
  app_type: string | null;
  user_id: string | null;
  preview: string;
  latency_ms: number | null;
  total_tokens: number | null;
  success: boolean;
  create_time: number;
  langfuse_trace_id: string | null;
  feedback: string | null;
}

export interface BuiltinToolResp {
  source: "builtin";
  tool_name: string;
  description: string;
  parameters: Record<string, unknown>;
  group?: string;
}

export interface McpServerResp {
  id: string;
  server_name: string;
  transport: string;
  endpoint_url: string;
  headers?: Record<string, unknown> | null;
  remark?: string | null;
  server_status: string;
  tool_count: number;
  create_time: number;
  update_time: number;
}

export interface McpDiscoveredTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface SkillToolItem {
  tool_id: string;
  tool_source: string;
  tool_name: string;
}

export interface SkillResp {
  id: string;
  name: string;
  description?: string | null;
  category_ids?: string[];
  categories?: AppCategoryRef[];
  instruction: string;
  skill_status: string;
  current_version?: string | null;
  tools: SkillToolItem[];
  create_time: number;
  update_time: number;
}

export interface SkillVersionResp {
  id: string;
  skill_id: string;
  version: string;
  version_note?: string | null;
  published_time: number;
  create_time: number;
}

export interface ToolResp {
  id: string;
  source: string;
  tool_name: string;
  description: string;
  parameters: Record<string, unknown>;
  tool_group?: string | null;
  risk_level?: string | null;
  tool_status: string;
  mcp_server_id?: string | null;
  api_config?: Record<string, unknown> | null;
  create_time: number;
  update_time: number;
}

export interface LlmModelResp {
  id: string;
  model: string;
  model_type: string;
  status: string;
  max_input_tokens?: number | null;
}

export interface LlmProviderResp {
  id: string;
  name: string;
  provider_type: string;
  base_url: string;
  api_key?: string | null;
  status: string;
  last_check?: number | null;
  models: LlmModelResp[];
  create_time: number;
  update_time: number;
}

// ── 智能助手 ──

export interface ConversationResp {
  id: string;
  app_id: string;
  app_type: string;
  app_name: string;
  title: string;
  status: string;
  last_message?: string | null;
  create_time: number;
  update_time: number;
}

export interface ConversationMessageResp {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content?: string | null;
  metadata?: Record<string, unknown> | null;
  create_time: number;
}

// ── 工具治理策略 ──

export type PolicyAction = "allow" | "deny" | "require_hitl";
export type PolicyMode = "active" | "shadow";

// AST 节点类型与 backend §5.1 对齐；v1 表单只生成 Compare 节点
export interface CompareNode {
  type: "Compare";
  op: string;
  var: string;
  value: unknown;
}

export interface AndNode {
  type: "And";
  conditions: WhenNode[];
}

export type WhenNode = CompareNode | AndNode;

export interface PolicyRuleReq {
  priority: number;
  action: PolicyAction;
  when_ast: WhenNode;
  reason?: string | null;
}

export interface PolicyRuleResp {
  id: string;
  priority: number;
  action: PolicyAction;
  when_ast: WhenNode;
  reason?: string | null;
}

export interface PolicyResp {
  tool_id: string;
  mode: PolicyMode;
  version: number;
  rules: PolicyRuleResp[];
}

export interface PolicyUpdateReq {
  mode: PolicyMode;
  rules: PolicyRuleReq[];
}

export interface PolicyContextVariable {
  name: string;
  kind: string;
  label: string;
}

export interface PolicyOptionsResp {
  actions: PolicyAction[];
  operators_by_kind: Record<string, string[]>;
  context_variables: PolicyContextVariable[];
}

// ── 知识库 v2 (详见 docs/knowledge-v2-design.md) ──
// 组织层:知识库 → 分类 → 文档;向量化层:RAG 库;中间靠分类映射连接。

export interface KbResp {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  doc_count: number;
  category_count: number;
  create_user?: string | null;
  create_time: number;
  update_time: number;
}

export interface KbOption {
  id: string;
  code: string;
  name: string;
  doc_count: number;
}

export interface KbCategoryNode {
  id: string;
  kb_id: string;
  name: string;
  parent_id: string;
  level: number;
  sort: number;
  // 直挂该节点(不含子树)的文档数
  doc_count: number;
  // 该分类映射到的 RAG 库(未映射时为空)
  rag_dataset_id?: string | null;
  rag_dataset_name?: string | null;
  children: KbCategoryNode[];
}

export interface KbCategoryDeletePreview {
  deleted: boolean;
  category_count: number;
  document_count: number;
}

export interface KbDocumentResp {
  id: string;
  // Base36 引用码,由 id 派生
  ref: string;
  kb_id: string;
  name: string;
  format: string;
  size_bytes?: number | null;
  // 树形分类: "0"=未分类; category_name 后端 join 回填
  category_id: string;
  category_name?: string | null;
  source_type: string;
  source_meta?: Record<string, unknown> | null;
  // 文档所属 RAG 库(由分类映射推导);未映射时为空
  rag_dataset_id?: string | null;
  ragflow_doc_id?: string | null;
  // not_mapped / pending / parsing / done / error
  vectorize_status: string;
  chunks_count: number;
  error_message?: string | null;
  parse_progress?: number;
  parse_begin_at?: number | null;
  parse_duration_sec?: number | null;
  parse_progress_msg?: string | null;
  // 原文是否已落 blob 存储
  has_original: boolean;
  create_user?: string | null;
  create_time: number;
  update_time: number;
}

export interface KbChunkResp {
  id: string;
  content: string;
  document_id?: string | null;
  document_keyword?: string | null;
  important_keywords: string[];
}

// ── RAG 库 / 映射 / 检索 ──

export interface RagDatasetResp {
  id: string;
  name: string;
  description?: string | null;
  ragflow_dataset_id?: string | null;
  embedding_model: string;
  chunk_method: string;
  parser_config?: Record<string, unknown> | null;
  doc_count: number;
  chunk_count: number;
  mapped_category_count: number;
  status: string;
  last_synced_at?: number | null;
  create_user?: string | null;
  create_time: number;
  update_time: number;
}

export interface RagDatasetOption {
  id: string;
  name: string;
  embedding_model: string;
  chunk_method: string;
  doc_count: number;
}

export interface MappedCategory {
  category_id: string;
  category_name: string;
  kb_id: string;
  kb_name: string;
  doc_count: number;
}

export interface LocalCategoryItem {
  kb_id: string;
  kb_name: string;
  category_id: string;
  category_name: string;
  doc_count: number;
  // 非空表示已被某 RAG 库占用
  mapped_dataset_id?: string | null;
}

export interface RetrieveHit {
  chunk_id: string;
  content: string;
  similarity?: number | null;
  doc_id?: string | null;
  doc_name?: string | null;
  highlight?: string | null;
  easyai_doc_id?: string | null;
  doc_ref?: string | null;
  kb_id?: string | null;
}

export interface RetrieveResp {
  hits: RetrieveHit[];
  total: number;
}

// ── 同步日志 ──

export interface SyncLogResp {
  id: string;
  log_type: string;
  source_type?: string | null;
  source_name?: string | null;
  target_kb_id?: string | null;
  target_dataset_id?: string | null;
  docs_added: number;
  docs_updated: number;
  docs_deleted: number;
  chunks_created: number;
  status: string;
  duration_ms?: number | null;
  detail?: string | null;
  create_time: number;
}

export interface SandboxViewResp {
  ready: boolean;
  url?: string | null;
  headers?: Record<string, string>;
}

export interface SandboxInstanceResp {
  id: string;
  status: string;
  image?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  metadata?: Record<string, string>;
}

// ── 应用集成 (详见 docs/application-integration-design.md) ──

export interface BoundAppItem {
  app_type: string;
  app_id: string;
}

export interface IntegrationKeyResp {
  id: string;
  integration_id: string;
  masked: string;
  status: string;
  rate_limit: number | null;
  last_used_at: number | null;
  create_time: number;
}

export interface IntegrationKeyPlaintextResp {
  key: IntegrationKeyResp;
  plaintext: string;
}

export interface IntegrationResp {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  quota: number | null;
  rate_limit: number | null;
  timeout: number | null;
  whitelist?: string | null;
  expire_at?: number | null;
  create_time: number;
  update_time: number;
  bound_apps: BoundAppItem[];
  keys: IntegrationKeyResp[];
}

export interface IntegrationCreateResp {
  integration: IntegrationResp;
  first_key: IntegrationKeyPlaintextResp | null;
}

export interface SandboxImageResp {
  id: string;
  name: string;
  image: string;
  description?: string | null;
  cpu?: string | null;
  memory?: string | null;
  is_default: boolean;
  enabled: boolean;
  create_time: number;
  update_time: number;
}

// ── 可观测性 · 告警 ──

export interface AlertRuleResp {
  id: string;
  rule_name: string;
  description: string | null;
  metric_type: string;
  target_error_type: string | null;
  operator: string;
  threshold: number;
  threshold_unit: string | null;
  scope: string;
  level: string;
  window_minutes: number;
  cooldown_minutes: number;
  notify_channels: string[];
  message_template: string | null;
  enabled: boolean;
  trigger_count: number;
  last_triggered_at: number | null;
  create_time: number;
  update_time: number;
}

export interface AlertRuleEvaluateResp {
  triggered: boolean;
  observed_value: number | null;
  threshold: number;
  message: string;
  record_id: string | null;
}

export interface AlertRecordResp {
  id: string;
  rule_id: string;
  rule_name: string;
  level: string;
  status: string;
  metric_type: string;
  scope: string;
  app_id: string | null;
  app_name: string | null;
  observed_value: number;
  threshold: number;
  message: string;
  triggered_at: number;
  resolved_at: number | null;
  acknowledged_at: number | null;
  acknowledged_by: string | null;
  duration_ms: number;
  create_time: number;
}

export interface AlertActiveResp {
  total: number;
  critical: number;
  warning: number;
  info: number;
  items: AlertRecordResp[];
}

export interface AlertTracePoint {
  ts: number;
  value: number | null;
}

export interface AlertTraceResp {
  record_id: string;
  metric_type: string;
  threshold: number;
  triggered_at: number;
  resolved_at: number | null;
  step_ms: number;
  points: AlertTracePoint[];
}
