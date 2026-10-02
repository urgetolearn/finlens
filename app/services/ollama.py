"""A tiny Ollama chat adapter, kept separate so the model can be swapped later."""

import requests

from app.config import settings


class OllamaError(RuntimeError):
    """Raised when the Ollama service cannot answer."""


def chat(messages: list[dict], tools: list[dict]) -> dict:
    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={"model": settings.ollama_model, "messages": messages, "tools": tools, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(
            "Could not reach Ollama. Ensure its local service is running and signed in to Ollama Cloud, "
            f"and confirm the configured model is available (current model: {settings.ollama_model}). "
            f"Details: {exc}"
        ) from exc
    try:
        return response.json()["message"]
    except (ValueError, KeyError) as exc:
        raise OllamaError("Ollama returned an unexpected response.") from exc
