import request from "./request";
import type {
  ApiResp,
  AppHealthRow,
  ErrorAppRow,
  ModelTokenRow,
  OverviewStats,
  RecentRequestRow,
  TrendResp,
} from "./types";

export interface RangeParams {
  from?: number;
  to?: number;
}

export function getOverviewStats(params: RangeParams = {}) {
  return request.get<ApiResp<OverviewStats>>("/api/v1/observability/stats", { params });
}

export function getOverviewTrend(params: RangeParams & { top?: number } = {}) {
  return request.get<ApiResp<TrendResp>>("/api/v1/observability/trend", { params });
}

export function getTokensByModel(params: RangeParams = {}) {
  return request.get<ApiResp<ModelTokenRow[]>>("/api/v1/observability/tokens-by-model", { params });
}

export function getAppHealth(
  params: RangeParams & { sort?: "calls" | "success_rate" | "feedback_rate"; limit?: number } = {}
) {
  return request.get<ApiResp<AppHealthRow[]>>("/api/v1/observability/app-health", { params });
}

export function getErrorsByApp(params: RangeParams & { limit?: number } = {}) {
  return request.get<ApiResp<ErrorAppRow[]>>("/api/v1/observability/errors-by-app", { params });
}

export function getRecentRequests(params: { limit?: number } = {}) {
  return request.get<ApiResp<RecentRequestRow[]>>("/api/v1/observability/recent-requests", {
    params,
  });
}
