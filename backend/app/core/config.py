from pathlib import Path

from langfuse import Langfuse
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py 位于 backend/app/core/config.py，向上三级回到 backend/。
# 用绝对路径锁死 .env 位置，避免 cwd 不同（CLI / PyCharm / pytest）找不到文件。
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")

    app_name: str = "easy-ai-backend"
    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@127.0.0.1:18032/easyai"
    )
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    snowflake_worker_id: int = 1
    litellm_gateway_url: str = Field(default="http://127.0.0.1:4000/v1")
    litellm_gateway_key: str | None = Field(default=None)

    # Langfuse 观测配置
    langfuse_enabled: bool = Field(default=False)
    langfuse_host: str = Field(default="http://localhost:3000")
    langfuse_public_key: str | None = Field(default=None)
    langfuse_secret_key: str | None = Field(default=None)

    # Checkpoint purge 后台任务
    purge_enabled: bool = Field(default=True)
    purge_interval_seconds: int = Field(default=86400)  # 24h
    purge_ttl_days: int = Field(default=30)

    # 单次 MCP tool 调用最长等待秒数；超过强制切断，避免一个慢工具卡住整轮 agent。
    mcp_tool_timeout_seconds: float = Field(default=300.0)

    # HITL 等待上限（秒）：工具未单独配置 hitl_timeout_seconds 时使用；超时后续跑 reject
    hitl_timeout_seconds: int = Field(default=300)
    # HITL 超时扫描频率
    hitl_timeout_check_interval_seconds: int = Field(default=30)

    # Flowise 嵌入接入（M1）
    flowise_enabled: bool = Field(default=False)
    flowise_internal_url: str = Field(default="http://127.0.0.1:3001")
    flowise_shared_secret: str = Field(default="change-me-easyai-flowise")
    flowise_default_workspace: str = Field(default="")

    # RAGFlow 知识库引擎（fork + trusted-header，详见 docs/knowledge-rag-integration-design.md §3）
    ragflow_enabled: bool = Field(default=False)
    ragflow_base_url: str = Field(default="http://127.0.0.1:9380")
    ragflow_shared_secret: str = Field(default="change-me-easyai-ragflow")
    ragflow_timeout_sec: float = Field(default=30.0)
    # 后台 poller: 扫 pending/parsing 文档与 RAGFlow 对账的间隔(秒)
    kb_status_poll_interval_seconds: int = Field(default=30)


settings = Settings()

langfuse = None

if settings.langfuse_enabled:
    langfuse = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
