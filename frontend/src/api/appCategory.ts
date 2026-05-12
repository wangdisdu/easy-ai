import request from "./request";
import type { ApiPageResp, ApiResp, AppCategoryResp } from "./types";

export interface AppCategoryCreateBody {
  code: string;
  name: string;
  description?: string | null;
  sort_order?: number;
}

export interface AppCategoryUpdateBody {
  name?: string;
  description?: string | null;
  sort_order?: number;
}

export function pageAppCategory(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
}) {
  return request.get<ApiPageResp<AppCategoryResp>>("/api/v1/app-category/page", { params });
}

export function listAppCategory() {
  return request.get<ApiResp<AppCategoryResp[]>>("/api/v1/app-category/list");
}

export function getAppCategory(id: string) {
  return request.get<ApiResp<AppCategoryResp>>(`/api/v1/app-category/${id}`);
}

export function createAppCategory(body: AppCategoryCreateBody) {
  return request.post<ApiResp<AppCategoryResp>>("/api/v1/app-category", body);
}

export function updateAppCategory(id: string, body: AppCategoryUpdateBody) {
  return request.put<ApiResp<AppCategoryResp>>(`/api/v1/app-category/${id}`, body);
}

export function deleteAppCategory(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/app-category/${id}`);
}
