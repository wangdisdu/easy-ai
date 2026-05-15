import request from "./request";
import type {
  ApiPageResp,
  ApiResp,
  KbChunkResp,
  KbDocumentResp,
  KbOption,
  KbResp,
  KbRetrieveResp,
} from "./types";

export interface KbCreateBody {
  code: string;
  name: string;
  description?: string;
  // 留空时后端从 system_setting 取默认 embedding,见后端
  // app/service/kb_service.py:_resolve_embedding_model_ref
  embedding_model?: string;
  chunk_method?: string;
  parser_config?: Record<string, unknown>;
}

export interface KbUpdateBody {
  name?: string;
  description?: string;
}

export interface KbRetrieveBody {
  kb_ids: string[];
  question: string;
  top_k?: number;
  similarity_threshold?: number;
  document_ids?: string[];
  rerank_id?: string;
  keyword?: boolean;
}

// ── KB ────────────────────────────────────────────────────────────────

export function pageKb(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  status?: string;
}) {
  return request.get<ApiPageResp<KbResp>>("/api/v1/kb/page", { params });
}

export function getKbDocumentByRef(ref: string) {
  return request.get<ApiResp<KbDocumentResp>>(
    `/api/v1/kb/document-by-ref/${encodeURIComponent(ref)}`,
  );
}

export function listKbOptions() {
  return request.get<ApiResp<KbOption[]>>("/api/v1/kb/options");
}

export function createKb(body: KbCreateBody) {
  return request.post<ApiResp<KbResp>>("/api/v1/kb", body);
}

export function getKb(id: string) {
  return request.get<ApiResp<KbResp>>(`/api/v1/kb/${id}`);
}

export function updateKb(id: string, body: KbUpdateBody) {
  return request.put<ApiResp<KbResp>>(`/api/v1/kb/${id}`, body);
}

export function deleteKb(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/kb/${id}`);
}


// ── Document ──────────────────────────────────────────────────────────

export function pageKbDocuments(
  kbId: string,
  params: {
    page_no: number;
    page_size: number;
    keyword?: string;
    category?: string;
    parse_status?: string;
  },
) {
  return request.get<ApiPageResp<KbDocumentResp>>(
    `/api/v1/kb/${kbId}/document/page`,
    { params },
  );
}

export function uploadKbDocuments(kbId: string, files: File[], category?: string) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  if (category) form.append("category", category);
  return request.post<ApiResp<KbDocumentResp[]>>(
    `/api/v1/kb/${kbId}/document`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
}

export function getKbDocument(kbId: string, docId: string) {
  return request.get<ApiResp<KbDocumentResp>>(
    `/api/v1/kb/${kbId}/document/${docId}`,
  );
}

export function listKbDocumentChunks(
  kbId: string,
  docId: string,
  params: { page_no: number; page_size: number; keyword?: string },
) {
  return request.get<ApiPageResp<KbChunkResp>>(
    `/api/v1/kb/${kbId}/document/${docId}/chunk`,
    { params },
  );
}

export function reparseKbDocument(kbId: string, docId: string) {
  return request.post<ApiResp<boolean>>(
    `/api/v1/kb/${kbId}/document/${docId}/reparse`,
  );
}

export function deleteKbDocuments(kbId: string, ids: string[]) {
  return request.delete<ApiResp<number>>(`/api/v1/kb/${kbId}/document`, {
    data: { ids },
  });
}

// ── Retrieve ──────────────────────────────────────────────────────────

export function retrieveKb(body: KbRetrieveBody) {
  return request.post<ApiResp<KbRetrieveResp>>("/api/v1/kb/retrieve", body);
}
