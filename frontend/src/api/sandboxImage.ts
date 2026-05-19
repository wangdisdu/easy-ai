import request from "./request";
import type { ApiPageResp, ApiResp, SandboxImageResp, SandboxViewResp } from "./types";

/** 取某会话沙盒 noVNC 桌面的签名访问信息;ready=false 表示沙盒尚未创建。 */
export function getSandboxView(threadId: string) {
  return request.get<ApiResp<SandboxViewResp>>("/api/v1/sandbox-view", {
    params: { thread_id: threadId },
  });
}

export interface SandboxImageCreateBody {
  name: string;
  image: string;
  description?: string | null;
  cpu?: string | null;
  memory?: string | null;
  is_default?: boolean;
  enabled?: boolean;
}

export interface SandboxImageUpdateBody {
  name?: string;
  image?: string;
  description?: string | null;
  cpu?: string | null;
  memory?: string | null;
  is_default?: boolean;
  enabled?: boolean;
}

export function pageSandboxImage(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
}) {
  return request.get<ApiPageResp<SandboxImageResp>>("/api/v1/sandbox-image/page", { params });
}

/** 只返回启用的镜像,供应用配置选择。 */
export function listSandboxImage() {
  return request.get<ApiResp<SandboxImageResp[]>>("/api/v1/sandbox-image/list");
}

export function getSandboxImage(id: string) {
  return request.get<ApiResp<SandboxImageResp>>(`/api/v1/sandbox-image/${id}`);
}

export function createSandboxImage(body: SandboxImageCreateBody) {
  return request.post<ApiResp<SandboxImageResp>>("/api/v1/sandbox-image", body);
}

export function updateSandboxImage(id: string, body: SandboxImageUpdateBody) {
  return request.put<ApiResp<SandboxImageResp>>(`/api/v1/sandbox-image/${id}`, body);
}

export function deleteSandboxImage(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/sandbox-image/${id}`);
}
