# Langfuse 本地开发启动指南

本文档说明如何在 macOS 上从源码启动 [Langfuse](https://github.com/langfuse/langfuse)（以仓库内 `languse` 子模块、标签 `v3.99.0` 为例），便于调试与功能预览。

## 1. 前置条件

| 依赖 | 说明 |
|------|------|
| **Node.js** | 仓库 `engines` 要求 **20.x**（不建议用 22，易遇类型/工具链差异） |
| **pnpm** | **9.5.0**（根目录 `package.json` 的 `packageManager` 字段） |
| **Docker** | 用于拉起 Postgres / ClickHouse / Redis / MinIO |
| **Homebrew** | 安装 `golang-migrate`（ClickHouse 迁移脚本依赖 `migrate` 命令） |

可选：用 conda 单独建 Node 20 环境，避免污染 `base`：

```bash
conda create -n langfuse-node20 -c conda-forge nodejs=20 pnpm=9.5.0
conda activate langfuse-node20
```

## 2. 目录与仓库

在 monorepo 根目录下，Langfuse 源码位于：

```text
languse/
```

以下命令均在 **`languse` 目录** 内执行（先 `cd languse`）。

## 3. 环境变量

```bash
cp .env.dev.example .env
```

在 `.env` 中建议**固定 Postgres 镜像版本**，避免 `postgres:latest` 升级后与旧数据卷不兼容（常见报错见下文「故障排查」）：

```bash
POSTGRES_VERSION=16
```

## 4. 安装依赖

优先使用锁文件安装，避免依赖漂移导致 `next-auth` 补丁无法应用或 TypeScript 版本过新：

```bash
pnpm install --frozen-lockfile
```

若曾修改过 `pnpm-lock.yaml` 或遇到 `ERR_PNPM_PATCH_NOT_APPLIED`（`next-auth@4.24.11`），可恢复锁文件后重装：

```bash
git restore pnpm-lock.yaml
rm -rf node_modules web/node_modules worker/node_modules packages/*/node_modules
pnpm store prune
pnpm install --frozen-lockfile
```

## 5. 启动基础设施（Docker Compose）

```bash
pnpm run infra:dev:up
```

`docker-compose.dev.yml` 会启动：

| 服务 | 作用 |
|------|------|
| **postgres** | 主库（元数据、业务表） |
| **clickhouse** | 分析型存储 |
| **redis** | 缓存 / 队列 |
| **minio** | S3 兼容对象存储 |

应用进程 **不在** compose 内，需后续用 `pnpm run dev` 本地启动 `web` + `worker`。

## 6. 安装 golang-migrate（ClickHouse 迁移必需）

`ch:reset` 等脚本会调用 `migrate`，需单独安装：

```bash
brew install golang-migrate
migrate -version
```

若在 conda 环境中找不到命令，确保 Homebrew 在 PATH 靠前：

```bash
export PATH="/opt/homebrew/bin:$PATH"
```

## 7. 初始化数据库

按顺序执行（均在 `languse` 根目录）：

```bash
pnpm --filter=shared run db:reset
pnpm --filter=shared run ch:reset
pnpm --filter=shared run db:seed:examples
```

说明：

- **db:reset**：Postgres schema + seed（依赖 Prisma 等）
- **ch:reset**：ClickHouse 迁移与种子数据（依赖 `migrate`）
- **db:seed:examples**：示例数据，便于界面有内容可看

## 8. 启动应用

同时启动 **web** 与 **worker**：

```bash
pnpm run dev
```

仅前端调试（不推荐长期，后台任务可能不完整）：

```bash
pnpm run dev:web
```

浏览器访问：**http://localhost:3000**（以 Next 默认端口为准，见终端输出）。

## 9. 一键初始化（可选，会重置数据）

适合全新机器或愿意清空本地卷时：

```bash
pnpm run dx
```

该命令会安装依赖、清理并重建基础设施、重置 DB/CH、seed 并启动 dev。  
**注意**：会清理/重建 Docker 卷与数据库数据，请谨慎使用。

## 10. 停止与清理

停止基础设施：

```bash
pnpm run infra:dev:down
```

连同卷删除（彻底清空本地数据）：

```bash
pnpm run infra:dev:prune
```

## 11. 故障排查

### 11.1 Postgres 容器 unhealthy（镜像 18+ 与旧数据卷冲突）

现象：日志提示数据目录格式与 `pg_ctlcluster` 不兼容、升级需 `pg_upgrade` 等。

处理：

1. 在 `.env` 中设置 `POSTGRES_VERSION=16`（或与团队一致的固定主版本）。
2. 删除旧卷后重建：

```bash
docker compose -f docker-compose.dev.yml down -v
pnpm run infra:dev:up
```

再重新执行第 7 节初始化命令。

### 11.2 `ERR_PNPM_PATCH_NOT_APPLIED`（next-auth）

确保 `pnpm-lock.yaml` 未被意外升级，并按第 4 节用 `--frozen-lockfile` 安装；必要时将 `web` 中 `next-auth` 固定为补丁对应版本后重装。

### 11.3 `db:reset` 时 TypeScript 编译错误（如 encryption.ts）

多为 **TypeScript / @types/node 版本被提升** 导致。恢复锁文件并全量重装 `node_modules`（见第 4 节）。

### 11.4 `golang-migrate is not installed`

安装 `golang-migrate` 并确认 `migrate` 在 PATH 中（见第 6 节）。

## 12. 架构速览（本地 dev）

- **进程**：至少 **web**（Next.js）+ **worker**（队列消费者）。
- **基础设施**：Postgres + ClickHouse + Redis + MinIO，由 Docker Compose 提供。

更细的模块划分见仓库内 `AGENTS.md` 与 `README.md`。

## 13. 许可说明（商用前必读）

仓库为 MIT + 企业目录混合授权：`ee/`、`web/src/ee/`、`worker/src/ee/` 等路径受单独许可约束。商用或裁剪前请阅读根目录 `LICENSE` 与 `ee/LICENSE`。

---

*文档根据本地实践整理；Langfuse 版本升级后请以官方文档与仓库脚本为准。*
