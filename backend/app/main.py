from fastapi import FastAPI

from app.api.flowise_proxy import router as flowise_proxy_router
from app.api.router import api_router
from app.core.bootstrap import ensure_default_admin
from app.core.config import settings
from app.core.exception_handler import register_exception_handlers
from app.core.logger import setup_logging
from app.db.schema import Base
from app.db.session import engine
from sqlalchemy import inspect, text

setup_logging()
app = FastAPI(title=settings.app_name)
register_exception_handlers(app)
app.include_router(api_router)
# Flowise 反向代理（M1 嵌入接入），挂在根路径 /flowise/* 而非 /api/v1 之下
app.include_router(flowise_proxy_router)


def _ensure_tb_app_columns() -> None:
    # create_all 不会 ALTER 已有表;手动补 agent_flow 联动需要的列
    inspector = inspect(engine)
    if "tb_app" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("tb_app")}
    if "flowise_chatflow_id" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tb_app ADD COLUMN flowise_chatflow_id VARCHAR(64)"))


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_tb_app_columns()
    ensure_default_admin()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
