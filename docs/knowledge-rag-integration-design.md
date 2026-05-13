# 知识库 × RAGFlow 集成方案

本文档用于描述 easy-ai 知识库模块的整体集成方案：以 RAGFlow 为底层 RAG 引擎，由 easy-ai 自研管理面承担业务建模、权限、生命周期治理与对外 API，RAGFlow 负责文档解析、分块、向量化、检索。

> 相关文档：`system-architecture.md`、`king-coding.md`、`app-factory-design.md`（RAG 应用绑定 `kb_ids`）、`tool-management-design.md`、`backend-design.md`。

---

## 1. 设计目标与原则

| 维度 | 目标 |
|------|------|
| **职责清晰** | RAGFlow 只做"知识工程"（parse / chunk / embed / retrieve），easy-ai 做"知识治理"（业务建模、权限、来源管理、对外 API） |
| **低耦合** | easy-ai 与 RAGFlow 通过 HTTP REST 解耦；RAGFlow 升级不影响 easy-ai 业务逻辑 |
| **可降级** | RAGFlow 不可用时，easy-ai 自身依然能运行 —— 知识库列表/详情等读路径降级到本地缓存 |
| **多租约束** | **软隔离**：RAGFlow 侧只用一个平台账号（单 tenant），easy-ai 层用 `owner` + 权限码做可见性过滤；不依赖 RAGFlow tenant 做硬隔离，避免 SDK 复杂度与跨租户运维成本 |
| **对外稳定** | easy-ai 暴露给前端 / 外部业务系统的 API 路径与字段是**契约**，与 RAGFlow 内部表示完全解耦 |

设计原则：
- **1:1 映射**：一个 easy-ai 知识库 ≡ 一个 RAGFlow Dataset。前端"分类"只是 RAGFlow document 的 `meta_fields` 或 tag，不在 easy-ai 单独建表。
- **强一致字段、弱一致计数**：`ragflow_dataset_id` / `ragflow_doc_id` 等映射 ID 强一致写入；`doc_count` / `chunk_count` 等统计字段最终一致（定时回填 + 关键写后立即拉取）。
- **写操作以 RAGFlow 为准**：先写 RAGFlow（拿到对方 ID），再回写 easy-ai 本地表。失败回滚或标记 `pending_sync`。
- **读操作以 easy-ai 为准**：列表/详情读 easy-ai 本地表，只在打开文档详情、查看 chunk、检索测试时回源 RAGFlow。

---

## 2. 部署架构

### 2.1 进程拓扑

```
┌──────────────────────────────────────────────────────────────────┐
│ deploy/docker-compose.yml — 单一编排文件                         │
│                                                                  │
│  easy-ai-frontend ──HTTP──> easy-ai-backend                      │
│                                  │  REST (Bearer API Key)        │
│                                  ▼                               │
│                              ragflow (:9380)                     │
│                                  │                               │
│                ┌─────────────────┼─────────────────┐             │
│                ▼                 ▼                 ▼             │
│         ragflow-mysql     ragflow-es          minio / redis      │
│         (独立)            (独立, ES 8.11)     (复用)             │
│                                                                  │
│  共享基础设施(easy-ai 自有):                                      │
│    postgres / clickhouse / minio / redis                         │
└──────────────────────────────────────────────────────────────────┘
```

实际服务命名（见 `deploy/docker-compose.yml`）：
- `easy-ai-ragflow` — RAGFlow 主进程（HTTP API + Web UI + task executor）
- `easy-ai-ragflow-mysql` — 专属 MySQL 8.0.39
- `easy-ai-ragflow-es` — 专属 Elasticsearch 8.11.3
- 复用 `easy-ai-minio`（按 `MINIO_PREFIX_PATH=ragflow/` 隔离）+ `easy-ai-redis`（RAGFlow 用 db=1，langfuse 用 db=0）

### 2.2 复用与隔离取舍

| 服务 | 策略 | 理由 |
|------|------|------|
| RAGFlow 主服务 | **独立容器**：`easy-ai-ragflow` | 镜像即官方发行版（`infiniflow/ragflow:v0.24.0`），不二次封装；通过 env 注入连接参数 |
| RAGFlow MySQL | **独立容器**：`easy-ai-ragflow-mysql` | RAGFlow 强依赖 MySQL schema，与 easy-ai PostgreSQL 解耦；避免跨 DB 兼容性问题 |
| RAGFlow ES | **独立容器**：`easy-ai-ragflow-es`（Elasticsearch 8.11.3） | 锁定 ES，不引入 Infinity（生态/稳定性优先）；现网 langfuse 用 ClickHouse 不冲突 |
| Embedding 推理 | **外部服务**，不部署 TEI | 由 LLM 管理中已注册的外部 embedding provider（OpenAI-API-Compatible 等）承担；省一个重量级容器，模型升级走 LLM 管理而非动镜像 |
| MinIO | **共享，prefix 隔离** | 复用 `easy-ai-minio`，使用 `MINIO_PREFIX_PATH=ragflow/` 与 langfuse 数据物理分离 |
| Redis | **共享，DB 隔离** | 复用 `easy-ai-redis`，RAGFlow 内部使用 db=1（其 `service_conf.yaml.template` 默认值），langfuse 仍走 db=0 |

> 共享 MinIO/Redis 是为了减少容器数与运维面，**强相关数据**（MySQL/ES）独立部署以避免 RAGFlow 升级时影响 easy-ai 数据。

### 2.3 端口规划（沿用 188xx 段）

| 服务 | 容器端口 | 宿主端口 | 暴露范围 |
|------|----------|----------|----------|
| ragflow API | 9380 | `127.0.0.1:18040` | 仅本机调试 / 运维 |
| ragflow Web UI | 80 | `127.0.0.1:18044` | 仅运维直访 |
| ragflow-es | 9200 | `127.0.0.1:18041` | 仅运维排障 |
| ragflow-mysql | 3306 | `127.0.0.1:18045` | 仅运维排障 |

> 前端不直连 RAGFlow，所有调用经 `easy-ai-backend` 代理；故 RAGFlow 不向外网暴露。

### 2.4 .env 新增

`deploy/.env.example` 已加入下列变量段（实际值请参考模板）：

```env
# ---- RAGFlow ----
RAGFLOW_ENABLED=true
RAGFLOW_IMAGE=ghcr.io/<org>/ragflow:v0.24.0-easyai   # fork + trusted-header
RAGFLOW_TIMEOUT_SEC=30
RAGFLOW_MYSQL_PASSWORD=<random>
RAGFLOW_ES_PASSWORD=<random>
RAGFLOW_ES_MEM_LIMIT=4g

# RAGFlow 鉴权(详见 §3)
EASYAI_TRUSTED_HEADER=true
EASYAI_SHARED_SECRET=<openssl rand -hex 24>       # backend 与 ragflow 容器共用
EASYAI_BOOTSTRAP_EMAIL=easyai@system.local
EASYAI_BOOTSTRAP_NICKNAME=easyai-system
EASYAI_BOOTSTRAP_PASSWORD=                        # 留空 = 启动时随机
```

`easy-ai-backend` 容器内进一步约定（compose 已写死，无需 env 暴露）：
- `RAGFLOW_BASE_URL=http://ragflow:9380` —— 容器内地址，不出网。

> **不部署 TEI**：`docker-compose` 不引入 `tei-cpu` / `tei-gpu`。embedding 模型完全由 LLM 管理（`system:llm`）维护，RAGFlow 仅作为消费方。
>
> **首个 embedding 注册**：在 RAGFlow 启动期的 `easyai_bootstrap` 钩子里（§3.2）通过 `/v1/llm/add_llm` 注册一个 OpenAI-API-Compatible provider；其 API key / base URL 来自 `.env` 提供的 `RAGFLOW_BOOTSTRAP_EMBEDDING_*` 变量。若部署时 LLM 管理还未初始化，可跳过此步，待管理员在前端"系统配置 → LLM 管理"补齐后由 §5.7 的双向同步触发。

### 2.5 首次部署 bootstrap

RAGFlow 启动期会自动跑 `easyai_bootstrap` 钩子（fork 增加，见 §3.2）：
1. 检查 `Tenant` 表为空 → 自动建默认 user / tenant，邮箱 `easyai@system.local`，密码由 `EASYAI_BOOTSTRAP_PASSWORD` 决定。
2. 检查可用 embedding 模型 → 若为空且 `.env` 配置了 `RAGFLOW_BOOTSTRAP_EMBEDDING_*` → 调用内部服务直接写入默认 embedding。

完成后 RAGFlow 即处于"已初始化"状态。easy-ai-backend 调任何 `/v1/*` API 时只需带上 HMAC trusted header 即可，无需 register / login / new_token 任何动态步骤。详见 §3。

---
## 3. 认证集成方案（fork + trusted-header）

对 RAGFlow 源码做**最小 fork 改造**，仿照 Flowise 已经走通的 `easyaiTrustedHeaderAuth` 模式：让 RAGFlow 内置一个"看见正确签名就以默认管理员身份过审"的中间件，并在启动时自动建好默认用户/租户/embedding。改造完成后，easy-ai-backend 与 RAGFlow 之间只剩一套 HMAC 共享密钥，运行时无任何动态状态，部署体验对齐 Langfuse。

### 3.1 设计取舍：为什么 fork

RAGFlow 原生鉴权是"register → login → new_token → Bearer"四步动态流程，password 还要 RSA 加密。不 fork 的方案需要在 easy-ai 侧维护整套 bootstrap 状态机、token 缓存、`tb_setting` 加密落库、401 自愈逻辑——对运维不透明、对一致性敏感。fork 一次解决得彻底：

| 维度 | 不 fork（动态 bootstrap） | **fork + trusted-header（本方案）** |
|------|---------|---------|
| RAGFlow 侧改动 | 0 行 | ~120 行 Python（startup hook + 中间件 + 2 个 env）|
| easy-ai 侧鉴权代码 | RSA、register、login、new_token、tb_setting、401 自愈 ~300 行 | 一个 30 行的 HMAC 签名函数 |
| 运行时状态 | Token 落 DB，env 与 DB 不一致风险 | 完全无状态，env 即真相 |
| 容器重建后行为 | 检查 env / DB 决定是否再 bootstrap | 与 Langfuse 一致：env 注入即可，每次启动幂等 |
| 故障恢复 | 401 → 重 register/login/new_token；DB 与 RAGFlow 实际不一致需要"重建 Token"按钮 | RAGFlow 数据被清 → 启动 hook 自动重建默认 user/tenant，零运维 |
| RAGFlow 升级 | 需重测整个 bootstrap 链路 | 中间件 + bootstrap 都是独立文件，rebase 冲突点固定 |

fork 是已经在 Flowise 上验证可行的模式（参见 `Flowise/packages/server/src/enterprise/middleware/easyai/trustedHeaderAuth.ts` + `enterprise/utils/easyaiBootstrap.ts`），把同一套思路平移到 RAGFlow。

### 3.2 RAGFlow 侧改造

代码组织（路径以 fork 仓库为参照）：

```
api/
├── apps/__init__.py        ← 在 _load_user() 顶部插入 trusted-header 短路（~25 行）
├── apps/easyai/
│   ├── __init__.py
│   ├── trusted_header.py   ← HMAC 校验 + 默认管理员加载
│   └── bootstrap.py        ← 启动期保证默认 tenant/user/embedding 存在
└── ragflow_server.py       ← 启动 hook 调用 easyai_bootstrap()（~3 行）
docker/.env                 ← 加 EASYAI_TRUSTED_HEADER / SHARED_SECRET 等
```

**改造点 1 — `_load_user()` 短路**（`api/apps/__init__.py`）

RAGFlow 当前的 `_load_user()` 同时承担"JWT session"与"Bearer APIToken"两条路。我们在最顶部再加一个分支：

```python
def _load_user():
    g.user = None
    # ── EASYAI-PATCH: trusted-header short circuit ──────────────────
    # 仅当 EASYAI_TRUSTED_HEADER=true 时启用。验证 HMAC 签名后,
    # 加载默认管理员到 g.user,后续 @login_required / @token_required
    # 一律放行;不改动任何上游 endpoint。
    if os.environ.get("EASYAI_TRUSTED_HEADER") == "true":
        from api.apps.easyai.trusted_header import try_load_trusted_user
        u = try_load_trusted_user(request)
        if u is not None:
            g.user = u
            return u
    # ── /EASYAI-PATCH ───────────────────────────────────────────────

    # ...保留原有 JWT / APIToken 逻辑作为 fallback,运维直访 UI 走原路。
```

**改造点 2 — `trusted_header.py`**（新增，~50 行）

```python
# api/apps/easyai/trusted_header.py
import hashlib
import hmac
import logging
import os
import time

from api.db.services.user_service import UserService
from api.db.constants import StatusEnum

# 头部协议(与 easy-ai-backend ragflow_client.py / Flowise trustedHeaderAuth 对齐):
#   X-EasyAI-User       — 业务侧 user id (snowflake), 仅审计日志, 不参与签名验证用户
#   X-EasyAI-Ts         — unix-ms 时间戳; 与本地时间相差 > 60s 拒绝(防重放)
#   X-EasyAI-Sign       — hex(hmac_sha256(EASYAI_SHARED_SECRET, f"{user}.{ts}"))

_logger = logging.getLogger(__name__)
_SKEW_MS = 60_000


def _verify_signature(user: str, ts: str, sig: str) -> bool:
    secret = os.environ.get("EASYAI_SHARED_SECRET", "")
    if not secret:
        _logger.warning("[easyai] EASYAI_SHARED_SECRET empty; rejecting all trusted headers")
        return False
    try:
        if abs(int(time.time() * 1000) - int(ts)) > _SKEW_MS:
            return False
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), f"{user}.{ts}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def try_load_trusted_user(req):
    sig = req.headers.get("X-EasyAI-Sign")
    if not sig:
        return None
    user_hint = req.headers.get("X-EasyAI-User", "")
    ts = req.headers.get("X-EasyAI-Ts", "")
    if not _verify_signature(user_hint, ts, sig):
        return None
    email = os.environ.get("EASYAI_BOOTSTRAP_EMAIL", "easyai@system.local")
    users = UserService.query(email=email, status=StatusEnum.VALID.value)
    if not users:
        _logger.error("[easyai] trusted-header: default user %s missing; bootstrap failed?", email)
        return None
    return users[0]
```

**改造点 3 — `bootstrap.py`**（新增，~70 行；启动期幂等）

```python
# api/apps/easyai/bootstrap.py
import logging
import os
import secrets

from api.db.services.user_service import UserService, TenantService
from api.db.services.llm_service import TenantLLMService

_logger = logging.getLogger(__name__)


def easyai_bootstrap():
    """RAGFlow 启动时跑一次, 保证 trusted-header 中间件所需的默认账户存在。
    幂等:已存在则跳过。Flowise easyaiBootstrap.ts 的等价物。"""
    if os.environ.get("EASYAI_TRUSTED_HEADER") != "true":
        return

    email = os.environ.get("EASYAI_BOOTSTRAP_EMAIL", "easyai@system.local")
    nickname = os.environ.get("EASYAI_BOOTSTRAP_NICKNAME", "easyai-system")
    password = os.environ.get("EASYAI_BOOTSTRAP_PASSWORD") or secrets.token_hex(16)

    if not UserService.query(email=email):
        UserService.register(
            email=email, nickname=nickname,
            password_hash=UserService.hash_password(password),
            is_active="1",
        )
        _logger.info("[easyai] bootstrap: default user %s created", email)
    else:
        _logger.info("[easyai] bootstrap: default user %s already exists", email)

    # 注册默认 embedding(可选)
    emb_name = os.environ.get("RAGFLOW_BOOTSTRAP_EMBEDDING_NAME")
    if emb_name:
        user = UserService.query(email=email)[0]
        tenant = TenantService.query(user_id=user.id)[0]
        if not TenantLLMService.query(tenant_id=tenant.tenant_id, llm_name=emb_name):
            TenantLLMService.register_external(
                tenant_id=tenant.tenant_id,
                factory="OpenAI-API-Compatible",
                llm_name=emb_name,
                model_type="embedding",
                api_base=os.environ.get("RAGFLOW_BOOTSTRAP_EMBEDDING_API_BASE", ""),
                api_key=os.environ.get("RAGFLOW_BOOTSTRAP_EMBEDDING_API_KEY", ""),
            )
            _logger.info("[easyai] bootstrap: default embedding %s registered", emb_name)
```

> 注：以上 service 方法签名是参照 RAGFlow 现有 `UserService.register` / `TenantLLMService.save` 风格的伪码，真正 fork 时按 master 当前 API 调整。

**改造点 4 — `ragflow_server.py` 启动 hook**

```python
# api/ragflow_server.py 启动收尾处:
from api.apps.easyai.bootstrap import easyai_bootstrap
try:
    easyai_bootstrap()
except Exception:
    logging.exception("[easyai] bootstrap failed; continuing without easyai-trust")
```

**改造点 5 — env 变量**

加在 `docker/.env`：

```env
EASYAI_TRUSTED_HEADER=true
EASYAI_SHARED_SECRET=<32-byte hex 与 easy-ai-backend 对齐>
EASYAI_BOOTSTRAP_EMAIL=easyai@system.local
EASYAI_BOOTSTRAP_NICKNAME=easyai-system
EASYAI_BOOTSTRAP_PASSWORD=                # 可选,留空 = 随机
RAGFLOW_BOOTSTRAP_EMBEDDING_NAME=
RAGFLOW_BOOTSTRAP_EMBEDDING_API_BASE=
RAGFLOW_BOOTSTRAP_EMBEDDING_API_KEY=
```

**fork 仓库与 Docker 镜像**：把 `eoitek-llm/ragflow-ref/`（当前是 shallow clone 只读）替换为 git submodule 指向我方 fork，与 `Flowise/` 同结构；CI 构建 `ghcr.io/<org>/ragflow:vX.X.X-easyai`，`deploy/docker-compose.yml` 的 `RAGFLOW_IMAGE` 切到该 tag。

### 3.3 身份模型：平台单租

- RAGFlow 侧只创建**一个**账户 `easyai@system.local`（由 `easyai_bootstrap()` 保证），所有 dataset/document/chunk 的 `created_by` 都是它。
- end-user 身份不传入 RAGFlow，所有可见性 / 配额 / 删除权限的判断在 easy-ai 层：`tb_kb.create_user` + 权限码 `kb:edit / kb:publish + *`。
- `X-EasyAI-User` 头部仍带上真实 user id，但仅用于 RAGFlow 侧的日志审计，不参与 ACL 决策。
- 这一选择隐含的代价：RAGFlow 内置的协作 / 多 tenant / OAuth 全部用不上。若未来要硬隔离（例如 SaaS 化），改造点局限于中间件的 user 选择逻辑，业务模型不动。

### 3.4 easy-ai-backend 侧调用

只剩一个 client 文件，与 `flowise_client.py` 几乎完全对称：

```python
# app/integration/ragflow_client.py
import hashlib, hmac, time
import httpx
from app.core.config import settings


def _sign(user_id: str, ts_ms: int) -> str:
    return hmac.new(settings.ragflow_shared_secret.encode(),
                    f"{user_id}.{ts_ms}".encode(), hashlib.sha256).hexdigest()


def _headers(user_id: int | str | None) -> dict[str, str]:
    ts = int(time.time() * 1000)
    uid = str(user_id or 0)
    return {
        "Content-Type": "application/json",
        "X-EasyAI-User": uid,
        "X-EasyAI-Ts":   str(ts),
        "X-EasyAI-Sign": _sign(uid, ts),
    }


class RagflowClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base = base_url.rstrip("/") + "/api/v1"
        self._client = httpx.AsyncClient(timeout=timeout)

    async def create_dataset(self, name: str, ctx, **kw) -> dict:
        r = await self._client.post(
            f"{self._base}/datasets", headers=_headers(ctx.user_id),
            json={"name": name, **kw},
        )
        r.raise_for_status()
        return r.json()["data"]

    # ...其余方法 1:1 映射 /v1/datasets/* /v1/documents/* /retrieval 等
```

行为约定：
- 每次请求从 `RequestContext` 取真实 user_id 用作 `X-EasyAI-User`（审计可追溯）。
- 401 / 5xx / 网络错误都按上游错误**直接抛出**，不再自愈；上层 service 决定是否降级。
- 没有 `RagflowAuth` 状态机，没有 token 缓存，没有 `tb_setting.ragflow.*`。

### 3.5 与 Flowise / Langfuse 横向对比（最终形态）

| 维度 | Flowise | Langfuse | RAGFlow（本方案）|
|------|---------|----------|------------------|
| **底层鉴权** | HMAC trusted-header（fork 后内置中间件）| Project public/secret key（env 注入）| HMAC trusted-header（fork 后内置中间件，与 Flowise 同形态）|
| **fork 改动** | ~100 行 enterprise 中间件 + bootstrap | 0（原生支持 `LANGFUSE_INIT_*`）| ~120 行 enterprise 中间件 + bootstrap |
| **密钥来源** | `FLOWISE_SHARED_SECRET` env，双方对齐 | `LANGFUSE_INIT_PROJECT_*` env，langfuse 首次写库 | `EASYAI_SHARED_SECRET` env，双方对齐 |
| **运行时状态** | 无 | 无 | 无 |
| **前端嵌入** | 是（反代 `/flowise/*`） | 否 | 否（RAGFlow UI 仅运维直访）|
| **end-user 身份** | 注入 `X-EasyAI-User`（→ workspace 上下文）| 不注入；trace 自带 | 注入 `X-EasyAI-User` 仅作审计；ACL 在 easy-ai 层 |
| **失败模式** | Flowise 不可达：iframe + API 5xx | Langfuse 不可达：trace 本地缓冲 | RAGFlow 不可达：写操作 503，读降级到本地（§9）|

三套体系合到一处看：**Flowise 与 RAGFlow 形态完全一致**（都是 fork + trusted-header），Langfuse 因原生支持 init-env 是另一类。

### 3.6 失效与恢复

| 场景 | 行为 |
|------|------|
| 签名时钟漂移 > 60s | 401。运维确认两端 NTP；client 不重试。 |
| `EASYAI_SHARED_SECRET` 两端不一致 | 401。在系统配置页"测试连接"按钮快速定位。 |
| RAGFlow 数据卷被清空 | 容器重启时 `easyai_bootstrap()` 自动重建默认 user/tenant；本地 `tb_kb.ragflow_dataset_id` 指向已失效 dataset → 进入 §9 "孤儿"补偿任务。 |
| RAGFlow 升级后 service 表结构变化导致 bootstrap 失败 | 启动 hook 抛异常但**不阻塞** RAGFlow 主进程（改造点 4 的 try/except），运维看日志人工修复。 |
| 头部签名被恶意伪造 | 不可能：`EASYAI_SHARED_SECRET` 仅 backend 与 RAGFlow 容器知道；攻击面等同于"能进入 docker 内部网络"。RAGFlow 端口仍仅绑 `127.0.0.1`，外部不可达。 |

### 3.7 运维入口

`系统配置 → 知识库引擎` 页面（M3 新增），仅 `system:setting` 可见：
- **测试连接**：调 `GET /v1/system/version`（带 trusted header），200 即通。
- **重新初始化默认账户**：仅用于 RAGFlow 数据卷被运维误清的极端场景；触发 backend 调一个内部接口 → RAGFlow 内部 `/v1/easyai/reset_bootstrap`（fork 时一并加，仅 trusted header 可访问）。
- 不再有"重建 Token"按钮（无 Token 概念）。

### 3.8 配置位汇总

`deploy/.env.example`（已存在的 RAGFlow 段扩充）：

```env
# RAGFlow 鉴权(fork 后)
EASYAI_TRUSTED_HEADER=true
EASYAI_SHARED_SECRET=<openssl rand -hex 24>
EASYAI_BOOTSTRAP_EMAIL=easyai@system.local
EASYAI_BOOTSTRAP_NICKNAME=easyai-system
EASYAI_BOOTSTRAP_PASSWORD=                 # 留空 = 启动时随机

# 默认 embedding(可选,留空跳过)
RAGFLOW_BOOTSTRAP_EMBEDDING_NAME=
RAGFLOW_BOOTSTRAP_EMBEDDING_API_BASE=
RAGFLOW_BOOTSTRAP_EMBEDDING_API_KEY=
```

backend 侧 `app/core/config.py`：

```python
# RAGFlow 知识库引擎(fork + trusted-header)
ragflow_enabled: bool = Field(default=False)
ragflow_base_url: str = Field(default="http://127.0.0.1:9380")
ragflow_shared_secret: str = Field(default="change-me-easyai-ragflow")
ragflow_timeout_sec: float = Field(default=30.0)
```

compose 在 `easy-ai-backend.environment` 注入 `RAGFLOW_ENABLED` / `RAGFLOW_BASE_URL` / `RAGFLOW_SHARED_SECRET` / `RAGFLOW_TIMEOUT_SEC`；在 `ragflow` 服务 environment 注入 `EASYAI_TRUSTED_HEADER` / `EASYAI_SHARED_SECRET` / `EASYAI_BOOTSTRAP_*`。两侧 SHARED_SECRET 强约束指向同一 `${EASYAI_SHARED_SECRET}` 变量，杜绝双方对不齐。

### 3.9 fork 维护策略

- 把 `eoitek-llm/ragflow-ref/`（当前是 shallow clone 只读）替换为 **git submodule** 指向我方 fork。
- 建 `easyai-master` 分支跟踪 upstream `infiniflow/ragflow:master`；每次升级主版本时 rebase 一次。
- 所有 patch 文件加 `# EASYAI-PATCH:` 注释前缀，便于 grep 定位 rebase 冲突。
- 涉及文件清单（共 4 个 + 1 个 env）固定，rebase 冲突面可控。

---

## 4. 数据模型

### 4.1 ER 概览

```
tb_kb (1) ────────── (N) tb_kb_document
              │
              ├────── (N) tb_kb_sync_log     [按需，外部 connector 才有]
              │
              └────── (N) tb_kb_app_binding  [扁平绑定表，与 tb_app 关联]
```

### 4.2 `tb_kb` —— 知识库

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGINT | 是 | Snowflake，主键 |
| `code` | VARCHAR(255) | 是 | 业务标识，唯一，全小写英文-数字-连字符 |
| `name` | VARCHAR(255) | 是 | 显示名 |
| `description` | TEXT | 否 | |
| `ragflow_dataset_id` | VARCHAR(255) | 否 | 对应 RAGFlow Dataset ID；创建中或解绑后为空 |
| `embedding_model` | VARCHAR(255) | 是 | 落库时间点的 embedding 模型；变更需重新解析 |
| `chunk_method` | VARCHAR(64) | 是 | `naive` / `qa` / `manual` / `book` / `table` / `laws`，对齐 RAGFlow |
| `parser_config` | TEXT (JSON) | 否 | RAGFlow parser_config，按 chunk_method 不同 schema 不同 |
| `doc_count` | INT | 否 | 缓存值，定时回填 |
| `chunk_count` | INT | 否 | 缓存值，定时回填 |
| `status` | VARCHAR(32) | 是 | `draft` / `ready` / `syncing` / `error` |
| `last_synced_at` | BIGINT | 否 | 最后一次与 RAGFlow 对账时间 |
| `audit columns` | | | `create_time` / `update_time` / `create_user` / `update_user` |

> **不重复存储分类**：原型中"分类"语义保留在前端，作为 `meta_fields.category` 写到 RAGFlow 文档侧；avoids two sources of truth。

### 4.3 `tb_kb_document` —— 文档

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | BIGINT | 是 | Snowflake，主键 |
| `kb_id` | BIGINT | 是 | 外键到 `tb_kb`（不加 FK 约束，与项目规范一致） |
| `name` | VARCHAR(255) | 是 | 文档名 |
| `format` | VARCHAR(32) | 是 | `PDF` / `DOCX` / `XLSX` / `MD` / `TXT` / `CSV` / `JSON` / `IMG` / `API` / `DB` |
| `size_bytes` | BIGINT | 否 | |
| `category` | VARCHAR(255) | 否 | 业务分类标签（仅做前端筛选用） |
| `source_type` | VARCHAR(32) | 是 | `file` / `ones` / `api_pull` / `api_push` / `confluence` |
| `source_meta` | TEXT (JSON) | 否 | 各 connector 私有字段：filePath / sourceUrl / syncSchedule 等 |
| `ragflow_doc_id` | VARCHAR(255) | 否 | 对应 RAGFlow Document ID |
| `parse_status` | VARCHAR(32) | 是 | `pending` / `parsing` / `done` / `error` / `cancelled`，对齐 RAGFlow run state |
| `chunks_count` | INT | 否 | 缓存值 |
| `error_message` | TEXT | 否 | |
| `audit columns` | | | |

唯一约束：`(kb_id, name)`，避免同名重复入库。

### 4.4 `tb_kb_sync_log` —— 同步日志（按需）

仅用于外部 connector（`api_pull` / `api_push` / `ones` 等），文件上传不进此表。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | |
| `kb_id` | BIGINT | |
| `source_type` | VARCHAR(32) | |
| `trigger_type` | VARCHAR(32) | `scheduled` / `manual` / `webhook` |
| `status` | VARCHAR(32) | `success` / `failed` / `partial` / `processing` |
| `docs_added` / `docs_updated` / `docs_deleted` | INT | |
| `duration_ms` | INT | |
| `error_message` | TEXT | |
| `audit columns` | | |

### 4.5 `tb_kb_app_binding` —— 应用绑定（可选）

App 与 KB 多对多绑定。也可以直接复用 `tb_app.app_config` JSON 中的 `kb_ids: string[]`（与现有 `app-factory-design.md` 一致），**初版推荐复用 JSON 字段**，等查询场景出现再独立表。

---

## 5. 后端实现

### 5.1 包结构

```
backend/app/
  core/
    config.py                # +ragflow_base_url / ragflow_shared_secret / ragflow_timeout
  integration/
    ragflow_client.py        # HTTP 客户端 + HMAC 签名(仿 flowise_client.py)
  service/
    kb_service.py            # 知识库 CRUD + RAGFlow Dataset 同步
    kb_document_service.py   # 文档上传 / 删除 / 状态回拉 / 重新解析
    kb_retrieve_service.py   # 检索（封装 RAGFlow /retrieval）
    kb_sync_service.py       # 外部 connector 同步任务 [M4]
  api/
    kb_api.py                # GET/POST /api/v1/kb
    kb_document_api.py       # /api/v1/kb/{id}/document
    kb_retrieve_api.py       # /api/v1/kb/{id}/retrieve
  model/
    kb_model.py              # Pydantic 模型
  db/
    schema.py                # +TbKb / TbKbDocument / TbKbSyncLog
  alembic/versions/
    0011_knowledge.py        # 迁移脚本
```

### 5.2 `RagflowClient`（核心层）

定位：**透明转译 HTTP**，不引入业务概念。所有方法签名贴近 RAGFlow `/api/v1` 原始接口；用 httpx 异步（与 FastAPI 一致）。

```python
class RagflowClient:
    # 每次请求注入 HMAC trusted header (X-EasyAI-User/Ts/Sign), 无需 token 状态
    def __init__(self, base_url: str, shared_secret: str, timeout: int = 30): ...

    # Dataset
    async def create_dataset(self, name: str, *, embedding_model: str, chunk_method: str,
                              description: str | None = None, parser_config: dict | None = None) -> dict: ...
    async def list_datasets(self, page: int = 1, page_size: int = 30) -> list[dict]: ...
    async def get_dataset(self, dataset_id: str) -> dict: ...
    async def update_dataset(self, dataset_id: str, *, name=None, **kwargs) -> dict: ...
    async def delete_datasets(self, ids: list[str]) -> None: ...

    # Document
    async def upload_documents(self, dataset_id: str,
                                files: list[tuple[str, bytes, str]]) -> list[dict]: ...
    async def list_documents(self, dataset_id: str, *, page=1, page_size=30, keywords=None) -> dict: ...
    async def get_document(self, dataset_id: str, document_id: str) -> dict: ...
    async def update_document(self, dataset_id: str, document_id: str, payload: dict) -> dict: ...
    async def delete_documents(self, dataset_id: str, ids: list[str]) -> None: ...
    async def parse_documents(self, dataset_id: str, ids: list[str]) -> None: ...
    async def stop_parse(self, dataset_id: str, ids: list[str]) -> None: ...

    # Chunk
    async def list_chunks(self, dataset_id: str, document_id: str, *, page=1, page_size=30) -> dict: ...

    # Retrieval
    async def retrieve(self, *, dataset_ids: list[str], question: str,
                        top_k: int = 8, similarity_threshold: float = 0.2,
                        rerank_id: str | None = None,
                        document_ids: list[str] | None = None) -> dict: ...

    # Models
    async def list_embedding_models(self) -> list[dict]: ...
```

错误处理：
- HTTP 401 → 几乎不应发生（trusted-header 全自动）；若出现说明 `SHARED_SECRET` 配错或 RAGFlow bootstrap 失败，直接抛 `ServiceError(ErrorCode.UPSTREAM_AUTH_FAILED)`，不重试。
- HTTP 其他非 2xx → `ServiceError(ErrorCode.UPSTREAM_ERROR, message=upstream.message)`。
- 超时 → `ServiceError(ErrorCode.UPSTREAM_TIMEOUT)`，service 层决定是否重试。
- 网络不可达 → `ServiceError(ErrorCode.UPSTREAM_UNAVAILABLE)`，触发降级。

### 5.3 `KbService`

关键方法签名：

```python
async def create_kb(self, db, req: KbCreateReq, ctx: RequestContext) -> KbResp:
    # 1. 校验 code 唯一
    # 2. 调 RAGFlow create_dataset，拿 dataset_id
    # 3. 落库 tb_kb（status=ready）
    # 失败回滚：若 RAGFlow 已创建但本地落库失败，记录补偿任务（异步删 dataset）

async def update_kb(self, db, kb_id: int, req: KbUpdateReq, ctx) -> KbResp:
    # name / description 直接改本地 + RAGFlow
    # embedding_model 或 chunk_method 变更：禁止变更或要求"清空文档"前置条件
    #   （RAGFlow 不允许 in-place 切换 embedding，必须重建 dataset）

async def delete_kb(self, db, kb_id: int, ctx) -> None:
    # 1. 调 RAGFlow delete_datasets
    # 2. 本地软删（也可直接物理删，与项目其他模块对齐）

async def refresh_stats(self, db, kb_id: int) -> None:
    # 拉 RAGFlow get_dataset 回填 doc_count / chunk_count

def list_kb(self, db, req: KbPageReq, ctx) -> tuple[list[KbResp], int]: ...   # 读本地表+owner过滤
def get_kb(self, db, kb_id) -> KbResp: ...
```

### 5.4 `KbDocumentService`

```python
async def upload_documents(self, db, kb_id: int, files: list[UploadFile], category: str | None, ctx) -> list[KbDocResp]:
    # 1. 读 tb_kb 取 ragflow_dataset_id
    # 2. 调 RAGFlow upload_documents（multipart），拿 doc 列表
    # 3. 异步触发 parse_documents（上传后默认开始解析）
    # 4. 落库 tb_kb_document（parse_status=parsing）
    # 5. 立即返回，不等解析完成；前端轮询或后台回拉

async def list_documents(self, db, kb_id: int, req: PageReq) -> tuple[list[KbDocResp], int]:
    # 读本地，定时回填可放后台任务
    # 若 req.refresh=true，强制拉 RAGFlow list_documents 对账

async def get_document_detail(self, db, doc_id: int) -> KbDocDetailResp:
    # 读本地 + 调 RAGFlow get_document 拿最新 parse_status / chunk_count

async def get_document_chunks(self, db, doc_id: int, page, page_size) -> list[ChunkResp]:
    # 透传 RAGFlow list_chunks

async def delete_documents(self, db, doc_ids: list[int], ctx) -> None: ...
async def reparse_documents(self, db, doc_ids: list[int], ctx) -> None: ...
```

### 5.5 `KbRetrieveService`

```python
async def retrieve(self, db, kb_ids: list[int], req: RetrieveReq) -> RetrieveResp:
    # 1. 取所有 kb 的 ragflow_dataset_id
    # 2. 校验：必须是同一 embedding_model（RAGFlow 限制）
    # 3. 调 RAGFlow /retrieval，封装结果（chunk + similarity + source doc）
```

返回字段对齐 `app-factory-design.md` 中 RAG 应用消费的"引用溯源"字段：`chunk_id` / `content` / `similarity` / `doc_id` / `doc_name` / `highlight`。

### 5.6 解析状态同步策略

RAGFlow 解析是异步的，文档的 `run` 状态为 `UNSTART/RUNNING/CANCEL/DONE/FAIL`，对应 easy-ai 的 `parse_status`。

| 策略 | 适用场景 |
|------|----------|
| **拉取式（轮询）** | 前端打开文档详情时按 ID 拉一次；前端列表页可选启用 5s 轮询 |
| **批量回拉** | 后台定时任务，每 30s 扫描 `parse_status in ('pending','parsing')` 的文档，批量 `list_documents` 回拉 |
| **Webhook** | RAGFlow 暂未稳定提供文档级 webhook；不依赖 |

初版采用 **批量回拉 + 前端按需轮询** 的组合，无需独立消息队列。

### 5.7 Embedding 模型双向同步（与 LLM 管理打通）

由于 embedding 不在 RAGFlow 内部部署，而由 LLM 管理（`system:llm`）维护的外部 provider 承担，需保持两侧一致：

| 触发动作 | 同步逻辑 |
|---------|---------|
| LLM 管理新增 embedding-capable provider/model | `LlmService.create_model` 成功后，触发 `RagflowSyncService.upsert_embedding(provider, model)` → 调 RAGFlow `/v1/llm/add_llm` 注册 |
| LLM 管理删除/禁用 embedding 模型 | 检查 `tb_kb.embedding_model` 是否仍被引用；被引用则拒绝删除（错误码 `EMBEDDING_IN_USE`），否则调 RAGFlow `/v1/llm/delete_llm` 同步删除 |
| LLM 管理修改 API Key | 调 RAGFlow `/v1/llm/set_api_key` 仅更新凭证 |
| 创建 KB 时下拉 embedding | `GET /api/v1/kb/embedding-options` 返回 RAGFlow `/v1/llm/my_llms` 中 `model_type=embedding` 的模型；UI 上若空，引导用户先去 `系统配置 → LLM 管理` 注册 |

约束：
- **同一 KB 的 embedding 模型不可变**（RAGFlow 限制）；变更需先清空文档。
- **跨 KB 检索（同一 retrieval 请求多 dataset）要求 embedding 一致**，UI 层在选 `kb_ids` 时按 embedding 分组。

### 5.8 重要约束

| 约束 | 实现位置 | 说明 |
|------|----------|------|
| 文档上传大小限制 | `kb_document_api.py` | 单文件 ≤ 50MB，与 RAGFlow 默认一致 |
| 并发上传 | `KbDocumentService` | 同一 dataset 单次最多 20 个文档（防 RAGFlow 队列阻塞） |
| 删除级联 | `KbService.delete_kb` | 删 KB 时本地 + RAGFlow 都删；本地文档行级联删 |
| 软隔离过滤 | 所有列表/详情 API | `kb_service.list_kb` 按 `create_user` + 当前用户权限码做可见性过滤；超级管理员 (`*`) 全可见 |

---

## 6. 对外 API

接口路径与项目规范一致（`/api/v1`，资源单数）。响应统一用 `Resp[T]` / `PagedResp[T]`。

### 6.1 知识库

| 方法 | 路径 | 权限码 | 说明 |
|------|------|--------|------|
| `GET` | `/api/v1/kb/page` | `kb:edit` 或 `kb:publish` | 分页 |
| `POST` | `/api/v1/kb` | `kb:edit` | 创建（同步创建 RAGFlow Dataset） |
| `GET` | `/api/v1/kb/{id}` | 任一 | 详情，含统计 |
| `PUT` | `/api/v1/kb/{id}` | `kb:edit` | 改名 / 描述 |
| `DELETE` | `/api/v1/kb/{id}` | `kb:edit` | 删除（含 RAGFlow） |
| `POST` | `/api/v1/kb/{id}/refresh` | `kb:publish` | 触发与 RAGFlow 对账（刷新统计） |
| `GET` | `/api/v1/kb/options` | 登录 | 给应用绑定下拉用 |

### 6.2 文档

| 方法 | 路径 | 权限码 | 说明 |
|------|------|--------|------|
| `GET` | `/api/v1/kb/{id}/document/page` | `kb:edit` 或 `kb:publish` | 分页 + 按 category 过滤 |
| `POST` | `/api/v1/kb/{id}/document` | `kb:edit` | 上传（multipart，多文件） |
| `GET` | `/api/v1/kb/{id}/document/{doc_id}` | 任一 | 详情 |
| `GET` | `/api/v1/kb/{id}/document/{doc_id}/chunk` | 任一 | 分页查看 chunks |
| `POST` | `/api/v1/kb/{id}/document/{doc_id}/reparse` | `kb:publish` | 重新解析 |
| `DELETE` | `/api/v1/kb/{id}/document` | `kb:edit` | 批量删除（body 传 ids） |
| `GET` | `/api/v1/kb/{id}/document/{doc_id}/file` | 任一 | 下载原始文件（仅 source_type=file） |

### 6.3 检索测试

| 方法 | 路径 | 权限码 | 说明 |
|------|------|--------|------|
| `POST` | `/api/v1/kb/retrieve` | 登录 | body 传 `kb_ids` + `question` + 参数，返回 chunks |

### 6.4 外部 connector（M4）

预留：
- `POST /api/v1/kb/{id}/connector`（创建外部 connector）
- `POST /api/v1/kb/connector/{id}/run`（手动触发）
- `POST /api/v1/kb/ingest/push/{token}`（接收推送，token 路由）
- `GET /api/v1/kb/{id}/sync-log/page`

---

## 7. 前端实现

### 7.1 路由变更

`frontend/src/router/index.ts`：

```ts
{
  path: "knowledge",
  meta: { menu: { title: "知识库管理", ... }, permissions: KB_ANY },
  component: () => import("@/views/knowledge/KbListView.vue"),
}
{
  path: "knowledge/:id",
  meta: { title: "知识库详情", permissions: KB_ANY },
  component: () => import("@/views/knowledge/KbDetailView.vue"),
}
{
  path: "knowledge/import/:id",
  meta: { title: "导入文档", permissions: [PERM.KB_EDIT] },
  component: () => import("@/views/knowledge/KbImportView.vue"),
}
```

替换原 `MockFeatureView`。

### 7.2 页面结构（参考 prototype 简化版）

| 页面 | 关键功能 |
|------|---------|
| `KbListView` | 知识库卡片网格 / 新建按钮 / 搜索 |
| `KbDetailView` | KB 信息条 + 文档表格 + 文档详情抽屉（含 chunks 预览 tab） |
| `KbImportView` | 文件上传 wizard（M1 仅支持文件，后续扩展 connector） |
| `KbRetrieveTester`（嵌入 KbDetailView） | 输入 query → 调 `/retrieve` → 展示命中 chunks + 相似度 |

### 7.3 与应用工厂集成

RAG 应用 form（`AppFormView.vue`，当 `app_type=rag`）增加"绑定知识库"多选器 → 通过 `GET /api/v1/kb/options` 拉取下拉，提交时写入 `app_config.kb_ids`。后端 app run 时由 `RagAppRunner` 读 `kb_ids`，调 `KbRetrieveService.retrieve` 拼装 system prompt。

---

## 8. 调用链

### 8.1 上传文档

```
[用户拖拽] → KbImportView
    │
    ▼
POST /api/v1/kb/{id}/document  (multipart)
    │
    ▼ KbDocumentService.upload_documents
    │
    ├── 1. SELECT tb_kb WHERE id={id}  → 取 ragflow_dataset_id
    ├── 2. ragflow.upload_documents(dataset_id, files)  → [doc_id...]
    ├── 3. ragflow.parse_documents(dataset_id, [doc_id...])  (异步)
    └── 4. INSERT tb_kb_document(parse_status='parsing')
    │
    ▼
返回 200 + 文档列表（parse_status=parsing）

[后台定时任务，每 30s]
    │
    ▼ KbDocumentService.batch_sync_status
    │
    ├── SELECT tb_kb_document WHERE parse_status IN ('pending','parsing')
    ├── 按 kb_id 分组，ragflow.list_documents(...)
    └── UPDATE tb_kb_document SET parse_status=..., chunks_count=...
```

### 8.2 RAG 应用调用

```
[业务调用] → POST /api/v1/rag/{app_id}
    │
    ▼ RagAppRunner
    │
    ├── 1. 读 tb_app.app_config → kb_ids
    ├── 2. SELECT tb_kb WHERE id IN kb_ids → ragflow_dataset_ids
    ├── 3. ragflow.retrieve(dataset_ids, question)
    ├── 4. 构造 system prompt（拼接命中 chunks）
    ├── 5. litellm.chat.completions(...)
    └── 6. 组装 response（含引用 chunk 索引）
    │
    ▼
返回回答 + 引用列表
```

### 8.3 删除知识库

```
DELETE /api/v1/kb/{id}
    │
    ▼ KbService.delete_kb
    │
    ├── 1. ragflow.delete_datasets([dataset_id])  → 失败则 abort
    ├── 2. DELETE tb_kb_document WHERE kb_id={id}
    └── 3. DELETE tb_kb WHERE id={id}
```

---

## 9. 错误处理与降级

| 场景 | 行为 |
|------|------|
| RAGFlow 完全不可达 | 知识库**列表/详情**仍可读（本地）；上传/删除/检索返回 503 + 明确提示 |
| RAGFlow 上传成功但本地落库失败 | 后台补偿任务：扫描 RAGFlow dataset 中无本地映射的文档（"孤儿"），按策略删除或标记 |
| RAGFlow 解析失败 | 文档 `parse_status=error` + `error_message`；前端展示重试按钮 |
| Embedding 模型缺失 | 创建 KB 前校验：RAGFlow `/v1/llm/my_llms` 必须有可用 embedding 模型；缺失给出"前往系统配置注册"引导 |
| 文件超限 / 类型不支持 | API 层拒绝（不下发到 RAGFlow），错误码 `KB_FILE_REJECTED` |
| Trusted-header 校验失败（401） | 一般是 `EASYAI_SHARED_SECRET` 两端不一致或 RAGFlow bootstrap 失败；client 不重试，直接抛 `UPSTREAM_AUTH_FAILED`，前端弹出"检查配置"提示，引导运维到 `系统配置 → 知识库引擎` 点"测试连接" |

错误码新增：
- `KB_NOT_FOUND`、`KB_DUPLICATE_CODE`、`KB_RAGFLOW_DATASET_MISSING`
- `KB_DOCUMENT_NOT_FOUND`、`KB_FILE_REJECTED`、`KB_EMBEDDING_NOT_REGISTERED`、`EMBEDDING_IN_USE`
- `UPSTREAM_RAGFLOW_ERROR`、`UPSTREAM_RAGFLOW_TIMEOUT`、`UPSTREAM_AUTH_FAILED`

---

## 10. 观测

- **日志**：`logger.info("[kb] action=X kb_id=Y ragflow_dataset_id=Z ms=...")` 统一前缀 `[kb]`，便于 grep。
- **Langfuse**：检索操作可作为 RAG 应用 trace 的一个 span（`kb.retrieve`），含 `dataset_ids` / `top_k` / 命中数。
- **指标**：暴露 prometheus（可选 M5）：
  - `kb_documents_total{kb_id}`
  - `kb_parse_failures_total{kb_id}`
  - `kb_retrieve_latency_seconds`
  - `ragflow_upstream_errors_total{op}`、`ragflow_auth_bootstrap_total{result}`

---

## 11. 演进路线

| 阶段 | 范围 | 时长预估 |
|------|------|----------|
| **M1 · 最小可用** | 部署 RAGFlow + Auth bootstrap + tb_setting；KB CRUD；文件上传 + 解析；文档详情 + chunks 预览；检索测试 | 1.5 周 |
| **M2 · 应用绑定** | App Factory 中"绑定知识库"多选器；RAG 应用 runtime 接入；引用溯源 UI | 1 周 |
| **M3 · 治理强化** | 错误恢复、补偿任务、并发上限、统计回填定时任务、运维入口"重建 Token" | 0.5 周 |
| **M4 · 外部 connector** | `api_pull` / `api_push` connector + 同步日志 + 调度 | 1.5 周 |
| **M5 · 高级特性** | Ones/Confluence connector；GraphRAG；rerank model 选择；指标 + 告警 | 按需 |

依赖：embedding 模型需先在 LLM 管理（`system:llm`）中注册一个 embedding-capable provider，否则 M1 创建 KB 即失败。

---

## 12. 与现有模块的协同

| 模块 | 协同点 |
|------|--------|
| **应用工厂** | 复用 `tb_app.app_config.kb_ids`；RAG 应用 runtime 调 `KbRetrieveService` |
| **技能管理** | 可新建内置工具 `kb_search`，让 Agent 主动查询知识库（与 RAG 应用模式互补） |
| **权限管理** | 复用 `kb:edit` / `kb:publish` 权限码；菜单按权限隐藏 |
| **系统配置** | embedding 模型在 LLM 管理（`system:llm`）注册外部服务（OpenAI-API-Compatible 等），由 easy-ai 主动同步到 RAGFlow `tenant_info`（详见 §5.7）；运维操作 RAGFlow Token 走"知识库引擎"子页（§3.8） |
| **可观测性** | 检索 trace 入 langfuse；KB 健康度作为 app health 子维度 |
| **长期记忆** | 互补：RAGFlow 管"客观知识"，memory 管"用户-agent 交互"；两者皆可作为 agent 工具暴露 |

---

## 13. 已确定决策与未决问题

### 13.1 已确定决策

| 决策 | 选择 | 影响 |
|------|------|------|
| 向量引擎 | **Elasticsearch 8.11.3**（不引入 Infinity） | 部署稳定可观测，运维成本中等；§2.2 / §2.4 已锁定 |
| Embedding 服务 | **外部 API**（OpenAI-API-Compatible 等），不部署 TEI | 节省一个重量级容器；模型升级走 LLM 管理；§2.4 / §2.5 / §5.7 已锁定 |
| 多租隔离 | **软隔离**：RAGFlow 单 tenant，easy-ai 按 owner+权限码可见性过滤 | 初期复杂度低；若未来有跨子公司硬隔离诉求，再迁移到 RAGFlow tenant；§1 / §3.3 / §5.8 已锁定 |
| 鉴权方式 | **fork RAGFlow + HMAC trusted-header**（与 Flowise 同形态） | 运行时无状态，env 即真相，对运维透明；fork 改动 ~120 行 Python；§3 已锁定 |
| RAGFlow fork 维护 | 单独 fork 仓库（git submodule 替换 `eoitek-llm/ragflow-ref`），`easyai-master` 分支跟踪 upstream | rebase 冲突面 ≤5 文件；与 `Flowise/` 同结构；§3.9 已锁定 |

### 13.2 未决问题（待后续阶段决定）

1. **批量重建索引**：embedding 模型升级时如何低损批量重建？暂留 M5 解决。
2. **chunk 手工编辑**：RAGFlow 支持手工编辑 chunk，是否在 easy-ai UI 暴露？倾向 M2+ 再做。
