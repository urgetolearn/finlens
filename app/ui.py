"""Streamlit story browser using the existing FinLens daily briefing."""

import re
from datetime import date, timedelta
from html import escape

import streamlit as st

from app.agent import generate_daily_briefing
from app.services.news import fetch_daily_news
from app.services.ollama import OllamaError
from app.tools.financial_news import FinLensTools


REGIONS = ("India", "United States", "Europe", "Asia-Pacific", "Global")


def _region_for(location: str) -> str:
    value = location.casefold()
    if "india" in value:
        return "India"
    if re.search(r"\b(united states|u\.?s\.?a?\.?|america|american)\b", value):
        return "United States"
    if any(
        term in value
        for term in ("europe", "european union", "eurozone", "germany", "france", "italy", "spain", "united kingdom", "britain", "uk")
    ):
        return "Europe"
    if any(
        term in value
        for term in ("china", "chinese", "asia-pacific", "asia pacific", "japan", "korea", "australia", "asean", "taiwan", "singapore")
    ):
        return "Asia-Pacific"
    return "Global"


def _shorten(text: str, limit: int = 170) -> str:
    text = re.sub(r"[*_`#]", "", text).strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(first_sentence) <= limit:
        return first_sentence
    return first_sentence[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _story_sections(story: str) -> dict[str, str]:
    """Extract the labeled sections from one agent-selected story."""
    label_aliases = {
        "what happened": "events", "key events": "events",
        "backstory": "backstory", "why": "why", "why is it happening": "why",
        "how it works": "cause", "cause -> effect": "cause", "cause → effect": "cause",
        "term to learn": "learn", "learn this": "learn",
        "why should i care": "care", "why the connection matters": "care",
        "why it matters": "care", "connect the dots": "connect",
        "check yourself": "check", "quick check": "check",
        "sources": "sources", "source": "sources",
    }
    label_pattern = re.compile(r"^\s*(?:[-*]\s*)?\*\*(?P<label>[^*]+)\*\*\s*:?[ \t]*(?P<inline>.*)$")
    lines = story.splitlines()
    fields: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        match = label_pattern.match(line)
        if not match:
            continue
        label = re.sub(
            r"\s+", " ", match.group("label").strip().rstrip(":?").casefold()
        )
        if label in label_aliases:
            fields.append((index, label_aliases[label], match.group("inline").strip()))

    sections: dict[str, str] = {}
    for position, (line_index, key, inline) in enumerate(fields):
        end = fields[position + 1][0] if position + 1 < len(fields) else len(lines)
        content = ([inline] if inline else []) + lines[line_index + 1 : end]
        value = "\n".join(part.strip() for part in content if part.strip())
        if value:
            sections[key] = value
    return sections


def _preview(story: str) -> str:
    event = _story_sections(story).get("events", "")
    return _shorten(event, 130) if event else "Open to understand the story and its context."


def _group_briefing(text: str) -> dict[str, list[tuple[str, str]]]:
    """Split the agent's final briefing into story blocks; no-heading text is no story."""
    groups = {region: [] for region in REGIONS}
    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", text or ""))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        story = text[heading.end() : end].strip()
        title = heading.group(1).strip()
        location_match = re.search(
            r"(?im)^\s*(?:[-*]\s*)?\*\*Country(?:/region| or region)?\*\*\s*:\s*(.+?)\s*$",
            story,
        )
        location = location_match.group(1) if location_match else title.partition(" — ")[0]
        if location == title:
            location = ""
        groups[_region_for(location)].append((title, story))
    return groups


def _cause_parts(text: str) -> dict[str, str]:
    matches = list(
        re.finditer(
            r"(?im)^\s*[-*]\s*\*\*(Reported fact|Economic explanation|Uncertainty):?\*\*:?[ \t]*",
            text,
        )
    )
    parts: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        parts[match.group(1).casefold()] = text[match.end() : end].strip()
    if not parts and text.strip():
        parts["economic explanation"] = text.strip()
    return parts


def _render_learning_card(story: str, news_story: dict[str, str]) -> None:
    sections = _story_sections(story)
    cause = _cause_parts(sections.get("cause", ""))
    happened = sections.get("events", "") or cause.get("reported fact", "")
    why = sections.get("why", "")

    if happened:
        with st.expander("WHAT HAPPENED?", expanded=False):
            st.markdown(happened)
    if why:
        with st.expander("WHY?", expanded=False):
            st.markdown(why)
    if cause.get("reported fact") or cause.get("economic explanation"):
        with st.expander("HOW IT WORKS / CAUSE → EFFECT", expanded=False):
            fact = cause.get("reported fact", "")
            explanation = cause.get("economic explanation", "")
            if fact:
                st.markdown(
                    '<div class="cause-step"><span>WHAT IS REPORTED</span><p>'
                    f"{escape(fact)}</p></div>",
                    unsafe_allow_html=True,
                )
            if fact and explanation:
                st.markdown('<div class="cause-arrow">↓</div>', unsafe_allow_html=True)
            if explanation:
                st.markdown(
                    '<div class="cause-step cause-step-inference"><span>POSSIBLE MECHANISM</span><p>'
                    f"{escape(explanation)}</p></div>",
                    unsafe_allow_html=True,
                )
            if cause.get("uncertainty"):
                st.caption(f"Still uncertain: {cause['uncertainty']}")
    if sections.get("learn"):
        with st.expander("🧠 LEARN THIS", expanded=False):
            learn_text = re.sub(r"[*_`]", "", sections["learn"])
            st.markdown(
                f'<div class="learn-card">{escape(learn_text)}</div>',
                unsafe_allow_html=True,
            )
            if sections.get("connect"):
                st.caption(f"Connect the dots: {sections['connect']}")
    if sections.get("care"):
        with st.expander("🏠 WHY SHOULD I CARE?", expanded=False):
            st.markdown(sections["care"])
    if sections.get("check"):
        with st.expander("🎯 CHECK YOURSELF", expanded=False):
            st.markdown(sections["check"])
    with st.expander("Sources", expanded=False):
        source_url = news_story.get("url", "")
        source_name = news_story.get("source", "Original source")
        if source_url:
            st.markdown(f"[{source_name}]({source_url})")
        if sections.get("sources"):
            st.markdown(sections["sources"])


def _toggle_story(story_key: str) -> None:
    """Update the expanded story before Streamlit reruns the page."""
    current_story = st.session_state.get("finlens_open_story")
    st.session_state["finlens_open_story"] = None if current_story == story_key else story_key


st.set_page_config(
    page_title="FinLens | Stories worth understanding",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

dark_mode = st.context.theme.type == "dark"
page_background = "#111827" if dark_mode else "#f5f7fb"
card_background = "#1f2937" if dark_mode else "#ffffff"
border_color = "#374151" if dark_mode else "#e5eaf1"
muted_text = "#cbd5e1" if dark_mode else "#52647a"
body_text = "#d1d5db" if dark_mode else "#5b6878"

st.markdown(
    f"""
    <style>
        .stApp {{ background: {page_background}; }}
        .block-container {{ max-width: 980px; padding-top: 3rem; padding-bottom: 4rem; }}
        .finlens-kicker {{
            color: {muted_text}; font-size: 0.82rem; font-weight: 700;
            letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 0.45rem;
        }}
        .finlens-subtitle, .finlens-note {{ color: {body_text}; }}
        .finlens-subtitle {{ font-size: 1.12rem; margin-top: -0.5rem; }}
        .finlens-note {{ line-height: 1.55; margin-bottom: 0; }}
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: {card_background}; border-color: {border_color}; border-radius: 18px;
            box-shadow: 0 5px 18px rgba(30, 48, 74, 0.07);
            transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
        }}
        div[data-testid="stExpander"] {{
            border: 1px solid {border_color}; border-radius: 13px;
            background: {card_background}; margin: 0.45rem 0;
            transition: border-color 180ms ease, box-shadow 180ms ease;
        }}
        div[data-testid="stExpander"]:hover {{
            border-color: #a9bfdc; box-shadow: 0 3px 12px rgba(30, 48, 74, 0.06);
        }}
        div[data-testid="stExpander"] summary {{ padding: 0.15rem 0.25rem; }}
        </style>
        """,
        unsafe_allow_html=True,
)
date_column, region_column = st.columns([1, 1], gap="medium")
with date_column:
    date_choice = st.selectbox("Date", ("Today", "Yesterday", "Pick a date"))
    if date_choice == "Pick a date":
        selected_date = st.date_input("Pick a date", value=date.today(), max_value=date.today())
    elif date_choice == "Yesterday":
        selected_date = date.today() - timedelta(days=1)
    else:
        selected_date = date.today()

with region_column:
    selected_region = st.selectbox("Region", REGIONS)

if selected_date != date.today():
    st.caption(
        "Historical date filtering is not connected yet; showing the currently loaded briefing."
    )

st.subheader(f"Worth understanding in {selected_region}")
st.markdown("A few stories worth understanding, explained simply.")

briefing_key = f"finlens_daily_briefing_{selected_region.casefold()}"
error_key = f"finlens_briefing_error_{selected_region.casefold()}"
news_key = f"finlens_news_stories_{selected_region.casefold()}"

if news_key not in st.session_state:
    with st.spinner("Loading today's stories..."):
        st.session_state[news_key] = fetch_daily_news(selected_region.casefold())

if briefing_key not in st.session_state:
    try:
        with st.spinner("Preparing today's selection..."):
            tools = FinLensTools(region=selected_region.casefold())
            st.session_state[briefing_key] = generate_daily_briefing(tools=tools)
            st.session_state[error_key] = None
    except OllamaError as exc:
        st.session_state[briefing_key] = ""
        st.session_state[error_key] = str(exc)

if st.session_state.get(error_key):
    st.error(st.session_state[error_key])

briefing_groups = _group_briefing(st.session_state.get(briefing_key, ""))
news_stories = st.session_state[news_key]

# A candidate is shown only when its exact source URL appears in a final agent story.
news_by_url = {item.get("url", ""): item for item in news_stories if item.get("url")}
selected_stories: list[tuple[str, str, dict[str, str]]] = []
used_urls: set[str] = set()
for region_stories in briefing_groups.values():
    for title, explanation in region_stories:
        source_text = _story_sections(explanation).get("sources", "")
        urls = {
            url.rstrip(".,;:!?)]}")
            for url in re.findall(r"https?://[^\s<>\]]+", source_text)
        }
        if len(urls) != 1:
            continue
        url = next(iter(urls))
        news_story = news_by_url.get(url)
        if news_story and url not in used_urls:
            selected_stories.append((title, explanation, news_story))
            used_urls.add(url)

if not selected_stories:
    st.info("No stories met FinLens's source and explanation requirements today.")
else:
    active_story = st.session_state.get("finlens_open_story")
    for index, (title, story, news_story) in enumerate(selected_stories, start=1):
        story_key = f"{selected_region.casefold()}-{news_story.get('id', index)}"
        is_open = active_story == story_key
        with st.container(border=True):
            st.markdown(f"### {_shorten(title, 90)}")
            st.caption(_preview(story))
            st.button(
                "Close this story ↑" if is_open else "Explore this story ↓",
                key=f"story-toggle-{story_key}",
                type="primary" if is_open else "secondary",
                on_click=_toggle_story,
                args=(story_key,),
            )
            if is_open:
                _render_learning_card(story, news_story)
