"""Small, environment-based configuration for FinLens."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class NewsFeed:
    url: str


DEFAULT_NEWS_FEEDS = (
    "https://www.thehindubusinessline.com/markets/feeder/default.rss",
    "https://www.thehindubusinessline.com/money-and-banking/feeder/default.rss",
    "https://www.business-standard.com/rss/finance-103.rss",
    "https://www.business-standard.com/rss/economy-102.rss",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://www.business-standard.com/rss/industry/banking-21703.rss",
)


def _news_feeds() -> tuple[NewsFeed, ...]:
    configured = os.getenv("FINANCIAL_NEWS_FEEDS")
    feed_values = (configured.split(",") if configured else DEFAULT_NEWS_FEEDS)
    feeds = []
    for value in feed_values:
        value = value.strip()
        if not value:
            continue
        if "|" in value:
            region, url = value.split("|", 1)
            if region.strip().casefold() != "india":
                continue
        else:
            # URL-only overrides are treated as India-focused sources.
            url = value
        url = url.strip()
        if url:
            feeds.append(NewsFeed(url=url))
    return tuple(feeds)


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:cloud")
    ollama_api_key: str = os.getenv("OLLAMA_API_KEY", "")
    timezone: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    news_feeds: tuple[NewsFeed, ...] = _news_feeds()


settings = Settings()
