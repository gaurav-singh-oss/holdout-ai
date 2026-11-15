import asyncio
import html
import json
import re
import streamlit as st
import websockets
from streamlit_mic_recorder import speech_to_text

from agent import (
    MISSION_BRIEF,
    ask_gemini_agent_response,
    ask_gemini_ivr_choice,
    call_gemini,
    contains_devanagari,
    get_last_turn_telemetry,
    get_script_instruction,
)
from speaker import VOICE_PROFILES, render_audio_visualizer, speak_text

# ---------------------------- PAGE SETUP ----------------------------
st.set_page_config(
    page_title="Holdout AI · Voice & Negotiation Studio",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------- FLUID STUDIO CSS -------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700&family=Outfit:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    :root {
        --bg-canvas: #070b16;
        --glass-surface: rgba(17, 25, 44, 0.72);
        --glass-elevated: rgba(24, 35, 62, 0.65);
        --border-soft: rgba(148, 163, 184, 0.14);
        --border-highlight: rgba(56, 189, 248, 0.38);
        --text-main: #f8fafc;
        --text-muted: #94a3b8;
        --accent-sky: #38bdf8;
        --accent-mint: #34d399;
        --accent-violet: #a78bfa;
        --accent-amber: #fbbf24;
        --accent-rose: #fb7185;
    }

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', 'Noto Sans Devanagari', sans-serif;
        color: var(--text-main);
    }

    .stApp {
        background:
            radial-gradient(circle at 10% 10%, rgba(56, 189, 248, 0.13) 0%, transparent 42%),
            radial-gradient(circle at 88% 14%, rgba(167, 139, 250, 0.12) 0%, transparent 40%),
            radial-gradient(circle at 50% 95%, rgba(52, 211, 153, 0.08) 0%, transparent 45%),
            linear-gradient(180deg, #060a15 0%, #091022 100%);
        background-color: var(--bg-canvas);
    }

    .block-container {
        padding-top: 1.8rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(8, 13, 27, 0.96) 0%, rgba(11, 18, 36, 0.98) 100%);
        border-right: 1px solid rgba(148, 163, 184, 0.12);
    }

    h1, h2, h3, h4 {
        font-family: 'Outfit', 'Noto Sans Devanagari
