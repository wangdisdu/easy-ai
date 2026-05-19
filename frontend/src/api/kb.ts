import request from "./request";
import type {
  ApiPageResp,
  ApiResp,
  KbCategoryDeletePreview,
  KbCategoryNode,
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
    category_id?: string;
    recursive?: boolean;
    parse_status?: string;
  },
) {
  return request.get<ApiPageResp<KbDocumentResp>>(
    `/api/v1/kb/${kbId}/document/page`,
    { params },
  );
}

export function uploadKbDocuments(
  kbId: string,
  files: File[],
  categoryId = "0",
) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("category_id", categoryId);
  return request.post<ApiResp<KbDocumentResp[]>>(
    `/api/v1/kb/${kbId}/document`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
}

export function moveKbDocuments(
  kbId: string,
  ids: string[],
  categoryId: string,
) {
  return request.put<ApiResp<number>>(`/api/v1/kb/${kbId}/document/move`, {
    ids,
    category_id: categoryId,
  });
}

// ── Category(树形, 单归属)────────────────────────────────────────────

export function getKbCategoryTree(kbId: string) {
  return request.get<ApiResp<KbCategoryNode[]>>(
    `/api/v1/kb/${kbId}/category/tree`,
  );
}

export function createKbCategory(
  kbId: string,
  body: { name: string; parent_id?: string },
) {
  return request.post<ApiResp<KbCategoryNode>>(
    `/api/v1/kb/${kbId}/category`,
    body,
  );
}

export function updateKbCategory(
  kbId: string,
  catId: string,
  body: { name?: string; parent_id?: string; sort?: number },
) {
  return request.put<ApiResp<KbCategoryNode>>(
    `/api/v1/kb/${kbId}/category/${catId}`,
    body,
  );
}

// confirm=false 时为 dry-run, 返回影响面不删除
export function deleteKbCategory(
  kbId: string,
  catId: string,
  confirm: boolean,
) {
  return request.delete<ApiResp<KbCategoryDeletePreview>>(
    `/api/v1/kb/${kbId}/category/${catId}`,
    { params: { confirm } },
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
