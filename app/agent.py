"""Tool-using Ollama agent and interactive CLI."""

import json

from app.prompts import SYSTEM_INSTRUCTION
from app.services.ollama import OllamaError, chat
from app.tools.financial_news import FinLensTools

MAX_TOOL_ROUNDS = 12
DAILY_BRIEFING_REQUEST = "Prepare today's financial news briefing for a beginner."


def answer(question: str, history: list[dict], tools: FinLensTools) -> str:
    """Let the model decide which tools are useful, then return its response."""
    history.append({"role": "user", "content": question})
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}, *history]

    for _ in range(MAX_TOOL_ROUNDS):
        reply = chat(messages, tools.definitions)
        messages.append(reply)
        calls = reply.get("tool_calls", [])
        if not calls:
            history[:] = messages[1:]
            return reply.get("content", "I couldn't produce an answer just now.")

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


def generate_daily_briefing(
    history: list[dict] | None = None,
    tools: FinLensTools | None = None,
) -> str:
    """Generate the same proactive briefing used when the CLI starts."""
    return answer(
        DAILY_BRIEFING_REQUEST,
        history if history is not None else [],
        tools if tools is not None else FinLensTools(),
    )


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
