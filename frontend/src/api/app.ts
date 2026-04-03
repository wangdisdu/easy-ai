import request from "./request";
import type { ApiPageResp, ApiResp, AppLogResp, AppResp, AppRunResp, AppVersionResp } from "./types";

const TEST_APP_REQUEST_TIMEOUT = 300000;

export interface AppCreateBody {
  name: string;
  description?: string;
  app_type: string;
  provider_id?: string;
  model_id?: string;
  model_setting?: Record<string, unknown>;
  app_config?: Record<string, unknown>;
  access_scope?: string;
  rate_limit?: number;
  enable_log?: boolean;
  tool_ids?: string[];
  skill_ids?: string[];
}

export interface AppUpdateBody {
  name?: string;
  description?: string;
  provider_id?: string;
  model_id?: string;
  model_setting?: Record<string, unknown>;
  app_config?: Record<string, unknown>;
  access_scope?: string;
  rate_limit?: number;
  enable_log?: boolean;
  tool_ids?: string[];
  skill_ids?: string[];
}

export interface AppTestBody {
  messages?: Array<{ role: string; content: string }>;
  inputs?: Record<string, unknown>;
  variables?: Record<string, unknown>;
  query?: string;
}

export function pageApp(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  app_type?: string;
  app_status?: string;
}) {
  return request.get<ApiPageResp<AppResp>>("/api/v1/app/page", { params });
}

export function getApp(id: string) {
  return request.get<ApiResp<AppResp>>(`/api/v1/app/${id}`);
}

export function createApp(body: AppCreateBody) {
  return request.post<ApiResp<AppResp>>("/api/v1/app", body);
}

export function updateApp(id: string, body: AppUpdateBody) {
  return request.put<ApiResp<AppResp>>(`/api/v1/app/${id}`, body);
}

export function deleteApp(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/app/${id}`);
}

export function publishApp(id: string, body: { version: string; version_note?: string }) {
  return request.post<ApiResp<AppVersionResp>>(`/api/v1/app/${id}/publish`, body);
}

export function listAppVersions(id: string) {
  return request.get<ApiResp<AppVersionResp[]>>(`/api/v1/app/${id}/version`);
}

export function listAppLogs(id: string, limit = 100) {
  return request.get<ApiResp<AppLogResp[]>>(`/api/v1/app/${id}/log`, {
    params: { limit },
  });
}

export function offlineApp(id: string) {
  return request.post<ApiResp<AppResp>>(`/api/v1/app/${id}/offline`);
}

export function testApp(id: string, body: AppTestBody) {
  return request.post<ApiResp<AppRunResp>>(`/api/v1/open/app/${id}/test`, body, {
    timeout: TEST_APP_REQUEST_TIMEOUT,
  });
}
