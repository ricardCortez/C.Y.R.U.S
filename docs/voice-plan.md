# C.Y.R.U.S — Voice Pipeline Improvement Plan

## Estado actual (implementado)

### Pipeline completo

```
LLM output (raw markdown)
  │
  ▼ _split_response()
  ├─── DISPLAY text ──────────────────────► Frontend (markdown renderizado)
  │
  └─── VOZ: line / fallback
         │
         ▼ prepare_speech()
         ├─ clean_for_tts()        ← stage 1: strip markdown
         └─ normalize_for_speech() ← stage 2: CLI → español natural
                │
                ▼
         SPEECH text ──────────────────────► TTS synthesis
```

### Backend TTS (cadena con fallback automático)

```
Piper (offline, mejor calidad)
  → Kokoro (offline, buena calidad)
    → Edge-TTS (API, siempre disponible)
```

---

## Comparativa de motores TTS

| Motor | Calidad | Velocidad | Offline | Español | VRAM | Recomendado |
|-------|---------|-----------|---------|---------|------|-------------|
| **Piper** | ★★★★☆ | ★★★★★ | ✅ | ✅ excelente | 0 MB | **← usar** |
| Kokoro | ★★★☆☆ | ★★★★☆ | ✅ | ✅ (ef_dora) | ~200 MB | fallback |
| XTTS v2 | ★★★★★ | ★★☆☆☆ | ✅ | ✅ excelente | ~3 GB | futuro |
| Coqui TTS | ★★★★☆ | ★★★☆☆ | ✅ | ✅ | ~1 GB | futuro |
| Edge-TTS | ★★★★☆ | ★★★★☆ | ❌ | ✅ | 0 MB | fallback API |

**Conclusión:** Piper es la mejor opción para CYRUS:
- 0 MB VRAM (no compite con Ollama)
- Latencia <100ms para frases cortas
- Calidad notablemente más natural que Kokoro para español

---

## Activar Piper TTS

### Paso 1 — Instalar piper-tts

```bash
pip install piper-tts
```

O descarga el ejecutable de https://github.com/rhasspy/piper/releases

### Paso 2 — Descargar voz en español

```bash
# Crear directorio de modelos
mkdir -p models/tts/piper

# Opción A: es_MX-claude-high (recomendada — México, alta calidad)
cd models/tts/piper
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json

# Opción B: es_MX-ald-medium (más ligera)
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/ald/medium/es_MX-ald-medium.onnx.json
```

### Paso 3 — Activar en config.yaml

```yaml
local:
  tts:
    provider: piper
    speed: 0.9
    piper_model: models/tts/piper/es_MX-claude-high.onnx
    piper_speaker: null
```

### Verificar

```bash
echo "Hola, soy C.Y.R.U.S" | piper --model models/tts/piper/es_MX-claude-high.onnx --output_file test.wav
```

---

## Limpieza de texto (implementado)

### `clean_for_tts(text)` — Stage 1

Elimina markdown antes del TTS:
- `**negrita**` → `negrita`
- `# Encabezado` → `Encabezado`
- `` `código inline` `` → `código inline`
- ` ```bloque``` ` → *(eliminado)*
- Listas, blockquotes, links, HTML, URLs

### `normalize_for_speech(text)` — Stage 2

Convierte texto técnico a español natural:

| Entrada | Salida |
|---------|--------|
| `docker-compose up -d` | `ejecuta docker compose en segundo plano` |
| `git push origin main` | `empuja los cambios a la rama main` |
| `systemctl restart nginx` | `reinicia el servicio nginx` |
| `sudo pip install piper-tts` | `instala el paquete piper-tts` |
| `192.168.1.1` | `la dirección 192.168.1.1` |
| `:8765` | `puerto 8765` |
| `/etc/nginx.conf` | `el archivo de configuración nginx.conf` |

### `prepare_speech(text)` — Pipeline completo

```python
def prepare_speech(text: str) -> str:
    return normalize_for_speech(clean_for_tts(text))
```

---

## Selección de voz en runtime

```python
# Cambiar velocidad
tts_manager.set_speed(0.85)  # más lento = más natural

# Cambiar voz Kokoro
tts_manager.set_voice("ef_dora")

# Ver backend activo
print(tts_manager.active_backend)  # "piper" | "kokoro" | "edge-tts"
```

---

## Roadmap futuro

| Prioridad | Tarea | Esfuerzo |
|-----------|-------|---------|
| 🔴 Alta | Activar Piper + descargar es_MX-claude-high | 15 min |
| 🟡 Media | XTTS v2 con clonado de voz de Ricardo | 2-3h |
| 🟡 Media | Ajustar normalize_for_speech según errores reales | continuo |
| 🟢 Baja | Soporte para múltiples idiomas (EN fallback) | 1h |
| 🟢 Baja | Control de velocidad/tono vía comando de voz | 2h |

---

## Próximo paso inmediato

```bash
# 1. Instalar
pip install piper-tts

# 2. Descargar voz
mkdir -p models/tts/piper
cd models/tts/piper
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx
curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json

# 3. En config.yaml: cambiar provider: piper

# 4. Reiniciar CYRUS — Piper se activa automáticamente
```
