from fastapi import FastAPI

from app.api.router import api_router
from app.core.bootstrap import ensure_default_admin
from app.core.config import settings
from app.core.exception_handler import register_exception_handlers
from app.core.logger import setup_logging
from app.db.schema import Base
from app.db.session import engine

setup_logging()
app = FastAPI(title=settings.app_name)
register_exception_handlers(app)
app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_default_admin()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
