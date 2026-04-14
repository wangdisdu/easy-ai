# Flowise 嵌入接入 M1 运行手册

M1 目标：在 easy-ai 中以 iframe 打开 Flowise 画布，且不出现 Flowise 自带登录页。
鉴权统一走 easy-ai 的 httpOnly cookie，前端不接触 token。

## 整体架构

```
浏览器 ──/flowise/*──► easy-ai 后端 (FastAPI :8000)
                       │  1. 读 cookie easyai_token → 校验 JWT
                       │  2. 注入 X-EasyAI-{User,Workspace,Ts,Sign}
                       ▼
                       Flowise (Express :3001)
                       │  trustedHeaderAuth 中间件
                       │  HMAC 校验通过 → 构造 lazy req.user
                       ▼
                       业务路由 / UI 静态资源
```

- 浏览器侧所有 Flowise URL 都带 `/flowise/` 前缀（硬编码，无环境变量）。
- easy-ai 反代剥前缀转发，注入身份头。
- Flowise UI 用 `<BrowserRouter basename="/flowise">` 剥前缀做路由匹配，资源 URL 由 Vite `base: '/flowise/'` 生成。
- Flowise 完全不感知 easy-ai cookie，只信任反代下发的 HMAC 头。

## 改动清单

### Flowise 源码（标记 `// EASYAI-PATCH:` 便于后续 rebase 升级）

| 文件 | 改动 |
| --- | --- |
| `Flowise/packages/server/src/enterprise/middleware/easyai/trustedHeaderAuth.ts` | 新增：HMAC 校验 + lazy `req.user` 构造，仅 `EASYAI_TRUSTED_HEADER=true` 时生效 |
| `Flowise/packages/server/src/index.ts` | 注册中间件 + 默认 auth gate 前 `_easyaiTrusted` 短路 |
| `Flowise/packages/ui/src/easyai/embed.js` | 新增：导出常量 `FLOWISE_EMBED_PREFIX = '/flowise'` 与 helper |
| `Flowise/packages/ui/src/index.jsx` | `<BrowserRouter basename="/flowise">`（Router 剥前缀的唯一正确位置）|
| `Flowise/packages/ui/src/routes/index.jsx` | 移除 `useRoutes(routes, config.basename)` 的第二参（上游 bug，该参数实为 `locationArg`）|
| `Flowise/packages/ui/src/routes/RequireAuth.jsx` | embed 模式跳过 `currentUser` 检查 |
| `Flowise/packages/ui/src/store/constant.js` | `baseURL` 自动追加 `/flowise` 前缀，axios 请求经 easy-ai 反代 |
| `Flowise/packages/ui/vite.config.js` | 硬编码 `base: '/flowise/'` |
| `Flowise/packages/server/.env`（不入库）| `PORT=3001`、`EASYAI_TRUSTED_HEADER=true`、共享密钥、`IFRAME_ORIGINS=*` |

### easy-ai

| 文件 | 改动 |
| --- | --- |
| `backend/app/api/flowise_proxy.py` | 新增：`/flowise/*` 反向代理，cookie 鉴权 + HMAC 注入 + 流式转发 |
| `backend/app/api/auth_api.py` | login 下发 httpOnly cookie；新增 logout 清 cookie |
| `backend/app/core/request_context.py` | 全站 cookie 优先，Bearer 作为 SDK/CLI 兜底 |
| `backend/app/core/config.py` | 新增 `flowise_*` 配置 |
| `backend/app/main.py` | 注册 `flowise_proxy_router`（挂根路径，不在 `/api/v1` 下）|
| `backend/app/.env.example` | 文档化 Flowise 配置 |
| `frontend/src/api/request.ts` | axios `withCredentials: true`；删除 Bearer 注入；401 → 跳 `/login` |
| `frontend/src/api/auth.ts` | 新增 `logout()` |
| `frontend/src/stores/auth.ts` | 删除 token / localStorage；`init()` 通过 `/auth/me` 引导登录态 |
| `frontend/src/router/index.ts` | `beforeEach` 中 lazy await `auth.init()` |
| `frontend/src/layouts/MainLayout.vue` | 删除重复 `loadProfile`；logout await 后端清 cookie |
| `frontend/vite.config.ts` | dev proxy `/flowise → :8000` |

## 关键约定

- **共享密钥**：`FLOWISE_SHARED_SECRET`(easy-ai) 必须与 `EASYAI_SHARED_SECRET`(Flowise) 完全一致。
- **签名格式**：`HMAC-SHA256(secret, "{user_id}.{workspace_id}.{ts_ms}")`，hex 编码。`ts_ms` 偏差超过 60 秒拒绝。
- **iframe URL**：`/flowise/agentcanvas/{flow_id}`（不带任何 query 参数；浏览器自动携带 cookie）。
- **路径前缀**：浏览器侧所有 Flowise URL 都在 `/flowise/` 之下，proxy 转发到 Flowise 时剥掉前缀（`path:path` 捕获 + 拼接到 `FLOWISE_INTERNAL_URL`）。
- **Flowise 数据隔离**：M1 使用 Flowise 默认 Organization + 默认 Workspace（OPEN_SOURCE 单租户），所有 easy-ai 用户共享。多用户/多工作区映射在 M2 落地。
- **Cookie 安全属性**：`httpOnly` + `SameSite=Lax` + `Path=/`，前端 JS 完全无法读取。

## 启动步骤

### 1. 一次性引导 Flowise 默认工作区

OPEN_SOURCE 模式下 Organization+Workspace 在首次"注册账号"时才创建。trustedHeaderAuth 依赖这两条记录存在，**第一次必须以独立模式注册一个账号**：

```bash
cd Flowise/packages/server
EASYAI_TRUSTED_HEADER=false pnpm --filter flowise build
EASYAI_TRUSTED_HEADER=false pnpm --filter flowise start
# 浏览器访问 http://localhost:3001 → 注册任意账号 → 看到画布列表后停服
```

之后 `~/.flowise/database.sqlite` 即包含默认 Org+Workspace，可复用。

### 2. 构建 Flowise UI

```bash
cd Flowise
rm -rf packages/ui/build packages/ui/.turbo .turbo
pnpm --filter flowise-ui build

# 验证产物 asset 路径包含 /flowise/ 前缀
grep -o 'src="[^"]*assets/[^"]*"' packages/ui/build/index.html | head -3
```

不需要 `VITE_BASE` 环境变量（已硬编码）。

### 3. 启动 Flowise（嵌入模式）

```bash
cd Flowise
pnpm start          # 监听 http://127.0.0.1:3001
# .env: PORT=3001 + EASYAI_TRUSTED_HEADER=true + EASYAI_SHARED_SECRET=...
```

### 4. 配置 easy-ai 后端

`backend/app/.env`:

```env
FLOWISE_ENABLED=true
FLOWISE_INTERNAL_URL=http://127.0.0.1:3001
FLOWISE_SHARED_SECRET=change-me-easyai-flowise   # 与 Flowise .env 一致
```

启动后端：

```bash
cd backend && uv run python app/run.py
```

### 5. 启动 easy-ai 前端

```bash
cd frontend && make dev
# http://localhost:5173
```

## 验证流程

1. 清浏览器 cookie 与 localStorage（确保是干净状态）。
2. 打开 `http://localhost:5173/` → 自动跳 `/login`。
3. 登录任意 easy-ai 账号；DevTools → Application → Cookies 应能看到 `easyai_token`(httpOnly)，**localStorage 为空**。
4. 刷新页面：仍保持登录（router guard 调 `auth.init()` → `/api/v1/auth/me` 通过 cookie 拿用户）。
5. 直接访问 `http://localhost:5173/flowise/agentflows`：
   - **不**跳 Flowise 登录页；
   - 渲染 Flowise 的 Agent Flows 列表（可能为空）；
   - Network 面板看到 `GET /flowise/api/v1/agentflows` 返回 200；
   - 资源（`/flowise/assets/index-*.js`、`manifest.json`）全部 200。
6. 进入某个画布 `/flowise/agentcanvas/<id>`：编辑器正常渲染，可拖拽节点、可保存。
7. 点登出：cookie 被 `/api/v1/auth/logout` 清除 → 跳回 `/login`。

## 已知限制 / 留待后续里程碑

- **单工作区**：所有 easy-ai 用户映射到同一 Flowise Workspace。M2 实现按 easy-ai 用户/工作区 lazy provision Flowise User+Workspace。
- **WebSocket**：HTTP SSE 已支持（`StreamingResponse` + `aiter_raw`）。WebSocket 升级未实现；Flowise 画布编辑不依赖 WS，运行时 prediction 走 SSE，均可用。
- **业务联动**：`AppFormView.vue` 创建 Agent Flow 时尚未联动调 Flowise 创建 chatflow，`tb_app` 也未加 `flowise_chatflow_id` 字段。M2 落地。
- **Flowise UI 热更新**：M1 用 Flowise 生产构建（server 服务静态文件），不支持 Flowise UI 的 dev HMR。如需边改边联调，可再加按 path 分流的 dev proxy。

## 故障排查

| 现象 | 原因 / 处理 |
| --- | --- |
| `503 flowise integration disabled` | 后端 `FLOWISE_ENABLED=false`，改成 `true` 后重启 |
| `401 Unauthorized` 访问 `/flowise/*` | 浏览器没带 `easyai_token` cookie，先登录 easy-ai；或 cookie 已过期 |
| `easyai trusted-header signature mismatch` | 两端 `*_SHARED_SECRET` 不一致，或服务器时钟漂移 > 60s |
| `503 ... no default Flowise workspace found` | 跳过了"步骤 1"。先用独立模式注册一次 |
| 页面白屏，console 无错误 | 多半是 Router basename 没生效。检查 `index.jsx` 的 `<BrowserRouter basename="/flowise">` 是否在最新构建里 |
| iframe 加载白屏，Network 看到 `/assets/...` 404 | Flowise 没用最新 vite.config.js 重新构建（`base: '/flowise/'`） |
| Flowise UI 跳到 `/login` | `RequireAuth` 没识别到 embed 模式。确认 `embed.js` 的 `isEmbedMode()` 返回 true，且未被 tree-shake |
| 登录后刷新仍跳 `/login`，但 `/api/v1/auth/me` 返回 200 | 检查 axios `withCredentials: true`；或 router guard 是否 await 了 `auth.init()` |
