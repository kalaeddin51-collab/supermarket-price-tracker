from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite:///./prices.db"

    # Must be set to a long random string in production (used to sign sessions)
    session_secret_key: str = "price-tracker-secret-key-change-in-prod"

    resend_api_key: str = ""
    email_from: str = ""
    email_to: str = ""

    ntfy_topic: str = ""

    woolworths_store_id: str = "3055"
    coles_store_id: str = "1234"
    scrape_delay_seconds: float = 3.0
    request_timeout_seconds: int = 30

    # Optional proxy for scrapers blocked by bot protection (Woolworths, Coles)
    scraper_proxy: str = ""

    # ScraperAPI key — set via env var OR saved via Settings page into DB
    scraperapi_key: str = ""


settings = Settings()

# ── Runtime key override ──────────────────────────────────────────────────────
# Because pydantic Settings objects are immutable at runtime, we store any
# DB-loaded or user-saved ScraperAPI key in a plain module-level variable.
# All scrapers call get_scraperapi_key() rather than settings.scraperapi_key.

_scraperapi_key_runtime: str = ""


def get_scraperapi_key() -> str:
    """Return ScraperAPI key: DB/runtime value takes priority over env var."""
    return _scraperapi_key_runtime or settings.scraperapi_key


def set_scraperapi_key(key: str) -> None:
    global _scraperapi_key_runtime
    _scraperapi_key_runtime = key
