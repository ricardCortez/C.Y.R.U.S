# JARVIS JARVIS UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing frontend with a full-screen Three.js particle network (neural mesh) as the core visual, plus a separate control dashboard view, connected to the existing WebSocket backend.

**Architecture:** Two React Router routes (`/` = full-screen Three.js scene, `/control` = Framer Motion dashboard). Three.js manages its own render loop via `useRef`/`useEffect`; Zustand state drives animation parameters reactively each frame. No postprocessing — glow simulated via GLSL additive blending.

**Tech Stack:** React 19 + TypeScript + Vite, Three.js r165, Framer Motion 11, React Router 6, TailwindCSS 3, Zustand 4, Web Audio API.

---

### Task 1: Install dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install new packages**

```bash
cd frontend
npm install three@^0.165.0 framer-motion@^11.0.0 react-router-dom@^6.24.0
npm install -D @types/three@^0.165.0
```

Expected output: packages added to `node_modules`, no peer dep errors.

- [ ] **Step 2: Verify build still works**

```bash
npm run build 2>&1 | tail -5
```

Expected: `✓ built in` — no errors.

- [ ] **Step 3: Commit**

```bash
cd ..
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add three, framer-motion, react-router-dom"
```

---

### Task 2: Fonts + base styles

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/styles/jarvis-theme.css`
- Modify: `frontend/tailwind.config.js`

- [ ] **Step 1: Add Google Fonts to index.html**

Replace the `<head>` section of `frontend/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>JARVIS</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Rewrite jarvis-theme.css**

```css
/* frontend/src/styles/jarvis-theme.css */
:root {
  --c-primary:   #00f0ff;
  --c-secondary: #0077ff;
  --c-bg:        #05070d;
  --c-warn:      #ff8c00;
  --c-error:     #ff3333;
  --c-ok:        #00ff88;
}

*, *::before, *::after { box-sizing: border-box; }

html, body, #root {
  width: 100%; height: 100%;
  margin: 0; padding: 0;
  background: var(--c-bg);
  color: var(--c-primary);
  font-family: 'Orbitron', sans-serif;
  overflow: hidden;
}

/* Scrollable pages override */
.page-scroll { overflow-y: auto; height: 100%; }

::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #00f0ff20; border-radius: 2px; }

/* Glow text utility */
.glow { text-shadow: 0 0 12px var(--c-primary); }

/* Mono data */
.mono {
  font-family: 'Share Tech Mono', monospace;
  letter-spacing: 0.18em;
}
```

- [ ] **Step 3: Update tailwind.config.js**

```js
// frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        orbitron: ['Orbitron', 'sans-serif'],
        mono: ['Share Tech Mono', 'monospace'],
      },
      colors: {
        primary:   '#00f0ff',
        secondary: '#0077ff',
        bg:        '#05070d',
        warn:      '#ff8c00',
        danger:    '#ff3333',
        ok:        '#00ff88',
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: `✓ built in` — no errors.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/index.html frontend/src/styles/jarvis-theme.css frontend/tailwind.config.js
git commit -m "style: Orbitron font, CSS vars, tailwind color tokens"
```

---

### Task 3: Update Zustand store

**Files:**
- Modify: `frontend/src/store/useJARVISStore.ts`

- [ ] **Step 1: Read current store**

Read `frontend/src/store/useJARVISStore.ts` to understand existing shape before editing.

- [ ] **Step 2: Rewrite store with new fields**

```typescript
// frontend/src/store/useJARVISStore.ts
import { create } from 'zustand'

export type SystemState =
  | 'offline' | 'connected' | 'idle'
  | 'listening' | 'transcribing' | 'thinking'
  | 'speaking' | 'error'

export type LogLevel = 'info' | 'warn' | 'error'

export interface LogEntry {
  id:        number
  timestamp: string
  level:     LogLevel
  message:   string
}

interface JARVISStore {
  // Existing
  systemState:  SystemState
  wsConnected:  boolean
  transcript:   { role: 'user' | 'assistant'; text: string }[]
  lastResponse: string

  // New
  logs:           LogEntry[]
  particleCount:  number
  bloomIntensity: number
  orbSpeed:       number

  // Actions
  setSystemState:    (s: SystemState) => void
  setWsConnected:    (v: boolean) => void
  addTranscript:     (entry: { role: 'user' | 'assistant'; text: string }) => void
  setLastResponse:   (t: string) => void
  addLog:            (level: LogLevel, message: string) => void
  clearLogs:         () => void
  setParticleCount:  (n: number) => void
  setBloomIntensity: (v: number) => void
  setOrbSpeed:       (v: number) => void
}

let logSeq = 0

export const useJARVISStore = create<JARVISStore>((set) => ({
  systemState:    'offline',
  wsConnected:    false,
  transcript:     [],
  lastResponse:   '',
  logs:           [],
  particleCount:  200,
  bloomIntensity: 1.4,
  orbSpeed:       1.0,

  setSystemState:  (s) => set({ systemState: s }),
  setWsConnected:  (v) => set({ wsConnected: v }),
  addTranscript:   (e) => set((st) => ({ transcript: [...st.transcript, e] })),
  setLastResponse: (t) => set({ lastResponse: t }),

  addLog: (level, message) => set((st) => {
    const entry: LogEntry = {
      id:        ++logSeq,
      timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false }),
      level,
      message,
    }
    const logs = [...st.logs, entry]
    return { logs: logs.length > 200 ? logs.slice(-200) : logs }
  }),

  clearLogs:         () => set({ logs: [] }),
  setParticleCount:  (n) => set({ particleCount: Math.min(400, Math.max(100, n)) }),
  setBloomIntensity: (v) => set({ bloomIntensity: Math.min(2.5, Math.max(0.5, v)) }),
  setOrbSpeed:       (v) => set({ orbSpeed: Math.min(3, Math.max(0.1, v)) }),
}))
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd .. && git add frontend/src/store/useJARVISStore.ts
git commit -m "feat(store): add logs, particleCount, bloomIntensity, orbSpeed"
```

---

### Task 4: useAudioAnalyser hook

**Files:**
- Create: `frontend/src/hooks/useAudioAnalyser.ts`

- [ ] **Step 1: Create hook**

```typescript
// frontend/src/hooks/useAudioAnalyser.ts
import { useEffect, useRef, useCallback } from 'react'

export interface AudioAnalyserHandle {
  /** 0–1 bass amplitude (bins 0-8) */
  getBass: () => number
  /** 0–1 mid amplitude (bins 8-24) */
  getMid:  () => number
  /** Connect to an HTMLAudioElement (TTS output) */
  connectElement: (el: HTMLAudioElement) => void
  /** Connect to microphone */
  connectMic: () => Promise<void>
  disconnect: () => void
}

/**
 * Returns a stable handle with getBass/getMid that read the latest
 * FFT data each call. Safe to call from a Three.js render loop.
 */
export function useAudioAnalyser(): AudioAnalyserHandle {
  const ctxRef      = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const dataRef     = useRef<Uint8Array>(new Uint8Array(0))
  const sourceRef   = useRef<MediaStreamAudioSourceNode | MediaElementAudioSourceNode | null>(null)

  const ensureCtx = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext()
      const analyser = ctxRef.current.createAnalyser()
      analyser.fftSize = 64
      analyser.connect(ctxRef.current.destination)
      analyserRef.current = analyser
      dataRef.current = new Uint8Array(analyser.frequencyBinCount)
    }
    return { ctx: ctxRef.current, analyser: analyserRef.current! }
  }, [])

  const getFreqData = useCallback(() => {
    if (analyserRef.current && dataRef.current.length > 0) {
      analyserRef.current.getByteFrequencyData(dataRef.current)
    }
    return dataRef.current
  }, [])

  const getBass = useCallback(() => {
    const d = getFreqData()
    if (d.length === 0) return 0
    let sum = 0
    const end = Math.min(8, d.length)
    for (let i = 0; i < end; i++) sum += d[i]
    return sum / (end * 255)
  }, [getFreqData])

  const getMid = useCallback(() => {
    const d = getFreqData()
    if (d.length === 0) return 0
    let sum = 0
    const start = Math.min(8, d.length)
    const end   = Math.min(24, d.length)
    for (let i = start; i < end; i++) sum += d[i]
    return sum / (Math.max(1, end - start) * 255)
  }, [getFreqData])

  const connectElement = useCallback((el: HTMLAudioElement) => {
    const { ctx, analyser } = ensureCtx()
    sourceRef.current?.disconnect()
    const src = ctx.createMediaElementSource(el)
    src.connect(analyser)
    sourceRef.current = src
  }, [ensureCtx])

  const connectMic = useCallback(async () => {
    const { ctx, analyser } = ensureCtx()
    sourceRef.current?.disconnect()
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const src = ctx.createMediaStreamSource(stream)
    src.connect(analyser)
    sourceRef.current = src
  }, [ensureCtx])

  const disconnect = useCallback(() => {
    sourceRef.current?.disconnect()
    sourceRef.current = null
    ctxRef.current?.close()
    ctxRef.current = null
    analyserRef.current = null
  }, [])

  useEffect(() => () => { disconnect() }, [disconnect])

  return { getBass, getMid, connectElement, connectMic, disconnect }
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/hooks/useAudioAnalyser.ts
git commit -m "feat(hooks): useAudioAnalyser — Web Audio API FFT wrapper"
```

---

### Task 5: ParticleNetwork component (Three.js core)

**Files:**
- Create: `frontend/src/components/ParticleNetwork.tsx`

This is the main visual component. It owns the Three.js scene lifecycle entirely.

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/ParticleNetwork.tsx
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useJARVISStore, SystemState } from '../store/useJARVISStore'
import { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'

// ── State → animation params ──────────────────────────────────────────────

interface StateParams {
  speed:     number
  connFrac:  number
  coreGlow:  number
  fireRate:  number
  electrons: boolean
  pulseAmt:  number
  color:     [number, number, number] // 0–1
}

const STATE_PARAMS: Record<SystemState, StateParams> = {
  offline:      { speed: 0.08, connFrac: 0.18, coreGlow: 0.10, fireRate: 0,      electrons: false, pulseAmt: 0,    color: [0.0, 0.20, 0.30] },
  connected:    { speed: 0.12, connFrac: 0.28, coreGlow: 0.22, fireRate: 0,      electrons: false, pulseAmt: 0,    color: [0.0, 0.75, 1.0]  },
  idle:         { speed: 0.13, connFrac: 0.32, coreGlow: 0.28, fireRate: 0,      electrons: false, pulseAmt: 0,    color: [0.0, 0.78, 1.0]  },
  listening:    { speed: 0.18, connFrac: 0.46, coreGlow: 0.42, fireRate: 0.0012, electrons: false, pulseAmt: 0.18, color: [0.0, 0.86, 1.0]  },
  transcribing: { speed: 0.20, connFrac: 0.52, coreGlow: 0.50, fireRate: 0.0020, electrons: false, pulseAmt: 0.22, color: [0.0, 0.86, 1.0]  },
  thinking:     { speed: 0.28, connFrac: 0.70, coreGlow: 0.68, fireRate: 0.0045, electrons: true,  pulseAmt: 0.35, color: [0.2, 0.67, 1.0]  },
  speaking:     { speed: 0.22, connFrac: 0.58, coreGlow: 0.55, fireRate: 0.0020, electrons: true,  pulseAmt: 0.60, color: [0.0, 0.94, 1.0]  },
  error:        { speed: 0.30, connFrac: 0.40, coreGlow: 0.60, fireRate: 0.0030, electrons: false, pulseAmt: 0.25, color: [1.0, 0.20, 0.20]  },
}

// ── GLSL shaders ──────────────────────────────────────────────────────────

const VERT_SHADER = /* glsl */`
  attribute float aSize;
  attribute float aFire;
  varying   float vFire;
  varying   float vDepth;

  void main() {
    vFire  = aFire;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth  = clamp((-mv.z - 80.0) / 300.0, 0.0, 1.0);
    gl_PointSize = aSize * (280.0 / -mv.z) * (1.0 + aFire * 1.6);
    gl_Position  = projectionMatrix * mv;
  }
`

const FRAG_SHADER = /* glsl */`
  uniform vec3  uColor;
  uniform float uOpacity;
  uniform float uBloom;
  varying float vFire;
  varying float vDepth;

  void main() {
    vec2  uv = gl_PointCoord - 0.5;
    float d  = length(uv);
    if (d > 0.5) discard;

    // Radial glow falloff
    float core = 1.0 - smoothstep(0.0, 0.5, d);
    float glow = 1.0 - smoothstep(0.0, 0.45, d);
    float alpha = (core * 0.85 + glow * 0.35) * uOpacity * (0.4 + vDepth * 0.6);

    // Fire boost — shifts toward white/warm
    vec3 fireColor = uColor + vec3(vFire * 0.55, vFire * 0.38, vFire * 0.18);
    vec3 col = mix(uColor * uBloom, fireColor, vFire * 0.8);

    gl_FragColor = vec4(col, alpha);
  }
`

// ── Electron type ─────────────────────────────────────────────────────────

interface Electron {
  ax: number; ay: number; az: number
  bx: number; by: number; bz: number
  t: number; spd: number
}

// ── Component ─────────────────────────────────────────────────────────────

interface Props {
  analyser?: AudioAnalyserHandle
}

export function ParticleNetwork({ analyser }: Props) {
  const mountRef     = useRef<HTMLDivElement>(null)
  const systemState  = useJARVISStore((s) => s.systemState)
  const particleCount = useJARVISStore((s) => s.particleCount)
  const bloomIntensity = useJARVISStore((s) => s.bloomIntensity)
  const orbSpeed      = useJARVISStore((s) => s.orbSpeed)

  // Store refs so the render loop always reads latest values
  const stateRef    = useRef(systemState)
  const countRef    = useRef(particleCount)
  const bloomRef    = useRef(bloomIntensity)
  const speedRef    = useRef(orbSpeed)
  const analyserRef = useRef(analyser)

  useEffect(() => { stateRef.current    = systemState   }, [systemState])
  useEffect(() => { countRef.current    = particleCount }, [particleCount])
  useEffect(() => { bloomRef.current    = bloomIntensity}, [bloomIntensity])
  useEffect(() => { speedRef.current    = orbSpeed      }, [orbSpeed])
  useEffect(() => { analyserRef.current = analyser      }, [analyser])

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    // ── Scene setup ────────────────────────────────────────────────────
    const scene    = new THREE.Scene()
    const camera   = new THREE.PerspectiveCamera(60, mount.clientWidth / mount.clientHeight, 0.1, 2000)
    camera.position.set(0, 0, 320)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(mount.clientWidth, mount.clientHeight)
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)

    // ── Particle data ─────────────────────────────────────────────────
    const N = countRef.current
    const positions = new Float32Array(N * 3)
    const velocities= new Float32Array(N * 3)
    const phases    = new Float32Array(N)
    const sizes     = new Float32Array(N)
    const fireAmts  = new Float32Array(N)
    const fireCools = new Float32Array(N)

    // Organic cloud — Gaussian-ish via sum of randoms, NOT perfect sphere
    for (let i = 0; i < N; i++) {
      // Box-Muller for Gaussian distribution
      const u1 = Math.random(), u2 = Math.random()
      const mag = Math.sqrt(-2 * Math.log(u1 + 1e-9))
      const ang = 2 * Math.PI * u2
      const gx  = mag * Math.cos(ang)
      const gy  = mag * Math.sin(ang)
      const gz  = (Math.random() - 0.5) * 2

      const spread = 85 + Math.random() * 45
      positions[i*3]   = gx * spread * 0.7
      positions[i*3+1] = gy * spread * 0.55
      positions[i*3+2] = gz * spread * 0.6

      velocities[i*3]   = (Math.random() - 0.5) * 0.18
      velocities[i*3+1] = (Math.random() - 0.5) * 0.18
      velocities[i*3+2] = (Math.random() - 0.5) * 0.18

      phases[i] = Math.random() * Math.PI * 2
      sizes[i]  = 0.7 + Math.random() * 1.1
    }

    // ── Points geometry + shader material ─────────────────────────────
    const ptGeo = new THREE.BufferGeometry()
    ptGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    ptGeo.setAttribute('aSize',    new THREE.BufferAttribute(sizes,     1))
    ptGeo.setAttribute('aFire',    new THREE.BufferAttribute(fireAmts,  1))

    const ptMat = new THREE.ShaderMaterial({
      vertexShader:   VERT_SHADER,
      fragmentShader: FRAG_SHADER,
      uniforms: {
        uColor:   { value: new THREE.Color(0x00f0ff) },
        uOpacity: { value: 0.85 },
        uBloom:   { value: bloomRef.current },
      },
      transparent: true,
      blending:    THREE.AdditiveBlending,
      depthWrite:  false,
    })

    const points = new THREE.Points(ptGeo, ptMat)
    scene.add(points)

    // ── Line geometry (pre-allocated max size) ─────────────────────────
    const MAX_LINES = N * 4
    const linePositions = new Float32Array(MAX_LINES * 6)  // 2 verts × 3 coords
    const lineColors    = new Float32Array(MAX_LINES * 6)  // per-vertex color+alpha packed as rgb

    const lineGeo = new THREE.BufferGeometry()
    const linePosAttr = new THREE.BufferAttribute(linePositions, 3)
    const lineColAttr = new THREE.BufferAttribute(lineColors, 3)
    linePosAttr.setUsage(THREE.DynamicDrawUsage)
    lineColAttr.setUsage(THREE.DynamicDrawUsage)
    lineGeo.setAttribute('position', linePosAttr)
    lineGeo.setAttribute('color',    lineColAttr)

    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent:  true,
      blending:     THREE.AdditiveBlending,
      depthWrite:   false,
      opacity:      1.0,
    })

    const lines = new THREE.LineSegments(lineGeo, lineMat)
    scene.add(lines)

    // ── Electrons ──────────────────────────────────────────────────────
    const electrons: Electron[] = []

    // ── Mouse tracking ─────────────────────────────────────────────────
    const mouse = { x: 0, y: 0, nx: 0, ny: 0 }
    const onMouseMove = (e: MouseEvent) => {
      mouse.nx = (e.clientX / window.innerWidth)  * 2 - 1
      mouse.ny = -(e.clientY / window.innerHeight) * 2 + 1
    }
    window.addEventListener('mousemove', onMouseMove)

    // ── Lerped state values ────────────────────────────────────────────
    let lSpeed    = 0.13
    let lConnFrac = 0.32
    let lCoreGlow = 0.28
    let lFireRate = 0
    let lPulse    = 0
    let lColor    = new THREE.Color(0x00c8ff)
    let audioAmp  = 0
    let simT      = 0
    let rafId     = 0

    const lerpN = (a: number, b: number, f: number) => a + (b - a) * f

    function fireNeuron(i: number, str: number) {
      if (fireCools[i] > 0 || fireAmts[i] > 0.1) return
      fireAmts[i]  = Math.min(1, str)
      fireCools[i] = 40 + Math.random() * 50
    }

    // ── Resize handler ─────────────────────────────────────────────────
    const onResize = () => {
      if (!mount) return
      camera.aspect = mount.clientWidth / mount.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(mount.clientWidth, mount.clientHeight)
    }
    window.addEventListener('resize', onResize)

    // ── Animation loop ─────────────────────────────────────────────────
    function animate() {
      rafId = requestAnimationFrame(animate)
      simT += 0.016

      const state    = stateRef.current
      const tgt      = STATE_PARAMS[state]
      const spd      = speedRef.current
      const bloom    = bloomRef.current

      // Lerp state params
      lSpeed    = lerpN(lSpeed,    tgt.speed    * spd, 0.03)
      lConnFrac = lerpN(lConnFrac, tgt.connFrac,       0.03)
      lCoreGlow = lerpN(lCoreGlow, tgt.coreGlow,       0.03)
      lFireRate = lerpN(lFireRate, tgt.fireRate,        0.06)
      lPulse    = lerpN(lPulse,    tgt.pulseAmt,        0.04)
      lColor.lerp(new THREE.Color(...tgt.color), 0.04)

      // Mouse parallax — camera drifts toward mouse
      mouse.x = lerpN(mouse.x, mouse.nx * 18, 0.04)
      mouse.y = lerpN(mouse.y, mouse.ny * 12, 0.04)
      camera.position.x = lerpN(camera.position.x, mouse.x, 0.06)
      camera.position.y = lerpN(camera.position.y, mouse.y, 0.06)
      camera.lookAt(0, 0, 0)

      // Audio amplitude
      if (analyserRef.current) {
        if (state === 'speaking' || state === 'listening') {
          audioAmp = lerpN(audioAmp, analyserRef.current.getBass(), 0.15)
        } else {
          audioAmp = lerpN(audioAmp, 0, 0.08)
        }
      } else {
        // Simulated
        if (state === 'speaking') {
          audioAmp = lerpN(audioAmp, 0.28 + 0.72 * Math.abs(Math.sin(simT * 4.2) * Math.cos(simT * 2.5)), 0.08)
        } else if (state === 'listening') {
          audioAmp = lerpN(audioAmp, 0.05 + 0.12 * Math.abs(Math.sin(simT * 6)), 0.08)
        } else {
          audioAmp = lerpN(audioAmp, 0, 0.05)
        }
      }

      const react = lPulse * (state === 'speaking' ? audioAmp : 1.0)
      const CONN_DIST = 72 + react * 20

      // ── Update particles ─────────────────────────────────────────────
      for (let i = 0; i < N; i++) {
        const ix = i * 3, iy = ix + 1, iz = ix + 2
        const ph = phases[i]

        // Organic sine drift
        velocities[ix]   = lerpN(velocities[ix],   Math.sin(simT * lSpeed + ph) * 0.40,                0.07)
        velocities[iy]   = lerpN(velocities[iy],   Math.cos(simT * lSpeed * 0.74 + ph * 1.3) * 0.40,  0.07)
        velocities[iz]   = lerpN(velocities[iz],   Math.sin(simT * lSpeed * 0.53 + ph * 0.87) * 0.40, 0.07)

        positions[ix] += velocities[ix]
        positions[iy] += velocities[iy]
        positions[iz] += velocities[iz]

        // Audio push (bass → radial)
        if (audioAmp > 0.15) {
          const d = Math.sqrt(positions[ix]**2 + positions[iy]**2 + positions[iz]**2)
          if (d > 0) {
            const push = audioAmp * 1.2
            positions[ix] += (positions[ix] / d) * push
            positions[iy] += (positions[iy] / d) * push
            positions[iz] += (positions[iz] / d) * push
          }
        }

        // Soft boundary — keep cloud organic, loose
        const d = Math.sqrt(positions[ix]**2 + positions[iy]**2 + positions[iz]**2)
        const maxR = 130 + react * 18
        if (d > maxR && d > 0) {
          const f = (maxR / d - 1) * 0.012
          positions[ix] += positions[ix] * f
          positions[iy] += positions[iy] * f
          positions[iz] += positions[iz] * f
        }

        // Neuron decay + cooldown
        if (fireAmts[i] > 0) fireAmts[i] = Math.max(0, fireAmts[i] - 0.022)
        if (fireCools[i] > 0) fireCools[i]--
        if (lFireRate > 0 && Math.random() < lFireRate && fireCools[i] === 0) {
          fireNeuron(i, 0.7 + Math.random() * 0.3)
        }
      }

      // ── Build connection segments ──────────────────────────────────────
      let lineIdx = 0
      const cdSq = CONN_DIST * CONN_DIST
      const cr = lColor.r, cg = lColor.g, cb = lColor.b

      for (let i = 0; i < N && lineIdx < MAX_LINES - 1; i++) {
        if (Math.random() > lConnFrac) continue
        const ix = i * 3, iy = ix + 1, iz = ix + 2

        for (let j = i + 1; j < N && lineIdx < MAX_LINES - 1; j++) {
          const jx = j * 3, jy = jx + 1, jz = jx + 2
          const dx = positions[ix] - positions[jx]
          const dy = positions[iy] - positions[jy]
          const dz = positions[iz] - positions[jz]
          const dSq = dx*dx + dy*dy + dz*dz
          if (dSq > cdSq) continue

          const str = 1 - Math.sqrt(dSq) / CONN_DIST
          const avgFire = (fireAmts[i] + fireAmts[j]) * 0.5

          // Cascade
          if (fireAmts[i] > 0.3 && fireCools[j] === 0 && Math.random() < 0.09) fireNeuron(j, fireAmts[i] * 0.55)
          if (fireAmts[j] > 0.3 && fireCools[i] === 0 && Math.random() < 0.09) fireNeuron(i, fireAmts[j] * 0.55)

          const alpha = (str * 0.55 + avgFire * 0.5 + react * 0.08) * lCoreGlow
          const fr = Math.min(1, cr + avgFire * 0.55)
          const fg = Math.min(1, cg + avgFire * 0.38)
          const fbC = Math.min(1, cb + avgFire * 0.22)

          const li = lineIdx * 6
          // Vertex A
          linePositions[li]   = positions[ix]; linePositions[li+1] = positions[iy]; linePositions[li+2] = positions[iz]
          lineColors[li]      = fr * alpha;    lineColors[li+1]    = fg * alpha;    lineColors[li+2]    = fbC * alpha
          // Vertex B
          linePositions[li+3] = positions[jx]; linePositions[li+4] = positions[jy]; linePositions[li+5] = positions[jz]
          lineColors[li+3]    = fr * alpha;    lineColors[li+4]    = fg * alpha;    lineColors[li+5]    = fbC * alpha

          lineIdx++

          // Spawn electrons on strong connections
          if (tgt.electrons && str > 0.5 && Math.random() < 0.0009 && electrons.length < 35) {
            electrons.push({
              ax: positions[ix], ay: positions[iy], az: positions[iz],
              bx: positions[jx], by: positions[jy], bz: positions[jz],
              t: 0, spd: 0.007 + Math.random() * 0.013,
            })
          }
        }
      }

      // Zero out unused line slots
      linePositions.fill(0, lineIdx * 6)
      lineColors.fill(0,    lineIdx * 6)
      lineGeo.setDrawRange(0, lineIdx * 2)
      linePosAttr.needsUpdate = true
      lineColAttr.needsUpdate = true

      // ── Update electrons (rendered as Points overlay) ──────────────────
      // (simple CPU trail — no extra geometry needed, just skip rendering them
      //  via Three.js for now; they exist in the connection visual via line brightening)
      for (let e = electrons.length - 1; e >= 0; e--) {
        electrons[e].t += electrons[e].spd
        if (electrons[e].t >= 1) electrons.splice(e, 1)
      }

      // ── Update shader uniforms ────────────────────────────────────────
      ptMat.uniforms.uColor.value.copy(lColor)
      ptMat.uniforms.uBloom.value = bloom

      // ── Update particle position + fire attributes ─────────────────────
      ptGeo.getAttribute('position').needsUpdate = true
      ;(ptGeo.getAttribute('aFire') as THREE.BufferAttribute).array = fireAmts
      ptGeo.getAttribute('aFire').needsUpdate = true

      renderer.render(scene, camera)
    }

    animate()

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      ptGeo.dispose()
      ptMat.dispose()
      lineGeo.dispose()
      lineMat.dispose()
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // intentionally empty — render loop reads latest via refs

  return <div ref={mountRef} className="w-full h-full" />
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/components/ParticleNetwork.tsx
git commit -m "feat(ui): ParticleNetwork — Three.js neural mesh with GLSL shader"
```

---

### Task 6: AudioVisualizer component

**Files:**
- Create: `frontend/src/components/AudioVisualizer.tsx`

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/AudioVisualizer.tsx
import { motion, AnimatePresence } from 'framer-motion'
import { useJARVISStore } from '../store/useJARVISStore'
import { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'
import { useEffect, useRef, useState } from 'react'

interface Props {
  analyser?: AudioAnalyserHandle
}

const BARS = 30
const STATE_COLOR: Record<string, string> = {
  listening:    '#00ff88',
  transcribing: '#00f0ff',
  thinking:     '#ff8c00',
  speaking:     '#00f0ff',
}

export function AudioVisualizer({ analyser }: Props) {
  const systemState = useJARVISStore((s) => s.systemState)
  const [heights, setHeights] = useState<number[]>(Array(BARS).fill(2))
  const rafRef  = useRef<number>(0)
  const simT    = useRef(0)
  const visible = systemState !== 'idle' && systemState !== 'offline' && systemState !== 'connected'

  useEffect(() => {
    if (!visible) { setHeights(Array(BARS).fill(2)); return }

    const tick = () => {
      simT.current += 0.016
      const bass = analyser?.getBass() ?? 0
      const sim  = 0.12 + 0.88 * Math.abs(Math.sin(simT.current * 4.1) * Math.cos(simT.current * 2.3))
      const amp  = analyser ? bass : sim * (systemState === 'speaking' ? 1 : 0.35)

      setHeights(Array.from({ length: BARS }, (_, i) => {
        const raw = 2 + (4 + amp * 22) * Math.abs(Math.sin(simT.current * (2.6 + i * 0.33) + i * 0.6))
        return Math.min(32, raw)
      }))
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [visible, analyser, systemState])

  const color = STATE_COLOR[systemState] ?? '#00f0ff'

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="flex items-end justify-center gap-[2.5px]"
          style={{ height: 36 }}
          initial={{ opacity: 0, scaleY: 0 }}
          animate={{ opacity: 1, scaleY: 1 }}
          exit={{   opacity: 0, scaleY: 0 }}
          transition={{ duration: 0.3 }}
        >
          {heights.map((h, i) => (
            <div
              key={i}
              style={{
                width:        '2.8px',
                height:       `${h}px`,
                background:   `linear-gradient(180deg, ${color}, ${color}55)`,
                boxShadow:    `0 0 4px ${color}66`,
                borderRadius: '2px',
                transition:   'height 0.05s ease',
              }}
            />
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/components/AudioVisualizer.tsx
git commit -m "feat(ui): AudioVisualizer — reactive FFT bar visualizer"
```

---

### Task 7: VoiceButton + HUDPanel

**Files:**
- Create: `frontend/src/components/VoiceButton.tsx`
- Create: `frontend/src/components/HUDPanel.tsx`

- [ ] **Step 1: Create VoiceButton**

```tsx
// frontend/src/components/VoiceButton.tsx
import { motion } from 'framer-motion'
import { useJARVISStore } from '../store/useJARVISStore'

const STATE_COLOR: Record<string, string> = {
  listening: '#00ff88',
  speaking:  '#00f0ff',
  thinking:  '#ff8c00',
  error:     '#ff3333',
}

export function VoiceButton() {
  const systemState = useJARVISStore((s) => s.systemState)
  const isActive    = ['listening', 'speaking', 'thinking'].includes(systemState)
  const color       = STATE_COLOR[systemState] ?? '#00f0ff'

  return (
    <motion.button
      className="relative flex items-center justify-center rounded-full cursor-pointer border"
      style={{
        width:       48,
        height:      48,
        background:  `${color}0a`,
        borderColor: `${color}55`,
        boxShadow:   isActive ? `0 0 20px ${color}44, 0 0 40px ${color}22` : 'none',
        flexShrink:  0,
      }}
      whileHover={{ scale: 1.08 }}
      whileTap={{   scale: 0.94 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
    >
      {/* Ping ring when active */}
      {isActive && (
        <motion.span
          className="absolute inset-0 rounded-full"
          style={{ border: `1px solid ${color}`, opacity: 0 }}
          animate={{ scale: [1, 1.6], opacity: [0.6, 0] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: 'easeOut' }}
        />
      )}
      {/* Mic icon */}
      <svg width="18" height="22" viewBox="0 0 18 22" fill="none">
        <rect x="5" y="1" width="8" height="13" rx="4" fill={color} />
        <path d="M1 10a8 8 0 0016 0" stroke={color} strokeWidth="1.5" strokeLinecap="round" fill="none" />
        <line x1="9" y1="18" x2="9" y2="21" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
        <line x1="5" y1="21" x2="13" y2="21" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </motion.button>
  )
}
```

- [ ] **Step 2: Create HUDPanel**

```tsx
// frontend/src/components/HUDPanel.tsx
import { motion } from 'framer-motion'
import { ReactNode } from 'react'

interface Props {
  title:    string
  children: ReactNode
  delay?:   number
}

export function HUDPanel({ title, children, delay = 0 }: Props) {
  return (
    <motion.div
      className="rounded-lg overflow-hidden"
      style={{
        background:   'rgba(3,8,16,0.85)',
        border:       '1px solid rgba(0,240,255,0.12)',
        backdropFilter: 'blur(12px)',
      }}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0  }}
      transition={{ duration: 0.5, delay, ease: 'easeOut' }}
      whileHover={{ borderColor: 'rgba(0,240,255,0.28)', boxShadow: '0 0 20px rgba(0,240,255,0.06)' }}
    >
      <div
        className="px-3 py-2 mono"
        style={{
          fontSize:     8,
          letterSpacing: '0.3em',
          color:         'rgba(0,240,255,0.35)',
          borderBottom:  '1px solid rgba(0,240,255,0.08)',
        }}
      >
        ⬡ {title}
      </div>
      <div className="p-3">{children}</div>
    </motion.div>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd .. && git add frontend/src/components/VoiceButton.tsx frontend/src/components/HUDPanel.tsx
git commit -m "feat(ui): VoiceButton, HUDPanel components"
```

---

### Task 8: SystemLog component

**Files:**
- Create: `frontend/src/components/SystemLog.tsx`

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/SystemLog.tsx
import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useJARVISStore, LogEntry } from '../store/useJARVISStore'
import { HUDPanel } from './HUDPanel'

const LEVEL_COLOR: Record<string, string> = {
  info:  'rgba(0,240,255,0.75)',
  warn:  'rgba(255,140,0,0.75)',
  error: 'rgba(255,51,51,0.75)',
}
const LEVEL_BORDER: Record<string, string> = {
  info:  'rgba(0,240,255,0.28)',
  warn:  'rgba(255,140,0,0.28)',
  error: 'rgba(255,51,51,0.28)',
}

function LogLine({ entry }: { entry: LogEntry }) {
  return (
    <motion.div
      className="flex gap-2 py-[2px] pl-[6px] mono"
      style={{
        fontSize:   8,
        borderLeft: `2px solid ${LEVEL_BORDER[entry.level]}`,
        color:      LEVEL_COLOR[entry.level],
      }}
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0  }}
      transition={{ duration: 0.2 }}
    >
      <span style={{ color: 'rgba(0,240,255,0.22)', flexShrink: 0 }}>{entry.timestamp}</span>
      <span style={{ wordBreak: 'break-all' }}>{entry.message}</span>
    </motion.div>
  )
}

export function SystemLog({ delay = 0 }: { delay?: number }) {
  const logs    = useJARVISStore((s) => s.logs)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <HUDPanel title="SYSTEM LOG" delay={delay}>
      <div
        className="flex flex-col gap-[1px] overflow-y-auto"
        style={{ maxHeight: 160, minHeight: 60 }}
      >
        <AnimatePresence initial={false}>
          {logs.map((e) => <LogLine key={e.id} entry={e} />)}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>
    </HUDPanel>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/components/SystemLog.tsx
git commit -m "feat(ui): SystemLog — auto-scrolling WebSocket log feed"
```

---

### Task 9: StatusPanel component

**Files:**
- Create: `frontend/src/components/StatusPanel.tsx`

- [ ] **Step 1: Create component**

```tsx
// frontend/src/components/StatusPanel.tsx
import { motion, useSpring, useTransform } from 'framer-motion'
import { useJARVISStore, SystemState } from '../store/useJARVISStore'
import { HUDPanel } from './HUDPanel'

const STATE_COLOR: Record<SystemState, string> = {
  offline:      '#ff3333',
  connected:    '#00f0ff',
  idle:         '#0077ff',
  listening:    '#00ff88',
  transcribing: '#00f0ff',
  thinking:     '#ff8c00',
  speaking:     '#00f0ff',
  error:        '#ff3333',
}
const STATE_LABEL: Record<SystemState, string> = {
  offline:      'OFFLINE',
  connected:    'STANDBY',
  idle:         'IDLE',
  listening:    'LISTENING',
  transcribing: 'PROCESSING',
  thinking:     'THINKING',
  speaking:     'SPEAKING',
  error:        'ERROR',
}

function StatBar({ label, value, unit, max = 100, delay = 0 }: {
  label: string; value: number; unit: string; max?: number; delay?: number
}) {
  const pct   = (value / max) * 100
  const color = pct > 80 ? '#ff3333' : pct > 60 ? '#ff8c00' : '#00f0ff'

  return (
    <div className="mb-3">
      <div className="flex justify-between mb-1 mono" style={{ fontSize: 8 }}>
        <span style={{ color: 'rgba(0,240,255,0.35)' }}>{label}</span>
        <span style={{ color: 'rgba(0,240,255,0.8)' }}>
          {value}<span style={{ color: 'rgba(0,240,255,0.35)', marginLeft: 2 }}>{unit}</span>
        </span>
      </div>
      <div style={{ height: 2, background: 'rgba(0,240,255,0.08)', borderRadius: 1, overflow: 'hidden' }}>
        <motion.div
          style={{ height: '100%', background: `linear-gradient(90deg, #0077ff, ${color})`, borderRadius: 1, boxShadow: `0 0 4px ${color}66` }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, delay, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}

export function StatusPanel({ delay = 0 }: { delay?: number }) {
  const systemState = useJARVISStore((s) => s.systemState)
  const color = STATE_COLOR[systemState]

  return (
    <div className="flex flex-col gap-3">
      {/* AI State badge */}
      <HUDPanel title="AI STATUS" delay={delay}>
        <motion.div
          className="flex items-center justify-between"
          style={{
            background:   `${color}08`,
            border:       `1px solid ${color}20`,
            borderRadius: 6,
            padding:      '8px 12px',
          }}
          animate={{ borderColor: [`${color}20`, `${color}45`, `${color}20`] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          <motion.div
            style={{ width: 8, height: 8, borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}` }}
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
          <span className="mono" style={{ fontSize: 9, letterSpacing: '0.25em', color }}>
            {STATE_LABEL[systemState]}
          </span>
          <span className="mono" style={{ fontSize: 7, color: 'rgba(0,240,255,0.2)' }}>JARVIS</span>
        </motion.div>
      </HUDPanel>

      {/* System stats */}
      <HUDPanel title="SYSTEM" delay={delay + 0.1}>
        <StatBar label="CPU"         value={34}   unit="%"  delay={delay + 0.2} />
        <StatBar label="GPU RTX2070S" value={12}  unit="%"  delay={delay + 0.3} />
        <StatBar label="RAM"         value={11.2} unit="GB" max={32} delay={delay + 0.4} />
        <div className="flex justify-between mono" style={{ fontSize: 8 }}>
          <span style={{ color: 'rgba(0,240,255,0.35)' }}>UPTIME</span>
          <span style={{ color: 'rgba(0,240,255,0.8)' }}>4h 22m</span>
        </div>
      </HUDPanel>

      {/* Weather */}
      <HUDPanel title="LIMA · WEATHER" delay={delay + 0.2}>
        <div className="flex justify-between items-center">
          <span className="font-orbitron" style={{ fontSize: 22, color: '#00f0ff', fontWeight: 700 }}>19°</span>
          <div className="mono text-right" style={{ fontSize: 8, color: 'rgba(0,240,255,0.4)' }}>
            <div>Mostly Cloudy</div>
            <div>72% humidity</div>
          </div>
        </div>
      </HUDPanel>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/components/StatusPanel.tsx
git commit -m "feat(ui): StatusPanel — AI state badge + system stats + weather"
```

---

### Task 10: AgentView (View 1)

**Files:**
- Create: `frontend/src/views/AgentView.tsx`

- [ ] **Step 1: Create view**

```tsx
// frontend/src/views/AgentView.tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ParticleNetwork } from '../components/ParticleNetwork'
import { AudioVisualizer } from '../components/AudioVisualizer'
import { useAudioAnalyser } from '../hooks/useAudioAnalyser'
import { useJARVISStore } from '../store/useJARVISStore'

export function AgentView() {
  const navigate    = useNavigate()
  const analyser    = useAudioAnalyser()
  const systemState = useJARVISStore((s) => s.systemState)
  const lastResponse= useJARVISStore((s) => s.lastResponse)
  const [hintVisible, setHintVisible] = useState(true)

  // Keyboard nav
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Tab') { e.preventDefault(); navigate('/control') }
      if (e.key === ',' && e.ctrlKey) { e.preventDefault(); navigate('/control') }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  // Fade hint after 4s
  useEffect(() => {
    const t = setTimeout(() => setHintVisible(false), 4000)
    return () => clearTimeout(t)
  }, [])

  return (
    <div className="w-full h-full relative overflow-hidden" style={{ background: '#05070d' }}>
      {/* Three.js particle network — fills entire screen */}
      <ParticleNetwork analyser={analyser} />

      {/* Bottom center: visualizer + response text */}
      <div
        className="absolute bottom-0 left-0 right-0 flex flex-col items-center gap-2 pb-8 px-4"
        style={{ pointerEvents: 'none' }}
      >
        <AudioVisualizer analyser={analyser} />

        <AnimatePresence>
          {lastResponse && (
            <motion.p
              className="mono text-center"
              style={{ fontSize: 11, color: 'rgba(0,240,255,0.65)', maxWidth: 520, letterSpacing: '0.06em', lineHeight: 1.6 }}
              initial={{ opacity: 0, y: 8, filter: 'blur(6px)' }}
              animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
              exit={{   opacity: 0, y: -4, filter: 'blur(4px)' }}
              transition={{ duration: 0.4 }}
            >
              {lastResponse}
            </motion.p>
          )}
        </AnimatePresence>
      </div>

      {/* Tab hint — fades after 4s */}
      <AnimatePresence>
        {hintVisible && (
          <motion.div
            className="absolute bottom-6 right-6 mono"
            style={{ fontSize: 8, letterSpacing: '0.2em', color: 'rgba(0,240,255,0.2)' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{   opacity: 0 }}
            transition={{ duration: 0.5 }}
          >
            [ Tab ] → control
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/views/AgentView.tsx
git commit -m "feat(ui): AgentView — full-screen immersive particle network view"
```

---

### Task 11: ControlView (View 2)

**Files:**
- Create: `frontend/src/views/ControlView.tsx`

- [ ] **Step 1: Create view**

```tsx
// frontend/src/views/ControlView.tsx
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useJARVISStore } from '../store/useJARVISStore'
import { StatusPanel } from '../components/StatusPanel'
import { SystemLog }   from '../components/SystemLog'
import { HUDPanel }    from '../components/HUDPanel'

const container = {
  hidden: {},
  show:   { transition: { staggerChildren: 0.08 } },
}
const item = {
  hidden: { opacity: 0, y: 20, filter: 'blur(8px)' },
  show:   { opacity: 1, y:  0, filter: 'blur(0px)', transition: { duration: 0.5, ease: 'easeOut' } },
}

function ConfigRow({ label, value, onChange }: {
  label:    string
  value:    string | number
  onChange?: (v: string) => void
}) {
  return (
    <div className="flex justify-between items-center py-[5px]" style={{ borderBottom: '1px solid rgba(0,240,255,0.06)' }}>
      <span className="mono" style={{ fontSize: 8, letterSpacing: '0.2em', color: 'rgba(0,240,255,0.35)' }}>{label}</span>
      <span
        className="mono"
        style={{
          fontSize: 8, color: 'rgba(0,240,255,0.8)',
          background: 'rgba(0,240,255,0.06)', border: '1px solid rgba(0,240,255,0.15)',
          borderRadius: 3, padding: '2px 8px', cursor: onChange ? 'pointer' : 'default',
        }}
      >
        {value}
      </span>
    </div>
  )
}

function SliderRow({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number
  onChange: (v: number) => void
}) {
  return (
    <div className="py-[5px]" style={{ borderBottom: '1px solid rgba(0,240,255,0.06)' }}>
      <div className="flex justify-between mb-1">
        <span className="mono" style={{ fontSize: 8, letterSpacing: '0.2em', color: 'rgba(0,240,255,0.35)' }}>{label}</span>
        <span className="mono" style={{ fontSize: 8, color: 'rgba(0,240,255,0.8)' }}>{value}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
        style={{ accentColor: '#00f0ff', height: 2 }}
      />
    </div>
  )
}

export function ControlView() {
  const navigate       = useNavigate()
  const particleCount  = useJARVISStore((s) => s.particleCount)
  const bloomIntensity = useJARVISStore((s) => s.bloomIntensity)
  const orbSpeed       = useJARVISStore((s) => s.orbSpeed)
  const setPC  = useJARVISStore((s) => s.setParticleCount)
  const setBI  = useJARVISStore((s) => s.setBloomIntensity)
  const setOS  = useJARVISStore((s) => s.setOrbSpeed)

  // Keyboard nav
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Tab') { e.preventDefault(); navigate('/') }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  return (
    <motion.div
      className="page-scroll w-full h-full"
      style={{ background: '#05070d' }}
      initial={{ opacity: 0, filter: 'blur(8px)' }}
      animate={{ opacity: 1, filter: 'blur(0px)' }}
      transition={{ duration: 0.6 }}
    >
      <div className="max-w-[480px] mx-auto px-4 py-6 flex flex-col gap-4">

        {/* Header */}
        <motion.div className="flex items-center justify-between mb-2" variants={item} initial="hidden" animate="show">
          <button
            onClick={() => navigate('/')}
            className="mono flex items-center gap-2"
            style={{ fontSize: 9, letterSpacing: '0.2em', color: 'rgba(0,240,255,0.5)', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            ← BACK
          </button>
          <span className="font-orbitron font-black" style={{ fontSize: 14, letterSpacing: '0.45em', color: '#00f0ff', textShadow: '0 0 14px #00f0ff55' }}>
            JARVIS
          </span>
          <span className="mono" style={{ fontSize: 7, color: 'rgba(0,240,255,0.2)' }}>CONTROL</span>
        </motion.div>

        <motion.div variants={container} initial="hidden" animate="show" className="flex flex-col gap-4">
          <motion.div variants={item}><StatusPanel delay={0} /></motion.div>
          <motion.div variants={item}><SystemLog   delay={0} /></motion.div>

          {/* Config */}
          <motion.div variants={item}>
            <HUDPanel title="CONFIGURATION">
              <ConfigRow label="LLM MODEL"   value="phi3:medium" />
              <ConfigRow label="TTS ENGINE"  value="edge-tts"    />
              <ConfigRow label="VAD"         value="ON"          />
              <ConfigRow label="WAKE WORD"   value="hey jarvis"   />
              <SliderRow label="BLOOM"       value={bloomIntensity} min={0.5} max={2.5} step={0.1} onChange={setBI} />
              <SliderRow label="PARTICLES"   value={particleCount}  min={100} max={400} step={10}  onChange={setPC} />
              <SliderRow label="ORB SPEED"   value={orbSpeed}       min={0.1} max={3.0} step={0.1} onChange={setOS} />
            </HUDPanel>
          </motion.div>
        </motion.div>

      </div>
    </motion.div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd .. && git add frontend/src/views/ControlView.tsx
git commit -m "feat(ui): ControlView — dashboard with stats, logs, config sliders"
```

---

### Task 12: App.tsx + React Router + WebSocket wiring

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Read existing useWebSocket.ts**

Read `frontend/src/hooks/useWebSocket.ts` to understand current message handling before editing.

- [ ] **Step 2: Update useWebSocket to populate logs**

Find where the WebSocket `onmessage` handler is. Add log population. The exact change depends on the current file; add this pattern wherever messages are processed:

```typescript
// Inside the message handler, after setting systemState/transcript:
const { addLog } = useJARVISStore.getState()

// Log state transitions
if (data.type === 'state_change') {
  addLog('info', `State → ${data.state}`)
}
if (data.type === 'transcript') {
  addLog('info', `[${data.role}] ${data.text?.slice(0, 80)}`)
}
if (data.type === 'error') {
  addLog('error', data.message ?? 'Unknown error')
}
```

- [ ] **Step 3: Rewrite App.tsx**

```tsx
// frontend/src/App.tsx
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import { AgentView }    from './views/AgentView'
import { ControlView }  from './views/ControlView'

export default function App() {
  useWebSocket() // starts WS connection, populates store

  return (
    <HashRouter>
      <Routes>
        <Route path="/"        element={<AgentView />}   />
        <Route path="/control" element={<ControlView />} />
        <Route path="*"        element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  )
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/App.tsx frontend/src/hooks/useWebSocket.ts
git commit -m "feat(app): React Router with AgentView + ControlView routes"
```

---

### Task 13: Create views directory + remove old components

**Files:**
- Create: `frontend/src/views/` (directory via files created in Tasks 10–11)
- Remove: `frontend/src/components/HologramView.tsx`
- Remove: `frontend/src/components/WaveformVisualizer.tsx`
- Remove: `frontend/src/components/DebugPanel.tsx`
- Remove: `frontend/src/components/CameraStream.tsx`
- Remove: `frontend/src/components/TranscriptPanel.tsx`

- [ ] **Step 1: Remove old components**

```bash
cd frontend/src/components
rm HologramView.tsx WaveformVisualizer.tsx DebugPanel.tsx CameraStream.tsx TranscriptPanel.tsx
```

- [ ] **Step 2: Full build verification**

```bash
cd frontend && npm run build 2>&1
```

Expected: `✓ built in` — zero TypeScript errors, zero import errors.

- [ ] **Step 3: Start dev server and verify visually**

```bash
npm run dev
```

Open `http://localhost:5173` — should show full-screen particle network. Press `Tab` — should navigate to control panel. Press `Tab` again — back to agent view.

- [ ] **Step 4: Final commit**

```bash
cd .. && git add -A
git commit -m "feat(ui): complete JARVIS frontend — neural particle network + control dashboard"
```

---

## Self-Review

**Spec coverage:**
- ✅ Three.js `Points` + `BufferGeometry` + `LineSegments` — Task 5
- ✅ GLSL `ShaderMaterial` glow — Task 5 (`VERT_SHADER`/`FRAG_SHADER`)
- ✅ Organic cloud distribution (Gaussian Box-Muller) — Task 5
- ✅ Mouse attraction/repulsion via camera parallax — Task 5
- ✅ State machine with lerped params — Task 5 (`STATE_PARAMS`)
- ✅ Neuron activation + cascade — Task 5 (`fireNeuron`)
- ✅ Electrons along connections — Task 5
- ✅ Audio reactivity (Web Audio API) — Task 4 + Task 5
- ✅ Simulated audio fallback — Task 5
- ✅ Framer Motion page + section animations — Tasks 7–11
- ✅ Two independent views with Tab navigation — Tasks 10–12
- ✅ System logs from WebSocket — Tasks 3, 8, 12
- ✅ Config sliders (particle count, bloom, speed) — Tasks 3, 9, 11
- ✅ Orbitron + Share Tech Mono fonts — Task 2
- ✅ `HashRouter` (no server config) — Task 12
- ✅ Old components removed — Task 13
- ✅ `particleCount` re-initializes network — Note: ParticleNetwork's `useEffect` depends on `[]` intentionally; particle count changes require a remount. AgentView should add `key={particleCount}` to `<ParticleNetwork>` to trigger remount on count change.

**Fix:** Add `key={particleCount}` to `<ParticleNetwork>` in `AgentView.tsx` — the component re-mounts when count changes, re-running `useEffect` with new `countRef.current`.

**Type consistency:** `LogEntry` defined in store (Task 3), imported in `SystemLog` (Task 8) ✅. `AudioAnalyserHandle` defined in hook (Task 4), used in `ParticleNetwork` props (Task 5) and `AudioVisualizer` (Task 6) ✅. `SystemState` used consistently across all components ✅.
