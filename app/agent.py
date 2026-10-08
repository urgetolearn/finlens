"""Tool-using Ollama agent and interactive CLI."""

import json
import re

from app.prompts import SELECTED_STORY_INSTRUCTION, STORY_TIME_INSTRUCTION, SYSTEM_INSTRUCTION
from app.services.ollama import OllamaError, chat
from app.tools.financial_news import FinLensTools

MAX_TOOL_ROUNDS = 12
DAILY_BRIEFING_REQUEST = "Prepare today's financial news briefing for a beginner."
BRIEFING_FIELDS = {
    "events": {"key events", "what happened", "what happened?"},
    "why": {"why", "why?"},
    "learn": {"term to learn", "learn this"},
    "care": {"why the connection matters", "why should i care"},
    "sources": {"sources", "source"},
}
EMPTY_EXPLANATION_MARKERS = (
    "not provided",
    "not available",
    "not specified",
    "cannot be established",
    "cannot determine",
    "not enough information",
    "no useful",
    "no clear",
    "not mentioned",
    "source does not explain",
    "sources do not explain",
    "no reason is given",
    "unknown",
    "n/a",
)


def _has_unlisted_source(response: str, tools: FinLensTools) -> bool:
    """Check that a generated briefing only cites URLs from its fetched stories."""
    allowed_urls = {story["url"] for story in tools.stories}
    cited_urls = {
        url.rstrip(".,;:!?)]}")
        for url in re.findall(r"https?://[^\s<>\"]+", response)
    }
    return bool(cited_urls - allowed_urls)


def _briefing_quality_issues(response: str, tools: FinLensTools) -> list[str]:
    """Flag story cards missing useful explanations or a matching source URL."""
    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", response))
    if not headings:
        # A plain no-eligible-stories response is a valid outcome of strict selection.
        if re.search(r"(?i)no (?:stories|story|items) (?:met|qualified|were selected|were suitable)", response):
            return []
        return ["The briefing has no story sections, despite fetched stories being available."] if tools.stories else []

    allowed_urls = {story["url"] for story in tools.stories}
    issues: list[str] = []
    labels = {label: key for key, names in BRIEFING_FIELDS.items() for label in names}
    field_pattern = re.compile(r"^\s*\*\*(?P<label>[^*]+)\*\*:?[ \t]*(?P<inline>.*)$")

    for index, heading in enumerate(headings, start=1):
        end = headings[index].start() if index < len(headings) else len(response)
        block = response[heading.end() : end]
        lines = block.splitlines()
        found: dict[str, list[str]] = {}
        field_matches = []
        for line_number, line in enumerate(lines):
            match = field_pattern.match(line)
            if not match:
                continue
            label = re.sub(r"\s+", " ", match.group("label").strip().rstrip(":").casefold())
            if label in labels:
                field_matches.append((line_number, labels[label], match.group("inline").strip()))

        for position, (line_number, key, inline) in enumerate(field_matches):
            field_end = field_matches[position + 1][0] if position + 1 < len(field_matches) else len(lines)
            content = ([inline] if inline else []) + lines[line_number + 1 : field_end]
            found[key] = [part.strip() for part in content if part.strip()]

        missing = [name for name in ("events", "sources") if not found.get(name)]
        if missing:
            issues.append(f"Story {index} is missing: {', '.join(missing)}.")
            continue

        for key in ("events", "why", "learn", "care"):
            if not found.get(key):
                continue
            value = re.sub(r"[*_`]", "", " ".join(found[key])).strip()
            words = re.findall(r"\b[\w’'-]+\b", value)
            if len(words) < 5 or any(marker in value.casefold() for marker in EMPTY_EXPLANATION_MARKERS):
                issues.append(f"Story {index} has no useful, story-specific {key} explanation.")

        source_text = " ".join(found["sources"])
        urls = {
            url.rstrip(".,;:!?)]}")
            for url in re.findall(r"https?://[^\s<>\"]+", source_text)
        }
        if not urls or not (urls & allowed_urls):
            issues.append(f"Story {index} has no source URL matching the fetched news list.")

    return issues


def answer(
    question: str,
    history: list[dict],
    tools: FinLensTools,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> str:
    """Let the model decide which tools are useful, then return its response."""
    history.append({"role": "user", "content": question})
    messages = [{"role": "system", "content": system_instruction}, *history]

    for _ in range(MAX_TOOL_ROUNDS):
        reply = dict(chat(messages, tools.definitions))
        if not isinstance(reply.get("content"), str):
            reply["content"] = ""
        calls = reply.get("tool_calls", [])
        if not calls:
            reply["content"] = reply["content"].strip() or "I couldn't produce an answer just now."
            messages.append(reply)
            history[:] = messages[1:]
            return reply["content"]

        messages.append(reply)

        for call in calls:
            function = call.get("function", {})
            name = function.get("name", "")
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            result = tools.run(name, arguments)
            messages.append({"role": "tool", "tool_name": name, "content": result})

    raise OllamaError("The model requested too many tool steps. Try asking a more focused question.")


def generate_story_time(history: list[dict], tools: FinLensTools) -> str:
    """Generate a story analogy without changing the selected-story chat history."""
    story_time_history = list(history)
    return answer(
        "Create Story Time for the selected story using its source and context already "
        "in this conversation. Choose the main financial concept that benefits from "
        "an analogy. Explain that concept through one simple everyday mini-story; do "
        "not summarize the article again.",
        story_time_history,
        tools,
        system_instruction=STORY_TIME_INSTRUCTION,
    )


def generate_daily_briefing(
    history: list[dict] | None = None,
    tools: FinLensTools | None = None,
) -> str:
    """Generate the same proactive briefing used when the CLI starts."""
    conversation = history if history is not None else []
    active_tools = tools if tools is not None else FinLensTools()
    briefing = answer(
        DAILY_BRIEFING_REQUEST,
        conversation,
        active_tools,
    )
    issues = _briefing_quality_issues(briefing, active_tools)
    if _has_unlisted_source(briefing, active_tools) or issues:
        briefing = answer(
            "Revise the briefing you just produced using only the current fetched stories. "
            "Remove every story that cannot meet all of the prompt's selection criteria. "
            "Every retained story must have useful, specific Key events and at least "
            "one exact source URL from the fetched list. Include Why?, a term, or an "
            "everyday connection only when useful and supported; do not force sections. "
            "Do not fill gaps with generic text or replace removed "
            "stories with events from memory. Cause -> effect is optional. "
            + (
                "Problems to correct: " + " ".join(issues)
                if issues
                else "Remove any unlisted source URL."
            ),
            conversation,
            active_tools,
        )
        if _has_unlisted_source(briefing, active_tools) or _briefing_quality_issues(briefing, active_tools):
            return (
                "No stories met FinLens's source and explanation requirements today. "
                "I won't fill missing details with guesses or generic explanations."
            )
    return briefing


def run_cli() -> None:
    print("FinLens — understand today's financial news in plain language.")
    print("Ask about today's news or a financial term. Type 'exit' to leave.\n")
    history: list[dict] = []
    tools = FinLensTools()
    try:
        print("\nFinLens: " + generate_daily_briefing(history, tools) + "\n")
    except OllamaError as exc:
        print(f"\nFinLens: {exc}\n")
    except KeyboardInterrupt:
        print("\nGoodbye.")
        return

    print("Ask a follow-up question, or type 'exit' to leave.\n")
    while True:
        try:
            question = input("You: ").strip()
            if question.casefold() in {"exit", "quit"}:
                break
            if not question:
                continue
            print("\nFinLens: " + answer(question, history, tools) + "\n")
        except (OllamaError, KeyboardInterrupt) as exc:
            if isinstance(exc, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            print(f"\nFinLens: {exc}\n")
