from fastapi import FastAPI

from app.api.flowise_proxy import router as flowise_proxy_router
from app.api.router import api_router
from app.core.config import settings
from app.core.exception_handler import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logger import setup_logging

setup_logging()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
register_exception_handlers(app)
app.include_router(api_router)
# Flowise 反向代理（M1 嵌入接入），挂在根路径 /flowise/* 而非 /api/v1 之下
app.include_router(flowise_proxy_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
