"""Tool definitions and execution for news, source reading, and cross-checking."""

from difflib import SequenceMatcher

import requests

from app.config import settings
from app.services.news import fetch_daily_news, find_matching_stories, retrieve_article

CONCEPTS = {
    "inflation": "A general rise in prices over time. If a weekly shop used to cost $50 and later costs $52 for the same items, that is one way inflation can show up.",
    "interest rate": "The price paid to borrow money, or the reward paid for saving it. A loan with a higher rate usually costs more to repay.",
    "central bank": "A public institution that manages a country's money system and often sets a key interest rate. Its decisions can affect borrowing costs across the economy.",
    "bond": "A loan an investor makes to a government or company. The borrower usually promises interest payments and repayment later; the details vary by bond.",
    "gdp": "The value of goods and services produced in a country over a period. It is one broad measure of economic activity, not a measure of how well every person is doing.",
    "tariff": "A tax on certain imported goods. For example, a tariff on imported steel can raise the cost for businesses that use that steel.",
    "recession": "A significant slowdown in economic activity. News outlets and official groups may use different measures to decide when one has started.",
    "mortgage": "A loan used to buy a home, usually repaid over many years. The home can be used as security for the loan.",
    "exchange rate": "The price of one currency in terms of another. It affects how much travelers pay abroad and what imported goods cost.",
}


class FinLensTools:
    def __init__(self, region: str | None = None) -> None:
        self.stories: list[dict[str, str]] = []
        self.region = region
        self.related_stories: dict[str, dict[str, str]] = {}
        self.retrieved_related_urls: set[str] = set()

    @property
    def definitions(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "get_daily_financial_news", "description": "Fetch today's financial news from configured public RSS feeds. Set region to India for India-tagged feeds; other regions use global-tagged feeds. Call this when the user asks what is happening today or needs current news.", "parameters": {"type": "object", "properties": {"region": {"type": "string", "enum": ["India", "United States", "Europe", "Asia-Pacific", "Global"], "description": "Requested region; India uses India feeds, other selections use global feeds."}}, "required": []}}},
            {"type": "function", "function": {"name": "read_story_source", "description": "Retrieve readable text from one story's original source page when more detail is needed. Call get_daily_financial_news first. This makes a single on-demand request.", "parameters": {"type": "object", "properties": {"story_id": {"type": "string", "description": "ID returned by get_daily_financial_news"}}, "required": ["story_id"]}}},
            {"type": "function", "function": {"name": "check_other_sources", "description": "When the selected story's source is too thin, find possible same-event coverage in other configured RSS feeds. Returns candidate titles, summaries, URLs, and IDs. A match is not proof it is the same event; compare the reported action, entities, and timing before reading it.", "parameters": {"type": "object", "properties": {"story_id": {"type": "string", "description": "ID returned by get_daily_financial_news"}}, "required": ["story_id"]}}},
            {"type": "function", "function": {"name": "read_related_source", "description": "Retrieve article text from one candidate returned by check_other_sources, after determining its headline and summary may describe the same event. Do not use it for a separate event.", "parameters": {"type": "object", "properties": {"related_story_id": {"type": "string", "description": "Candidate ID returned by check_other_sources"}}, "required": ["related_story_id"]}}},
            {"type": "function", "function": {"name": "explain_financial_concept", "description": "Get a plain-language definition and beginner example for a common financial term when explaining a story or answering a concept question.", "parameters": {"type": "object", "properties": {"term": {"type": "string", "description": "The financial term to explain"}}, "required": ["term"]}}},
        ]

    def run(self, name: str, arguments: dict) -> str:
        if name == "explain_financial_concept":
            term = str(arguments.get("term", "")).strip()
            if not term:
                return "A term was not provided."
            definition = CONCEPTS.get(term.casefold())
            if definition:
                return f"{term}: {definition}"
            return (
                f"No built-in glossary entry for '{term}'. Explain it using general financial knowledge, "
                "keep it simple, and say when the meaning depends on context."
            )

        if name == "get_daily_financial_news":
            self.stories = fetch_daily_news(self.region or arguments.get("region"))
            self.related_stories.clear()
            self.retrieved_related_urls.clear()
            if not self.stories:
                return "No stories dated today were found in the configured RSS feeds. Be transparent; do not invent current news."
            return "Stories dated today (local timezone):\n" + "\n".join(
                f"[{s['id']}] {s['title']} — {s['source']} ({s['published_at']})\n"
                f"RSS description: {s['summary'][:600]}\nSource URL: {s['url']}"
                for s in self.stories
            )

        if name == "read_related_source":
            related_id = str(arguments.get("related_story_id", ""))
            related_story = self.related_stories.get(related_id)
            if not related_story:
                return "That related-source ID is not available. Call check_other_sources first."
            try:
                text = retrieve_article(related_story["url"])
            except (ValueError, OSError, requests.RequestException) as exc:
                return f"Could not retrieve the related source page. Detail: {exc}"
            if not text or text.startswith("No readable article text"):
                return "No readable article text was available from that related source. Do not rely on it for additional context."
            self.retrieved_related_urls.add(related_story["url"])
            return f"Retrieved article from {related_story['source']} ({related_story['url']}), candidate [{related_id}]:\n{text}"

        story = next(
            (item for item in self.stories if item["id"] == str(arguments.get("story_id", ""))),
            None,
        )
        if not story:
            return "That story ID is not in the current news list. Fetch today's news first."

        if name == "read_story_source":
            try:
                return f"Article page from {story['source']} ({story['url']}):\n{retrieve_article(story['url'])}"
            except (ValueError, OSError, requests.RequestException) as exc:
                return f"Could not retrieve the source page. RSS information is still available. Detail: {exc}"

        if name == "check_other_sources":
            own_feed = story["feed_url"]
            other_feeds = {feed.url for feed in settings.news_feeds if feed.url != own_feed}
            matches = find_matching_stories(other_feeds)
            title = story["title"].casefold()
            matches_with_scores = [
                (SequenceMatcher(None, title, match["title"].casefold()).ratio(), match)
                for match in matches
                if match["url"] != story["url"]
                and SequenceMatcher(None, title, match["title"].casefold()).ratio() >= 0.48
            ]
            matches_with_scores.sort(key=lambda scored: scored[0], reverse=True)
            matches = []
            seen_urls = {story["url"]}
            for _, match in matches_with_scores:
                if match["url"] in seen_urls:
                    continue
                seen_urls.add(match["url"])
                matches.append(match)
                if len(matches) == 5:
                    break
            if not matches:
                return "No similar story was found in the other configured feeds today. This is not proof the story is false; only one configured publisher has been checked."
            lines = []
            for index, match in enumerate(matches, start=1):
                related_id = f"R{story['id']}-{index}"
                self.related_stories[related_id] = match
                summary = match.get("summary", "").strip()
                lines.append(
                    f"[{related_id}] {match['source']}: {match['title']}\n"
                    f"RSS description: {summary[:600]}\nSource URL: {match['url']}"
                )
            return (
                "Possible same-event RSS candidates (headline similarity only; compare "
                "entities, action, and timing before treating these as the same event):\n"
                + "\n".join(lines)
            )

        return f"Unknown tool: {name}"
