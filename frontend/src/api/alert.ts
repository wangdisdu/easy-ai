import request from "./request";
import type {
  AlertActiveResp,
  AlertRecordResp,
  AlertRuleEvaluateResp,
  AlertRuleResp,
  AlertTraceResp,
  ApiPageResp,
  ApiResp,
} from "./types";

export interface AlertRuleCreateBody {
  rule_name: string;
  description?: string;
  metric_type: string;
  target_error_type?: string | null;
  operator: string;
  threshold: number;
  threshold_unit?: string | null;
  scope?: string;
  level?: string;
  window_minutes?: number;
  cooldown_minutes?: number;
  notify_channels?: string[];
  message_template?: string | null;
  enabled?: boolean;
}

export type AlertRuleUpdateBody = Partial<AlertRuleCreateBody>;

// ── 告警规则 ──

export function pageAlertRule(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  metric_type?: string;
  enabled?: boolean;
}) {
  return request.get<ApiPageResp<AlertRuleResp>>("/api/v1/observability/alert-rule/page", {
    params,
  });
}

export function getAlertRule(id: string) {
  return request.get<ApiResp<AlertRuleResp>>(`/api/v1/observability/alert-rule/${id}`);
}

export function createAlertRule(body: AlertRuleCreateBody) {
  return request.post<ApiResp<AlertRuleResp>>("/api/v1/observability/alert-rule", body);
}

export function updateAlertRule(id: string, body: AlertRuleUpdateBody) {
  return request.put<ApiResp<AlertRuleResp>>(`/api/v1/observability/alert-rule/${id}`, body);
}

export function deleteAlertRule(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/observability/alert-rule/${id}`);
}

export function enableAlertRule(id: string) {
  return request.post<ApiResp<AlertRuleResp>>(`/api/v1/observability/alert-rule/${id}/enable`);
}

export function disableAlertRule(id: string) {
  return request.post<ApiResp<AlertRuleResp>>(`/api/v1/observability/alert-rule/${id}/disable`);
}

export function evaluateAlertRule(id: string) {
  return request.post<ApiResp<AlertRuleEvaluateResp>>(
    `/api/v1/observability/alert-rule/${id}/evaluate`,
  );
}

// ── 告警记录 / 告警中心 ──

export function pageAlertRecord(params: {
  page_no: number;
  page_size: number;
  level?: string;
  status?: string;
  rule_id?: string;
  from?: number;
  to?: number;
}) {
  return request.get<ApiPageResp<AlertRecordResp>>("/api/v1/observability/alert/page", {
    params,
  });
}

export function getAlertRecord(id: string) {
  return request.get<ApiResp<AlertRecordResp>>(`/api/v1/observability/alert/${id}`);
}

export function getActiveAlerts() {
  return request.get<ApiResp<AlertActiveResp>>("/api/v1/observability/alert/active");
}

export function getAlertTrace(id: string) {
  return request.get<ApiResp<AlertTraceResp>>(`/api/v1/observability/alert/${id}/trace`);
}

export function acknowledgeAlert(id: string) {
  return request.post<ApiResp<AlertRecordResp>>(
    `/api/v1/observability/alert/${id}/acknowledge`,
  );
}

export function resolveAlert(id: string) {
  return request.post<ApiResp<AlertRecordResp>>(`/api/v1/observability/alert/${id}/resolve`);
}
