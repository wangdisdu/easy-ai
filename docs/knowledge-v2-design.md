# 知识库管理重构设计(v2)

> 状态:设计已评审,实施中
> 日期:2026-05-22
> 取代:v1 的「知识库 ≡ RAGFlow Dataset(1:1)」模型相关设计

## 1. 背景与动机

v1 中知识库与 RAGFlow Dataset 1:1 绑定(`tb_kb.ragflow_dataset_id`),存在三个问题:

- **embedding 不可改**:模型落库后不可切换,选错只能删除整个知识库。
- **无独立真相源**:文档原文只存在 RAGFlow,easy-ai 无法独立重新向量化或迁移。
- **多源集成无落点**:文件 / API / Ones 等多源知识集成缺少 staging 层。

v2 引入**三层解耦**:组织层(知识库 / 分类 / 文档)与向量化层(RAG 库)分离,中间通过映射连接。**easy-ai 成为文档真相源**,RAGFlow 退化为下游索引。

## 2. 概念模型

```
┌─ 组织层(easy-ai 真相源)──────┐      ┌─ 向量化层(RAGFlow)─┐
│  知识库 ── 分类 ── 文档       │  映射  │      RAG 库          │
│  (原文存 blob)               │ ─────▶ │  (embedding/分块)   │
└──────────────────────────────┘  N:1   └─────────────────────┘
        ▲ 知识集成(源→知识库)          ▲ 知识向量化(知识库→RAGFlow)
```

- **知识库**:纯组织单元。
- **分类**:知识库下单层扁平分组。
- **文档**:属于一个知识库 + 一个分类,原文存 easy-ai blob 存储。
- **RAG 库**:对应一个 RAGFlow Dataset,持有 embedding / 分块配置。
- **映射**:分类 → RAG 库,**N:1 互斥** —— 一个分类只能映射一个 RAG 库;多分类(可跨知识库)可汇入同一 RAG 库;一篇文档因只属于一个分类,故只落一个 RAG 库,不存在跨库复制。

两个数据流阶段:

- **知识集成**:外部源 → 知识库(本轮仅实现文件上传)。
- **知识向量化**:知识库分类内容 → RAG 库(RAGFlow)。

## 3. 文件处理策略

本轮**不做 file→Markdown 转换**:easy-ai 存原始二进制文件,向量化时把原文件推给 RAGFlow,复用其 DeepDoc 解析。未来 Ones / API 连接器送来的本就是 Markdown,届时两种形态并存(RAGFlow 接受 `.md` 文件)。

## 4. 数据模型

### 4.1 `tb_kb`(改 — 退化为纯组织层)

- **删除**:`ragflow_dataset_id`、`embedding_model`、`chunk_method`、`parser_config`、`doc_count`、`chunk_count`、`last_synced_at`、`status`。
- **保留**:`id`、`code`、`name`、`description`、审计列。

### 4.2 `tb_kb_category`(基本不变)

单层使用(`parent_id` 恒为 0);树形基建保留不用。

### 4.3 `tb_kb_document`(改)

- **新增**:`storage_path VARCHAR(512)`(blob 引用)、`rag_dataset_id BIGINT NULL`(冗余,文档所属 RAG 库,由分类映射推导并固化,便于查询与改映射)。
- **重命名**:`parse_status` → `vectorize_status`,取值 `not_mapped` / `pending` / `parsing` / `done` / `error`。
- **保留**:`ref`、`kb_id`、`name`、`format`、`size_bytes`、`category_id`、`source_type`、`source_meta`、`ragflow_doc_id`、`chunks_count`、`error_message`、`parse_progress` 系列、审计列。
- **删除**:`category`(旧字符串列)。

### 4.4 `tb_rag_dataset`(新)

`id`、`name`、`description`、`ragflow_dataset_id`、`embedding_model`、`chunk_method`、`parser_config`、`doc_count`、`chunk_count`、`status`(`creating` / `ready` / `syncing` / `error`)、`last_synced_at`、审计列。

### 4.5 `tb_kb_category_mapping`(新)

`id`、`category_id BIGINT`(**UNIQUE** —— 互斥保证)、`rag_dataset_id BIGINT`、`status`、审计列。

### 4.6 `tb_sync_log`(新)

`id`、`log_type`(`integration` / `vectorization`)、`source_type`、`source_name`、`target_kb_id NULL`、`target_dataset_id NULL`、`docs_added`、`docs_updated`、`docs_deleted`、`chunks_created`、`status`(`success` / `failed` / `partial` / `processing`)、`duration_ms`、`detail TEXT`、`create_time`、`create_user`。

## 5. Blob 存储

新配置 `kb_storage_path`(默认 `./data/kb_storage`)。`app/integration/kb_storage.py` 提供 `save / load / delete / exists`,本地文件系统实现,路径 `{root}/{kb_id}/{doc_id}{ext}`。抽象接口,后续可换 S3 / MinIO。

## 6. 后端服务与 API

### 6.1 服务

| 服务 | 职责 |
|---|---|
| `kb_service` / `kb_category_service` / `kb_document_service` | 组织层 CRUD,不再调用 RAGFlow;上传 = 存 blob + 写记录 + 写集成日志 |
| `rag_dataset_service` | RAG 库 CRUD,封装 RAGFlow dataset API |
| `mapping_service` | 映射增删、互斥校验、触发向量化 |
| `vectorization_service` | 推原文进 RAGFlow、轮询进度、写向量化日志 |
| `kb_retrieve_service` | 面向 RAG 库检索(签名 `kb_ids` → `dataset_ids`) |
| `sync_log_service` | 日志分页查询 |

### 6.2 API 端点

- **知识库**:`GET /api/v1/kb/page`、`POST /api/v1/kb`、`GET|PUT|DELETE /api/v1/kb/{id}`、`GET /api/v1/kb/options`
- **分类**:`GET /api/v1/kb/{kbId}/category/tree`、`POST /api/v1/kb/{kbId}/category`、`PUT|DELETE /api/v1/kb/{kbId}/category/{id}`
- **文档**:`GET /api/v1/kb/{kbId}/document/page`、`POST /api/v1/kb/{kbId}/document`(上传存 blob)、`GET /api/v1/kb/{kbId}/document/{id}`、`DELETE /api/v1/kb/{kbId}/document`(批量)、`PUT /api/v1/kb/{kbId}/document/move`、`GET .../{id}/download`、`GET .../{id}/chunk`、`POST .../{id}/revectorize`
- **RAG 库**:`GET /api/v1/rag-dataset/page`、`POST /api/v1/rag-dataset`、`GET|PUT|DELETE /api/v1/rag-dataset/{id}`、`GET /api/v1/rag-dataset/options`、`POST /api/v1/rag-dataset/{id}/sync`、`POST /api/v1/rag-dataset/retrieve`
- **映射**:`GET /api/v1/rag-dataset/{id}/mapping`、`PUT /api/v1/rag-dataset/{id}/mapping`(整体设置该库映射的分类集合)
- **同步日志**:`GET /api/v1/sync-log/page?log_type=`

### 6.3 权限

复用 `PERM.KB_VIEW` / `KB_EDIT` / `KB_PUBLISH`。RAG 库 CRUD + 映射 = `KB_EDIT`;触发向量化 / 同步 = `KB_PUBLISH`。

## 7. 异步 worker

`kb_status_poller` 改造为**向量化 worker**:

- 扫 `vectorize_status ∈ {pending, parsing}` 的文档。
- `pending`:上传原文件到映射 RAG 库的 RAGFlow dataset + 触发 parse → `parsing`。
- `parsing`:轮询 RAGFlow 进度,回填 `parse_progress` / `chunks_count`,完成 → `done`。
- 阶段结束写一条 `vectorization` 同步日志。

配置 `kb_status_poll_interval_seconds` 沿用(默认 30s)。本轮无定时连接器,故无集成 worker;集成日志在文件上传时同步写入。

## 8. 文档生命周期

- **上传到分类 X**:存 blob → 写记录(X 已映射 → `vectorize_status=pending`,未映射 → `not_mapped`)→ 写集成日志 → worker 异步推 RAGFlow。
- **分类被映射 / 改映射**:其下文档 `vectorize_status → pending`(改映射时还需从旧 RAG 库删除对应 RAGFlow doc)。
- **删除文档**:删 blob + 删记录 +(已向量化则)删 RAGFlow doc。

## 9. 前端结构

单路由 `/knowledge` + `a-tabs` 四 Tab(tab 走 query param `?tab=` 可深链):

| Tab | 组件 | 内容 |
|---|---|---|
| 知识库 | `KbTab.vue` | 左:全部知识库 + 分类树侧栏;右:文档表 + 页内内嵌文档详情 |
| 知识集成 | `IntegrationTab.vue` | 文件上传向导(数据源固定 file → 选目标 KB/分类 → 上传) |
| 知识向量化 | `VectorizeTab.vue` | 左:RAG 库列表;右:勾选映射分类 + 检索测试 |
| 同步日志 | `SyncLogTab.vue` | 集成日志 / 向量化日志 两子表,可展开详情 |

独立路由 `/knowledge/document/:id/preview` 保留(从 blob 读原文)。新建 RAG 库表单承接 embedding / 分块字段;新建知识库表单仅 `name` / `code` / 描述。布局照 `eoitek-llm` 原型,组件与配色用 Ant Design Vue。

## 10. 跨模块影响

RAG 应用(`app/app/rag_app.py`)、assistant 选知识源处:从「选知识库」改为「选 RAG 库」;检索接口签名 `kb_ids` → `dataset_ids`。

## 11. 迁移方案

**Alembic `0024_knowledge_v2`**:建 `tb_rag_dataset` / `tb_kb_category_mapping` / `tb_sync_log`;`tb_kb_document` 加 `storage_path` / `rag_dataset_id`,`parse_status` 改名 `vectorize_status`;`tb_kb` 旧列暂留。

**数据迁移脚本**:

1. 每个 `tb_kb` → 建 1 个 `tb_rag_dataset`(搬 `embedding_model` / `chunk_method` / `parser_config` / `ragflow_dataset_id` / 计数)。
2. 每个 KB 建「默认分类」,`category_id=0` 的文档移入。
3. 每个分类 → 建 `tb_kb_category_mapping` 指向该 RAG 库。
4. 文档 `rag_dataset_id` 回填;`vectorize_status` 由 `parse_status` 映射。
5. **blob 回填**:逐文档 `ragflow_client.download_document` → `kb_storage.save` → 回填 `storage_path`;失败的标记(仍可检索,不能重新向量化)。
6. 数据迁移与回填确认无误后,应用 `0025_drop_tb_kb_legacy_columns` 删除 `tb_kb` 旧列。

**部署顺序约束**:`0025` 会删掉数据迁移脚本要读的列,故不能 `alembic upgrade head` 一步到位 —— 须 `upgrade 0024` → 跑迁移脚本 → `upgrade head`。

## 12. 实施分期

| 阶段 | 内容 |
|---|---|
| P1 数据层 | schema migration + blob 存储 + 数据迁移/回填脚本 |
| P2 后端 | 各 service + API + 向量化 worker 改造 |
| P3 前端 | 4-Tab 重构 |
| P4 收尾 | RAG 应用改引用 RAG 库、清理旧路由/旧字段、drop `tb_kb` 旧列 |
