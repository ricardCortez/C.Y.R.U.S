"""
C.Y.R.U.S — Main Orchestration Engine.

Entry point for the backend.  Wires together audio capture, ASR, trigger
detection, LLM reasoning, TTS synthesis, and the WebSocket broadcast layer
into a continuous async conversation loop.

Run with:
    python -m backend.core.cyrus_engine
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# System monitoring
try:
    import psutil as _psutil
    _PSUTIL_OK = True
except ImportError:
    _PSUTIL_OK = False

try:
    import pynvml as _pynvml
    _pynvml.nvmlInit()
    _NVML_OK = True
except Exception:
    _NVML_OK = False

# Ensure project root is on sys.path when run as __main__
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.api.websocket_server import WebSocketServer
from backend.core.config_manager import load_config
from backend.core.event_bus import EventBus
from backend.core.state_manager import StateManager, SystemStatus
from backend.modules.audio.audio_input import AudioInput
from backend.modules.audio.audio_output import AudioOutput
from backend.modules.audio.speaker_profile import SpeakerProfile
from backend.modules.audio.whisper_asr import WhisperASR
from backend.modules.llm.claude_client import ClaudeClient
from backend.modules.llm.llm_manager import LLMManager
from backend.modules.llm.ollama_client import OllamaClient
from backend.modules.nlp.trigger_detector import TriggerDetector
from backend.modules.tts.kokoro_tts import KokoroTTS
from backend.modules.tts.piper_tts import PiperTTS
from backend.modules.vision.camera_local import LocalCamera
from backend.modules.vision.face_detector import FaceDetector
from backend.modules.vision.frigate_client import FrigateClient
from backend.modules.vision.vision_manager import VisionManager
from backend.modules.vision.yolo_detector import YOLODetector
from backend.modules.tts.remote_tts import RemoteTTS
from backend.modules.tts.tts_manager import TTSManager
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
from backend.modules.tts.xtts_tts import XTTTS
from backend.modules.memory.embedder import Embedder
from backend.modules.memory.qdrant_store import QdrantStore
from backend.modules.memory.conversation_db import ConversationDB
from backend.modules.memory.memory_manager import MemoryManager
from backend.utils.helpers import current_time_str
from backend.utils.logger import configure_file_logging, get_logger

logger = get_logger("cyrus.engine")


class CYRUSEngine:
    """Main C.Y.R.U.S orchestration engine.

    Initialised from ``config/config.yaml``.  Call :meth:`run` to start
    the full voice pipeline.
    """

    def __init__(self) -> None:
        self._cfg = load_config()
        self._bus = EventBus()
        self._state = StateManager(max_history=self._cfg.conversation.max_history_turns)

        # ── Audio ──────────────────────────────────────────────────────────
        ai_cfg = self._cfg.audio.input
        self._audio_in = AudioInput(
            sample_rate=ai_cfg.sample_rate,
            chunk_size=ai_cfg.chunk_size,
            channels=ai_cfg.channels,
            silence_duration=ai_cfg.silence_duration,
            silence_threshold=ai_cfg.silence_threshold,
            device_name=ai_cfg.device,
        )
        ao_cfg = self._cfg.audio.output
        self._audio_out = AudioOutput(
            volume=ao_cfg.volume,
            sample_rate=ao_cfg.sample_rate,
            device_name=ao_cfg.device,
        )

        # ── ASR ────────────────────────────────────────────────────────────
        asr_cfg = self._cfg.asr
        self._asr = WhisperASR(
            model_size=asr_cfg.model,
            device=asr_cfg.device,
            compute_type=asr_cfg.compute_type,
            language=asr_cfg.language,
            beam_size=asr_cfg.beam_size,
            vad_filter=asr_cfg.vad_filter,
            initial_prompt=getattr(asr_cfg, "initial_prompt", None),
        )

        # ── Trigger ────────────────────────────────────────────────────────
        trig_cfg = self._cfg.trigger
        self._trigger = TriggerDetector(
            wake_words=trig_cfg.wake_words,
            threshold=trig_cfg.threshold,
            fuzzy_matching=trig_cfg.fuzzy_matching,
        )

        # ── LLM ────────────────────────────────────────────────────────────
        llm_local_cfg = self._cfg.local.llm
        llm_api_cfg = self._cfg.api.llm
        self._ollama = OllamaClient(
            host=llm_local_cfg.host,
            model=llm_local_cfg.model,
            timeout=llm_local_cfg.timeout,
            stream=llm_local_cfg.stream,
        )
        self._local_ai_detector = 'ollama'
        self._claude = ClaudeClient(
            api_key=llm_api_cfg.api_key,
            model=llm_api_cfg.model,
            max_tokens=llm_api_cfg.max_tokens,
            timeout=llm_api_cfg.timeout,
        )
        self._llm = LLMManager(
            ollama=self._ollama,
            claude=self._claude,
            soul_text=self._cfg.soul_text,
            prompts=self._cfg.prompts,
            mode=self._cfg.system.mode,
        )

        # ── TTS ────────────────────────────────────────────────────────────
        tts_local_cfg = self._cfg.local.tts
        tts_api_cfg = self._cfg.api.tts
        self._kokoro = KokoroTTS(
            voice=tts_local_cfg.voice,
            speed=tts_local_cfg.speed,
            sample_rate=tts_local_cfg.sample_rate,
            lang_code=getattr(tts_local_cfg, "lang_code", "e"),
        )
        self._voiceforge = VoiceforgeTTS(
            voice=tts_api_cfg.voice,
            rate=tts_api_cfg.rate,
            volume=tts_api_cfg.volume,
        )
        # Piper — instantiated always; only activated when load() succeeds
        self._piper = PiperTTS(
            model_path=getattr(tts_local_cfg, "piper_model", ""),
            speed=tts_local_cfg.speed,
            speaker_id=getattr(tts_local_cfg, "piper_speaker", None),
        )
        # XTTS v2 — optional high-quality offline TTS; loaded only if enabled in config
        xtts_cfg = getattr(tts_local_cfg, "xtts", None)
        self._xtts = XTTTS(
            language=getattr(xtts_cfg, "language", "es") if xtts_cfg else "es",
            speaker=getattr(xtts_cfg, "speaker", "Tammie Ema") if xtts_cfg else "Tammie Ema",
            speed=tts_local_cfg.speed,
        )
        # RemoteTTS — external TTS server (xtts-api-server or OpenAI-compat)
        svc_tts = self._cfg.services.tts
        self._remote_tts = RemoteTTS(
            host=svc_tts.host,
            language=svc_tts.language,
            speaker=svc_tts.speaker,
            timeout=svc_tts.timeout,
        ) if svc_tts.enabled else None

        self._tts = TTSManager(
            kokoro=self._kokoro,
            voiceforge=self._voiceforge,
            mode=self._cfg.system.mode,
            piper=self._piper,
            xtts=self._xtts,
            remote=self._remote_tts,
        )

        # ── Vision ─────────────────────────────────────────────────────
        vis_cfg = getattr(self._cfg, "vision", None)
        self._vision: VisionManager | None = None
        if vis_cfg and getattr(vis_cfg, "enabled", False):
            lc = vis_cfg.local
            fr = vis_cfg.frigate
            yo = vis_cfg.yolo
            fa = vis_cfg.face
            self._vision = VisionManager(
                source=vis_cfg.source,
                local_camera=LocalCamera(
                    device_index=lc.device_index,
                    width=lc.width,
                    height=lc.height,
                    fps=lc.fps,
                ),
                frigate_client=FrigateClient(
                    host=fr.host,
                    camera=fr.camera,
                    timeout=fr.timeout,
                ),
                yolo=YOLODetector(
                    model_name=yo.model,
                    confidence=yo.confidence,
                    device=yo.device,
                ),
                face=FaceDetector(
                    db_path=fa.db_path,
                    model_name=fa.model_name,
                    detector_backend=fa.detector_backend,
                ),
                interval=vis_cfg.interval,
                encode_frame=vis_cfg.encode_frame,
            )

        # ── Memory (Phase 3) ───────────────────────────────────────────────
        mem_cfg = getattr(self._cfg, "memory", None)
        self._memory: MemoryManager | None = None
        if mem_cfg and getattr(mem_cfg, "enabled", False):
            qd = mem_cfg.qdrant
            emb_cfg = mem_cfg.embedder
            self._embedder = Embedder(model_name=emb_cfg.model)
            self._qdrant_store = QdrantStore(
                host=qd.host,
                port=qd.port,
                collection=qd.collection,
            )
            self._conv_db = ConversationDB(db_path=mem_cfg.db_path)
            self._memory = MemoryManager(
                embedder=self._embedder,
                qdrant=self._qdrant_store,
                db=self._conv_db,
                top_k=mem_cfg.top_k,
            )

        # ── WebSocket ──────────────────────────────────────────────────────
        ws_cfg = self._cfg.websocket
        self._ws = WebSocketServer(
            event_bus=self._bus,
            host=ws_cfg.host,
            port=ws_cfg.port,
            ping_interval=ws_cfg.ping_interval,
            ping_timeout=ws_cfg.ping_timeout,
        )

        # ── Audio output lock — prevents greeting/TTS overlap ──────────────
        self._audio_lock: asyncio.Lock | None = None   # created in async context
        self._last_greeting_at: float = 0.0

        # ── Barge-in (speech interruption during TTS) ─────────────────────
        self._barge_in_task: asyncio.Task | None = None

        # ── Conversation mode ──────────────────────────────────────────────
        # After the wake word is detected, the user can speak freely for
        # CONVERSATION_TIMEOUT seconds without repeating the wake word.
        self._in_conversation: bool = False
        self._last_interaction_at: float = 0.0
        self._CONVERSATION_TIMEOUT: float = 45.0   # seconds of silence → back to standby

        # ── Enrollment mode ────────────────────────────────────────────────
        self._enrollment_active: bool = False   # pauses the pipeline loop

        # ── Startup timestamp for uptime tracking ─────────────────────────
        self._start_time: float = time.monotonic()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def _models_then_pipeline(self) -> None:
        """Load models then start the voice pipeline."""
        await self._init_models()
        await self._pipeline_loop()

    async def _init_models(self) -> None:
        """Load all ML models asynchronously (in executor to avoid blocking)."""
        loop = asyncio.get_event_loop()

        logger.info("[C.Y.R.U.S] Loading Whisper ASR model…")
        await loop.run_in_executor(None, self._asr.load)

        # Try Piper first (best quality) — non-fatal if unavailable
        if getattr(self._cfg.local.tts, "piper_model", ""):
            logger.info("[C.Y.R.U.S] Loading Piper TTS model…")
            try:
                await loop.run_in_executor(None, self._piper.load)
                logger.info(f"[C.Y.R.U.S] Piper ready — active backend: piper")
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Piper unavailable ({exc}); falling back to Kokoro")

        logger.info("[C.Y.R.U.S] Loading Kokoro TTS model…")
        try:
            await loop.run_in_executor(None, self._kokoro.load)
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] Kokoro unavailable ({exc}); will use Edge-TTS fallback")

        # RemoteTTS — probe the external server if enabled
        if self._remote_tts is not None:
            logger.info(f"[C.Y.R.U.S] Probing RemoteTTS server at {self._cfg.services.tts.host}…")
            ok = await self._remote_tts.check_health()
            if ok:
                logger.info("[C.Y.R.U.S] RemoteTTS server ready — active backend: remote-tts")
            else:
                logger.warning("[C.Y.R.U.S] RemoteTTS server not reachable — will fall through to next backend")

        # XTTS v2 — only load if explicitly enabled in config
        xtts_cfg = getattr(self._cfg.local.tts, "xtts", None)
        if xtts_cfg and getattr(xtts_cfg, "enabled", False):
            logger.info("[C.Y.R.U.S] Loading XTTS v2 model…")
            try:
                await loop.run_in_executor(None, self._xtts.load)
                logger.info("[C.Y.R.U.S] XTTS v2 ready")
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] XTTS v2 unavailable ({exc})")

        logger.info("[C.Y.R.U.S] Checking Ollama availability…")
        if not await self._ollama.is_available():
            logger.warning("[C.Y.R.U.S] Ollama not responding — API fallback will be used")
        else:
            logger.info("[C.Y.R.U.S] Ollama is online")

        if self._vision:
            logger.info("[C.Y.R.U.S] Starting vision pipeline…")
            await self._vision.start()

        if self._memory:
            logger.info("[C.Y.R.U.S] Loading embedder model…")
            await loop.run_in_executor(None, self._embedder.load)
            logger.info("[C.Y.R.U.S] Connecting to Qdrant…")
            try:
                self._qdrant_store.connect()
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Qdrant unavailable ({exc}); memory search disabled")
            self._conv_db.init()
            logger.info(f"[C.Y.R.U.S] Memory session: {self._memory.session_id}")

        # ── Voice profile (speaker verification for barge-in) ─────────────
        profile_path = self._cfg.project_root / "config" / "voice_profile.npy"
        if profile_path.exists():
            try:
                profile = SpeakerProfile.load(profile_path, sample_rate=self._cfg.audio.input.sample_rate)
                self._audio_in.set_voice_profile(profile)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Could not load voice profile: {exc}")
        else:
            logger.info("[C.Y.R.U.S] No voice profile found — barge-in accepts any voice (run enrollment to set up)")

        logger.info("[C.Y.R.U.S] All models initialised")

    # ------------------------------------------------------------------
    # System stats broadcaster
    # ------------------------------------------------------------------

    async def _stats_loop(self) -> None:
        """Broadcast real system metrics every 5 seconds."""
        # Prime psutil CPU measurement (first call returns 0)
        if _PSUTIL_OK:
            _psutil.cpu_percent(interval=None)
        await asyncio.sleep(2)

        while True:
            try:
                cpu = _psutil.cpu_percent(interval=None) if _PSUTIL_OK else 0.0
                ram = _psutil.virtual_memory().percent if _PSUTIL_OK else 0.0

                vram_pct = 0.0
                gpu_temp = 0
                gpu_name = "RTX 2070S"
                if _NVML_OK:
                    try:
                        handle = _pynvml.nvmlDeviceGetHandleByIndex(0)
                        mem = _pynvml.nvmlDeviceGetMemoryInfo(handle)
                        vram_pct = round(mem.used / mem.total * 100, 1)
                        gpu_temp = _pynvml.nvmlDeviceGetTemperature(
                            handle, _pynvml.NVML_TEMPERATURE_GPU
                        )
                        raw_name = _pynvml.nvmlDeviceGetName(handle)
                        gpu_name = raw_name if isinstance(raw_name, str) else raw_name.decode()
                    except Exception:
                        pass

                uptime = int(time.monotonic() - self._start_time)

                await self._bus.emit("system_stats", {
                    "cpu":         round(cpu, 1),
                    "ram":         round(ram, 1),
                    "vram":        vram_pct,
                    "gpu_temp":    gpu_temp,
                    "gpu_name":    gpu_name,
                    "uptime":      uptime,
                    "tts_backend": self._tts.active_backend,
                })
            except Exception as exc:
                logger.debug(f"[C.Y.R.U.S] Stats loop error: {exc}")

            await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # TTS helper (used by test_tts command and enrollment)
    # ------------------------------------------------------------------

    async def _barge_in_watcher(self) -> None:
        """Background task — monitors mic for speech while CYRUS is speaking.
        If the user starts talking, interrupt playback immediately."""
        try:
            detected = await self._audio_in.detect_speech_onset(timeout=60.0)
            if detected:
                logger.info("[C.Y.R.U.S] Barge-in detected — interrupting playback")
                self._audio_out.interrupt()
                await self._bus.emit("debug", {"text": "⚡ Interrupción detectada", "level": "warn"})
                # Clear the mute so the next record_utterance() hears the user
                self._audio_in.mute_for(0.0)
        except asyncio.CancelledError:
            pass  # Normal: cancelled when CYRUS finishes speaking

    async def _speak_text(self, text: str) -> None:
        """Synthesise and play text without going through the full pipeline."""
        if self._audio_lock is None:
            return
        await self._bus.emit("status", {"state": "speaking"})
        await self._bus.emit("response", {"text": text, "language": "es"})
        async with self._audio_lock:
            try:
                audio_bytes, mime = await self._tts.synthesise(text)
                if audio_bytes:
                    if mime == "audio/wav":
                        await self._audio_out.play_wav(audio_bytes)
                    else:
                        await self._play_mp3(audio_bytes)
                    self._audio_in.mute_for(1.2)
            except Exception as exc:
                logger.error(f"[C.Y.R.U.S] _speak_text failed: {exc}")
        await self._bus.emit("status", {"state": "idle"})

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def _save_wake_words(self) -> None:
        """Persist current wake words list to config.yaml."""
        import yaml as _yaml
        config_path = self._cfg.project_root / "config" / "config.yaml"
        try:
            raw = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            raw.setdefault("trigger", {})["wake_words"] = self._trigger.wake_words
            config_path.write_text(
                _yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            logger.info(f"[C.Y.R.U.S] Wake words saved to config: {self._trigger.wake_words}")
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] Failed to save wake words: {exc}")

    async def _save_llm_model(self) -> None:
        """Persist the currently selected local LLM model to config.yaml."""
        import yaml as _yaml
        config_path = self._cfg.project_root / "config" / "config.yaml"
        try:
            raw = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            local_section = raw.setdefault("local", {})
            llm_section = local_section.setdefault("llm", {})
            llm_section["model"] = self._ollama._model
            config_path.write_text(
                _yaml.dump(raw, allow_unicode=True, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
            logger.info(f"[C.Y.R.U.S] Local LLM model saved to config: {self._ollama._model}")
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] Failed to save local LLM model: {exc}")

    async def _run_enrollment(self, samples: int = 5) -> None:
        """Record N samples, transcribe each, register wake-word variants, and build voice profile."""
        self._enrollment_active = True
        # Interrupt any currently-blocked recording
        self._audio_in.request_stop()
        await asyncio.sleep(0.5)  # let the interrupted recording return

        collected: list[str] = []
        added: list[str] = []
        pcm_samples: list[bytes] = []  # raw audio kept for voice profile

        intro = (
            f"Modo de enrollamiento activado. "
            f"Voy a pedirte que digas mi nombre {samples} veces. "
            f"Habla con naturalidad, como lo harías normalmente."
        )
        await self._bus.emit("enrollment", {"step": "start", "total": samples})
        await self._bus.emit("status", {"state": "speaking"})
        await self._bus.emit("response", {"text": intro, "language": "es"})
        async with self._audio_lock:
            try:
                audio_bytes, mime = await self._tts.synthesise(intro)
                if audio_bytes:
                    await self._audio_out.play_wav(audio_bytes) if mime == "audio/wav" else await self._play_mp3(audio_bytes)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Enrollment TTS failed: {exc}")

        for i in range(1, samples + 1):
            prompt_text = f"Muestra {i} de {samples}. Di mi nombre ahora."
            await self._bus.emit("enrollment", {"step": "prompt", "sample": i, "total": samples})
            await self._bus.emit("debug", {"text": f"ENROLLMENT {i}/{samples}: escuchando…", "level": "info"})

            # Play short beep prompt via TTS
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(f"Muestra {i}.")
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception:
                    pass

            await asyncio.sleep(0.3)

            # Record one utterance
            try:
                pcm = await self._audio_in.record_utterance()
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Enrollment recording failed: {exc}")
                continue

            if not pcm:
                await self._bus.emit("enrollment", {"step": "result", "sample": i, "heard": "(silencio)"})
                continue

            pcm_samples.append(pcm)  # keep for voice profile

            # Transcribe with no initial_prompt so we capture raw perception
            orig_prompt = self._asr._initial_prompt
            self._asr._initial_prompt = None
            try:
                text, lang = self._asr.transcribe(pcm)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Enrollment ASR failed: {exc}")
                text = ""
            finally:
                self._asr._initial_prompt = orig_prompt

            heard = text.strip().lower()
            collected.append(heard)
            await self._bus.emit("enrollment", {"step": "result", "sample": i, "heard": heard or "(silencio)"})
            await self._bus.emit("debug", {"text": f"  Muestra {i}: \"{heard}\"", "level": "info"})

            if heard:
                self._trigger.add_wake_word(heard)
                added.append(heard)

        # Save to config.yaml
        if added:
            await self._save_wake_words()
            await self._bus.emit("wake_words", {"words": self._trigger.wake_words})

        # Build and save voice profile from enrollment audio
        if pcm_samples:
            try:
                loop = asyncio.get_event_loop()
                sample_rate = self._cfg.audio.input.sample_rate
                profile = await loop.run_in_executor(
                    None,
                    lambda: SpeakerProfile.from_pcm_samples(pcm_samples, sample_rate=sample_rate),
                )
                profile_path = self._cfg.project_root / "config" / "voice_profile.npy"
                profile.save(profile_path)
                self._audio_in.set_voice_profile(profile)
                logger.info("[C.Y.R.U.S] Voice profile built and activated for barge-in")
                await self._bus.emit("debug", {"text": "✓ Perfil de voz guardado — barge-in personalizado activo", "level": "ok"})
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Voice profile build failed: {exc}")

        # Summary
        if added:
            summary = f"Enrollamiento completado. Registré {len(added)} variante{'s' if len(added) != 1 else ''}: {', '.join(added)}. Tu voz quedó registrada para el sistema de interrupción."
        else:
            summary = "No detecté audio claro. Intenta de nuevo en un ambiente más silencioso."

        await self._bus.emit("enrollment", {"step": "done", "added": added})
        await self._bus.emit("status", {"state": "speaking"})
        await self._bus.emit("response", {"text": summary, "language": "es"})
        async with self._audio_lock:
            try:
                ab, mime = await self._tts.synthesise(summary)
                if ab:
                    await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Enrollment summary TTS failed: {exc}")

        self._enrollment_active = False
        await self._bus.emit("status", {"state": "idle"})
        await self._bus.emit("enrollment", {"step": "idle"})

    async def _greet(self) -> None:
        """Synthesise and play the startup greeting in Spanish."""
        GREETING = (
            "Hola. Soy C.Y.R.U.S, tu asistente de inteligencia artificial. "
            "Todos los sistemas están en línea. "
            "Menciona mi nombre cuando necesites asistencia."
        )
        logger.info("[C.Y.R.U.S] Playing startup greeting")
        await self._bus.emit("status", {"state": "speaking"})
        await self._bus.emit("response", {"text": GREETING, "language": "es"})
        async with self._audio_lock:
            try:
                audio_bytes, mime = await self._tts.synthesise(GREETING)
                if audio_bytes:
                    if mime == "audio/wav":
                        await self._audio_out.play_wav(audio_bytes)
                    else:
                        await self._play_mp3(audio_bytes)
                    self._audio_in.mute_for(1.5)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Greeting TTS failed: {exc}")
        self._last_greeting_at = time.monotonic()
        await self._bus.emit("status", {"state": "idle"})

    async def _on_client_connected(self, _payload: dict) -> None:
        """Trigger greeting when a new frontend client connects."""
        # Send current wake words list so the UI can display them
        await self._bus.emit("wake_words", {"words": self._trigger.wake_words})
        # Debounce: skip if greeted less than 20 seconds ago
        if time.monotonic() - self._last_greeting_at < 20:
            return
        asyncio.create_task(self._greet())

    async def _on_all_clients_disconnected(self, _payload: dict) -> None:
        """Called when the last frontend client drops — interrupts any live recording."""
        logger.info("[C.Y.R.U.S] All clients disconnected — pausing mic")
        self._audio_in.request_stop()
        # Reset conversation mode so next session starts fresh from wake-word standby
        self._in_conversation = False
        await self._bus.emit("status", {"state": "idle", "message": "Esperando conexión…"})

    async def _on_frontend_command(self, payload: dict) -> None:
        """Handle commands sent from the frontend UI."""
        cmd = payload.get("cmd")
        if cmd == "add_wake_word":
            word = str(payload.get("word", "")).strip()
            if word:
                self._trigger.add_wake_word(word)
                logger.info(f"[C.Y.R.U.S] Wake word added via UI: '{word}'")
                await self._bus.emit("wake_words", {"words": self._trigger.wake_words})
                await self._bus.emit("debug", {"text": f"✓ Wake word '{word}' registrado", "level": "ok"})
        elif cmd == "remove_wake_word":
            word = str(payload.get("word", "")).strip().lower()
            self._trigger.remove_wake_word(word)
            await self._save_wake_words()
            await self._bus.emit("wake_words", {"words": self._trigger.wake_words})
            await self._bus.emit("debug", {"text": f"✗ Wake word '{word}' eliminado", "level": "warn"})
        elif cmd == "start_enrollment":
            if not self._enrollment_active:
                samples = int(payload.get("samples", 5))
                asyncio.create_task(self._run_enrollment(samples=samples))

        elif cmd == "set_tts_speed":
            speed = float(payload.get("speed", 1.0))
            self._tts.set_speed(speed)
            logger.info(f"[C.Y.R.U.S] TTS speed → {speed}")
            await self._bus.emit("debug", {"text": f"TTS speed ajustada a {speed:.2f}", "level": "ok"})

        elif cmd == "test_tts":
            text = str(payload.get("text", "Sistema de voz operativo. C.Y.R.U.S en línea.")).strip()
            if text and not self._enrollment_active:
                asyncio.create_task(self._speak_text(text))

        elif cmd == "set_local_ai_detector":
            detector = str(payload.get("detector", "ollama")).strip().lower()
            if detector == "ollama":
                self._local_ai_detector = "ollama"
                logger.info("[C.Y.R.U.S] Local AI detector set to Ollama")
                await self._bus.emit("debug", {"text": "Detector local: Ollama", "level": "ok"})
            else:
                logger.warning(f"[C.Y.R.U.S] Unsupported local AI detector: {detector}")
                await self._bus.emit("debug", {"text": f"Detector local no soportado: {detector}", "level": "warn"})

        elif cmd == "probe_local_ai_detector":
            detector = str(payload.get("detector", "ollama")).strip().lower()
            await self._bus.emit("debug", {"text": "Comprobando detector local...", "level": "info"})
            if detector == "ollama":
                try:
                    available = await self._ollama.is_available()
                    if available:
                        self._local_ai_detector = "ollama"
                        await self._bus.emit("debug", {"text": "Ollama local disponible.", "level": "ok"})
                    else:
                        await self._bus.emit("debug", {"text": "Ollama local no disponible.", "level": "warn"})
                except Exception as exc:
                    logger.warning(f"[C.Y.R.U.S] Ollama probe failed: {exc}")
                    await self._bus.emit("debug", {"text": "No se pudo conectar a Ollama local.", "level": "warn"})
            else:
                await self._bus.emit("debug", {"text": f"Detector local no reconocido: {detector}", "level": "warn"})

        elif cmd == "list_ollama_models":
            try:
                models = await self._ollama.list_models()
                results = []
                for model_info in models:
                    name = str(model_info.get("name") or model_info.get("model") or "unknown")
                    compatible = True
                    compatibility = "Compatible"
                    if not _NVML_OK:
                        low_cost = any(k in name.lower() for k in ["tiny", "mini", "micro", "nano"])
                        if not low_cost:
                            compatible = False
                            compatibility = "Requiere GPU"
                        else:
                            compatibility = "OK en CPU"
                    results.append({
                        "name": name,
                        "compatible": compatible,
                        "compatibility": compatibility,
                    })
                await self._bus.emit("available_models", {"models": results, "current": self._ollama._model})
                await self._bus.emit("debug", {"text": f"Modelos locales listados: {len(results)}", "level": "ok"})
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Could not list Ollama models: {exc}")
                await self._bus.emit("debug", {"text": "No se pudieron obtener los modelos de Ollama.", "level": "warn"})

        elif cmd == "set_tts_engine":
            engine = str(payload.get("engine", "")).strip().lower()
            valid = {"piper", "remote-tts", "xtts", "kokoro", "edge-tts"}
            if engine in valid:
                self._tts.set_forced_backend(engine)
                await self._bus.emit("debug", {"text": f"Motor TTS fijado a: {engine}", "level": "ok"})
            elif engine == "auto":
                self._tts.set_forced_backend(None)
                await self._bus.emit("debug", {"text": "Motor TTS: prioridad automática restaurada", "level": "ok"})
            else:
                await self._bus.emit("debug", {"text": f"Motor TTS desconocido: {engine}", "level": "warn"})

        elif cmd == "set_voice_preset":
            preset = str(payload.get("preset", "natural")).strip().lower()
            self._tts.set_voice_preset(preset)
            await self._bus.emit("debug", {"text": f"Preset de voz: {preset}", "level": "ok"})

        elif cmd == "set_llm_model":
            model = str(payload.get("model", "")).strip()
            if model:
                self._ollama._model = model
                logger.info(f"[C.Y.R.U.S] LLM model → {model}")
                await self._bus.emit("debug", {"text": f"Modelo LLM cambiado a {model}", "level": "ok"})
                await self._save_llm_model()
                try:
                    models = await self._ollama.list_models()
                    results = []
                    for model_info in models:
                        name = str(model_info.get("name") or model_info.get("model") or "unknown")
                        size_bytes = model_info.get("size", 0)
                        size_gb = size_bytes / (1024 ** 3) if size_bytes else 0
                        compatible = True
                        compatibility = f"Compatible ({size_gb:.1f} GB)"
                        if not _NVML_OK:
                            # Estimar RAM requerida: aproximadamente 2x el tamaño del modelo para inferencia
                            estimated_ram_gb = size_gb * 2
                            import psutil
                            available_ram_gb = psutil.virtual_memory().available / (1024 ** 3)
                            low_cost = any(k in name.lower() for k in ["tiny", "mini", "micro", "nano"]) or estimated_ram_gb < 4
                            if not low_cost and estimated_ram_gb > available_ram_gb:
                                compatible = False
                                compatibility = f"Requiere más RAM ({estimated_ram_gb:.1f} GB needed, {available_ram_gb:.1f} GB available)"
                            elif not low_cost:
                                compatibility = f"Requiere GPU ({size_gb:.1f} GB)"
                            else:
                                compatibility = f"OK en CPU ({size_gb:.1f} GB)"
                        results.append({
                            "name": name,
                            "compatible": compatible,
                            "compatibility": compatibility,
                        })
                    await self._bus.emit("available_models", {"models": results, "current": self._ollama._model})
                except Exception:
                    pass

    async def _pipeline_loop(self) -> None:
        """Continuous voice pipeline loop."""
        self._audio_lock = asyncio.Lock()
        self._audio_in.open()
        self._audio_out.open()

        # Subscribe to client-connected events so we greet on every new session
        self._bus.subscribe("client_connected", self._on_client_connected)
        # Pause mic when all clients disconnect
        self._bus.subscribe("all_clients_disconnected", self._on_all_clients_disconnected)
        # Handle commands sent by the frontend
        self._bus.subscribe("frontend_command", self._on_frontend_command)

        # Start background system stats broadcaster
        asyncio.create_task(self._stats_loop())

        logger.info("[C.Y.R.U.S] Starting… Say 'Hola C.Y.R.U.S' or 'Hey C.Y.R.U.S'")
        await self._bus.emit("status", {"state": "idle", "message": "C.Y.R.U.S online"})
        await self._state.set_status(SystemStatus.IDLE)

        try:
            while True:
                await self._process_one_turn()
        except KeyboardInterrupt:
            logger.info("[C.Y.R.U.S] Interrupted — shutting down")
        except asyncio.CancelledError:
            pass
        finally:
            self._audio_in.close()
            self._audio_out.close()
            if self._vision:
                await self._vision.stop()

    async def _process_one_turn(self) -> None:
        """Capture one utterance and drive it through the full pipeline."""

        # Yield to enrollment if active
        if self._enrollment_active:
            await asyncio.sleep(0.1)
            return

        # ── Client gate: mic is silent until at least one UI client is connected ──
        if not self._ws.has_clients:
            await asyncio.sleep(0.5)
            return

        # 1. Capture audio ───────────────────────────────────────────────
        # Only broadcast the state change when transitioning INTO listening;
        # avoids LISTENING → TRANSCRIBING → LISTENING flicker on noise frames.
        if self._state.status != SystemStatus.LISTENING:
            await self._state.set_status(SystemStatus.LISTENING)
            await self._bus.emit("status", {"state": "listening"})
        try:
            pcm = await self._audio_in.record_utterance()
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] Audio capture failed: {exc}")
            await asyncio.sleep(0.5)
            return

        if not pcm:
            return

        # Gate: discard utterances shorter than 300 ms — almost certainly noise.
        # 16 kHz × 2 bytes × 0.3 s = 9 600 bytes
        _MIN_PCM = int(self._cfg.audio.input.sample_rate * 2 * 0.30)
        if len(pcm) < _MIN_PCM:
            logger.debug(f"[C.Y.R.U.S] PCM too short ({len(pcm)} B < {_MIN_PCM} B) — discarded")
            await asyncio.sleep(0.05)
            return

        # 2. Transcribe ──────────────────────────────────────────────────
        await self._state.set_status(SystemStatus.PROCESSING)
        await self._bus.emit("status", {"state": "transcribing"})
        try:
            transcript, lang = self._asr.transcribe(pcm)
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] ASR failed: {exc}")
            await self._bus.emit("error", {"message": "Transcription failed — please repeat"})
            await self._state.set_status(SystemStatus.LISTENING)
            await self._bus.emit("status", {"state": "listening"})
            return

        if not transcript.strip():
            logger.debug("[C.Y.R.U.S] Empty transcript — ignoring")
            # Return to LISTENING without emitting state (no visible flicker)
            await self._state.set_status(SystemStatus.LISTENING)
            await asyncio.sleep(0.05)
            return

        logger.info(f"[C.Y.R.U.S] Transcript: '{transcript}' [{lang}]")
        # Emit raw ASR result to frontend debug log
        await self._bus.emit("debug", {"text": f"ASR [{lang}]: \"{transcript}\"", "level": "info"})
        await self._bus.emit("transcript", {"text": transcript, "language": lang})

        # 3. Trigger detection / conversation-mode gate ──────────────────
        now = time.monotonic()

        # Check if conversation session has timed out
        if self._in_conversation and (now - self._last_interaction_at) > self._CONVERSATION_TIMEOUT:
            self._in_conversation = False
            logger.info("[C.Y.R.U.S] Conversation timeout — back to wake-word mode")
            await self._bus.emit("debug", {
                "text": "💤 Sesión terminada por inactividad — di mi nombre para activarme",
                "level": "warn",
            })
            await self._bus.emit("status", {"state": "idle", "message": "Esperando activación…"})

        if self._in_conversation:
            # Already in an active session — use full transcript directly
            clean_input = transcript.strip()
            self._last_interaction_at = now
            await self._bus.emit("debug", {
                "text": f"💬 Conversación activa → \"{clean_input}\"",
                "level": "ok",
            })
            if not clean_input:
                await self._state.set_status(SystemStatus.IDLE)
                return
        else:
            # Standby mode — require wake word
            triggered, clean_input = self._trigger.detect(transcript)
            if not triggered:
                logger.debug(f"[C.Y.R.U.S] No wake word in: '{transcript}'")
                await self._bus.emit("debug", {
                    "text": f"⚠ Sin wake word en: \"{transcript}\"",
                    "level": "warn",
                })
                # Transition back to LISTENING (not IDLE) so the status bar stays
                # consistent and the next iteration won't re-broadcast the change.
                await self._state.set_status(SystemStatus.LISTENING)
                await self._bus.emit("status", {"state": "listening"})
                return

            # Wake word heard — activate conversation mode
            self._in_conversation = True
            self._last_interaction_at = now
            await self._bus.emit("debug", {
                "text": f"✓ Wake word detectado — sesión iniciada → \"{clean_input or '(sin consulta)'}\"",
                "level": "ok",
            })

            if not clean_input.strip():
                # Only wake word, no query — let CYRUS acknowledge and wait
                clean_input = "El usuario te acaba de llamar. Salúdalo brevemente y pregúntale en qué puedes ayudarle."

        # 4. LLM inference ───────────────────────────────────────────────
        await self._bus.emit("status", {"state": "thinking"})
        await self._state.add_turn("user", clean_input, lang)
        vision_ctx = self._vision.get_context() if self._vision else None

        # 4a. Retrieve memory context
        memory_ctx = ""
        if self._memory:
            try:
                memory_ctx = await self._memory.retrieve_context(clean_input)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Memory retrieval failed: {exc}")

        try:
            display_text, speech_text = await self._llm.generate(
                clean_input,
                history=self._state.get_history_for_llm()[:-1],  # exclude the turn we just added
                language=lang,
                turn_count=self._state.turn_count,
                vision_context=vision_ctx,
                memory_context=memory_ctx,
            )
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] LLM failed: {exc}")
            display_text = "Tengo problemas para procesar tu solicitud. Por favor intenta de nuevo."
            speech_text = display_text

        # Store display text in history (markdown-safe version for context)
        await self._state.add_turn("assistant", display_text, lang)

        # 4b. Persist both turns to memory
        if self._memory:
            try:
                await self._memory.store_turn("user", clean_input, lang)
                await self._memory.store_turn("assistant", display_text, lang)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Memory storage failed: {exc}")
        # Debug log: show full text transformation pipeline
        logger.info(f"[C.Y.R.U.S] DISPLAY ({len(display_text)}ch): {display_text[:120]!r}")
        logger.info(f"[C.Y.R.U.S] SPEECH  ({len(speech_text)}ch): {speech_text[:120]!r}")
        await self._bus.emit("debug", {
            "text": f"DISPLAY ({len(display_text)}ch) → SPEECH ({len(speech_text)}ch) via {self._tts.active_backend}",
            "level": "info",
        })
        # Emit display text to frontend (markdown rendered in UI)
        await self._bus.emit("response", {"text": display_text, "language": lang})

        # 5. TTS synthesis & playback ────────────────────────────────────
        await self._state.set_status(SystemStatus.SPEAKING)
        await self._bus.emit("status", {"state": "speaking"})
        try:
            audio_bytes, mime = await self._tts.synthesise(speech_text)
            if audio_bytes:
                # Launch barge-in watcher — concurrently monitors mic for speech onset
                self._barge_in_task = asyncio.create_task(self._barge_in_watcher())
                async with self._audio_lock:
                    if mime == "audio/wav":
                        await self._audio_out.play_wav(audio_bytes)
                    else:
                        await self._play_mp3(audio_bytes)
                # Cancel barge-in task if playback finished normally
                if self._barge_in_task and not self._barge_in_task.done():
                    self._barge_in_task.cancel()
                    self._barge_in_task = None
                # Mute mic briefly so CYRUS doesn't transcribe its own voice (echo)
                # If interrupted by barge-in, mute_for(0) was already set — skip
                if not self._audio_out._stop_flag.is_set():
                    self._audio_in.mute_for(0.8)
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] TTS/playback failed: {exc}")

        # Refresh conversation timestamp after each full exchange so the
        # 45-second window starts from when CYRUS finished speaking, not when
        # the user started talking.
        if self._in_conversation:
            self._last_interaction_at = time.monotonic()

        await self._state.set_status(SystemStatus.IDLE)
        await self._bus.emit("status", {"state": "idle"})

    async def _play_mp3(self, mp3_bytes: bytes) -> None:
        """Decode and play MP3 bytes (edge-tts fallback output)."""
        try:
            import io
            import soundfile as sf
            import numpy as np

            buf = io.BytesIO(mp3_bytes)
            data, rate = sf.read(buf, dtype="int16")
            pcm = data.tobytes()
            await self._audio_out.play_pcm(pcm, sample_rate=rate)
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] MP3 decode/playback failed: {exc}")

    # ------------------------------------------------------------------
    # Public run method
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the C.Y.R.U.S engine (models + pipeline + WebSocket)."""
        log_cfg = self._cfg.logging
        project_root = self._cfg.project_root
        if log_cfg.file:
            configure_file_logging(
                project_root / log_cfg.log_dir,
                level=log_cfg.level,
            )

        logger.info("=" * 60)
        logger.info("[C.Y.R.U.S] COGNITIVE SYSTEM v1.0 — STARTING")
        logger.info(f"[C.Y.R.U.S] Mode: {self._cfg.system.mode}")
        logger.info(f"[C.Y.R.U.S] Time: {current_time_str()}")
        logger.info("=" * 60)

        # Start WebSocket server immediately so the frontend can connect
        # while models are still loading, then run the voice pipeline.
        await asyncio.gather(
            self._ws.start(),
            self._models_then_pipeline(),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    engine = CYRUSEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("[C.Y.R.U.S] Shutdown complete")


if __name__ == "__main__":
    main()
