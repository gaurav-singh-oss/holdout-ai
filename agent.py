import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------- LOGGING SETUP --------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | HoldoutAgent | %(message)s",
)
logger = logging.getLogger("HoldoutAgent")

# ---------------------------- CONFIGURATION --------------------------
API_KEY = os.getenv("GEMINI_API_KEY")

# If the key is not found in .env, check Streamlit Cloud Secrets
if not API_KEY:
    try:
        import streamlit as st
        API_KEY = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        API_KEY = None

ACTIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


# Automatic failover cascade if the primary model is rate-limited or unavailable
MODEL_CASCADE: List[str] = [
    ACTIVE_MODEL,
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

# Deduplicate while preserving order
MODEL_CASCADE = list(dict.fromkeys(MODEL_CASCADE))

ai_client = genai.Client(api_key=API_KEY) if API_KEY else None

MISSION_BRIEF: Dict[str, Any] = {
    "goal": "Cancel internet subscription and refuse early termination fees.",
    "target_department": "Billing or Cancellations",
    "customer_name": "Kumar",
    "max_acceptable_fee": 0.0,
}

# Keep recent conversation context for standalone negotiation calls.
CONVERSATION_HISTORY: List[Dict[str, str]] = []

# Stores real-time tactical telemetry from the latest turn
LAST_TURN_TELEMETRY: Dict[str, Any] = {
    "tactic_used": "Standby",
    "rep_stance": "Neutral",
    "detected_fee": None,
    "model_used": ACTIVE_MODEL,
    "latency_ms": 0,
}


# ------------------------ STRUCTURED SCHEMAS -------------------------
class TurnTelemetry(BaseModel):
    """Structured reasoning schema for standalone negotiation turns."""
    rep_stance: str = Field(
        description="Representative's current stance: 'Cooperative', 'Stonewalling', 'Fee-Demanding', 'Retention-Pitching', or 'Confirming'"
    )
    tactic_selected: str = Field(
        description="Tactical move chosen: 'Polite Anchor', 'Tactical Empathy + Fee Refusal', 'Policy/Waiver Inquiry', 'Billing-Pause Pivot', 'Supervisor Escalation', or 'Confirmation Lock-In'"
    )
    spoken_reply: str = Field(
        description="Exact natural spoken response to say aloud to the representative. No markdown or stage directions."
    )


# ---------------------- TACTICAL PLAYBOOK ENGINE ---------------------
def analyze_conversation_signals(text: str, max_fee: float) -> Dict[str, Any]:
    """
    Deterministic pre-analysis of incoming text to detect fee demands,
    retention stalls, waiver mentions, and confirmations.
    """
    lower = (text or "").lower()
    fee_pattern = (
        r"\$\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd)\b"
    )
    matches = re.findall(fee_pattern, lower, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]

    fee_keywords = ("fee", "charge", "payment", "pay", "termination", "cancellation", "penalty", "cost")
    has_fee_context = any(k in lower for k in fee_keywords)
    highest_fee = max(amounts) if (has_fee_context and amounts) else None
    over_limit = highest_fee is not None and highest_fee > float(max_fee)

    # Detect representative stance
    if any(p in lower for p in ("waived", "no cancellation fee", "zero fee", "cancelled", "canceled")):
        rep_stance = "Confirming / Cooperative"
        recommended_tactic = "Confirmation Lock-In (Request reference number & verify $0 balance)"
    elif over_limit:
        rep_stance = f"Demanding Over-Limit Fee (${highest_fee:.2f})"
        recommended_tactic = (
            "Tactical Empathy + Hard Refusal (Acknowledge their system prompt, firmly refuse the fee, "
            "and ask for a courtesy loyalty waiver, billing pause, or retention supervisor)"
        )
    elif any(k in lower for k in ("discount", "promo", "lower rate", "keep your service", "stay with us")):
        rep_stance = "Retention Pitching"
        recommended_tactic = "Polite Pivot (Decline retention upsell and redirect back to full cancellation + waiver)"
    elif any(k in lower for k in ("policy", "mandatory", "contract", "cannot waive", "can't waive")):
        rep_stance = "Policy Stonewalling"
        recommended_tactic = (
            "Escalation / Alternative Framing (Ask if a supervisor has override authority or if downgrading/pausing "
            "first eliminates the early termination fee)"
        )
    else:
        rep_stance = "Information Gathering"
        recommended_tactic = "Clear Directive (State objective clearly and keep momentum toward resolution)"

    return {
        "highest_fee": highest_fee,
        "over_limit": over_limit,
        "rep_stance": rep_stance,
        "recommended_tactic": recommended_tactic,
    }


def sanitize_spoken_output(text: str) -> str:
    """
    Clean LLM output so it is 100% ready for TTS voice synthesis:
    - Removes speaker prefixes ('HOLDOUT AI:', 'Assistant:', etc.)
    - Strips markdown symbols (*, #, `) and bracketed stage directions ([sighs], (pauses))
    - Collapses extra whitespace
    """
    if not text:
        return ""

    cleaned = text.strip()
    # Remove leading speaker labels
    cleaned = re.sub(
        r"^(?:holdout\s*ai|assistant|agent|ai|response)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove stage directions in brackets or asterisks like [polite tone] or *smiles*
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"\*[^*]+\*", "", cleaned)
    # Strip remaining markdown characters
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    # Remove surrounding quotes if the entire response was wrapped in quotes
    if len(cleaned) >= 2 and cleaned[0] in ('"', "“") and cleaned[-1] in ('"', "”"):
        cleaned = cleaned[1:-1].strip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def enforce_agent_fee_guardrail(reply: str, max_fee: float) -> str:
    """
    Ensure the AI never accidentally agrees to pay an unauthorized fee.
    """
    lower = reply.lower()
    agreement_phrases = (
        "i agree to pay",
        "i will pay the",
        "go ahead and charge",
        "you can charge the",
        "i accept the fee",
        "i'll pay the",
    )
    if any(phrase in lower for phrase in agreement_phrases):
        fee_pattern = (
            r"\$\s*(\d+(?:\.\d{1,2})?)"
            r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd)\b"
        )
        matches = re.findall(fee_pattern, lower, flags=re.IGNORECASE)
        amounts = [float(a or b) for a, b in matches]
        if not amounts and max_fee == 0:
            return (
                "I am not authorized to approve any cancellation or termination fee. "
                "Please check if we can process a courtesy fee waiver or explore a no-fee option."
            )
        if any(amt > float(max_fee) for amt in amounts):
            return (
                f"I cannot authorize any fee above ${float(max_fee):.2f}. "
                "Could you check if a loyalty waiver applies, or connect me with a specialist who can waive that charge?"
            )
    return reply


# ------------------------- CORE GEMINI CALLER ------------------------
def call_gemini(
    prompt: str,
    max_retries: int = 3,
    temperature: float = 0.35,
    system_instruction: Optional[str] = None,
) -> str:
    """
    Generate a response using Gemini with multi-model failover,
    exponential backoff + jitter, and TTS output sanitization.
    """
    if ai_client is None:
        return (
            "The AI is not configured yet. "
            "Please check the GEMINI_API_KEY in your .env file."
        )

    start_time = time.perf_counter()

    # Inject a lightweight tactical hint if this is a negotiation prompt
    max_fee = float(MISSION_BRIEF.get("max_acceptable_fee", 0.0))
    signals = analyze_conversation_signals(prompt, max_fee)

    default_sys_instruction = (
        "You are Holdout AI, an elite voice-first negotiation and conversation assistant. "
        "Speak naturally, concisely, and persuasively in plain spoken English suitable for "
        "real-time text-to-speech playback. Never use markdown, bullet points, or stage directions."
    )
    active_sys_instruction = system_instruction or default_sys_instruction

    config = types.GenerateContentConfig(
        system_instruction=active_sys_instruction,
        temperature=temperature,
        top_p=0.9,
        max_output_tokens=280,
    )

    last_error: Optional[Exception] = None

    for model_name in MODEL_CASCADE:
        for attempt in range(max_retries):
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )

                raw_answer = response.text if response and response.text else ""
                cleaned_answer = sanitize_spoken_output(raw_answer)

                if cleaned_answer:
                    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                    LAST_TURN_TELEMETRY.update({
                        "tactic_used": signals["recommended_tactic"].split("(")[0].strip(),
                        "rep_stance": signals["rep_stance"],
                        "detected_fee": signals["highest_fee"],
                        "model_used": model_name,
                        "latency_ms": elapsed_ms,
                    })
                    return cleaned_answer

                return "Could you clarify that last point for me before we proceed?"

            except Exception as error:
                last_error = error
                logger.warning(
                    "Model '%s' attempt %d/%d failed: %s",
                    model_name,
                    attempt + 1,
                    max_retries,
                    error,
                )
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    sleep_time = (1.2 ** attempt) + random.uniform(0.15, 0.55)
                    time.sleep(sleep_time)

        logger.info("Switching to next fallback model in cascade...")

    logger.error("All Gemini models failed. Last error: %s", last_error)
    return (
        "I'm experiencing a brief connection delay on my end. "
        "Please hold for just a moment while I reconnect."
    )


# ------------------------ IVR MENU NAVIGATION ------------------------
def _heuristic_ivr_choice(ivr_text: str, target_department: str) -> Optional[str]:
    """
    Fast regex pattern matcher for standard IVR menus (e.g., 'Press 2 for Billing').
    Used as an instant fallback if the API is unreachable.
    """
    target_words = [
        w.lower()
        for w in re.split(r"\W+", target_department or "")
        if len(w) > 2 and w.lower() not in ("and", "the", "for")
    ]
    if not target_words:
        target_words = ["cancel", "billing", "retention", "support", "representative", "agent"]

    # Match patterns like "press 1 for billing" or "for cancellations, press 3"
    lines = re.split(r"[.\n;]+", ivr_text.lower())
    for line in lines:
        if any(word in line for word in target_words):
            digit_match = re.search(r"\b([0-9])\b", line)
            if digit_match:
                return digit_match.group(1)
    return None


def ask_gemini_ivr_choice(ivr_text: str, target_department: str) -> str:
    """Choose a valid menu digit (0-9) based on the IVR transcript."""
    if not (ivr_text or "").strip():
        return "0"

    prompt = f"""
You are Holdout AI, an automated telephone IVR navigation engine.

Target department: {target_department}

Telephone menu transcript:
{ivr_text}

Task:
Select the single keypad digit (0-9) that most directly routes the call to the target department,
cancellations, retention, or a live human representative.

Rules:
- Return ONLY a single digit from 0 to 9.
- Do not include explanations, words, or punctuation.
- If no suitable option exists, return 0.
"""

    if ai_client is not None:
        answer = call_gemini(prompt, max_retries=2, temperature=0.0)
        for character in answer:
            if character.isdigit():
                return character

    # Zero-latency deterministic fallback if Gemini response had no digit or API key is missing
    heuristic_digit = _heuristic_ivr_choice(ivr_text, target_department)
    return heuristic_digit if heuristic_digit is not None else "0"


# --------------------- STANDALONE AGENT LOOP -------------------------
def ask_gemini_agent_response(agent_speech: str) -> str:
    """
    Generate a tactical negotiation response using the current MISSION_BRIEF
    and structured Pydantic reasoning when available.
    """
    clean_speech = (agent_speech or "").strip()
    if not clean_speech:
        return "Hello, I am on the line. Could you repeat that for me?"

    max_fee = float(MISSION_BRIEF.get("max_acceptable_fee", 0.0))
    signals = analyze_conversation_signals(clean_speech, max_fee)

    history = "\n".join(
        f"{entry['speaker']}: {entry['text']}"
        for entry in CONVERSATION_HISTORY[-12:]
    )

    prompt = f"""
You are Holdout AI, an authorized negotiation agent acting on behalf of {MISSION_BRIEF['customer_name']}.

MISSION OBJECTIVE:
{MISSION_BRIEF['goal']}

TARGET DEPARTMENT:
{MISSION_BRIEF['target_department']}

MAXIMUM AUTHORISED FEE CEILING:
${max_fee:.2f}

REAL-TIME TACTICAL ANALYSIS OF REPRESENTATIVE'S STATEMENT:
- Detected Representative Stance: {signals['rep_stance']}
- Recommended Negotiation Tactic: {signals['recommended_tactic']}

RECENT CONVERSATION HISTORY:
{history if history else "No previous conversation."}

LATEST REPRESENTATIVE STATEMENT:
{clean_speech}

NEGOTIATION PLAYBOOK RULES:
1. Be calm, polite, natural, and concise (2 to 3 sentences maximum).
2. Use tactical empathy: acknowledge the representative's position before pivoting to your request.
3. Never agree to or authorize any fee above ${max_fee:.2f}.
4. If the representative demands an early termination or cancellation fee above ${max_fee:.2f},
   politely refuse it and ask for a courtesy loyalty waiver, a billing pause/downgrade option that
   avoids the fee, or escalation to a retention specialist.
5. Never fabricate personal details, account numbers, legal statutes, or prior promises.
6. Do not claim the cancellation or waiver is complete until the representative explicitly confirms it.
7. Once confirmed, thank them and ask for a confirmation or reference number.
8. Output ONLY the exact spoken words you would say aloud.
"""

    reply = ""

    # Try structured Pydantic reasoning first for rich telemetry
    if ai_client is not None:
        try:
            start_time = time.perf_counter()
            response = ai_client.models.generate_content(
                model=ACTIVE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TurnTelemetry,
                    temperature=0.3,
                ),
            )
            if response and response.text:
                parsed = TurnTelemetry.model_validate_json(response.text)
                reply = sanitize_spoken_output(parsed.spoken_reply)
                LAST_TURN_TELEMETRY.update({
                    "tactic_used": parsed.tactic_selected,
                    "rep_stance": parsed.rep_stance,
                    "detected_fee": signals["highest_fee"],
                    "model_used": ACTIVE_MODEL,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                })
        except Exception as exc:
            logger.debug("Structured output fallback to standard call_gemini: %s", exc)

    if not reply:
        reply = call_gemini(prompt)

    # Apply hard deterministic fee guardrail
    reply = enforce_agent_fee_guardrail(reply, max_fee)

    CONVERSATION_HISTORY.append({
        "speaker": "Representative",
        "text": clean_speech,
    })
    CONVERSATION_HISTORY.append({
        "speaker": "Holdout AI",
        "text": reply,
    })

    return reply


def get_last_turn_telemetry() -> Dict[str, Any]:
    """Return the tactical telemetry dictionary from the most recent turn."""
    return dict(LAST_TURN_TELEMETRY)
