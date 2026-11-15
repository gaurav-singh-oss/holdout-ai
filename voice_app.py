import html
import re
import streamlit as st
from streamlit_mic_recorder import speech_to_text

import agent
import speaker

# ---------------------------- SAFE IMPORTS ---------------------------
MISSION_BRIEF = getattr(
    agent,
    "MISSION_BRIEF",
    {
        "goal": "Cancel internet subscription and refuse early termination fees.",
        "target_department": "Billing or Cancellations",
        "customer_name": "Kumar",
        "max_acceptable_fee": 0.0,
        "language_preference": "Auto (Match User — Hindi in देवनागरी)",
    },
)
call_gemini = agent.call_gemini
render_audio_visualizer = speaker.render_audio_visualizer

DEFAULT_VOICE_PROFILES = {
    "Auto (Smart Hindi देवनागरी + English)": {
        "hi": "hi-IN-SwaraNeural",
        "en": "en-IN-NeerjaNeural",
        "label": "Swara / Neerja Neural",
    },
    "Swara — Hindi & Bilingual (Female)": {
        "hi": "hi-IN-SwaraNeural",
        "en": "hi-IN-SwaraNeural",
        "label": "hi-IN-SwaraNeural",
    },
    "Madhur — Hindi & Bilingual (Male)": {
        "hi": "hi-IN-MadhurNeural",
        "en": "hi-IN-MadhurNeural",
        "label": "hi-IN-MadhurNeural",
    },
    "Neerja — Indian English (Female)": {
        "hi": "hi-IN-SwaraNeural",
        "en": "en-IN-NeerjaNeural",
        "label": "en-IN-NeerjaNeural",
    },
    "Prabhat — Indian English (Male)": {
        "hi": "hi-IN-MadhurNeural",
        "en": "en-IN-PrabhatNeural",
        "label": "en-IN-PrabhatNeural",
    },
    "Aria — Global Studio English (Female)": {
        "hi": "hi-IN-SwaraNeural",
        "en": "en-US-AriaNeural",
        "label": "en-US-AriaNeural",
    },
}
VOICE_PROFILES = getattr(speaker, "VOICE_PROFILES", DEFAULT_VOICE_PROFILES)


def safe_speak(text: str, voice_profile: str) -> None:
    """Call speak_text safely whether speaker.py accepts 1 or 2 arguments."""
    try:
        speaker.speak_text(text, voice_profile=voice_profile)
    except TypeError:
        speaker.speak_text(text)


def contains_devanagari(text: str) -> bool:
    """Return True if text contains Devanagari characters."""
    if hasattr(agent, "contains_devanagari"):
        return agent.contains_devanagari(text)
    return bool(re.search(r"[\u0900-\u097F]", text or ""))


def get_telemetry() -> dict:
    """Fetch latest turn telemetry safely."""
    if hasattr(agent, "get_last_turn_telemetry"):
        return agent.get_last_turn_telemetry()
    return {
        "tactic_used": "Standby",
        "rep_stance": "Neutral",
        "detected_fee": None,
        "script_detected": "Auto • देवनागरी / EN",
        "model_used": "gemini-2.5-flash",
        "latency_ms": 0,
    }


def build_script_instruction(user_text: str, language_pref: str) -> str:
    """Enforce native Devanagari script for Hindi and Romanized Hinglish inputs."""
    if hasattr(agent, "get_script_instruction"):
        return agent.get_script_instruction(user_text, language_pref)
    return (
        "CRITICAL HINDI / VOICE SCRIPT RULE:\n"
        "- Whenever speaking Hindi (or replying to Romanized Hinglish), write 100% in native "
        "DEVANAGARI script (देवनागरी).\n"
        "- NEVER write Hindi in Roman/Latin letters so the TTS engine pronounces Hindi naturally."
    )


# ---------------------------- PAGE SETUP -----------------------------
st.set_page_config(
    page_title="Holdout AI · Voice & Negotiation Studio",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

STUDIO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600;700&family=Outfit:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

:root {
    --bg-canvas: #070b16;
    --glass-surface: rgba(17, 25, 44, 0.72);
    --border-soft: rgba(148, 163, 184, 0.14);
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
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

.empty-studio-card {
    text-align: center;
    padding: 28px 24px;
    margin-top: 14px;
    border-radius: 20px;
    background: rgba(15, 23, 42, 0.45);
    border: 1px dashed rgba(148, 163, 184, 0.22);
    color: #94a3b8;
    font-size: 14px;
    line-height: 1.6;
    animation: fadeSlideUp 0.4s cubic-bezier(0.22, 1, 0.36, 1);
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
"""
st.markdown(STUDIO_CSS, unsafe_allow_html=True)


# ------------------------------ HELPERS -----------------------------
def get_status_badge_class(value: str) -> str:
    """Return semantic CSS badge class based on status text."""
    val = (value or "").lower()
    if any(k in val for k in ("over-limit", "not authorised", "not authorized")):
        return "badge-rose"
    if any(k in val for k in ("waiver stated", "confirmation stated", "goals stated as met")):
        return "badge-emerald"
    if any(k in val for k in ("waiver discussed", "in progress", "ready")):
        return "badge-cyan"
    if "fee amount mentioned" in val:
        return "badge-amber"
    return "badge-slate"


def enforce_fee_limit(user_message: str, maximum_fee: float, ai_reply: str) -> str:
    """Safeguard for explicit currency amounts in role-play turns."""
    pattern = (
        r"(?:\$|₹|rs\.?|inr)\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|rupees?|inr|रुपये|डॉलर)\b"
    )
    matches = re.findall(pattern, user_message, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]
    text = user_message.lower()
    fee_words = (
        "fee", "charge", "payment", "pay", "termination", "cancellation",
        "फीस", "चार्ज", "पेमेंट", "भुगतान", "पेनल्टी", "शुल्क",
    )
    fee_context = any(word in text for word in fee_words)
    if fee_context and any(amount > float(maximum_fee) for amount in amounts):
        agreement_words = (
            "i agree", "i will pay", "go ahead and charge", "मैं तैयार हूँ", "चार्ज कर लीजिए"
        )
        if any(w in ai_reply.lower() for w in agreement_words):
            if contains_devanagari(ai_reply) or contains_devanagari(user_message):
                return (
                    f"मुझे ${float(maximum_fee):.2f} से अधिक किसी भी शुल्क को मंज़ूर करने की अनुमति नहीं है। "
                    "कृपया देखें कि क्या यह चार्ज माफ़ किया जा सकता है या कोई बिना शुल्क वाला विकल्प उपलब्ध है।"
                )
            return (
                f"I cannot authorize a fee above ${float(maximum_fee):.2f}. "
                "Please check whether the fee can be waived or whether a no-fee alternative is available."
            )
    return ai_reply


def update_negotiation_status(
    message: str, statuses: dict, maximum_fee: float, source: str = "conversation"
) -> dict:
    """Track negotiation progress signals across both English and Hindi turns."""
    text = message.lower()
    pattern = (
        r"(?:\$|₹|rs\.?|inr)\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|rupees?|inr|रुपये|डॉलर)\b"
    )
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]
    fee_words = (
        "fee", "charge", "payment", "pay", "termination", "cancellation",
        "फीस", "चार्ज", "पेमेंट", "भुगतान", "पेनल्टी", "शुल्क",
    )
    fee_context = any(word in text for word in fee_words)

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


def process_turn(user_text: str, maximum_fee: float, voice_enabled: bool) -> None:
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

    is_roleplay_mode = mode == "Negotiation role-play (I act as the representative)"
    if is_roleplay_mode:
        st.session_state.negotiation_status = update_negotiation_status(
            clean_text, st.session_state.negotiation_status, maximum_fee, source="other_party"
        )

    history = "\n".join(
        f"{'USER' if item['role'] == 'user' else 'HOLDOUT AI'}: {item['content']}"
        for item in st.session_state.messages[-16:]
    )

    script_instruction = build_script_instruction(clean_text, language_pref)

    if is_roleplay_mode:
        role_instructions = (
            "CONVERSATION MODE: NEGOTIATION ROLE-PLAY\n"
            "- The user is acting as the company representative in a simulated negotiation.\n"
            f"- You are Holdout AI, acting as the authorised negotiation agent for {customer_name}.\n"
            "- Speak directly to the representative in first-person spoken dialogue.\n"
            f"- Never agree to any fee above ${maximum_fee:.2f}."
        )
    else:
        role_instructions = (
            "CONVERSATION MODE: DIRECT CHAT\n"
            "- The person typing or speaking is the USER talking directly to you, Holdout AI.\n"
            "- Talk TO the user as a smart, supportive conversation and negotiation partner.\n"
            "- Do not pretend the user is a company representative or service agent.\n"
            "- Help with their current request, draft scripts, or answer questions naturally."
        )

    prompt = (
        "You are Holdout AI, a refined, natural voice-first AI assistant.\n\n"
        f"{role_instructions}\n\n"
        f"{script_instruction}\n\n"
        f"RELATIONSHIP / SOCIAL CONTEXT: {relationship}\n"
        f"TARGET DEPARTMENT OR CONTACT: {department}\n"
        f"USER'S STATED OBJECTIVE: {target}\n"
        f"CUSTOMER NAME: {customer_name}\n"
        f"MAXIMUM AUTHORISED FEE: ${maximum_fee:.2f}\n\n"
        f"CONVERSATION HISTORY:\n{history}\n\n"
        "VOICE & STYLE RULES:\n"
        "- Keep responses concise (2 to 4 natural spoken sentences) so voice playback feels fluid and human.\n"
        "- Never use markdown bullets, asterisks, or stage directions.\n"
        "- Remember: If speaking Hindi, write 100% in native देवनागरी script (never Romanized Hinglish).\n"
        "- Reply only with the exact words to be spoken aloud."
    )

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

    if is_roleplay_mode:
        reply = enforce_fee_limit(clean_text, maximum_fee, reply)
        st.session_state.negotiation_status = update_negotiation_status(
            reply, st.session_state.negotiation_status, maximum_fee, source="assistant"
        )

    st.session_state.messages.append({"role": "assistant", "content": reply})

    if voice_enabled:
        try:
            safe_speak(reply, voice_profile)
            st.session_state.last_voice_error = ""
        except Exception as exc:
            st.session_state.last_voice_error = f"{type(exc).__name__}: {exc}"


def render_mode_banner(is_roleplay: bool) -> None:
    """Render the active mode banner."""
    if is_roleplay:
        banner_html = (
            '<div class="mode-strip">'
            '<div style="font-size:13px; color:#cbd5e1;">'
            "🎭 <strong>Role-Play Mode:</strong> Speak or type as the <em>other party</em> "
            "(in English, हिंदी, or Hinglish). Holdout AI responds as your negotiation agent."
            "</div>"
            '<span class="pill-badge badge-amber">Role-Play</span>'
            "</div>"
        )
    else:
        banner_html = (
            '<div class="mode-strip">'
            '<div style="font-size:13px; color:#cbd5e1;">'
            "💬 <strong>Direct Studio:</strong> Speak or type in English, हिंदी, or Hinglish. "
            "Hindi replies are automatically crafted in <strong>देवनागरी</strong> for natural voice flow."
            "</div>"
            '<span class="pill-badge badge-cyan">Direct Chat</span>'
            "</div>"
        )
    st.markdown(banner_html, unsafe_allow_html=True)


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

    if target_department_choice == "Other (enter my own)":
        target_department = custom_department.strip() or "Custom Department"
    elif target_department_choice == "None / not applicable":
        target_department = "Not specified"
    else:
        target_department = target_department_choice

    resolved_relationship = (
        custom_relationship.strip() if custom_relationship.strip() else relationship_context
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
telemetry = get_telemetry()
persona_label = VOICE_PROFILES.get(voice_profile, {}).get("label", "Neural Voice")

hero_html = (
    '<div class="studio-hero">'
    '<div class="hero-flex">'
    "<div>"
    '<div class="hero-tag">✨ Bilingual Neural Voice &amp; Negotiation Studio</div>'
    '<div class="hero-title">Holdout AI</div>'
    '<div class="hero-desc">'
    "Fluid conversational negotiation with native <strong>देवनागरी Hindi</strong> &amp; English neural speech, "
    "real-time fee protection, and organic audio spectrum synthesis."
    "</div>"
    "</div>"
    '<div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px;">'
    f'<span class="live-badge"><span class="live-dot"></span>{mode_label}</span>'
    '<span style="font-size:12px; color:#94a3b8;">'
    f'Voice Persona: <strong style="color:#e2e8f0;">{html.escape(persona_label)}</strong>'
    "</span>"
    "</div>"
    "</div>"
    "</div>"
)
st.markdown(hero_html, unsafe_allow_html=True)

# ---------------------------- METRIC RIBBON -------------------------
m1, m2, m3, m4 = st.columns(4)
m1.markdown(
    '<div class="metric-card">'
    '<div class="metric-title">Session Exchanges</div>'
    f'<div class="metric-val">{len(st.session_state.messages)}</div>'
    '<div class="metric-caption">Active context memory</div>'
    "</div>",
    unsafe_allow_html=True,
)
m2.markdown(
    '<div class="metric-card">'
    '<div class="metric-title">Fee Protection Cap</div>'
    f'<div class="metric-val" style="color:#34d399;">${max_fee:,.2f}</div>'
    '<div class="metric-caption">Automatic fee guardrail</div>'
    "</div>",
    unsafe_allow_html=True,
)
script_now = str(telemetry.get("script_detected", "Auto • देवनागरी / EN"))
m3.markdown(
    '<div class="metric-card">'
    '<div class="metric-title">Active Voice Script</div>'
    f'<div class="metric-val" style="color:#7dd3fc; font-size:20px;">{html.escape(script_now)}</div>'
    '<div class="metric-caption">Native pronunciation routing</div>'
    "</div>",
    unsafe_allow_html=True,
)
m4.markdown(
    '<div class="metric-card">'
    '<div class="metric-title">Context &amp; Routing</div>'
    f'<div class="metric-val" style="font-size:19px;">{html.escape(resolved_relationship)}</div>'
    f'<div class="metric-caption">{html.escape(target_department)}</div>'
    "</div>",
    unsafe_allow_html=True,
)

# ---------------------------- MAIN WORKSPACE ------------------------
left, right = st.columns([1.68, 1], gap="large")

with left:
    render_mode_banner(is_roleplay)
    render_audio_visualizer(voice_enabled=voice_enabled)

    mic_col, hint_col = st.columns([1.05, 2.2])
    with mic_col:
        mic_key = f"holdout_microphone_{st.session_state.mic_version}"
        mic_label = "हिंदी" if mic_lang_code == "hi-IN" else "EN / Hinglish"
        spoken_text = speech_to_text(
            language=mic_lang_code,
            start_prompt=f"🎤 Speak ({mic_label})",
            stop_prompt="⏹️ Complete Turn",
            just_once=True,
            key=mic_key,
        )
    with hint_col:
        st.markdown(
            '<div style="font-size:12.5px; color:#94a3b8; padding-top:8px;">'
            "Speak naturally or type below. Even if you type in <strong>Hinglish</strong>, "
            "Holdout AI replies in <strong>देवनागरी</strong> so the Hindi voice sounds authentic."
            "</div>",
            unsafe_allow_html=True,
        )

    if spoken_text and spoken_text.strip():
        st.session_state.mic_version += 1
        process_turn(spoken_text, max_fee, voice_enabled)
        st.rerun()

    with st.form("typed_message_form", clear_on_submit=True):
        placeholder_text = (
            "Speak or type as the representative (in English, हिंदी, or Hinglish)..."
            if is_roleplay
            else "Ask anything in English, हिंदी, or Hinglish..."
        )
        typed_text = st.text_input(
            "Your Message",
            placeholder=placeholder_text,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Send Message ➤", use_container_width=True)

    if submitted and typed_text.strip():
        process_turn(typed_text, max_fee, voice_enabled)
        st.rerun()

    if st.session_state.last_voice_error:
        st.warning("Audio synthesis note: " + st.session_state.last_voice_error)

    if not st.session_state.messages:
        empty_html = (
            '<div class="empty-studio-card">'
            "🎙️ <strong>Studio Ready</strong><br>"
            "Use the microphone button or type a message above in English, हिंदी, or Hinglish to begin."
            "</div>"
        )
        st.markdown(empty_html, unsafe_allow_html=True)
    else:
        st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
        for item in st.session_state.messages:
            role = "user" if item["role"] == "user" else "assistant"
            avatar = "🧑‍💼" if role == "user" else "🎙️"
            with st.chat_message(role, avatar=avatar):
                st.write(item["content"])

# ------------------------- RIGHT TELEMETRY STUDIO -------------------
with right:
    safe_customer = html.escape(customer_name)
    safe_dept = html.escape(target_department)
    safe_goal = html.escape(mission_goal)

    brief_card_html = (
        '<div class="glass-card">'
        '<div class="card-eyebrow">Active Mission Brief</div>'
        '<div style="font-family:\'Outfit\',sans-serif; font-size:20px; font-weight:700; color:#f8fafc; margin-bottom:4px;">'
        f"{safe_customer}"
        "</div>"
        '<div style="font-size:13.5px; color:#cbd5e1; line-height:1.55; margin-bottom:10px;">'
        f"{safe_goal}"
        "</div>"
        '<div style="font-size:12px; color:#94a3b8;">'
        f'Target Department: <strong style="color:#e2e8f0;">{safe_dept}</strong>'
        "</div>"
        "</div>"
    )
    st.markdown(brief_card_html, unsafe_allow_html=True)

    tactic_str = html.escape(str(telemetry.get("tactic_used", "Standby")))
    stance_str = html.escape(str(telemetry.get("rep_stance", "Neutral")))
    model_str = html.escape(str(telemetry.get("model_used", "gemini-2.5-flash")))
    latency_val = int(telemetry.get("latency_ms", 0))

    reasoning_card_html = (
        '<div class="glass-card">'
        '<div class="card-eyebrow">Real-Time AI Reasoning</div>'
        '<div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px;">'
        '<span style="color:#94a3b8;">Selected Tactic</span>'
        f'<strong style="color:#7dd3fc;">{tactic_str}</strong>'
        "</div>"
        '<div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px;">'
        '<span style="color:#94a3b8;">Detected Counterparty Stance</span>'
        f'<strong style="color:#e2e8f0;">{stance_str}</strong>'
        "</div>"
        '<div style="display:flex; justify-content:space-between; font-size:12px; color:#64748b;">'
        f"<span>Model: {model_str}</span>"
        f"<span>Latency: {latency_val} ms</span>"
        "</div>"
        "</div>"
    )
    st.markdown(reasoning_card_html, unsafe_allow_html=True)

    st.markdown(
        '<div style="font-size:12.5px; font-weight:600; color:#94a3b8; margin: 12px 0 8px 4px;">'
        "Guardrail &amp; Outcome Tracker"
        "</div>",
        unsafe_allow_html=True,
    )

    for label, value in st.session_state.negotiation_status.items():
        badge_cls = get_status_badge_class(value)
        row_html = (
            '<div class="status-item">'
            f'<span class="status-name">{html.escape(label)}</span>'
            f'<span class="pill-badge {badge_cls}">{html.escape(value)}</span>'
            "</div>"
        )
        st.markdown(row_html, unsafe_allow_html=True)

    if st.session_state.messages:
        st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
        transcript_text = "\n\n".join(
            f"{'USER' if item['role'] == 'user' else 'HOLDOUT AI'}: {item['content']}"
            for item in st.session_state.messages
        )
        st.download_button(
            "⬇️ Export Session Transcript (.txt)",
            data=transcript_text,
            file_name="holdout_ai_transcript.txt",
            mime="text/plain",
            use_container_width=True,
        )

st.markdown("<div style='height: 18px'></div>", unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center; font-size:11.5px; color:#64748b; padding: 12px 0;">'
    "Holdout AI Studio · Bilingual Neural Speech (देवनागरी &amp; English) · Real-Time Web Audio Silk-Wave"
    "</div>",
    unsafe_allow_html=True,
)
