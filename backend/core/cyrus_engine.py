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
from pathlib import Path

# Ensure project root is on sys.path when run as __main__
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.api.websocket_server import WebSocketServer
from backend.core.config_manager import load_config
from backend.core.event_bus import EventBus
from backend.core.state_manager import StateManager, SystemStatus
from backend.modules.audio.audio_input import AudioInput
from backend.modules.audio.audio_output import AudioOutput
from backend.modules.audio.whisper_asr import WhisperASR
from backend.modules.llm.claude_client import ClaudeClient
from backend.modules.llm.llm_manager import LLMManager
from backend.modules.llm.ollama_client import OllamaClient
from backend.modules.nlp.trigger_detector import TriggerDetector
from backend.modules.tts.kokoro_tts import KokoroTTS
from backend.modules.vision.camera_local import LocalCamera
from backend.modules.vision.face_detector import FaceDetector
from backend.modules.vision.frigate_client import FrigateClient
from backend.modules.vision.vision_manager import VisionManager
from backend.modules.vision.yolo_detector import YOLODetector
from backend.modules.tts.tts_manager import TTSManager
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
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
        )
        self._voiceforge = VoiceforgeTTS(
            voice=tts_api_cfg.voice,
            rate=tts_api_cfg.rate,
            volume=tts_api_cfg.volume,
        )
        self._tts = TTSManager(
            kokoro=self._kokoro,
            voiceforge=self._voiceforge,
            mode=self._cfg.system.mode,
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

        logger.info("[C.Y.R.U.S] Loading Kokoro TTS model…")
        try:
            await loop.run_in_executor(None, self._kokoro.load)
        except Exception as exc:
            logger.warning(f"[C.Y.R.U.S] Kokoro unavailable ({exc}); will use Edge-TTS fallback")

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

        logger.info("[C.Y.R.U.S] All models initialised")

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def _pipeline_loop(self) -> None:
        """Continuous voice pipeline loop."""
        self._audio_in.open()
        self._audio_out.open()

        logger.info("[C.Y.R.U.S] Starting… Say 'Hola C.Y.R.U.S' or 'Hey C.Y.R.U.S'")
        await self._bus.emit("status", {"state": "idle", "message": "C.Y.R.U.S online — listening"})
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

        # 1. Capture audio ───────────────────────────────────────────────
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

        # 2. Transcribe ──────────────────────────────────────────────────
        await self._state.set_status(SystemStatus.PROCESSING)
        await self._bus.emit("status", {"state": "transcribing"})
        try:
            transcript, lang = self._asr.transcribe(pcm)
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] ASR failed: {exc}")
            await self._bus.emit("error", {"message": "Transcription failed — please repeat"})
            return

        if not transcript.strip():
            logger.debug("[C.Y.R.U.S] Empty transcript — ignoring")
            await self._state.set_status(SystemStatus.IDLE)
            return

        logger.info(f"[C.Y.R.U.S] Transcript: '{transcript}' [{lang}]")
        await self._bus.emit("transcript", {"text": transcript, "language": lang})

        # 3. Trigger detection ───────────────────────────────────────────
        triggered, clean_input = self._trigger.detect(transcript)
        if not triggered:
            logger.debug(f"[C.Y.R.U.S] No wake word in: '{transcript}'")
            await self._state.set_status(SystemStatus.IDLE)
            return

        if not clean_input.strip():
            # Wake word only — prompt for intent
            clean_input = "Please tell me how you'd like me to help."

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
            response = await self._llm.generate(
                clean_input,
                history=self._state.get_history_for_llm()[:-1],  # exclude the turn we just added
                language=lang,
                turn_count=self._state.turn_count,
                vision_context=vision_ctx,
                memory_context=memory_ctx,
            )
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] LLM failed: {exc}")
            response = "I'm having trouble thinking right now. Please try again."

        await self._state.add_turn("assistant", response, lang)

        # 4b. Persist both turns to memory
        if self._memory:
            try:
                await self._memory.store_turn("user", clean_input, lang)
                await self._memory.store_turn("assistant", response, lang)
            except Exception as exc:
                logger.warning(f"[C.Y.R.U.S] Memory storage failed: {exc}")
        logger.info(f"[C.Y.R.U.S] Response: '{response}'")
        await self._bus.emit("response", {"text": response, "language": lang})

        # 5. TTS synthesis & playback ────────────────────────────────────
        await self._state.set_status(SystemStatus.SPEAKING)
        await self._bus.emit("status", {"state": "speaking"})
        try:
            audio_bytes, mime = await self._tts.synthesise(response)
            if audio_bytes:
                if mime == "audio/wav":
                    await self._audio_out.play_wav(audio_bytes)
                else:
                    # MP3 from edge-tts — play via soundfile/numpy decode if needed
                    await self._play_mp3(audio_bytes)
        except Exception as exc:
            logger.error(f"[C.Y.R.U.S] TTS/playback failed: {exc}")

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
