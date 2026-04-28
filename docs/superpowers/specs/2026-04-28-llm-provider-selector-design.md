# LLM Provider Selector — Design Spec
**Date:** 2026-04-28  
**Status:** Approved  

---

## Objetivo

Permitir al usuario elegir desde la vista CONFIG del frontend si CYRUS usa
Ollama local o una API externa (OpenAI, Anthropic, Groq, Gemini) como motor LLM,
con prueba de conectividad integrada.

---

## Alcance

- 3 nuevos clientes LLM en backend
- `LLMManager` con provider activo configurable en runtime
- 2 nuevos comandos WebSocket + 1 nuevo evento broadcast
- Panel "MOTOR LLM" en `TabConfig` reemplaza al actual "MODELO LLM (OLLAMA)"

**Fuera de alcance:** streaming por token, selección de provider para TTS/ASR,
múltiples providers simultáneos, fetch dinámico de modelos disponibles via API.

---

## Backend

### Nuevos archivos

#### `backend/modules/llm/openai_client.py`
Cliente para OpenAI y cualquier API compatible (base_url configurable).

```python
class OpenAIClient:
    def __init__(self, api_key, model, base_url=None, timeout=60): ...
    async def chat(self, messages, system_prompt, temperature) -> str: ...
    async def test_connectivity(self) -> dict: ...  # {"ok": bool, "latency_ms": int, "error": str}
```

Usa `openai` SDK (`pip install openai`). El `system_prompt` se inserta como
mensaje `{"role": "system", ...}` al inicio de la lista de mensajes.

#### `backend/modules/llm/groq_client.py`
Hereda de `OpenAIClient` con `base_url="https://api.groq.com/openai/v1"`.
No requiere lógica adicional — Groq implementa la API de OpenAI completamente.

#### `backend/modules/llm/gemini_client.py`
Usa `google-generativeai` SDK. Convierte mensajes OpenAI-style a formato Gemini
(roles `user`/`model`, system prompt como `system_instruction`).

```python
class GeminiClient:
    def __init__(self, api_key, model, timeout=60): ...
    async def chat(self, messages, system_prompt, temperature) -> str: ...
    async def test_connectivity(self) -> dict: ...
```

### Cambios en `LLMManager`

**Estado nuevo:** `_active_provider: str` — uno de `ollama | openai | anthropic | groq | gemini`.

**Método `generate()` actualizado:**
- Si `_active_provider == "ollama"`: comportamiento actual (Ollama → fallback Claude si HYBRID)
- Si `_active_provider` es cualquier API: va directo al cliente correspondiente, sin pasar por Ollama

**Nuevo método `set_provider(provider, api_key, model)`:**
- Instancia el cliente correcto con las credenciales dadas
- Persiste `api.llm.provider`, `api.llm.model`, `api.llm.api_key` en `config.yaml`
- Retorna `{"ok": True}` o `{"ok": False, "error": "..."}`

**Nuevo método `test_connectivity(provider, api_key, model)`:**
- Crea una instancia temporal del cliente (no modifica el activo)
- Envía `{"role": "user", "content": "ping"}` con `max_tokens=5`
- Retorna `{"ok": bool, "latency_ms": int, "error": str}`

### Comandos WebSocket nuevos (en `cyrus_engine.py`)

| Comando | Payload | Acción |
|---|---|---|
| `set_llm_provider` | `{provider, api_key, model}` | Llama `llm.set_provider(...)`, broadcast `llm_config` |
| `test_llm_connectivity` | `{provider, api_key, model}` | Llama `llm.test_connectivity(...)`, emite `llm_test_result` |

### Nuevos eventos broadcast

| Evento | Payload | Cuándo |
|---|---|---|
| `llm_config` | `{provider, model, mode}` | Al conectar cliente WS y tras `set_llm_provider` |
| `llm_test_result` | `{ok, latency_ms, error}` | Tras `test_llm_connectivity` |

### Config `config.yaml`

```yaml
api:
  llm:
    provider: anthropic        # openai | anthropic | groq | gemini
    model: claude-sonnet-4-6
    api_key: ""                # se puede setear también via env var
    temperature: 0.7
```

La API key también se lee de variables de entorno como fallback:
`OPENAI_API_KEY`, `CLAUDE_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`.

---

## Frontend

### Panel "MOTOR LLM" en `TabConfig`

Reemplaza el panel actual "MODELO LLM (OLLAMA)".

**Estado local del componente:**
```typescript
const [llmMode, setLlmMode] = useState<'local' | 'api'>('local')
const [apiProvider, setApiProvider] = useState<string>('openai')
const [apiModel, setApiModel] = useState<string>('gpt-4o-mini')
const [apiKey, setApiKey] = useState<string>('')
const [showKey, setShowKey] = useState(false)
const [testState, setTestState] = useState<'idle'|'testing'|'ok'|'error'>('idle')
const [testMsg, setTestMsg] = useState('')
```

**Modelos pre-cargados por provider:**
```typescript
const PROVIDER_MODELS = {
  openai:    ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5'],
  groq:      ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768', 'gemma2-9b-it'],
  gemini:    ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
}
```

**Al cambiar de LOCAL → API:** envía `set_llm_provider` con los valores actuales.  
**Al cambiar de API → LOCAL:** envía `set_llm_provider` con `{provider: "ollama"}`.  
**Botón PROBAR:** envía `test_llm_connectivity`, espera evento `llm_test_result`.

**Seguridad de API key:**
- El campo muestra `••••••••` por defecto con botón 👁 para revelar temporalmente
- Al recibir `llm_config` del backend, el key se muestra como `sk-...XXXX` (últimos 4 chars)
- La key se envía por WebSocket (conexión local), no se expone en ningún log de frontend

**Evento `llm_test_result` en el store:**
- `ok: true` → muestra `● Conectado — {model} respondió en {latency_ms}ms` en verde
- `ok: false` → muestra `✗ Error — {error}` en rojo
- Estado se resetea a `idle` tras 8 segundos

### Store (`useJARVISStore`)

Campos nuevos:
```typescript
llmConfig: { provider: string; model: string; mode: string } | null
llmTestResult: { ok: boolean; latency_ms: number; error: string } | null
```

Handlers nuevos para eventos `llm_config` y `llm_test_result`.

---

## Dependencias nuevas

| Paquete | Para |
|---|---|
| `openai>=1.0` | OpenAI + Groq |
| `google-generativeai>=0.8` | Gemini |

`anthropic` ya está instalado.

---

## Flujo completo

```
Usuario selecciona "API" + elige "Groq" + pega API key + elige modelo
    → frontend envía set_llm_provider {provider:"groq", api_key:"gsk_...", model:"llama-3.3-70b"}
    → engine llama llm.set_provider(...)
    → LLMManager instancia GroqClient, persiste en config.yaml
    → broadcast llm_config {provider:"groq", model:"llama-3.3-70b", mode:"API"}
    → frontend actualiza UI, muestra "GROQ ACTIVO"

Usuario pulsa "PROBAR CONEXIÓN"
    → frontend envía test_llm_connectivity {provider:"groq", api_key:"gsk_...", model:"llama-3.3-70b"}
    → engine llama llm.test_connectivity(...) — instancia temporal, no cambia activo
    → Groq responde en 380ms
    → broadcast llm_test_result {ok:true, latency_ms:380, error:""}
    → frontend muestra "● Conectado — llama-3.3-70b respondió en 380ms"
```

---

## Archivos a modificar / crear

| Archivo | Tipo |
|---|---|
| `backend/modules/llm/openai_client.py` | Nuevo |
| `backend/modules/llm/groq_client.py` | Nuevo |
| `backend/modules/llm/gemini_client.py` | Nuevo |
| `backend/modules/llm/llm_manager.py` | Modificar |
| `backend/core/cyrus_engine.py` | Modificar (2 comandos + 1 evento) |
| `frontend/src/views/ControlView.tsx` | Modificar (panel LLM) |
| `frontend/src/store/` | Modificar (2 campos + 2 handlers) |
| `config/config.yaml` | Modificar (sección api.llm) |
| `requirements.txt` | Modificar (openai, google-generativeai) |
