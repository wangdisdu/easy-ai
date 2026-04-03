import request from "./request";
import type {
  ApiPageResp,
  ApiResp,
  BuiltinToolResp,
  McpDiscoveredTool,
  McpServerResp,
  ToolResp,
} from "./types";

// ── Tool ──

export interface ToolCreateBody {
  source: string;
  tool_name: string;
  description: string;
  parameters: Record<string, unknown>;
  tool_group?: string;
  risk_level?: string;
  mcp_server_id?: string;
  api_config?: Record<string, unknown>;
}

export interface ToolUpdateBody {
  tool_name?: string;
  description?: string;
  parameters?: Record<string, unknown>;
  tool_group?: string;
  risk_level?: string;
  api_config?: Record<string, unknown>;
}

export function listBuiltinTools() {
  return request.get<ApiResp<BuiltinToolResp[]>>("/api/v1/tool/builtin");
}

export function pageTool(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  source?: string;
  tool_status?: string;
}) {
  return request.get<ApiPageResp<ToolResp>>("/api/v1/tool/page", { params });
}

export function getTool(id: string) {
  return request.get<ApiResp<ToolResp>>(`/api/v1/tool/${id}`);
}

export function createTool(body: ToolCreateBody) {
  return request.post<ApiResp<ToolResp>>("/api/v1/tool", body);
}

export function updateTool(id: string, body: ToolUpdateBody) {
  return request.put<ApiResp<ToolResp>>(`/api/v1/tool/${id}`, body);
}

export function deleteTool(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/tool/${id}`);
}

export function enableTool(id: string) {
  return request.post<ApiResp<ToolResp>>(`/api/v1/tool/${id}/enable`);
}

export function disableTool(id: string) {
  return request.post<ApiResp<ToolResp>>(`/api/v1/tool/${id}/disable`);
}

// ── MCP Server ──

export interface McpDiscoverBody {
  transport: string;
  endpoint_url: string;
  headers?: Record<string, unknown>;
}

export interface McpServerCreateBody {
  server_name: string;
  transport: string;
  endpoint_url: string;
  headers?: Record<string, unknown>;
  remark?: string;
}

export interface McpServerUpdateBody {
  server_name?: string;
  transport?: string;
  endpoint_url?: string;
  headers?: Record<string, unknown>;
  remark?: string;
  server_status?: string;
}

export function discoverMcpTools(body: McpDiscoverBody) {
  return request.post<ApiResp<McpDiscoveredTool[]>>("/api/v1/mcp-server/discover", body);
}

export function listMcpServers() {
  return request.get<ApiResp<McpServerResp[]>>("/api/v1/mcp-server");
}

export function createMcpServer(body: McpServerCreateBody) {
  return request.post<ApiResp<McpServerResp>>("/api/v1/mcp-server", body);
}

export function getMcpServer(id: string) {
  return request.get<ApiResp<McpServerResp>>(`/api/v1/mcp-server/${id}`);
}

export function updateMcpServer(id: string, body: McpServerUpdateBody) {
  return request.put<ApiResp<McpServerResp>>(`/api/v1/mcp-server/${id}`, body);
}

export function deleteMcpServer(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/mcp-server/${id}`);
}
