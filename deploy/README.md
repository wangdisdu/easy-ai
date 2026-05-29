# easy-ai 全栈一键部署

单文件 Docker Compose 同时启动：easy-ai backend / frontend、Flowise（嵌入模式）、Langfuse 全套（postgres + clickhouse + redis + minio + langfuse-web/worker）。

## 拓扑

```
浏览器
  ├── easy-ai-frontend  (nginx :18080)   ← 用户唯一入口
  │     ├── /api/*       → easy-ai-backend :8000
  │     └── /flowise/*   → easy-ai-backend :8000  (反代 + 注入 HMAC)
  │                            └── flowise :3001  (内网)
  └── langfuse-web :18030                ← 运维/数据同学直连
```

所有组件在单个 compose project `easy-ai` 下、同一 docker network 里通信。仅 `easy-ai-frontend` 和 `langfuse-web` 对外暴露（0.0.0.0），其它全部绑定 127.0.0.1。

## 前置条件

- Docker 24+ 和 Docker Compose v2
- 宿主机至少 8 GB 内存（Langfuse 全栈较重）
- 已 `git submodule update --init --recursive` 拉取 Flowise / langfuse 子模块（langfuse 子模块里有 CLAUDE.md 等文档，不再使用它的 compose）

## 一键启动

```bash
cd deploy
cp .env.example .env
vim .env                  # 修改所有 change-me / CHANGEME 密钥
./deploy.sh start         # 启动;镜像缺失会自动构建(首次会构建 backend / frontend / flowise)
```

启动完成后访问：
- easy-ai：`http://<host>:18080`（端口由 `EASYAI_HTTP_PORT` 控制）
- Langfuse：`http://<host>:18030`（端口由 `LANGFUSE_WEB_PORT` 控制）

## Flowise 默认 Org+Workspace 自动创建

启用 `EASYAI_TRUSTED_HEADER=true` 时，Flowise 首次启动会自动创建默认的
Organization + Workspace + admin 用户（由 `easyaiBootstrapDefaults` 完成），
无需手动注册。

可通过环境变量覆盖默认值（一般无需修改）：

| 变量 | 默认值 |
| --- | --- |
| `EASYAI_BOOTSTRAP_EMAIL` | `admin@easyai.local` |
| `EASYAI_BOOTSTRAP_NAME` | `easyai-admin` |
| `EASYAI_BOOTSTRAP_PASSWORD` | `Easyai@12345` |

该 admin 账号只是为了让 trusted-header 中间件能定位到单租户的 Org+Workspace；
终端用户始终通过 easy-ai 身份进入 Flowise，不会用到这个账号。Flowise 数据持久
化在 docker volume `flowise-data` 中，后续启动会跳过 bootstrap。

## Langfuse keys 配置

第一次启动 Langfuse 后需要：
1. 浏览器登录 `http://<host>:3000`，创建账号 + 组织 + project
2. 在 project 里生成 API Key（public + secret）
3. 把 keys 填入 `deploy/.env` 的 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
4. 设置 `LANGFUSE_ENABLED=true`
5. `./deploy.sh restart easy-ai-backend`

## 常用命令

```bash
./deploy.sh start        # 启动(镜像缺失才构建,已存在直接复用)
./deploy.sh stop         # 停止容器(保留容器与数据卷)
./deploy.sh down         # 停止并删除容器(volume 保留)
./deploy.sh restart      # 重启全部
./deploy.sh status       # 服务状态(含 healthy/exited)
./deploy.sh logs         # 流式查看所有日志
./deploy.sh logs easy-ai-backend  # 单服务日志
```

服务组关键字 `infra` = 除 `easy-ai-backend` / `easy-ai-frontend` 外的全部服务
（前后端通常本地开发,不由脚本托管),可用于任意接受服务名的命令:
```bash
./deploy.sh start infra      # 只起除前后端外的依赖栈
./deploy.sh redeploy infra   # 只重建除前后端外的全部服务,不动本地前后端
```

清空数据（谨慎）：
```bash
./deploy.sh down --volumes   # 删除容器并清空 easy-ai-data / flowise-data / langfuse 全部 volume
```

## 数据持久化

| Volume | 内容 |
| --- | --- |
| `easy-ai-data` | easy-ai 后端 SQLite (`easy_ai.db`) |
| `flowise-data` | Flowise SQLite + secrets + 上传文件 |
| langfuse 自带 | postgres / clickhouse / redis / minio 各自 volume |

## 升级 / 重建

注意:`start` 不会因代码改动而重建已存在的镜像,重建需显式用 `build` / `redeploy`。

代码改动后全量重建(默认保留数据卷,实时打印构建日志):
```bash
./deploy.sh redeploy             # 全部重建并重建容器
./deploy.sh redeploy --no-cache  # 强制不走构建缓存
./deploy.sh redeploy --volumes   # 同时清空全部数据卷(需输入 yes 二次确认)
```

只重建某个服务 / 服务组(不会 down 整栈,适合本地开发时只刷依赖):
```bash
./deploy.sh redeploy easy-ai-backend   # 只重建并重建该服务容器
./deploy.sh redeploy infra             # 只重建除前后端外的全部服务
./deploy.sh build flowise              # 只构建镜像(实时日志),不重建容器
```

## 故障排查

| 现象 | 处理 |
| --- | --- |
| `503 flowise integration disabled` | backend 没读到 `FLOWISE_ENABLED=true`,检查 .env 后 restart easy-ai-backend |
| `easyai trusted-header signature mismatch` | `FLOWISE_SHARED_SECRET` 两端不一致;两端都从同一个 .env 读,重启即可 |
| `503 ... no default Flowise workspace found` | bootstrap 失败,查 `./deploy.sh logs flowise` 看 `[easyai] bootstrap` 日志 |
| nginx `502 Bad Gateway` | backend 没起或还在初始化,`./deploy.sh logs easy-ai-backend` 看启动日志 |
| Flowise 白屏 | volume 旧数据残留,`docker volume rm easy-ai_flowise-data` 后重新 bootstrap |
| Langfuse postgres 启动失败 | 内存不足或 5432 端口冲突;`./deploy.sh logs postgres` |

## 端口占用清单

所有宿主机端口统一在 **188xx** 段，避开 Vite(5173) / Next(3000) / Prometheus(9090) / Postgres(5432) 等常见本机冲突。

| 服务 | 宿主端口 | 绑定 | 可配置 |
| --- | --- | --- | --- |
| easy-ai-frontend (nginx, 用户入口) | **18080** | 0.0.0.0 | `EASYAI_HTTP_PORT` |
| langfuse-web | **18030** | 0.0.0.0 | `LANGFUSE_WEB_PORT` |
| langfuse-worker | 18033 | 127.0.0.1 | 改 compose |
| postgres | 18032 | 127.0.0.1 | 改 compose |
| redis | 18079 | 127.0.0.1 | 改 compose |
| clickhouse http | 18123 | 127.0.0.1 | 改 compose |
| clickhouse tcp | 18190 | 127.0.0.1 | 改 compose |
| minio API | 18090 | 127.0.0.1 | 改 compose |
| minio console | 18091 | 127.0.0.1 | 改 compose |

`easy-ai-backend` / `flowise` 完全不暴露宿主端口，全部通过 easy-ai-frontend (nginx) 的 `/api/*` 和 `/flowise/*` 反代访问。
