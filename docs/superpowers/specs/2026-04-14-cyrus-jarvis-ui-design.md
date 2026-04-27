# JARVIS — JARVIS-Style Frontend Design Spec
**Date:** 2026-04-14  
**Status:** Approved  

---

## Overview

Complete replacement of the existing frontend (`frontend/src/`). Two independent views navigated via `Tab` / React Router. The core visual is a Three.js particle network (neural mesh) — not an orb. The UI is minimal, futuristic, immersive.

---

## View 1 — Agent (route `/`)

Full-screen, 100% immersive. No text, no panels. Only the particle network fills the screen.

### ParticleNetwork (Three.js)

- **Renderer:** `WebGLRenderer`, fills viewport, transparent background
- **Camera:** `PerspectiveCamera`, slight mouse parallax
- **Particles:** 200–260 via `THREE.Points` + `BufferGeometry`
  - Organic cloud distribution (not perfect sphere) — semi-random with Gaussian bias
  - Per-particle: position, velocity, phase offset, size variance (0.7–1.8)
  - Soft spherical constraint keeps them loosely grouped
  - Constant gentle drift (sine/cosine phase motion)
- **Connections:** `THREE.LineSegments` with `BufferGeometry`
  - Dynamic: recalculate each frame which pairs are within `connDist` threshold
  - Line opacity fades with distance (1 - dist/connDist)
  - Line width: glow pass (thick, transparent) + core pass (thin, bright) via two draw calls
  - Max connections capped to avoid O(n²) blowup: skip pair with `Math.random() > connFrac`
- **Glow:** `ShaderMaterial` on Points with custom GLSL — radial falloff per point, additive blending
- **Core glow:** radial gradient at scene center, intensity driven by state
- **Mouse:** raycaster or direct NDC → slight attraction/repulsion (±15px max displacement), dampened

### State Machine (driven by Zustand `systemState`)

| State | Speed | connFrac | coreGlow | fireRate | Electrons | Pulse |
|-------|-------|----------|----------|----------|-----------|-------|
| idle | 0.13 | 0.32 | 0.28 | 0 | No | 0 |
| listening | 0.18 | 0.46 | 0.42 | 0.0012 | No | 0.18 |
| thinking | 0.28 | 0.70 | 0.68 | 0.0045 | Yes | 0.35 |
| speaking | 0.22 | 0.58 | 0.55 | 0.0020 | Yes | 0.60 |

All values lerp smoothly (factor 0.03/frame) — no hard cuts.

### Neuron Activation (listening / thinking / speaking)

- Each particle has `fireAmt` (0→1) and `fireCool` (cooldown frames)
- Spontaneous ignition at `fireRate` probability per frame
- Cascade: if particle A fires (fireAmt > 0.3) and particle B is a connected neighbor → B fires at 55% of A's intensity with 9% probability per frame
- Visual: multi-ring halo + pulse ring + bright dot on firing particle; connected line brightens + thickens
- Electrons: bright white dots that travel along hot connections (thinking/speaking only), 3-point trail

### Audio Reactivity

- `AudioContext` + `AnalyserNode` attached to TTS audio output element
- FFT bins 0–8 (bass) → radial push on all particles (outward displacement)
- FFT bins 8–24 (mid) → synchronized pulse on connection opacity
- Fallback: simulated amplitude via `Math.sin()` when no audio
- Mic input (optional): `getUserMedia` → same AnalyserNode pipeline, used during `listening` state

### Minimal Bottom UI

- Audio visualizer: 30 bars, only visible when state ≠ idle, `audioAmp > 0.04`
- `Tab` hint: `position:fixed bottom-6 right-6`, 8px mono text, fades out after 4s on load
- No labels, no name, no header

---

## View 2 — Control Panel (route `/control`)

Separate page. Futuristic dashboard. Framer Motion animations on mount.

### Layout

Full-screen dark bg (`#05070d`). Single scrollable column, max-width 480px centered. Header: `JARVIS` brand + back arrow to View 1.

### Sections (top → bottom)

1. **AI State Badge** — large badge with pulsing dot, color-coded by `systemState`
2. **System Stats** — CPU / GPU (RTX 2070S) / RAM with animated bar fills + uptime + weather Lima (fake data, static)
3. **System Log** — scrolling console feed from WebSocket `log` messages, auto-scroll, color-coded: info=cyan, warn=orange, error=red
4. **Configuration** — editable fields:
   - LLM Model (text pill, clickable)
   - TTS Engine
   - VAD on/off toggle
   - Wake word
   - Bloom intensity slider (0.5–2.5)
   - Particle count (100–400)
   - Orb speed multiplier

### Animations (Framer Motion)

- Page enter: `opacity 0→1`, `blur(8px)→0`, duration 0.6s
- Each section: staggered `y: 20→0` fade-in, 0.1s delay between sections
- Stat bars: animate width on mount (0→actual%)
- State badge: `scale` pulse on state change

---

## Component Structure

```
frontend/src/
├── App.tsx                      # React Router, two routes
├── views/
│   ├── AgentView.tsx            # View 1 — full screen particle network
│   └── ControlView.tsx          # View 2 — dashboard
├── components/
│   ├── ParticleNetwork.tsx      # Three.js canvas, manages scene lifecycle
│   ├── AudioVisualizer.tsx      # 30-bar FFT visualizer
│   ├── VoiceButton.tsx          # Animated mic button (Framer Motion)
│   ├── HUDPanel.tsx             # Glassmorphism panel wrapper
│   ├── SystemLog.tsx            # Scrolling log feed
│   └── StatusPanel.tsx          # Stats + AI state
├── hooks/
│   ├── useWebSocket.ts          # Existing — keep
│   └── useAudioAnalyser.ts      # New — Web Audio API wrapper
├── store/
│   └── useJARVISStore.ts         # Existing — keep, add: logs[], particleCount, bloomIntensity
├── styles/
│   └── jarvis-theme.css          # Existing — update fonts to Orbitron
└── utils/
    └── ws-client.ts             # Existing — keep
```

---

## Dependencies to Add

```json
"three": "^0.165.0",
"@types/three": "^0.165.0",
"framer-motion": "^11.0.0",
"react-router-dom": "^6.24.0"
```

---

## Color System

| Token | Value | Use |
|-------|-------|-----|
| `--c-primary` | `#00f0ff` | Particles, active connections, highlights |
| `--c-secondary` | `#0077ff` | Inactive connections, core glow |
| `--c-bg` | `#05070d` | Background |
| `--c-warn` | `#ff8c00` | Warnings, thinking state |
| `--c-error` | `#ff3333` | Error state |
| `--c-ok` | `#00ff88` | Listening / ok state |

---

## Typography

- **Headers:** Orbitron 700–900, tracking 0.3–0.45em, uppercase
- **Mono data:** Share Tech Mono, tracking 0.15–0.25em
- **Body:** Orbitron 400

---

## Performance Budget

- Target 60fps on RTX 2070S
- Particle count: 200 default, configurable 100–400
- O(n²) connection loop mitigated by `connFrac` sampling + early distance check
- Three.js `BufferGeometry` with pre-allocated `Float32Array`, update `needsUpdate` only on position change
- No postprocessing bloom (real bloom costs too much for this geometry count) — simulate with additive blending + layered glow passes in shader

---

## WebSocket Integration

Existing `useWebSocket.ts` drives `systemState` in Zustand. ParticleNetwork reads state reactively via `useJARVISStore`. No changes to backend protocol.

New store fields:
- `logs: LogEntry[]` — populated by WS `log` events, capped at 200 entries
- `particleCount: number` — default 200, configurable from ControlView
- `bloomIntensity: number` — default 1.4, drives shader uniform

---

## Navigation

- `Tab` key → toggles between `/` and `/control`  
- `Ctrl+,` → jumps directly to `/control`
- Arrow `←` button in ControlView header → back to `/`
- React Router `<HashRouter>` (no server config needed)
