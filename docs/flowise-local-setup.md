# Flowise 本地启动说明

本文档说明如何在本地以源码方式启动 `Flowise/` 子目录中的 Flowise 服务（v3.1.2）。

## 1. 环境要求

| 依赖     | 版本                               | 备注                                      |
| -------- | ---------------------------------- | ----------------------------------------- |
| Node.js  | `>=18.15.0 <19` 或 `^20`           | 推荐 Node 20 LTS                          |
| pnpm     | `^10.26.0`                         | 必须使用 pnpm，仓库根有 `pnpm-workspace.yaml` |
| Python   | 3.x（可选）                        | 部分原生依赖编译时需要                    |
| 系统工具 | `git`、构建工具链（Xcode CLT）     | macOS 已具备                              |

安装 pnpm（推荐通过 corepack）：

```bash
corepack enable
corepack prepare pnpm@10.26.0 --activate
pnpm -v
```

## 2. 目录结构速览

`Flowise/` 是一个 monorepo（Turborepo + pnpm workspaces），关键 packages：

- `packages/server` — 后端 API（Express + TypeORM），默认端口 `3000`
- `packages/ui` — 前端 React 应用，开发模式默认端口 `8080`
- `packages/components` — 节点/集成组件库
- `packages/api-documentation` — Swagger 文档
- `packages/agentflow` — Agent Flow 相关代码

## 3. 安装依赖

在仓库根目录的 `Flowise/` 下执行：

```bash
cd Flowise
pnpm install
```

> 首次安装会拉取大量原生依赖（如 `sqlite3`、`faiss-node`、`onnxruntime` 等），耗时 5–15 分钟，请保持网络畅通。如遇到 `node-gyp` 报错，确认已安装 Xcode Command Line Tools：`xcode-select --install`。

## 4. 配置环境变量

服务端配置位于 `packages/server/.env`，已有 `.env.example` 可参考。最简配置（使用本地 SQLite，无需额外服务）：

```bash
cd packages/server
cp .env.example .env
```

常用变量：

```env
PORT=3000
# 数据库：留空时默认使用 SQLite，文件位于 ~/.flowise/database.sqlite
# DATABASE_TYPE=postgres
# DATABASE_HOST=localhost
# DATABASE_PORT=5432
# DATABASE_NAME=flowise
# DATABASE_USER=flowise
# DATABASE_PASSWORD=flowise

# 加密密钥（建议设置一个固定值，避免重启后历史凭据失效）
FLOWISE_SECRETKEY_OVERWRITE=easyai-flowise-dev-key

# 日志
LOG_LEVEL=info
DEBUG=false
```

> 数据与密钥默认存放在 `~/.flowise/`，包括 `database.sqlite`、`encryption.key`、`logs/`、`storage/` 等。

可选：开启登录鉴权，在 `.env` 中设置：

```env
FLOWISE_USERNAME=admin
FLOWISE_PASSWORD=admin
```

## 5. 构建

首次启动前必须构建一次（`turbo` 会按依赖顺序构建 `components → server → ui`）：

```bash
cd Flowise
pnpm build
```

构建产物输出到各 package 的 `dist/`。

## 6. 启动方式

### 方式 A：生产模式（推荐，首次验证用）

```bash
cd Flowise
pnpm start
```

启动成功后访问 <http://localhost:3000>。该模式直接以构建产物运行 server，并由 server 托管 UI 静态文件。

### 方式 B：开发模式（热更新）

需要边改代码边验证时使用：

```bash
cd Flowise
pnpm dev
```

`turbo run dev --parallel` 会同时启动：

- server: <http://localhost:3000>（nodemon 监听 TypeScript 变更）
- ui: <http://localhost:8080>（Vite dev server，代理 API 到 3000）

开发模式下请通过 **<http://localhost:8080>** 访问 UI。

## 7. 常用运维命令

```bash
# 创建用户（启用鉴权时）
pnpm user

# 启动 worker（队列模式时使用）
pnpm start-worker

# 全量清理构建产物
pnpm clean

# 彻底重置（删除 node_modules + .turbo + dist）
pnpm nuke
```

## 8. 与 easy-ai 集成时的注意事项

- Flowise 默认占用 `3000`，与 Langfuse Web 默认端口冲突。如同时启动两者，请将其中之一改为其他端口（修改 `Flowise/packages/server/.env` 的 `PORT`）。
- 数据持久化在用户目录 `~/.flowise/`，重装 node_modules 不会丢数据；如需重置，删除该目录即可。
- easy-ai 后端通过 HTTP 调用 Flowise 时，使用 `http://localhost:<PORT>/api/v1` 作为基址。

## 9. 常见问题

| 问题 | 解决方案 |
| ---- | -------- |
| `pnpm install` 卡在 sqlite3/onnxruntime | 检查 Xcode CLT、清空 `~/.npm`、重试，必要时设置 npm 镜像 |
| 启动后页面空白 | 确认已执行 `pnpm build`；生产模式下 UI 由 server 提供 |
| `EADDRINUSE :::3000` | 修改 `.env` 中的 `PORT`，或释放占用进程 |
| 历史 Credential 解密失败 | `.env` 未设置 `FLOWISE_SECRETKEY_OVERWRITE`，每次启动会生成新 key；建议固定该值 |
| 构建报 `turbo: command not found` | 在 `Flowise/` 目录下执行命令（依赖通过 workspace 安装），不要在子包目录直接运行 |

## 10. 快速启动清单

```bash
cd Flowise
corepack enable && corepack prepare pnpm@10.26.0 --activate
pnpm install
cp packages/server/.env.example packages/server/.env
# 编辑 .env，至少设置 FLOWISE_SECRETKEY_OVERWRITE
pnpm build
pnpm start
# 浏览器打开 http://localhost:3000
```
