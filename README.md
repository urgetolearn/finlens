# FinLens

FinLens is a small financial literacy agent for beginners. It uses public RSS feeds to find daily stories and the `gemma4:cloud` model through Ollama Cloud to explain them, answer follow-ups, and decide when to read or cross-check sources. News retrieval and tool execution remain in the local Python app. It is educational and does not make investment recommendations.

## Minimal structure

```text
app/
  agent.py                 # Tool-using conversation loop and CLI
  config.py                # Environment-based settings
  prompts.py               # Agent behavior and safety instructions
  services/
    news.py                # RSS discovery and on-demand source reading
    ollama.py              # Swappable Ollama API adapter
  tools/
    financial_news.py      # Tools exposed to the agent
```

## Run with Ollama Cloud

1. Install [Ollama](https://ollama.com/download), start its local service, and sign in to Ollama Cloud if needed:

   ```powershell
   ollama signin
   ```

   FinLens sends requests to the local Ollama API at `http://localhost:11434`; Ollama routes `gemma4:cloud` to cloud inference. No local model download is needed.

2. Activate the repository virtual environment and install the small app dependencies:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

3. Optionally copy `.env.example` to `.env` and change the model, Ollama URL, timezone, or RSS feed list. The defaults are `OLLAMA_MODEL=gemma4:cloud` and `OLLAMA_BASE_URL=http://localhost:11434`.
4. Start the CLI:

   ```powershell
   python -m app
   ```

Ask a question such as `What are the important financial stories today?` and then ask follow-ups. Type `exit` to quit.

## Notes

- The app reads configured RSS feeds and keeps their publisher and source URLs with each story. Stories without a usable publication date are omitted from the daily list.
- Article pages are requested only when the agent chooses the source-reading tool, with a timeout and a 1 MB download cap. Some publishers block automated requests; the agent can still use the RSS description and should say when article text was unavailable.
- Cross-checking compares headline similarity across the other configured feeds. It is a discovery aid, not proof that a claim is true.
- Keep `.env` private; do not put credentials or secrets in source control. The default setup needs no API key.
- Ollama Cloud requests use account usage. `gemma4:cloud` has published per-token rates, so this setup does not guarantee ₹0 inference; check [Ollama pricing](https://ollama.com/pricing) and your account's included credits before use.
- Google ADK is not required for this minimal prototype. The agent/tool boundary and model adapter are separated so another model adapter can be added later without coupling news retrieval to the model.
