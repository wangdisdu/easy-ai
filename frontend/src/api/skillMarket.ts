import request from "./request";
import type { ApiResp, MarketSearchResp, MarketSkill, SkillResp } from "./types";

export function searchMarket(q?: string) {
  return request.get<ApiResp<MarketSearchResp>>("/api/v1/skill-market/search", {
    params: q ? { q } : {},
  });
}

export function inspectMarketSkill(slug: string) {
  return request.get<ApiResp<MarketSkill>>(`/api/v1/skill-market/${encodeURIComponent(slug)}`);
}

export function translateMarketText(text: string) {
  return request.post<ApiResp<{ text: string }>>("/api/v1/skill-market/translate", { text });
}

export interface InstallMarketBody {
  slug: string;
  visibility: "group" | "system";
  skill_name?: string;
}

export function installMarketSkill(body: InstallMarketBody) {
  return request.post<ApiResp<SkillResp>>("/api/v1/skill-market/install", body);
}
