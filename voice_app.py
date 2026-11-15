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
        font-family: 'Outfit', 'Noto Sans Devanagari', sans-serif !important;
        letter-spacing: -0.015em;
    }

    @keyframes fadeSlideUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    @keyframes breatheDot {
        0%, 100% { transform: scale(1); opacity: 0.95; }
        50% { transform: scale(1.25); opacity: 0.55; }
    }

    .studio-hero {
        position: relative;
        overflow: hidden;
        padding: 26px 30px;
        border-radius: 24px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: linear-gradient(135deg, rgba(19, 30, 56, 0.85) 0%, rgba(12, 19, 38, 0.9) 60%, rgba(18, 37, 58, 0.82) 100%);
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(24px);
        margin-bottom: 20px;
        animation: fadeSlideUp 0.45s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .hero-flex {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 16px;
    }

    .hero-tag {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        font-weight: 600;
        color: #7dd3fc;
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.25);
        padding: 5px 13px;
        border-radius: 999px;
        margin-bottom: 10px;
    }

    .hero-title {
        font-family: 'Outfit', sans-serif;
        font-size: 34px;
        font-weight: 700;
        color: #f8fafc;
        margin: 0 0 6px 0;
        letter-spacing: -0.02em;
    }

    .hero-desc {
        color: #94a3b8;
        font-size: 14.5px;
        max-width: 660px;
        line-height: 1.55;
    }

    .live-badge {
        display: inline-flex;
        align-items: center;
        gap: 9px;
        padding: 8px 16px;
        border-radius: 999px;
        background: rgba(16, 185, 129, 0.14);
        border: 1px solid rgba(52, 211, 153, 0.35);
        color: #6ee7b7;
        font-size: 12.5px;
        font-weight: 600;
    }

    .live-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #34d399;
        box-shadow: 0 0 10px #34d399;
        animation: breatheDot 2.4s infinite ease-in-out;
    }

    .metric-card {
        background: var(--glass-surface);
        backdrop-filter: blur(18px);
        border: 1px solid var(--border-soft);
        border-radius: 20px;
        padding: 16px 20px;
        margin-bottom: 18px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.2);
        transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), border-color 0.28s ease;
        animation: fadeSlideUp 0.5s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .metric-card:hover {
        transform: translateY(-3px);
        border-color: rgba(56, 189, 248, 0.35);
    }

    .metric-title {
        font-size: 12px;
        font-weight: 500;
        color: #94a3b8;
        margin-bottom: 6px;
    }

    .metric-val {
        font-family: 'Outfit', 'Noto Sans Devanagari', sans-serif;
        font-size: 22px;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.25;
    }

    .metric-caption {
        font-size: 11.5px;
        color: #64748b;
        margin-top: 4px;
    }

    .glass-card {
        background: var(--glass-surface);
        backdrop-filter: blur(18px);
        border: 1px solid var(--border-soft);
        border-radius: 20px;
        padding: 18px 20px;
        margin-bottom: 14px;
        box-shadow: 0 10px 28px rgba(0, 0, 0, 0.2);
        transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .glass-card:hover {
        border-color: rgba(148, 163, 184, 0.28);
    }

    .card-eyebrow {
        font-size: 11.5px;
        font-weight: 600;
        color: #7dd3fc;
        letter-spacing: 0.4px;
        margin-bottom: 6px;
    }

    .mode-strip {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 13px 18px;
        border-radius: 16px;
        background: rgba(17, 25, 44, 0.65);
        border: 1px solid rgba(56, 189, 248, 0.2);
        margin-bottom: 12px;
    }

    .status-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 14px;
        padding: 10px 14px;
        margin-bottom: 8px;
        transition: transform 0.2s ease;
    }

    .status-item:hover {
        transform: translateX(2px);
    }

    .status-name {
        font-size: 12.5px;
        font-weight: 500;
        color: #cbd5e1;
    }

    .pill-badge {
        font-size: 11.5px;
        font-weight: 600;
        padding: 4px 12px;
        border-radius: 999px;
    }

    .badge-emerald {
        background: rgba(16, 185, 129, 0.16);
        color: #6ee7b7;
        border: 1px solid rgba(52, 211, 153, 0.35);
    }

    .badge-rose {
        background: rgba(244, 63, 94, 0.16);
        color: #fda4af;
        border: 1px solid rgba(251, 113, 133, 0.38);
    }

    .badge-amber {
        background: rgba(245, 158, 11, 0.16);
        color: #fcd34d;
        border: 1px solid rgba(251, 191, 36, 0.38);
    }

    .badge-cyan {
        background: rgba(56, 189, 248, 0.15);
        color: #7dd3fc;
        border: 1px solid rgba(56, 189, 248, 0.35);
    }

    .badge-slate {
        background: rgba(51, 65, 85, 0.45);
        color: #cbd5e1;
        border: 1px solid rgba(148, 163, 184, 0.2);
    }

    .stButton > button, .stFormSubmitButton > button {
        border-radius: 14px !important;
        font-weight: 600 !important;
        font-family: 'Plus Jakarta Sans', 'Noto Sans Devanagari', sans-serif !important;
        border: 1px solid rgba(56, 189, 248, 0.28) !important;
        background: linear-gradient(135deg, rgba(14, 116, 144, 0.42), rgba(49, 46, 129, 0.52)) !important;
        color: #f8fafc !important;
        padding: 0.55rem 1.1rem !important;
        transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1) !important;
    }

    .stButton > button:hover, .stFormSubmitButton > button:hover {
        border-color: rgba(56, 189, 248, 0.7) !important;
        box-shadow: 0 8px 22px rgba(56, 189, 248, 0.22) !important;
        transform: translateY(-1.5px);
    }

    div[data-testid="stChatMessage"] {
        background: rgba(17, 26, 48, 0.78);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 20px;
        padding: 15px 20px;
        margin-bottom: 12px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
        animation: fadeSlideUp 0.35s cubic-bezier(0.22, 1, 0.36, 1);
        font-size: 15px;
        line-height: 1.65;
    }

    [data-testid="stForm"] {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 20px;
        padding: 16px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------ HELPERS -----------------------------
def get_status_badge_class(value: str) -> str:
    """Return semantic CSS badge class based on status text."""
    val = (value or "").lower()
    if any(k in val for k in ("over-limit", "not authorised", "not authorized")):
        return "badge-rose"
    if any(k in val for k in ("waiver stated", "confirmation stated", "goals stated as met")):
        return "badge-emerald"
    if any(k in val for k in ("waiver discussed", "in progress")):
        return "badge-cyan"
    if "fee amount mentioned" in val:
        return "badge-amber"
    return "badge-slate"


def enforce_fee_limit(user_message: str, maximum_fee: float, ai_reply: str) -> str:
    """Safeguard for explicit currency amounts in role-play turns (English & Devanagari)."""
    pattern = (
        r"(?:\$|₹|rs\.?|inr)\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|rupees?|inr|रुपये|डॉलर)\b"
    )
    matches = re.findall(pattern, user_message, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]
    text = user_message.lower()
    fee_context = any(
        word in text
        for word in (
            "fee", "charge", "payment", "pay", "termination", "cancellation",
            "फीस", "चार्ज", "पेमेंट", "भुगतान", "पेनल्टी", "शुल्क",
        )
    )
    if fee_context and any(amount > float(maximum_fee) for amount in amounts):
        agreement_words = ("i agree", "i will pay", "go ahead and charge", "मैं तैयार हूँ", "चार्ज कर लीजिए")
        if any(w in ai_reply.lower() for w in agreement_words):
            if contains_devanagari(ai_reply) or contains_devanagari(user_message):
                return (
                    f"मुझे ${float(maximum_fee):.2f} से अधिक किसी भी शुल्क को मंज़ूर करने की अनुमति नहीं है। "
                    "कृपया देखें कि क्या यह चार्ज वेव किया जा सकता है या कोई बिना शुल्क वाला विकल्प उपलब्ध है।"
                )
            return (
                f"I cannot authorize a fee above ${float(maximum_fee):.2f}. "
                "Please check whether the fee can be waived or whether a no-fee "
                "alternative is available."
            )
    return ai_reply


def update_negotiation_status(message: str, statuses: dict, maximum_fee: float, source: str = "conversation") -> dict:
    """Track negotiation progress signals across both English and Hindi turns."""
    text = message.lower()
    pattern = (
        r"(?:\$|₹|rs\.?|inr)\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|rupees?|inr|रुपये|डॉलर)\b"
    )
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]
    fee_context = any(
        word in text
        for word in (
            "fee", "charge", "payment", "pay", "termination", "cancellation",
            "फीस", "चार्ज", "पेमेंट", "भुगतान", "पेनल्टी", "शुल्क",
        )
    )

    if fee_context and amounts:
        if any(amount > float(maximum_fee) for amount in amounts):
            statuses["Fee limit"] = "Over-limit amount mentioned"
            statuses["Authorisation"] = "Not authorised"
        else:
            statuses["Fee limit"] = "Fee amount mentioned"

    if any(word in text for word in ("waiver", "waived", "waive", "माफ़", "माफ", "वेव", "छूट")):
        statuses["Negotiation"] = "Waiver discussed"

    waiver_confirmations = (
        "fee has been waived",
        "fee is waived",
        "waiver has been approved",
        "waiver is approved",
        "your cancellation fee is zero",
        "there is no cancellation fee",
        "there is no early termination fee",
        "फीस माफ़ कर दी",
        "चार्ज माफ़ कर दिया",
        "कोई चार्ज नहीं लगेगा",
        "चार्ज हटा दिया",
    )
    if source == "other_party" and any(phrase in text for phrase in waiver_confirmations):
        statuses["Fee outcome"] = "Waiver stated by demo participant"

    cancellation_confirmations = (
        "cancellation is confirmed",
        "subscription has been cancelled",
        "subscription has been canceled",
        "service has been cancelled",
        "service has been canceled",
        "your service is now cancelled",
        "your service is now canceled",
        "कैंसिल कर दिया गया",
        "कैंसिलेशन कन्फर्म",
        "सेवा बंद कर दी गई",
    )
    if source == "other_party" and any(phrase in text for phrase in cancellation_confirmations):
        statuses["Cancellation"] = "Confirmation stated in demo"

    if (
        statuses.get("Fee outcome") == "Waiver stated by demo participant"
        and statuses.get("Cancellation") == "Confirmation stated in demo"
    ):
        statuses["Mission"] = "Demo goals stated as met"
    return statuses


async def run_autonomous_call(scenario_name: str, max_fee: float, voice_enabled: bool):
    """Connect to the mock call center WebSocket and run an automated negotiation."""
    uri = f"ws://localhost:8000/call-stream?scenario={scenario_name}"

    st.session_state.messages.append({
        "role": "assistant",
        "content": f"Dialing simulated call center for scenario '{scenario_name}'...",
    })

    try:
        async with websockets.connect(uri) as websocket:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                except Exception:
                    continue

                msg_type = data.get("type")
                sender = data.get("sender", "")
                text = data.get("text", "")

                if msg_type == "audio_transcript":
                    if sender == "IVR":
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"🤖 **[IVR Menu]**: {text}",
                        })
                        target_dept = MISSION_BRIEF.get("target_department", "Billing")
                        digit = ask_gemini_ivr_choice(text, target_dept)

                        st.session_state.messages.append({
                            "role": "user",
                            "content": f"🔢 **[Keypad]**: Selected option **{digit}**",
                        })
                        await websocket.send(digit)

                    elif sender == "HUMAN_AGENT":
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"🧑‍💼 **[Representative]**: {text}",
                        })

                        if voice_enabled:
                            speak_text(text)

                        ai_reply = ask_gemini_agent_response(text)

                        st.session_state.messages.append({
                            "role": "user",
                            "content": f"🎙️ **[Holdout AI]**: {ai_reply}",
                        })

                        if voice_enabled:
                            speak_text(ai_reply)

                        await websocket.send(ai_reply)

                elif msg_type == "audio_event":
                    sound_desc = data.get("sound", "Hold music playing...")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"🎵 *[Audio Event]*: {sound_desc}",
                    })

                st.rerun()

    except Exception as exc:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"Could not connect to mock server at `{uri}`. Ensure FastAPI/Uvicorn is running (`{exc}`).",
        })
        st.rerun()


def process_turn(user_text: str, maximum_fee: float, voice_enabled: bool):
    """Handle a conversation turn with native Devanagari enforcement for Hindi/Hinglish."""
    clean_text = (user_text or "").strip()
    if not clean_text:
        return

    mode = st.session_state.get("interaction_mode", "Direct conversation with me")
    relationship = st.session_state.get(
        "resolved_relationship_context",
        st.session_state.get("relationship_context", "General conversation"),
    )
    department = st.session_state.get("resolved_department", "Not specified")
    target = st.session_state.get("mission_goal", "Help me with my request")
    customer_name = st.session_state.get("customer_name", "Kumar")
    language_pref = st.session_state.get(
        "language_preference", "Auto (Match User — Hindi in देवनागरी)"
    )
    voice_profile = st.session_state.get(
        "voice_profile", "Auto (Smart Hindi देवनागरी + English)"
    )

    st.session_state.messages.append({"role": "user", "content": clean_text})

    if mode == "Negotiation role-play (I act as the representative)":
        st.session_state.negotiation_status = update_negotiation_status(
            clean_text, st.session_state.negotiation_status, maximum_fee, source="other_party"
        )

    history = "\n".join(
        f"{'USER' if item['role'] == 'user' else 'HOLDOUT AI'}: {item['content']}"
        for item in st.session_state.messages[-16:]
    )

    script_instruction = get_script_instruction(clean_text, language_pref)

    if mode == "Direct conversation with me":
        role_instructions = """
CONVERSATION MODE: DIRECT CHAT
- The person typing or speaking is the USER talking directly to you, Holdout AI.
- Talk TO the user as a smart, supportive conversation & negotiation partner.
- Do not pretend the user is a company representative or service agent.
- Help with their current request, draft scripts, or answer questions naturally.
"""
    else:
        role_instructions = f"""
CONVERSATION MODE: NEGOTIATION ROLE-PLAY
- The user is acting as the company representative in a simulated negotiation.
- You are Holdout AI, acting as the authorised negotiation agent for {customer_name}.
- Speak directly to the representative in first-person spoken dialogue.
- Never agree to any fee above ${maximum_fee:.2f}.
"""

    prompt = f"""
You are Holdout AI, a refined, natural voice-first AI assistant.

{role_instructions}

{script_instruction}

RELATIONSHIP / SOCIAL CONTEXT: {relationship}
TARGET DEPARTMENT OR CONTACT: {department}
USER'S STATED OBJECTIVE: {target}
CUSTOMER NAME: {customer_name}
MAXIMUM AUTHORISED FEE: ${maximum_fee:.2f}

CONVERSATION HISTORY:
{history}

VOICE & STYLE RULES:
- Keep responses concise (2 to 4 natural spoken sentences) so voice playback feels fluid and human.
- Never use markdown bullets, asterisks, or stage directions.
- Remember: If speaking Hindi, write 100% in native देवनागरी script (never Romanized Hinglish).
- Reply only with the exact words to be spoken aloud.
"""
    try:
        with st.spinner("Synthesizing response..."):
            reply = call_gemini(prompt)
        if not isinstance(reply, str) or not reply.strip():
            reply = "I couldn't generate a response just now. Please try again."
    except Exception as exc:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"Connection error: {type(exc).__name__}: {exc}",
        })
        return

    if mode == "Negotiation role-play (I act as the representative)":
        reply = enforce_fee_limit(clean_text, maximum_fee, reply)
        st.session_state.negotiation_status = update_negotiation_status(
            reply, st.session_state.negotiation_status, maximum_fee, source="assistant"
        )

    st.session_state.messages.append({"role": "assistant", "content": reply})

    if voice_enabled:
        try:
            speak_text(reply, voice_profile=voice_profile)
            st.session_state.last_voice_error = ""
        except Exception as exc:
            st.session_state.last_voice_error = f"{type(exc).__name__}: {exc}"


# ---------------------------- SESSION STATE -------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "negotiation_status" not in st.session_state:
    st.session_state.negotiation_status = {
        "Fee limit": "Not assessed",
        "Authorisation": "No fee approved",
        "Negotiation": "Ready",
        "Fee outcome": "Pending",
        "Cancellation": "Pending",
        "Mission": "In progress",
    }
if "mic_version" not in st.session_state:
    st.session_state.mic_version = 0
if "last_voice_error" not in st.session_state:
    st.session_state.last_voice_error = ""
if "interaction_mode" not in st.session_state:
    st.session_state.interaction_mode = "Direct conversation with me"
if "relationship_context" not in st.session_state:
    st.session_state.relationship_context = "Customer service"
if "language_preference" not in st.session_state:
    st.session_state.language_preference = "Auto (Match User — Hindi in देवनागरी)"
if "voice_profile" not in st.session_state:
    st.session_state.voice_profile = "Auto (Smart Hindi देवनागरी + English)"

# ------------------------------- SIDEBAR ----------------------------
with st.sidebar:
    st.markdown("## 🎙️ Holdout Studio")
    st.caption("Voice, Language & Negotiation Settings")

    customer_name = st.text_input(
        "Your Name", value=MISSION_BRIEF.get("customer_name", "Kumar")
    )

    interaction_mode = st.selectbox(
        "Studio Mode",
        [
            "Direct conversation with me",
            "Negotiation role-play (I act as the representative)",
        ],
        key="interaction_mode",
        help="Direct mode talks with you. Role-play mode lets you act as the company agent while Holdout AI negotiates on your behalf.",
    )

    st.divider()
    st.markdown("**🗣️ Language & Neural Voice**")

    language_preference = st.selectbox(
        "Response Language & Script",
        [
            "Auto (Match User — Hindi in देवनागरी)",
            "Hindi (Always reply in देवनागरी)",
            "English (Always reply in English)",
        ],
        key="language_preference",
        help="Prevents awkward Hinglish spelling by writing Hindi responses in native Devanagari script for neural Hindi pronunciation.",
    )

    voice_profile = st.selectbox(
        "Neural Voice Persona",
        list(VOICE_PROFILES.keys()),
        key="voice_profile",
    )

    mic_lang_choice = st.radio(
        "Microphone Recognition Language",
        ["English / Hinglish (en-IN)", "हिंदी देवनागरी (hi-IN)"],
        horizontal=True,
    )
    mic_lang_code = "hi-IN" if "hi-IN" in mic_lang_choice else "en-IN"

    voice_enabled = st.toggle("Speak AI responses aloud", value=True)

    st.divider()
    st.markdown("**🎯 Context & Guardrails**")

    relationship_context = st.selectbox(
        "Conversation Context",
        [
            "Customer service",
            "General conversation",
            "Bank / financial institution",
            "Company / business",
            "Workplace / professional contact",
            "Friend",
            "Family",
            "Other (I will describe it)",
        ],
        key="relationship_context",
    )

    custom_relationship = ""
    if relationship_context == "Other (I will describe it)":
        custom_relationship = st.text_input(
            "Describe context",
            placeholder="e.g. Landlord, ISP manager, University office",
        )

    target_department_choice = st.selectbox(
        "Target Department",
        [
            "Billing or Cancellations",
            "Retention",
            "Customer Support",
            "Technical Support",
            "None / not applicable",
            "Other (enter my own)",
        ],
    )

    custom_department = ""
    if target_department_choice == "Other (enter my own)":
        custom_department = st.text_input(
            "Custom Department",
            placeholder="e.g. Card Disputes, Accounts",
        )

    target_department = (
        custom_department.strip()
        if target_department_choice == "Other (enter my own)"
        else (
            "Not specified"
            if target_department_choice == "None / not applicable"
            else target_department_choice
        )
    )

    resolved_relationship = (
        custom_relationship.strip()
        if custom_relationship.strip()
        else relationship_context
    )

    mission_goal = st.text_area(
        "Active Objective",
        value=MISSION_BRIEF.get(
            "goal", "Cancel internet subscription and refuse early termination fees."
        ),
        height=85,
    )

    max_fee = st.number_input(
        "Maximum Authorised Fee ($)",
        min_value=0.0,
        max_value=100000.0,
        value=float(MISSION_BRIEF.get("max_acceptable_fee", 0.0)),
        step=5.0,
    )

    st.divider()
    if st.button("↻ Clear & Reset Studio", use_container_width=True):
        st.session_state.messages = []
        st.session_state.negotiation_status = {
            "Fee limit": "Not assessed",
            "Authorisation": "No fee approved",
            "Negotiation": "Ready",
            "Fee outcome": "Pending",
            "Cancellation": "Pending",
            "Mission": "In progress",
        }
        st.session_state.pop("audio_payload", None)
        st.session_state.last_voice_error = ""
        st.session_state.mic_version += 1
        st.rerun()

    with st.expander("🔌 Mock Call Center WebSocket"):
        selected_mock_scenario = st.selectbox(
            "Scenario",
            ["aegis_security", "apex_telecom", "vantis_bank", "cloudscale_saas"],
        )
        if st.button("Start Autonomous Call", use_container_width=True):
            st.session_state.messages = []
            asyncio.run(run_autonomous_call(selected_mock_scenario, max_fee, voice_enabled))

# Sync state and MISSION_BRIEF
st.session_state.customer_name = customer_name
st.session_state.target_department = target_department
st.session_state.resolved_department = target_department
st.session_state.resolved_relationship_context = resolved_relationship
st.session_state.mission_goal = mission_goal
MISSION_BRIEF["customer_name"] = customer_name
MISSION_BRIEF["target_department"] = target_department
MISSION_BRIEF["goal"] = mission_goal
MISSION_BRIEF["max_acceptable_fee"] = max_fee
MISSION_BRIEF["language_preference"] = language_preference

# -------------------------------- HEADER ----------------------------
is_roleplay = interaction_mode == "Negotiation role-play (I act as the representative)"
mode_label = "Role-Play Negotiation" if is_roleplay else "Direct Voice & Chat"
telemetry = get_last_turn_telemetry()

st.markdown(
    f"""
    <div class="studio-hero">
      <div class="hero-flex">
        <div>
          <div class="hero-tag">✨ Bilingual Neural Voice &amp; Negotiation Studio</div>
          <div class="hero-title">Holdout AI</div>
          <div class="hero-desc">
            Fluid conversational negotiation with native <strong>देवनागरी Hindi</strong> &amp; English neural speech,
            real-time fee protection, and organic audio spectrum synthesis.
          </div>
        </div>
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px;">
          <span class="live-badge"><span class="live-dot"></span>{mode_label}</span>
          <span style="font-size:12px; color:#94a3b8;">
            Voice Persona: <strong style="color:#e2e8f0;">{html.escape(VOICE_PROFILES[voice_profile]['label'])}</strong>
          </span>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------- METRIC RIBBON -------------------------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-title">Session Exchanges</div>
          <div class="metric-val">{len(st.session_state.messages)}</div>
          <div class="metric-caption">Active context memory</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m2:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-title">Fee Protection Cap</div>
          <div class="metric-val" style="color:#34d399;">${max_fee:,.2f}</div>
          <div class="metric-caption">Automatic fee guardrail</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m3:
    script_now = telemetry.get("script_detected", "Auto • देवनागरी / EN")
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-title">Active Voice Script</div>
          <div class="metric-val" style="color:#7dd3fc; font-size:20px;">{html.escape(script_now)}</div>
          <div class="metric-caption">Native pronunciation routing</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-title">Context &amp; Routing</div>
          <div class="metric-val" style="font-size:19px;">{html.escape(resolved_relationship)}</div>
          <div class="metric-caption">{html.escape(target_department)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------- MAIN WORKSPACE ------------------------
left, right = st.columns([1.68, 1], gap="large")

with left:
    if is_roleplay:
        st.markdown(
            """
            <div class="mode-strip">
              <div style="font-size:13px; color:#cbd5e1;">
                🎭 <strong>Role-Play Simulator:</strong> Speak or type as the <em>company representative</em> (in English, Hindi, or Hinglish). Holdout AI responds as the customer's negotiation agent.
              </div>
              <span class="pill-badge badge-amber">Rep Mode</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
