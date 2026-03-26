from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "easy-ai-backend"
    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = Field(default="sqlite:///./easy_ai.db")
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    snowflake_worker_id: int = 1


settings = Settings()
