UV_DEFAULT_INDEX ?= https://pypi.tuna.tsinghua.edu.cn/simple
export UV_DEFAULT_INDEX

UV_RUN := uv run
APP := app

.PHONY: py-dev dev code-format code-check db-upgrade db-revision db-downgrade db-current help

help:
	@echo "Targets:"
	@echo "  py-dev         创建 Python 开发环境并安装所需依赖"
	@echo "  dev            启动开发服务器(端口 8000,自动 reload)"
	@echo "  code-format    ruff --fix(含 import 排序) + black"
	@echo "  code-check     ruff + black --check(CI)"
	@echo "  db-upgrade     应用所有未执行的 alembic 迁移(升级到 head)"
	@echo "  db-current     查看当前数据库处于哪个 revision"
	@echo "  db-revision    生成新的 autogenerate 迁移,用法: make db-revision m='add xxx'"
	@echo "  db-downgrade   回退一个版本 (make db-downgrade step=-1)"

py-dev:
	uv sync
	@if [ ! -f .env ]; then cp .env.example .env; fi

dev:
	$(UV_RUN) python $(APP)/run.py

code-format:
	$(UV_RUN) ruff check --fix $(APP)
	$(UV_RUN) black $(APP)

code-check:
	$(UV_RUN) ruff check    $(APP)
	$(UV_RUN) black --check $(APP)

db-upgrade:
	$(UV_RUN) alembic upgrade head

db-current:
	$(UV_RUN) alembic current

db-revision:
	@if [ -z "$(m)" ]; then echo "usage: make db-revision m='your message'"; exit 1; fi
	$(UV_RUN) alembic revision --autogenerate -m "$(m)"

db-downgrade:
	$(UV_RUN) alembic downgrade $(or $(step),-1)
