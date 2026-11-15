import asyncio
import base64
import io
import os
import tempfile
import time
import json
import streamlit as st
import streamlit.components.v1 as components


def _synthesize_edge_tts(text: str, voice: str = "en-US-AriaNeural") -> tuple[bytes, str]:
    """Tier 1: Microsoft Edge Neural TTS (in-memory MP3 bytes)."""
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
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


def _synthesize_gtts(text: str) -> tuple[bytes, str]:
    """Tier 2: Google Text-to-Speech (in-memory MP3 bytes)."""
    from gtts import gTTS

    buffer = io.BytesIO()
    tts = gTTS(text=text, lang="en", slow=False)
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
        engine.setProperty("rate", 175)
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


def speak_text(text: str) -> None:
    """
    Synthesize speech and queue it in st.session_state so it plays smoothly
    inside the Streamlit browser after st.rerun() completes.
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return

    generators = [
        ("Edge Neural TTS", _synthesize_edge_tts),
        ("Google TTS", _synthesize_gtts),
        ("Offline pyttsx3", _synthesize_pyttsx3),
    ]

    audio_b64 = ""
    mime_type = "audio/mp3"
    engine_used = "Browser Web Speech API"

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
        "autoplay": True,
    }


def render_audio_visualizer(voice_enabled: bool = True) -> None:
    """
    Render an interactive 60FPS Web Audio API Waveform & Spectrum Visualizer
    that automatically plays queued TTS responses and optionally monitors the user's mic.
    """
    payload = st.session_state.get(
        "audio_payload",
        {
            "id": "idle",
            "text": "",
            "b64": "",
            "mime": "audio/mp3",
            "engine": "Standby",
            "autoplay": False,
        },
    )

    should_autoplay = bool(voice_enabled and payload.get("autoplay", False))
    # Consume the autoplay flag so subsequent UI interactions don't replay old audio
    if "audio_payload" in st.session_state and st.session_state["audio_payload"].get("autoplay"):
        st.session_state["audio_payload"]["autoplay"] = False

    safe_text_json = json.dumps(payload.get("text", ""))
    b64_data = payload.get("b64", "")
    mime_type = payload.get("mime", "audio/mp3")
    engine_label = payload.get("engine", "Standby") if voice_enabled else "Muted"
    turn_id = payload.get("id", "idle")

    visualizer_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;600&family=Plus+Jakarta+Sans:wght@500;600;700&display=swap');
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          background: transparent;
          font-family: 'Plus Jakarta Sans', sans-serif;
          color: #f8fafc;
          overflow: hidden;
        }}
        .deck {{
          background: linear-gradient(135deg, rgba(12, 21, 39, 0.92), rgba(8, 14, 28, 0.96));
          border: 1px solid rgba(56, 189, 248, 0.28);
          border-radius: 16px;
          padding: 14px 18px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
        }}
        .deck-header {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
          gap: 10px;
          flex-wrap: wrap;
        }}
        .deck-title {{
          display: flex;
          align-items: center;
          gap: 9px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 11px;
          letter-spacing: 1.4px;
          text-transform: uppercase;
          color: #7dd3fc;
          font-weight: 600;
        }}
        .led {{
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #475569;
          transition: all 0.25s ease;
        }}
        .led.active {{
          background: #34d399;
          box-shadow: 0 0 10px #34d399;
        }}
        .led.mic {{
          background: #38bdf8;
          box-shadow: 0 0 10px #38bdf8;
        }}
        .controls {{
          display: flex;
          align-items: center;
          gap: 8px;
        }}
        .btn {{
          font-family: 'JetBrains Mono', monospace;
          font-size: 10.5px;
          font-weight: 600;
          padding: 5px 11px;
          border-radius: 8px;
          border: 1px solid rgba(56, 189, 248, 0.3);
          background: rgba(15, 23, 42, 0.8);
          color: #e2e8f0;
          cursor: pointer;
          transition: all 0.18s ease;
        }}
        .btn:hover {{
          border-color: #38bdf8;
          background: rgba(14, 116, 144, 0.35);
          color: #ffffff;
        }}
        .btn.active-mic {{
          border-color: #34d399;
          background: rgba(16, 185, 129, 0.22);
          color: #6ee7b7;
        }}
        .canvas-wrap {{
          position: relative;
          width: 100%;
          height: 92px;
          background: rgba(4, 8, 18, 0.78);
          border: 1px solid rgba(148, 163, 184, 0.14);
          border-radius: 12px;
          overflow: hidden;
        }}
        canvas {{
          width: 100%;
          height: 100%;
          display: block;
        }}
        .deck-footer {{
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 8px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 10px;
          color: #64748b;
        }}
      </style>
    </head>
    <body>
      <div class="deck" data-turn="{turn_id}">
        <div class="deck-header">
          <div class="deck-title">
            <span id="statusLed" class="led"></span>
            <span id="statusText">AUDIO TRANSCEIVER · STANDBY</span>
          </div>
          <div class="controls">
            <button id="replayBtn" class="btn" title="Replay latest AI response">▶ Replay AI Voice</button>
            <button id="micToggleBtn" class="btn" title="Visualize your live microphone input">🎙️ Live Mic Scope</button>
          </div>
        </div>
        <div class="canvas-wrap">
          <canvas id="waveCanvas"></canvas>
        </div>
        <div class="deck-footer">
          <span>ENGINE: <strong style="color:#94a3b8;">{engine_label}</strong></span>
          <span id="dbMeter">PEAK: -∞ dB</span>
        </div>
        <audio id="ttsAudio" crossorigin="anonymous" style="display:none;"></audio>
      </div>

      <script>
        (function() {{
          const b64Audio = "{b64_data}";
          const mimeType = "{mime_type}";
          const fallbackText = {safe_text_json};
          const shouldAutoplay = {"true" if should_autoplay else "false"};

          const canvas = document.getElementById("waveCanvas");
          const ctx = canvas.getContext("2d");
          const audioEl = document.getElementById("ttsAudio");
          const statusLed = document.getElementById("statusLed");
          const statusText = document.getElementById("statusText");
          const dbMeter = document.getElementById("dbMeter");
          const replayBtn = document.getElementById("replayBtn");
          const micToggleBtn = document.getElementById("micToggleBtn");

          let audioCtx = null;
          let analyser = null;
          let mediaSource = null;
          let micStream = null;
          let micSource = null;
          let isMicActive = false;
          let isSyntheticSpeaking = false;
          let phase = 0;

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
              analyser.fftSize = 128;
              analyser.smoothingTimeConstant = 0.82;
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
                  statusLed.className = "led active";
                  statusText.textContent = "TRANSMITTING AI VOICE · LIVE";
                }}).catch(() => {{
                  statusText.textContent = "READY · CLICK REPLAY TO UNMUTE BROWSER";
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
            utter.rate = 1.02;
            utter.onstart = () => {{
              isSyntheticSpeaking = true;
              statusLed.className = "led active";
              statusText.textContent = "TRANSMITTING AI VOICE · WEB SPEECH";
            }};
            utter.onend = () => {{
              isSyntheticSpeaking = false;
              if (!isMicActive) {{
                statusLed.className = "led";
                statusText.textContent = "AUDIO TRANSCEIVER · STANDBY";
              }}
            }};
            window.speechSynthesis.speak(utter);
          }}

          audioEl.addEventListener("ended", () => {{
            if (!isMicActive) {{
              statusLed.className = "led";
              statusText.textContent = "AUDIO TRANSCEIVER · STANDBY";
              dbMeter.textContent = "PEAK: -∞ dB";
            }}
          }});

          replayBtn.addEventListener("click", () => {{
            playTtsAudio();
          }});

          micToggleBtn.addEventListener("click", async () => {{
            if (isMicActive) {{
              if (micStream) {{
                micStream.getTracks().forEach(t => t.stop());
              }}
              if (micSource) {{
                try {{ micSource.disconnect(); }} catch (e) {{}}
              }}
              isMicActive = false;
              micToggleBtn.classList.remove("active-mic");
              micToggleBtn.textContent = "🎙️ Live Mic Scope";
              statusLed.className = "led";
              statusText.textContent = "AUDIO TRANSCEIVER · STANDBY";
              return;
            }}
            try {{
              ensureAudioContext();
              micStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
              micSource = audioCtx.createMediaStreamSource(micStream);
              micSource.connect(analyser);
              isMicActive = true;
              micToggleBtn.classList.add("active-mic");
              micToggleBtn.textContent = "⏹️ Stop Mic Scope";
              statusLed.className = "led mic";
              statusText.textContent = "LIVE MICROPHONE SPECTRUM ACTIVE";
            }} catch (err) {{
              statusText.textContent = "MIC PERMISSION DENIED OR UNAVAILABLE";
            }}
          }});

          function renderFrame() {{
            requestAnimationFrame(renderFrame);
            const width = canvas.clientWidth;
            const height = canvas.clientHeight;
            const midY = height / 2;

            ctx.clearRect(0, 0, width, height);

            // Subtle baseline grid
            ctx.strokeStyle = "rgba(56, 189, 248, 0.08)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(0, midY);
            ctx.lineTo(width, midY);
            ctx.stroke();

            const barCount = 48;
            const gap = 4;
            const barWidth = Math.max(2, (width - (barCount - 1) * gap - 24) / barCount);
            let freqData = new Uint8Array(barCount);
            let timeData = new Uint8Array(barCount);
            let hasLiveSignal = false;

            const isAudioPlaying = !audioEl.paused && !audioEl.ended && audioEl.currentTime > 0;

            if (analyser && (isAudioPlaying || isMicActive)) {{
              analyser.getByteFrequencyData(freqData);
              analyser.getByteTimeDomainData(timeData);
              hasLiveSignal = true;
            }} else if (isSyntheticSpeaking) {{
              hasLiveSignal = true;
              for (let i = 0; i < barCount; i++) {{
                freqData[i] = Math.floor(
                  85 + 75 * Math.sin(phase * 3 + i * 0.35) * Math.cos(phase * 1.7 - i * 0.2)
                );
                timeData[i] = Math.floor(128 + 38 * Math.sin(phase * 4 + i * 0.4));
              }}
            }}

            let maxAmp = 0;
            for (let i = 0; i < barCount; i++) {{
              const val = hasLiveSignal
                ? freqData[i]
                : (8 + 5 * Math.sin(phase + i * 0.22));
              if (val > maxAmp) maxAmp = val;

              const norm = Math.min(1, Math.max(0.05, val / 255));
              const barH = Math.max(4, norm * (height * 0.78));
              const x = 12 + i * (barWidth + gap);
              const y = midY - barH / 2;

              const grad = ctx.createLinearGradient(0, y, 0, y + barH);
              if (isMicActive) {{
                grad.addColorStop(0, "#38bdf8");
                grad.addColorStop(0.5, "#818cf8");
                grad.addColorStop(1, "#38bdf8");
              }} else if (hasLiveSignal) {{
                grad.addColorStop(0, "#34d399");
                grad.addColorStop(0.5, "#38bdf8");
                grad.addColorStop(1, "#34d399");
              }} else {{
                grad.addColorStop(0, "rgba(56, 189, 248, 0.22)");
                grad.addColorStop(1, "rgba(16, 185, 129, 0.22)");
              }}

              ctx.fillStyle = grad;
              ctx.beginPath();
              ctx.roundRect(x, y, barWidth, barH, 3);
              ctx.fill();
            }}

            // Smooth glowing oscilloscope wave overlay
            ctx.beginPath();
            ctx.lineWidth = hasLiveSignal ? 2.0 : 1.2;
            ctx.strokeStyle = hasLiveSignal
              ? "rgba(125, 211, 252, 0.9)"
              : "rgba(56, 189, 248, 0.35)";

            for (let i = 0; i < barCount; i++) {{
              const x = 12 + i * (barWidth + gap) + barWidth / 2;
              let y = midY;
              if (hasLiveSignal) {{
                const tNorm = (timeData[i] - 128) / 128;
                y = midY + tNorm * (height * 0.36);
              }} else {{
                y = midY + Math.sin(phase * 1.4 + i * 0.25) * 4;
              }}
              if (i === 0) ctx.moveTo(x, y);
              else ctx.lineTo(x, y);
            }}
            ctx.stroke();

            if (hasLiveSignal && maxAmp > 5) {{
              const db = (20 * Math.log10(maxAmp / 255)).toFixed(1);
              dbMeter.textContent = "PEAK: " + db + " dB";
            }}

            phase += 0.06;
          }}

          renderFrame();

          if (shouldAutoplay) {{
            setTimeout(playTtsAudio, 120);
          }}
        }})();
      </script>
    </body>
    </html>
    """
    components.html(visualizer_html, height=185, scrolling=False)