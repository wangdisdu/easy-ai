import request from "./request";
import type { ApiResp } from "./types";

export type MemoryScope = "user" | "app";
export type MemorySource = "user_explicit" | "agent_learned" | "admin_set";

export interface MemoryItem {
  id: string;
  scope: string;
  scope_id: string;
  owner_user_id?: string | null;
  memory_key: string;
  memory_value: string;
  source: string;
  create_time: number;
  update_time: number;
}

export interface MemoryAuditItem {
  id: string;
  event_type: string;
  scope: string;
  scope_id: string;
  memory_key: string;
  memory_value_before?: string | null;
  memory_value_after?: string | null;
  source: string;
  actor_user_id?: string | null;
  app_id?: string | null;
  conversation_id?: string | null;
  create_time: number;
}

export interface MemoryUpsertBody {
  scope: MemoryScope;
  scope_id: string;
  memory_key: string;
  memory_value: string;
  source?: MemorySource;
}

export function listMemories(params: {
  scope: MemoryScope;
  scope_id: string;
  limit?: number;
}) {
  return request.get<ApiResp<MemoryItem[]>>("/api/v1/memory", { params });
}

export function upsertMemory(body: MemoryUpsertBody) {
  return request.put<ApiResp<MemoryItem>>("/api/v1/memory", body);
}

export function deleteMemory(params: {
  scope: MemoryScope;
  scope_id: string;
  memory_key: string;
}) {
  return request.delete<ApiResp<boolean>>("/api/v1/memory", { params });
}

export function listMemoryAudit(params: {
  scope: MemoryScope;
  scope_id: string;
  limit?: number;
}) {
  return request.get<ApiResp<MemoryAuditItem[]>>("/api/v1/memory/audit", { params });
}

export function purgeSelfMemories() {
  return request.delete<ApiResp<number>>("/api/v1/memory/_self");
}
