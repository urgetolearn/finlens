"""Public RSS discovery and on-demand source retrieval."""

from datetime import date, datetime, timezone
from html.parser import HTMLParser
from calendar import timegm
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import feedparser
import requests

from app.config import settings

MAX_STORIES = 12
MAX_SOURCE_CHARS = 7_000
MAX_DOWNLOAD_BYTES = 1_000_000


def _local_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _today() -> date:
    return datetime.now(_local_timezone()).date()


def _published_today(entry: dict, today: date) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    published = datetime.fromtimestamp(timegm(parsed), tz=timezone.utc).astimezone(_local_timezone())
    return published.isoformat() if published.date() == today else None


def fetch_daily_news() -> list[dict[str, str]]:
    """Return up to twelve stories dated today in the configured local timezone."""
    stories: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    today = _today()

    for feed_url in settings.news_feeds:
        try:
            response = requests.get(
                feed_url,
                headers={"User-Agent": "FinLens/0.1 (beginner financial literacy prototype)"},
                timeout=12,
            )
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except requests.RequestException:
            continue

        source_name = feed.feed.get("title", urlparse(feed_url).netloc)
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url or url in seen_urls:
                continue
            published_at = _published_today(entry, today)
            if not published_at:
                continue
            seen_urls.add(url)
            stories.append(
                {
                    "id": str(len(stories) + 1),
                    "title": entry.get("title", "Untitled story"),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "source": source_name,
                    "url": url,
                    "published_at": published_at,
                    "feed_url": feed_url,
                }
            )

    stories.sort(key=lambda item: item["published_at"], reverse=True)
    return [{**story, "id": str(index)} for index, story in enumerate(stories[:MAX_STORIES], 1)]


class _ReadableText(HTMLParser):
    """Extract visible text without scripts, styles, or embedded page assets."""

    blocked = {"script", "style", "noscript", "svg", "header", "footer", "nav"}
    breaks = {"p", "br", "div", "article", "section", "h1", "h2", "h3", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.blocked:
            self.blocked_depth += 1
        elif not self.blocked_depth and tag in self.breaks:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.blocked and self.blocked_depth:
            self.blocked_depth -= 1
        elif not self.blocked_depth and tag in self.breaks:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def retrieve_article(url: str) -> str:
    """Fetch one requested story page, with a timeout and strict download cap."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("The story does not have a valid HTTP source URL.")

    with requests.get(
        url,
        headers={"User-Agent": "FinLens/0.1 (on-demand reader; contact: project maintainers)"},
        timeout=12,
        stream=True,
    ) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=16_384):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                break
            chunks.append(chunk)
        raw_html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    parser = _ReadableText()
    parser.feed(raw_html)
    text = " ".join(" ".join(parser.parts).split())
    return text[:MAX_SOURCE_CHARS] or "No readable article text was available from this source."


def find_matching_stories(feed_urls: set[str]) -> list[dict[str, str]]:
    """Return RSS items for existing stories from a different configured feed."""
    results: list[dict[str, str]] = []
    today = _today()
    for feed_url in feed_urls:
        try:
            response = requests.get(feed_url, timeout=12, headers={"User-Agent": "FinLens/0.1"})
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except requests.RequestException:
            continue
        for entry in feed.entries:
            if not _published_today(entry, today):
                continue
            results.append({"title": entry.get("title", ""), "url": entry.get("link", ""), "source": feed.feed.get("title", urlparse(feed_url).netloc)})
    return results
