# Agent 记忆系统详细设计

> easy-ai 企业级 harness agent 的记忆能力——跨会话、跨用户、跨团队的持久化"知道什么"层。

---

## 1. 功能概述

### 1.1 目标

给 agent 补齐**跨会话的"知道什么"**能力。短期上下文由 `long-session-design.md` 的 checkpointer 承接；本设计解决**长期记忆**：

1. 记住用户个人偏好、事实、过去对话要点
2. 记住团队 / 应用 / 组织的共识（政策、术语、流程）
3. 让 agent 主动"学到东西就记下来"，并接受用户审阅
4. 记忆可被搜索、引用、追溯来源、遵守合规

### 1.2 与已有能力的边界

| 能力 | 性质 | 本设计关系 |
|---|---|---|
| **Skill（SKILL.md）** | 程序性记忆（Procedural） —— "怎么做" | 不重叠，互补 |
| **RAGFlow** | 企业文档检索 —— 结构化大知识库 | 可作为 "外部语义记忆" 一等公民，但不是本设计核心 |
| **Checkpointer（state + messages）** | 本次会话工作记忆 | 本设计之外；memory 跨会话存在 |
| **Langfuse trace** | 观测数据 | 可作为记忆抽取源（§9.2），不做 agent 实时注入 |
| **deepagents `MemoryMiddleware`** | 从 backend path 加载 `AGENTS.md` 并注入 system prompt | 仅作为 L1 静态记忆的只读注入底座；企业级写入、审批、PII、GDPR 均由 easy-ai 自研层实现 |

运行上下文约束：本设计复用 `tool-approval-and-acl-design.md` 中定义的统一 `AgentRunContext`，由入口层提供 `app_id`、`user_id`、`conversation_id`、`team_ids`、`tenant_id` 等字段；不要假设现有 `RequestContext` 已包含会话或租户信息。

deepagents 边界约束：原生 `MemoryMiddleware` 会在提示词中鼓励模型用 `edit_file` 更新记忆。easy-ai 企业记忆不能依赖该写入路径，因为它只会修改 StateBackend / checkpoint 中的虚拟文件，无法自动落入 `tb_memory_*`、pending 审批、PII 策略和 GDPR 流程。首期必须把 L1 作为只读注入；所有长期记忆写入只允许走 `remember` / `forget` 等自研工具。

### 1.3 核心用户价值

- "记住我喜欢中文回复" — 持久偏好，不再每次重说
- "上次咱们讨论的营销方案" — 跨会话上下文召回
- "公司的退款政策" — 团队共享知识
- "我不想让你记住这条" — GDPR 式 right-to-forget
- 管理员："哪些事实是 agent 自动学到的？"

---

## 2. 适用场景

| 场景 | 使用的记忆层 | 操作 |
|---|---|---|
| 用户首次说"用中文" | User KV | 自动写入或询问用户 |
| 跨会话回忆"上次的方案" | Episodic + Semantic | 语义检索 top-k 注入 |
| 新员工问"请假流程" | Team/Org AGENTS.md + Semantic | 静态 + 语义混合注入 |
| 用户纠正 agent："我姓王不姓张" | User KV | 覆盖旧记忆，写审计 |
| 项目组术语表 | App AGENTS.md | 固定注入 |
| "忘掉我 5 月之前所有对话" | 所有层 | GDPR 删除 API |
| Agent 发现新事实 | Reflection | 加入 pending 区等用户确认 |
| 管理员审视团队记忆 | 后台页面 | 浏览、编辑、批准、撤回 |

---

## 3. 记忆分类（Taxonomy）

### 3.1 按作用域（Scope）

```
Org (organization)      ─┐
  └── Team (user_group) ─┤
        └── App         ─┤─→ 组合注入（从宽到窄）
              └── User  ─┘
                    └── Conversation (checkpoint，不在本设计)
```

查询时按 **User → App → Team → Org** 顺序合并；下层同键覆盖上层。

### 3.2 按结构（Structure）

| 层 | 名称 | 形态 | 典型条目 |
|---|---|---|---|
| L1 | **静态文件记忆** | Markdown 文件（AGENTS.md 风格） | "本项目 API 路径用单数形式" |
| L2 | **结构化 KV 记忆** | `{key, value, category, confidence, source}` | `{key: "language_preference", value: "zh-CN"}` |
| L3 | **语义记忆** | 自由文本 + embedding | "用户在 2026-04 决定把预算投入 RAG" |
| L4 | **情景记忆（Episodic）** | 每次会话的摘要 | "2026-04-20 讨论了促销活动 X" |
| L5 | **反思记忆（Reflection）** | Agent 自写，默认进 pending | "用户偏好简洁回复" |

各层独立存储、独立策略、统一 `MemoryService` 门面。

### 3.3 按写入者（Authority）

| 写入者 | 可写层 | 置信度初值 |
|---|---|---|
| 管理员（人工） | L1 / L2 / L3 | 1.0 |
| 普通用户（对自己） | L2 / L3 | 0.9 |
| Agent 自写（user 作用域） | L2 / L3 / L5 | 0.5（pending） |
| 系统自动（episodic 摘要） | L4 | 0.7 |

Agent 自写默认进 pending，用户在"我的记忆"页确认后晋升到 confirmed（置信度+）。

---

## 4. 总体架构

### 4.1 系统分层

```
┌──────────────────────────────────────────────────────────┐
│ Agent 运行时                                              │
│  ┌────────────────────────────────────────────────────┐  │
│  │ MemoryInjectionMiddleware（before_model 注入）     │  │
│  │   - 组装多层记忆（budget-aware）                   │  │
│  │   - 写入 system prompt 的 <memory> 段              │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ 自研工具（暴露给 LLM）                             │  │
│  │   recall / remember / forget / list_memories       │  │
│  │   （受 tool-approval-and-acl-design 的策略守护）   │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │ MemoryReflectionMiddleware（after_model 抽取）     │  │
│  │   - 从本轮对话自动抽取候选记忆 → pending          │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│ MemoryService（门面）                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │ L1 Files │  │ L2 KV  │  │ L3 Sem  │  │ L4 Epi  │     │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘     │
│  ┌─────────────────────────────────────┐                │
│  │ L5 Reflection（pending / confirmed）│                │
│  └─────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│ 存储                                                      │
│  - PostgreSQL: tb_memory_* 系列表                        │
│  - pgvector: embedding 列（L3/L4）                       │
│  - 对象存储（可选）: 大附件                               │
└──────────────────────────────────────────────────────────┘
```

### 4.2 关键组件

| 组件 | 位置 | 职责 |
|---|---|---|
| `MemoryService` | `backend/app/service/memory_service.py` | 多层记忆统一门面（CRUD + 查询） |
| `EmbeddingClient` | `backend/app/core/embedding.py` | 调 LiteLLM gateway 的 `embeddings` 接口 |
| `MemoryInjectionMiddleware` | `backend/app/app/middlewares/memory_inject.py` | 注入记忆到 system prompt |
| `MemoryReflectionMiddleware` | `backend/app/app/middlewares/memory_reflect.py` | 抽取候选记忆 |
| `MemoryToolset` | `backend/app/app/memory_tools.py` | 给 LLM 的 recall/remember/forget/list 工具 |
| `MemoryCompactor` | `backend/app/task/memory_compactor.py` | 后台合并 / 去重 / 衰减 |
| `EpisodicSummarizer` | `backend/app/task/episodic_summarizer.py` | 会话结束后抽一句摘要入 L4 |

---

## 5. 数据模型

### 5.1 L1 静态文件记忆（复用 skills 模式）

不新增数据库外键约束；只新增业务表、唯一约束和查询索引。L1 静态记忆内容持久化在数据库或对象存储，运行时按约定路径转成 deepagents `StateBackend` 的虚拟文件注入：

```
/memory/org/AGENTS.md                # 全租户共享
/memory/team/{group_id}/AGENTS.md
/memory/app/{app_id}/AGENTS.md
/memory/user/{user_id}/AGENTS.md
```

内容形如 skill 的 SKILL.md 但无 YAML frontmatter，纯 markdown。Web 后端首期禁止直接使用 deepagents `FilesystemBackend` 读取真实磁盘，避免 agent 获得宿主机文件访问能力；统一通过 `StateBackend` 的 `files` 参数注入虚拟 `/memory/.../AGENTS.md`。

运行时在 `_prepare` 拼装 `memory=[...]` 参数传给 `create_deep_agent`，但必须把该层视作只读上下文。若保留 deepagents 原生 `MemoryMiddleware`，必须通过工具策略禁止或拦截模型对 `/memory/**` 的 `edit_file` 写入；推荐 P0 直接用自研 `MemoryInjectionMiddleware` 注入 L1 文本，避免原生 memory prompt 诱导模型写虚拟文件。

### 5.2 L2 结构化 KV 记忆 `tb_memory_kv`

```python
class TbMemoryKv(Base):
    __tablename__ = "tb_memory_kv"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "key",
                         name="uk_tb_memory_kv_scope_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 'user' | 'app' | 'team' | 'org'
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # user_id / app_id / user_group_id / org_id；org 可用租户 id
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    # 轻分类：preference / fact / relationship / contact / reminder / ...
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # 0.0 - 1.0
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # 'user' | 'agent' | 'admin' | 'system'
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'pending' | 'confirmed' | 'archived'
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    # 用于证据链：最初在哪条消息提出的
    origin_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 引用次数，高频记忆不被衰减
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 到期时间，null=永久
    expire_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # PII 标记：高敏记忆默认加密
    sensitivity: Mapped[str] = mapped_column(String(8), nullable=False, default="normal")
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：
- `(scope_type, scope_id, status)` — 列表查询
- `(scope_type, scope_id, category)` — 按类过滤
- `(expire_time)` — 后台过期清理

### 5.3 L3 语义记忆 `tb_memory_semantic`

```python
class TbMemorySemantic(Base):
    __tablename__ = "tb_memory_semantic"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 轻分类
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # pgvector column：维度在全局锁定为 settings.memory_embedding_dim，
    # 行为见下方 "Embedding 维度锁定" 说明
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    # 实际写入时的 embedding model id，只做追溯；不允许不同维度混入同一列
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed")
    origin_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expire_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(8), nullable=False, default="normal")
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    update_user: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
```

索引：
- 向量索引：`CREATE INDEX ... USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)`
- `(scope_type, scope_id, status)` 过滤

Alembic 迁移需先 `CREATE EXTENSION IF NOT EXISTS vector;`。

实现前置依赖：当前 backend 需新增 `pgvector`/SQLAlchemy vector 类型支持，并在部署数据库中安装 pgvector 扩展；若目标环境不能安装扩展，P2 语义记忆降级为文本检索或外部向量服务。

### 5.4 L4 情景记忆（会话摘要）`tb_memory_episodic`

```python
class TbMemoryEpisodic(Base):
    __tablename__ = "tb_memory_episodic"
    __table_args__ = (
        UniqueConstraint("conversation_id", name="uk_tb_memory_episodic_conversation"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 一句话摘要，给未来检索用
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # 可选的详情（保留前 N 条关键消息）
    highlights: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False)
    # 会话时间范围
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ended_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

约束与索引：
- `UniqueConstraint(conversation_id)` — 一会话一摘要，`EpisodicSummarizer` 用 `INSERT ... ON CONFLICT(conversation_id) DO UPDATE` 幂等写入
- 向量 `ivfflat` 索引
- `(user_id, started_at DESC)` — 时间线

### 5.5 L5 反思记忆 pending 区

复用 `tb_memory_kv` / `tb_memory_semantic` 的 `status='pending'`，不单独建表。前端"我的记忆 → 待确认"页只筛 `status=pending`。

### 5.6 审计 `tb_memory_audit`

```python
class TbMemoryAudit(Base):
    __tablename__ = "tb_memory_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 'created' | 'updated' | 'deleted' | 'archived' | 'confirmed' |
    # 'accessed_read' | 'accessed_inject' | 'exported' | 'gdpr_deleted'
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    layer: Mapped[str] = mapped_column(String(8), nullable=False)  # 'kv'|'sem'|'epi'
    memory_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    scope_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scope_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # before/after snapshot + context
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
```

与 policy audit（`tool-approval-and-acl-design.md` §4.8）分表，避免相互干扰。GDPR 删除需要保留审计元数据（what was deleted, by whom）但不保留原文。

### 5.7 `app_config` 扩展

```jsonc
{
  "memory": {
    "enabled": true,
    "sources": ["org", "team", "app", "user"],   // 启用的作用域
    "layers": {
      "files":     true,            // L1
      "kv":        true,            // L2
      "semantic":  true,            // L3
      "episodic":  true,            // L4
      "reflection":{"enabled": true, "auto_confirm": false}
    },
    "injection": {
      "max_tokens": 2000,           // 注入预算
      "kv_top":     20,             // L2 注入条数上限
      "semantic_top": 5,            // L3 top-k
      "episodic_top": 3
    },
    "embedding": {
      "model": "text-embedding-3-small",
      "dimensions": 1536
    },
    "retention_days": 365
  }
}
```

---

## 6. 存储选型

### 6.1 pgvector 即可，不引入独立向量库

- 已有 PG 基础设施，新组件越少越好
- `ivfflat`（或 `hnsw`）对 10M 级记忆性能足够
- 事务一致性（KV 写入 + embedding 写入同一 tx）
- 后续数据量上来可再引入 Milvus/Qdrant

### 6.2 Embedding 来源

使用项目已有的 LiteLLM gateway（`backend/app/service/model_gateway_service.py`）的 embeddings 端点：

```python
class EmbeddingClient:
    def __init__(self, gateway_url: str):
        self._gateway_url = gateway_url

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        response = httpx.post(
            f"{self._gateway_url}/embeddings",
            json={"model": model, "input": texts},
            timeout=15.0,
        )
        return [d["embedding"] for d in response.json()["data"]]
```

统一走 gateway 的好处：模型切换无缝、成本有日志、可限流。

### 6.2.1 Embedding 维度锁定

pgvector 的 `Vector(N)` 列维度在建表时固定。同一列**不允许混入不同维度的向量**，否则插入或 `ivfflat` 查询都会失败。设计约束：

- **全局单一维度**：`settings.memory_embedding_dim`（默认 1536 对应 `text-embedding-3-small`）在部署时锁定
- `MemoryService` 写入时校验 `len(emb) == settings.memory_embedding_dim`，不一致拒绝写入
- `EmbeddingClient` 只暴露单一模型句柄，`build_from_settings()` 启动时校验 gateway 返回维度
- **模型升级路径**（换到 768 / 1024 / 3072 维模型）：
  1. 新增 alembic migration 创建 `tb_memory_semantic_v2` / `tb_memory_episodic_v2`，列维度改成新值
  2. 后台 `EmbeddingMigrator` 双写过渡期内，读路径优先查新表，fallback 旧表
  3. 回填完成后切读路径、归档旧表
  4. 任何时候**不**原地 `ALTER COLUMN` 维度

### 6.3 PII 高敏策略

首期必须实现敏感度策略，即使暂不接 KMS：
- `sensitivity='high'` 的记忆默认不允许 agent 自动写入，只能用户或管理员确认后保存。
- 高敏记忆默认不进入自动注入；如业务必须注入，需 app 显式开启并走私有模型或可信网关。
- 审计、日志、反馈和 Langfuse 上报只记录脱敏摘要，不记录原文。
- AES-256-GCM（key 存 KMS / Vault）作为 P1+ 存储加密能力接入；接入前高敏字段至少做应用层占位/掩码展示。

---

## 7. 写入策略（Write Policy）

### 7.1 谁可以写

| 写入者 | 可写 scope | 需否审批 |
|---|---|---|
| 管理员 | org / team / app / user（代替用户） | 否（但受审计） |
| 用户 | 自己的 user scope；app scope（受 app 权限） | 否 |
| Agent（通过 `remember` 工具） | 默认 user scope；app scope 需管理员策略放行 | 默认入 pending |
| 系统（episodic summarizer） | user + conversation | 否 |

### 7.2 Agent 的 `remember` 工具

```python
@tool("remember",
    description="将一条事实保存到用户记忆。用户通常需要确认才生效。",
    args_schema=RememberArgs)
def remember_tool(
    content: str,
    category: str,
    scope: Literal["user", "app"] = "user",
    confidence: float = 0.5,
) -> str:
    ...
```

调用链：
1. LLM 调 `remember` → 经过 `tool-approval` 的策略（可阻断或要审批）
2. `MemoryService.write_from_agent(...)` → `status='pending'`
3. 通过 SSE 推 `memory_candidate` 事件给前端
4. 用户在对话里点"接受记忆"或去 `/memory` 页批准
5. 批准 → `status='confirmed'`, `confidence` 提升
6. 拒绝 → `status='archived'`, 审计 `confirmed=false`

### 7.3 冲突解决

同 `(scope, key)` 二次 INSERT：

- 旧 value 与新 value 相同 → `ref_count++`，`update_time` 刷新
- 不同 → 走**冲突策略**：
  - `confidence_higher_wins`（默认）：比较置信度，高者胜；败者归档（保留用于回滚）
  - `latest_wins`：新值覆盖旧值
  - `ask_user`：创建 pending 冲突单，用户选择
- 规则可在 `app_config.memory.conflict_policy` 配置

### 7.4 去重（Semantic）

写入 L3 前用 embedding 相似度检测：

```python
existing = service.search_semantic(
    scope_type, scope_id, content_embedding, top_k=1
)
if existing and existing[0].similarity > 0.92:
    # 视为重复，ref_count++
    service.touch(existing[0].id)
    return existing[0].id
return service.create_semantic(...)
```

---

## 8. 注入策略（Injection）

### 8.1 `MemoryInjectionMiddleware`

挂在 `before_model` hook：

```python
class MemoryInjectionMiddleware(AgentMiddleware):
    async def amodify_model_request(self, request, state):
        app_id = self._run_ctx.app_id
        user_id = self._run_ctx.user_id
        latest_user_msg = self._last_user_message(state)

        memories = await self._memory_service.collect_for_injection(
            user_id=user_id,
            app_id=app_id,
            team_ids=self._user_team_ids,
            query=latest_user_msg.content if latest_user_msg else None,
            budget=self._injection_budget,
        )

        prompt_block = self._render_memory_block(memories)
        request.system_prompt = append_to_system_message(
            request.system_prompt, prompt_block
        )
        return request
```

### 8.2 组装算法（budget-aware）

```python
def collect_for_injection(user_id, app_id, team_ids, query, budget):
    # 1. 固定注入（总是拉全）
    blocks = []
    blocks += load_layer1_files(user_id, app_id, team_ids)   # AGENTS.md
    blocks += load_kv_top(scope='user',  scope_id=user_id, limit=20)
    blocks += load_kv_top(scope='app',   scope_id=app_id,  limit=10)
    blocks += load_kv_top(scope='team',  scope_ids=team_ids, limit=10)

    # 2. 查询驱动（semantic / episodic，按 query 相关度）
    if query:
        q_emb = embedder.embed([query])[0]
        blocks += search_semantic(user_id, app_id, q_emb, top_k=5)
        blocks += search_episodic(user_id, q_emb, top_k=3)

    # 3. token budget cut
    return budget_truncate(blocks, budget)
```

`budget_truncate` 按 **重要性**（scope 优先级、confidence、ref_count 加权）降序保留，超预算丢尾。

### 8.3 注入格式（system prompt 末尾）

```markdown
<memory>

## 永久记忆

- [用户偏好] 用中文回复
- [用户资料] 工位在 B 区 12 号
- [团队政策] 对外邮件 CC 合规 sec@...

## 最近相关

- 2026-04-12: 你和用户讨论过对账报表格式，决定用 CSV
- 2026-04-15: 用户提到项目代号 "Aurora"

## 本应用知识

- "订单状态" 的合法取值：pending / paid / shipped / done / refunded

</memory>
```

使用 `<memory>` XML 包裹，给 LLM 清晰信号；与 `<skills>` / 工具说明分开。

### 8.4 引用与证据（可选）

每条记忆带 id，LLM 引用时可在答案末尾 `<cite memory="123,456">`，前端渲染为小徽标，点击跳转"我的记忆"。

实现：prompt 里要求 `<cite memory="...">` 语法；`MemoryInjectionMiddleware` 返回 `id` 映射；SSE 事件把引用推出；`MemoryService.touch(ids)` 更新 `ref_count / last_used_time`。

---

## 9. Agent 工具集（Memory Toolset）

### 9.1 `recall(query, top_k=5, scopes=None)`

```python
def recall_tool(query: str, top_k: int = 5, scopes: list[str] | None = None) -> str:
    results = service.search_semantic(..., embedding=q_emb, top_k=top_k)
    # 返回 markdown 列表给 LLM
```

适用场景：agent 发现问题超出当前注入记忆范围，主动去查。

### 9.2 `remember(content, category, scope='user', confidence=0.5)`

见 §7.2。

### 9.3 `forget(memory_id, reason)`

- 仅允许遗忘 agent 可见的 user / app scope 记忆
- 转 `status='archived'` 而非硬删（保留审计 30 天）
- 需经 tool-approval 策略检查

### 9.4 `list_memories(category=None, scope='user', limit=50)`

供 agent 在被问"你都记得什么"时返回。

### 9.5 工具暴露与 deepagents 的集成

在 `_prepare` 里把这 4 个工具连同用户自定义工具一起注入：

```python
tools = self._build_tools(db, req.app_id)
if memory_cfg.get("enabled"):
    tools.extend(self._build_memory_tools(user_id=..., app_id=...))
```

这些工具会经过 `ToolPolicyMiddleware` —— 企业可以为 `remember` 设置"仅 user scope 且 confidence < 0.8 自动通过，否则审批"的策略。

---

## 10. 反思机制（Reflection）

### 10.1 `MemoryReflectionMiddleware`

挂在 `after_model` hook，每轮对话结束后：

```python
class MemoryReflectionMiddleware(AgentMiddleware):
    async def aafter_model(self, response, state):
        if not self._reflection_enabled:
            return response

        recent_messages = self._tail_messages(state, n=6)
        candidates = await self._extractor.extract(recent_messages)
        for c in candidates:
            await self._memory_service.write_pending(
                scope_type="user", scope_id=self._user_id,
                content=c.content, category=c.category,
                confidence=c.confidence, source="agent",
                origin_message_id=c.origin_message_id,
            )
        return response
```

`MemoryExtractor` 是一个轻量 LLM 调用（haiku/mini），prompt：

```
Given the last 3 turns, extract 0-3 durable facts about the user
(preferences, identity, commitments). Output JSON:
[{"content": "...", "category": "preference|fact|...", "confidence": 0.0-1.0}]
Rules:
- Skip ephemeral facts (weather, current task).
- Skip questions, commands, opinions.
- Only extract what user stated about themselves/their context.
```

调用频次控制：
- 每会话前 3 轮才跑（避免噪声）
- 或超过 N 轮后每 5 轮跑一次
- 有速率上限，失败不影响主流程

### 10.2 用户确认

前端在对话下方显示小卡片：

```
💡 AI 想记住这些：
  ☐ 用中文回复
  ☐ 工位在 B 区 12 号
  [ 全部接受 ] [ 忽略 ] [ 单独选择 ]
```

接受 → `status='pending' → 'confirmed'`，confidence 提升到 0.9；忽略 → `status='archived'`。

---

## 11. 情景摘要（Episodic）

### 11.1 `EpisodicSummarizer` 后台任务

触发条件之一：
- 会话 `status='archived'`
- 会话 `update_time` 静默超 24 小时
- 显式请求

```python
def summarize_conversation(conversation_id: int) -> None:
    msgs = load_messages(conversation_id)
    if len(msgs) < 4:
        return  # 太短不摘要

    summary = summarizer_llm.invoke(
        prompt=EPISODIC_PROMPT,
        messages=msgs[:50],
    ).content

    highlights = select_key_messages(msgs, max=5)
    emb = embedder.embed([summary])[0]

    service.upsert_episodic(
        user_id=conversation.user_id, app_id=conversation.app_id,
        conversation_id=conversation_id,
        summary=summary, highlights=json.dumps(highlights),
        embedding=emb, ...
    )
```

摘要模型用便宜档（haiku/mini），摘要长度约 50-100 字。

### 11.2 检索流程

新会话首条消息到达时，`MemoryInjectionMiddleware` 用 query embedding 在 `tb_memory_episodic` 里找 `top_k=3`：

```sql
SELECT id, summary, started_at,
       1 - (embedding <=> :q_emb) AS similarity
FROM tb_memory_episodic
WHERE user_id = :uid AND tenant_id = :tid
ORDER BY embedding <=> :q_emb
LIMIT 3;
```

相似度阈值 0.7 以下不召回，避免不相关打扰。

### 11.3 与 RAGFlow 的关系

RAGFlow 是**企业文档**的 RAG；episodic 是**用户-agent 交互史**的 RAG。两者独立，互不替代。如果要在 agent 上同时召回：
- RAGFlow 通过 tool 暴露（`query_knowledge_base`），agent 主动调
- Episodic 通过 `MemoryInjectionMiddleware` 自动注入

---

## 12. 合并 / 衰减 / 压缩

### 12.1 `MemoryCompactor` 后台任务

每日运行：

1. **衰减**：`confidence := confidence * 0.99^days_since_last_used` 对 `source='agent'` 的记忆；降到阈值（如 0.2）以下自动归档
2. **合并**：同 scope 内 embedding 相似度 > 0.95 的两条 semantic → 合并为一条（保留 ref_count 较高者，另一条归档并把 ref_count 加过来）
3. **过期**：`expire_time < now` 的记忆 → 归档 + GDPR-safe 删原文
4. **容量**：单 scope 超阈值（如 user scope 1000 条 KV）→ 最旧且 ref_count 最低的归档

### 12.2 不动硬删

所有"删除"默认 `status='archived'`，保留 90 天给审计 / 回滚，之后物理删。`gdpr_deleted` 例外：立即清内容，保留行空壳 + 审计。

---

## 13. 治理：访问控制、审计、合规

### 13.1 访问矩阵

| 操作 | 用户 | 管理员 |
|---|---|---|
| 读自己 user scope | ✅ | ✅ |
| 写 / 改 / 删自己 user scope | ✅ | ✅ |
| 读其他用户 user scope | ❌ | ✅（敏感操作，强审计） |
| 读 app / team / org scope（已绑定） | ✅ | ✅ |
| 写 app / team / org scope | ❌ | ✅ |
| GDPR 删除请求（按 user_id 抹除所有） | ✅（对自己） | ✅（代为执行） |

### 13.2 审计事件

每次 `inject / read / write / delete / confirm` 写入 `tb_memory_audit`。注入事件批量聚合（每会话一条记录，包含注入记忆 id 列表），避免审计表爆炸。

### 13.3 GDPR / 被遗忘权

`POST /api/v1/memory/gdpr-delete` body:
```json
{ "user_id": "...", "confirm": "DELETE MY DATA" }
```

执行：
- `tb_memory_kv` / `tb_memory_semantic` / `tb_memory_episodic` 中 `scope_type='user' AND scope_id=user_id` 全部 `gdpr_delete`
- 内容字段清空，保留行（审计用），`status='gdpr_deleted'`
- 写一条审计事件
- 用户相关 L1 文件 `/memory/user/{id}/AGENTS.md` 清空
- 返回执行数量

不会联动删 `TbConversationMessage`（那是业务对话记录，另走对话 GDPR 流程）。

### 13.4 导出（数据携带权）

```
GET /api/v1/memory/export?scope=user&format=json|markdown
```

导出该用户可访问的所有记忆，markdown 对人友好、json 机器可读。

### 13.5 租户隔离

- 所有查询自动注入 `tenant_id` 约束
- 跨租户读 → deny + 告警
- 迁移租户需管理员显式操作（复制记忆 + 审计）

---

## 14. API 设计

### 14.1 用户侧

```
# 列表 / 查询
GET    /api/v1/memory/kv/page?scope=user&category=preference
GET    /api/v1/memory/semantic/search?q=...&scope=user&top_k=10
GET    /api/v1/memory/episodic/timeline?user_id=...&limit=50

# 单条 CRUD（对自己）
POST   /api/v1/memory/kv
PUT    /api/v1/memory/kv/{id}
DELETE /api/v1/memory/kv/{id}

POST   /api/v1/memory/semantic
PUT    /api/v1/memory/semantic/{id}
DELETE /api/v1/memory/semantic/{id}

# Pending 管理
GET    /api/v1/memory/pending/page
POST   /api/v1/memory/pending/{id}/confirm
POST   /api/v1/memory/pending/{id}/reject
POST   /api/v1/memory/pending/bulk-confirm     # 批量

# 会话确认入口（Reflection 小卡片走这个）
POST   /api/v1/memory/from-conversation
body: { conversation_id, candidate_ids: [...], action: "confirm"|"reject" }
```

### 14.2 管理员侧

```
GET    /api/v1/memory/admin/page?scope=app&scope_id=...
POST   /api/v1/memory/admin/kv
PUT    /api/v1/memory/admin/kv/{id}
DELETE /api/v1/memory/admin/kv/{id}

# L1 文件
PUT    /api/v1/memory/admin/files?path=/memory/team/7823/AGENTS.md
GET    /api/v1/memory/admin/files?path=...

# 审计
GET    /api/v1/memory/admin/audit?scope=user&scope_id=...
GET    /api/v1/memory/admin/stats?period=7d

# GDPR
POST   /api/v1/memory/admin/gdpr-delete
```

### 14.3 运行时调试

```
GET /api/v1/conversation/{id}/memory-injection
  → 返回本次请求实际注入给 LLM 的记忆块（透明度）
```

---

## 15. 前端 UX

### 15.1 "我的记忆"主页

左侧 Tab：
- **全部**（含 KV 平铺 + semantic 卡片 + episodic 时间线合并）
- **偏好**（category=preference）
- **事实**（category=fact）
- **关系**（category=relationship）
- **提醒**（category=reminder）
- **待确认**（status=pending）
- **已归档**

每条展示：内容、类别、来源（user/agent 图标）、置信度条、创建时间、引用次数；行内可编辑 / 删除 / 归档。

### 15.2 对话内小卡片

见 §10.2 反思确认。

### 15.3 记忆证据链（引用跳转）

当 agent 答案里出现 `<cite memory="123">`，前端渲染为小徽标 `🧠`，点击展示气泡：

```
[偏好] 用中文回复
来源: 用户 · 2026-04-01
被引用: 34 次
[ 查看 ] [ 修改 ] [ 删除 ]
```

### 15.4 管理员后台

- 租户/app/team/user 选择器
- 按 scope 浏览、编辑、删除记忆
- 统计卡片：记忆总数 / pending / 本月新增 / 平均 ref_count
- 审计日志视图

---

## 16. 运行时改造（`agent_app.py`）

### 16.1 `_prepare` 新增

```python
def _prepare(self, db, req, request_type):
    # ... 现有逻辑 ...
    # run_ctx: AgentRunContext —— 由入口层统一构造（见 tool-approval-and-acl-design.md §3.0）
    # 禁止再用 RequestContext 生造 conversation_id/tenant_id/team_ids

    memory_cfg = app_config.get("memory") or {}
    if memory_cfg.get("enabled") and settings.memory_enabled:
        # 1. L1 静态记忆：MemoryService 返回只读 memory block 和可选虚拟 FileData。
        #    P0 推荐由 MemoryInjectionMiddleware 直接注入文本，不启用 deepagents 原生
        #    MemoryMiddleware 的可写记忆提示，避免 edit_file 写入 checkpoint 虚拟文件。
        memory_bundle = self._memory_service.build_l1_bundle(run_ctx)
        if memory_bundle.use_deepagents_memory:
            agent_kwargs["memory"] = memory_bundle.sources             # list[str]
            payload.setdefault("files", {}).update(memory_bundle.files)  # dict[path, FileData]

        # 2. 工具
        memory_tools = self._memory_toolset.build(run_ctx, app.id)
        tools.extend(memory_tools)

        # 3. 注入 / 反思 middleware
        agent_kwargs.setdefault("middleware", []).extend([
            MemoryInjectionMiddleware(self._memory_service, run_ctx, memory_cfg),
            MemoryReflectionMiddleware(self._memory_service, run_ctx, memory_cfg),
        ])

    agent = create_deep_agent(**agent_kwargs)
```

`MemoryService.build_l1_bundle` 伪代码：

```python
@dataclass
class L1Bundle:
    sources: list[str]                   # e.g. ["/memory/org/AGENTS.md", "/memory/user/{uid}/AGENTS.md"]
    files: dict[str, FileData]           # StateBackend 的虚拟 FileData，内容取自 DB / 对象存储
    rendered_block: str                  # 推荐 P0 路径：由自研 MemoryInjectionMiddleware 注入
    use_deepagents_memory: bool = False  # 默认 false，避免原生 MemoryMiddleware 诱导 edit_file 写入

def build_l1_bundle(run_ctx: AgentRunContext) -> L1Bundle:
    paths = []
    files = {}
    # 从 org → team → app → user 顺序加载
    for scope_path, content in self._load_l1_layers(run_ctx):
        paths.append(scope_path)
        if content:
            files[scope_path] = create_file_data(content)
    return L1Bundle(sources=paths, files=files)
```

### 16.1.1 `tenant_id` NULL 语义

P0/P1 默认 `tenant_id=None`（单租户假设）。所有 MemoryService 查询必须避免 `WHERE tenant_id = :tid`（NULL 等值不命中），统一规则：

- **Runtime 侧**：`AgentRunContext.tenant_id` 为 None 时，注入 `WHERE tenant_id IS NULL`；非 None 时注入 `WHERE tenant_id = :tid`
- **可选规范化**：也可把 P0 所有行落 `tenant_id=0`（常量默认租户）并在 `build_l1_bundle` / `evaluate` 入口把 None 归一化为 0；二者择一在 `MemoryService._normalize_tenant()` 里实现，全项目一致
- 本文档示例 SQL 里的 `tenant_id = :tid` 默认为已归一化版本（tenant_id=0 或真实 id）；保留 NULL 的话必须改成 `tenant_id IS NOT DISTINCT FROM :tid`

### 16.2 SSE 事件补充

| 事件 | 时机 |
|---|---|
| `memory_candidate` | ReflectionMiddleware 产出候选 |
| `memory_cited` | 模型输出含 `<cite memory="...">` |
| `memory_written` | 用户/agent 写入成功 |

---

## 17. 性能与可扩展性

### 17.1 注入延迟

`MemoryInjectionMiddleware` 每次请求可能查 L1+L2+L3+L4。目标拆分：
- L1/L2 纯数据库/缓存注入：p95 < 50ms。
- L3/L4 语义召回（含 embedding + pgvector）：p95 < 300-800ms，具体按模型网关延迟校准。
- 对首 token 延迟的总增量：p95 < 1s。
- embedding 服务异常或超时时跳过 L3/L4，只注入 L1/L2，不能阻断主对话。

优化：
- L2 按 `(scope_type, scope_id)` 拉全表进程内缓存（每用户量小，<1K 条）
- L3 / L4 的 embedding 查询单 SQL 合并（`UNION ALL` + 统一 rank）
- Embedding 当前 user query → 走 LiteLLM，若延迟过高用进程内 LRU 缓存（key=hash(query)）

### 17.2 向量索引容量

`pgvector ivfflat` 百万级性能够；千万级考虑切分表（分 user bucket）或迁 HNSW。`retention_days` 配合后台清理控制规模。

### 17.3 Embedding 成本

- 批量调用：一批请求合并 → 一次 embeddings API
- 去重：相似度 > 0.92 不新建 → 省一次调用
- 增量：KV 类仅在 `value` 变更时重算（KV 不需要 embedding 即可查，L2 无向量列）

### 17.4 横向扩展

MemoryService 无状态，可多副本；后台任务（Compactor / EpisodicSummarizer）用分布式锁（PG advisory lock）保证单点执行。

---

## 18. 兼容与回滚

- `settings.memory_enabled=false`（默认） → 全局关，middleware 不挂
- `app_config.memory.enabled=false` → 单应用关
- Layer 级别开关 → `app_config.memory.layers.{files|kv|semantic|episodic|reflection}=false`
- 回滚：关 flag 即可；已有记忆数据留库不影响
- Alembic 迁移可独立 downgrade（drop tables + drop vector 扩展留着不影响）

---

## 19. 测试要点

| 场景 | 预期 |
|---|---|
| 首次对话无记忆 | 注入块为空，agent 正常回复 |
| 用户写 KV | 后续对话注入生效 |
| Agent reflection 产出 pending | 不自动生效，用户确认后生效 |
| 冲突：用户新 value 覆盖旧 | 旧版归档可回滚 |
| 语义去重 | 相似度 > 0.92 不新建，ref_count 加 1 |
| Episodic 召回 | 新会话能引用 7 天前会话摘要 |
| 注入超 budget | 按重要性截断，不溢出 |
| GDPR 删除 | 所有 scope=user 记忆清空，审计保留 |
| 租户隔离 | 跨租户查被 deny |
| PII 脱敏 | 敏感记忆在审计里显示占位符 |
| 并发写同 key | 冲突策略生效 |
| Embedding 服务挂 | 降级：L3/L4 召回跳过，L1/L2 仍注入 |
| L1/L2 注入延迟 | p95 < 50ms |
| L3/L4 语义召回延迟 | p95 < 300-800ms |
| Embedding 服务超时降级 | 仅注入 L1/L2，流不中断 |
| 压缩任务 | 每日衰减 / 合并 / 过期正确执行 |
| 引用徽标 | 用户点击能跳转到原记忆 |

---

## 20. 分期落地

| 阶段 | 范围 | 主要产出 |
|---|---|---|
| **P0** | L1（AGENTS.md 文件）+ 管理员编辑 UI | 立即见效，最低风险 |
| **P1** | L2（KV）+ 用户端编辑 + 基础注入 | 显性偏好能力 |
| **P2** | L3（semantic）+ 嵌入 + 语义召回 | 跨会话自由记忆 |
| **P3** | Reflection + pending 确认小卡片 | agent 自动学习 |
| **P4** | L4（episodic）+ 后台摘要任务 | 跨会话回忆 |
| **P5** | 压缩 + 衰减 + GDPR + 审计大盘 | 治理与合规闭环 |
| **P6** | 跨租户管理 / 导入工具（Slack / 文档）/ 引用证据链 | 生态扩展 |

P0 可两周上线；P1-P2 一季度内；P3-P5 视反馈节奏；P6 视业务需要。

---

## 21. 与其他设计的联动

- `long-session-design.md`：checkpoint 存"当前会话工作记忆"；本设计存"跨会话长期记忆"。两者互补，都通过 `_prepare` 挂载。
- `tool-approval-and-acl-design.md`：`remember` / `forget` 等工具经过策略引擎；高敏记忆注入前需过 PII/DLP。
- `skill-management-design.md`：Skill 是"怎么做"；Memory 是"知道什么"。Skill 的 SKILL.md 放 `/skills/...`，Memory 的 AGENTS.md 放 `/memory/...`。
- `observability-design.md`：注入大小 / 命中率 / 衰减统计进 Langfuse + Prometheus。
- RAGFlow：可作为外部知识工具挂入 agent，与 Memory 独立。

---

## 21.1 PR-M1 实施记录（**首版交付**）

设计文档原稿覆盖 L1–L5 五层、reflection / pending / 语义召回 / GDPR 全套。**首版只交付最小骨架**——结构化 KV（对应原设计 L2），其余层暂未实施。

### 实际范围

- **存储**：`tb_memory(scope, scope_id, memory_key, memory_value, source, ...)` + `tb_memory_audit`（追加写）。alembic 迁移 `0009_memory_kv.py`
- **scope**：仅 `user` + `app` 两层；`team` / `org` / `tenant` 不在第一版（依赖 `RequestContext` 扩展）
- **注入**：`MemoryInjectionMiddleware` 在 `wrap_model_call` 前查 DB 各取 user / app top-N（默认 20，硬编码），渲染成 `<agent_memory>` 段落附到 system prompt
- **写入**：agent 自带 `remember` / `forget` / `list_my_memories` 三个工具，`scope` 锁死为 `user`、`scope_id` 锁死为当前 user_id（避免模型污染 app 级 prompt）
- **API**：`/api/v1/memory` GET / PUT / DELETE / `/audit` / `/_self`（自助 GDPR）
- **鉴权**：user-scope 只允许自己；app-scope 只允许 `tb_app.create_user == 当前 user`（owner）
- **前端**：`MemoryView.vue` 提供"我的记忆 / 应用记忆 / 审计 / 一键清空"
- **subagent 不注入**（避免污染技能行为；技能子代理拿到 task 描述里已含相关上下文）
- **tests**：`backend/tests/test_memory.py` 9 个纯逻辑用例（rendering、tool factory、Pydantic 校验），全部 pass

### 显式不做（与原设计 §3-§9 偏离）

- **L1 静态文件 + deepagents `MemoryMiddleware`**：用 admin 写入的 `scope='app'` KV 替代；不读磁盘 markdown
- **L3 语义记忆 + pgvector**：本期不做 embedding；recall 等价于 list（按 update_time desc）
- **L4 情景摘要**：交给 checkpointer summarization；本设计不再单独抽
- **L5 反思 pending 区**：agent 工具直接 upsert，没有 admin pre-approval 环节
- **复合 PII 策略 + 跨应用共享 + 加密分级**：未实现，按 `tool-approval-and-acl-design.md` §6.4 punch list 的 PII 增强一并跟进

### 演进路径（按需启用，不强排）

| 触发信号 | 增量动作 |
|---|---|
| 用户记忆超 50 条/人，注入裁剪偏差大 | 加 `pinned: bool` 列；按 pinned 优先 + recency 次之策略 |
| 出现"找类似过往交流"诉求 | L3 上 pgvector：`tb_memory` 加 `embedding vector(N)`；recall 改 hybrid |
| 出现 team / org 共享需求 | 扩 `RequestContext.team_ids`；`scope` 增 `team` 枚举值 + 对应 owner 模型 |
| 模型频繁误记瞬时事实 | L5 pending：`source='agent_learned'` 默认进 pending，admin 审批后转 active |
| 合规要求显式分级 | 加 `sensitivity` 列；高敏走专用注入（仅本地模型） |

### M1 punch list（暂不做）

- DB-touching 集成测试（service upsert / delete / purge / audit 行写入校验）需要 pytest-postgresql 或 SQLite-in-memory 切换 ORM；与 PR-G11 的工具治理测试一同补
- 注入 budget 控制（按 token 数而非条数）：先用条数兜底
- API 鉴权 admin 维度：等 user_role（PR-G10）落地后扩展

---

## 22. 风险与未决

1. **Reflection 误抽取**：LLM 可能把临时信息当偏好（"用户现在心情不好"不应入 memory）。缓解：提示词约束 + pending 机制 + 用户拒绝样本回流调优。
2. **记忆漂移**：老记忆与新事实矛盾未被识别。缓解：冲突检测时触发用户二次确认。
3. **Embedding 模型升级**：换模型需全量重算 embedding。方案：双写过渡期；`embedding_model` 字段区分版本。
4. **高敏数据的加密边界**：注入到 LLM 时必然解密，云厂商或 proxy 可能看到。缓解：高敏层级走本地私有模型。
5. **跨应用共享尺度**：用户在 app A 告诉 agent "我的预算 10k"，app B 是否该看到？默认不共享，除非用户显式配置"跨应用共享"。
6. **Reflection 触发成本**：每轮都跑抽取成本可观。推荐策略：只在对话前 3 轮或用户显式说"记住"时触发。
7. **注入 token 预算与答案质量**：预算太小丢重要记忆、太大挤占答案空间。建议初期 2K、根据实际反馈调整。
