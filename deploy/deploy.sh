#!/usr/bin/env bash
# easy-ai 一键部署脚本
#
# 用法:
#   ./deploy.sh up          # 启动全部服务(首次会构建镜像)
#   ./deploy.sh down        # 停止并删除容器(保留 volume)
#   ./deploy.sh restart     # 重启
#   ./deploy.sh logs [svc]  # 查看日志
#   ./deploy.sh ps          # 查看状态
#
# 首次启动时 Flowise 会自动创建默认 Organization+Workspace+admin 账号
# (由 easyaiBootstrapDefaults 完成),无需任何手动引导步骤。
set -euo pipefail

cd "$(dirname "$0")"

PROJECT="easy-ai"
ENV_FILE=".env"
COMPOSE_FILE="docker-compose.yml"

if [[ ! -f "${ENV_FILE}" ]]; then
    if [[ -f .env.example ]]; then
        echo "[easy-ai] .env not found, copying from .env.example"
        cp .env.example .env
        echo "[easy-ai] 请编辑 deploy/.env 修改密钥后重新执行此脚本"
        exit 1
    else
        echo "[easy-ai] missing .env and .env.example" >&2
        exit 1
    fi
fi

COMPOSE=(docker compose -p "${PROJECT}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")

cmd="${1:-up}"
shift || true

case "${cmd}" in
    up)
        "${COMPOSE[@]}" up -d --build "$@"
        echo
        echo "[easy-ai] 启动完成。"
        easyai_port=$(grep -E '^EASYAI_HTTP_PORT=' .env | cut -d= -f2)
        langfuse_port=$(grep -E '^LANGFUSE_WEB_PORT=' .env | cut -d= -f2)
        echo "  - easy-ai 入口: http://localhost:${easyai_port:-18080}"
        echo "  - Langfuse:    http://localhost:${langfuse_port:-18030}"
        echo "  - Flowise:     内网,经 easy-ai 反代访问,不直接暴露宿主端口"
        echo "  - RAGFlow API: http://127.0.0.1:18040  (内网,经 easy-ai-backend 调用)"
        echo "  - RAGFlow UI:  http://127.0.0.1:18044  (仅运维直访)"
        echo
        echo "Flowise 默认 Organization+Workspace 会在首次启动时自动创建,无需手动引导。"
        echo "RAGFlow 首次启动后,需通过 easy-ai 后台调用 bootstrap 接口生成 API Key 并回写 .env。"
        ;;
    down)
        "${COMPOSE[@]}" down "$@"
        ;;
    restart)
        "${COMPOSE[@]}" restart "$@"
        ;;
    logs)
        "${COMPOSE[@]}" logs -f "$@"
        ;;
    ps)
        "${COMPOSE[@]}" ps
        ;;
    config)
        "${COMPOSE[@]}" config
        ;;
    *)
        echo "未知命令: ${cmd}" >&2
        echo "用法: $0 {up|down|restart|logs|ps|config}" >&2
        exit 1
        ;;
esac
