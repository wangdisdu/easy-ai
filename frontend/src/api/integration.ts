import request from "./request";
import type {
  ApiPageResp,
  ApiResp,
  BoundAppItem,
  IntegrationCreateResp,
  IntegrationKeyPlaintextResp,
  IntegrationKeyResp,
  IntegrationResp,
} from "./types";

export interface IntegrationCreateBody {
  name: string;
  description?: string | null;
  // 三态:null/undefined = 留空继承全局默认, 0 = 显式不限, >0 = 具体阈值
  quota?: number | null;
  rate_limit?: number | null;
  timeout?: number | null;
  whitelist?: string | null;
  expire_at?: number | null;
  bound_apps?: BoundAppItem[];
}

export interface IntegrationUpdateBody {
  name?: string;
  description?: string | null;
  quota?: number | null;
  rate_limit?: number | null;
  timeout?: number | null;
  whitelist?: string | null;
  expire_at?: number | null;
  // null = 不修改绑定, [] = 解绑全部
  bound_apps?: BoundAppItem[] | null;
}

export interface IntegrationKeyUpdateBody {
  rate_limit?: number | null;
  rate_limit_inherit?: boolean;
  status?: "active" | "disabled";
}

export function pageIntegration(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  status?: "active" | "disabled";
}) {
  return request.get<ApiPageResp<IntegrationResp>>("/api/v1/integration/page", {
    params,
  });
}

export function getIntegration(id: string) {
  return request.get<ApiResp<IntegrationResp>>(`/api/v1/integration/${id}`);
}

export function createIntegration(body: IntegrationCreateBody) {
  return request.post<ApiResp<IntegrationCreateResp>>("/api/v1/integration", body);
}

export function updateIntegration(id: string, body: IntegrationUpdateBody) {
  return request.put<ApiResp<IntegrationResp>>(`/api/v1/integration/${id}`, body);
}

export function deleteIntegration(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/integration/${id}`);
}

export function setIntegrationStatus(id: string, status: "active" | "disabled") {
  return request.put<ApiResp<IntegrationResp>>(`/api/v1/integration/${id}/status`, {
    status,
  });
}

export function createIntegrationKey(id: string) {
  return request.post<ApiResp<IntegrationKeyPlaintextResp>>(
    `/api/v1/integration/${id}/key`,
  );
}

export function updateIntegrationKey(
  id: string,
  keyId: string,
  body: IntegrationKeyUpdateBody,
) {
  return request.put<ApiResp<IntegrationKeyResp>>(
    `/api/v1/integration/${id}/key/${keyId}`,
    body,
  );
}

export function resetIntegrationKey(id: string, keyId: string) {
  return request.post<ApiResp<IntegrationKeyPlaintextResp>>(
    `/api/v1/integration/${id}/key/${keyId}/reset`,
  );
}

export function deleteIntegrationKey(id: string, keyId: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/integration/${id}/key/${keyId}`);
}
