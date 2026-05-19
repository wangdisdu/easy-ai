#!/usr/bin/env bash
# easy-ai 一键部署脚本
#
# 用法:
#   ./deploy.sh up               # 启动全部服务(首次会构建镜像)
#   ./deploy.sh down             # 停止并删除容器(保留 volume)
#   ./deploy.sh restart          # 重启
#   ./deploy.sh redeploy         # 删除容器后重建并启动(保留数据 volume)
#   ./deploy.sh redeploy --volumes  # 同时清空数据 volume(需二次确认)
#   ./deploy.sh logs [svc]       # 查看日志
#   ./deploy.sh ps               # 查看状态
#
# 首次启动时 Flowise 会自动创建默认 Organization+Workspace+admin 账号
# (由 easyaiBootstrapDefaults 完成),无需任何手动引导步骤。
set -euo pipefail

cd "$(dirname "$0")"

PROJECT="easy-ai"
ENV_FILE="${PWD}/.env"
COMPOSE_FILE="${PWD}/docker-compose.yml"

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

# SANDBOX_ENABLED=true 时自动加上 sandbox profile,把 opensandbox-server 与
# sandbox-desktop(本地构建可视化镜像)一并纳入 up/down/build/ps。
if grep -qE '^SANDBOX_ENABLED=true' "${ENV_FILE}"; then
    COMPOSE+=(--profile sandbox)
    echo "[easy-ai] sandbox profile enabled (SANDBOX_ENABLED=true)"
fi

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
        ragflow_ui_port=$(grep -E '^RAGFLOW_WEB_PORT=' .env | cut -d= -f2)
        echo "  - RAGFlow UI:  http://localhost:${ragflow_ui_port:-18044}  (已对外开放)"
        echo
        echo "Flowise 默认 Organization+Workspace 会在首次启动时自动创建,无需手动引导。"
        echo "RAGFlow 镜像由 ragflow/ submodule 本地 build (首次约 5-10 分钟)。"
        echo "  - 默认管理员 easyai@system.local 由 ragflow 容器启动期自动创建,无需手动 bootstrap。"
        ;;
    down)
        "${COMPOSE[@]}" down "$@"
        ;;
    restart)
        "${COMPOSE[@]}" restart "$@"
        ;;
    redeploy)
        wipe_volumes=false
        if [[ "${1:-}" == "--volumes" || "${1:-}" == "-v" ]]; then
            wipe_volumes=true
            shift
        fi
        if [[ "${wipe_volumes}" == true ]]; then
            echo "[easy-ai] 警告: --volumes 会删除所有数据卷(postgres 等),数据不可恢复!"
            read -r -p "确认清空数据并重新部署? 输入 yes 继续: " confirm
            if [[ "${confirm}" != "yes" ]]; then
                echo "[easy-ai] 已取消。"
                exit 1
            fi
            echo "[easy-ai] 停止并删除容器及数据卷..."
            "${COMPOSE[@]}" down --volumes
        else
            echo "[easy-ai] 停止并删除容器(保留数据卷)..."
            "${COMPOSE[@]}" down
        fi
        echo "[easy-ai] 重新构建并启动..."
        "${COMPOSE[@]}" up -d --build "$@"
        echo
        echo "[easy-ai] 重新部署完成。"
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
        echo "用法: $0 {up|down|restart|redeploy|logs|ps|config}" >&2
        exit 1
        ;;
esac
