import request from "./request";
import type { ApiPageResp, ApiResp, UserGroupResp } from "./types";

export interface UserGroupCreateBody {
  code: string;
  name: string;
}

export interface UserGroupUpdateBody {
  name: string;
}

export function pageUserGroup(params: { page_no: number; page_size: number; keyword?: string }) {
  return request.get<ApiPageResp<UserGroupResp>>("/api/v1/user-group/page", { params });
}

export function getUserGroup(id: string) {
  return request.get<ApiResp<UserGroupResp>>(`/api/v1/user-group/${id}`);
}

export function createUserGroup(body: UserGroupCreateBody) {
  return request.post<ApiResp<UserGroupResp>>("/api/v1/user-group", body);
}

export function updateUserGroup(id: string, body: UserGroupUpdateBody) {
  return request.put<ApiResp<UserGroupResp>>(`/api/v1/user-group/${id}`, body);
}

export function deleteUserGroup(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/user-group/${id}`);
}
