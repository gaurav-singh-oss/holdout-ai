import asyncio
import base64
import io
import json
import os
import re
import tempfile
import time
from typing import Optional

import streamlit as st
import streamlit.components.v1 as components

# Curated Neural Voices supporting natural Hindi (Devanagari) & Indian/Global English
VOICE_PROFILES = {
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


def _has_devanagari(text: str) -> bool:
    """Detect whether the text contains Devanagari script characters."""
    return bool(re.search(r"[\u0900-\u097F]", text or ""))


def _resolve_edge_voice(text: str, voice_profile: Optional[str] = None) -> tuple[str, str]:
    """
    Pick the optimal Edge Neural TTS voice and language code based on
    script detection (Devanagari vs. English) and user profile preference.
    """
    is_hindi = _has_devanagari(text)
    profile_key = voice_profile or st.session_state.get(
        "voice_profile", "Auto (Smart Hindi देवनागरी + English)"
    )
    profile = VOICE_PROFILES.get(
        profile_key, VOICE_PROFILES["Auto (Smart Hindi देवनागरी + English)"]
    )
    selected_voice = profile["hi"] if is_hindi else profile["en"]
    lang_code = "hi-IN" if is_hindi else "en-IN"
    return selected_voice, lang_code


def _synthesize_edge_tts(text: str, voice: str = "hi-IN-SwaraNeural") -> tuple[bytes, str]:
    """Tier 1: Microsoft Edge Neural TTS (in-memory MP3 bytes)."""
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate="+2%")
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])
        return buffer.getvalue()

    loop = asyncio.new_event_loop()
    try:
        audio_bytes = loop.run_until_complete(_run())
    finally:
        loop.close()

    if not audio_bytes:
        raise RuntimeError("edge-tts returned empty audio stream.")
    return audio_bytes, "audio/mp3"


def _synthesize_gtts(text: str, is_hindi: bool = False) -> tuple[bytes, str]:
    """Tier 2: Google Text-to-Speech (automatically switches to 'hi' for Devanagari)."""
    from gtts import gTTS

    buffer = io.BytesIO()
    tts = gTTS(
        text=text,
        lang="hi" if is_hindi else "en",
        tld="co.in",
        slow=False,
    )
    tts.write_to_fp(buffer)
    audio_bytes = buffer.getvalue()
    if not audio_bytes:
        raise RuntimeError("gTTS returned empty audio stream.")
    return audio_bytes, "audio/mp3"


def _synthesize_pyttsx3(text: str) -> tuple[bytes, str]:
    """Tier 3: Offline pyttsx3 rendered to WAV bytes for browser playback."""
    import pyttsx3

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 172)
        engine.save_to_file(text, tmp_path)
        engine.runAndWait()
        engine.stop()

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise RuntimeError("pyttsx3 failed to write WAV file.")

        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes, "audio/wav"
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def speak_text(text: str, voice_profile: Optional[str] = None) -> None:
    """
    Synthesize speech with automatic Devanagari Hindi detection and queue it
    in st.session_state for fluid browser playback.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return

    is_hindi = _has_devanagari(clean_text)
    edge_voice, lang_code = _resolve_edge_voice(clean_text, voice_profile)

    generators = [
        (f"Neural ({edge_voice.replace('Neural', '')})", lambda t: _synthesize_edge_tts(t, voice=edge_voice)),
        (f"Google TTS ({'Hindi' if is_hindi else 'Indian EN'})", lambda t: _synthesize_gtts(t, is_hindi=is_hindi)),
        ("Offline Voice", _synthesize_pyttsx3),
    ]

    audio_b64 = ""
    mime_type = "audio/mp3"
    engine_used = f"Browser Speech ({lang_code})"

    for engine_name, generator in generators:
        try:
            audio_bytes, mime_type = generator(clean_text)
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            engine_used = engine_name
            break
        except Exception:
            continue

    st.session_state["audio_payload"] = {
        "id": f"turn_{int(time.time() * 1000)}",
        "text": clean_text,
        "b64": audio_b64,
        "mime": mime_type,
        "engine": engine_used,
        "lang": lang_code,
        "script": "देवनागरी • Hindi" if is_hindi else "Latin • English",
        "autoplay": True,
    }


def render_audio_visualizer(voice_enabled: bool = True) -> None:
    """
    Render a fluid, organic 60FPS Silk-Wave & Breathing Orb Audio Stage
    with spring-damped motion, Web Audio API analysis, and live mic monitoring.
    """
    payload = st.session_state.get(
        "audio_payload",
        {
            "id": "idle",
            "text": "",
            "b64": "",
            "mime": "audio/mp3",
            "engine": "Ready",
            "lang": "en-IN",
            "script": "Auto • देवनागरी / EN",
            "autoplay": False,
        },
    )

    should_autoplay = bool(voice_enabled and payload.get("autoplay", False))
    if "audio_payload" in st.session_state and st.session_state["audio_payload"].get("autoplay"):
        st.session_state["audio_payload"]["autoplay"] = False

    safe_text_json = json.dumps(payload.get("text", ""))
    b64_data = payload.get("b64", "")
    mime_type = payload.get("mime", "audio/mp3")
    lang_code = payload.get("lang", "en-IN")
    engine_label = payload.get("engine", "Ready") if voice_enabled else "Voice Muted"
    script_label = payload.get("script", "Auto • देवनागरी / EN")
    turn_id = payload.get("id", "idle")

    visualizer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap');
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: transparent;
          font-family: 'Plus Jakarta Sans', sans-serif;
          color: #f8fafc;
          overflow: hidden;
        }}
        .stage {{
          position: relative;
          background: linear-gradient(145deg, rgba(17, 24, 43, 0.86), rgba(11, 16, 30, 0.94));
          border: 1px solid rgba(148, 163, 184, 0.16);
          border-radius: 22px;
          padding: 16px 20px;
          box-shadow: 0 20px 45px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.08);
          backdrop-filter: blur(20px);
          transition: border-color 0.4s ease, box-shadow 0.4s ease;
        }}
        .stage.speaking {{
          border-color: rgba(56, 189, 248, 0.45);
          box-shadow: 0 20px 50px rgba(14, 165, 233, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.12);
        }}
        .stage.listening {{
          border-color: rgba(167, 139, 250, 0.5);
          box-shadow: 0 20px 50px rgba(139, 92, 246, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.12);
        }}
        .stage-top {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
          gap: 12px;
          flex-wrap: wrap;
        }}
        .status-cluster {{
          display: flex;
          align-items: center;
          gap: 10px;
        }}
        .orb {{
          width: 11px;
          height: 11px;
          border-radius: 50%;
          background: linear-gradient(135deg, #64748b, #475569);
          transition: all 0.4s cubic-bezier(0.22, 1, 0.36, 1);
        }}
        .orb.active {{
          background: linear-gradient(135deg, #34d399, #38bdf8);
          box-shadow: 0 0 14px rgba(52, 211, 153, 0.75);
          transform: scale(1.15);
        }}
        .orb.mic {{
          background: linear-gradient(135deg, #a78bfa, #f472b6);
          box-shadow: 0 0 14px rgba(167, 139, 250, 0.8);
          transform: scale(1.15);
        }}
        .status-title {{
          font-family: 'Outfit', sans-serif;
          font-size: 13.5px;
          font-weight: 600;
          color: #e2e8f0;
          letter-spacing: 0.2px;
        }}
        .script-badge {{
          font-size: 11px;
          font-weight: 500;
          padding: 3px 10px;
          border-radius: 999px;
          background: rgba(56, 189, 248, 0.12);
          border: 1px solid rgba(56, 189, 248, 0.25);
          color: #7dd3fc;
        }}
        .controls {{
          display: flex;
          align-items: center;
          gap: 8px;
        }}
        .btn {{
          font-family: 'Plus Jakarta Sans', sans-serif;
          font-size: 11.5px;
          font-weight: 600;
          padding: 6px 13px;
          border-radius: 999px;
          border: 1px solid rgba(148, 163, 184, 0.22);
          background: rgba(30, 41, 59, 0.65);
          color: #e2e8f0;
          cursor: pointer;
          transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
        }}
        .btn:hover {{
          border-color: rgba(56, 189, 248, 0.5);
          background: rgba(56, 189, 248, 0.18);
          color: #ffffff;
          transform: translateY(-1px);
        }}
        .btn.active-mic {{
          border-color: rgba(167, 139, 250, 0.65);
          background: rgba(139, 92, 246, 0.24);
          color: #ddd6fe;
        }}
        .canvas-container {{
          position: relative;
          width: 100%;
          height: 96px;
          background: radial-gradient(circle at 50% 50%, rgba(15, 23, 42, 0.55), rgba(6, 10, 21, 0.85));
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 16px;
          overflow: hidden;
        }}
        canvas {{
          width: 100%;
          height: 100%;
          display: block;
        }}
        .stage-footer {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 9px;
          font-size: 11.5px;
          color: #94a3b8;
        }}
        .stage-footer strong {{
          color: #cbd5e1;
          font-weight: 600;
        }}
      </style>
    </head>
    <body>
      <div id="stageCard" class="stage" data-turn="{turn_id}">
        <div class="stage-top">
          <div class="status-cluster">
            <span id="statusOrb" class="orb"></span>
            <span id="statusText" class="status-title">Voice Studio Ready</span>
            <span class="script-badge">{script_label}</span>
          </div>
          <div class="controls">
            <button id="replayBtn" class="btn" title="Replay latest AI voice response">▶ Replay Voice</button>
            <button id="micToggleBtn" class="btn" title="Visualize your live microphone wave">🎙️ Live Mic Wave</button>
          </div>
        </div>
        <div class="canvas-container">
          <canvas id="silkCanvas"></canvas>
        </div>
        <div class="stage-footer">
          <span>Synthesizer: <strong>{engine_label}</strong></span>
          <span id="energyLabel">Ambient Flow</span>
        </div>
        <audio id="ttsAudio" crossorigin="anonymous" style="display:none;"></audio>
      </div>

      <script>
        (function() {{
          const b64Audio = "{b64_data}";
          const mimeType = "{mime_type}";
          const fallbackText = {safe_text_json};
          const fallbackLang = "{lang_code}";
          const shouldAutoplay = {"true" if should_autoplay else "false"};

          const stageCard = document.getElementById("stageCard");
          const canvas = document.getElementById("silkCanvas");
          const ctx = canvas.getContext("2d");
          const audioEl = document.getElementById("ttsAudio");
          const statusOrb = document.getElementById("statusOrb");
          const statusText = document.getElementById("statusText");
          const energyLabel = document.getElementById("energyLabel");
          const replayBtn = document.getElementById("replayBtn");
          const micToggleBtn = document.getElementById("micToggleBtn");

          let audioCtx = null;
          let analyser = null;
          let mediaSource = null;
          let micStream = null;
          let micSource = null;
          let isMicActive = false;
          let isSyntheticSpeaking = false;

          // Smooth spring-damped state variables for fluid motion
          let phase = 0;
          let smoothEnergy = 0.06;
          let smoothBass = 0.05;
          let smoothTreble = 0.05;

          function resizeCanvas() {{
            const dpr = window.devicePixelRatio || 1;
            canvas.width = canvas.clientWidth * dpr;
            canvas.height = canvas.clientHeight * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          }}
          window.addEventListener("resize", resizeCanvas);
          resizeCanvas();

          function ensureAudioContext() {{
            if (!audioCtx) {{
              const AudioContextClass = window.AudioContext || window.webkitAudioContext;
              audioCtx = new AudioContextClass();
              analyser = audioCtx.createAnalyser();
              analyser.fftSize = 256;
              analyser.smoothingTimeConstant = 0.88;
            }}
            if (audioCtx.state === "suspended") {{
              audioCtx.resume();
            }}
          }}

          function playTtsAudio() {{
            if (b64Audio && b64Audio.length > 0) {{
              try {{
                ensureAudioContext();
                audioEl.src = "data:" + mimeType + ";base64," + b64Audio;
                if (!mediaSource) {{
                  mediaSource = audioCtx.createMediaElementSource(audioEl);
                  mediaSource.connect(analyser);
                  analyser.connect(audioCtx.destination);
                }}
                audioEl.currentTime = 0;
                audioEl.play().then(() => {{
                  statusOrb.className = "orb active";
                  stageCard.className = "stage speaking";
                  statusText.textContent = "Speaking Aloud...";
                }}).catch(() => {{
                  statusText.textContent = "Ready · Click Replay to Unmute";
                }});
              }} catch (err) {{
                speakWithWebSpeech();
              }}
            }} else if (fallbackText && fallbackText.trim().length > 0) {{
              speakWithWebSpeech();
            }}
          }}

          function speakWithWebSpeech() {{
            if (!("speechSynthesis" in window) || !fallbackText) return;
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(fallbackText);
            utter.lang = fallbackLang || "hi-IN";
            utter.rate = 1.0;
            utter.onstart = () => {{
              isSyntheticSpeaking = true;
              statusOrb.className = "orb active";
              stageCard.className = "stage speaking";
              statusText.textContent = "Speaking Aloud...";
            }};
            utter.onend = () => {{
              isSyntheticSpeaking = false;
              if (!isMicActive) {{
                statusOrb.className = "orb";
                stageCard.className = "stage";
                statusText.textContent = "Voice Studio Ready";
                energyLabel.textContent = "Ambient Flow";
              }}
            }};
            window.speechSynthesis.speak(utter);
          }}

          audioEl.addEventListener("ended", () => {{
            if (!isMicActive) {{
              statusOrb.className = "orb";
              stageCard.className = "stage";
              statusText.textContent = "Voice Studio Ready";
              energyLabel.textContent = "Ambient Flow";
            }}
          }});

          replayBtn.addEventListener("click", () => {{
            playTtsAudio();
          }});

          micToggleBtn.addEventListener("click", async () => {{
            if (isMicActive) {{
              if (micStream) micStream.getTracks().forEach(t => t.stop());
              if (micSource) {{
                try {{ micSource.disconnect(); }} catch (e) {{}}
              }}
              isMicActive = false;
              micToggleBtn.classList.remove("active-mic");
              micToggleBtn.textContent = "🎙️ Live Mic Wave";
              statusOrb.className = "orb";
              stageCard.className = "stage";
              statusText.textContent = "Voice Studio Ready";
              energyLabel.textContent = "Ambient Flow";
              return;
            }}
            try {{
              ensureAudioContext();
              micStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
              micSource = audioCtx.createMediaStreamSource(micStream);
              micSource.connect(analyser);
              isMicActive = true;
              micToggleBtn.classList.add("active-mic");
              micToggleBtn.textContent = "⏹️ Stop Mic Wave";
              statusOrb.className = "orb mic";
              stageCard.className = "stage listening";
              statusText.textContent = "Listening to Microphone...";
            }} catch (err) {{
              statusText.textContent = "Microphone Permission Needed";
            }}
          }});

          function drawSilkRibbon(width, height, midY, amp, freq, phaseOffset, colorStart, colorEnd, fillAlpha) {{
            ctx.beginPath();
            const grad = ctx.createLinearGradient(0, 0, width, 0);
            grad.addColorStop(0, "rgba(0,0,0,0)");
            grad.addColorStop(0.15, colorStart);
            grad.addColorStop(0.85, colorEnd);
            grad.addColorStop(1, "rgba(0,0,0,0)");

            const step = 6;
            for (let x = 0; x <= width; x += step) {{
              const normX = x / width;
              // Smooth bell-curve envelope so wave tapers gracefully at both edges
              const envelope = Math.sin(normX * Math.PI);
              const wave1 = Math.sin(normX * freq + phase + phaseOffset);
              const wave2 = Math.cos(normX * (freq * 0.6) - phase * 0.75 + phaseOffset);
              const y = midY + (wave1 * 0.65 + wave2 * 0.35) * amp * envelope;
              if (x === 0) ctx.moveTo(x, y);
              else ctx.lineTo(x, y);
            }}

            ctx.strokeStyle = grad;
            ctx.lineWidth = 2.4;
            ctx.stroke();

            // Soft glowing fill back to center line
            ctx.lineTo(width, midY);
            ctx.lineTo(0, midY);
            ctx.closePath();
            ctx.fillStyle = fillAlpha;
            ctx.fill();
          }}

          function renderFrame() {{
            requestAnimationFrame(renderFrame);
            const width = canvas.clientWidth;
            const height = canvas.clientHeight;
            const midY = height / 2;

            ctx.clearRect(0, 0, width, height);

            let targetEnergy = 0.08;
            let targetBass = 0.08;
            let targetTreble = 0.08;

            const isAudioPlaying = !audioEl.paused && !audioEl.ended && audioEl.currentTime > 0;

            if (analyser && (isAudioPlaying || isMicActive)) {{
              const binCount = analyser.frequencyBinCount;
              const freqData = new Uint8Array(binCount);
              analyser.getByteFrequencyData(freqData);

              let sum = 0, bassSum = 0, trebleSum = 0;
              const bassLimit = Math.floor(binCount * 0.25);
              for (let i = 0; i < binCount; i++) {{
                const v = freqData[i] / 255.0;
                sum += v;
                if (i < bassLimit) bassSum += v;
                else trebleSum += v;
              }}
              targetEnergy = Math.min(1.0, (sum / binCount) * 2.4);
              targetBass = Math.min(1.0, (bassSum / Math.max(1, bassLimit)) * 1.8);
              targetTreble = Math.min(1.0, (trebleSum / Math.max(1, binCount - bassLimit)) * 2.6);
            }} else if (isSyntheticSpeaking) {{
              targetEnergy = 0.45 + 0.28 * Math.sin(phase * 2.3) * Math.cos(phase * 1.4);
              targetBass = 0.5 + 0.25 * Math.sin(phase * 1.8);
              targetTreble = 0.4 + 0.25 * Math.cos(phase * 2.9);
            }}

            // Spring-like linear interpolation for silky 60fps transitions
            smoothEnergy += (targetEnergy - smoothEnergy) * 0.14;
            smoothBass += (targetBass - smoothBass) * 0.12;
            smoothTreble += (targetTreble - smoothTreble) * 0.16;

            const maxWaveHeight = height * 0.44;
            const primaryAmp = Math.max(4, smoothEnergy * maxWaveHeight);
            const secondaryAmp = Math.max(3, smoothBass * maxWaveHeight * 0.82);
            const tertiaryAmp = Math.max(2.5, smoothTreble * maxWaveHeight * 0.68);

            if (isMicActive) {{
              drawSilkRibbon(width, height, midY, secondaryAmp, 8.5, 2.1, "rgba(244, 114, 182, 0.55)", "rgba(167, 139, 250, 0.55)", "rgba(244, 114, 182, 0.05)");
              drawSilkRibbon(width, height, midY, tertiaryAmp, 12.0, 4.2, "rgba(56, 189, 248, 0.6)", "rgba(129, 140, 248, 0.6)", "rgba(56, 189, 248, 0.05)");
              drawSilkRibbon(width, height, midY, primaryAmp, 6.5, 0.0, "rgba(167, 139, 250, 0.95)", "rgba(244, 114, 182, 0.95)", "rgba(167, 139, 250, 0.09)");
              energyLabel.textContent = "Live Input Resonance · " + Math.round(smoothEnergy * 100) + "%";
            }} else {{
              drawSilkRibbon(width, height, midY, secondaryAmp, 7.5, 1.8, "rgba(99, 102, 241, 0.5)", "rgba(56, 189, 248, 0.5)", "rgba(99, 102, 241, 0.04)");
              drawSilkRibbon(width, height, midY, tertiaryAmp, 11.0, 3.6, "rgba(52, 211, 153, 0.55)", "rgba(45, 212, 191, 0.55)", "rgba(52, 211, 153, 0.04)");
              drawSilkRibbon(width, height, midY, primaryAmp, 6.0, 0.0, "rgba(56, 189, 248, 0.95)", "rgba(52, 211, 153, 0.95)", "rgba(56, 189, 248, 0.08)");
              if (isAudioPlaying || isSyntheticSpeaking) {{
                energyLabel.textContent = "Voice Resonance · " + Math.round(smoothEnergy * 100) + "%";
              }}
            }}

            phase += 0.045 + smoothEnergy * 0.055;
          }}

          renderFrame();

          if (shouldAutoplay) {{
            setTimeout(playTtsAudio, 110);
          }}
        }})();
      </script>
    </body>
    </html>
    """
    components.html(visualizer_html, height=192, scrolling=False)
