# C.Y.R.U.S — Plan de Memoria

## Objetivo
Darle a CYRUS memoria persistente en tres capas:
1. **Perfil estático** — quién es Ricardo, quién es CYRUS (ya en soul.md, ampliar)
2. **Memoria de sesión** — historial de conversación dentro de una sesión (ya funciona, 10 turnos)
3. **Memoria semántica** — recordar entre sesiones usando embeddings + SQLite + Qdrant

---

## Capa 1 — Perfil Persistente (inmediato, sin dependencias)

### Qué es
Un archivo `config/user_profile.yaml` con datos fijos de Ricardo y del entorno que se inyectan en el system prompt en cada conversación.

### Contenido
```yaml
user:
  name: Ricardo
  location: Lima, Perú
  timezone: America/Lima
  role: Ingeniero / Administrador de Homelab
  languages: [español, inglés]
  interests:
    - Automatización de infraestructura
    - Domótica (Home Assistant)
    - Sistemas de IA y ML
    - Redes y virtualización (Proxmox)
    - Vigilancia (Frigate + NVR)

homelab:
  hypervisor: Proxmox VE
  smart_home: Home Assistant
  nvr: Frigate
  gpu: RTX 2070 Super
  network: LAN local (192.168.1.0/24)

cyrus:
  version: "1.0"
  persona: Asistente cognitivo personal, similar a JARVIS de Iron Man
  voice: ef_dora (Kokoro TTS, español)
  wake_words: [cyrus, hola cyrus, oye cyrus]
```

### Implementación
- `config_manager.py` → leer `user_profile.yaml`
- `llm_manager.py` → inyectar perfil en el system prompt
- `soul.md` → referenciar el perfil dinámicamente

---

## Capa 2 — Memoria de Sesión (ya implementada)

- `StateManager` mantiene historial de hasta 10 turnos
- Se pasa a Ollama en cada llamada como `history`
- **Mejora pendiente**: aumentar a 20 turnos y resumir turnos viejos con el LLM

---

## Capa 3 — Memoria Semántica Entre Sesiones

### Infraestructura (ya implementada en Phase 3, requiere activación)

#### Componentes
| Componente | Archivo | Estado |
|---|---|---|
| `ConversationDB` | `backend/modules/memory/conversation_db.py` | ✅ listo |
| `Embedder` | `backend/modules/memory/embedder.py` | ✅ listo |
| `QdrantStore` | `backend/modules/memory/qdrant_store.py` | ✅ listo |
| `MemoryManager` | `backend/modules/memory/memory_manager.py` | ✅ listo |

#### Dependencias
- **SQLite**: sin dependencias — funciona en Windows sin instalar nada
- **Qdrant**: requiere Docker o ejecutable local
- **Embedder**: `all-MiniLM-L6-v2` (~90MB), se descarga automáticamente

### Plan de activación

#### Paso A — SQLite solo (sin Qdrant)
Activar solo `ConversationDB` para guardar todas las conversaciones.
Qdrant opcional: si no está disponible, `MemoryManager` ya tiene fallback graceful.

```yaml
# config.yaml
memory:
  enabled: true
  db_path: data/conversations.db
  qdrant:
    host: localhost
    port: 6333
  embedder:
    model: all-MiniLM-L6-v2
  top_k: 5
```

#### Paso B — Qdrant local (búsqueda semántica)
```bash
# Opción 1: ejecutable directo (sin Docker)
qdrant.exe --config-path config/qdrant_config.yaml

# Opción 2: Docker
docker run -p 6333:6333 qdrant/qdrant
```

#### Paso C — Integración con LLM
Ya implementado en `cyrus_engine.py`:
```python
memory_ctx = await self._memory.retrieve_context(clean_input)
response = await self._llm.generate(..., memory_context=memory_ctx)
```

### Qué recuerda entre sesiones
- Cada turno de conversación (usuario + CYRUS)
- Embeddings vectoriales del contenido
- Búsqueda semántica: "¿qué me dijiste sobre Proxmox?" → recupera contexto relevante
- Timestamp, idioma, session_id

---

## Roadmap de implementación

| Prioridad | Tarea | Esfuerzo | Dependencias |
|---|---|---|---|
| 🔴 Alta | Perfil de usuario en `user_profile.yaml` | 1h | Ninguna |
| 🔴 Alta | Inyección de perfil en LLMManager | 1h | Perfil yaml |
| 🟡 Media | Activar SQLite memory (`enabled: true`) | 30min | Ninguna |
| 🟡 Media | Resumen de historial largo (>10 turnos) con LLM | 2h | Ninguna |
| 🟢 Baja | Instalar Qdrant local (Docker o exe) | 30min | Docker/exe |
| 🟢 Baja | Activar búsqueda semántica completa | 1h | Qdrant |

---

## Próximos pasos inmediatos

1. Crear `config/user_profile.yaml` con datos de Ricardo y el homelab
2. Actualizar `config_manager.py` para leer el perfil
3. Actualizar `llm_manager.py` para inyectarlo en el system prompt
4. Activar `memory.enabled: true` en config (SQLite sin Qdrant)
5. Probar que CYRUS recuerda el nombre de Ricardo entre reinicios
