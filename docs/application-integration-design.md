# 应用集成功能详细设计

> 基于原型页面 [IntegrationView](/Users/wangdi/workspace/king/easy-ai/eoitek-llm/web-demo/assets/IntegrationView-CyIo-cYa.js)、[IntegrationFormView](/Users/wangdi/workspace/king/easy-ai/eoitek-llm/web-demo/assets/IntegrationFormView-Bbp1xee9.js) 反推整理。两个视图是 demo 构建的混淆产物,本文档已抽取其完整中文文案、字段、路由与交互。

---

## 1. 功能概述

应用集成是平台对外开放 AI 能力的统一网关:把应用工厂里已发布的应用封装成对外可调用的 REST 端点,并配套 API Key、配额、限流、白名单、过期时间等管控参数。

**P0 支持的应用类型**:`agent` / `llm` / `rag`(与 `backend/app/api/open_api.py` 现有分发能力对齐)。
**P1 规划**:`agent_flow`(经 `flowise_proxy` 桥接)、`kb_push`(知识库对外 API)。文档其余章节涉及 P1 类型的部分会显式标注。

与"应用工厂"是**消费 / 被消费**关系:

| 模块 | 关注点 |
|------|------|
| 应用工厂 | 造应用(配置、调试、发布) |
| 应用集成 | 把应用对外开放(谁能调、调多少、什么时候停) |

设计原则:

- **资源解耦**:Integration 只保存"网关元数据"和"绑定的应用 ID 列表",不持有任何业务逻辑。
- **凭证一次性可见**:API Key 明文仅在创建/重置时返回一次,之后只能查看密文摘要。
- **双层限速 + 日配额**:Key 级限流可覆盖 Integration 级限流;两层都通过后再扣日配额。
- **优雅降级**:Integration 写库成功但 Key 生成失败时不回滚,让用户补救。
- **状态正交**:Integration 状态、ApiKey 状态、过期时间三者独立,组合控制可见范围。
- **双契约**:**管理 API**(`/api/v1/integration/*`)沿用主仓约定(HTTP 200 + 业务 `code`);**对外网关**(`/open/v1/*`)走标准 HTTP 语义(4xx/5xx + `Retry-After` / `X-RateLimit-*` headers),便于外部客户端用通用 HTTP 中间件做重试/熔断。

---

## 2. 页面范围

| 页面 | 路由 | 作用 |
|------|------|------|
| 集成列表页 | `/integration` | 展示全部集成应用,支持筛选、展开详情、启停、重置 Key、修改限流 |
| 集成创建/编辑页 | `/integration/create` / `/integration/edit/:id` | 填写元数据 + 管控配置 + 绑定应用 |
| 调用日志页 | `/integration/logs` | 查看 API 调用流水(归入可观测性模块,本文档不展开) |
| 知识管理 API 入口 | `/knowledge/integration` | 知识库对外 API 的快捷入口(归入知识库文档) |

---

## 3. 数据模型

### 3.1 Integration(集成应用)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT(Snowflake,字符串传输) | 主键 |
| `name` | VARCHAR(64) | 集成名称,例如"风控工单系统" |
| `description` | TEXT | 用途和场景描述 |
| `status` | VARCHAR(16) | `active` / `disabled`,创建即 `active` |
| `quota` | INT | 日配额(次/天,三态见 §3.4) |
| `rate_limit` | INT | 集成级限流(次/分钟,三态见 §3.4) |
| `timeout` | INT | 调用超时(秒) |
| `whitelist` | TEXT | IP/CIDR 白名单,逗号分隔(空 = 不限制) |
| `expire_at` | BIGINT | 过期时间(Unix ms,NULL = 永不过期) |
| `create_time` / `update_time` | BIGINT | 标准审计列 |
| `create_user` / `update_user` | VARCHAR | 标准审计列 |

### 3.2 ApiKey(集成密钥)

一个 Integration 可挂多把 Key,便于按调用方区分计量。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `integration_id` | BIGINT | 所属集成 |
| `key_prefix` | VARCHAR(16) | 列表展示前缀(例 `sk-prod-9f3`) |
| `key_suffix` | VARCHAR(8) | 列表展示末尾(例 `xY2k`),与 prefix 拼出 `sk-prod-9f3****xY2k` |
| `key_hash` | VARCHAR(128) | 完整 Key 的 SHA-256,**不存明文** |
| `status` | VARCHAR(16) | `active` / `disabled` |
| `rate_limit` | INT | Key 级限流(次/分钟,三态见 §3.4) |
| `last_used_at` | BIGINT | 最近一次使用时间(异步更新) |
| `revoked_at` | BIGINT | 重置时打标记,旧 hash 立即失效 |
| `deleted_at` | BIGINT | 软删除时间(NULL = 未删除) |
| `create_time` / `create_user` | | 标准审计列 |

### 3.3 IntegrationApp(应用绑定)

| 字段 | 类型 | 说明 |
|------|------|------|
| `integration_id` | BIGINT | |
| `app_type` | VARCHAR(16) | `agent` / `llm` / `rag`(P0);`agent_flow` / `kb_push` 为 P1 |
| `app_id` | BIGINT | 资源 ID,语义随 `app_type` 切换:P0 三类均指向应用工厂的应用 |

**主键**:`(integration_id, app_type, app_id)`。app_type 进主键是因为 P1 的 `kb_push` 指向知识库表,与应用工厂的 ID 空间不同,避免跨表 ID 冲突。

### 3.4 三态字段:NULL / 0 / >0

`rate_limit` 与 `quota` 都采用三态(**留空 ≠ 不限**):

| 取值 | 含义 |
|------|------|
| `NULL` | 继承上一层(Key→Integration→全局默认) |
| `0` | 显式"不限速 / 不限额" |
| `>0` | 具体阈值 |

UI 上"留空"对应 `NULL`,这是原型里"修改限流阈值"对话框的"已恢复为全局默认"含义。前端若要表达"不限",必须显式提交 `0`。

---

## 4. 集成列表页

### 4.1 页面目标

- 总览所有对外开放端点的健康度与用量
- 快速完成启停、重置 Key、修改限流等运维动作
- 提供创建入口与"知识管理 API"快捷链接

### 4.2 页面结构

| 区域 | 内容 |
|------|------|
| 顶部 | 标题`应用集成` + 副标题`创建 API 发布端点,分配 API Key,对外开放智能体服务` |
| 操作区 | 按钮:`知识管理 API`、`调用日志`、`创建集成应用` |
| 搜索区 | 输入框`搜索 API 路径或智能体名称...` + 状态筛选(全部 / 运行中 / 已停用) |
| 列表区 | 集成卡片网格(可展开) |
| 空态 | `暂无集成应用 / 点击「创建集成应用」发布你的第一个 API 端点` |

### 4.3 集成卡片(收起态)

| 元素 | 内容 |
|------|------|
| 状态点 | 绿色`运行中` / 灰色`已停用` |
| 名称 | 一级标题 |
| 描述 | 副文本,缺省显示`暂无描述` |
| 应用 Tag | `绑定应用 (N)`,按 type 着色 |
| meta-pills | 日配额 / 限流 / 超时 / 白名单 / 过期时间 / 创建时间 |
| 展开箭头 | 点击展开详情 |

### 4.4 集成卡片(展开态)

两栏 `detail-grid`:

**左侧 API Key 列表**

每个 Key 行包含:
- 密文 Key(默认 `sk-prod-9f3******xY2`)
- `显示完整 Key` 按钮(原型只显示一次完整 Key,后续不可再见;详见 §6)
- `复制完整 Key` 按钮
- 状态徽章:`有效` / `已禁用`
- 限流标识:`限流: 100 req/min` 或 `默认`(继承)
- 操作菜单:`修改`(限流)、`启停`、`重置 Key`、`删除`

空态:`暂无 API Key`,提供"生成 Key"按钮。

**右侧绑定应用列表**

每项:
- 应用图标 + 名称(链接到应用详情)
- 应用类型 tag(P0:`AGENT` / `LLM` / `RAG`)
- 空态:`未绑定应用`

### 4.5 卡片底部动作

`编辑配置` / `编辑` / `删除` / 状态切换按钮(`启用`/`停用`)。

### 4.6 关键弹窗

| 弹窗 | 触发 | 文案 |
|------|------|------|
| 删除确认 | 点击删除 | `确认删除该集成应用?此操作不可恢复。` |
| 启停确认 | 点击启用/停用 | `确认{启用\|停用}该集成应用?` |
| 重置 Key 确认 | 点击重置 | `重置后旧 Key 将立即失效,请确认。` |
| 重置 Key 成功 | 重置后 | `新 API Key:{明文}` + `请立即保存,关闭后将无法再次查看` |
| 修改限流阈值 | Key 行的"修改" | 输入框`每分钟最大请求次数(1-100000)`,留空提示`已恢复为全局默认` |

---

## 5. 集成创建/编辑页

### 5.1 页面结构

两栏布局(`form-grid`),底部统一操作栏。

**左栏 / 集成应用信息**

| 字段 | 控件 | 备注 |
|------|------|------|
| 应用名称 | 单行输入,1-64 字符 | 占位`例如:风控工单系统` |
| 描述 | 多行 textarea,显示字数 | 占位`描述该外部系统的用途和集成场景...` |

**左栏 / 管控配置**

| 字段 | 控件 | 说明 |
|------|------|------|
| 日配额(次/天) | 数字输入 | 留空 = 继承全局默认;填 `0` 表示不限额(三态语义见 §3.4) |
| 限流(次/分钟) | 数字输入 | 留空 = 继承全局默认;填 `0` 表示不限速 |
| 超时(秒) | 数字输入 | 留空 = 继承全局默认 |
| 过期时间 | 日期选择器,`YYYY-MM-DD` | `留空则永不过期` |
| 白名单 | 单行输入 | `可选,逗号分隔` |

> **限流单位**:原型 UI 上 Integration 标的是 `req/s`、Key 标的是 `req/min`。落地时**统一为 req/min**,前端文案改为"次/分钟",原型上的 `req/s` 不再使用。

**右栏 / 绑定应用权限**

提示:`选择该集成应用可调用的应用(来自应用工厂)`

按 type 分组(`app-groups`):

| 分组标题 | type | 来源 | 阶段 |
|------|------|------|------|
| 智能体应用 | `agent` | 应用工厂 | P0 |
| 对话应用 | `llm` | 应用工厂 | P0 |
| 知识库 | `rag` | 应用工厂 | P0 |
| 工作流 | `agent_flow` | 应用工厂(经 flowise_proxy 桥接) | P1 |
| 知识推送 | `kb_push` | 知识库管理 | P1 |

P0 阶段 UI 上隐藏 `agent_flow` 与 `kb_push` 两组(或显示为禁用的"敬请期待")。后端 `POST /api/v1/integration` 收到这两类绑定时直接返回 `400 BAD_REQUEST`。

每组:
- 头部显示该组应用数(`app-group__count`)
- 多选 checkbox + 应用名 + 应用描述
- 空组提示:`暂无可绑定的应用,请先在应用工厂中发布应用`

底部 `selected-count`:`已选 N 个应用`

### 5.2 操作栏

| 模式 | 按钮 |
|------|------|
| 创建 | `取消` / `创建并生成 API Key` |
| 编辑 | `返回列表` / `保存修改` |

### 5.3 创建成功对话框(key-success-card)

- 标题`集成应用创建成功 / 已生成 API Key`
- 明文 Key + `复制` 按钮
- 警告`请立即保存此 Key,关闭后将无法再次查看完整内容`
- 关闭按钮`返回列表`

### 5.4 失败容忍

- Integration 写库成功但 Key 生成失败 → 弹提示`集成应用已创建,但 API Key 生成失败,请手动创建`,跳转列表后用户可在详情里手动新建 Key。
- Integration 写库成功但获取不到 ID → 提示`集成应用已创建,但无法获取 ID 来生成 API Key`(理论上不应发生,作为后端事务异常兜底)。

---

## 6. API Key 生命周期

| 阶段 | 行为 |
|------|------|
| 生成 | 后端生成 32 字节随机串 → `sk-{env}-{base62}`,落库 `key_prefix`(前 11 位)+ `key_suffix`(后 4 位)+ `key_hash`(SHA-256),明文仅一次性返回给前端 |
| 显示 | 列表默认拼装为 `{key_prefix}****{key_suffix}`(例 `sk-prod-9f3****xY2k`) |
| `显示完整 Key` | 后端**不返回明文**;若产品要"短期可见",可在 Redis/内存缓存里存 10 分钟明文,过期自动销毁(本期不实现) |
| 重置 | 标记旧记录 `revoked_at`,生成新 Key 插入新行,新明文一次性返回(便于审计回溯) |
| 启停 | 修改 `status` 字段,不删除 |
| 删除 | 软删除(`deleted_at`),保留调用日志关联 |

> 鉴权时按 `key_hash` 反查 ApiKey,命中后再校验 `status`、`revoked_at IS NULL`、`deleted_at IS NULL`,以及与 Integration 关联。

---

## 7. 状态机

### 7.1 Integration 状态

```
(创建)─▶ active ◀──启用── disabled
            │                ▲
            └──停用──────────┘
        (任意状态)─删除─▶ (软删除)
```

仅两态(`active` / `disabled`),无 `draft`。创建即可对外服务,产品上不需要"草稿"的中间态;若后续要做发布审批,再扩展。

### 7.2 ApiKey 状态

```
active ◀─启停─▶ disabled
   │
   └─重置──▶ (旧 revoked) + (新 active)
```

### 7.3 调用准入(优先级从高到低)

绑定校验**先于**限流计数,避免攻击者用合法 Key 调用未绑定应用反复消耗集成的限流和日配额。

1. Integration 不存在 / 已删除 → 401 `INTEGRATION_NOT_FOUND`
2. Integration `disabled` → 403 `INTEGRATION_DISABLED`
3. Integration 已过期(`expire_at < now`) → 403 `INTEGRATION_EXPIRED`
4. Key 不存在 / hash 不匹配 → 401 `API_KEY_INVALID`
5. Key `disabled` / `revoked` / `deleted` → 403 `API_KEY_DISABLED`
6. IP 不在白名单 → 403 `IP_NOT_ALLOWED`
7. 应用未绑定到该 Integration / 应用类型非 P0 范围 → 403 `APP_NOT_BOUND`
8. 双层限流 + 日配额 → 429 `RATE_LIMITED`(细分原因见 §8)
9. 通过 → 转发到对应应用 runtime

---

## 8. 限流与配额

### 8.1 模型概览

三个独立计数维度,全部通过才放行:

| 维度 | 范围 | 默认值来源 |
|------|------|------|
| Key RPM | `(integration_id, key_id)` | `ApiKey.rate_limit` → `Integration.rate_limit` → 全局默认 |
| Integration RPM | `integration_id` | `Integration.rate_limit` → 全局默认 |
| 日配额 | `integration_id`(按自然日) | `Integration.quota` → 全局默认 |

三态语义见 §3.4。

### 8.2 算法选择

| 维度 | 算法 | 理由 |
|------|------|------|
| RPM 两层 | **滑动窗口计数(Sliding Window Counter)** | 仅 2 个计数器,无滑动日志的 O(N) 内存;比固定窗口的边界突发误差小 |
| 日配额 | **固定窗口** | 配额本就按"自然日"计;TTL 设到次日 0 点 + 60s 缓冲 |

滑动窗口公式:

```
estimated = curr_count + prev_count * (60 - elapsed_in_minute) / 60
```

### 8.3 Fallback 解析

```python
def resolve_limits(intg, key, defaults) -> Limits:
    return Limits(
        key_rpm   = key.rate_limit  if key.rate_limit  is not None
                    else intg.rate_limit if intg.rate_limit is not None
                    else defaults.key_rpm,
        int_rpm   = intg.rate_limit if intg.rate_limit is not None
                    else defaults.integration_rpm,
        day_quota = intg.quota      if intg.quota      is not None
                    else defaults.day_quota,
    )
```

### 8.4 拒绝时的响应

```
HTTP/1.1 429 Too Many Requests
Retry-After: 37
X-RateLimit-Reason: INTEGRATION_RPM
X-RateLimit-Limit-Key: 100
X-RateLimit-Used-Key: 12
X-RateLimit-Limit-Integration: 1000
X-RateLimit-Used-Integration: 1000
X-Quota-Limit: 10000
X-Quota-Used: 4231
```

`Reason` 枚举:`KEY_RPM` / `INTEGRATION_RPM` / `DAY_QUOTA`,与 §8.5 抽象返回值一致。

### 8.5 抽象接口

```python
# core/rate_limit/base.py
class Limits(NamedTuple):
    key_rpm: int      # 0 = 不限
    int_rpm: int
    day_quota: int

class Decision(NamedTuple):
    allowed: bool
    reason: str       # 'OK' | 'KEY_RPM' | 'INTEGRATION_RPM' | 'DAY_QUOTA'
    key_used: int
    int_used: int
    day_used: int

class RateLimiter(Protocol):
    async def check_and_incr(
        self, intg_id: str, key_id: str, limits: Limits
    ) -> Decision: ...
```

将来切 Redis 时只换实现,Dependency 不动。

---

## 9. 单机限流实现(P0)

P0 阶段不引入 Redis,所有计数在进程内存里完成。

### 9.1 约束与权衡

| 约束 | 应对 |
|------|------|
| `uvicorn --workers N > 1` 每进程一份计数 → 实际限速 ≈ 配置值 × N | 部署强制 `workers=1`;需要横扩时升级到 Redis 实现 |
| 进程重启计数清零 | 分钟级桶丢失可接受;日配额可选持久化(§9.5) |
| 内存随活跃 (intg, key) 数增长 | 后台 janitor 周期清理超过 1 小时未访问的桶 |

### 9.2 数据结构

```python
@dataclass
class _Bucket:
    minute: int = 0
    curr: int = 0
    prev: int = 0
    day: str = ""
    day_count: int = 0
    last_seen: float = 0.0
```

两张字典:`_int: dict[str, _Bucket]`、`_key: dict[tuple[str, str], _Bucket]`。

### 9.3 核心方法

```python
class MemoryRateLimiter:
    @staticmethod
    def _swc(b: _Bucket, minute: int, elapsed: int) -> int:
        if b.minute != minute:
            b.prev = b.curr if b.minute == minute - 1 else 0
            b.curr = 0
            b.minute = minute
        return b.curr + (b.prev * (60 - elapsed)) // 60

    async def check_and_incr(self, intg_id, key_id, limits) -> Decision:
        now = int(time.time())
        minute, elapsed = now // 60, now % 60
        today = time.strftime("%Y%m%d", time.localtime(now))

        ib = self._int[intg_id]
        kb = self._key[(intg_id, key_id)]
        ib.last_seen = kb.last_seen = time.monotonic()
        if ib.day != today:
            ib.day, ib.day_count = today, 0

        key_used = self._swc(kb, minute, elapsed)
        int_used = self._swc(ib, minute, elapsed)
        day_used = ib.day_count

        if limits.key_rpm > 0 and key_used >= limits.key_rpm:
            return Decision(False, "KEY_RPM", key_used, int_used, day_used)
        if limits.int_rpm > 0 and int_used >= limits.int_rpm:
            return Decision(False, "INTEGRATION_RPM", key_used, int_used, day_used)
        if limits.day_quota > 0 and day_used >= limits.day_quota:
            return Decision(False, "DAY_QUOTA", key_used, int_used, day_used)

        kb.curr += 1
        ib.curr += 1
        ib.day_count += 1
        return Decision(True, "OK", key_used + 1, int_used + 1, day_used + 1)
```

### 9.4 为何不需要锁

`check_and_incr` 内部全是 CPU 操作,**没有 `await`**,在 asyncio 单线程事件循环里整体原子。仅当路由配置为 `def`(同步路由跑在线程池)时,才需要给桶加 `threading.Lock`。

### 9.5 日配额可选持久化

进程重启会丢日计数。如在意:

- 启动时从 `tb_integration_quota_day` hydrate 当天用量
- 每分钟把脏的 Integration 批量 `UPSERT` 回去

```sql
CREATE TABLE tb_integration_quota_day (
    integration_id BIGINT NOT NULL,
    day           VARCHAR(8) NOT NULL,
    day_count     INT NOT NULL DEFAULT 0,
    update_time   BIGINT NOT NULL,
    PRIMARY KEY (integration_id, day)
);
```

精度损失最多 1 分钟,符合配额业务的容忍度。

### 9.6 后台清理

```python
async def janitor():
    while True:
        await asyncio.sleep(300)
        cutoff = time.monotonic() - 3600
        for d in (self._int, self._key):
            for k in [k for k, v in d.items() if v.last_seen < cutoff]:
                del d[k]
```

在 `lifespan` 启动时创建任务,关闭时 cancel。

---

## 10. 后端 API(双契约)

### 10.1 管理 API(主仓约定:HTTP 200 + 业务 `code`)

路径单数、ID 字符串传输、`Resp[T]` / `PagedResp[T]`、Snowflake ID,统一走 `core/exception_handler.py` 已注册的全局 handler,**异常仍返回 HTTP 200**。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/integration/page` | 分页列表,支持 `name` 关键字 + `status` 过滤 |
| POST | `/api/v1/integration` | 创建集成 + 首把 API Key(返回明文) |
| GET | `/api/v1/integration/{id}` | 详情(含 keys 摘要 + boundApps) |
| PUT | `/api/v1/integration/{id}` | 修改元数据 + 管控配置 + 绑定应用 |
| DELETE | `/api/v1/integration/{id}` | 软删除 |
| PUT | `/api/v1/integration/{id}/status` | 启用/停用 |
| POST | `/api/v1/integration/{id}/key` | 生成新 Key(返回明文) |
| PUT | `/api/v1/integration/{id}/key/{kid}` | 修改 Key 限流 / 启停 |
| POST | `/api/v1/integration/{id}/key/{kid}/reset` | 重置(旧失效 + 返回新明文) |
| DELETE | `/api/v1/integration/{id}/key/{kid}` | 软删除 Key |
| GET | `/api/v1/integration/log/page` | 调用日志,支持 `integration_id` / `only_failed` 过滤(详见 §14) |

### 10.2 对外网关(标准 HTTP 语义)

```
POST /open/v1/{app_type}/{app_id}/invoke
Header: Authorization: Bearer {api_key}
```

P0 `app_type` ∈ `agent` / `llm` / `rag`(P1 扩展 `agent_flow` / `kb_push`)。

**与管理 API 不同**:`/open/v1/*` 走独立的 FastAPI Router + 独立异常 handler,不复用 `register_exception_handlers` 注册的全局处理逻辑。返回标准 HTTP 语义:

- 鉴权失败 → `401 Unauthorized`
- 准入失败(停用/过期/无绑定/白名单/Key 禁用)→ `403 Forbidden`
- 限流/配额超限 → `429 Too Many Requests` + `Retry-After` + `X-RateLimit-*`
- 应用 runtime 异常 → `502 Bad Gateway`(包装原错误,不泄露内部细节)
- 参数校验 → `400 Bad Request`

响应体仍是统一 JSON 结构,但 HTTP status code 与 body 中的 `code` 字段对齐:

```json
{"code": "RATE_LIMITED", "reason": "INTEGRATION_RPM", "message": "调用频率超限"}
```

请求处理顺序:鉴权 → 白名单 → 应用绑定校验 → 限流/配额 → 转发到对应 runtime(顺序细节见 §7.3)。

---

## 11. 数据库表

```sql
-- 集成应用主表
CREATE TABLE tb_integration (
    id            BIGINT       PRIMARY KEY,
    name          VARCHAR(64)  NOT NULL,
    description   TEXT,
    status        VARCHAR(16)  NOT NULL DEFAULT 'active',
    quota         INT,
    rate_limit    INT,
    timeout       INT          NOT NULL DEFAULT 30,
    whitelist     TEXT,
    expire_at     BIGINT,
    create_time   BIGINT       NOT NULL,
    update_time   BIGINT       NOT NULL,
    create_user   VARCHAR(64),
    update_user   VARCHAR(64),
    deleted_at    BIGINT
);
CREATE INDEX idx_intg_status ON tb_integration(status, deleted_at);

-- API Key
CREATE TABLE tb_integration_key (
    id              BIGINT       PRIMARY KEY,
    integration_id  BIGINT       NOT NULL,
    key_prefix      VARCHAR(16)  NOT NULL,
    key_suffix      VARCHAR(8)   NOT NULL,
    key_hash        VARCHAR(128) NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'active',
    rate_limit      INT,
    last_used_at    BIGINT,
    revoked_at      BIGINT,
    deleted_at      BIGINT,
    create_time     BIGINT       NOT NULL,
    create_user     VARCHAR(64)
);
CREATE UNIQUE INDEX uk_intg_key_hash ON tb_integration_key(key_hash);
CREATE INDEX idx_intg_key_intg ON tb_integration_key(integration_id, deleted_at);

-- 应用绑定(app_type 进主键以避免跨表 ID 冲突)
CREATE TABLE tb_integration_app (
    integration_id  BIGINT       NOT NULL,
    app_type        VARCHAR(16)  NOT NULL,
    app_id          BIGINT       NOT NULL,
    create_time     BIGINT       NOT NULL,
    PRIMARY KEY (integration_id, app_type, app_id)
);
CREATE INDEX idx_intg_app_lookup ON tb_integration_app(app_type, app_id);

-- 日配额持久化(可选,§9.5)
CREATE TABLE tb_integration_quota_day (
    integration_id  BIGINT       NOT NULL,
    day             VARCHAR(8)   NOT NULL,
    day_count       INT          NOT NULL DEFAULT 0,
    update_time     BIGINT       NOT NULL,
    PRIMARY KEY (integration_id, day)
);
```

调用日志表 `tb_api_access_log` 见 §14.1。

迁移文件:`tb_integration*` 四张表在 `0019_integration`,`tb_api_access_log` 在 `0020_api_access_log`。

遵循主仓约定:`tb_` 前缀、无外键、`BIGINT` ID、Unix ms 时间戳、`VARCHAR(255)` / `TEXT` 字符串。

---

## 12. 错误码

### 12.1 管理 API:沿用 `core/error_code.py`

现有 `ErrorCode` 是整型业务码,管理 API 直接复用主仓的 `ServiceError(code, msg)`,全部走 HTTP 200。下面这些常量加进去即可:

| 常量 | 含义 |
|------|------|
| `INTEGRATION_NOT_FOUND` | 集成应用不存在 |
| `INTEGRATION_NAME_DUPLICATE` | 集成应用名称重复 |
| `INTEGRATION_BIND_NOT_ALLOWED` | 绑定了 P1 未支持的应用类型 |
| `API_KEY_PLAINTEXT_INVISIBLE` | API Key 明文已不可见 |

### 12.2 对外网关:独立异常 + Header 装载

`/open/v1/*` 不使用 `ServiceError`(其签名只接受 `code/msg`,不支持携带 HTTP status 与 headers)。新增独立异常类:

```python
# core/integration_errors.py
class IntegrationApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        extra: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.extra = extra or {}
```

错误码枚举(字符串,直接进响应体):

| `code` | HTTP | 触发 |
|------|------|------|
| `INTEGRATION_NOT_FOUND` | 401 | Key 找不到对应集成 |
| `INTEGRATION_DISABLED` | 403 | 集成 `disabled` |
| `INTEGRATION_EXPIRED` | 403 | `expire_at < now` |
| `API_KEY_INVALID` | 401 | Bearer 缺失 / hash 不匹配 |
| `API_KEY_DISABLED` | 403 | Key `disabled` / `revoked` / `deleted` |
| `IP_NOT_ALLOWED` | 403 | IP 不在白名单 |
| `APP_NOT_BOUND` | 403 | 应用未绑定或类型非 P0 |
| `RATE_LIMITED` | 429 | 双层限流 / 日配额超限,`reason` 字段细化 |
| `UPSTREAM_ERROR` | 502 | 应用 runtime 抛出非业务异常 |

`reason` 子枚举(仅 `RATE_LIMITED` 时附带):`KEY_RPM` / `INTEGRATION_RPM` / `DAY_QUOTA`。

---

## 13. FastAPI 接入

### 13.1 异常 handler(仅作用于 `/open/v1/*`)

```python
# api/open_gateway/handlers.py
def register_open_gateway_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrationApiError)
    async def _(_: Request, exc: IntegrationApiError) -> JSONResponse:
        body = {"code": exc.code, "message": exc.message, **exc.extra}
        return JSONResponse(
            status_code=exc.status_code, content=body, headers=exc.headers
        )
```

注册时机:`app.py` 启动里在 `register_exception_handlers(app)` **之后**追加调用,FastAPI 优先匹配更具体的异常类,管理 API 不受影响。

### 13.2 Dependency 链(注意顺序)

```python
# api/open_gateway/deps.py
async def integration_auth(request: Request) -> AuthCtx:
    raw_key = extract_bearer(request)
    if not raw_key:
        raise IntegrationApiError(401, "API_KEY_INVALID", "missing bearer token")
    intg, key = await load_by_key(raw_key)
    if not intg or not key:
        raise IntegrationApiError(401, "API_KEY_INVALID", "key not found")
    if intg.status != "active":
        raise IntegrationApiError(403, "INTEGRATION_DISABLED", "integration disabled")
    if intg.expire_at and intg.expire_at < now_ms():
        raise IntegrationApiError(403, "INTEGRATION_EXPIRED", "integration expired")
    if key.status != "active" or key.revoked_at or key.deleted_at:
        raise IntegrationApiError(403, "API_KEY_DISABLED", "key not usable")
    if not ip_in_whitelist(request.client.host, intg.whitelist):
        raise IntegrationApiError(403, "IP_NOT_ALLOWED", "ip not whitelisted")
    return AuthCtx(intg=intg, key=key)

async def app_bound(
    app_type: str, app_id: str, ctx: AuthCtx = Depends(integration_auth)
) -> AuthCtx:
    if app_type not in {"agent", "llm", "rag"}:               # P0 范围
        raise IntegrationApiError(403, "APP_NOT_BOUND", f"unsupported: {app_type}")
    if not await is_bound(ctx.intg.id, app_type, app_id):
        raise IntegrationApiError(403, "APP_NOT_BOUND", "app not bound")
    return ctx

async def rate_limit(
    request: Request, ctx: AuthCtx = Depends(app_bound)
) -> AuthCtx:
    limits = resolve_limits(ctx.intg, ctx.key, GLOBAL_DEFAULTS)
    d = await request.app.state.limiter.check_and_incr(
        ctx.intg.id, ctx.key.id, limits
    )
    headers = build_ratelimit_headers(d, limits)
    if not d.allowed:
        retry_after = 60 - (int(time.time()) % 60)
        raise IntegrationApiError(
            429, "RATE_LIMITED", "rate limit exceeded",
            headers={**headers, "Retry-After": str(retry_after)},
            extra={"reason": d.reason},
        )
    request.state.rl_headers = headers
    return ctx

@router.post("/open/v1/{app_type}/{app_id}/invoke")
async def invoke(
    app_type: str, app_id: str, ctx: AuthCtx = Depends(rate_limit)
):
    try:
        return await dispatcher.invoke(app_type, app_id, ctx)
    except Exception as e:
        raise IntegrationApiError(502, "UPSTREAM_ERROR", str(e)) from e
```

Dependency 链 `integration_auth` → `app_bound` → `rate_limit`,保证**绑定校验先于限流计数**,未绑定请求不消耗配额(对应 §7.3)。

响应中间件读取 `request.state.rl_headers` 在成功响应里也填上 `X-RateLimit-*` 头(便于客户端预测剩余配额)。

---

## 14. 调用日志

`/open/v1/*` 每次调用落一行 `tb_api_access_log`,**无论成功、鉴权拒绝、限流拒绝还是上游错误**。

### 14.1 表结构

```sql
CREATE TABLE tb_api_access_log (
    id              BIGINT       PRIMARY KEY,
    -- 鉴权在解析集成之前就失败时,下面四列可能为空
    integration_id  BIGINT,
    key_id          BIGINT,
    app_type        VARCHAR(32),
    app_id          BIGINT,
    status_code     INT          NOT NULL,  -- HTTP 状态码
    code            VARCHAR(64)  NOT NULL,  -- 业务码:OK / API_KEY_INVALID / RATE_LIMITED ...
    reason          VARCHAR(32),            -- 限流细分:KEY_RPM / INTEGRATION_RPM / DAY_QUOTA
    latency_ms      INT,
    client_ip       VARCHAR(64),
    request_bytes   INT,                    -- 取自 Content-Length
    error_message   TEXT,                   -- 截断至 2000 字符
    create_time     BIGINT       NOT NULL
);
CREATE INDEX idx_tb_api_access_log_intg ON tb_api_access_log(integration_id, create_time);
```

> 仅记 `request_bytes`(来自 `Content-Length`,零成本);`response_size` 因 `JSONResponse`
> 流式读取代价较高,P0 不记。

### 14.2 埋点实现

两个汇聚点覆盖 100% 结果,一次请求恰好一条,不漏不重:

- **`IntegrationApiError` handler** — 记录全部错误响应(401/403/429/502/400)
- **`invoke` 成功返回前** — 记录 200(`code=OK`)

`integration_id` / `key_id` 由 `integration_auth` 在解析成功后写到 `request.state`;
鉴权在解析之前失败时这两列为 `NULL`。`record_access_log` 用独立 `SessionLocal()`
写入,任何异常只 warning,绝不影响主响应。

### 14.3 查询接口

`GET /api/v1/integration/log/page` — 分页,支持 `integration_id`、`only_failed`(`status_code >= 400`)过滤。

### 14.4 后续(P1+)

- 调用量趋势(按 Integration / Key 维度)
- 拒绝率告警(同一 Key 1 分钟内拒绝 > 50 次)
- Top N 调用方、错误码分布
- 接入 Langfuse trace

---

## 15. 演进路径

| 阶段 | 能力 | 说明 |
|------|------|------|
| P0 | 单机内存限流 + 日配额可选持久化 | 当前文档范围,应用类型限 `agent` / `llm` / `rag` |
| P1 | 切换到 Redis 限流 + 集群部署 | 实现 `RedisRateLimiter`,实例与 lifespan 二选一 |
| P1 | 扩展 `agent_flow` | 网关 dispatcher 增加分支,转发到 `flowise_proxy` |
| P1 | 扩展 `kb_push` | 知识推送 API 接入网关,绑定来源切到 `tb_knowledge_base` |
| P1 | CIDR 白名单 | 字符串解析支持 `10.0.0.0/8` |
| P1 | API Key 短期可见(10 分钟内可回看明文) | Redis 缓存 + 自动销毁 |
| P2 | 按用量计费 | 调用日志聚合 + 月度结算 |
| P2 | 配额预警 | 日用量到达 80% 时邮件/Webhook 通知 |
| P2 | 调用方 SDK | Python / TS 两套,封装鉴权 + 重试 + 限流退避 |

---

## 16. 落地拆分(P0,✅ 已实现)

后端
1. `backend/alembic/versions/0019_integration.py` — 四张表迁移
2. `backend/alembic/versions/0020_api_access_log.py` — 调用日志表迁移
3. `backend/app/db/schema.py` — 5 个 ORM 模型(四张集成表 + `TbApiAccessLog`)
4. `backend/app/model/integration_model.py` — 请求/响应 Pydantic 模型(含 `ApiAccessLog*`)
5. `backend/app/service/integration_service.py` — 业务逻辑(CRUD + Key 管理 + 绑定 + 调用日志读写;拒绝绑定 `agent_flow` / `kb_push`)
6. `backend/app/core/rate_limit/{base,memory}.py` — `RateLimiter` 协议 + `MemoryRateLimiter`
7. `backend/app/core/lifespan.py` — 启动 limiter + janitor
8. `backend/app/core/error_code.py` — 管理 API 错误码常量(§12.1)
9. `backend/app/core/integration_errors.py` — `IntegrationApiError` 异常类(§12.2)
10. `backend/app/api/integration_api.py` — 管理 CRUD + `log/page` 路由
11. `backend/app/api/open_gateway/` — 网关模块:
    - `handlers.py` — 独立异常 handler + 错误响应日志埋点
    - `deps.py` — `integration_auth` / `app_bound` / `rate_limit` 三个 Dependency
    - `invoke.py` — `/open/v1/{type}/{id}/invoke` 路由(dispatcher 复用 `open_api.py` 的 llm/agent/rag 单例)+ 成功响应日志埋点
    - `access_log.py` — 调用日志上下文提取
12. `backend/app/main.py` — `register_open_gateway_handlers` 在全局 handler 之后注册;include 网关 router

前端
13. `frontend/src/api/integration.ts` + `types.ts` — API client + 类型
14. `frontend/src/views/integration/` — 列表页 + 表单页(P0 隐藏 `agent_flow` / `kb_push` 分组)
15. `frontend/src/router/index.ts` — 3 条路由 + 菜单项

> 调用日志的前端"调用日志"页(消费 `log/page`)尚未实现,后端接口已就绪。
