import request from "./request";
import type { ApiPageResp, ApiResp, UserResp } from "./types";

export interface UserCreateBody {
  account: string;
  passwd: string;
  email?: string | null;
  name?: string | null;
  phone?: string | null;
  department?: string | null;
  role_ids?: string[];
}

export interface UserUpdateBody {
  email?: string | null;
  name?: string | null;
  phone?: string | null;
  department?: string | null;
  role_ids?: string[];
}

export function pageUser(params: { page_no: number; page_size: number; keyword?: string }) {
  return request.get<ApiPageResp<UserResp>>("/api/v1/user/page", { params });
}

export function getUser(userId: string) {
  return request.get<ApiResp<UserResp>>(`/api/v1/user/${userId}`);
}

export function createUser(body: UserCreateBody) {
  return request.post<ApiResp<UserResp>>("/api/v1/user", body);
}

export function updateUser(userId: string, body: UserUpdateBody) {
  return request.put<ApiResp<UserResp>>(`/api/v1/user/${userId}`, body);
}

export function deleteUser(userId: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/user/${userId}`);
}
