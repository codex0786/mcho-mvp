from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    log_level: str = "INFO"
    # Managed providers may supply DATABASE_URL. Otherwise build a safe URL from discrete fields.
    database_url: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mcho"
    postgres_user: str = "mcho"
    postgres_password: str = "local-only"
    redis_url: str = "redis://localhost:6379/0"
    reviewer_api_key: str = ""
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url and self.database_url.strip():
            return self.database_url.strip()
        username = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        database = quote(self.postgres_db, safe="")
        return (
            f"postgresql+psycopg://{username}:{password}@"
            f"{self.postgres_host}:{self.postgres_port}/{database}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
