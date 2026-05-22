// 告警模块共享的枚举标签与下拉选项。与后端 alert_rule_model / alert_evaluator 对齐。

export interface Option {
  value: string;
  label: string;
}

// 监控指标。unit 为该指标的固定阈值单位(由指标决定,表单据此自动填充)。
export const METRIC_OPTIONS: Array<Option & { unit: string }> = [
  { value: "success_rate", label: "成功率", unit: "%" },
  { value: "error_rate", label: "错误率", unit: "%" },
  { value: "p95_latency", label: "P95 延迟", unit: "ms" },
  { value: "request_latency", label: "请求延迟", unit: "ms" },
  { value: "token_usage_daily", label: "Token 消耗", unit: "tokens" },
  // 计数类指标无阈值单位(threshold_unit 存 null)
  { value: "consecutive_failures", label: "连续失败", unit: "" },
  { value: "negative_feedback_rate", label: "负面反馈率", unit: "%" },
  { value: "llm_error_count_by_type", label: "LLM 错误次数", unit: "" },
];

export const OPERATOR_OPTIONS: Option[] = [
  { value: "lt", label: "< 小于" },
  { value: "lte", label: "≤ 小于等于" },
  { value: "gt", label: "> 大于" },
  { value: "gte", label: "≥ 大于等于" },
  { value: "eq", label: "= 等于" },
];

export const SCOPE_OPTIONS: Option[] = [
  { value: "global", label: "全局汇总" },
  { value: "per_app", label: "按 AI 应用" },
  { value: "per_request", label: "按单次请求" },
];

export const LEVEL_OPTIONS: Option[] = [
  { value: "critical", label: "严重" },
  { value: "warning", label: "警告" },
  { value: "info", label: "通知" },
];

// LLM 错误类型(metric=llm_error_count_by_type 时可选;留空=任意错误)
export const ERROR_TYPE_OPTIONS: Option[] = [
  { value: "quota_exhausted", label: "余额耗尽" },
  { value: "rate_limited", label: "限流" },
  { value: "auth_failed", label: "认证失败" },
  { value: "model_not_found", label: "模型不存在" },
  { value: "context_length_exceeded", label: "上下文超长" },
  { value: "content_filter", label: "内容审查拦截" },
  { value: "invalid_request", label: "请求参数错误" },
  { value: "provider_server_error", label: "供应商服务错误" },
  { value: "service_unavailable", label: "服务不可用" },
  { value: "timeout", label: "请求超时" },
  { value: "network_error", label: "网络错误" },
  { value: "response_invalid", label: "响应格式异常" },
  { value: "model_not_configured", label: "模型未配置" },
];

function toMap(opts: Option[]): Record<string, string> {
  return Object.fromEntries(opts.map((o) => [o.value, o.label]));
}

export const METRIC_LABEL = toMap(METRIC_OPTIONS);
export const SCOPE_LABEL = toMap(SCOPE_OPTIONS);
export const LEVEL_LABEL = toMap(LEVEL_OPTIONS);
export const ERROR_TYPE_LABEL = toMap(ERROR_TYPE_OPTIONS);

export const OPERATOR_SYMBOL: Record<string, string> = {
  lt: "<",
  lte: "≤",
  gt: ">",
  gte: "≥",
  eq: "=",
};

export const STATUS_LABEL: Record<string, string> = {
  firing: "触发中",
  acknowledged: "已确认",
  resolved: "已恢复",
};

export function metricUnit(metric: string): string {
  return METRIC_OPTIONS.find((m) => m.value === metric)?.unit ?? "";
}

/** 把毫秒时长格式化为「2h 5m」「3m 12s」「45s」。 */
export function formatDuration(ms: number): string {
  if (ms <= 0) return "0s";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
