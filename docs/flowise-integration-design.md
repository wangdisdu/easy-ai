# easy-ai 嵌入 Flowise 接入设计

## 1. 背景与目标

`AppFormView.vue` 中的 **Agent Flow 应用**类型，由本仓库子目录 `Flowise/`（开源 FlowiseAI v3.1.2，monorepo）提供可视化编排能力。本文档定义两者的接入方案，目标：

1. 用户在 easy-ai 内创建/编辑/运行 Agent Flow 应用时，**无感知**地使用 Flowise 编辑器与运行时；
2. 不依赖 Flowise 自带的登录页，复用 easy-ai 的账号体系；
3. **允许直接修改 Flowise 源码**（认证、品牌、路由前缀等），便于后续随上游版本迭代；
4. 数据模型上保持 easy-ai `tb_app` 与 Flowise `chatflow` 的一对一映射。

## 2. 架构总览

```
┌────────────────────────────────────────────────────────────┐
│                        浏览器                               │
│  easy-ai 前端 (Vue, :5173)                                  │
│  └─ AppFormView.vue                                         │
│      └─ <iframe src="/flowise/canvas/{flow_id}?token=...">  │
└────────────────────────────────────────────────────────────┘
                │  同源请求（Vite/nginx 反代）
                ▼
┌────────────────────────────────────────────────────────────┐
│  easy-ai 后端 (FastAPI, :8000)                              │
│  ├─ /api/v1/app          (应用 CRUD, 维护 flowise_chatflow_id)│
│  ├─ /api/v1/agent-flow   (代理调 Flowise REST)              │
│  └─ /flowise/*           (反向代理到 Flowise:3001,           │
│                           注入 X-EasyAI-User 头)             │
└────────────────────────────────────────────────────────────┘
                │  HTTP（仅内网）
                ▼
┌────────────────────────────────────────────────────────────┐
│  Flowise (Node, :3001)                                      │
│  ├─ 修改后的 auth 中间件：信任 X-EasyAI-User 头              │
│  ├─ REST: /api/v1/chatflows, /api/v1/prediction/{id}        │
│  └─ UI: /canvas/{id}（隐藏导航/登录, 走品牌定制）            │
└────────────────────────────────────────────────────────────┘
```

**核心原则**：

- Flowise 永远只暴露在 easy-ai 后端反向代理之后，**外网不直接可访问**。
- 浏览器看到的 Flowise URL 是 `/flowise/...`，与 easy-ai **同源**，避免跨域、Cookie、`X-Frame-Options` 等问题。
- easy-ai 后端是唯一签发"Flowise 通行凭证"的地方：将 easy-ai 当前登录用户身份注入到反代请求头中，Flowise 端的鉴权中间件直接信任它。

## 3. Flowise 源码改造点（fork + patch）

### 3.1 仓库管理策略

Flowise 已 clone 在 `Flowise/`。建议：

1. 在该目录下保留独立 git 仓库（不做 submodule，便于直接改源码）；
2. 添加 upstream remote：`git remote add upstream https://github.com/FlowiseAI/Flowise.git`；
3. 在 `easy-ai-integration` 分支上做所有改造，便于后续 `git fetch upstream && git rebase upstream/main` 升级；
4. 所有改造集中在以下目录，避免散落，方便冲突解决：
   - `packages/server/src/middlewares/easyai/`（新增）
   - `packages/ui/src/easyai/`（新增）
   - 必要时对 `packages/server/src/index.ts`、`packages/ui/src/routes/` 做最小修改并打补丁注释 `// EASYAI-PATCH:`

### 3.2 后端改造：信任头鉴权中间件

新增 `packages/server/src/middlewares/easyai/trustedHeaderAuth.ts`：

- 读取请求头 `X-EasyAI-User`（用户 ID）、`X-EasyAI-Workspace`、`X-EasyAI-Sign`（HMAC 签名）；
- 用共享密钥 `EASYAI_SHARED_SECRET` 校验签名（防止内网横向伪造）；
- 校验通过后，构造一个最小的 `req.user` 对象（兼容 Flowise 现有 `req.user.id` 用法），并 `next()`；
- 校验失败返回 401。

接入位置（**关键 patch 点**）：

- `packages/server/src/index.ts` 中 `this.app.use(...)` 注册顺序里，将 `trustedHeaderAuth` 放在 Flowise 默认 passport / `validateAPIKey` **之前**；
- 命中后跳过原有 `whitelistURLs` 之外的登录跳转逻辑，写法上加一个旁路开关 `if (process.env.EASYAI_TRUSTED_HEADER === 'true')`，默认关闭，不影响 Flowise 独立部署模式。

为什么选"信任头"而不是改 SSO：

- Flowise 的 SSO/passport 体系绑定 session + 浏览器跳转，不适合后端代理场景；
- 信任头是反代场景下最常见的 SSO 桥接做法（参考 Grafana auth.proxy、Kibana proxyauth），改动量最小；
- 仍然保留原始登录页用于"独立调试 Flowise"的需求（环境变量未开启时回到原行为）。

### 3.3 用户/工作区映射

Flowise 的 `chatflow` 和 `credential` 表都带 `workspaceId`。easy-ai 接入层需要：

- 首次为某用户/工作区代理请求时，调用 Flowise 内部服务确保对应的 `User` + `Workspace` 记录已存在（不存在则创建）；
- easy-ai 用户 ID → Flowise userId，可直接用同一字符串（Snowflake ID）；
- 此逻辑也实现在 `trustedHeaderAuth` 中间件里，实现 lazy provision。

### 3.4 前端改造：隐藏导航 / 嵌入模式

新增 `packages/ui/src/easyai/embed.ts`：

- 通过 URL query `?embed=1` 进入嵌入模式；
- 在 `App.tsx`（或对应根组件）顶部读取该参数，写入全局 store；
- CSS 隐藏：左侧主导航、顶部 Logo bar、用户菜单、登录/注册入口；
- 路由收敛：嵌入模式下只允许 `/canvas/:id`、`/chatbot/:id` 等画布相关页面，其它路径 redirect 回画布。

**Patch 点**（最小化）：

- `packages/ui/src/layout/MainLayout/index.tsx`（或同名文件）外层加一个 `if (isEmbed) return <EmbedLayout/>;`；
- 新建 `EmbedLayout` 组件直接渲染 `<Outlet />`，不带任何 chrome；
- `vite.config.ts` 中 `base` 改为 `/flowise/`，让所有静态资源 URL 自动带上前缀（与反代路径一致），避免改一万个 `<img src>`。

### 3.5 启动配置

`Flowise/packages/server/.env` 增加：

```env
PORT=3001
EASYAI_TRUSTED_HEADER=true
EASYAI_SHARED_SECRET=<与 easy-ai 后端共享的随机串>
APIKEY_PATH=/var/lib/flowise   # 或保持默认
FLOWISE_SECRETKEY_OVERWRITE=<固定值，避免重启失效>
# 关闭自带登录页
DISABLE_FLOWISE_TELEMETRY=true
```

## 4. easy-ai 后端改造

### 4.1 反向代理路由

新增 `backend/app/api/flowise_proxy.py`：

- 挂载在 `/flowise/{path:path}`，使用 `httpx.AsyncClient` 流式转发到 `FLOWISE_INTERNAL_URL`；
- 处理 GET/POST/PUT/DELETE/WebSocket（chat 流式响应需要 SSE 透传）；
- **请求改写**：
  - 注入头 `X-EasyAI-User: {current_user.id}`、`X-EasyAI-Workspace: {workspace_id}`、`X-EasyAI-Sign: HMAC_SHA256(secret, "{user}.{ts}")`；
  - 透传原始 `Cookie`、`Content-Type`；
- **响应改写**：
  - 移除 `X-Frame-Options`、`Content-Security-Policy: frame-ancestors`，允许同源 iframe；
  - HTML 响应不需要重写 URL，因为前面已经把 Flowise 的 `base` 设成 `/flowise/`。
- 鉴权：proxy 路由本身受 easy-ai JWT 中间件保护，未登录直接 401，从源头杜绝直连 Flowise。

### 4.2 业务 API：Agent Flow 应用 CRUD

`backend/app/service/agent_flow_service.py` 封装对 Flowise REST 的调用：

| 操作 | easy-ai 行为 | Flowise 调用 |
| --- | --- | --- |
| 创建 Agent Flow 应用 | 写入 `tb_app`（`app_type=agent_flow`），同时调用 Flowise 创建空 chatflow，回写 `flowise_chatflow_id` | `POST /api/v1/chatflows` |
| 编辑画布 | 前端打开 iframe `src="/flowise/canvas/{flowise_chatflow_id}?embed=1"` | （由 iframe 内的 Flowise UI 自行调用其 REST） |
| 删除应用 | 软删 `tb_app`，同步删 Flowise chatflow | `DELETE /api/v1/chatflows/{id}` |
| 运行 | easy-ai 后端代理调用，落 langfuse trace + `tb_app_log` | `POST /api/v1/prediction/{id}` |
| 发布版本 | 导出 chatflow JSON，存入 `tb_app_version.config_snapshot` | `GET /api/v1/chatflows/{id}` 拿 `flowData` |

### 4.3 数据库字段

`tb_app` 增加列（不破坏现有结构）：

```sql
ALTER TABLE tb_app ADD COLUMN flowise_chatflow_id VARCHAR(64);
ALTER TABLE tb_app ADD COLUMN flowise_workspace_id VARCHAR(64);
```

`AppResp` 模型对应增加这两个字段。Snowflake ID 同样以字符串透传。

## 5. easy-ai 前端改造

### 5.1 AppFormView：创建分支

第二步配置阶段，对 `app_type === 'agent_flow'` 的处理改为：

1. 用户填完基础信息（名称/描述/平台配置）后点击"下一步"；
2. 调用 `POST /api/v1/app`，后端创建 easy-ai App + Flowise chatflow，返回 `flowise_chatflow_id`；
3. 跳转到新的画布编辑页 `AppFlowEditorView.vue`，内嵌 iframe；
4. 用户在画布中编辑保存（由 Flowise 自身负责），完成后点 easy-ai 顶部"完成"按钮回到应用详情。

### 5.2 新页面 `AppFlowEditorView.vue`

```html
<iframe
  :src="`/flowise/canvas/${app.flowise_chatflow_id}?embed=1`"
  class="flow-iframe"
  allow="clipboard-read; clipboard-write"
/>
```

- iframe 占满内容区；
- 顶部仍保留 easy-ai 的 PageHeader（标题、返回、保存、发布按钮）；
- 通过 `window.postMessage` 与 iframe 双向通信：
  - easy-ai → Flowise：`{type: 'easyai:save'}` 触发 Flowise 内部保存逻辑；
  - Flowise → easy-ai：`{type: 'flowise:saved', flowData}` 通知保存完成，easy-ai 同步更新 `update_time`。
  - 这要求在 Flowise 的 `Canvas` 组件中加几行 `window.parent.postMessage(...)`，是 §3.4 的一部分。

### 5.3 Vite 代理

`frontend/vite.config.ts` 增加：

```ts
proxy: {
  "/api": "http://127.0.0.1:8000",
  "/flowise": {
    target: "http://127.0.0.1:8000",  // 走 easy-ai 后端反代，而不是直连 Flowise
    changeOrigin: true,
    ws: true,
  },
},
```

## 6. 运行与会话流（端到端）

1. 用户登录 easy-ai，浏览器持有 easy-ai JWT cookie；
2. 用户进入"创建应用 → Agent Flow"，填写基础信息，提交；
3. easy-ai 后端：
   - 校验 JWT；
   - 调 `POST flowise:3001/api/v1/chatflows`（带 `X-EasyAI-User` 头），Flowise 中间件信任头并 lazy provision 用户；
   - 拿到 `chatflow.id`，写入 `tb_app`；
4. 前端跳转到 `/app/{id}/flow`，渲染 iframe `src="/flowise/canvas/{flow_id}?embed=1"`；
5. 浏览器对 `/flowise/...` 的请求带着 easy-ai JWT cookie 进入 easy-ai 后端 → 反代到 Flowise，注入信任头；
6. Flowise UI（嵌入模式）渲染画布；用户编辑→保存，所有 XHR 同样走 `/flowise/api/v1/...` → easy-ai 反代 → Flowise；
7. 用户通过 easy-ai 调用应用（聊天测试 / 公开 API），easy-ai 后端调 `POST /flowise/api/v1/prediction/{flow_id}`，记录 langfuse trace + `tb_app_log`。

## 7. 安全要点

- `EASYAI_SHARED_SECRET` 仅存在于 easy-ai 后端与 Flowise 容器环境变量中，不出现在前端；
- Flowise 监听 **127.0.0.1** 或 docker 内部网络，对外不开放 3001 端口；
- 反代路由强制要求登录态，未登录直接 401；
- HMAC 签名带时间戳，Flowise 中间件校验 ±60s 时间窗，防重放；
- iframe 加 `sandbox="allow-scripts allow-same-origin allow-forms allow-popups"`；
- 删除应用时，事务里同时调用 Flowise DELETE，失败回滚 easy-ai 侧删除。

## 8. 升级 Flowise 上游版本的流程

1. `cd Flowise && git fetch upstream`
2. `git checkout easy-ai-integration && git rebase upstream/main`
3. 解决冲突时关注 `// EASYAI-PATCH:` 标记；
4. 重新 `pnpm install && pnpm build`；
5. 跑回归用例（见 §9）。

## 9. 落地里程碑（建议）

- **M1 接入打通**（1 周）：反向代理 + 信任头中间件 + Flowise embed 模式；手工创建 chatflow，验证 iframe 能进入画布并保存。
- **M2 业务联动**（1 周）：`tb_app` 字段、AppFormView 创建分支、`AppFlowEditorView`、postMessage 桥。
- **M3 运行与可观测**（1 周）：prediction 代理 + langfuse 接入 + `tb_app_log` 记录。
- **M4 发布与版本**（0.5 周）：导出/导入 flowData 到 `tb_app_version`。
- **M5 删除/权限/审计**（0.5 周）：级联删除、workspace 隔离测试、安全回归。

## 10. 不在本设计范围内

- Flowise 自带 SSO（Auth0/Azure/Google/Github）的继续支持 —— 嵌入模式下完全用 easy-ai 账号；
- Flowise marketplace、API key 管理 UI —— 嵌入模式下隐藏，由 easy-ai 侧统一管理；
- 多租户的资源配额 —— 后续在 easy-ai 网关层做。
