"""Small, environment-based configuration for FinLens."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:cloud")
    timezone: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    news_feeds: tuple[str, ...] = tuple(
        feed.strip()
        for feed in os.getenv(
            "FINANCIAL_NEWS_FEEDS",
            "https://feeds.bbci.co.uk/news/business/rss.xml,https://www.theguardian.com/business/rss",
        ).split(",")
        if feed.strip()
    )


settings = Settings()
