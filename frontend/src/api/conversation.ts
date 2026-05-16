import request from "./request";
import { fetchSSE, type SSEOptions } from "./sse";
import type {
  ApiPageResp,
  ApiResp,
  ConversationMessageResp,
  ConversationResp,
} from "./types";

export function pageConversation(params: {
  page_no: number;
  page_size: number;
  status?: string;
}) {
  return request.get<ApiPageResp<ConversationResp>>("/api/v1/conversation/page", { params });
}

export function createConversation(body: { app_id: string }) {
  return request.post<ApiResp<ConversationResp>>("/api/v1/conversation", body);
}

export function getConversation(id: string) {
  return request.get<ApiResp<ConversationResp>>(`/api/v1/conversation/${id}`);
}

export function updateConversation(id: string, body: { title?: string; status?: string }) {
  return request.put<ApiResp<ConversationResp>>(`/api/v1/conversation/${id}`, body);
}

export function deleteConversation(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/conversation/${id}`);
}

export function listMessages(conversationId: string) {
  return request.get<ApiResp<ConversationMessageResp[]>>(
    `/api/v1/conversation/${conversationId}/message`,
  );
}

export function sendMessageStream(
  conversationId: string,
  body: { content: string },
  options: Omit<SSEOptions, "signal">,
): { abort: () => void } {
  const controller = new AbortController();
  fetchSSE(
    `/api/v1/conversation/${conversationId}/message/stream`,
    body as Record<string, unknown>,
    { ...options, signal: controller.signal },
  ).catch((err: unknown) => {
    if (err instanceof Error && err.name === "AbortError") return;
    options.onError?.(err instanceof Error ? err : new Error(String(err)));
  });
  return { abort: () => controller.abort() };
}

export type HitlAction = "confirm" | "modify" | "reject";

/** 协议续跑请求体：outcome 二选一 selected / cancelled。 */
export interface HitlResponseBody {
  hitl_id?: string;
  /** 被中断 run 的 run_id（从 hitl.required 事件信封捕获），供审计追溯链接 */
  parent_run_id?: string;
  outcome:
    | { selected: { option_id: HitlAction; parameters?: Record<string, unknown> } }
    | { cancelled: true };
}

/** 由 action(+参数) 构造协议 outcome 请求体。 */
export function buildHitlBody(
  action: HitlAction,
  parameters?: Record<string, unknown>,
  parentRunId?: string,
): HitlResponseBody {
  const selected: { option_id: HitlAction; parameters?: Record<string, unknown> } = {
    option_id: action,
  };
  if (action === "modify" && parameters) selected.parameters = parameters;
  const body: HitlResponseBody = { outcome: { selected } };
  if (parentRunId) body.parent_run_id = parentRunId;
  return body;
}

export function respondHitlStream(
  conversationId: string,
  hitlId: string,
  body: HitlResponseBody,
  options: Omit<SSEOptions, "signal">,
): { abort: () => void } {
  const controller = new AbortController();
  fetchSSE(
    `/api/v1/conversation/${conversationId}/hitl/${hitlId}/respond`,
    body as unknown as Record<string, unknown>,
    { ...options, signal: controller.signal },
  ).catch((err: unknown) => {
    if (err instanceof Error && err.name === "AbortError") return;
    options.onError?.(err instanceof Error ? err : new Error(String(err)));
  });
  return { abort: () => controller.abort() };
}
