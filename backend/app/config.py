"""Application settings, loaded from environment variables (or a local .env file).

Every value has a safe default for local development, so the app starts with no
.env at all. In production (Render), the real values come from the dashboard.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" or "production". Used to refuse an open CORS policy in production.
    environment: str = "development"

    # Comma-separated list, e.g. "https://my-app.vercel.app,http://localhost:3000".
    # Kept as a plain string because a comma list is easier to type into a hosting
    # dashboard than the JSON list pydantic-settings would otherwise expect.
    cors_origins: str = "http://localhost:3000"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "climate_hazards"
    analysis_cache_ttl_days: int = 30

    # Open-Meteo (no API key needed)
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    open_meteo_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    # Pin one dataset. Open-Meteo's default ("best_match") blends sources that change
    # over time (a ~0.3 °C step around 2017 in tests), which could fake a trend.
    open_meteo_model: str = "era5"
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 2

    # Rate limits, in slowapi's "N/period" format
    rate_limit_analysis: str = "30/minute"
    rate_limit_geocode: str = "60/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return one shared Settings instance (the env is read only once)."""
    return Settings()
