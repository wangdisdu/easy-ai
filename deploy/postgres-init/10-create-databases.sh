#!/bin/bash
# 只在 postgres 数据目录首次初始化时执行一次(pg 官方镜像 entrypoint 约定)。
# 显式创建 easy-ai 和 langfuse 两个应用库,均由 ${POSTGRES_USER} 超级用户拥有,
# 两边共用同一套凭据。
#
# POSTGRES_DB=postgres 保留为 bootstrap 默认库(仅用于连 pg 执行下面的 CREATE),
# langfuse 和 easy-ai 运行时都不使用它。
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE langfuse OWNER ${POSTGRES_USER};
  CREATE DATABASE easyai   OWNER ${POSTGRES_USER};
EOSQL
