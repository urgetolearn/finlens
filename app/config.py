"""Small, environment-based configuration for FinLens."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class NewsFeed:
    url: str
    region: str


DEFAULT_NEWS_FEEDS = (
    "global|https://feeds.bbci.co.uk/news/business/rss.xml",
    "global|https://www.theguardian.com/business/rss",
    "global|https://www.bloomberg.com/feeds/business/news.rss",
    "global|https://www.bloomberg.com/feeds/economics/news.rss",
    "global|https://www.bloomberg.com/feeds/markets/news.rss",
    "india|https://www.thehindubusinessline.com/markets/feeder/default.rss",
    "india|https://www.thehindubusinessline.com/money-and-banking/feeder/default.rss",
    "india|https://www.business-standard.com/rss/finance-103.rss",
    "india|https://www.business-standard.com/rss/economy-102.rss",
    "india|https://www.business-standard.com/rss/markets-106.rss",
    "india|https://www.business-standard.com/rss/industry/banking-21703.rss",
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
        else:
            # Preserve compatibility with existing URL-only .env values.
            region, url = "global", value
        region, url = region.strip().lower(), url.strip()
        if url:
            feeds.append(NewsFeed(url=url, region=region or "global"))
    return tuple(feeds)


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:cloud")
    timezone: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    news_feeds: tuple[NewsFeed, ...] = _news_feeds()


settings = Settings()
