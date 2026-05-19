import request from "./request";
import type { ApiResp, SandboxInstanceResp, SandboxViewResp } from "./types";

/** 列出 OpenSandbox server 当前所有沙盒实例(包含 backend 进程不知道的孤儿)。 */
export function listSandboxInstances() {
  return request.get<ApiResp<SandboxInstanceResp[]>>("/api/v1/sandbox-instance");
}

/** 手动停止某沙盒。 */
export function killSandboxInstance(sandboxId: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/sandbox-instance/${sandboxId}`);
}

/** 取某沙盒的 noVNC 桌面 URL(非桌面镜像会 ready=true 但 iframe 加载失败,前端按经验提示)。 */
export function getSandboxInstanceView(sandboxId: string) {
  return request.get<ApiResp<SandboxViewResp>>(
    `/api/v1/sandbox-instance/${sandboxId}/view`,
  );
}
