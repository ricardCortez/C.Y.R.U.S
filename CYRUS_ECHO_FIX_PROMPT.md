# CYRUS — Echo Cancellation & Wake Word Gate Fix
**Prompt listo para ejecutar en nueva sesión de Claude Code**

---

## Contexto del proyecto

**C.Y.R.U.S** es un asistente de voz local en Python (Windows, RTX 2070S).
- Backend: FastAPI + asyncio en `backend/`
- Engine principal: `backend/core/cyrus_engine.py`
- Audio input: `backend/modules/audio/audio_input.py`
- VAD: `backend/modules/audio/vad_detector.py` (webrtcvad)
- TTS: `backend/modules/tts/` (Piper → Kokoro → Edge-TTS)
- ASR: faster-whisper o servidor remoto en `backend/modules/audio/`

---

## El bug a resolver

**Síntoma:** Cuando CYRUS habla por los parlantes, el micrófono captura el audio del TTS,
lo procesa como si fuera el usuario hablando, y entra en un loop: responde → el mic
captura la respuesta → vuelve a responder → loop infinito.

**Causa raíz (ya identificada en el código):**

1. El pipeline graba con `record_utterance()` **siempre que VAD detecta voz**, incluyendo
   el audio que sale por los parlantes.

2. `mute_for(actual_duration + 5.0)` se aplica al inicio del TTS, pero luego se
   **sobreescribe a `echo_tail_secs` (1.5s)** apenas termina el playback
   (`cyrus_engine.py` líneas ~1820-1826). Si la respuesta TTS es larga y hay reverb,
   1.5s no alcanza.

3. En modo `_in_conversation = True`, **no se verifica wake word** — todo transcript
   se procesa directamente. Entonces si el mic captura el TTS durante esos 1.5s,
   se procesa como consulta del usuario.

4. No existe un gate de estado: si `SystemStatus == SPEAKING`, el audio grabado
   debería descartarse incondicionalmente, pero la verificación del estado ocurre
   demasiado tarde (después de grabar y transcribir).

---

## Solución a implementar (3 capas, en orden de prioridad)

### CAPA 1 — Fix inmediato: no sobreescribir el mute tail (cambio de 1 línea)

**Archivo:** `backend/core/cyrus_engine.py`  
**Problema:** después del playback, se hace `mute_for(echo_tail_secs)` que resetea el
timer a solo 1.5s, descartando los segundos de cola que ya estaban contados.  
**Fix:** no llamar `mute_for()` después del playback si el tiempo restante ya es suficiente.

```python
# ANTES (líneas ~1820-1826):
_echo_tail_cfg = getattr(
    getattr(getattr(self._cfg, "audio", None), "input", None),
    "echo_tail_secs", 1.5
)
self._audio_in.mute_for(_echo_tail_cfg)

# DESPUÉS — solo actualizar si el tiempo restante es menor al tail configurado:
_echo_tail_cfg = getattr(
    getattr(getattr(self._cfg, "audio", None), "input", None),
    "echo_tail_secs", 1.5
)
remaining = self._audio_in.mute_remaining()   # nuevo método (ver abajo)
if remaining < _echo_tail_cfg:
    self._audio_in.mute_for(_echo_tail_cfg)
```

Agregar `mute_remaining()` en `AudioInput`:
```python
def mute_remaining(self) -> float:
    """Seconds of mute window still active. 0 if not muted."""
    return max(0.0, self._muted_until - time.monotonic())
```

---

### CAPA 2 — Gate de estado en el loop principal

**Archivo:** `backend/core/cyrus_engine.py`  
**Ubicación:** al inicio de `_handle_audio()` o justo después de `record_utterance()`,
antes de llamar al ASR.

```python
# Después de obtener pcm de record_utterance(), antes del ASR:
if self._state.status in (SystemStatus.SPEAKING, SystemStatus.PROCESSING):
    logger.debug("[CYRUS] Audio descartado — sistema ocupado (SPEAKING/PROCESSING)")
    return

# También verificar el flag de mute directamente:
if self._audio_in.mute_remaining() > 0:
    logger.debug(f"[CYRUS] Audio descartado — mute activo ({self._audio_in.mute_remaining():.1f}s restantes)")
    return
```

Esto es el seguro: incluso si `mute_for()` falla o el timing es impreciso,
el audio capturado mientras el sistema habla se descarta antes de ir a Whisper.

---

### CAPA 3 — Wake word siempre requerido (modo estricto configurable)

**Problema:** en `_in_conversation = True`, cualquier transcripción se procesa.
Si el TTS dice "¿En qué más puedo ayudarte?" y el mic lo captura, se procesa
como nueva consulta.

**Fix:** agregar opción `strict_wake_word: false` en config. Si `true`, siempre
verificar wake word aunque haya sesión activa.

**Archivo:** `config/config.yaml`
```yaml
trigger:
  wake_words: [jarvis, hey jarvis, oye jarvis]
  strict_wake_word: false   # true = siempre requiere wake word, incluso en sesión activa
```

**Archivo:** `backend/core/cyrus_engine.py`, en la sección de trigger detection (~línea 1592):
```python
strict_mode = getattr(getattr(self._cfg, "trigger", None), "strict_wake_word", False)

if self._in_conversation and not strict_mode:
    clean_input = transcript.strip()
    # ... resto del flujo existente
else:
    # Standby mode O strict_mode activo — siempre verificar wake word
    triggered, clean_input = self._trigger.detect(transcript)
    if not triggered:
        # ... resto del flujo existente (no wake word → descartar)
```

---

## Archivos a modificar (resumen)

| Archivo | Cambio |
|---|---|
| `backend/modules/audio/audio_input.py` | Agregar método `mute_remaining()` |
| `backend/core/cyrus_engine.py` | Fix post-playback mute, gate de estado, strict_wake_word |
| `config/config.yaml` | Agregar `strict_wake_word: false` en sección `trigger` |

---

## Cambios en config.yaml recomendados

```yaml
audio:
  input:
    echo_tail_secs: 3.0   # subir de 2.0 a 3.0 para parlantes de escritorio

trigger:
  strict_wake_word: false  # cambiar a true si el echo persiste
```

---

## Verificación después del fix

1. CYRUS responde → el mic NO debe capturar la respuesta como nuevo input
2. Durante `SPEAKING`, cualquier audio grabado debe mostrar en logs:
   `[CYRUS] Audio descartado — sistema ocupado (SPEAKING/PROCESSING)`
3. El flag de mute debe cubrir desde el inicio del TTS hasta
   `actual_duration + echo_tail_secs` sin interrupciones

---

## Estado actual del código (referencia)

- `mute_for()`: implementado en `AudioInput` — funciona correctamente
- `mute_remaining()`: NO existe aún — hay que agregarlo
- `_in_conversation`: existe, controla si se verifica wake word
- `echo_tail_secs`: existe en config, valor actual `2.0`
- `_ECHO_TAIL = 5.0`: hardcodeado en el loop principal, se aplica al inicio del TTS
- El problema: `mute_for(echo_tail_cfg)` post-playback sobreescribe el timer existente

---

## Notas adicionales

- NO usar `openwakeword` ni otras librerías externas — el sistema ya tiene wake word
  por transcript (funciona bien). El bug es de timing, no de arquitectura.
- NO refactorizar el pipeline de audio — solo los 3 cambios puntuales descritos.
- Mantener compatibilidad con todos los backends TTS existentes (Piper/Kokoro/Edge-TTS/Remote).
