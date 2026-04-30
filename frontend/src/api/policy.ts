import request from "./request";
import type {
  ApiResp,
  PolicyOptionsResp,
  PolicyResp,
  PolicyUpdateReq,
} from "./types";

export function getToolPolicy(toolId: string) {
  return request.get<ApiResp<PolicyResp>>(`/api/v1/tool/${toolId}/policy`);
}

export function putToolPolicy(toolId: string, body: PolicyUpdateReq) {
  return request.put<ApiResp<PolicyResp>>(`/api/v1/tool/${toolId}/policy`, body);
}

export function getPolicyOptions() {
  return request.get<ApiResp<PolicyOptionsResp>>("/api/v1/policy/options");
}
