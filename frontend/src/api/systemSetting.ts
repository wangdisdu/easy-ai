import request from "./request";
import type { ApiResp } from "./types";

export interface SystemSettingResp {
  key: string;
  value: string | null;
  update_time?: number | null;
}

// 已知的 AI 基础设施默认指针 key,与后端 system_setting_service.py 同名常量
export const AI_DEFAULT_EMBEDDING_KEY = "ai.default.embedding_model_id";
export const AI_DEFAULT_RERANK_KEY = "ai.default.rerank_model_id";
export const AI_DEFAULT_VISION_KEY = "ai.default.vision_model_id";

export function listSystemSettings() {
  return request.get<ApiResp<SystemSettingResp[]>>("/api/v1/system-setting");
}

export function getSystemSetting(key: string) {
  return request.get<ApiResp<SystemSettingResp>>(
    `/api/v1/system-setting/${encodeURIComponent(key)}`,
  );
}

export function setSystemSetting(key: string, value: string | null) {
  return request.put<ApiResp<SystemSettingResp>>(
    `/api/v1/system-setting/${encodeURIComponent(key)}`,
    { value },
  );
}
