"""
JARVIS — Main Orchestration Engine.

Entry point for the backend.  Wires together audio capture, ASR, trigger
detection, LLM reasoning, TTS synthesis, and the WebSocket broadcast layer
into a continuous async conversation loop.

Run with:
    python -m backend.core.cyrus_engine
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
import wave
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
from backend.modules.audio.remote_asr import RemoteASR
from backend.modules.audio.denoiser import Denoiser
from backend.modules.audio.speaker_intelligence import SpeakerIntelligence, SpeakerRole
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
from backend.modules.vision.remote_vision import RemoteVision
from backend.modules.vision.vision_manager import VisionManager
from backend.modules.vision.yolo_detector import YOLODetector
from backend.modules.tts.remote_tts import RemoteTTS
from backend.modules.tts.tts_manager import TTSManager
from backend.modules.tts.voiceforge_tts import VoiceforgeTTS
from backend.modules.tts.xtts_tts import XTTTS
from backend.modules.memory.embedder import Embedder
from backend.modules.memory.remote_embedder import RemoteEmbedder
from backend.modules.memory.qdrant_store import QdrantStore
from backend.modules.memory.conversation_db import ConversationDB
from backend.modules.memory.memory_manager import MemoryManager
from backend.modules.memory.fact_memory import FactMemory
from backend.modules.memory.fact_extractor import extract_and_store
from backend.modules.tracking.usage_tracker import UsageTracker
from backend.modules.planner.planner import TaskPlanner
from backend.modules.home_assistant.ha_client import HomeAssistantClient
from backend.modules.home_assistant.device_controller import DeviceController
from backend.modules.tools.registry import get_registry
from backend.modules.tools.executor import ToolExecutor
import backend.modules.tools.builtins       # registers built-in tools
import backend.modules.tools.system_tools   # registers screen/files/system tools
from backend.modules.scheduler.scheduler import AgentScheduler
from backend.modules.scheduler.briefing import MorningBriefingAgent
from backend.utils.helpers import current_time_str
from backend.utils.logger import configure_file_logging, get_logger

logger = get_logger("jarvis.engine")

# ── STT correction map ────────────────────────────────────────────────────────
# Whisper frequently mis-transcribes "JARVIS" in Spanish speech.
# Each tuple is (pattern_regex, replacement) — applied case-insensitively.
_STT_CORRECTIONS: list[tuple[str, str]] = [
    # "JARVIS" misrecognitions (Spanish phonetics)
    (r"\bjar\s*bis\b",    "jarvis"),
    (r"\bjar\s*vis\b",    "jarvis"),
    (r"\bjar\s*bees\b",   "jarvis"),
    (r"\bjar\s*wis\b",    "jarvis"),
    (r"\bjarbis\b",       "jarvis"),
    (r"\bjarbes\b",       "jarvis"),
    (r"\bharvis\b",       "jarvis"),
    (r"\byar\s*vis\b",    "jarvis"),
    (r"\byarbis\b",       "jarvis"),
    (r"\bcharbis\b",      "jarvis"),
    (r"\bsarbis\b",       "jarvis"),
    (r"\bgarvis\b",       "jarvis"),
    (r"\bjarves\b",       "jarvis"),
    (r"\btravis\b",       "jarvis"),   # English STT confusion
    (r"\bj\.a\.r\.v\.i\.s\.?\b", "jarvis"),   # spelled out
    # Spanish + name combinations that Whisper breaks
    (r"\bola\s+jar\b",    "hola jarvis"),
    (r"\boye\s+jar\b",    "oye jarvis"),
    (r"\bhey\s+jar\b",    "hey jarvis"),
]

_STT_PATTERN = None  # compiled lazily


def _compile_stt_patterns() -> list[tuple]:
    import re
    return [(re.compile(p, re.IGNORECASE), r) for p, r in _STT_CORRECTIONS]


def _correct_transcript(text: str) -> str:
    """Apply STT correction map to fix common Whisper misrecognitions."""
    global _STT_PATTERN
    if _STT_PATTERN is None:
        _STT_PATTERN = _compile_stt_patterns()
    for pattern, replacement in _STT_PATTERN:
        text = pattern.sub(replacement, text)
    return text


class JARVISEngine:
    """Main JARVIS orchestration engine.

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
            noise_gate_factor=getattr(ai_cfg, "noise_gate_factor", 3.5),
            noise_calibration_secs=getattr(ai_cfg, "noise_calibration_secs", 2.0),
            speaker_gate_enabled=getattr(ai_cfg, "speaker_gate_enabled", True),
        )
        ao_cfg = self._cfg.audio.output
        self._audio_out = AudioOutput(
            volume=ao_cfg.volume,
            sample_rate=ao_cfg.sample_rate,
            device_name=ao_cfg.device,
        )

        # ── Denoiser ───────────────────────────────────────────────────────
        self._denoiser = Denoiser(
            sample_rate=ai_cfg.sample_rate,
            prop_decrease=0.75,
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
        # RemoteASR — external ASR server (faster-whisper-server / OpenAI-compat)
        svc_asr = self._cfg.services.asr
        self._remote_asr: RemoteASR | None = RemoteASR(
            host=svc_asr.host,
            language=svc_asr.language,
            timeout=svc_asr.timeout,
            sample_rate=self._cfg.audio.input.sample_rate,
        ) if svc_asr.enabled else None

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
        # ── Tool executor (ReAct loop for web search, files, system, etc.) ──
        self._tools = ToolExecutor(
            registry=get_registry(),
            ollama=self._ollama,
        )
        _tool_names = get_registry().names()
        logger.info(f"[JARVIS] Tools registered: {_tool_names}")

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
        _xtts_ref = None
        if xtts_cfg:
            _ref_str = getattr(xtts_cfg, "reference_voice", None)
            if _ref_str:
                _ref_path = self._cfg.project_root / _ref_str
                _xtts_ref = str(_ref_path) if _ref_path.is_file() else None
        self._xtts = XTTTS(
            language=getattr(xtts_cfg, "language", "es") if xtts_cfg else "es",
            speaker=getattr(xtts_cfg, "speaker", "Tammie Ema") if xtts_cfg else "Tammie Ema",
            speed=tts_local_cfg.speed,
            reference_wav=_xtts_ref,
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
        svc_vis = self._cfg.services.vision
        self._vision: VisionManager | RemoteVision | None = None

        if svc_vis.enabled:
            # RemoteVision takes priority over in-process VisionManager
            self._vision = RemoteVision(host=svc_vis.host, timeout=svc_vis.timeout)
        elif vis_cfg and getattr(vis_cfg, "enabled", False):
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

        # ── Memory ────────────────────────────────────────────────────────
        mem_cfg = getattr(self._cfg, "memory", None)
        svc_emb = self._cfg.services.embedder
        self._memory: MemoryManager | None = None
        if mem_cfg and getattr(mem_cfg, "enabled", False):
            qd = mem_cfg.qdrant
            emb_cfg = mem_cfg.embedder
            # Use RemoteEmbedder if configured, otherwise in-process Embedder
            if svc_emb.enabled:
                self._embedder: Embedder | RemoteEmbedder = RemoteEmbedder(
                    host=svc_emb.host,
                    timeout=svc_emb.timeout,
                )
            else:
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

        # ── Fact Memory (always enabled — SQLite FTS5, no Qdrant needed) ─
        _facts_path = str(self._cfg.project_root / "data" / "facts.db")
        self._fact_memory = FactMemory(db_path=_facts_path)

        # ── Usage tracker ─────────────────────────────────────────────────
        _usage_path = str(self._cfg.project_root / "data" / "usage.jsonl")
        self._usage = UsageTracker(log_path=_usage_path)
        # Expose as module-level singleton so uso_jarvis tool can find it
        import backend.modules.tools.builtins as _bt
        _bt._JARVIS_USAGE_TRACKER = self._usage

        # ── Planner ───────────────────────────────────────────────────────
        planner_cfg = getattr(self._cfg, "planner", None)
        planner_enabled = planner_cfg and getattr(planner_cfg, "enabled", True)
        if planner_enabled:
            self._planner = TaskPlanner(
                db_path=str(self._cfg.project_root / getattr(planner_cfg, "db_path", "data/planner.db")),
                max_tasks=getattr(planner_cfg, "max_tasks", 100),
            )
        else:
            self._planner = TaskPlanner(db_path=str(self._cfg.project_root / "data/planner.db"))

        # ── Scheduler ─────────────────────────────────────────────────────
        self._scheduler = AgentScheduler(tick_secs=30.0)
        self._briefing_agent = MorningBriefingAgent(
            ollama=self._ollama,
            planner=self._planner,
            city=getattr(getattr(self._cfg, "scheduler", None), "weather_city", "Lima"),
        )

        # ── Home Assistant (Phase 4) ───────────────────────────────────────
        ha_cfg = getattr(self._cfg, "home_assistant", None)
        self._ha_client: HomeAssistantClient | None = None
        self._ha_controller: DeviceController | None = None
        if ha_cfg and getattr(ha_cfg, "enabled", False):
            _ha_token = getattr(ha_cfg, "token", "")
            if _ha_token and _ha_token not in ("${HA_TOKEN}", ""):
                self._ha_client = HomeAssistantClient(
                    base_url=ha_cfg.base_url,
                    token=_ha_token,
                    timeout=getattr(ha_cfg, "timeout", 10),
                    verify_ssl=getattr(ha_cfg, "verify_ssl", True),
                )
                self._ha_controller = DeviceController(client=self._ha_client)

        # ── Speaker Intelligence ───────────────────────────────────────────
        spk_cfg = self._cfg.speaker
        self._speaker_intel = SpeakerIntelligence(
            data_dir=str(self._cfg.project_root / spk_cfg.data_dir),
            model_dir=str(self._cfg.project_root / spk_cfg.model_dir),
            threshold=spk_cfg.threshold,
            adaptive_lr=spk_cfg.adaptive_lr,
            sample_rate=ai_cfg.sample_rate,
        )
        # Expose speaker intel as singleton so tools can access it
        import backend.modules.tools.system_tools as _st
        _st._JARVIS_SPEAKER_INTEL = self._speaker_intel

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
        loop = asyncio.get_running_loop()

        # RemoteASR — probe if enabled, otherwise load local Whisper
        if self._remote_asr is not None:
            logger.info(f"[JARVIS] Probing RemoteASR server at {self._cfg.services.asr.host}…")
            ok = await self._remote_asr.check_health()
            if ok:
                logger.info("[JARVIS] RemoteASR server ready — skipping local Whisper load")
            else:
                logger.warning("[JARVIS] RemoteASR server not reachable — falling back to local Whisper")
                self._remote_asr = None   # disable so pipeline uses local ASR

        if self._remote_asr is None:
            logger.info("[JARVIS] Loading Whisper ASR model…")
            await loop.run_in_executor(None, self._asr.load)

        # Try Piper first (best quality) — non-fatal if unavailable
        if getattr(self._cfg.local.tts, "piper_model", ""):
            logger.info("[JARVIS] Loading Piper TTS model…")
            try:
                await loop.run_in_executor(None, self._piper.load)
                logger.info(f"[JARVIS] Piper ready — active backend: piper")
            except Exception as exc:
                logger.warning(f"[JARVIS] Piper unavailable ({exc}); falling back to Kokoro")

        logger.info("[JARVIS] Loading Kokoro TTS model…")
        try:
            await loop.run_in_executor(None, self._kokoro.load)
        except Exception as exc:
            logger.warning(f"[JARVIS] Kokoro unavailable ({exc}); will use Edge-TTS fallback")

        # RemoteTTS — probe the external server if enabled
        if self._remote_tts is not None:
            logger.info(f"[JARVIS] Probing RemoteTTS server at {self._cfg.services.tts.host}…")
            ok = await self._remote_tts.check_health()
            if ok:
                logger.info("[JARVIS] RemoteTTS server ready — active backend: remote-tts")
            else:
                logger.warning("[JARVIS] RemoteTTS server not reachable — will fall through to next backend")

        # XTTS v2 — only load if explicitly enabled in config
        xtts_cfg = getattr(self._cfg.local.tts, "xtts", None)
        if xtts_cfg and getattr(xtts_cfg, "enabled", False):
            logger.info("[JARVIS] Loading XTTS v2 model…")
            try:
                await loop.run_in_executor(None, self._xtts.load)
                logger.info("[JARVIS] XTTS v2 ready")
            except Exception as exc:
                logger.warning(f"[JARVIS] XTTS v2 unavailable ({exc})")

        logger.info("[JARVIS] Checking Ollama availability…")
        if not await self._ollama.is_available():
            logger.warning("[JARVIS] Ollama not responding — API fallback will be used")
        else:
            logger.info("[JARVIS] Ollama is online")

        if self._vision:
            logger.info("[JARVIS] Starting vision pipeline…")
            await self._vision.start()
            import backend.modules.tools.system_tools as _st
            _st._JARVIS_VISION = self._vision

        if self._memory:
            if isinstance(self._embedder, RemoteEmbedder):
                logger.info(f"[JARVIS] Probing RemoteEmbedder at {self._cfg.services.embedder.host}…")
                ok = await self._embedder.check_health()
                if not ok:
                    logger.warning("[JARVIS] RemoteEmbedder not reachable — memory search disabled")
            else:
                logger.info("[JARVIS] Loading embedder model…")
                await loop.run_in_executor(None, self._embedder.load)
            logger.info("[JARVIS] Connecting to Qdrant…")
            try:
                self._qdrant_store.connect()
            except Exception as exc:
                logger.warning(f"[JARVIS] Qdrant unavailable ({exc}); memory search disabled")
            self._conv_db.init()
            logger.info(f"[JARVIS] Memory session: {self._memory.session_id}")

        # ── Fact Memory ────────────────────────────────────────────────────
        self._fact_memory.init()
        fact_count = self._fact_memory.count()
        logger.info(f"[JARVIS] FactMemory ready — {fact_count} facts stored")

        # ── Home Assistant ─────────────────────────────────────────────────
        if self._ha_client is not None:
            logger.info("[JARVIS] Checking Home Assistant connection…")
            await self._ha_client.check_connection()
            if self._ha_client.available:
                logger.info("[JARVIS] Home Assistant connected")
            else:
                logger.warning("[JARVIS] Home Assistant not reachable — automation disabled")

        # ── Speaker Intelligence (ECAPA-TDNN) ─────────────────────────────
        logger.info("[JARVIS] Loading speaker intelligence model...")
        await loop.run_in_executor(None, self._speaker_intel.load)
        enrolled = self._speaker_intel.list_speakers()
        if enrolled:
            logger.info(f"[JARVIS] Speaker profiles loaded: {[s['id'] for s in enrolled]}")
        else:
            logger.info("[JARVIS] No speaker profiles enrolled — all voices accepted as UNKNOWN")

        logger.info("[JARVIS] All models initialised")

        # Broadcast service status to frontend
        await self._emit_service_status()

    # ------------------------------------------------------------------
    # Service status helper
    # ------------------------------------------------------------------

    async def _emit_service_status(self) -> None:
        """Probe all configured microservices and emit their status to frontend."""
        svc = self._cfg.services

        async def _probe(enabled: bool, host: str) -> dict:
            # Always do a fresh HTTP probe so status reflects the current moment,
            # not a cached value from startup.
            try:
                import httpx
                async with httpx.AsyncClient(timeout=2.0) as c:
                    r = await c.get(f"{host}/health")
                    online = r.status_code < 500
            except Exception:
                online = False
            return {"enabled": enabled, "online": online, "host": host}

        tts_info, asr_info, vis_info, emb_info = await asyncio.gather(
            _probe(svc.tts.enabled,      svc.tts.host),
            _probe(svc.asr.enabled,      svc.asr.host),
            _probe(svc.vision.enabled,   svc.vision.host),
            _probe(svc.embedder.enabled, svc.embedder.host),
        )

        await self._bus.emit("service_status", {
            "tts":      tts_info,
            "asr":      asr_info,
            "vision":   vis_info,
            "embedder": emb_info,
        })

    # ------------------------------------------------------------------
    # Voice-triggered enrollment intercepts
    # ------------------------------------------------------------------

    _ENROLL_OWNER_PATTERNS = [
        "registra mi voz", "enróllame la voz", "enrolla mi voz",
        "aprende mi voz", "reconóceme la voz", "registra quien soy",
        "start enrollment", "enroll owner",
    ]
    _ENROLL_GUEST_RE = re.compile(
        r"(?:registra|enrólla|enrolla|aprende)\s+(?:la\s+)?voz\s+de\s+(\w+)", re.IGNORECASE
    )
    _FACE_OWNER_PATTERNS = [
        "registra mi cara", "enróllame la cara", "aprende mi cara",
        "reconóceme la cara", "registra mi rostro", "aprende mi rostro",
    ]
    _FACE_GUEST_RE = re.compile(
        r"(?:registra|enrólla|enrolla|aprende)\s+(?:la\s+)?(?:cara|rostro)\s+de\s+(\w+)", re.IGNORECASE
    )

    async def _check_enrollment_voice_command(self, text: str) -> Optional[str]:
        """Check if the utterance is an enrollment command and dispatch if so.

        Returns a non-None string if enrollment was triggered (caller should return).
        Returns None if this is a normal query.
        """
        low = text.lower().strip()

        # Speaker enrollment — owner
        if any(p in low for p in self._ENROLL_OWNER_PATTERNS):
            if not self._enrollment_active:
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.OWNER, "owner", 6))
            return "enrollment_started"

        # Speaker enrollment — guest
        m = self._ENROLL_GUEST_RE.search(low)
        if m:
            guest_name = m.group(1).lower()
            if not self._enrollment_active:
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.GUEST, guest_name, 5))
            return "enrollment_started"

        # Face enrollment — owner
        if any(p in low for p in self._FACE_OWNER_PATTERNS):
            owner_name = getattr(getattr(self._cfg, "system", None), "owner_name", "Ricardo")
            if not self._enrollment_active:
                asyncio.create_task(self._run_face_enrollment(owner_name.lower()))
            return "face_enrollment_started"

        # Face enrollment — guest
        m = self._FACE_GUEST_RE.search(low)
        if m:
            guest_name = m.group(1).lower()
            if not self._enrollment_active:
                asyncio.create_task(self._run_face_enrollment(guest_name))
            return "face_enrollment_started"

        return None

    async def _run_face_enrollment(self, name: str, n_frames: int = 8) -> None:
        """Capture N frames from camera and save to face DB for recognition."""
        if not self._vision:
            await self._speak_text("No tengo acceso a la cámara en este momento.")
            return

        self._enrollment_active = True
        try:
            face_dir = self._cfg.project_root / "data" / "faces" / name
            face_dir.mkdir(parents=True, exist_ok=True)

            await self._speak_text(f"Voy a registrar la cara de {name}. Mira a la cámara.")
            await asyncio.sleep(1.0)

            loop = asyncio.get_running_loop()
            saved = 0
            for i in range(n_frames):
                await asyncio.sleep(0.5)
                try:
                    ctx   = self._vision.get_context()
                    frame = ctx.frame if ctx else None
                    if frame is not None:
                        import cv2
                        img_path = face_dir / f"{name}_{i:02d}.jpg"
                        cv2.imwrite(str(img_path), frame)
                        saved += 1
                        await self._bus.emit("debug", {"text": f"📸 Cara {i+1}/{n_frames} guardada", "level": "info"})
                except Exception as exc:
                    logger.warning(f"[JARVIS] Face frame {i} capture failed: {exc}")

            if saved >= 3:
                await self._speak_text(f"Cara de {name} registrada con {saved} imágenes. Ahora puedo reconocerte.")
                await self._bus.emit("face_enrolled", {"name": name, "frames": saved})
            else:
                await self._speak_text("No pude capturar suficientes imágenes. Asegúrate de que la cámara esté activa.")
        finally:
            self._enrollment_active = False

    # ------------------------------------------------------------------
    # Fact extraction (background, post-turn)
    # ------------------------------------------------------------------

    async def _extract_facts(self, user_msg: str, jarvis_msg: str) -> None:
        """Extract and store facts from a completed exchange. Never raises."""
        try:
            await extract_and_store(
                user_msg=user_msg,
                jarvis_msg=jarvis_msg,
                fact_memory=self._fact_memory,
                ollama=self._ollama,
            )
        except Exception as exc:
            logger.debug(f"[JARVIS] FactExtractor background task failed: {exc}")

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
                logger.debug(f"[JARVIS] Stats loop error: {exc}")

            await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # TTS helper (used by test_tts command and enrollment)
    # ------------------------------------------------------------------

    async def _barge_in_watcher(self) -> None:
        """Background task — monitors mic for speech while JARVIS is speaking.
        If the user starts talking, interrupt playback immediately."""
        try:
            detected = await self._audio_in.detect_speech_onset(timeout=60.0)
            if detected:
                logger.info("[JARVIS] Barge-in detected — interrupting playback")
                self._audio_out.interrupt()
                await self._bus.emit("debug", {"text": "⚡ Interrupción detectada", "level": "warn"})
                # Clear the mute so the next record_utterance() hears the user
                self._audio_in.mute_for(0.0)
        except asyncio.CancelledError:
            pass  # Normal: cancelled when JARVIS finishes speaking
        finally:
            # Always release the barge-in stream so the device is free for
            # the next record_utterance() call (fixes WASAPI exclusive deadlock).
            self._audio_in.stop_barge_in()

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
                    try:
                        _pb, _pr, _dur = self._decode_to_pcm(audio_bytes, mime)
                    except Exception:
                        _pb, _pr, _dur = None, 24000, 5.0
                    _echo_tail = getattr(
                        getattr(getattr(self._cfg, "audio", None), "input", None),
                        "echo_tail_secs", 1.5
                    )
                    self._audio_in.mute_for(_dur + _echo_tail)
                    if _pb is not None:
                        await self._audio_out.play_pcm(_pb, sample_rate=_pr)
                    elif mime == "audio/wav":
                        await self._audio_out.play_wav(audio_bytes)
                    else:
                        await self._play_mp3(audio_bytes)
                    self._audio_in.mute_for(_echo_tail)
            except Exception as exc:
                logger.error(f"[JARVIS] _speak_text failed: {exc}")
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
            logger.info(f"[JARVIS] Wake words saved to config: {self._trigger.wake_words}")
        except Exception as exc:
            logger.error(f"[JARVIS] Failed to save wake words: {exc}")

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
            logger.info(f"[JARVIS] Local LLM model saved to config: {self._ollama._model}")
        except Exception as exc:
            logger.error(f"[JARVIS] Failed to save local LLM model: {exc}")

    async def _run_enrollment(self, samples: int = 5) -> None:
        """Record N samples, transcribe each, register wake-word variants, and build voice profile."""
        # DEPRECATED: SpeakerProfile removed in Voice Intelligence v2.
        # Use _run_neural_enrollment() instead.
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
                logger.warning(f"[JARVIS] Enrollment TTS failed: {exc}")

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
                logger.warning(f"[JARVIS] Enrollment recording failed: {exc}")
                continue

            if not pcm:
                await self._bus.emit("enrollment", {"step": "result", "sample": i, "heard": "(silencio)"})
                continue

            pcm_samples.append(pcm)  # keep for voice profile

            # Transcribe with no initial_prompt so we capture raw perception
            try:
                if self._remote_asr is not None:
                    text, lang = await self._remote_asr.atranscribe(
                        pcm, self._cfg.audio.input.sample_rate
                    )
                else:
                    orig_prompt = self._asr._initial_prompt
                    self._asr._initial_prompt = None
                    try:
                        text, lang = self._asr.transcribe(pcm)
                    finally:
                        self._asr._initial_prompt = orig_prompt
            except Exception as exc:
                logger.warning(f"[JARVIS] Enrollment ASR failed: {exc}")
                text = ""

            heard = _correct_transcript(text.strip()).lower()
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
            logger.warning("[JARVIS] Legacy enrollment: SpeakerProfile removed — use neural enrollment commands instead")

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
                logger.warning(f"[JARVIS] Enrollment summary TTS failed: {exc}")

        self._enrollment_active = False
        await self._bus.emit("status", {"state": "idle"})
        await self._bus.emit("enrollment", {"step": "idle"})

    async def _run_neural_enrollment(self, role: SpeakerRole, name: str, samples: int = 5) -> None:
        """Record samples and enroll speaker with ECAPA-TDNN."""
        self._enrollment_active = True
        try:
            self._audio_in.request_stop()
            await asyncio.sleep(0.5)

            role_str = "propietario" if role == SpeakerRole.OWNER else f"invitado '{name}'"
            intro = f"Enrollamiento neural para {role_str}. Voy a pedirte que hables {samples} veces. Habla con naturalidad."

            await self._bus.emit("enrollment", {"step": "start", "total": samples, "role": role.value, "name": name})
            await self._bus.emit("status", {"state": "speaking"})
            await self._bus.emit("response", {"text": intro, "language": "es"})
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(intro)
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception:
                    pass

            pcm_samples: list[bytes] = []
            for i in range(1, samples + 1):
                await self._bus.emit("enrollment", {"step": "prompt", "sample": i, "total": samples})
                async with self._audio_lock:
                    try:
                        ab, mime = await self._tts.synthesise(f"Muestra {i}.")
                        if ab:
                            await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                    except Exception:
                        pass
                await asyncio.sleep(0.3)
                try:
                    pcm = await self._audio_in.record_utterance()
                    if pcm:
                        pcm_samples.append(pcm)
                    await self._bus.emit("enrollment", {"step": "result", "sample": i, "heard": f"Muestra {i} {'OK' if pcm else '(silencio)'}"})
                except Exception as exc:
                    logger.warning(f"[JARVIS] Neural enrollment recording failed: {exc}")

            if pcm_samples:
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self._speaker_intel.enroll(role, name, pcm_samples),
                    )
                    speakers = self._speaker_intel.list_speakers()
                    await self._bus.emit("speaker_profiles", {"speakers": speakers})
                    summary = f"Perfil de voz registrado para {role_str} con {len(pcm_samples)} muestras."
                    await self._bus.emit("debug", {"text": f"✓ {summary}", "level": "ok"})
                except Exception as exc:
                    summary = f"No se pudo registrar el perfil: {exc}"
                    logger.warning(f"[JARVIS] Neural enrollment failed: {exc}")
            else:
                summary = "No se detectó audio. Intenta en un ambiente más silencioso."

            await self._bus.emit("enrollment", {"step": "done", "added": [name] if pcm_samples else []})
            await self._bus.emit("status", {"state": "speaking"})
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(summary)
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception:
                    pass
        finally:
            self._enrollment_active = False
            await self._bus.emit("status", {"state": "idle"})
            await self._bus.emit("enrollment", {"step": "idle"})

    async def _record_tts_reference(self) -> None:
        """Record 20s of voice as XTTS cloning reference."""
        self._enrollment_active = True
        try:
            self._audio_in.request_stop()
            await asyncio.sleep(0.3)

            ref_dir  = self._cfg.project_root / "data" / "tts"
            ref_dir.mkdir(parents=True, exist_ok=True)
            ref_path = ref_dir / "reference_voice.wav"

            intro = "Voy a grabar tu voz como referencia para la síntesis. Habla durante 20 segundos sobre cualquier tema."
            await self._bus.emit("status", {"state": "speaking"})
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(intro)
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception:
                    pass

            await asyncio.sleep(0.5)
            await self._bus.emit("debug", {"text": "🎙 Grabando referencia TTS (20s)...", "level": "info"})

            pcm_chunks: list[bytes] = []
            _sr = self._cfg.audio.input.sample_rate
            target_bytes = _sr * 2 * 20  # 20 seconds
            collected = 0
            while collected < target_bytes:
                try:
                    pcm = await self._audio_in.record_utterance()
                    if pcm:
                        pcm_chunks.append(pcm)
                        collected += len(pcm)
                except Exception:
                    break

            if pcm_chunks:
                combined = b"".join(pcm_chunks)
                with wave.open(str(ref_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(_sr)
                    wf.writeframes(combined)
                self._xtts.set_reference(str(ref_path))
                await self._bus.emit("debug", {"text": f"✓ Referencia TTS guardada: {ref_path.name}", "level": "ok"})
                summary = "Referencia de voz guardada. La síntesis de voz ahora usará tu voz como modelo."
            else:
                summary = "No se detectó audio para la referencia."

            await self._bus.emit("status", {"state": "speaking"})
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(summary)
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception:
                    pass
        finally:
            self._enrollment_active = False
            await self._bus.emit("status", {"state": "idle"})

    async def _greet(self) -> None:
        """Synthesise and play the startup greeting in Spanish."""
        GREETING = (
            "Hola. Soy JARVIS, tu asistente de inteligencia artificial. "
            "Todos los sistemas están en línea. "
            "Menciona mi nombre cuando necesites asistencia."
        )
        logger.info("[JARVIS] Playing startup greeting")
        await self._bus.emit("status", {"state": "speaking"})
        await self._bus.emit("response", {"text": GREETING, "language": "es"})
        async with self._audio_lock:
            try:
                audio_bytes, mime = await self._tts.synthesise(GREETING)
                if audio_bytes:
                    try:
                        pcm_b, pcm_r, dur = self._decode_to_pcm(audio_bytes, mime)
                    except Exception:
                        pcm_b, pcm_r, dur = None, 24000, 5.0
                    self._audio_in.mute_for(dur + 5.0)
                    if pcm_b is not None:
                        await self._audio_out.play_pcm(pcm_b, sample_rate=pcm_r)
                    elif mime == "audio/wav":
                        await self._audio_out.play_wav(audio_bytes)
                    else:
                        await self._play_mp3(audio_bytes)
                    # tail already included — do not reset mute
            except Exception as exc:
                logger.warning(f"[JARVIS] Greeting TTS failed: {exc}")
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
        logger.info("[JARVIS] All clients disconnected — pausing mic")
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
                logger.info(f"[JARVIS] Wake word added via UI: '{word}'")
                await self._bus.emit("wake_words", {"words": self._trigger.wake_words})
                await self._bus.emit("debug", {"text": f"✓ Wake word '{word}' registrado", "level": "ok"})
        elif cmd == "remove_wake_word":
            word = str(payload.get("word", "")).strip().lower()
            self._trigger.remove_wake_word(word)
            await self._save_wake_words()
            await self._bus.emit("wake_words", {"words": self._trigger.wake_words})
            await self._bus.emit("debug", {"text": f"✗ Wake word '{word}' eliminado", "level": "warn"})
        elif cmd == "start_enrollment":
            # Redirected to neural enrollment (SpeakerProfile removed)
            if not self._enrollment_active:
                samples = int(payload.get("samples", 8))
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.OWNER, "owner", samples))

        elif cmd == "start_owner_enrollment":
            if not self._enrollment_active:
                samples = int(payload.get("samples", 8))
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.OWNER, "owner", samples))

        elif cmd == "start_guest_enrollment":
            if not self._enrollment_active:
                name    = str(payload.get("name", "guest")).strip().lower()
                name    = re.sub(r'[^\w\-]', '_', name)[:32] or "guest"
                samples = int(payload.get("samples", 5))
                asyncio.create_task(self._run_neural_enrollment(SpeakerRole.GUEST, name, samples))

        elif cmd == "remove_speaker":
            sid = str(payload.get("speaker_id", "")).strip()
            if sid:
                self._speaker_intel.remove_speaker(sid)
                speakers = self._speaker_intel.list_speakers()
                await self._bus.emit("speaker_profiles", {"speakers": speakers})
                await self._bus.emit("debug", {"text": f"✗ Perfil de voz eliminado: {sid}", "level": "warn"})

        elif cmd == "list_speakers":
            speakers = self._speaker_intel.list_speakers()
            await self._bus.emit("speaker_profiles", {"speakers": speakers})

        elif cmd == "record_tts_reference":
            if not self._enrollment_active:
                asyncio.create_task(self._record_tts_reference())

        elif cmd == "set_tts_speed":
            speed = float(payload.get("speed", 1.0))
            self._tts.set_speed(speed)
            logger.info(f"[JARVIS] TTS speed → {speed}")
            await self._bus.emit("debug", {"text": f"TTS speed ajustada a {speed:.2f}", "level": "ok"})

        elif cmd == "test_tts":
            text = str(payload.get("text", "Sistema de voz operativo. JARVIS en línea.")).strip()
            if text and not self._enrollment_active:
                asyncio.create_task(self._speak_text(text))

        elif cmd == "set_local_ai_detector":
            detector = str(payload.get("detector", "ollama")).strip().lower()
            if detector == "ollama":
                self._local_ai_detector = "ollama"
                logger.info("[JARVIS] Local AI detector set to Ollama")
                await self._bus.emit("debug", {"text": "Detector local: Ollama", "level": "ok"})
            else:
                logger.warning(f"[JARVIS] Unsupported local AI detector: {detector}")
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
                    logger.warning(f"[JARVIS] Ollama probe failed: {exc}")
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
                logger.warning(f"[JARVIS] Could not list Ollama models: {exc}")
                await self._bus.emit("debug", {"text": "No se pudieron obtener los modelos de Ollama.", "level": "warn"})

        elif cmd == "set_tts_engine":
            engine = str(payload.get("engine", "")).strip().lower()
            valid = {"piper", "remote-tts", "xtts", "kokoro", "edge-tts"}
            if engine in valid:
                # Check backend is actually available before pinning
                unavailable = (
                    (engine == "piper"      and (not self._piper or not self._piper.available)) or
                    (engine == "remote-tts" and (not self._remote_tts or not self._remote_tts.available)) or
                    (engine == "xtts"       and (not self._xtts or not self._xtts.available))
                )
                self._tts.set_forced_backend(engine)
                if unavailable:
                    await self._bus.emit("debug", {
                        "text": f"Motor TTS '{engine}' no disponible — usando fallback automatico",
                        "level": "warn",
                    })
                else:
                    await self._bus.emit("debug", {"text": f"Motor TTS fijado a: {engine}", "level": "ok"})
            elif engine == "auto":
                self._tts.set_forced_backend(None)
                await self._bus.emit("debug", {"text": "Motor TTS: prioridad automatica restaurada", "level": "ok"})
            else:
                await self._bus.emit("debug", {"text": f"Motor TTS desconocido: {engine}", "level": "warn"})

        elif cmd == "set_voice_preset":
            preset = str(payload.get("preset", "natural")).strip().lower()
            self._tts.set_voice_preset(preset)
            await self._bus.emit("debug", {"text": f"Preset de voz: {preset}", "level": "ok"})

        elif cmd == "planner_list":
            tasks = self._planner.get_pending()
            await self._bus.emit("planner_tasks", {"tasks": [t.to_dict() for t in tasks]})

        elif cmd == "planner_add":
            desc = str(payload.get("description", "")).strip()
            if desc:
                task = self._planner.add_task(desc, due_hint=payload.get("due_hint"))
                tasks = self._planner.get_pending()
                await self._bus.emit("planner_tasks", {"tasks": [t.to_dict() for t in tasks]})
                await self._bus.emit("debug", {"text": f"📋 Tarea agregada: {task.description}", "level": "ok"})

        elif cmd == "planner_complete":
            tid = int(payload.get("task_id", 0))
            self._planner.complete_task(tid)
            tasks = self._planner.get_pending()
            await self._bus.emit("planner_tasks", {"tasks": [t.to_dict() for t in tasks]})
            await self._bus.emit("debug", {"text": f"📋 Tarea #{tid} completada", "level": "ok"})

        elif cmd == "planner_cancel":
            tid = int(payload.get("task_id", 0))
            self._planner.cancel_task(tid)
            tasks = self._planner.get_pending()
            await self._bus.emit("planner_tasks", {"tasks": [t.to_dict() for t in tasks]})
            await self._bus.emit("debug", {"text": f"📋 Tarea #{tid} cancelada", "level": "warn"})

        elif cmd == "set_llm_model":
            model = str(payload.get("model", "")).strip()
            if model:
                self._ollama._model = model
                logger.info(f"[JARVIS] LLM model → {model}")
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

        elif cmd == "probe_services":
            await self._bus.emit("debug", {"text": "Comprobando servicios API...", "level": "info"})
            await self._emit_service_status()

        elif cmd == "scheduler_list":
            jobs = self._scheduler.list_jobs()
            await self._bus.emit("scheduler_jobs", {"jobs": jobs})

        elif cmd == "scheduler_trigger":
            job_id = str(payload.get("job_id", "briefing_matutino"))
            ok = await self._scheduler.trigger(job_id)
            await self._bus.emit("debug", {
                "text": f"☀ Briefing manual disparado: {job_id}" if ok else f"Job '{job_id}' no encontrado",
                "level": "ok" if ok else "warn",
            })

        elif cmd == "briefing_now":
            # Direct shortcut to trigger briefing without knowing job_id
            asyncio.create_task(self._run_briefing())
            await self._bus.emit("debug", {"text": "☀ Briefing matutino en curso…", "level": "info"})

        elif cmd == "scheduler_set_time":
            new_time = str(payload.get("time", "07:00")).strip()
            job = self._scheduler._jobs.get("briefing_matutino")
            if job:
                job.schedule = f"daily {new_time}"
                job.compute_next_fire()
                await self._bus.emit("debug", {"text": f"☀ Briefing reprogramado a las {new_time}", "level": "ok"})
                await self._bus.emit("scheduler_jobs", {"jobs": self._scheduler.list_jobs()})

    # ------------------------------------------------------------------
    # Scheduler helpers
    # ------------------------------------------------------------------

    async def _run_briefing(self) -> None:
        """Generate and play the morning briefing."""
        logger.info("[JARVIS] Running morning briefing…")
        await self._bus.emit("debug", {"text": "☀ Generando briefing matutino…", "level": "info"})

        try:
            text = await self._briefing_agent.generate()
        except Exception as exc:
            logger.error(f"[JARVIS] Briefing generation failed: {exc}")
            return

        await self._bus.emit("response", {"text": text, "language": "es"})
        await self._bus.emit("debug", {"text": f"☀ Briefing: {text[:80]}…", "level": "ok"})

        # Speak briefing through TTS pipeline
        if self._audio_lock is None:
            return
        try:
            await self._bus.emit("status", {"state": "speaking"})
            audio_bytes, mime = await self._tts.synthesise(text)
            if audio_bytes:
                pcm_b, pcm_r, dur = self._decode_to_pcm(audio_bytes, mime)
                self._audio_in.mute_for(dur + 5.0)
                async with self._audio_lock:
                    await self._audio_out.play_pcm(pcm_b, sample_rate=pcm_r)
            await self._bus.emit("status", {"state": "idle"})
        except Exception as exc:
            logger.error(f"[JARVIS] Briefing TTS/playback failed: {exc}")
            await self._bus.emit("status", {"state": "idle"})

    async def _on_scheduler_event(self, job_id: str, payload: dict) -> None:
        """Forward scheduler events to the frontend."""
        await self._bus.emit("scheduler_event", payload)
        if payload.get("event") == "error":
            await self._bus.emit("debug", {
                "text": f"⚠ Tarea '{job_id}' falló: {payload.get('last_error', '')}",
                "level": "warn",
            })

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

        # ── Scheduler setup ────────────────────────────────────────────────
        sched_cfg = getattr(self._cfg, "scheduler", None)
        briefing_time = getattr(sched_cfg, "briefing_time", "07:00") if sched_cfg else "07:00"
        briefing_enabled = getattr(sched_cfg, "enabled", True) if sched_cfg else True

        if briefing_enabled:
            self._scheduler.register(
                job_id="briefing_matutino",
                label="Briefing matutino",
                fn=self._run_briefing,
                schedule=f"daily {briefing_time}",
            )
            self._scheduler.on_job_event(self._on_scheduler_event)
            self._scheduler.start()
            logger.info(f"[JARVIS] Scheduler started — briefing at {briefing_time}")

        logger.info("[JARVIS] Starting… Say 'Hola JARVIS' or 'Hey JARVIS'")
        await self._bus.emit("status", {"state": "idle", "message": "JARVIS online"})
        await self._state.set_status(SystemStatus.IDLE)

        try:
            while True:
                await self._process_one_turn()
        except KeyboardInterrupt:
            logger.info("[JARVIS] Interrupted — shutting down")
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
            logger.error(f"[JARVIS] Audio capture failed: {exc}")
            await asyncio.sleep(0.5)
            return

        if not pcm:
            return

        # Denoise PCM before further processing
        pcm = self._denoiser.process(pcm)

        # Gate: discard utterances shorter than 600 ms — almost certainly noise.
        # 16 kHz × 2 bytes × 0.6 s = 19 200 bytes
        _MIN_PCM = int(self._cfg.audio.input.sample_rate * 2 * 0.60)
        if len(pcm) < _MIN_PCM:
            logger.debug(f"[JARVIS] PCM too short ({len(pcm)} B < {_MIN_PCM} B) — discarded")
            await asyncio.sleep(0.05)
            return

        # Speaker Intelligence — identify who is speaking
        speaker_result = await asyncio.get_running_loop().run_in_executor(
            None, self._speaker_intel.identify, pcm
        )
        logger.debug(f"[JARVIS] Speaker: {speaker_result.speaker_id} ({speaker_result.role.value}) conf={speaker_result.confidence:.2f}")
        _speaker_result = speaker_result
        _speaker_role   = speaker_result.role
        _speaker_id     = speaker_result.speaker_id

        # 2. Transcribe ──────────────────────────────────────────────────
        await self._state.set_status(SystemStatus.PROCESSING)
        await self._bus.emit("status", {"state": "transcribing"})
        try:
            if self._remote_asr is not None:
                transcript, lang = await self._remote_asr.atranscribe(
                    pcm, self._cfg.audio.input.sample_rate
                )
            else:
                transcript, lang = await asyncio.get_running_loop().run_in_executor(
                    None, self._asr.transcribe, pcm
                )
        except Exception as exc:
            logger.error(f"[JARVIS] ASR failed: {exc}")
            await self._bus.emit("error", {"message": "Transcription failed — please repeat"})
            await self._state.set_status(SystemStatus.LISTENING)
            await self._bus.emit("status", {"state": "listening"})
            return

        # Apply STT correction map (Whisper Spanish misrecognitions of "JARVIS")
        corrected = _correct_transcript(transcript)
        if corrected != transcript:
            logger.info(f"[JARVIS] STT corrected: '{transcript}' → '{corrected}'")
            await self._bus.emit("debug", {
                "text": f"STT corrected: \"{transcript}\" → \"{corrected}\"",
                "level": "info",
            })
            transcript = corrected

        if not transcript.strip():
            logger.debug("[JARVIS] Empty transcript — ignoring")
            # Return to LISTENING without emitting state (no visible flicker)
            await self._state.set_status(SystemStatus.LISTENING)
            await asyncio.sleep(0.05)
            return

        # Reject Whisper hallucination patterns
        _tokens = [t.strip(" ,.'\"") for t in transcript.split(",") if t.strip(" ,.'\"")]
        if len(_tokens) >= 3 and len(set(t.lower() for t in _tokens)) == 1:
            logger.info(f"[JARVIS] Hallucination (repeated token) — discarding: '{transcript}'")
            await self._state.set_status(SystemStatus.LISTENING)
            await asyncio.sleep(0.05)
            return

        # Whisper sometimes echoes phrases from initial_prompt or common training data
        _hallucination_phrases = [
            "jarvis es un asistente de ia personal",
            "jarvis es un asistente de ia",
            "habla en español",
            "subtítulos realizados",
            "subtitulos realizados",
            "subtítulos por la comunidad",
            "thanks for watching",
            "gracias por ver el video",
            "gracias por ver",
            "amara.org",
        ]
        _norm = transcript.lower().strip(" ,.'\"!?¿¡")
        if any(p in _norm for p in _hallucination_phrases):
            logger.info(f"[JARVIS] Hallucination (known phrase) — discarding: '{transcript}'")
            await self._state.set_status(SystemStatus.LISTENING)
            await asyncio.sleep(0.05)
            return

        logger.info(f"[JARVIS] Transcript: '{transcript}' [{lang}]")
        # Emit raw ASR result to frontend debug log
        await self._bus.emit("debug", {"text": f"ASR [{lang}]: \"{transcript}\"", "level": "info"})
        await self._bus.emit("transcript", {"text": transcript, "language": lang})

        # 3. Trigger detection / conversation-mode gate ──────────────────
        now = time.monotonic()

        # Check if conversation session has timed out
        if self._in_conversation and (now - self._last_interaction_at) > self._CONVERSATION_TIMEOUT:
            self._in_conversation = False
            logger.info("[JARVIS] Conversation timeout — back to wake-word mode")
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
                logger.debug(f"[JARVIS] No wake word in: '{transcript}'")
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
                # Only wake word, no query — let JARVIS acknowledge and wait
                clean_input = "El usuario te acaba de llamar. Salúdalo brevemente y pregúntale en qué puedes ayudarle."

        # ── Voice enrollment intercept (before role routing) ─────────────
        _enroll_reply = await self._check_enrollment_voice_command(clean_input)
        if _enroll_reply is not None:
            return   # enrollment started — pipeline handles the rest

        # ── Role-based routing ────────────────────────────────────────────
        if _speaker_role == SpeakerRole.OWNER:
            owner_name = getattr(getattr(self._cfg, "system", None), "owner_name", "Ricardo")
            await self._bus.emit("debug", {"text": f"✅ Propietario reconocido: {owner_name} (conf={_speaker_result.confidence:.2f})", "level": "ok"})
            await self._bus.emit("speaker_identified", {"id": _speaker_id, "role": "owner", "name": owner_name, "confidence": _speaker_result.confidence})
        elif _speaker_role == SpeakerRole.UNKNOWN and self._speaker_intel.list_speakers():
            clean_input = (
                "[SYSTEM: Voz no reconocida. Pregúntale quién es y explícale que solo el propietario "
                "puede dar comandos al sistema. Sé amable pero firme.]"
            )
            await self._bus.emit("debug", {"text": "⚠ Voz desconocida detectada", "level": "warn"})
            await self._bus.emit("speaker_identified", {"id": "unknown", "role": "unknown", "confidence": 0.0})
        elif _speaker_role == SpeakerRole.GUEST:
            clean_input = f"[INVITADO: {_speaker_id}] {clean_input}"
            await self._bus.emit("debug", {"text": f"👤 Invitado: {_speaker_id}", "level": "info"})
            await self._bus.emit("speaker_identified", {"id": _speaker_id, "role": "guest", "confidence": _speaker_result.confidence})

        # 3b. Planner voice command intercept ────────────────────────────
        planner_reply = self._planner.handle_voice_command(clean_input)
        if planner_reply:
            await self._bus.emit("debug", {"text": f"📋 Planner: {planner_reply}", "level": "ok"})
            await self._bus.emit("response", {"text": planner_reply, "language": lang})
            await self._state.add_turn("user", clean_input, lang)
            await self._state.add_turn("assistant", planner_reply, lang)
            await self._bus.emit("status", {"state": "speaking"})
            async with self._audio_lock:
                try:
                    ab, mime = await self._tts.synthesise(planner_reply)
                    if ab:
                        await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                except Exception as exc:
                    logger.warning(f"[JARVIS] Planner TTS failed: {exc}")
            await self._bus.emit("status", {"state": "idle"})
            return

        # 3c. Home Assistant voice command intercept ───────────────────────
        if self._ha_controller is not None and self._ha_client is not None and self._ha_client.available:
            ha_reply = await self._ha_controller.handle_voice_command(clean_input)
            if ha_reply:
                await self._bus.emit("debug", {"text": f"🏠 HA: {ha_reply}", "level": "ok"})
                await self._bus.emit("response", {"text": ha_reply, "language": lang})
                await self._state.add_turn("user", clean_input, lang)
                await self._state.add_turn("assistant", ha_reply, lang)
                await self._bus.emit("status", {"state": "speaking"})
                async with self._audio_lock:
                    try:
                        ab, mime = await self._tts.synthesise(ha_reply)
                        if ab:
                            await self._audio_out.play_wav(ab) if mime == "audio/wav" else await self._play_mp3(ab)
                    except Exception as exc:
                        logger.warning(f"[JARVIS] HA TTS failed: {exc}")
                await self._bus.emit("status", {"state": "idle"})
                return

        # 4. LLM inference ───────────────────────────────────────────────
        await self._bus.emit("status", {"state": "thinking"})
        await self._state.add_turn("user", clean_input, lang)
        vision_ctx = self._vision.get_context() if self._vision else None

        # 4a. Retrieve memory context (Qdrant vector) + fact memory (FTS5)
        memory_ctx = ""
        if self._memory:
            try:
                memory_ctx = await self._memory.retrieve_context(clean_input)
            except Exception as exc:
                logger.warning(f"[JARVIS] Memory retrieval failed: {exc}")

        # Inject known facts about Ricardo (always available, no Qdrant needed)
        try:
            fact_ctx = self._fact_memory.to_prompt_text(clean_input, limit=5)
            if fact_ctx:
                memory_ctx = (memory_ctx + "\n\n" + fact_ctx).strip()
        except Exception as exc:
            logger.warning(f"[JARVIS] FactMemory retrieval failed: {exc}")

        # 4b. Try tool-assisted ReAct path first (web search, clima, archivos, etc.)
        display_text = speech_text = ""
        try:
            system_prompt = self._llm._build_system_prompt(lang, self._state.turn_count, vision_ctx, memory_ctx)
            tool_display, tool_speech = await self._tools.run(
                user_input=clean_input,
                messages=self._state.get_history_for_llm()[:-1],
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=300,
            )
            if tool_display and tool_speech:
                display_text = tool_display
                speech_text  = tool_speech
                await self._bus.emit("debug", {"text": "🔧 Respondió via Tools (ReAct)", "level": "ok"})
        except Exception as exc:
            logger.warning(f"[JARVIS] Tool executor error: {exc}")

        # 4c. Fall back to normal LLM if tools didn't produce a result
        if not display_text:
            try:
                display_text, speech_text = await self._llm.generate(
                    clean_input,
                    history=self._state.get_history_for_llm()[:-1],
                    language=lang,
                    turn_count=self._state.turn_count,
                    vision_context=vision_ctx,
                    memory_context=memory_ctx,
                )
            except Exception as exc:
                logger.error(f"[JARVIS] LLM failed: {exc}")
                display_text = "Tengo problemas para procesar tu solicitud. Por favor intenta de nuevo."
                speech_text  = display_text

        # Store display text in history (markdown-safe version for context)
        await self._state.add_turn("assistant", display_text, lang)

        # 4b. Persist both turns to memory
        if self._memory:
            try:
                await self._memory.store_turn("user", clean_input, lang)
                await self._memory.store_turn("assistant", display_text, lang)
            except Exception as exc:
                logger.warning(f"[JARVIS] Memory storage failed: {exc}")

        # Extract facts from this exchange in background (never blocks pipeline)
        asyncio.create_task(self._extract_facts(clean_input, display_text))
        # Debug log: show full text transformation pipeline
        logger.info(f"[JARVIS] DISPLAY ({len(display_text)}ch): {display_text[:120]!r}")
        logger.info(f"[JARVIS] SPEECH  ({len(speech_text)}ch): {speech_text[:120]!r}")
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
                # Pre-decode to PCM to get EXACT audio duration.
                # This avoids the bug where MP3 used a hardcoded 30s estimate and
                # then mute_for(tail) would reset it to just 2s post-playback.
                try:
                    pcm_bytes, pcm_rate, actual_duration = self._decode_to_pcm(audio_bytes, mime)
                except Exception as dec_exc:
                    logger.warning(f"[JARVIS] Audio decode failed ({dec_exc}); using fallback 8s duration")
                    pcm_bytes, pcm_rate, actual_duration = None, 24000, 8.0

                # Mute mic for full playback + echo tail.
                # 5s tail absorbs laptop speaker reverb (speakers/mic close together).
                # We do NOT call mute_for() again after playback — the tail is already
                # included here so the remaining mute covers the reverb window.
                _ECHO_TAIL = 5.0
                self._audio_in.mute_for(actual_duration + _ECHO_TAIL)
                logger.info(
                    f"[JARVIS] TTS playback: actual={actual_duration:.2f}s "
                    f"tail={_ECHO_TAIL}s mime={mime} bytes={len(audio_bytes)}"
                )

                # Launch barge-in watcher concurrently
                self._barge_in_task = asyncio.create_task(self._barge_in_watcher())
                async with self._audio_lock:
                    if pcm_bytes is not None:
                        await self._audio_out.play_pcm(pcm_bytes, sample_rate=pcm_rate)
                    elif mime == "audio/wav":
                        await self._audio_out.play_wav(audio_bytes)
                    else:
                        await self._play_mp3(audio_bytes)

                # Cancel barge-in task if playback finished normally.
                # stop_barge_in() aborts its stream so the thread exits fast;
                # we then await the task so the device is free before we try
                # to open a new recording stream (fixes WASAPI exclusive deadlock).
                if self._barge_in_task and not self._barge_in_task.done():
                    self._barge_in_task.cancel()
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(self._barge_in_task), timeout=0.3
                        )
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    self._barge_in_task = None

                # Override the pre-set mute window with a short echo tail.
                # The original mute_for(duration + 5s) was set before playback;
                # by the time we reach here there are ~5s remaining.  Reducing
                # it to 1.5s lets the mic reopen quickly while still absorbing
                # immediate speaker reverb.  Adjust via config if needed.
                _echo_tail_cfg = getattr(
                    getattr(getattr(self._cfg, "audio", None), "input", None),
                    "echo_tail_secs", 1.5
                )
                self._audio_in.mute_for(_echo_tail_cfg)
        except Exception as exc:
            logger.error(f"[JARVIS] TTS/playback failed: {exc}")

        # Refresh conversation timestamp after each full exchange so the
        # 45-second window starts from when JARVIS finished speaking, not when
        # the user started talking.
        if self._in_conversation:
            self._last_interaction_at = time.monotonic()

        await self._state.set_status(SystemStatus.IDLE)
        await self._bus.emit("status", {"state": "idle"})

        # Compress conversation history if it's grown too large (rolling summary)
        asyncio.create_task(self._state.maybe_compress(self._ollama))

    def _decode_to_pcm(self, audio_bytes: bytes, mime: str) -> tuple[bytes, int, float]:
        """Decode audio to PCM int16 mono. Returns (pcm_bytes, sample_rate, duration_secs).

        Works for both WAV and MP3/MPEG.  Duration is computed from the actual
        decoded PCM length so mute_for() receives the real playback time.
        """
        import io as _io
        import soundfile as _sf

        buf = _io.BytesIO(audio_bytes)
        try:
            data, rate = _sf.read(buf, dtype="int16", always_2d=False)
        except Exception:
            # soundfile failed (unlikely for WAV, possible for some MP3)
            # Fall back to treating it as raw WAV bytes
            if mime == "audio/wav":
                rate = 24000
                import numpy as _np
                data = _np.frombuffer(audio_bytes[44:], dtype="int16")
            else:
                raise

        # Mono-mix if stereo
        import numpy as _np
        if data.ndim == 2:
            data = data[:, 0]

        pcm      = data.tobytes()
        duration = len(data) / rate
        return pcm, rate, duration

    async def _play_mp3(self, mp3_bytes: bytes) -> None:
        """Decode and play MP3 bytes (edge-tts fallback output)."""
        try:
            pcm, rate, _ = self._decode_to_pcm(mp3_bytes, "audio/mpeg")
            await self._audio_out.play_pcm(pcm, sample_rate=rate)
        except Exception as exc:
            logger.error(f"[JARVIS] MP3 decode/playback failed: {exc}")

    # ------------------------------------------------------------------
    # Public run method
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start the JARVIS engine (models + pipeline + WebSocket)."""
        log_cfg = self._cfg.logging
        project_root = self._cfg.project_root
        if log_cfg.file:
            configure_file_logging(
                project_root / log_cfg.log_dir,
                level=log_cfg.level,
                process_name="backend",
            )

        # Tell HuggingFace libraries to use only locally cached files.
        # Without this, every Kokoro synthesis triggers a network check to
        # huggingface.co (5 retries × exponential backoff = ~23 s per call
        # when the machine has no internet access).
        import os as _os
        _os.environ.setdefault("HF_HUB_OFFLINE", "1")
        _os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        # Suppress the verbose retry WARNING flood from huggingface_hub
        import logging as _logging
        _logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
        _logging.getLogger("huggingface_hub.utils._http").setLevel(_logging.ERROR)

        # ctranslate2 emits harmless "Could not locate cudnn_ops_infer64_8.dll"
        # probes at startup — INT8 CUDA inference does not need cuDNN.
        _logging.getLogger("ctranslate2").setLevel(_logging.ERROR)
        _logging.getLogger("faster_whisper").setLevel(_logging.WARNING)

        logger.info("=" * 60)
        logger.info("[JARVIS] COGNITIVE SYSTEM v1.0 — STARTING")
        logger.info(f"[JARVIS] Mode: {self._cfg.system.mode}")
        logger.info(f"[JARVIS] Time: {current_time_str()}")
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
    engine = JARVISEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("[JARVIS] Shutdown complete")


if __name__ == "__main__":
    main()
