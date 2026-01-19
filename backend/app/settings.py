from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    # Core
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+psycopg://openstream:openstream@localhost:5432/openstream"

    # Auth
    auth_jwt_issuer: str = "openstream"
    auth_jwt_audience: str = "openstream"
    auth_jwt_secret: str = "dev-only-change-me"
    auth_jwt_ttl_seconds: int = 3600

    # Ingestion / partitioning
    partitions_default: int = 8
    backpressure_max_stream_len: int = 200_000

    # CORS (for local UI)
    cors_allow_origins: str = "http://localhost:3000"

    # Redis keyspace
    redis_key_prefix: str = "os"


settings = Settings()

