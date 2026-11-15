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
def _get_api_key() -> Optional[str]:
    """Fetch and sanitize GEMINI_API_KEY from environment or Streamlit Secrets."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            key = None
    if key:
        return str(key).strip().strip('"').strip("'")
    return None


def _get_ai_client() -> Optional[genai.Client]:
    """Return an initialized Gemini client."""
    key = _get_api_key()
    if not key:
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as exc:
        logger.error("Failed to initialize genai.Client: %s", exc)
        return None


ACTIVE_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

# Full multi-model failover cascade including Flash-Lite & Flash tiers
MODEL_CASCADE: List[str] = list(
    dict.fromkeys([
        ACTIVE_MODEL,
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ])
)

ai_client = _get_ai_client()

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
    "script_detected": "Auto • देवनागरी / EN",
    "model_used": ACTIVE_MODEL,
    "latency_ms": 0,
}

HINGLISH_MARKERS = {
    "mera", "meri", "mere", "aap", "aapka", "kya", "nahi", "nhi", "karna",
    "karo", "kijiye", "chahiye", "paisa", "paise", "zyada", "bahut", "bhai",
    "yaar", "kaise", "kyun", "kab", "abhi", "band", "hatana", "maaf", "batao",
    "kripya", "dhanyawad", "namaste", "haan", "achha", "theek", "sahi", "ho",
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
    return len(matches) >= 1


def get_script_instruction(user_text: str, language_pref: str = "Auto") -> str:
    """
    Build strict script enforcement instructions so TTS never spells out
    awkward Romanized Hinglish.
    """
    pref = (language_pref or "Auto").lower()
    use_hindi = (
        ("hindi" in pref and "auto" not in pref)
        or ("auto" in pref and looks_like_hinglish_or_hindi(user_text))
    )

    if use_hindi:
        return (
            "CRITICAL HINDI / VOICE SCRIPT RULE:\n"
            "- Respond in natural, conversational Indian Hindi written strictly in native DEVANAGARI script (देवनागरी).\n"
            "- NEVER write Hindi words in Roman/Latin alphabet (no Hinglish like 'Main theek hoon' or 'Kya haal hai').\n"
            "- Write common English loanwords inside Hindi sentences in Devanagari too (e.g. हेलो, होल्डआउट एआई, कैंसिल, सब्सक्रिप्शन, चार्ज, वेवर) "
            "so the neural Hindi TTS voice pronounces the entire sentence smoothly.\n"
            "- Keep the tone warm, natural, and spoken (बोलचाल की सहज हिंदी)."
        )

    return (
        "CRITICAL MULTILINGUAL / VOICE SCRIPT RULE:\n"
        "- If the user speaks or writes in English, reply in natural, fluent spoken English.\n"
        "- If the user switches to Hindi or Romanized Hinglish (like 'aap kaise ho'), ALWAYS reply in native DEVANAGARI script (देवनागरी), "
        "NEVER in Romanized Hinglish, so the voice synthesizer pronounces Hindi natively."
    )


def analyze_conversation_signals(text: str, max_fee: float) -> Dict[str, Any]:
    """
    Deterministic pre-analysis of incoming text to detect fee demands,
    retention stalls, waiver mentions, and confirmations.
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
    """Clean LLM output for TTS while preserving all Devanagari characters."""
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
    max_retries: int = 2,
    temperature: float = 0.35,
    system_instruction: Optional[str] = None,
) -> str:
    """
    Generate a response using Gemini with fast multi-model failover,
    Devanagari enforcement, and TTS output sanitization.
    """
    global ai_client
    if ai_client is None:
        ai_client = _get_ai_client()

    if ai_client is None:
        return (
            "The AI is not configured yet. "
            "Please check the GEMINI_API_KEY in your .env file or Streamlit Secrets."
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
                err_str = str(error).lower()
                logger.warning(
                    "Model '%s' attempt %d/%d failed: %s",
                    model_name,
                    attempt + 1,
                    max_retries,
                    error,
                )
                # If model is not found (404) or rate-limited (429), jump immediately to next model in cascade
                if any(code in err_str for code in ("404", "not_found", "not found", "429", "resource_exhausted", "quota")):
                    break
                if attempt < max_retries - 1:
                    time.sleep(0.4 + random.uniform(0.1, 0.3))

        logger.info("Switching to next fallback model in cascade...")

    logger.error("All Gemini models failed. Last error: %s", last_error)
    return (
        "I'm experiencing a brief connection delay on my end. "
        "Please hold for just a moment while I reconnect."
    )


# ------------------------ IVR & AGENT HELPERS ------------------------
def ask_gemini_ivr_choice(ivr_text: str, target_department: str) -> str:
    """Choose a valid menu digit (0-9) based on the IVR transcript."""
    if not (ivr_text or "").strip():
        return "0"
    answer = call_gemini(
        f"Select only the single digit (0-9) for {target_department} from: {ivr_text}",
        max_retries=1,
        temperature=0.0,
    )
    for ch in answer:
        if ch.isdigit():
            return ch
    return "0"


def ask_gemini_agent_response(agent_speech: str) -> str:
    """Generate a tactical negotiation response using MISSION_BRIEF."""
    clean_speech = (agent_speech or "").strip()
    if not clean_speech:
        return "Hello, I am on the line. Could you repeat that for me?"
    max_fee = float(MISSION_BRIEF.get("max_acceptable_fee", 0.0))
    reply = call_gemini(clean_speech)
    return enforce_agent_fee_guardrail(reply, max_fee)


def get_last_turn_telemetry() -> Dict[str, Any]:
    """Return the tactical telemetry dictionary from the most recent turn."""
    return dict(LAST_TURN_TELEMETRY)
