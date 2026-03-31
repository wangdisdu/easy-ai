import request from "./request";
import type { ApiPageResp, ApiResp, UserGroupResp, UserResp } from "./types";

export interface UserGroupCreateBody {
  code: string;
  name: string;
}

export interface UserGroupUpdateBody {
  name: string;
}

export interface UserGroupMemberAddBody {
  user_id: string;
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

export function listUserGroupMembers(id: string) {
  return request.get<ApiResp<UserResp[]>>(`/api/v1/user-group/${id}/member`);
}

export function addUserGroupMember(id: string, body: UserGroupMemberAddBody) {
  return request.post<ApiResp<boolean>>(`/api/v1/user-group/${id}/member`, body);
}

export function removeUserGroupMember(id: string, userId: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/user-group/${id}/member/${userId}`);
}
