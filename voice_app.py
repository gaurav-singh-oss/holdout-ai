import asyncio
import html
import re
import time
import websockets  # <-- Added for live mock call connection
import streamlit as st
from streamlit_mic_recorder import speech_to_text

from agent import call_gemini, ask_gemini_ivr_choice, ask_gemini_agent_response, MISSION_BRIEF
from speaker import speak_text, render_audio_visualizer


# ---------------------------- PAGE SETUP ----------------------------
st.set_page_config(
    page_title="Holdout AI | Mission Control",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------- STYLE ------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --bg-deep: #050914;
        --bg-panel: rgba(13, 22, 40, 0.78);
        --bg-card: rgba(18, 30, 54, 0.65);
        --border-subtle: rgba(148, 163, 184, 0.14);
        --border-glow: rgba(56, 189, 248, 0.35);
        --text-primary: #f8fafc;
        --text-secondary: #94a3b8;
        --accent-cyan: #38bdf8;
        --accent-emerald: #10b981;
        --accent-amber: #f59e0b;
        --accent-rose: #f43f5e;
    }

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--text-primary);
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(29, 78, 216, 0.22) 0%, transparent 40%),
            radial-gradient(circle at 88% 15%, rgba(16, 185, 129, 0.12) 0%, transparent 38%),
            radial-gradient(circle at 50% 100%, rgba(15, 23, 42, 0.95) 0%, #040711 100%);
        background-color: var(--bg-deep);
    }

    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 3rem !important;
        max-width: 1440px;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #070d1c 0%, #0a1226 100%);
        border-right: 1px solid rgba(56, 189, 248, 0.14);
    }

    [data-testid="stSidebar"] .stMarkdown h2 {
        font-family: 'Space Grotesk', sans-serif !important;
        letter-spacing: -0.5px;
    }

    h1, h2, h3, h4 {
        font-family: 'Space Grotesk', sans-serif !important;
        letter-spacing: -0.02em;
    }

    .hero {
        position: relative;
        overflow: hidden;
        padding: 28px 32px;
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 22px;
        background: linear-gradient(135deg, rgba(15, 28, 54, 0.92) 0%, rgba(9, 16, 32, 0.95) 60%, rgba(12, 34, 52, 0.88) 100%);
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.08);
        margin-bottom: 22px;
    }

    .hero-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        flex-wrap: wrap;
        gap: 12px;
    }

    .eyebrow {
        font-family: 'JetBrains Mono', monospace;
        color: #38bdf8;
        text-transform: uppercase;
        letter-spacing: 2.2px;
        font-size: 11px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .hero-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 36px;
        font-weight: 700;
        color: #f8fafc;
        margin: 6px 0 4px;
        letter-spacing: -0.03em;
    }

    .hero-sub {
        color: #94a3b8;
        font-size: 14.5px;
        max-width: 680px;
        line-height: 1.5;
    }

    .pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border: 1px solid rgba(16, 185, 129, 0.45);
        background: rgba(6, 78, 59, 0.55);
        color: #6ee7b7;
        border-radius: 999px;
        padding: 6px 14px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.6px;
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.15);
    }

    .pulse-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #34d399;
        box-shadow: 0 0 8px #34d399;
        animation: pulse-glow 2s infinite;
    }

    @keyframes pulse-glow {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.25); opacity: 0.55; }
    }

    .kpi-card {
        background: var(--bg-panel);
        backdrop-filter: blur(14px);
        border: 1px solid var(--border-subtle);
        border-top: 2px solid rgba(56, 189, 248, 0.45);
        border-radius: 16px;
        padding: 16px 20px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.25);
        margin-bottom: 18px;
    }

    .kpi-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10.5px;
        text-transform: uppercase;
        letter-spacing: 1.4px;
        color: #94a3b8;
        margin-bottom: 6px;
    }

    .kpi-value {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 24px;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
    }

    .kpi-sub {
        font-size: 11.5px;
        color: #64748b;
        margin-top: 4px;
    }

    .panel {
        background: var(--bg-panel);
        backdrop-filter: blur(16px);
        border: 1px solid var(--border-subtle);
        border-radius: 16px;
        padding: 16px 18px;
        margin-bottom: 12px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
        transition: border-color 0.2s ease, transform 0.2s ease;
    }

    .panel:hover {
        border-color: rgba(56, 189, 248, 0.3);
    }

    .panel-label {
        font-family: 'JetBrains Mono', monospace;
        color: #7dd3fc;
        text-transform: uppercase;
        letter-spacing: 1.4px;
        font-size: 10px;
        font-weight: 600;
        margin-bottom: 6px;
    }

    .metric {
        font-family: 'Space Grotesk', sans-serif;
        color: #f8fafc;
        font-size: 21px;
        font-weight: 700;
    }

    .muted {
        color: #94a3b8;
        font-size: 12.5px;
        line-height: 1.5;
    }

    .mode-banner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 12px 16px;
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(56, 189, 248, 0.22);
        margin-bottom: 12px;
    }

    .mode-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 8px;
        white-space: nowrap;
    }

    .status-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        background: rgba(13, 22, 40, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.14);
        border-radius: 13px;
        padding: 11px 15px;
        margin-bottom: 9px;
    }

    .status-key {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #94a3b8;
    }

    .status-pill {
        font-size: 12px;
        font-weight: 600;
        padding: 4px 11px;
        border-radius: 999px;
        text-align: right;
    }

    .badge-emerald {
        background: rgba(16, 185, 129, 0.15);
        color: #6ee7b7;
        border: 1px solid rgba(16, 185, 129, 0.35);
    }

    .badge-rose {
        background: rgba(244, 63, 94, 0.16);
        color: #fda4af;
        border: 1px solid rgba(244, 63, 94, 0.4);
    }

    .badge-amber {
        background: rgba(245, 158, 11, 0.15);
        color: #fcd34d;
        border: 1px solid rgba(245, 158, 11, 0.38);
    }

    .badge-cyan {
        background: rgba(56, 189, 248, 0.14);
        color: #7dd3fc;
        border: 1px solid rgba(56, 189, 248, 0.35);
    }

    .badge-slate {
        background: rgba(51, 65, 85, 0.45);
        color: #cbd5e1;
        border: 1px solid rgba(148, 163, 184, 0.2);
    }

    .stButton > button, .stFormSubmitButton > button {
        border-radius: 11px !important;
        font-weight: 600 !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        background: linear-gradient(135deg, rgba(14, 116, 144, 0.45), rgba(30, 58, 138, 0.55)) !important;
        color: #f8fafc !important;
        transition: all 0.2s ease !important;
    }

    .stButton > button:hover, .stFormSubmitButton > button:hover {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 18px rgba(56, 189, 248, 0.28) !important;
        transform: translateY(-1px);
    }

    div[data-testid="stChatMessage"] {
        background: rgba(15, 25, 45, 0.82);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 16px;
        padding: 14px 18px;
        margin-bottom: 10px;
        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.2);
    }

    [data-testid="stForm"] {
        background: rgba(13, 22, 40, 0.65);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 16px;
        padding: 14px 16px;
    }

    hr {
        border-color: rgba(148, 163, 184, 0.15);
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


def enforce_fee_limit(user_message, maximum_fee, ai_reply):
    """Basic demo safeguard for explicit currency amounts in the latest input."""
    pattern = (
        r"\$\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd)\b"
    )
    matches = re.findall(pattern, user_message, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]
    text = user_message.lower()
    fee_context = any(
        word in text
        for word in ("fee", "charge", "payment", "pay", "termination", "cancellation")
    )
    if fee_context and any(amount > float(maximum_fee) for amount in amounts):
        return (
            f"I cannot authorize a fee above ${float(maximum_fee):.2f}. "
            "Please check whether the fee can be waived or whether a no-fee "
            "alternative is available. I will not agree to the proposed fee."
        )
    return ai_reply

async def run_autonomous_call(scenario_name: str, max_fee: float, voice_enabled: bool):
    """Connect to the mock call center WebSocket and run an automated negotiation."""
    uri = f"ws://localhost:8000/call-stream?scenario={scenario_name}"
    
    st.session_state.messages.append({
        "role": "assistant",
        "content": f"🚀 [System]: Dialing mock call center for scenario '{scenario_name}'..."
    })
    
    try:
        async with websockets.connect(uri) as websocket:
            async for raw_message in websocket:
                import json
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
                            "content": f"🤖 **[IVR Menu]**: {text}"
                        })
                        # Use agent.py IVR selector to pick the digit
                        target_dept = MISSION_BRIEF.get("target_department", "Billing")
                        digit = ask_gemini_ivr_choice(text, target_dept)
                        
                        st.session_state.messages.append({
                            "role": "user",
                            "content": f"[DTMF Keypad]: Pressed digit **{digit}**"
                        })
                        await websocket.send(digit)
                        
                    elif sender == "HUMAN_AGENT":
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"👤 **[Mock Representative]**: {text}"
                        })
                        
                        if voice_enabled:
                            speak_text(text)
                            
                        # Generate autonomous agent response using agent.py
                        ai_reply = ask_gemini_agent_response(text)
                        
                        st.session_state.messages.append({
                            "role": "user",
                            "content": f"🎙️ **[Holdout AI Agent]**: {ai_reply}"
                        })
                        
                        if voice_enabled:
                            speak_text(ai_reply)
                            
                        # Send AI reply back to the mock call center
                        await websocket.send(ai_reply)
                        
                elif msg_type == "audio_event":
                    sound_desc = data.get("sound", "Hold music playing...")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"🎶 *[Call Audio Event]*: {sound_desc}"
                    })
                    
                st.rerun()
                
    except Exception as exc:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"❌ **[Connection Error]**: Could not connect to mock server at `{uri}`. Is Uvicorn running? Error: {exc}"
        })
        st.rerun()

def update_negotiation_status(message, statuses, maximum_fee, source="conversation"):
    """Track signals mentioned in the demo; these are not external verification."""
    text = message.lower()
    pattern = (
        r"\$\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd)\b"
    )
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]
    fee_context = any(
        word in text for word in ("fee", "charge", "payment", "pay", "termination", "cancellation")
    )

    if fee_context and amounts:
        if any(amount > float(maximum_fee) for amount in amounts):
            statuses["Fee limit"] = "Over-limit amount mentioned"
            statuses["Authorisation"] = "Not authorised"
        else:
            statuses["Fee limit"] = "Fee amount mentioned"

    if any(word in text for word in ("waiver", "waived", "waive")):
        statuses["Negotiation"] = "Waiver discussed"

    waiver_confirmations = (
        "fee has been waived",
        "fee is waived",
        "waiver has been approved",
        "waiver is approved",
        "your cancellation fee is zero",
        "there is no cancellation fee",
        "there is no early termination fee",
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
    )
    if source == "other_party" and any(phrase in text for phrase in cancellation_confirmations):
        statuses["Cancellation"] = "Confirmation stated in demo"

    if (
        statuses.get("Fee outcome") == "Waiver stated by demo participant"
        and statuses.get("Cancellation") == "Confirmation stated in demo"
    ):
        statuses["Mission"] = "Demo goals stated as met — verify externally"
    return statuses


def process_turn(user_text, maximum_fee, voice_enabled):
    """Handle a turn using the selected conversation mode and relationship context."""
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

    st.session_state.messages.append({"role": "user", "content": clean_text})

    if mode == "Negotiation role-play (I act as the representative)":
        st.session_state.negotiation_status = update_negotiation_status(
            clean_text, st.session_state.negotiation_status, maximum_fee, source="other_party"
        )

    history = "\n".join(
        f"{'USER' if item['role'] == 'user' else 'HOLDOUT AI'}: {item['content']}"
        for item in st.session_state.messages[-16:]
    )

    if mode == "Direct conversation with me":
        role_instructions = """
CONVERSATION MODE: DIRECT CHAT
- The person typing or speaking is the USER talking directly to you, Holdout AI.
- Talk TO the user. Do not pretend the user is a company representative, bank employee,
  customer-service agent, or a different customer.
- Do not speak on the user's behalf or write dialogue as if you are calling another person.
- Follow the user's current request. The saved mission objective may belong to a previous
  negotiation scenario; do not force it onto unrelated questions. Use it when the user asks
  about that mission or when their request clearly relates to it. If the current request is
  unclear, ask the user a short clarifying question.
- Explain, advise, draft, or help with the task as requested. Do not treat ordinary chat as
  proof that a negotiation, waiver, payment, or cancellation happened.
"""
    else:
        role_instructions = f"""
CONVERSATION MODE: NEGOTIATION ROLE-PLAY
- The user is acting as the representative/other party in a simulated conversation.
- You are Holdout AI, acting as the customer's authorised negotiation agent for {customer_name}.
- Speak directly to the role-play representative, not to the user as a coach.
- The user's messages represent what the representative says. Your replies are what the AI agent says.
- Follow the mission and authorisation limits below. This is only a simulation.
"""

    prompt = f"""
You are Holdout AI, a conversational AI assistant. Follow the user's instructions and the selected
mode. Do not silently switch roles or assume who the user is.

{role_instructions}

RELATIONSHIP / SOCIAL CONTEXT: {relationship}
TARGET DEPARTMENT OR CONTACT: {department}
USER'S STATED OBJECTIVE: {target}
CUSTOMER NAME (used only in negotiation role-play): {customer_name}
MAXIMUM AUTHORISED FEE (only relevant to fee negotiations): ${maximum_fee:.2f}

HOW TO HANDLE CONTEXT AND TONE:
- Adapt naturally to the selected relationship/context; do not use one generic professional tone for everyone.
- Family: warm, familiar, considerate, and relaxed.
- Friend: casual, natural, friendly, and direct.
- Stranger / general public: polite, neutral, and respectful without assuming familiarity.
- Customer service / company: clear, polite, concise, and solution-focused.
- Bank / financial institution: precise, calm, formal, and careful about commitments.
- Workplace / professional contact: professional, respectful, and collaborative.
- If the context is not specified or the person is not actually present in the conversation, ask for clarification rather than inventing details.
- Do not infer a relationship solely from someone's name or from a single message; use the selected context.

CONVERSATION HISTORY:
{history}

GENERAL RULES:
- Respond to the latest user message using relevant history.
- Follow the stated objective and the user's direct instructions; do not substitute a different mission.
- Be natural, expressive, and concise, suitable for spoken audio.
- Avoid repeating the same answer or question unless needed.
- Do not invent personal details, company policies, legal rights, promises, or outcomes.
- Do not claim to have contacted anyone or changed a real account.
- In direct-chat mode, never treat the user as the representative in a role-play.
- In negotiation role-play, never agree to or authorise a fee above ${maximum_fee:.2f}.
- Do not claim cancellation or a waiver is complete unless the role-play representative explicitly confirms it.
- If a statement or instruction is ambiguous, ask one short clarifying question.
- Reply only with the words you would say aloud. No headings or internal notes.

This is a browser-based academic prototype. No real telephone call is connected.
"""
    try:
        with st.spinner("Holdout AI is synthesizing a response..."):
            reply = call_gemini(prompt)
        if not isinstance(reply, str) or not reply.strip():
            reply = "I couldn't generate a response just now. Please try again."
    except Exception as exc:
        st.session_state.messages.append({
            "role": "assistant",
            "content": f"I couldn't reach Gemini: {type(exc).__name__}: {exc}",
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
            speak_text(reply)
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
        "Negotiation": "Not started",
        "Fee outcome": "Not confirmed",
        "Cancellation": "Not confirmed",
        "Mission": "In progress",
    }
if "mic_version" not in st.session_state:
    st.session_state.mic_version = 0
if "last_voice_error" not in st.session_state:
    st.session_state.last_voice_error = ""
if "interaction_mode" not in st.session_state:
    st.session_state.interaction_mode = "Direct conversation with me"
if "relationship_context" not in st.session_state:
    st.session_state.relationship_context = "General conversation"
if "custom_department" not in st.session_state:
    st.session_state.custom_department = ""

# ------------------------------- SIDEBAR ---------------------------
with st.sidebar:
    st.markdown("## 🎙️ Holdout AI")
    st.caption("MISSION CONFIGURATION & GUARDRAILS")

    customer_name = st.text_input(
        "Customer name", value=MISSION_BRIEF.get("customer_name", "Kumar")
    )

    interaction_mode = st.selectbox(
        "Conversation mode",
        [
            "Direct conversation with me",
            "Negotiation role-play (I act as the representative)",
        ],
        key="interaction_mode",
        help="Direct chat means the AI talks to you. Role-play means you pretend to be the service representative.",
    )

    relationship_context = st.selectbox(
        "Who / what context are you talking about?",
        [
            "General conversation",
            "Family",
            "Friend",
            "Stranger / general public",
            "Customer service",
            "Bank / financial institution",
            "Company / business",
            "Workplace / professional contact",
            "Government / official service",
            "Other (I will describe it)",
        ],
        key="relationship_context",
    )

    custom_relationship = ""
    if relationship_context == "Other (I will describe it)":
        custom_relationship = st.text_input(
            "Describe the relationship/context",
            placeholder="e.g. professor, neighbour, shop owner",
        )

    target_department_choice = st.selectbox(
        "Target department (optional)",
        [
            "None / not applicable",
            "Billing or Cancellations",
            "Retention",
            "Customer Support",
            "Technical Support",
            "Other (enter my own)",
        ],
    )

    custom_department = ""
    if target_department_choice == "Other (enter my own)":
        custom_department = st.text_input(
            "Enter department or contact",
            placeholder="e.g. Fraud Prevention, Loans, HR, Admissions",
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

    st.divider()
    st.caption("NEGOTIATION PARAMETERS")

    mission_goal = st.text_area(
        "Mission objective",
        value=MISSION_BRIEF.get(
            "goal", "Cancel the subscription and request a fee waiver."
        ),
        height=95,
    )

    max_fee = st.number_input(
        "Maximum authorised fee ($)",
        min_value=0.0,
        max_value=100000.0,
        value=float(MISSION_BRIEF.get("max_acceptable_fee", 0)),
        step=5.0,
    )

    voice_enabled = st.toggle("Speak AI responses aloud", value=True)

    st.divider()
    st.markdown("**DEMO CONTROLS**")
    if st.button("↻ Reset conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.negotiation_status = {
            "Fee limit": "Not assessed",
            "Authorisation": "No fee approved",
            "Negotiation": "Not started",
            "Fee outcome": "Not confirmed",
            "Cancellation": "Not confirmed",
            "Mission": "In progress",
        }
        st.session_state.pop("audio_payload", None)
        st.session_state.last_voice_error = ""
        st.session_state.mic_version += 1
        st.rerun()

    st.divider()
    st.markdown("**🤖 AUTONOMOUS LIVE CALL**")
    selected_mock_scenario = st.selectbox(
        "Mock Call Scenario",
        ["aegis_security", "apex_telecom", "vantis_bank", "cloudscale_saas"],
        help="Select which mock company to dial autonomously."
    )
    if st.button("🚀 Start Live Autonomous Call", use_container_width=True):
        st.session_state.messages = []
        # Run the async WebSocket client loop inside Streamlit
        asyncio.run(run_autonomous_call(selected_mock_scenario, max_fee, voice_enabled))

    st.caption("Browser simulation • No live telephone connection")

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

# -------------------------------- HEADER ----------------------------
is_roleplay = interaction_mode == "Negotiation role-play (I act as the representative)"
mode_short = "NEGOTIATION SIMULATOR" if is_roleplay else "DIRECT ASSISTANT"

st.markdown(
    f"""
    <div class="hero">
      <div class="hero-top">
        <div>
          <div class="eyebrow">⚡ Adaptive Conversation &amp; Negotiation Engine · v1.3</div>
          <div class="hero-title">Holdout AI · Mission Control</div>
          <div class="hero-sub">
            Autonomous voice-enabled customer service navigation, real-time fee-cap enforcement,
            and live Web Audio spectrum synthesis.
          </div>
        </div>
        <div style="display:flex; flex-direction:column; align-items:flex-end; gap:8px;">
          <span class="pill"><span class="pulse-dot"></span>DEMO TELEMETRY ACTIVE</span>
          <span style="font-family:'JetBrains Mono',monospace; font-size:11px; color:#94a3b8;">
            MODE: <strong style="color:#38bdf8;">{mode_short}</strong>
          </span>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------- KPI RIBBON ----------------------------
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">Conversation Turns</div>
          <div class="kpi-value">{len(st.session_state.messages)}</div>
          <div class="kpi-sub">Active session memory</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f"""
        <div class="kpi-card" style="border-top-color: rgba(16, 185, 129, 0.55);">
          <div class="kpi-label">Authorised Fee Ceiling</div>
          <div class="kpi-value">${max_fee:,.2f}</div>
          <div class="kpi-sub">Hard regex safeguard active</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with k3:
    voice_color = "#34d399" if voice_enabled else "#94a3b8"
    st.markdown(
        f"""
        <div class="kpi-card" style="border-top-color: rgba(245, 158, 11, 0.55);">
          <div class="kpi-label">Voice Synthesizer</div>
          <div class="kpi-value" style="color:{voice_color};">
            {"Enabled" if voice_enabled else "Muted"}
          </div>
          <div class="kpi-sub">Browser Web Audio TTS</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        f"""
        <div class="kpi-card" style="border-top-color: rgba(168, 85, 247, 0.55);">
          <div class="kpi-label">Social Context</div>
          <div class="kpi-value" style="font-size:18px; padding-top:4px;">
            {html.escape(resolved_relationship)}
          </div>
          <div class="kpi-sub">Dept: {html.escape(target_department)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

left, right = st.columns([1.68, 1], gap="large")

# ---------------------------- CONVERSATION -------------------------
with left:
    st.markdown("### 💬 Live Transceiver & Audio Spectrum")

    if is_roleplay:
        st.markdown(
            """
            <div class="mode-banner">
              <div class="muted" style="color:#cbd5e1;">
                <strong>Role-Play Active:</strong> Speak or type as the <em>company representative</em>.
                Holdout AI will respond as the customer's authorized negotiation agent.
              </div>
              <span class="mode-badge badge-amber">REP SIMULATION</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="mode-banner">
              <div class="muted" style="color:#cbd5e1;">
                <strong>Direct Mode Active:</strong> Talk directly to Holdout AI for strategy advice,
                call scripting, or general questions.
              </div>
              <span class="mode-badge badge-cyan">DIRECT CHAT</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Live 60FPS Web Audio Spectrum & Waveform Visualizer
    render_audio_visualizer(voice_enabled=voice_enabled)

    # Audio + Text Input Dock
    mic_col, info_col = st.columns([1, 2.2])
    with mic_col:
        mic_key = f"holdout_microphone_{st.session_state.mic_version}"
        spoken_text = speech_to_text(
            language="en",
            start_prompt="🎤 Push to Speak",
            stop_prompt="⏹️ Finish Recording",
            just_once=True,
            key=mic_key,
        )
    with info_col:
        st.markdown(
            '<div class="muted" style="padding-top:8px;">'
            "Use <strong>Push to Speak</strong> to capture your voice turn, or toggle "
            "<strong>Live Mic Scope</strong> inside the waveform deck to inspect your audio levels."
            "</div>",
            unsafe_allow_html=True,
        )

    if spoken_text and spoken_text.strip():
        st.session_state.mic_version += 1
        process_turn(spoken_text, max_fee, voice_enabled)
        st.rerun()

    with st.form("typed_message_form", clear_on_submit=True):
        placeholder_text = (
            "Example: We can cancel the service, but there is a $100 early termination fee..."
            if is_roleplay
            else "Ask Holdout AI anything, or ask how to negotiate your bill..."
        )
        typed_text = st.text_input(
            "Transmit text message",
            placeholder=placeholder_text,
        )
        submitted = st.form_submit_button("Send Transmission ➤", use_container_width=True)

    if submitted and typed_text.strip():
        process_turn(typed_text, max_fee, voice_enabled)
        st.rerun()

    if st.session_state.last_voice_error:
        st.warning(
            "The text response was generated, but audio playback failed: "
            + st.session_state.last_voice_error
        )

    st.divider()

    # Empty State + Quick-Test Triggers
    if not st.session_state.messages:
        st.info(
            "No transmissions yet. Record voice, type a message above, or click a quick-test scenario below:"
        )
        q1, q2 = st.columns(2)
        if is_roleplay:
            with q1:
                if st.button("💸 Test $100 Fee Pushback", use_container_width=True):
                    process_turn(
                        "I can process that cancellation for you, but your contract has a $100 early termination fee.",
                        max_fee,
                        voice_enabled,
                    )
                    st.rerun()
            with q2:
                if st.button("✅ Test Waiver & Cancellation", use_container_width=True):
                    process_turn(
                        "Okay, the fee has been waived and your subscription has been cancelled.",
                        max_fee,
                        voice_enabled,
                    )
                    st.rerun()
        else:
            with q1:
                if st.button("📋 Draft a Fee-Waiver Script", use_container_width=True):
                    process_turn(
                        "Give me a concise 3-step script to ask retention to waive my cancellation fee.",
                        max_fee,
                        voice_enabled,
                    )
                    st.rerun()
            with q2:
                if st.button("🎯 Review My Mission Brief", use_container_width=True):
                    process_turn(
                        "Summarize my current mission objective and how you would handle a pushy agent.",
                        max_fee,
                        voice_enabled,
                    )
                    st.rerun()
    else:
        for item in st.session_state.messages:
            role = "user" if item["role"] == "user" else "assistant"
            avatar = "🧑‍💼" if role == "user" else "🎙️"
            with st.chat_message(role, avatar=avatar):
                st.write(item["content"])

# ----------------------------- MISSION PANEL -----------------------
with right:
    st.markdown("### 🎯 Mission Telemetry")

    safe_customer = html.escape(customer_name)
    safe_dept = html.escape(target_department)
    safe_goal = html.escape(mission_goal)

    st.markdown(
        f"""
        <div class="panel">
          <div class="panel-label">Authorised Principal &amp; Routing</div>
          <div class="metric">{safe_customer}</div>
          <div class="muted" style="margin-top:4px;">Target Dept: <strong style="color:#e2e8f0;">{safe_dept}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="panel">
          <div class="panel-label">Active Directive</div>
          <div style="color:#e2e8f0; font-size:14px; line-height:1.55;">{safe_goal}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="panel-label" style="margin: 14px 0 8px 4px;">Live Signal Matrix</div>',
        unsafe_allow_html=True,
    )

    for label, value in st.session_state.negotiation_status.items():
        badge_cls = get_status_badge_class(value)
        st.markdown(
            f"""
            <div class="status-row">
              <span class="status-key">{html.escape(label)}</span>
              <span class="status-pill {badge_cls}">{html.escape(value)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(
        "ℹ️ Telemetry is inferred from role-play dialogue signals and does not verify external account changes."
    )

# ---------------------------- SESSION SUMMARY ----------------------
st.markdown("<div style='height: 12px'></div>", unsafe_allow_html=True)
with st.expander("📄 Session Summary & Transcript Export"):
    if not st.session_state.messages:
        st.write("No conversation recorded in this session yet.")
    else:
        s1, s2 = st.columns(2)
        with s1:
            st.write(f"**Customer:** {customer_name}")
            st.write(f"**Mode:** {interaction_mode}")
            st.write(f"**Relationship/Context:** {resolved_relationship}")
            st.write(f"**Target Department/Contact:** {target_department}")
        with s2:
            st.write(f"**Objective:** {mission_goal}")
            st.write(f"**Maximum Fee:** ${max_fee:.2f}")
            st.write(f"**Messages Exchanged:** {len(st.session_state.messages)}")

        st.markdown("**Latest AI Response:**")
        latest_ai = next(
            (
                item["content"]
                for item in reversed(st.session_state.messages)
                if item["role"] == "assistant"
            ),
            "No AI response yet.",
        )
        st.info(latest_ai)

        st.download_button(
            "⬇️ Download Conversation Transcript (.txt)",
            data="\n\n".join(
                f"{'USER' if item['role'] == 'user' else 'HOLDOUT AI'}: {item['content']}"
                for item in st.session_state.messages
            ),
            file_name="holdout_ai_transcript.txt",
            mime="text/plain",
            use_container_width=True,
        )

st.markdown("---")
st.markdown(
    '<div class="muted" style="text-align:center; font-family:\'JetBrains Mono\', monospace; font-size:11px;">'
    "HOLDOUT AI · Academic Prototype · Gemini Text Reasoning · Browser Speech Input · "
    "Web Audio Spectrum TTS · No Live Telephone Connection"
    "</div>",
    unsafe_allow_html=True,
)