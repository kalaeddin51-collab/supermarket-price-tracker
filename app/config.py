from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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
    # e.g. "http://user:pass@proxy.example.com:8080" or ScraperAPI URL
    scraper_proxy: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
