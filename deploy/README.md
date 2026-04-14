# easy-ai 全栈一键部署

利用 Docker Compose 同时启动 easy-ai backend / frontend、Flowise（嵌入模式）、Langfuse 全套（postgres + clickhouse + redis + minio + langfuse-web/worker）。

## 拓扑

```
浏览器
  └── easy-ai-frontend  (nginx :5173)
        ├── /api/*       → easy-ai-backend :8000
        └── /flowise/*   → easy-ai-backend :8000  (反代 + 注入 HMAC)
                              └── flowise :3001  (内网,不直接暴露)
                              └── langfuse-web :3000
```

所有内部服务通过 docker network `easy-ai-net` 通信，只有 `easy-ai-frontend` 和 `langfuse-web` 暴露宿主端口。

## 前置条件

- Docker 24+ 和 Docker Compose v2（必须支持 `include:` 顶级字段）
- 宿主机至少 8 GB 内存（Langfuse 全栈较重）
- 已 `git submodule update --init --recursive` 拉取 Flowise / langfuse 子模块

## 一键启动

```bash
cd deploy
cp .env.example .env
vim .env                  # 修改所有 change-me / CHANGEME 密钥
./deploy.sh up            # 首次会构建 backend / frontend / flowise 镜像
```

启动完成后访问：
- easy-ai：`http://<host>:5173`（端口由 `EASYAI_HTTP_PORT` 控制）
- Langfuse：`http://<host>:3000`

## 首次必须的 Flowise 引导

OPEN_SOURCE 模式下，Flowise 的默认 Organization+Workspace 在「首次注册账号」时才会创建。
我们的 trusted-header 中间件依赖这两条记录，所以首次必须手动跑一次：

```bash
./deploy.sh bootstrap-flowise   # 打印操作步骤
```

简化版操作：
```bash
docker compose stop flowise
docker compose run --rm -p 3001:3001 -e EASYAI_TRUSTED_HEADER=false flowise
# 浏览器打开 http://<host>:3001 → 注册任意账号 → 看到画布列表后 Ctrl+C
docker compose up -d flowise
```

之后 Flowise 数据存在 docker volume `flowise-data` 里，重启不丢。

## Langfuse keys 配置

第一次启动 Langfuse 后需要：
1. 浏览器登录 `http://<host>:3000`，创建账号 + 组织 + project
2. 在 project 里生成 API Key（public + secret）
3. 把 keys 填入 `deploy/.env` 的 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
4. 设置 `LANGFUSE_ENABLED=true`
5. `./deploy.sh restart easy-ai-backend`

## 常用命令

```bash
./deploy.sh up           # 启动(含构建)
./deploy.sh down         # 停止并删除容器(volume 保留)
./deploy.sh restart      # 重启全部
./deploy.sh logs         # 流式查看所有日志
./deploy.sh logs easy-ai-backend  # 单服务日志
./deploy.sh ps           # 服务状态
```

清空数据（谨慎）：
```bash
docker compose down -v   # -v 会同时删除 easy-ai-data / flowise-data / langfuse 全部 volume
```

## 数据持久化

| Volume | 内容 |
| --- | --- |
| `easy-ai-data` | easy-ai 后端 SQLite (`easy_ai.db`) |
| `flowise-data` | Flowise SQLite + secrets + 上传文件 |
| langfuse 自带 | postgres / clickhouse / redis / minio 各自 volume |

## 升级 / 重建

代码改动后：
```bash
./deploy.sh up           # --build 默认带在 up 命令中,会自动重新构建变更的镜像
```

只重建某个服务：
```bash
docker compose build easy-ai-backend && docker compose up -d easy-ai-backend
```

## 故障排查

| 现象 | 处理 |
| --- | --- |
| `503 flowise integration disabled` | backend 没读到 `FLOWISE_ENABLED=true`,检查 .env 后 restart easy-ai-backend |
| `easyai trusted-header signature mismatch` | `FLOWISE_SHARED_SECRET` 两端不一致;两端都从同一个 .env 读,重启即可 |
| `503 ... no default Flowise workspace found` | 没做 `bootstrap-flowise` |
| nginx `502 Bad Gateway` | backend 没起或还在初始化,`./deploy.sh logs easy-ai-backend` 看启动日志 |
| Flowise 白屏 | volume 旧数据残留,`docker volume rm easy-ai_flowise-data` 后重新 bootstrap |
| Langfuse postgres 启动失败 | 内存不足或 5432 端口冲突;`docker compose logs postgres` |

## 端口占用清单

| 服务 | 宿主端口 | 来源 |
| --- | --- | --- |
| easy-ai-frontend (nginx) | `${EASYAI_HTTP_PORT}` (默认 5173) | 本 compose |
| langfuse-web | 3000 | langfuse compose |
| minio console | 9090 | langfuse compose |

其余服务（easy-ai-backend / flowise / postgres / clickhouse / redis / minio API）仅在内网暴露。
