# 知识库 RAG 实施计划

> 本文档是 `knowledge-rag-integration-design.md` 的工程落地拆分。按里程碑 + 组件依赖排序，覆盖代码、数据、部署、测试四个层面。M1 详写到文件级别，M2-M5 给目标 + 关键路径。

---

## 1. 当前状态盘点

| 模块 | 状态 | 备注 |
|---|---|---|
| RAGFlow 部署 | ✅ 已合并到 `deploy/docker-compose.yml` | `ragflow` + `ragflow-mysql` + `ragflow-es`；本地 build context = `ragflow/` submodule |
| RAGFlow fork (auth + bootstrap) | ✅ 已 commit 到 `ragflow/v0.25.2` 分支 | EASYAI-PATCH × 5：trusted_header / bootstrap / _load_user 短路 / 启动 hook / docker .env |
| RAGFlow Dockerfile submodule 兼容 | ⚠ 已改文件未 commit | `COPY .git` 在 submodule 形态下需 `RAGFLOW_VERSION` 兜底（已 patch + compose 传 arg） |
| backend Config | ✅ `core/config.py` 加 `ragflow_*` 字段 |
| backend HMAC client | ✅ `app/integration/ragflow_client.py` |
| 权限码 | ✅ `kb:edit` / `kb:publish` 已上线 |
| 前端菜单入口 | ⚠ `/knowledge` 路由占位 `MockFeatureView` | M1 替换 |
| **数据模型（tb_kb / tb_kb_document）** | ❌ 未开始 | M1 第 1 步 |
| **kb_service / kb_document_service / kb_retrieve_service** | ❌ 未开始 | M1 第 2-4 步 |
| **kb_* API 路由** | ✅ 已完成 | M1 第 6 步,3 个 router |
| **前端 Kb 视图** | ✅ 已完成 | KbListView / KbDetailView / KbImportView |
| 后台解析状态回拉任务 | ✅ 已完成 | `kb_status_poller.py`,30s 周期 |
| **系统设置(默认 embedding 等)** | ❌ 未开始 | M1.5 |
| **LLM 管理 → RAGFlow 同步** | ❌ 未开始 | M1.5(原 M3 提前) |
| 应用工厂绑定 kb_ids | ❌ 未开始 | M2 |
| 孤儿补偿任务 | ❌ 未开始 | M3 |

---

## 2. 里程碑总览

| 阶段 | 范围 | 时长预估 | 出口标准 |
|---|---|---|---|
| **M1 · MVP** | KB CRUD + 文件上传/解析 + 文档详情 + chunks 预览 + 检索测试 | 1.5 周 | 前端 `/knowledge` 走通"建库 → 上传 PDF → 看解析进度 → 查 chunk → 检索测试"端到端 |
| **M1.5 · AI 基础设施联动** | 系统设置 + LLM 管理↔RAGFlow 双向同步 + KB 默认 embedding | 0.5 周 | 用户在 LLM 管理录入阿里百炼 embedding → 在系统设置选为默认 → 创建 KB 不再要求填 embedding 字段,E2E 跑通 |
| **M2 · 应用绑定** | App Factory 多选 `kb_ids` + RAG 应用 runtime + 引用溯源 UI | 1 周 | 一个 `rag` 类型应用调用时调 RAGFlow `/retrieval`,回答带引用 |
| **M3 · 治理强化** | 错误恢复、孤儿补偿、并发限制、运维入口 | 0.5 周 | 删 LLM provider 校验 KB 引用;RAGFlow 重启后本地数据不漂;运维"测试连接"按钮可用 |
| **M4 · 外部 connector** | `api_pull` / `api_push` connector + 同步日志 + 调度 | 1.5 周 | 配置 API 拉取后定时同步生效，前端"同步日志"tab 可见 |
| **M5 · 高级特性** | GraphRAG、rerank model、chunk 手工编辑、Prometheus 指标 | 按需 | 单独评估 |

---

## 3. M1 详细拆分

M1 工作流按依赖顺序排列，**每步都可独立 PR**。

### Step 1 · 数据模型 + 迁移（0.5 天）

**输出**：
- `backend/app/db/schema.py` 新增 `TbKb` / `TbKbDocument`
- `backend/alembic/versions/0012_knowledge.py` 迁移脚本

**字段**（与 §4 完全一致）：

`tb_kb`：
```
id BIGINT PK, code VARCHAR(255) UNIQUE, name VARCHAR(255), description TEXT,
ragflow_dataset_id VARCHAR(255), embedding_model VARCHAR(255), chunk_method VARCHAR(64),
parser_config TEXT, doc_count INT, chunk_count INT,
status VARCHAR(32), last_synced_at BIGINT,
create_time/update_time/create_user/update_user (BIGINT)
```

`tb_kb_document`：
```
id BIGINT PK, kb_id BIGINT, name VARCHAR(255), format VARCHAR(32), size_bytes BIGINT,
category VARCHAR(255), source_type VARCHAR(32), source_meta TEXT,
ragflow_doc_id VARCHAR(255), parse_status VARCHAR(32), chunks_count INT, error_message TEXT,
audit columns
UNIQUE(kb_id, name)
```

**验收**：`make db-upgrade` 通过，schema 与 §4 字段表 1:1 对齐。

### Step 2 · `KbService` + 模型层（1 天）

**输出**：
- `backend/app/model/kb_model.py`：`KbCreateReq` / `KbUpdateReq` / `KbResp` / `KbPageReq` / `EmbeddingOption`
- `backend/app/service/kb_service.py`

**关键方法**（与 §5.3 对齐）：
- `async def create_kb(db, req, ctx) -> KbResp`：先调 `ragflow_client.create_dataset` → 拿 `dataset_id` → 落 `tb_kb`；失败回滚（删 dataset）
- `async def update_kb(db, kb_id, req, ctx) -> KbResp`：name/desc 同步两边；embedding_model 改动直接拒绝
- `async def delete_kb(db, kb_id, ctx)`：先调 RAGFlow，再删本地
- `async def refresh_stats(db, kb_id)`：拉 `get_dataset` 回填 `doc_count` / `chunk_count`
- `def list_kb(db, req, ctx) -> tuple[list[KbResp], int]`：纯读本地 + owner/超管过滤

**调用方式**：所有方法接收 `RequestContext`（已有），透传 `user_id` 给 `ragflow_client._headers`。

**验收**：service 单元测试覆盖 create/delete 回滚、embedding 不可变约束、owner 过滤；用真实 RAGFlow 容器测 happy path。

### Step 3 · `KbDocumentService`（1 天）

**输出**：`backend/app/service/kb_document_service.py`

**关键方法**（§5.4）：
- `upload_documents(db, kb_id, files, category, ctx)`：multipart 转 `(name, blob, mime)` 列表 → `ragflow.upload_documents` → 立即 `ragflow.parse_documents` 触发解析 → 本地落 `parse_status='parsing'`
- `list_documents(db, kb_id, req)`：纯读本地；`refresh=true` 强制回拉一次
- `get_document_detail(db, doc_id)`：本地 + 上游 `get_document` 拿最新状态
- `get_document_chunks(db, doc_id, page, size)`：透传 `list_chunks`
- `delete_documents(db, doc_ids, ctx)`：先上游再本地
- `reparse_documents(db, doc_ids, ctx)`：调 `parse_documents` 再次解析

**约束**：单次上传 ≤ 20 文件、单文件 ≤ 50MB（API 层兜底）。

**验收**：上传 PDF 后，3 分钟内本地 `parse_status` 从 `parsing` 变 `done`，`chunks_count` 与 RAGFlow 一致。

### Step 4 · 后台解析回拉任务（0.5 天）

**输出**：`backend/app/app/kb_status_poller.py`（仿 `checkpoint_purger.py` / `hitl_timeout_worker.py` 结构）

**逻辑**：
- 后台循环，默认 30s 一次
- `SELECT tb_kb_document WHERE parse_status IN ('pending','parsing')` 按 `kb_id` 分组
- 每组调 `ragflow.list_documents(...)` → 用 `ragflow_doc_id` 匹配 → 更新本地 `parse_status` / `chunks_count` / `error_message`
- 失败仅 log，不抛

**挂载**：`backend/app/core/lifespan.py` 启动期 `await poller.start()`，停止期 `await poller.stop()`。

**验收**：上传后即使前端不开启轮询，30s 内列表也能看到状态翻转。

### Step 5 · `KbRetrieveService`（0.5 天）

**输出**：`backend/app/service/kb_retrieve_service.py`

**关键方法**：
- `retrieve(db, kb_ids, req)`：
  1. `SELECT tb_kb WHERE id IN kb_ids` 取 dataset_ids + embedding_model
  2. 校验：embedding_model 必须全部一致（否则报 `KB_EMBEDDING_MISMATCH`）
  3. 调 `ragflow.retrieve(dataset_ids=..., question=..., top_k=...)`
  4. 重组返回：`[{chunk_id, content, similarity, doc_id, doc_name, highlight}, ...]`

**验收**：建库 + 上传 + 给问题 → 返回命中 chunks，前端能在测试面板看见相似度排序。

### Step 6 · API 路由（0.5 天）

**输出**：
- `backend/app/api/kb_api.py`
- `backend/app/api/kb_document_api.py`
- `backend/app/api/kb_retrieve_api.py`
- 在 `backend/app/api/router.py` 注册并加 `require_authenticated_user` 依赖

接口集合见 §6.1-§6.3（M1 不实现 §6.4 connector 路由）。

**验收**：`pytest` 或 `httpx` 拉一遍每个路由 200；错误码遵循 §9。

### Step 7 · 前端 `KbListView` / `KbDetailView` / `KbImportView`（2 天）

**输出**：
- `frontend/src/api/kb.ts`：与 §6 路由对齐的 axios wrapper
- `frontend/src/views/knowledge/KbListView.vue`：卡片网格 + 新建按钮 + 搜索
- `frontend/src/views/knowledge/KbDetailView.vue`：信息条 + 文档表 + 文档详情 drawer（含 chunks tab）+ 嵌入 RetrieveTester
- `frontend/src/views/knowledge/KbImportView.vue`：M1 仅文件上传向导
- `frontend/src/router/index.ts`：替换 `MockFeatureView`

**关键交互**：
- 文档列表：5s 轮询 `parse_status` 直至所有行变为 `done|error`
- 检索测试：`POST /api/v1/kb/retrieve` body 传 `kb_ids[]+question`，结果展示 chunk 内容 + similarity bar

**验收**：`make build` 通过，浏览器走通建库 → 上传 PDF → 看进度变绿 → 抽屉里点开看 chunks → RetrieveTester 输入问题拿到 chunks。

### Step 8 · 错误码与日志（0.25 天）

**输出**：
- `backend/app/core/error_code.py` 加 §9 错误码：`KB_NOT_FOUND` / `KB_DUPLICATE_CODE` / `KB_RAGFLOW_DATASET_MISSING` / `KB_DOCUMENT_NOT_FOUND` / `KB_FILE_REJECTED` / `KB_EMBEDDING_NOT_REGISTERED` / `KB_EMBEDDING_MISMATCH` / `UPSTREAM_RAGFLOW_ERROR` / `UPSTREAM_AUTH_FAILED`
- service 层关键路径加 `logger.info("[kb] action=X kb_id=Y ms=Z")` 统一前缀

**验收**：grep `[kb]` 可看到上传/检索全链路日志。

### Step 9 · E2E 验证（0.25 天）

**脚本**：`backend/scripts/kb_e2e_smoke.py`（pytest 或 standalone）
- 启 compose（含 fork 后的 ragflow 容器）
- create_kb("smoke", embedding=...) → upload PDF → poll 直到 done → retrieve("...") 拿到至少 1 个 chunk → delete_kb

**验收**：脚本退出码 0，无残留 RAGFlow dataset。

### M1 总工时

约 **6.5 人天**，前端 / 后端两边并行可压到 4 人天日历。

---

## 4. M1.5 详细拆分(AI 基础设施联动)

M1 已交付 KB 数据/服务/API/前端骨架,但 E2E 卡在"RAGFlow 无可用 embedding"——根本原因是 LLM 管理与 RAGFlow 内部 `tenant_llm` 表完全独立,easy-ai 把模型注册了 RAGFlow 还看不见。M1.5 解决这个断层。

**总范围**:**单一事实源 = easy-ai LLM 管理**(`tb_llm_provider` + `tb_llm_model`)。RAGFlow 内部 `tenant_llm` 由 easy-ai 单向写入(双向同步只读不写)。系统设置只存"默认指针",不存凭证。

**前置依赖**:M1 完成。

### Step 1 · `tb_system_setting` 表 + 服务 + API(0.5 天)

**输出**:
- `backend/app/db/schema.py` 新增 `TbSystemSetting(key VARCHAR(128) PK, value TEXT, update_time BIGINT, update_user BIGINT)`
- `backend/alembic/versions/0012_system_setting.py`
- `backend/app/service/system_setting_service.py`:`get(key) / set(key, value, ctx) / list_all()`
- `backend/app/api/system_setting_api.py`:
  - `GET /api/v1/system-setting`(列出全部,仅 `system:setting`)
  - `GET /api/v1/system-setting/{key}`
  - `PUT /api/v1/system-setting/{key}` body `{"value": "..."}`

**约定 key 命名**(平台级 AI 默认):
- `ai.default.embedding_model_id` → 指 `tb_llm_model.id`(字符串)
- `ai.default.rerank_model_id`
- `ai.default.vision_model_id`
- 未来扩展:`ai.default.asr_model_id` / `ai.default.tts_model_id` / `ai.default.image_gen_model_id`

**验收**:PUT 后 GET 可读回;权限拦截生效。

### Step 2 · `provider_type → ragflow_factory` 映射(0.25 天)

**输出**:`backend/app/integration/ragflow_client.py` 加常量 + 工具函数

**映射表**(stock RAGFlow v0.25.2 的 `llm_factory` 取值):
| easy-ai provider_type | ragflow llm_factory |
|---|---|
| `openai` | `OpenAI` |
| `openai_compatible` | `OpenAI-API-Compatible` |
| `anthropic` | `Anthropic` |
| `gemini` | `Gemini` |
| `azure` | `Azure-OpenAI` |
| `ollama` | `Ollama` |

**注意**:RAGFlow `embedding_model` 字段值是 `"{model}@{factory}"` 拼串,所以同一个 model 名跨 factory 可共存,无歧义。

**验收**:`_resolve_ragflow_factory("openai_compatible") == "OpenAI-API-Compatible"`;未知 provider_type 抛 `ValueError`,不静默回落。

### Step 3 · LLM 管理 → RAGFlow 单向同步(1 天)

**输出**:
- `backend/app/service/llm_service.py`
  - `create_model` 成功后,若 `model_type ∈ {Embedding, Rerank}` 且 `settings.ragflow_enabled`,**异步火并忘**(threadpool)调 `ragflow_client.add_llm(...)`;失败 `logger.warning` 不抛
  - `delete_model` 同理调 `ragflow_client.delete_llm(...)`
  - `update_model` 改了 `model` 字段:先 delete 旧 + add 新(简单可靠,RAGFlow 内部允许重复 add)
- 新增 `POST /api/v1/llm/model/{id}/resync`(`system:llm` 权限),手动重同步单个模型
- 新增 `GET /api/v1/llm/model/{id}/ragflow-ref` 返回 `"{model}@{factory}"` 串(KB 创建表单会用到)

**为什么 fire-and-forget**:RAGFlow 偶发不可用不能让 easy-ai LLM 管理写不进去;Step 3 的 resync API 是补偿手段。

**验收**:
- 在 LLM 管理新建一个 Embedding 模型 → 在 RAGFlow 容器内 `mysql -e "SELECT llm_name, llm_factory FROM tenant_llm"` 看到新行
- 删除该模型 → RAGFlow 内对应行消失
- 关掉 ragflow 容器,LLM 管理仍能创建/删除,只是同步失败 warn

### Step 4 · KB 默认 embedding 落地(0.5 天)

**输出**:
- `backend/app/model/kb_model.py`:`KbCreateReq.embedding_model: str | None = None`
- `backend/app/service/kb_service.py.create_kb`:
  1. 若 `req.embedding_model` 为空,从 `system_setting_service.get("ai.default.embedding_model_id")` 取 model_id
  2. 反查 `tb_llm_model` + `tb_llm_provider` → `_resolve_ragflow_factory()` → 拼 `"{model}@{factory}"`
  3. 都没有 → 抛 `KB_EMBEDDING_NOT_CONFIGURED` 错误码
- `backend/app/service/kb_retrieve_service.py.retrieve`:
  - `req.rerank_id` 为空时,从 system setting 取 `ai.default.rerank_model_id`,反查同样拼串,作为 ragflow `rerank_id` 透传(空也允许,RAGFlow 自己跳过 rerank)

**验收**:不传 `embedding_model` 也能 create_kb 成功。

### Step 5 · 前端"AI 基础设施"设置页(0.5 天)

**输出**:
- `frontend/src/api/system-setting.ts`:`getSetting / setSetting / listSettings`
- `frontend/src/api/llm.ts`:补 `listAllModels({ model_type? })` 接口(若已有,复用)
- `frontend/src/views/setting/AiInfraView.vue`:三个 a-select,options 按 model_type 过滤,显示 `{provider_name} / {model}`,保存调 PUT
- 在 `SettingView` 加 tab,权限 `system:setting`

**验收**:在该页面选完百炼 embedding 保存后,KB 创建表单的 embedding 字段可不填,后端 happy。

### Step 6 · 配置阿里百炼 + E2E 复跑(0.25 天)

**步骤**:
1. 用户在前端 LLM 管理新建 provider:
   - name=`阿里百炼`,provider_type=`openai_compatible`
   - base_url=`https://dashscope.aliyuncs.com/compatible-mode/v1`
   - api_key=(用户填)
2. 在该 provider 下加模型:
   - `text-embedding-v3` / Embedding
   - `gte-rerank-v2` / Rerank(可选)
3. 前端"AI 基础设施"页选 `text-embedding-v3` 为默认 embedding
4. 重跑 `cd backend && uv run python scripts/kb_e2e_smoke.py`(不再传 `--embedding`,走默认)
5. 看 retrieve hits ≥ 1

**验收**:smoke test 退出码 0,日志有命中的 chunk。

### M1.5 出口验收(一句话)

> 用户开两个浏览器 tab,一个录百炼 api_key,一个在系统设置选默认 embedding,然后回到 `/knowledge` 直接建库上传文件就能检索——全程不写 RAGFlow,不知道 `tenant_llm` 是啥。

### M1.5 总工时

约 **3 人天**,前后端可并行。

---

## 5. M2 应用绑定（1 周）

**前置**：M1 完成。

### 任务列表

1. **AppFormView 增加 KB 多选器**（前端）
   - `app_type === 'rag'` 时显示
   - 调 `GET /api/v1/kb/options`（带 embedding 过滤分组）
   - 提交时写入 `app_config.kb_ids: string[]`

2. **`RagAppRunner`（后端）**
   - `app/app/rag_app.py`：参考现有 `LlmApp` / `AgentApp`
   - run() 接收 `question`，读 `app_config.kb_ids`，调 `KbRetrieveService.retrieve`，把 chunks 拼进 system prompt（template 来自 `app_config.prompt_template`）
   - 调 LiteLLM 生成回答
   - 在响应里附加 `references: [{chunk_id, doc_name, snippet}, ...]`

3. **OpenAPI 路由**：`backend/app/api/open_api.py` 加 `POST /api/v1/rag/{app_id}` + stream 版

4. **AppDetailView 引用溯源 UI**：测试 drawer 里把 references 渲染成卡片，点击高亮 chunk 内容

5. **Langfuse trace**：`KbRetrieveService.retrieve` 作为 `kb.retrieve` span，记录 `dataset_ids` / `top_k` / `hit_count`

**验收**：创建一个 RAG 应用，绑定一个 KB，在测试面板里问问题，拿到回答 + 引用列表，langfuse 看到完整 trace。

---

## 6. M3 治理强化（0.5 周）

> M1.5 已完成 LLM↔RAGFlow 单向同步;M3 仅做"用前校验"和"运维兜底"。

1. **Embedding 引用阻断**(配合 M1.5 同步)
   - `LlmService.delete_model` 在 fire-and-forget 同步前先 `SELECT count FROM tb_kb WHERE embedding_model LIKE '{model}@%'` 校验,>0 则返回 `EMBEDDING_IN_USE`
   - 同理 `delete_provider` 校验该 provider 下任意 model 是否被引用

2. **孤儿补偿任务**（§9）
   - 后台任务：每天扫描 `ragflow.list_datasets` 与本地 `tb_kb`，删 RAGFlow 中无本地映射的 dataset；本地 `ragflow_dataset_id` 不存在的 KB 标 `status=error`

3. **运维入口 `系统配置 → 知识库引擎`**（§3.7）
   - 前端：`SettingView` 加 tab，仅 `system:setting` 可见
   - 后端：`GET /api/v1/system/ragflow/health`、`POST /api/v1/system/ragflow/reset-bootstrap`

4. **并发限制**：`KbDocumentService.upload_documents` 用 `asyncio.Semaphore(5)` 限制同时调用 RAGFlow 的连接数

5. **错误码完善 + 用户友好提示**：前端拦截 `UPSTREAM_AUTH_FAILED` 弹"检查 RAGFLOW_SHARED_SECRET 配置"

**验收**：删 embedding provider 触发引用阻断；RAGFlow 容器重启 + 数据卷被清后，本地能"自愈"到一个可用状态（KB 标 error，不让用户瞎用）。

---

## 7. M4 外部 connector（1.5 周）

1. **`tb_kb_connector` 表**（§4.4 之外新增）
   - `id, kb_id, source_type, config(JSON), schedule(cron), enabled, last_run_at`
2. **`tb_kb_sync_log` 表**（§4.4）
3. **`KbConnectorService` + apscheduler 调度**
4. **两种 connector 实现**：
   - `ApiPullConnector`：按 schedule 拉对方接口 → 翻页 → 落 RAGFlow upload + 本地 tb_kb_document
   - `ApiPushConnector`：暴露 `POST /api/v1/kb/ingest/push/{token}`，对方 token + Bearer 鉴权后写入
5. **同步日志 UI**：前端 "知识集成日志" tab

**验收**：配置一个 API 拉取后，每日自动同步生效，前端能看见每次同步的成功/失败/新增数。

---

## 8. M5 待评估特性（按需）

- GraphRAG 接入（RAGFlow 已支持）
- Rerank model 选择
- Chunk 手工编辑 UI
- Prometheus 指标（`kb_documents_total` / `kb_parse_failures_total` / `kb_retrieve_latency_seconds`）
- Ones / Confluence connector

---

## 9. 风险与依赖

| 风险 | 概率 | 缓解 |
|---|---|---|
| 首次 `./deploy.sh up ragflow` build 时间长（拉 `infiniflow/ragflow_deps:latest` 镜像 ~5GB） | 高 | 文档明示"首次约 10-20 分钟"；提供 `RAGFLOW_NEED_MIRROR=1` 加速国内构建 |
| 内存不足导致 ragflow 容器 OOM（开发机 8G 不够） | 中 | 文档建议生产 ≥16G；开发环境压低 `RAGFLOW_ES_MEM_LIMIT=2g` |
| 上传 PDF 解析耗时长导致前端轮询超时 | 中 | M1 用 30s 后台回拉兜底；前端 5s 轮询展示进度 |
| RAGFlow upstream API 在版本升级时变化（特别是 `/v1/datasets/<id>/chunks` 解析触发协议） | 中 | `ragflow_client.py` 方法 1:1 映射，rebase 时只需调 ~10 个方法签名 |
| Embedding provider 未注册导致 create_kb 失败 | 高 | 前端建库表单 embedding 下拉为空时引导到 LLM 管理 |
| 多用户并发上传同一文件名冲突 | 低 | `UNIQUE(kb_id, name)` 兜底，service 层错误码 `KB_DOC_DUPLICATE_NAME` |

**强依赖**：
- `system:llm` 必须先有 embedding provider（OpenAI-API-Compatible），否则 M1 第一个 create_kb 即失败。
- RAGFlow fork 镜像可被 docker build 成功（依赖 `infiniflow/ragflow_deps:latest` 可拉取）。

---

## 10. M1 出口验收（一句话）

> 一个新员工拉代码 → `cp deploy/.env.example deploy/.env` → `./deploy.sh up` → 浏览器登录 → 在系统配置加一个 OpenAI-Compatible embedding provider → 在 `/knowledge` 建一个 KB → 上传 README.md → 30s 后看见 chunks → 测试面板问一个关键词 → 拿到命中 chunk。

整个流程无需手动调任何 RAGFlow API、无需 bootstrap、无需写 Token。

---

## 11. PR 切片建议

按 Step 顺序切，每个 Step 一个 PR，便于代码评审：

| PR | 内容 | 依赖 |
|---|---|---|
| #1 | Step 1: 数据迁移 + schema | - |
| #2 | Step 2: kb_service + model | #1 |
| #3 | Step 3: kb_document_service | #2 |
| #4 | Step 4: 后台 poller | #3 |
| #5 | Step 5: kb_retrieve_service | #2 |
| #6 | Step 6: kb API 路由 | #2-5 |
| #7 | Step 7: 前端三视图 | #6 |
| #8 | Step 8: 错误码 + 日志 | 与 #6 合并也可 |
| #9 | Step 9: E2E 脚本 | 全部 |

合并到 master 即视为 M1 完成。
