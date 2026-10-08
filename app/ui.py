"""India-focused news browser with a story-specific explainer chat."""

import re
from html import unescape

import streamlit as st

from app.agent import answer
from app.prompts import SELECTED_STORY_INSTRUCTION
from app.services.news import fetch_daily_news
from app.services.ollama import OllamaError
from app.tools.financial_news import FinLensTools


def _shorten(text: str, limit: int = 170) -> str:
    text = unescape(re.sub(r"<[^>]*>", " ", text))
    text = re.sub(r"[*_`#]", "", text).strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    if len(first_sentence) <= limit:
        return first_sentence
    return first_sentence[: limit - 4].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def _select_story(story_url: str) -> None:
    st.session_state["finlens_selected_story_url"] = story_url


def _back_to_stories() -> None:
    st.session_state["finlens_selected_story_url"] = None


st.set_page_config(
    page_title="FinLens India | Financial news, explained",
    page_icon="FL",
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
st.title("Today's Indian Financial News")
st.caption("Indian finance and economy stories, with their original sources.")

news_key = "finlens_news_stories_india"
tools_key = "finlens_news_tools_india"
if news_key not in st.session_state:
    with st.spinner("Finding today's Indian financial news..."):
        st.session_state[news_key] = fetch_daily_news()

if tools_key not in st.session_state:
    st.session_state[tools_key] = FinLensTools(stories=st.session_state[news_key])
tools = st.session_state[tools_key]
stories = tools.stories

selected_url = st.session_state.get("finlens_selected_story_url")
if not selected_url:
    if not stories:
        st.info("No India-focused financial stories were found today. Please check back later.")
    for story in stories:
        with st.container(border=True):
            st.markdown(f"### {story.get('title', 'Untitled story')}")
            st.caption(story.get("source", "Indian news source"))
            preview = _shorten(story.get("summary") or "Open this source to read the full story.", 190)
            st.write(preview)
            source_url = story.get("url", "")
            if source_url:
                st.markdown(f"[Read original source]({source_url})")
            st.button(
                "Understand this story",
                key=f"understand-{story.get('id', source_url)}",
                type="primary",
                on_click=_select_story,
                args=(source_url,),
                disabled=not source_url,
            )
else:
    selected_story = next((item for item in stories if item.get("url") == selected_url), None)
    if selected_story is None:
        st.session_state["finlens_selected_story_url"] = None
        st.error("That story is no longer in today's news list. Return to the list and choose another.")
        st.button("Back to today's stories", on_click=_back_to_stories)
        st.stop()
    st.button("Back to today's stories", on_click=_back_to_stories)
    st.title(selected_story.get("title", "Selected story"))
    st.caption(selected_story.get("source", "Indian news source"))
    if selected_story.get("url"):
        st.markdown(f"[Read original source]({selected_story['url']})")
    conversations = st.session_state.setdefault("finlens_story_conversations", {})
    story_url = selected_story["url"]
    history = conversations.setdefault(story_url, [])
    error_key = f"finlens_story_error_{selected_story.get('id', 'selected')}"

    if not history:
        initial_request = (
            "Explain the Indian financial news story I selected. Read its original source "
            "when possible, then explain only the context and financial concepts that help "
            "me understand it.\n\n"
            f"Story ID: {selected_story.get('id', '')}\n"
            f"Headline: {selected_story.get('title', '')}\n"
            f"Publisher: {selected_story.get('source', '')}\n"
            f"RSS preview: {selected_story.get('summary', '')}\n"
            f"Original source URL: {story_url}"
        )
        try:
            with st.spinner("Reading and explaining this story..."):
                answer(
                    initial_request,
                    history,
                    tools,
                    system_instruction=SELECTED_STORY_INSTRUCTION,
                )
            st.session_state.pop(error_key, None)
        except OllamaError as exc:
            history.clear()
            st.session_state[error_key] = str(exc)

    if st.session_state.get(error_key):
        st.error(st.session_state[error_key])
        if st.button("Try the explanation again", key=f"retry-{selected_story.get('id', 'selected')}"):
            st.session_state.pop(error_key, None)
            st.rerun()

    first_user_message = True
    for message in history:
        role = message.get("role")
        content = message.get("content")
        if role == "user" and first_user_message:
            # The initial story context is for the agent; don't display it as user chat.
            first_user_message = False
            continue
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        with st.chat_message(role):
            st.markdown(content)

    follow_up = None
    if history:
        follow_up = st.chat_input(
            "Ask a follow-up about this story...",
            key=f"story-chat-{selected_story.get('id', 'selected')}",
        )
    if follow_up:
        try:
            answer(
                follow_up,
                history,
                tools,
                system_instruction=SELECTED_STORY_INSTRUCTION,
            )
            st.session_state.pop(error_key, None)
        except OllamaError as exc:
            if history and history[-1].get("role") == "user":
                history.pop()
            st.session_state[error_key] = str(exc)
        st.rerun()
