"""Streamlit story browser using the existing FinLens daily briefing."""

import re
from datetime import date, timedelta
from html import escape
from urllib.parse import urlparse

import streamlit as st

from app.agent import generate_daily_briefing
from app.services.ollama import OllamaError


REGIONS = ("India", "United States", "Europe", "Asia-Pacific", "Global")
FIELD_LABELS = (
    ("country", r"country(?:/region|\s+or\s+region)"),
    ("happened", r"what happened"),
    ("cause", r"why is (?:it|this) happening|why is this happening"),
    ("terms", r"(?:financial\s+)?terms?(?:\s+to know)?"),
    ("example", r"(?:a\s+)?real[- ]life example|example"),
    ("impact", r"so what|why it matters(?: to (?:an? )?ordinary person)?|how it could affect(?: an ordinary person)?"),
    ("connections", r"connections?(?: to other countries or events)?"),
    ("sources", r"sources?"),
)


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


def _group_briefing(text: str) -> dict[str, list[tuple[str, str]]]:
    """Group Markdown story sections by the country/region field."""
    groups = {region: [] for region in REGIONS}
    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", text))
    if not headings and text.strip():
        groups["Global"].append(("Today's briefing", text.strip()))
        return groups

    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        story = text[heading.end() : end].strip()
        title = heading.group(1).strip()
        country = re.search(
            r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?country(?:/region|\s+or\s+region)(?:\*\*)?\s*:\s*(.+?)\s*$",
            story,
        )
        heading_region, separator, headline = title.partition(" — ")
        if not separator:
            heading_region, separator, headline = title.partition(" - ")
        location = country.group(1) if country else (heading_region if separator else "")
        groups[_region_for(location)].append(
            (headline.strip() if separator else title, story)
        )
    return groups


def _shorten(text: str, limit: int = 170) -> str:
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    if len(first_sentence) <= limit:
        return first_sentence
    return first_sentence[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _preview(story: str) -> str:
    """Return one short sentence from the story's What happened field."""
    lines = story.splitlines()
    for index, line in enumerate(lines):
        plain = re.sub(r"^\s*[-*]\s*|\*", "", line).strip()
        if plain.casefold().startswith("what happened"):
            preview = re.sub(
                r"^what happened\??(?:\s*\([^)]*\))?\s*[:—-]?\s*",
                "",
                plain,
                flags=re.I,
            )
            if preview and preview.casefold() != plain.casefold():
                return _shorten(preview)
            for next_line in lines[index + 1 :]:
                preview = re.sub(r"^\s*[-*]\s*|\*", "", next_line).strip()
                if preview:
                    return _shorten(preview)

    for line in story.splitlines():
        plain = re.sub(r"^\s*[-*]\s*|\*", "", line).strip()
        if plain and not plain.casefold().startswith(("country/region", "country or region")):
            return _shorten(plain)
    return "Open to understand the story and its context."


def _story_fields(story: str) -> dict[str, str]:
    """Read the existing labeled briefing fields for a compact story view."""
    fields: dict[str, list[str]] = {}
    current_field = None
    for line in story.splitlines():
        content = re.sub(r"^\s*[-*]\s*", "", line).strip()
        label_text = content.replace("**", "").replace("__", "")
        for field, pattern in FIELD_LABELS:
            match = re.match(
                rf"^(?:{pattern})\??(?:\s*\([^)]*\))?\s*(?::|—|-)?\s*(.*)$",
                label_text,
                flags=re.I,
            )
            if match:
                current_field = field
                value = match.group(1).strip()
                if value:
                    fields.setdefault(field, []).append(value)
                break
        else:
            if current_field and content:
                fields.setdefault(current_field, []).append(content)
    return {name: "\n".join(values).strip() for name, values in fields.items()}


def _plain_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`#]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _one_sentence(text: str, limit: int = 190) -> str:
    lines = [re.sub(r"^\s*[-*]\s*", "", line).strip() for line in text.splitlines()]
    text = _plain_text(next((line for line in lines if line), ""))
    return _shorten(text, limit) if text else ""


def _everyday_implications(text: str, example: str = "") -> list[tuple[str, str, str]]:
    lines = [re.sub(r"^\s*[-*]\s*", "", line).strip() for line in text.splitlines()]
    items = [line for line in lines if line]
    if len(items) == 1:
        items = [part.strip() for part in re.split(r"(?<=[.!?])\s+", items[0]) if part.strip()]
    if len(items) < 2 and example:
        items.append(example)

    results = []
    for item in items[:3]:
        role_match = re.match(r"([^→:]+?)\s*(?:→|->|:)\s*(.+)$", item)
        if role_match:
            role, implication = role_match.groups()
        else:
            role, implication = "Everyday life", item
        role_lower = role.casefold()
        if any(word in role_lower for word in ("job", "worker", "employee")):
            icon = "👩‍💻"
        elif any(word in role_lower for word in ("borrow", "loan", "homeowner")):
            icon = "🏦"
        elif any(word in role_lower for word in ("shop", "consumer", "price")):
            icon = "🛒"
        elif any(word in role_lower for word in ("saver", "saving", "deposit")):
            icon = "💰"
        else:
            icon = "👥"
        results.append((icon, _shorten(_plain_text(role), 36), _shorten(_plain_text(implication), 120)))
    return results


def _term_to_know(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    line = re.sub(r"^\s*[-*]\s*", "", line)
    if not line or any(word in line.casefold() for word in ("none", "no unfamiliar terms", "not needed", "n/a")):
        return None
    match = re.match(r"(?:\*\*)?([^:*—-]{1,55}?)(?:\*\*)?\s*[:—-]\s*(.+)$", line)
    if match:
        return _plain_text(match.group(1)), _one_sentence(match.group(2), 130)
    parts = _plain_text(line).split(" ", 5)
    return ("Term to know", _shorten(_plain_text(line), 130)) if len(parts) > 1 else None


def _sources(text: str) -> list[tuple[str, str]]:
    links = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)
    if links:
        return links[:3]
    urls = re.findall(r"https?://\S+", text)
    return [(urlparse(url.rstrip(".,)\u200b")).netloc or "Source", url.rstrip(".,)")] for url in urls[:3]]


def _render_open_story(story: str) -> None:
    fields = _story_fields(story)
    happened = fields.get("happened", "") or _preview(story)
    short_version = _one_sentence(happened)
    if short_version:
        st.markdown(
            '<div class="story-short-version">' + escape(short_version) + "</div>",
            unsafe_allow_html=True,
        )

    flow = []
    cause = _one_sentence(fields.get("cause", ""), 125)
    event = _one_sentence(fields.get("happened", ""), 125)
    impact = _one_sentence(fields.get("impact", ""), 125)
    if cause:
        flow.append(("WHAT'S DRIVING IT", cause))
    if event:
        flow.append(("THE CHANGE", event))
    if impact:
        flow.append(("WHAT MAY FOLLOW", impact))
    if len(flow) < 2 and fields.get("example"):
        flow.append(("PICTURE THIS", _one_sentence(fields["example"], 125)))

    if flow:
        st.markdown("**How it can ripple**")
        layout = []
        for index in range(len(flow)):
            layout.append(1)
            if index < len(flow) - 1:
                layout.append(0.12)
        columns = st.columns(layout)
        for index, (label, description) in enumerate(flow):
            with columns[index * 2]:
                with st.container(border=True):
                    st.markdown(
                        f'<div class="story-step-label">{label}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(_shorten(description, 135))
            if index < len(flow) - 1:
                with columns[index * 2 + 1]:
                    st.markdown(
                        '<div class="story-flow-arrow">→</div>',
                        unsafe_allow_html=True,
                    )

    implications = _everyday_implications(fields.get("impact", ""), fields.get("example", ""))
    if implications:
        st.markdown("**So what?**")
        cards = st.columns(len(implications), gap="small")
        for column, (icon, audience, implication) in zip(cards, implications):
            with column:
                with st.container(border=True):
                    st.markdown(f"{icon} **{audience}**")
                    st.caption(implication)

    term = _term_to_know(fields.get("terms", ""))
    if term:
        st.markdown("**A term to know**")
        with st.container(border=True):
            st.markdown(f"**{term[0]}**")
            st.caption(term[1])

    source_links = _sources(fields.get("sources", ""))
    if source_links:
        st.caption("Sources")
        st.markdown(" · ".join(f"[{name}]({url})" for name, url in source_links))


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
        .story-short-version {{ font-size: 1.16rem; line-height: 1.5; }}
        .story-flow-arrow {{ color: {muted_text}; font-size: 1.5rem; text-align: center; padding-top: 1.5rem; }}
        .story-step-label {{ color: {muted_text}; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; }}
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: {card_background}; border-color: {border_color}; border-radius: 14px;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="finlens-kicker">Everyday money, in context</div>',
    unsafe_allow_html=True,
)
st.title("FinLens")
st.markdown(
    '<p class="finlens-subtitle">'
    "Understand what's happening in the world of money."
    "</p>",
    unsafe_allow_html=True,
)
st.divider()

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

if "finlens_daily_briefing" not in st.session_state:
    try:
        with st.spinner("Preparing today's selection..."):
            st.session_state.finlens_daily_briefing = generate_daily_briefing()
            st.session_state.finlens_briefing_error = None
    except OllamaError as exc:
        st.session_state.finlens_daily_briefing = ""
        st.session_state.finlens_briefing_error = str(exc)

if st.session_state.get("finlens_briefing_error"):
    st.error(st.session_state.finlens_briefing_error)

briefing_groups = _group_briefing(st.session_state.get("finlens_daily_briefing", ""))
stories = briefing_groups[selected_region]

if not stories:
    st.info("There are no stories for this region in the currently loaded briefing.")
else:
    for title, story in stories:
        with st.container(border=True):
            st.markdown(f"### {_shorten(title, 90)}")
            st.caption(_preview(story))
            with st.expander("See what this could mean"):
                _render_open_story(story)
