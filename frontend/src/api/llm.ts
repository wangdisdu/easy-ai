import request from "./request";
import type { ApiPageResp, ApiResp, LlmModelResp, LlmProviderResp } from "./types";

// ── Provider ──

export interface LlmModelItem {
  model: string;
  model_type: string;
  max_input_tokens?: number | null;
}

export interface LlmProviderCreateBody {
  name: string;
  provider_type: string;
  base_url: string;
  api_key?: string | null;
  models?: LlmModelItem[];
}

export interface LlmProviderUpdateBody {
  name?: string;
  provider_type?: string;
  base_url?: string;
  api_key?: string | null;
}

export function pageProvider(params: { page_no: number; page_size: number; keyword?: string }) {
  return request.get<ApiPageResp<LlmProviderResp>>("/api/v1/llm/provider/page", { params });
}

export function getProvider(id: string) {
  return request.get<ApiResp<LlmProviderResp>>(`/api/v1/llm/provider/${id}`);
}

export function createProvider(body: LlmProviderCreateBody) {
  return request.post<ApiResp<LlmProviderResp>>("/api/v1/llm/provider", body);
}

export function updateProvider(id: string, body: LlmProviderUpdateBody) {
  return request.put<ApiResp<LlmProviderResp>>(`/api/v1/llm/provider/${id}`, body);
}

export function deleteProvider(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/llm/provider/${id}`);
}

export function testProviderConnection(id: string) {
  return request.post<ApiResp<LlmProviderResp>>(`/api/v1/llm/provider/${id}/test`);
}

export function getProviderAvailableModels(id: string) {
  return request.get<ApiResp<string[]>>(`/api/v1/llm/provider/${id}/available-models`);
}

// ── Model ──

export interface LlmModelCreateBody {
  model: string;
  model_type: string;
  max_input_tokens?: number | null;
}

export interface LlmModelUpdateBody {
  model?: string;
  model_type?: string;
  max_input_tokens?: number | null;
}

export function createModel(providerId: string, body: LlmModelCreateBody) {
  return request.post<ApiResp<LlmModelResp>>(`/api/v1/llm/provider/${providerId}/model`, body);
}

export function updateModel(id: string, body: LlmModelUpdateBody) {
  return request.put<ApiResp<LlmModelResp>>(`/api/v1/llm/model/${id}`, body);
}

export function enableModel(id: string) {
  return request.post<ApiResp<LlmModelResp>>(`/api/v1/llm/model/${id}/enable`);
}

export function disableModel(id: string) {
  return request.post<ApiResp<LlmModelResp>>(`/api/v1/llm/model/${id}/disable`);
}

export function deleteModel(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/llm/model/${id}`);
}

export function getPredefinedProviders() {
  return request.get<ApiResp<Record<string, string>>>("/api/v1/llm/provider/predefined");
}
