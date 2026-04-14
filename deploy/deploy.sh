#!/usr/bin/env bash
# easy-ai 一键部署脚本
#
# 用法:
#   ./deploy.sh up          # 启动全部服务(首次会构建镜像)
#   ./deploy.sh down        # 停止并删除容器(保留 volume)
#   ./deploy.sh restart     # 重启
#   ./deploy.sh logs [svc]  # 查看日志
#   ./deploy.sh ps          # 查看状态
#   ./deploy.sh bootstrap-flowise  # 首次引导 Flowise 默认 Org+Workspace
#
set -euo pipefail

cd "$(dirname "$0")"

PROJECT="easy-ai"
ENV_FILE=".env"
EASYAI_FILE="docker-compose.yml"
LANGFUSE_FILE="../langfuse/docker-compose.yml"

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

if [[ ! -f "${LANGFUSE_FILE}" ]]; then
    echo "[easy-ai] 缺少 langfuse 子模块,请先执行: git submodule update --init --recursive" >&2
    exit 1
fi

COMPOSE=(docker compose -p "${PROJECT}" --env-file "${ENV_FILE}" -f "${EASYAI_FILE}" -f "${LANGFUSE_FILE}")

cmd="${1:-up}"
shift || true

case "${cmd}" in
    up)
        "${COMPOSE[@]}" up -d --build "$@"
        echo
        echo "[easy-ai] 启动完成。"
        echo "  - easy-ai 入口: http://localhost:$(grep -E '^EASYAI_HTTP_PORT=' .env | cut -d= -f2)"
        echo "  - Langfuse:    http://localhost:3000"
        echo "  - Flowise:     内网,经 easy-ai 反代访问,不直接暴露宿主端口"
        echo
        echo "首次启动需引导 Flowise 默认 Org+Workspace:"
        echo "  ./deploy.sh bootstrap-flowise"
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
    bootstrap-flowise)
        cat <<EOF
[easy-ai] Flowise 首次引导步骤:

OPEN_SOURCE 模式下 Org+Workspace 在首次"注册账号"时才创建,trustedHeaderAuth
中间件依赖这两条记录,所以第一次必须以独立模式注册一个账号:

  1. 临时停止 flowise 容器
       ${COMPOSE[*]} stop flowise
  2. 用独立模式启动一次(关闭 trusted-header,临时开放注册端口)
       ${COMPOSE[*]} run --rm -p 3001:3001 \\
         -e EASYAI_TRUSTED_HEADER=false flowise
  3. 浏览器打开 http://localhost:3001 → 注册任意账号 → 看到画布列表后 Ctrl+C
  4. 重新启动正常模式
       ${COMPOSE[*]} up -d flowise

之后 flowise volume 已包含默认 Org+Workspace,后续都走 trusted-header。
EOF
        ;;
    *)
        echo "未知命令: ${cmd}" >&2
        echo "用法: $0 {up|down|restart|logs|ps|config|bootstrap-flowise}" >&2
        exit 1
        ;;
esac
