import request from "./request";
import type { ApiResp, UserLoginResp, UserResp } from "./types";

export function login(account: string, passwd: string) {
  return request.post<ApiResp<UserLoginResp>>("/api/v1/auth/login", { account, passwd });
}

export function fetchMe() {
  return request.get<ApiResp<UserResp>>("/api/v1/auth/me");
}

export function logout() {
  return request.post<ApiResp<null>>("/api/v1/auth/logout");
}
