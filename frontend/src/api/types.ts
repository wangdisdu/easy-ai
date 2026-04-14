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
  category?: string | null;
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
