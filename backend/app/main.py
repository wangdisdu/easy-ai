from fastapi import FastAPI

from app.api.flowise_proxy import router as flowise_proxy_router
from app.api.open_gateway import open_gateway_router, register_open_gateway_handlers
from app.api.router import api_router
from app.core.config import settings
from app.core.exception_handler import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logger import setup_logging

setup_logging()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
register_exception_handlers(app)
# 网关异常 handler 必须在全局 handler 之后注册,FastAPI 才会优先匹配 IntegrationApiError
register_open_gateway_handlers(app)
app.include_router(api_router)
# Flowise 反向代理（M1 嵌入接入），挂在根路径 /flowise/* 而非 /api/v1 之下
app.include_router(flowise_proxy_router)
# 对外 API 网关 /open/v1/*，走标准 HTTP 语义（4xx/5xx + X-RateLimit-* headers）
app.include_router(open_gateway_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
