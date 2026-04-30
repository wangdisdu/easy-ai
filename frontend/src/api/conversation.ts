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

export interface HitlResponseBody {
  action: HitlAction;
  parameters?: Record<string, unknown>;
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
