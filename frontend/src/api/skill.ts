import request from "./request";
import type {
  ApiPageResp,
  ApiResp,
  SkillResp,
  SkillToolItem,
  SkillVersionResp,
} from "./types";

export interface SkillCreateBody {
  name: string;
  description?: string;
  category_ids?: string[];
  instruction: string;
  tools?: SkillToolItem[];
}

export interface SkillUpdateBody {
  name?: string;
  description?: string;
  category_ids?: string[];
  instruction?: string;
  tools?: SkillToolItem[];
}

export function pageSkill(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  category_id?: string;
  skill_status?: string;
}) {
  return request.get<ApiPageResp<SkillResp>>("/api/v1/skill/page", { params });
}

export function getSkill(id: string) {
  return request.get<ApiResp<SkillResp>>(`/api/v1/skill/${id}`);
}

export function createSkill(body: SkillCreateBody) {
  return request.post<ApiResp<SkillResp>>("/api/v1/skill", body);
}

export function updateSkill(id: string, body: SkillUpdateBody) {
  return request.put<ApiResp<SkillResp>>(`/api/v1/skill/${id}`, body);
}

export function deleteSkill(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/skill/${id}`);
}

export function enableSkill(id: string) {
  return request.post<ApiResp<SkillResp>>(`/api/v1/skill/${id}/enable`);
}

export function disableSkill(id: string) {
  return request.post<ApiResp<SkillResp>>(`/api/v1/skill/${id}/disable`);
}

export function publishSkill(id: string, body: { version: string; version_note?: string }) {
  return request.post<ApiResp<SkillVersionResp>>(`/api/v1/skill/${id}/publish`, body);
}

export function listSkillVersions(id: string) {
  return request.get<ApiResp<SkillVersionResp[]>>(`/api/v1/skill/${id}/version`);
}
