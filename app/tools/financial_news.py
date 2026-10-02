"""Tool definitions and execution for news, source reading, and cross-checking."""

from difflib import SequenceMatcher

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
    def __init__(self) -> None:
        self.stories: list[dict[str, str]] = []

    @property
    def definitions(self) -> list[dict]:
        return [
            {"type": "function", "function": {"name": "get_daily_financial_news", "description": "Fetch today's financial news from configured public RSS feeds. Call this when the user asks what is happening today or needs current news.", "parameters": {"type": "object", "properties": {}, "required": []}}},
            {"type": "function", "function": {"name": "read_story_source", "description": "Retrieve readable text from one story's original source page when more detail is needed. Call get_daily_financial_news first. This makes a single on-demand request.", "parameters": {"type": "object", "properties": {"story_id": {"type": "string", "description": "ID returned by get_daily_financial_news"}}, "required": ["story_id"]}}},
            {"type": "function", "function": {"name": "check_other_sources", "description": "Look for today's independent RSS coverage of a story to check whether another configured publisher also reports it.", "parameters": {"type": "object", "properties": {"story_id": {"type": "string", "description": "ID returned by get_daily_financial_news"}}, "required": ["story_id"]}}},
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
            self.stories = fetch_daily_news()
            if not self.stories:
                return "No stories dated today were found in the configured RSS feeds. Be transparent; do not invent current news."
            return "Stories dated today (local timezone):\n" + "\n".join(
                f"[{s['id']}] {s['title']} — {s['source']} ({s['published_at']})\n"
                f"RSS description: {s['summary'][:600]}\nSource URL: {s['url']}"
                for s in self.stories
            )

        story = next((item for item in self.stories if item["id"] == str(arguments.get("story_id", ""))), None)
        if not story:
            return "That story ID is not in the current news list. Fetch today's news first."

        if name == "read_story_source":
            try:
                return f"Article page from {story['source']} ({story['url']}):\n{retrieve_article(story['url'])}"
            except (ValueError, OSError) as exc:
                return f"Could not retrieve the source page. RSS information is still available. Detail: {exc}"

        if name == "check_other_sources":
            own_feed = story["feed_url"]
            other_feeds = {feed for feed in settings.news_feeds if feed != own_feed}
            matches = find_matching_stories(other_feeds)
            title = story["title"].casefold()
            matches = [
                match for match in matches
                if match["url"] != story["url"]
                and SequenceMatcher(None, title, match["title"].casefold()).ratio() >= 0.48
            ]
            if not matches:
                return "No similar story was found in the other configured feeds today. This is not proof the story is false; only one configured publisher has been checked."
            return "Possible independent coverage (headline similarity only; compare details before treating claims as confirmed):\n" + "\n".join(
                f"{match['source']}: {match['title']} — {match['url']}" for match in matches[:5]
            )
        return f"Unknown tool: {name}"
