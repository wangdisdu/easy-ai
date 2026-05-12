import request from "./request";
import type { ApiResp } from "./types";

export interface PermissionOption {
  code: string;
  label: string;
  group: string;
  description: string;
}

export function listPermissionOptions() {
  return request.get<ApiResp<PermissionOption[]>>("/api/v1/permission/options");
}
