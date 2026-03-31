import request from "./request";
import type { ApiPageResp, ApiResp, RoleResp, UserResp } from "./types";

export interface RoleCreateBody {
  code: string;
  name: string;
  permissions: string[];
}

export interface RoleUpdateBody {
  name: string;
  permissions: string[];
}

export function pageRole(params: { page_no: number; page_size: number; keyword?: string }) {
  return request.get<ApiPageResp<RoleResp>>("/api/v1/role/page", { params });
}

export function listRole() {
  return request.get<ApiResp<RoleResp[]>>("/api/v1/role");
}

export function getRole(id: string) {
  return request.get<ApiResp<RoleResp>>(`/api/v1/role/${id}`);
}

export function createRole(body: RoleCreateBody) {
  return request.post<ApiResp<RoleResp>>("/api/v1/role", body);
}

export function updateRole(id: string, body: RoleUpdateBody) {
  return request.put<ApiResp<RoleResp>>(`/api/v1/role/${id}`, body);
}

export function deleteRole(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/role/${id}`);
}

export function listRoleUsers(id: string) {
  return request.get<ApiResp<UserResp[]>>(`/api/v1/role/${id}/user`);
}
