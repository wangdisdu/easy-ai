# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

easy-ai (智瞻 AI) is an enterprise AI platform with modules for RAG (via RAGFlow), TextToSQL, AI agent applications (DeepAgents + LiteLLM), agent orchestration (via Flowise), and observability (via Langfuse). Deployed as a set of services via Docker Compose.

## Repository Structure

- `backend/` — Python 3.12 FastAPI backend
- `frontend/` — Vue 3 + TypeScript frontend (Ant Design Vue, Pinia, Vite)
- `Flowise/` — Git submodule: FlowiseAI agent orchestration
- `langfuse/` — Git submodule: Langfuse observability
- `docs/` — Architecture and design docs
- `eoitek-llm/` — Product prototype design, used as UI/UX reference for frontend development

## Backend

### Setup & Commands

```bash
cd backend
make py-dev          # Create venv and install deps (uses uv)
uv run python app/run.py  # Start dev server (port 8000, auto-reload)
make code-format     # ruff --fix + black
make code-check      # ruff + black --check (CI)
```

Environment: copy `.env.example` to `.env`. Key vars: `DATABASE_URL` (postgres, e.g. `postgresql+psycopg://easyai:...@127.0.0.1:18032/easyai`), `JWT_SECRET`, `SNOWFLAKE_WORKER_ID`. Local dev needs a postgres reachable at `DATABASE_URL` — easiest is `cd deploy && ./deploy.sh start postgres`.

### Architecture (backend/app/)

- `api/` — FastAPI routers. Declare endpoints only; delegate logic to services.
- `service/` — Business logic layer.
- `model/` — Pydantic request/response models (e.g., `UserCreateReq`, `UserResp`).
- `core/` — Config, logging, exceptions (`ServiceError`), error codes (`ErrorCode`), JWT security, request context (`RequestContext`), Snowflake ID generator, unified response (`Resp`, `PagedResp`).
- `db/` — SQLAlchemy ORM schema (`schema.py`) and session management. Schema changes go through Alembic (`backend/alembic/versions/`); run `make db-upgrade` after pulling or generating a migration.

### Conventions

- **API paths are singular**: `/api/v1/user`, `/api/v1/role`, `/api/v1/user-group`
- **Standard REST endpoints per resource**: `GET .../page` (paginated, max 10000), `POST ...`, `GET .../{id}`, `PUT .../{id}`, `DELETE .../{id}`
- **IDs**: Snowflake-generated BIGINT, always transmitted as **strings** in API/frontend to avoid JS precision loss
- **Timestamps**: Unix milliseconds (BIGINT)
- **DB tables**: prefixed `tb_`, no foreign key constraints, standard audit columns (`create_time`, `update_time`, `create_user`, `update_user`)
- **Strings in DB**: `VARCHAR(255)` or `TEXT`; JSON stored as text strings
- **Ruff config**: ignores RUF001/RUF002/RUF003 (Chinese punctuation rules), line-length 100
- **Black**: line-length 100, target py312
- **Error codes**: defined as constants in `ErrorCode` class (`error_code.py`)
- **Unified response**: all APIs return `Resp[T]` or `PagedResp[T]`

## Frontend

### Setup & Commands

```bash
cd frontend
make install   # npm install
make dev       # Vite dev server (proxies /api to localhost:8000)
make build     # Production build
```

### Key Details

- UI library: Ant Design Vue 4.x — prefer its built-in components/layouts over custom styles
- State management: Pinia
- Path alias: `@` → `src/`
- API proxy: Vite proxies `/api` requests to `http://127.0.0.1:8000`
