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
  LocalCategoryItem,
  MappedCategory,
  RagDatasetOption,
  RagDatasetResp,
  RetrieveResp,
  SyncLogResp,
} from "./types";

// ── 知识库 ────────────────────────────────────────────────────────────

export interface KbCreateBody {
  code: string;
  name: string;
  description?: string;
}

export interface KbUpdateBody {
  name?: string;
  description?: string;
}

export function pageKb(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
}) {
  return request.get<ApiPageResp<KbResp>>("/api/v1/kb/page", { params });
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

// ── 分类 ──────────────────────────────────────────────────────────────

export function getKbCategoryTree(kbId: string) {
  return request.get<ApiResp<KbCategoryNode[]>>(`/api/v1/kb/${kbId}/category/tree`);
}

export function createKbCategory(kbId: string, body: { name: string; parent_id?: string }) {
  return request.post<ApiResp<KbCategoryNode>>(`/api/v1/kb/${kbId}/category`, body);
}

export function updateKbCategory(
  kbId: string,
  catId: string,
  body: { name?: string; parent_id?: string; sort?: number },
) {
  return request.put<ApiResp<KbCategoryNode>>(`/api/v1/kb/${kbId}/category/${catId}`, body);
}

// confirm=false 时为 dry-run, 返回影响面不删除
export function deleteKbCategory(kbId: string, catId: string, confirm: boolean) {
  return request.delete<ApiResp<KbCategoryDeletePreview>>(
    `/api/v1/kb/${kbId}/category/${catId}`,
    { params: { confirm } },
  );
}

// ── 文档 ──────────────────────────────────────────────────────────────

export function pageKbDocuments(
  kbId: string,
  params: {
    page_no: number;
    page_size: number;
    keyword?: string;
    category_id?: string;
    recursive?: boolean;
    vectorize_status?: string;
  },
) {
  return request.get<ApiPageResp<KbDocumentResp>>(`/api/v1/kb/${kbId}/document/page`, {
    params,
  });
}

export function uploadKbDocuments(kbId: string, files: File[], categoryId = "0") {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("category_id", categoryId);
  return request.post<ApiResp<KbDocumentResp[]>>(`/api/v1/kb/${kbId}/document`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function getKbDocument(kbId: string, docId: string) {
  return request.get<ApiResp<KbDocumentResp>>(`/api/v1/kb/${kbId}/document/${docId}`);
}

export function getKbDocumentByRef(ref: string) {
  return request.get<ApiResp<KbDocumentResp>>(
    `/api/v1/kb/document-by-ref/${encodeURIComponent(ref)}`,
  );
}

export function moveKbDocuments(kbId: string, ids: string[], categoryId: string) {
  return request.put<ApiResp<number>>(`/api/v1/kb/${kbId}/document/move`, {
    ids,
    category_id: categoryId,
  });
}

export function deleteKbDocuments(kbId: string, ids: string[]) {
  return request.delete<ApiResp<number>>(`/api/v1/kb/${kbId}/document`, {
    data: { ids },
  });
}

export function revectorizeKbDocument(kbId: string, docId: string) {
  return request.post<ApiResp<boolean>>(
    `/api/v1/kb/${kbId}/document/${docId}/revectorize`,
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

export function kbDocumentDownloadUrl(kbId: string, docId: string, inline = false) {
  const base = `/api/v1/kb/${kbId}/document/${docId}/download`;
  return inline ? `${base}?inline=true` : base;
}

// ── RAG 库 ────────────────────────────────────────────────────────────

export interface RagDatasetCreateBody {
  name: string;
  description?: string;
  embedding_model?: string;
  chunk_method?: string;
  parser_config?: Record<string, unknown>;
}

export interface RagDatasetUpdateBody {
  name?: string;
  description?: string;
}

export function pageRagDatasets(params: {
  page_no: number;
  page_size: number;
  keyword?: string;
  status?: string;
}) {
  return request.get<ApiPageResp<RagDatasetResp>>("/api/v1/rag-dataset/page", { params });
}

export function listRagDatasetOptions() {
  return request.get<ApiResp<RagDatasetOption[]>>("/api/v1/rag-dataset/options");
}

export function createRagDataset(body: RagDatasetCreateBody) {
  return request.post<ApiResp<RagDatasetResp>>("/api/v1/rag-dataset", body);
}

export function getRagDataset(id: string) {
  return request.get<ApiResp<RagDatasetResp>>(`/api/v1/rag-dataset/${id}`);
}

export function updateRagDataset(id: string, body: RagDatasetUpdateBody) {
  return request.put<ApiResp<RagDatasetResp>>(`/api/v1/rag-dataset/${id}`, body);
}

export function deleteRagDataset(id: string) {
  return request.delete<ApiResp<boolean>>(`/api/v1/rag-dataset/${id}`);
}

export function syncRagDataset(id: string) {
  return request.post<ApiResp<number>>(`/api/v1/rag-dataset/${id}/sync`);
}

// ── 分类映射 ──────────────────────────────────────────────────────────

export function getRagDatasetMapping(id: string) {
  return request.get<ApiResp<MappedCategory[]>>(`/api/v1/rag-dataset/${id}/mapping`);
}

export function setRagDatasetMapping(id: string, categoryIds: string[]) {
  return request.put<ApiResp<boolean>>(`/api/v1/rag-dataset/${id}/mapping`, {
    category_ids: categoryIds,
  });
}

export function listLocalCategories() {
  return request.get<ApiResp<LocalCategoryItem[]>>("/api/v1/rag-dataset/local-categories");
}

// ── 检索 ──────────────────────────────────────────────────────────────

export interface RetrieveBody {
  dataset_ids: string[];
  question: string;
  top_k?: number;
  similarity_threshold?: number;
  vector_similarity_weight?: number;
  document_ids?: string[];
  rerank_id?: string;
  keyword?: boolean;
}

export function retrieveRag(body: RetrieveBody) {
  return request.post<ApiResp<RetrieveResp>>("/api/v1/rag-dataset/retrieve", body);
}

// ── 同步日志 ──────────────────────────────────────────────────────────

export function pageSyncLogs(params: {
  page_no: number;
  page_size: number;
  log_type?: string;
  status?: string;
}) {
  return request.get<ApiPageResp<SyncLogResp>>("/api/v1/sync-log/page", { params });
}
