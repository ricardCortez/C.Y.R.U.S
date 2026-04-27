# JARVIS — Mejoras v1.1 Design Spec
**Fecha:** 2026-04-17  
**Estado:** Aprobado por usuario  
**Alcance:** 3 sub-proyectos independientes, implementables en secuencia

---

## Sub-proyecto 1 — Launcher inteligente

### Objetivo
Reemplazar `start_services.bat` con un launcher robusto que instale dependencias, levante servicios en orden, haga health-check activo, y abra el browser solo cuando todo esté UP.

### Archivos afectados
- `launch.py` (nuevo — launcher principal Python)
- `launch.bat` (reemplaza `start_services.bat` — wrapper de una línea)
- `stop_services.bat` (sin cambios)

### Flujo de ejecución
```
launch.bat
  └─ python launch.py [flags]
       ├─ [1] Verificar Python >= 3.11 y existencia de venv
       │       Si no existe venv → crearlo con py -3.11 -m venv venv
       ├─ [2] pip install -r requirements.txt
       │       Solo si hash(requirements.txt) cambió desde última ejecución
       │       Hash guardado en .jarvis_launcher_state (gitignored)
       ├─ [3] npm install en /frontend
       │       Solo si hash(package.json) cambió
       ├─ [4] Matar procesos en puertos: 8020, 8765, 3007, 8000, 8001, 8002
       ├─ [5] Levantar servicios en orden:
       │       a. TTS Server (8020)     → poll /health hasta OK o timeout
       │       b. Backend JARVIS (8765)  → poll puerto TCP hasta OK o timeout
       │       c. Frontend React (3007) → poll HTTP 200 hasta OK o timeout
       │       (ASR/Vision/Embedder opcionales via flags CLI)
       ├─ [6] Tabla de estado final con colores
       └─ [7] abrir http://localhost:3007 en browser del sistema
```

### Health-wait
- Polling cada 2 segundos
- Timeout por servicio: 120 segundos (configurable en `launch.py`)
- Si un servicio excede el timeout: mostrar últimas 10 líneas del proceso + preguntar `[C]ontinuar / [A]bortar`
- El browser NO se abre hasta que todos los servicios requeridos estén en estado OK

### Salida en consola (colores ANSI)
```
  ┌─────────────────────────────────────┐
  │  JARVIS  —  INICIANDO SISTEMA   │
  └─────────────────────────────────────┘
  [✓] Python 3.11           encontrado
  [✓] Entorno virtual       activo
  [✓] Deps Python           sin cambios (hash igual)
  [✓] Deps Frontend         sin cambios (hash igual)
  [↑] TTS Server   :8020 ........... OK (12s)
  [↑] Backend      :8765 ........... OK (4s)
  [↑] Frontend     :3007 ........... OK (8s)
  ──────────────────────────────────────
  [✓] Sistema listo → abriendo navegador...
```

### Flags CLI
```
launch.bat              → TTS + Backend + Frontend (default)
launch.bat all          → todos los servicios incluyendo ASR/Vision/Embedder
launch.bat tts asr      → servicios específicos
launch.bat noui         → sin frontend (headless)
launch.bat install-only → solo instalar deps, no levantar servicios
```

### Estado persistido
Archivo `.jarvis_launcher_state` (gitignored):
```json
{
  "requirements_hash": "sha256:...",
  "package_json_hash": "sha256:..."
}
```

---

## Sub-proyecto 2 — Audio Pipeline mejorado

### Objetivo
Eliminar el eco del micrófono, filtrar ruido de fondo con un noise gate adaptivo, y verificar identidad del hablante antes de transcribir — eliminando falsos positivos.

### Archivos afectados
- `backend/modules/audio/audio_input.py` (migración PyAudio → sounddevice + noise gate + speaker gate)
- `backend/modules/audio/vad_detector.py` (sin cambios)
- `backend/modules/audio/speaker_profile.py` (sin cambios — ya tiene `is_match`)
- `config/config.yaml` (nuevos parámetros: `noise_gate_factor`, `speaker_gate_enabled`)

### 2a — Fix de eco (mic monitoring)

**Causa:** PyAudio en Windows abre el stream de micrófono y el driver de audio activa monitoring automático (rutea mic → speaker).

**Solución:** Migrar `AudioInput` de PyAudio a `sounddevice` usando WASAPI en modo compartido con `extra_settings` que deshabilita el loopback del driver.

```python
import sounddevice as sd

stream = sd.InputStream(
    samplerate=self._sample_rate,
    channels=self._channels,
    dtype='int16',
    blocksize=self._chunk_size,
    device=self._device_index,
    # WASAPI shared mode — sin monitoring
    extra_settings=sd.WasapiSettings(exclusive=False, auto_convert=True),
)
```

PyAudio se elimina completamente de `audio_input.py`. `requirements.txt` se actualiza: quitar `PyAudio`, mantener `sounddevice` (ya está listado).

### 2b — Noise gate adaptivo

**Calibración al inicio:** Antes del primer `record_utterance`, el sistema graba 2 segundos de silencio y calcula el RMS promedio del ambiente (`ambient_noise_floor`).

**Umbral dinámico:** `effective_threshold = max(config_threshold, ambient_noise_floor × noise_gate_factor)`  
`noise_gate_factor` default: `3.5` (configurable en `config.yaml`)

**Recalibración:** `AudioInput` registra internamente el timestamp del último frame de speech detectado. Si han pasado más de 5 minutos sin speech, la próxima llamada a `_record_sync` ejecuta una recalibración de 1 segundo antes de entrar al loop normal. No requiere señal externa del engine.

```yaml
# config.yaml — nuevos parámetros
audio:
  input:
    noise_gate_factor: 3.5      # umbral = noise_floor × factor
    noise_calibration_secs: 2.0 # segundos de calibración inicial
```

### 2c — Speaker verification gate

**Condición:** Solo activo si existe `config/voice_profile.npy` (requiere enrollment previo).

**Posición en pipeline:** Después de VAD + RMS gate, antes de enviar a Whisper ASR.

**Lógica:**
```
audio capturado
  → si NO hay voice_profile: pasar directo a ASR (comportamiento actual)
  → si HAY voice_profile: SpeakerProfile.is_match(audio)
      → True:  pasar a ASR
      → False: descartar silenciosamente (log debug)
```

**Sin enrollment = sin gate** — el sistema funciona igual que antes para usuarios que no han hecho enrollment.

### 2d — Flujo completo resultante
```
Mic (sounddevice WASAPI, sin monitoring)
  → Noise gate adaptivo (RMS > noise_floor × 3.5)
  → WebRTC VAD aggressiveness=3
  → [si voice_profile existe] Speaker verification
  → Whisper ASR base (con initial_prompt)
  → Hallucination filter
  → Trigger detector
  → LLM → TTS
```

### Parámetros de config nuevos
```yaml
audio:
  input:
    noise_gate_factor: 3.5
    noise_calibration_secs: 2.0
    speaker_gate_enabled: true   # false = deshabilitar aunque haya perfil
```

---

## Sub-proyecto 3 — ParticleNetwork Visual (Opción C + Presets)

### Objetivo
Reestructura visual completa con geometría volumétrica de 3 capas, 3 tipos de conexiones, shaders WebGL mejorados, estados más dramáticos, y 5 presets configurables desde ControlView.

### Archivos afectados
- `frontend/src/components/ParticleNetwork.tsx` (reestructura completa)
- `frontend/src/views/ControlView.tsx` (agregar selector de presets)
- `frontend/src/store/useJARVISStore.ts` (agregar `visualPreset` al estado global)
- `frontend/src/types/presets.ts` (nuevo — tipos de presets)

### 3a — Geometría volumétrica (400 nodos, 3 capas)

| Capa | % nodos | Radio | Comportamiento |
|---|---|---|---|
| Corteza (externa) | 40% (160n) | r=100 | Reacciona rápido, pulsos frecuentes |
| Materia gris (media) | 35% (140n) | r=72 | Intermediaria, transmite señales |
| Núcleo (interno) | 25% (100n) | r=45 | Pulsa lento, genera ondas hacia afuera |

Distribución aleatoria en cada capa con jitter ±8% del radio para naturalidad.

### 3b — 3 tipos de conexiones

| Tipo | % del total | Criterio | Visual |
|---|---|---|---|
| Local | 80% | Nodos cercanos, mismo cluster | Delgadas, opacidad 0.4 |
| Hemisférica | 15% | Cruzan hemisferios | Más brillantes, opacidad 0.7 |
| Axón largo | 5% | Cruzan capas distintas | Muy finas, pulsantes lentos, opacidad 0.3 |

Total conexiones: ~1800 (vs ~400 actuales).

### 3c — Shaders WebGL mejorados

**Nodos:**
- Halo de glow volumétrico (doble círculo: núcleo opaco + corona difusa)
- Tamaño variable por capa (corteza más pequeña, núcleo más grande)
- Depth-based opacity: elementos lejanos al 40% de opacidad

**Conexiones:**
- Grosor variable: fino en reposo (1px), engrosado durante pulso (3px)
- Pulso renderizado como gradiente a lo largo de la línea (no punto viajero)
- Color diferente por tipo: local=base, hemisférico=más saturado, axón=más tenue

### 3d — Estados dramáticos mejorados

| Estado | Comportamiento |
|---|---|
| `idle` | Pulsos espontáneos de baja frecuencia desde núcleo — el cerebro nunca duerme |
| `listening` | Corteza se ilumina progresivamente, pulsos rápidos en superficie |
| `thinking` | Cascada desde núcleo → materia gris → corteza, múltiples frentes simultáneos |
| `speaking` | Ondas radiales de propagación sincronizadas con el ritmo del TTS |
| `error` | Pulsos rojos erráticos, desincronizados |

### 3e — 5 presets visuales

```typescript
type VisualPreset = 'neural' | 'holographic' | 'cyber' | 'organic' | 'monochrome'

interface PresetConfig {
  name: string
  palette: { node: [r,g,b], connection: [r,g,b], pulse: [r,g,b] }
  rotSpeedMult: number    // multiplicador sobre velocidades base por estado
  pulseDensity: number    // multiplicador de pulsos
  glowIntensity: number   // 0.0–2.0
  connectionWidth: number // multiplicador de grosor
  gridOverlay: boolean    // líneas de grid sutil (holographic)
}
```

| Preset | Paleta | Glow | Notas |
|---|---|---|---|
| `Neural` | Azul/cyan | 1.0 | Default — biológico |
| `Holographic` | Verde neón | 1.4 | Grid overlay sutil |
| `Cyber` | Naranja/rojo | 1.6 | Pulsos agresivos, rápidos |
| `Organic` | Violeta/lavanda | 0.8 | Movimiento lento y fluido |
| `Monochrome` | Blanco puro | 1.2 | Opacidad variable |

### 3f — Selector en ControlView

Sección nueva "Visualización" en `ControlView.tsx`:
- 5 tarjetas clickeables, cada una con preview canvas en miniatura (50×50px) renderizado en tiempo real con el preset
- La selección se guarda en `useJARVISStore` → `visualPreset`
- `ParticleNetwork` observa `visualPreset` y transiciona suavemente (lerp 60 frames) entre paletas

---

## Orden de implementación recomendado

1. **Sub-proyecto 1** (Launcher) — independiente, no rompe nada, beneficio inmediato
2. **Sub-proyecto 2** (Audio) — requiere probar con hardware, impacto en UX inmediato
3. **Sub-proyecto 3** (Visual) — solo frontend, sin riesgos para el backend

## No incluido en este spec
- Reentrenamiento del modelo ASR
- Cambios al modelo LLM
- Nuevas features de memory o vision
- Rediseño del layout general del frontend
