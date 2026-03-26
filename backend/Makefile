UV_DEFAULT_INDEX ?= https://pypi.tuna.tsinghua.edu.cn/simple
export UV_DEFAULT_INDEX

UV_RUN := uv run
APP := app

.PHONY: py-dev code-format code-check help

help:
	@echo "Targets:"
	@echo "  py-dev       创建 Python 开发环境并安装所需依赖"
	@echo "  code-format  ruff --fix（含 import 排序）+ black"
	@echo "  code-check   ruff + black --check（CI）"

py-dev:
	uv sync
	@if [ ! -f .env ]; then cp .env.example .env; fi

code-format:
	$(UV_RUN) ruff check --fix $(APP)
	$(UV_RUN) black $(APP)

code-check:
	$(UV_RUN) ruff check    $(APP)
	$(UV_RUN) black --check $(APP)
