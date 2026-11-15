import asyncio
import json
import streamlit as st
import websockets
from agent import (
    MISSION_BRIEF,
    ask_gemini_agent_response,
    ask_gemini_ivr_choice,
)
from speaker import speak_text

st.set_page_config(
    page_title="Holdout AI - Mission Control",
    layout="wide",
)

st.title("🛡️ Holdout AI: Autonomous Voice Agent")
st.caption("AI-Powered Support Line Navigation & Negotiation")

# Sidebar Configuration
with st.sidebar:
    st.header("📋 Mission Briefing")
    customer_name = st.text_input("Customer Name", value="Kumar")
    target_dept = st.text_input(
        "Target Department", value="Billing or Cancellations"
    )
    mission_goal = st.text_area(
        "Mission Goal",
        value=(
            "Cancel internet subscription and refuse to pay any early"
            " termination fees."
        ),
    )
    max_fee = st.number_input(
        "Max Acceptable Fee ($)",
        min_value=0,
        value=0,
    )
    enable_voice = st.checkbox(
        "Enable Local Voice Output",
        value=True,
    )
    start_button = st.button(
        "🚀 Launch Autonomous Mission",
        use_container_width=True,
    )

st.subheader("📡 Live Call Monitor")
status_placeholder = st.empty()
feed_container = st.container()


def log_message(label, message):
    feed_container.markdown(f"**{label}**: *\"{message}\"*")


def assess_outcome(transcript, maximum_fee):
    """Conservative assessment based on explicit statements in the simulated conversation."""
    text = " ".join(transcript).lower()
    cancellation_confirmed = any(
        phrase in text
        for phrase in (
            "cancellation is confirmed",
            "subscription has been cancelled",
            "subscription has been canceled",
            "service has been cancelled",
            "service has been canceled",
        )
    )
    fee_waived = any(
        phrase in text
        for phrase in (
            "fee has been waived",
            "fee is waived",
            "no early termination fee",
            "no cancellation fee",
            "final fee is $0",
            "final fee: $0",
            "zero cancellation fee",
        )
    )

    if cancellation_confirmed and fee_waived and maximum_fee == 0:
        return (
            "Both cancellation and the fee waiver were explicitly stated in"
            " the conversation. External verification is still required."
        )
    if cancellation_confirmed and fee_waived:
        return (
            "Both goals appear to have been confirmed in the conversation."
            " Verify the final charges independently."
        )
    if cancellation_confirmed:
        return (
            "Cancellation appears to be confirmed, but the fee waiver has"
            " not been explicitly confirmed."
        )
    if fee_waived:
        return (
            "The fee waiver appears to be confirmed, but cancellation has"
            " not been explicitly confirmed."
        )
    return (
        "Outcome unverified. The conversation does not explicitly confirm"
        " both cancellation and the fee waiver."
    )


async def execute_mission():
    uri = "ws://127.0.0.1:8000/call-stream"
    transcript = []
    representative_turns = 0
    max_turns = 8

    # Dynamic Mission Config Assignment
    MISSION_BRIEF["customer_name"] = customer_name
    MISSION_BRIEF["target_department"] = target_dept
    MISSION_BRIEF["goal"] = mission_goal
    MISSION_BRIEF["max_acceptable_fee"] = max_fee

    status_placeholder.info("🔄 Connecting to simulated call centre...")

    try:
        async with websockets.connect(uri, open_timeout=10) as ws:
            status_placeholder.success("🟢 Connected to simulated call centre")

            while representative_turns < max_turns:
                raw_data = await ws.recv()
                event = json.loads(raw_data)

                # 1. IVR Navigation Menu Handling
                if event.get("sender") == "IVR":
                    text = event.get("text", "")
                    transcript.append(f"IVR: {text}")
                    log_message("📞 IVR Voice", text)

                    if "press" in text.lower():
                        status_placeholder.info(
                            "🧠 Gemini is analysing the phone menu..."
                        )
                        key = ask_gemini_ivr_choice(text, target_dept)
                        if not key.isdigit():
                            key = "0"
                        feed_container.markdown(
                            f"👉 **Holdout AI Action:** Selected DTMF digit"
                            f" `[{key}]`"
                        )
                        await ws.send(key)

                # 2. Hold Music Handling
                elif event.get("event") == "HOLD_MUSIC":
                    sound = event.get("sound", "Hold music")
                    status_placeholder.warning(
                        "⏳ Waiting in the simulated queue..."
                    )
                    feed_container.caption(f"🎶 {sound}")

                # 3. Live Support Agent Negotiation
                elif event.get("sender") == "HUMAN_AGENT":
                    agent_speech = event.get("text", "")
                    transcript.append(f"Representative: {agent_speech}")
                    representative_turns += 1

                    log_message("👤 Call Centre Agent", agent_speech)
                    status_placeholder.info(
                        f"🧠 Preparing negotiation response (turn"
                        f" {representative_turns})..."
                    )

                    bot_reply = ask_gemini_agent_response(agent_speech)
                    transcript.append(f"Holdout AI: {bot_reply}")
                    log_message("🤖 Holdout AI", bot_reply)

                    if enable_voice:
                        speak_text(bot_reply)

                    await ws.send(bot_reply)

            status_placeholder.warning(
                "Maximum conversation turns reached. The outcome has not been"
                " independently verified."
            )

    except websockets.exceptions.ConnectionClosed:
        status_placeholder.info(
            "The simulated call ended. Checking the conversation for explicit"
            " outcome statements..."
        )
    except Exception as error:
        status_placeholder.error(
            f"Call stream error: {type(error).__name__}: {error}"
        )
        st.error(
            "Check that call_center_mock.py is running and that the virtual"
            " environment has the required packages."
        )
        return

    # Post-Call Evaluation Report UI
    outcome = assess_outcome(transcript, max_fee)
    st.subheader("📋 Mission Outcome")
    st.info(outcome)

    with st.expander("View conversation transcript"):
        for entry in transcript:
            st.write(entry)

    st.caption(
        "Demo mode: conversation text is simulated. This dashboard does not"
        " independently verify real account changes or place actual telephone"
        " calls."
    )


if start_button:
    # Safely handles Streamlit's event loop environment
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Fallback tasks scheduler if execution loop exists
        loop.create_task(execute_mission())
    else:
        asyncio.run(execute_mission())