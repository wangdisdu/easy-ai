from langfuse import Langfuse
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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

    # Flowise 嵌入接入（M1）
    flowise_enabled: bool = Field(default=False)
    flowise_internal_url: str = Field(default="http://127.0.0.1:3001")
    flowise_shared_secret: str = Field(default="change-me-easyai-flowise")
    flowise_default_workspace: str = Field(default="")


settings = Settings()

langfuse = None

if settings.langfuse_enabled:
    langfuse = Langfuse(
        public_key = settings.langfuse_public_key,
        secret_key = settings.langfuse_secret_key,
        host = settings.langfuse_host,
    )
