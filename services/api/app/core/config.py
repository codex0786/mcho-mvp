from urllib.parse import quote

from pydantic import AliasChoices, Field
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
    # Redis only carries Celery ingestion tasks. Deployments without a worker (the
    # free tier) set this false: readiness then reports Redis as "disabled".
    redis_required: bool = True
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_role_claim: str = "roles"
    oidc_algorithms: str = "RS256"
    reliefweb_appname: str = ""
    reliefweb_countries: str = ""
    reliefweb_initial_lookback_days: int = 7
    reliefweb_max_pages: int = 3
    reliefweb_page_size: int = 100
    reliefweb_overlap_hours: int = 24
    # Active ingestion runs older than this are treated as abandoned (worker crash).
    ingestion_stale_run_minutes: int = 60
    cors_origins: str = "http://localhost:3000"
    # NASA FIRMS satellite heat detections (docs/satellite-thermal.md). The key is a
    # free FIRMS MAP_KEY; without it the thermal endpoints report "not configured".
    nasa_firms_api_key: str = Field(default="", validation_alias=AliasChoices("NASA_FIRMS_API_KEY", "FIRMS_MAP_KEY"))
    firms_products: str = "VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT"
    # west,south,east,north; detections are kept only inside the MENA country borders.
    firms_area: str = "-18,8,64,40"
    firms_refresh_minutes: int = 45
    firms_retention_days: int = 21
    # Self-ping so the free Render instance does not sleep (app/core/keep_warm.py).
    # Render sets RENDER_EXTERNAL_URL itself; empty elsewhere, so local runs and tests never ping.
    keep_warm_url: str = Field(default="", validation_alias=AliasChoices("KEEP_WARM_URL", "RENDER_EXTERNAL_URL"))
    keep_warm_minutes: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url and self.database_url.strip():
            supplied = self.database_url.strip()
            # Managed PostgreSQL URLs often omit SQLAlchemy's explicit psycopg v3 driver.
            if supplied.startswith("postgres://"):
                return "postgresql+psycopg://" + supplied[len("postgres://"):]
            if supplied.startswith("postgresql://"):
                return "postgresql+psycopg://" + supplied[len("postgresql://"):]
            return supplied
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
