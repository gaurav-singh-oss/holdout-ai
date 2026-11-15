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

if not API_KEY:
    try:
        import streamlit as st
        API_KEY = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        API_KEY = None

ACTIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

MODEL_CASCADE: List[str] = list(
    dict.fromkeys([
        ACTIVE_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ])
)

ai_client = genai.Client(api_key=API_KEY) if API_KEY else None

MISSION_BRIEF: Dict[str, Any] = {
    "goal": "Cancel internet subscription and refuse early termination fees.",
    "target_department": "Billing or Cancellations",
    "customer_name": "Kumar",
    "max_acceptable_fee": 0.0,
    "language_preference": "Auto (Match User — Hindi in देवनागरी)",
}

CONVERSATION_HISTORY: List[Dict[str, str]] = []

LAST_TURN_TELEMETRY: Dict[str, Any] = {
    "tactic_used": "Standby",
    "rep_stance": "Neutral",
    "detected_fee": None,
    "script_detected": "English",
    "model_used": ACTIVE_MODEL,
    "latency_ms": 0,
}

# Common Roman Hinglish markers to detect when a user types in Hinglish
HINGLISH_MARKERS = {
    "mera", "meri", "mere", "aap", "aapka", "kya", "nahi", "nhi", "karna",
    "karo", "kijiye", "chahiye", "paisa", "paise", "zyada", "bahut", "bhai",
    "yaar", "kaise", "kyun", "kab", "abhi", "band", "hatana", "maaf", "batao",
    "kripya", "dhanyawad", "namaste", "haan", "achha", "theek", "sahi",
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
        description="Exact natural spoken response to say aloud. If speaking Hindi, MUST be written in native Devanagari script (देवनागरी), never Roman Hinglish."
    )


# ---------------------- LANGUAGE & SIGNAL ENGINE ---------------------
def contains_devanagari(text: str) -> bool:
    """Return True if the text contains Devanagari characters."""
    return bool(re.search(r"[\u0900-\u097F]", text or ""))


def looks_like_hinglish_or_hindi(text: str) -> bool:
    """Detect if user input is in Devanagari Hindi or Romanized Hinglish."""
    if not text:
        return False
    if contains_devanagari(text):
        return True
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    matches = words.intersection(HINGLISH_MARKERS)
    return len(matches) >= 2


def get_script_instruction(user_text: str, language_pref: str = "Auto") -> str:
    """
    Build strict script enforcement instructions so TTS never spells out
    awkward Romanized Hinglish.
    """
    pref = (language_pref or "Auto").lower()
    use_hindi = (
        "hindi" in pref
        or "देवनागरी" in pref
        and "auto" not in pref
        or ("auto" in pref and looks_like_hinglish_or_hindi(user_text))
    )

    if use_hindi:
        return (
            "CRITICAL HINDI / VOICE SCRIPT RULE:\n"
            "- Respond in natural, conversational Indian Hindi written strictly in native DEVANAGARI script (देवनागरी).\n"
            "- NEVER write Hindi words in Roman/Latin alphabet (no Hinglish like 'Main aapki madad karunga' or 'Kya haal hai').\n"
            "- Even common English loanwords used inside a Hindi sentence (like कैंसिल, सब्सक्रिप्शन, चार्ज, वेवर, अकाउंट, कन्फर्मेशन) "
            "should be written in Devanagari so the neural Hindi TTS voice pronounces the entire sentence with seamless flow.\n"
            "- Keep the tone warm, natural, and spoken (बोलचाल की सहज हिंदी), avoiding stiff or overly archaic vocabulary."
        )

    return (
        "CRITICAL MULTILINGUAL / VOICE SCRIPT RULE:\n"
        "- If the user speaks or writes in English, reply in natural, fluent spoken English.\n"
        "- If the user switches to Hindi or Romanized Hinglish, ALWAYS reply in native DEVANAGARI script (देवनागरी), "
        "NEVER in Romanized Hinglish, so the voice synthesizer pronounces Hindi natively."
    )


def analyze_conversation_signals(text: str, max_fee: float) -> Dict[str, Any]:
    """
    Deterministic pre-analysis of incoming text to detect fee demands,
    retention stalls, waiver mentions, and confirmations (supports English & Hindi).
    """
    lower = (text or "").lower()
    fee_pattern = (
        r"(?:\$|₹|rs\.?|inr)\s*(\d+(?:\.\d{1,2})?)"
        r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|rupees?|inr|रुपये|डॉलर)\b"
    )
    matches = re.findall(fee_pattern, lower, flags=re.IGNORECASE)
    amounts = [float(a or b) for a, b in matches]

    fee_keywords = (
        "fee", "charge", "payment", "pay", "termination", "cancellation", "penalty", "cost",
        "फीस", "चार्ज", "पेमेंट", "भुगतान", "पेनल्टी", "शुल्क", "extra",
    )
    has_fee_context = any(k in lower for k in fee_keywords)
    highest_fee = max(amounts) if (has_fee_context and amounts) else None
    over_limit = highest_fee is not None and highest_fee > float(max_fee)

    if any(
        p in lower
        for p in (
            "waived", "no cancellation fee", "zero fee", "cancelled", "canceled",
            "माफ़", "माफ", "वेव", "कैंसिल कर दिया", "कोई चार्ज नहीं", "जीरो फीस",
        )
    ):
        rep_stance = "Confirming / Cooperative"
        recommended_tactic = "Confirmation Lock-In (Request reference number & verify $0 balance)"
    elif over_limit:
        rep_stance = f"Demanding Over-Limit Fee (${highest_fee:.2f})"
        recommended_tactic = (
            "Tactical Empathy + Hard Refusal (Acknowledge their system prompt, firmly refuse the fee, "
            "and ask for a courtesy loyalty waiver, billing pause, or retention supervisor)"
        )
    elif any(
        k in lower
        for k in (
            "discount", "promo", "lower rate", "keep your service", "stay with us",
            "डिस्काउंट", "ऑफर", "कम प्लान",
        )
    ):
        rep_stance = "Retention Pitching"
        recommended_tactic = "Polite Pivot (Decline retention upsell and redirect back to full cancellation + waiver)"
    elif any(
        k in lower
        for k in (
            "policy", "mandatory", "contract", "cannot waive", "can't waive",
            "पॉलिसी", "नियम", "माफ़ नहीं",
        )
    ):
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
    - Strips markdown symbols (*, #, `) and bracketed stage directions
    - Preserves all Devanagari characters and matras intact
    """
    if not text:
        return ""

    cleaned = text.strip()
    cleaned = re.sub(
        r"^(?:holdout\s*ai|assistant|agent|ai|response|उत्तर|एजेंट)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\*[^*]+\*", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "").replace("#", "")

    if len(cleaned) >= 2 and cleaned[0] in ('"', "“", "'") and cleaned[-1] in ('"', "”", "'"):
        cleaned = cleaned[1:-1].strip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def enforce_agent_fee_guardrail(reply: str, max_fee: float) -> str:
    """Ensure the AI never accidentally agrees to pay an unauthorized fee."""
    lower = reply.lower()
    agreement_phrases = (
        "i agree to pay",
        "i will pay the",
        "go ahead and charge",
        "you can charge the",
        "i accept the fee",
        "i'll pay the",
        "मैं फीस देने के लिए तैयार",
        "आप चार्ज कर सकते हैं",
    )
    if any(phrase in lower for phrase in agreement_phrases):
        is_hindi = contains_devanagari(reply)
        fee_pattern = (
            r"(?:\$|₹|rs\.?)\s*(\d+(?:\.\d{1,2})?)"
            r"|\b(\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|rupees?)\b"
        )
        matches = re.findall(fee_pattern, lower, flags=re.IGNORECASE)
        amounts = [float(a or b) for a, b in matches]

        if (not amounts and max_fee == 0) or any(amt > float(max_fee) for amt in amounts):
            if is_hindi:
                return (
                    f"मुझे ${float(max_fee):.2f} से अधिक किसी भी कैंसिलेशन चार्ज को मंज़ूर करने की अनुमति नहीं है। "
                    "कृपया चेक करें कि क्या लॉयल्टी वेवर मिल सकता है या किसी सीनियर स्पेशलिस्ट से बात हो सकती है।"
                )
            return (
                f"I am not authorized to approve any fee above ${float(max_fee):.2f}. "
                "Could you check if a courtesy loyalty waiver applies, or connect me with a specialist who can waive that charge?"
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
    exponential backoff + jitter, Devanagari enforcement, and TTS sanitization.
    """
    if ai_client is None:
        return (
            "The AI is not configured yet. "
            "Please check the GEMINI_API_KEY in your .env file."
        )

    start_time = time.perf_counter()

    max_fee = float(MISSION_BRIEF.get("max_acceptable_fee", 0.0))
    lang_pref = str(MISSION_BRIEF.get("language_preference", "Auto"))
    signals = analyze_conversation_signals(prompt, max_fee)
    script_rule = get_script_instruction(prompt, lang_pref)

    default_sys_instruction = (
        "You are Holdout AI, an elite voice-first negotiation and conversation assistant. "
        "Speak naturally, warmly, and concisely in plain spoken language suitable for "
        "real-time text-to-speech playback. Never use markdown, bullet points, or stage directions.\n\n"
        f"{script_rule}"
    )
    active_sys_instruction = system_instruction or default_sys_instruction

    config = types.GenerateContentConfig(
        system_instruction=active_sys_instruction,
        temperature=temperature,
        top_p=0.9,
        max_output_tokens=320,
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
                        "script_detected": "देवनागरी (Hindi)" if contains_devanagari(cleaned_answer) else "English",
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
    """Fast regex pattern matcher for standard IVR menus."""
    target_words = [
        w.lower()
        for w in re.split(r"\W+", target_department or "")
        if len(w) > 2 and w.lower() not in ("and", "the", "for")
    ]
    if not target_words:
        target_words = ["cancel", "billing", "retention", "support", "representative", "agent"]

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
    lang_pref = str(MISSION_BRIEF.get("language_preference", "Auto"))
    signals = analyze_conversation_signals(clean_speech, max_fee)
    script_rule = get_script_instruction(clean_speech, lang_pref)

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

{script_rule}

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
                    "script_detected": "देवनागरी (Hindi)" if contains_devanagari(reply) else "English",
                    "model_used": ACTIVE_MODEL,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                })
        except Exception as exc:
            logger.debug("Structured output fallback to standard call_gemini: %s", exc)

    if not reply:
        reply = call_gemini(prompt)

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
