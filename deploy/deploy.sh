#!/usr/bin/env bash
# easy-ai 一键部署脚本
#
# 用法:
#   ./deploy.sh start [服务...|infra]           启动(镜像缺失才构建,不强制重建)
#   ./deploy.sh stop  [服务...|infra]           停止容器(保留容器与数据卷)
#   ./deploy.sh restart [服务...|infra]         重启
#   ./deploy.sh build [--no-cache] [服务...|infra]   构建镜像(始终实时日志 --progress=plain)
#   ./deploy.sh redeploy [服务...|infra] [--no-cache] [--volumes]
#                                               全量重新构建并重建容器
#                                               默认保留数据卷;--volumes 才清空(需二次确认)
#                                               --no-cache 强制不走构建缓存
#   ./deploy.sh status | ps                     查看容器状态(含 healthy/exited)
#   ./deploy.sh logs [服务...|infra]            跟踪日志
#   ./deploy.sh down [--volumes]                停止并删除容器(--volumes 连数据卷一起删)
#   ./deploy.sh config                          渲染并校验 compose 配置
#
# 服务组关键字:
#   infra   = 除 easy-ai-backend / easy-ai-frontend 外的全部服务
#             (backend/frontend 通常本地开发,不由本脚本托管)
#             例:./deploy.sh redeploy infra        只重建除前后端外的全部
#                 ./deploy.sh build infra flowise   组与具体服务可混用
#
# 首次启动时 Flowise 会自动创建默认 Organization+Workspace+admin 账号
# (由 easyaiBootstrapDefaults 完成),无需任何手动引导步骤。
set -euo pipefail

cd "$(dirname "$0")"

PROJECT="easy-ai"
ENV_FILE="${PWD}/.env"
COMPOSE_FILE="${PWD}/docker-compose.yml"

# backend/frontend 默认本地开发,infra 组会排除它们
DEV_SERVICES=("easy-ai-backend" "easy-ai-frontend")

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

# FLOWISE_DEV_PROXY=true 时启用 flowise-dev-proxy(nginx 反代 Flowise),
# 让 dev 在 http://127.0.0.1:8888/flowise/ 直接访问 Flowise UI 调试。
# 生产环境别开,Flowise 应该走 easy-ai-backend 反代(带 HMAC SSO)。
if grep -qE '^FLOWISE_DEV_PROXY=true' "${ENV_FILE}"; then
    COMPOSE+=(--profile flowise-dev)
    echo "[easy-ai] flowise-dev profile enabled (FLOWISE_DEV_PROXY=true) -> http://127.0.0.1:8888/flowise/"
fi

# ---- 工具函数 ----

# 列出当前 profile 下的全部服务名
list_all_services() {
    "${COMPOSE[@]}" config --services
}

# 把参数里的 infra 关键字展开为「除 DEV_SERVICES 外的全部服务」,其余参数原样保留。
# 结果写入全局数组 EXPANDED。
EXPANDED=()
expand_targets() {
    EXPANDED=()
    local infra_list=""
    local a
    for a in "$@"; do
        if [[ "${a}" == "infra" ]]; then
            if [[ -z "${infra_list}" ]]; then
                local excl
                excl=$(printf '%s\n' "${DEV_SERVICES[@]}")
                infra_list=$(list_all_services | grep -vxF "${excl}" | tr '\n' ' ')
            fi
            # shellcheck disable=SC2206
            EXPANDED+=(${infra_list})
        else
            EXPANDED+=("${a}")
        fi
    done
}

print_endpoints() {
    echo
    echo "[easy-ai] 启动完成。"
    local easyai_port langfuse_port ragflow_ui_port
    easyai_port=$(grep -E '^EASYAI_HTTP_PORT=' .env | cut -d= -f2)
    langfuse_port=$(grep -E '^LANGFUSE_WEB_PORT=' .env | cut -d= -f2)
    ragflow_ui_port=$(grep -E '^RAGFLOW_WEB_PORT=' .env | cut -d= -f2)
    echo "  - easy-ai 入口: http://localhost:${easyai_port:-18080}"
    echo "  - Langfuse:    http://localhost:${langfuse_port:-18030}"
    echo "  - Flowise:     内网,经 easy-ai 反代访问,不直接暴露宿主端口"
    echo "  - RAGFlow API: http://127.0.0.1:18040  (内网,经 easy-ai-backend 调用)"
    echo "  - RAGFlow UI:  http://localhost:${ragflow_ui_port:-18044}  (已对外开放)"
    echo
    echo "Flowise 默认 Organization+Workspace 会在首次启动时自动创建,无需手动引导。"
    echo "  - 默认管理员 admin@easyai.com 由各服务启动期自动创建,无需手动 bootstrap。"
}

usage() {
    echo "用法: $0 {start|stop|restart|build|redeploy|status|ps|logs|down|config} [服务...|infra] [选项]" >&2
    echo "      infra = 除 ${DEV_SERVICES[*]} 外的全部服务" >&2
}

cmd="${1:-start}"
shift || true

case "${cmd}" in
    start|up)
        expand_targets "$@"
        # 不带 --build:镜像缺失时 compose 仍会自动构建,但已存在则直接复用(不因改码重建)
        "${COMPOSE[@]}" up -d ${EXPANDED[@]+"${EXPANDED[@]}"}
        # 仅在「启动全部」时打印入口信息
        if [[ ${#EXPANDED[@]} -eq 0 ]]; then
            print_endpoints
        fi
        ;;

    stop)
        expand_targets "$@"
        "${COMPOSE[@]}" stop ${EXPANDED[@]+"${EXPANDED[@]}"}
        ;;

    restart)
        expand_targets "$@"
        "${COMPOSE[@]}" restart ${EXPANDED[@]+"${EXPANDED[@]}"}
        ;;

    build)
        no_cache=()
        targets=()
        for arg in "$@"; do
            case "${arg}" in
                --no-cache) no_cache=(--no-cache) ;;
                *) targets+=("${arg}") ;;
            esac
        done
        expand_targets ${targets[@]+"${targets[@]}"}
        echo "[easy-ai] 构建镜像(实时日志)..."
        "${COMPOSE[@]}" build --progress=plain ${no_cache[@]+"${no_cache[@]}"} ${EXPANDED[@]+"${EXPANDED[@]}"}
        echo "[easy-ai] 构建完成。"
        ;;

    redeploy)
        no_cache=()
        wipe_volumes=false
        targets=()
        for arg in "$@"; do
            case "${arg}" in
                --no-cache) no_cache=(--no-cache) ;;
                --volumes|-v) wipe_volumes=true ;;
                *) targets+=("${arg}") ;;
            esac
        done
        expand_targets ${targets[@]+"${targets[@]}"}

        if [[ "${wipe_volumes}" == true && ${#EXPANDED[@]} -gt 0 ]]; then
            echo "[easy-ai] --volumes 会删除项目全部数据卷,不能与指定服务同时使用。" >&2
            echo "[easy-ai] 如需清空数据请执行不带服务名的全量重部署: $0 redeploy --volumes" >&2
            exit 1
        fi

        if [[ ${#EXPANDED[@]} -gt 0 ]]; then
            # 指定服务/服务组:只重建这些,不动整栈(不 down 全部)
            echo "[easy-ai] 重新构建并重建容器(实时日志): ${EXPANDED[*]}"
            "${COMPOSE[@]}" build --progress=plain ${no_cache[@]+"${no_cache[@]}"} "${EXPANDED[@]}"
            "${COMPOSE[@]}" up -d --force-recreate "${EXPANDED[@]}"
            echo "[easy-ai] 重新部署完成: ${EXPANDED[*]}"
        else
            # 全量重部署
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
            echo "[easy-ai] 重新构建(实时日志)..."
            "${COMPOSE[@]}" build --progress=plain ${no_cache[@]+"${no_cache[@]}"}
            echo "[easy-ai] 重建并启动容器..."
            "${COMPOSE[@]}" up -d --force-recreate
            print_endpoints
            echo "[easy-ai] 全量重新部署完成。"
        fi
        ;;

    status|ps)
        "${COMPOSE[@]}" ps -a
        ;;

    logs)
        expand_targets "$@"
        "${COMPOSE[@]}" logs -f --tail=200 ${EXPANDED[@]+"${EXPANDED[@]}"}
        ;;

    down)
        "${COMPOSE[@]}" down "$@"
        ;;

    config)
        "${COMPOSE[@]}" config
        ;;

    -h|--help|help)
        usage
        ;;

    *)
        echo "未知命令: ${cmd}" >&2
        usage
        exit 1
        ;;
esac
