// frontend/src/components/ParticleNetwork.tsx
//
// Sphere-surface neural network with synaptic firing.
// — Nodes on sphere shell with hub/dendrite structure
// — Synapse pulses travel along axons (connections)
// — Arriving pulses trigger cascades on adjacent connections
// — Connection "flash" traces the dendritic path after each pulse
// — Node "flash" brightens the soma on reception

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'
import { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'

// ── Per-state parameters ──────────────────────────────────────────────────

interface StateParams {
  rotSpeed:   number
  radius:     number
  connAngle:  number   // max connection angle (radians)
  brightness: number
  pulseAmt:   number
  spawnRate:  number   // synapse pulses spawned per frame (base)
  color:      [number, number, number]
}

const STATE_PARAMS: Record<SystemState, StateParams> = {
  offline:      { rotSpeed: 0.0008, radius: 100, connAngle: 0.65, brightness: 0.50, pulseAmt: 0,    spawnRate: 0.005, color: [0.45, 0.55, 0.65] },
  connected:    { rotSpeed: 0.0012, radius: 100, connAngle: 0.72, brightness: 0.70, pulseAmt: 0,    spawnRate: 0.012, color: [0.70, 0.88, 1.00] },
  idle:         { rotSpeed: 0.0014, radius: 100, connAngle: 0.75, brightness: 0.75, pulseAmt: 0,    spawnRate: 0.014, color: [0.75, 0.90, 1.00] },
  listening:    { rotSpeed: 0.0022, radius: 100, connAngle: 0.88, brightness: 1.10, pulseAmt: 0.60, spawnRate: 0.050, color: [0.00, 1.00, 0.55] },
  transcribing: { rotSpeed: 0.0026, radius: 100, connAngle: 0.90, brightness: 1.10, pulseAmt: 0.40, spawnRate: 0.060, color: [0.00, 0.95, 0.75] },
  thinking:     { rotSpeed: 0.0042, radius: 100, connAngle: 0.92, brightness: 1.30, pulseAmt: 0.50, spawnRate: 0.100, color: [1.00, 0.55, 0.10] },
  speaking:     { rotSpeed: 0.0030, radius: 100, connAngle: 0.90, brightness: 1.20, pulseAmt: 0.70, spawnRate: 0.070, color: [0.30, 0.90, 1.00] },
  error:        { rotSpeed: 0.0028, radius: 100, connAngle: 0.68, brightness: 1.00, pulseAmt: 0.25, spawnRate: 0.025, color: [1.00, 0.25, 0.25] },
}

// ── GLSL — Neuron nodes ───────────────────────────────────────────────────

const NODE_VERT = /* glsl */`
  attribute float aSize;
  attribute float aGlow;
  varying   float vGlow;
  varying   float vDepth;
  void main() {
    vGlow = aGlow;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth  = clamp((-mv.z - 60.0) / 280.0, 0.0, 1.0);
    gl_PointSize = aSize * (350.0 / -mv.z) * (1.0 + aGlow * 2.2);
    gl_Position  = projectionMatrix * mv;
  }
`
const NODE_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uBright;
  varying float vGlow;
  varying float vDepth;
  void main() {
    vec2  uv = gl_PointCoord - 0.5;
    float d  = length(uv);
    if (d > 0.5) discard;
    float core = 1.0 - smoothstep(0.0, 0.18, d);
    float halo = 1.0 - smoothstep(0.0, 0.50, d);
    float a    = (core * 0.95 + halo * 0.30) * uBright * (0.35 + vDepth * 0.65);
    vec3  col  = mix(uColor, vec3(1.0), vGlow * 0.6 + core * 0.2);
    gl_FragColor = vec4(col * (1.0 + vGlow * 0.9), a);
  }
`

// ── GLSL — Axon lines ─────────────────────────────────────────────────────

const LINE_VERT = /* glsl */`
  attribute float aAlpha;
  varying   float vAlpha;
  void main() {
    vAlpha      = aAlpha;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`
const LINE_FRAG = /* glsl */`
  uniform vec3  uColor;
  varying float vAlpha;
  void main() {
    gl_FragColor = vec4(uColor, vAlpha);
  }
`

// ── GLSL — Synapse pulses ─────────────────────────────────────────────────

const SYN_VERT = /* glsl */`
  attribute float aBright;
  varying   float vBright;
  void main() {
    vBright = aBright;
    vec4 mv  = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = 10.0 * aBright * (300.0 / -mv.z);
    gl_Position  = projectionMatrix * mv;
  }
`
const SYN_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uWarm;   // 0=normal, 1=thinking warm tint
  varying float vBright;
  void main() {
    vec2  uv = gl_PointCoord - 0.5;
    float d  = length(uv);
    if (d > 0.5) discard;
    float core = 1.0 - smoothstep(0.00, 0.12, d);
    float halo = 1.0 - smoothstep(0.00, 0.50, d);
    float a    = (core + halo * 0.5) * vBright;
    vec3  warm = vec3(0.40, 0.85, 1.00);   // electric cyan-blue for thinking
    vec3  col  = mix(uColor, warm, uWarm * 0.75);
    col = mix(col, vec3(1.0), core * 0.35);
    gl_FragColor = vec4(col, a);
  }
`

// ── Synapse pulse data ────────────────────────────────────────────────────

interface Pulse {
  c:        number   // connection index (into connA/connB)
  t:        number   // 0 → 1 travel progress
  speed:    number   // Δt per frame
  bright:   number   // brightness 0–1
  cascades: number   // remaining cascade depth
  fwd:      boolean  // A→B (true) or B→A (false)
}

// ── Component ─────────────────────────────────────────────────────────────

interface Props { analyser?: AudioAnalyserHandle }

const MAX_PULSES = 80

export function ParticleNetwork({ analyser }: Props) {
  const mountRef       = useRef<HTMLDivElement>(null)
  const systemState    = useCYRUSStore(s => s.systemState)
  const particleCount  = useCYRUSStore(s => s.particleCount)
  const bloomIntensity = useCYRUSStore(s => s.bloomIntensity)
  const orbSpeed       = useCYRUSStore(s => s.orbSpeed)

  const stateRef    = useRef(systemState)
  const countRef    = useRef(particleCount)
  const bloomRef    = useRef(bloomIntensity)
  const speedRef    = useRef(orbSpeed)
  const analyserRef = useRef(analyser)

  useEffect(() => { stateRef.current    = systemState    }, [systemState])
  useEffect(() => { countRef.current    = particleCount  }, [particleCount])
  useEffect(() => { bloomRef.current    = bloomIntensity }, [bloomIntensity])
  useEffect(() => { speedRef.current    = orbSpeed       }, [orbSpeed])
  useEffect(() => { analyserRef.current = analyser       }, [analyser])

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    // ── Renderer ───────────────────────────────────────────────────────
    const W = mount.clientWidth  || window.innerWidth
    const H = mount.clientHeight || window.innerHeight

    const scene    = new THREE.Scene()
    const camera   = new THREE.PerspectiveCamera(60, W / H, 0.1, 2000)
    camera.position.set(0, 0, 260)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;'
    mount.appendChild(renderer.domElement)

    // ── Sphere surface nodes ───────────────────────────────────────────
    const N      = countRef.current
    const BASE_R = 100

    const sTheta    = new Float32Array(N)
    const sPhi      = new Float32Array(N)
    const positions = new Float32Array(N * 3)
    const sizes     = new Float32Array(N)
    const glows     = new Float32Array(N)   // dynamic: base + nodeFlash
    const baseGlow  = new Float32Array(N)   // static: 0=normal, >0=hub
    const nodeFlash = new Float32Array(N)   // soma firing brightness

    for (let i = 0; i < N; i++) {
      const theta = Math.acos(2 * Math.random() - 1)
      const phi   = Math.random() * Math.PI * 2
      const r     = BASE_R + (Math.random() - 0.5) * 8

      sTheta[i] = theta
      sPhi[i]   = phi
      positions[i*3]   = r * Math.sin(theta) * Math.cos(phi)
      positions[i*3+1] = r * Math.cos(theta)
      positions[i*3+2] = r * Math.sin(theta) * Math.sin(phi)

      const isHub   = Math.random() < 0.14
      sizes[i]      = isHub ? 6.0 + Math.random() * 4.0 : 2.5 + Math.random() * 2.5
      baseGlow[i]   = isHub ? 0.7 + Math.random() * 0.3 : 0.05
      glows[i]      = baseGlow[i]
    }

    // ── Node mesh ──────────────────────────────────────────────────────
    const ptGeo = new THREE.BufferGeometry()
    ptGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const sizeAttr = new THREE.BufferAttribute(sizes, 1)
    sizeAttr.setUsage(THREE.DynamicDrawUsage)
    ptGeo.setAttribute('aSize', sizeAttr)
    const glowAttr = new THREE.BufferAttribute(glows, 1)
    glowAttr.setUsage(THREE.DynamicDrawUsage)
    ptGeo.setAttribute('aGlow', glowAttr)

    const ptMat = new THREE.ShaderMaterial({
      vertexShader: NODE_VERT, fragmentShader: NODE_FRAG,
      uniforms: {
        uColor:  { value: new THREE.Color(0.80, 0.92, 1.0) },
        uBright: { value: 0.90 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const points = new THREE.Points(ptGeo, ptMat)

    // ── Pre-compute unit vectors + connection graph ────────────────────
    const ux = new Float32Array(N)
    const uy = new Float32Array(N)
    const uz = new Float32Array(N)
    for (let i = 0; i < N; i++) {
      ux[i] = Math.sin(sTheta[i]) * Math.cos(sPhi[i])
      uy[i] = Math.cos(sTheta[i])
      uz[i] = Math.sin(sTheta[i]) * Math.sin(sPhi[i])
    }

    const MAX_CONN  = N * 6
    const connA     = new Int32Array(MAX_CONN)
    const connB     = new Int32Array(MAX_CONN)
    const connAng   = new Float32Array(MAX_CONN)
    let   nConn     = 0

    const BASE_ANGLE = 0.82
    for (let i = 0; i < N && nConn < MAX_CONN - 1; i++) {
      for (let j = i + 1; j < N && nConn < MAX_CONN - 1; j++) {
        const dot = Math.max(-1, Math.min(1, ux[i]*ux[j] + uy[i]*uy[j] + uz[i]*uz[j]))
        const ang = Math.acos(dot)
        if (ang < BASE_ANGLE) {
          connA[nConn]   = i
          connB[nConn]   = j
          connAng[nConn] = ang
          nConn++
        }
      }
    }

    // Per-node adjacency list (for cascade spawning)
    const nodeAdj: number[][] = Array.from({ length: N }, () => [])
    for (let c = 0; c < nConn; c++) {
      nodeAdj[connA[c]].push(c)
      nodeAdj[connB[c]].push(c)
    }

    // ── Axon line geometry ─────────────────────────────────────────────
    const connFlash    = new Float32Array(nConn)   // per-connection flash intensity
    const linePos      = new Float32Array(nConn * 6)
    const lineAlpha    = new Float32Array(nConn * 2)

    const lineGeo     = new THREE.BufferGeometry()
    const linePosAttr = new THREE.BufferAttribute(linePos,   3)
    const lineAlpAttr = new THREE.BufferAttribute(lineAlpha, 1)
    linePosAttr.setUsage(THREE.DynamicDrawUsage)
    lineAlpAttr.setUsage(THREE.DynamicDrawUsage)
    lineGeo.setAttribute('position', linePosAttr)
    lineGeo.setAttribute('aAlpha',   lineAlpAttr)

    const lineMat = new THREE.ShaderMaterial({
      vertexShader: LINE_VERT, fragmentShader: LINE_FRAG,
      uniforms: { uColor: { value: new THREE.Color(0.80, 0.92, 1.0) } },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const lineSegs = new THREE.LineSegments(lineGeo, lineMat)

    // ── Synapse pulse geometry ─────────────────────────────────────────
    const synPos    = new Float32Array(MAX_PULSES * 3)
    const synBright = new Float32Array(MAX_PULSES)

    const synGeo     = new THREE.BufferGeometry()
    const synPosAttr = new THREE.BufferAttribute(synPos,    3)
    const synBrtAttr = new THREE.BufferAttribute(synBright, 1)
    synPosAttr.setUsage(THREE.DynamicDrawUsage)
    synBrtAttr.setUsage(THREE.DynamicDrawUsage)
    synGeo.setAttribute('position', synPosAttr)
    synGeo.setAttribute('aBright',  synBrtAttr)

    const synMat = new THREE.ShaderMaterial({
      vertexShader: SYN_VERT, fragmentShader: SYN_FRAG,
      uniforms: {
        uColor: { value: new THREE.Color(0.80, 0.92, 1.0) },
        uWarm:  { value: 0.0 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const synPoints = new THREE.Points(synGeo, synMat)

    // ── Orbital scan rings (JARVIS-style halo) ─────────────────────────
    // Three thin rings just outside the neural sphere, each at a different tilt
    // and rotation speed. Opacity reacts to system state.
    const RING_DEFS = [
      { r: 114, tiltX: Math.PI / 2,        tiltZ: 0,              dZ:  0.00090 },
      { r: 119, tiltX: Math.PI / 2.8,      tiltZ: Math.PI / 5,    dZ: -0.00065 },
      { r: 124, tiltX: Math.PI / 1.6,      tiltZ: Math.PI / 3.2,  dZ:  0.00045 },
    ]

    const RING_SEGS = 160
    const ringLoops: THREE.LineLoop[] = []
    const ringMats:  THREE.LineBasicMaterial[] = []

    for (const def of RING_DEFS) {
      const pts = new Float32Array((RING_SEGS + 1) * 3)
      for (let i = 0; i <= RING_SEGS; i++) {
        const a = (i / RING_SEGS) * Math.PI * 2
        pts[i * 3]     = Math.cos(a) * def.r
        pts[i * 3 + 1] = Math.sin(a) * def.r
        pts[i * 3 + 2] = 0
      }
      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pts, 3))

      const mat = new THREE.LineBasicMaterial({
        color:       new THREE.Color(0.00, 0.82, 1.00),
        transparent: true,
        opacity:     0.0,
        blending:    THREE.AdditiveBlending,
        depthWrite:  false,
      })

      const loop = new THREE.LineLoop(geo, mat)
      loop.rotation.x = def.tiltX
      loop.rotation.z = def.tiltZ
      ringMats.push(mat)
      ringLoops.push(loop)
    }

    // Rings live outside the main group so they don't co-rotate with the sphere
    const ringGroup = new THREE.Group()
    ringLoops.forEach(l => ringGroup.add(l))
    scene.add(ringGroup)

    let lRingOpacity = 0.0

    // ── Scene group ────────────────────────────────────────────────────
    const group = new THREE.Group()
    group.add(points)
    group.add(lineSegs)
    group.add(synPoints)
    scene.add(group)

    // ── Pulse helpers ──────────────────────────────────────────────────
    const pulses: Pulse[] = []

    function spawnPulse(c: number, fwd: boolean, bright: number, cascades: number) {
      if (pulses.length >= MAX_PULSES) return
      pulses.push({
        c, t: 0,
        speed:    0.008 + Math.random() * 0.014,
        bright:   Math.min(1, bright),
        cascades,
        fwd,
      })
      // Flash this connection immediately
      connFlash[c] = Math.max(connFlash[c], bright * 0.9)
    }

    function spawnRandom(rate: number, audioBoost: number) {
      if (Math.random() > rate || pulses.length >= MAX_PULSES) return
      // Prefer hub nodes as origin
      let origin = Math.floor(Math.random() * N)
      if (Math.random() < 0.6) {
        for (let attempt = 0; attempt < 8; attempt++) {
          const k = Math.floor(Math.random() * N)
          if (baseGlow[k] > 0.3) { origin = k; break }
        }
      }
      const adj = nodeAdj[origin]
      if (adj.length === 0) return
      const c        = adj[Math.floor(Math.random() * adj.length)]
      const fwd      = connA[c] === origin
      const st       = stateRef.current
      const bright   = st === 'thinking' ? 0.85 + Math.random() * 0.15
                     : 0.65 + Math.random() * 0.30 + audioBoost * 0.1
      const cascades = st === 'thinking' ? 3 : 2
      spawnPulse(c, fwd, bright, cascades)
    }

    // ── Mouse / resize ─────────────────────────────────────────────────
    const mouse = { tx: 0, ty: 0, x: 0, y: 0 }
    const onMouse = (e: MouseEvent) => {
      mouse.tx = (e.clientX / window.innerWidth  - 0.5) * 2
      mouse.ty = (e.clientY / window.innerHeight - 0.5) * 2
    }
    window.addEventListener('mousemove', onMouse)

    const onResize = () => {
      const rw = mount.clientWidth  || window.innerWidth
      const rh = mount.clientHeight || window.innerHeight
      camera.aspect = rw / rh
      camera.updateProjectionMatrix()
      renderer.setSize(rw, rh)
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(mount)
    window.addEventListener('resize', onResize)

    // ── Lerped state ───────────────────────────────────────────────────
    const lerp = (a: number, b: number, t: number) => a + (b - a) * t

    let lRotSpeed  = 0.0012
    let lConnAngle = 0.75
    let lBright    = 0.90
    let lPulse     = 0.0
    let lRadius    = BASE_R
    let lSpawn     = 0.012
    let lColor     = new THREE.Color(0.80, 0.92, 1.0)
    let audioAmp   = 0
    let rotY       = 0
    let simT       = 0
    let rafId      = 0

    // ── Animation loop ─────────────────────────────────────────────────
    function animate() {
      rafId = requestAnimationFrame(animate)
      simT += 0.016

      const state = stateRef.current
      const tgt   = STATE_PARAMS[state]

      lRotSpeed  = lerp(lRotSpeed,  tgt.rotSpeed  * speedRef.current, 0.03)
      lConnAngle = lerp(lConnAngle, tgt.connAngle,                    0.025)
      lBright    = lerp(lBright,    tgt.brightness,                   0.03)
      lPulse     = lerp(lPulse,     tgt.pulseAmt,                     0.04)
      lRadius    = lerp(lRadius,    tgt.radius,                       0.02)
      lSpawn     = lerp(lSpawn,     tgt.spawnRate,                    0.05)
      lColor.lerp(new THREE.Color(...tgt.color), 0.04)

      mouse.x = lerp(mouse.x, mouse.tx, 0.06)
      mouse.y = lerp(mouse.y, mouse.ty, 0.06)

      // ── Audio input per state ────────────────────────────────────────
      const an = analyserRef.current
      let bass = 0, mid = 0

      if (state === 'listening' || state === 'transcribing') {
        // Real mic data
        bass = an ? an.getBass() : 0
        mid  = an ? an.getMid()  : 0
        audioAmp = lerp(audioAmp, bass, 0.18)
      } else if (state === 'speaking') {
        // Simulate TTS voice — rich harmonic oscillation
        bass = 0.25 + 0.55 * Math.abs(Math.sin(simT * 5.1) * Math.cos(simT * 2.3))
        mid  = 0.15 + 0.40 * Math.abs(Math.sin(simT * 8.7 + 1.2))
        audioAmp = lerp(audioAmp, bass, 0.10)
      } else if (state === 'thinking') {
        // Slow neural oscillation
        bass = 0.15 + 0.25 * Math.abs(Math.sin(simT * 1.8))
        mid  = 0.10 + 0.20 * Math.abs(Math.sin(simT * 2.6 + 0.8))
        audioAmp = lerp(audioAmp, bass * 0.6, 0.05)
      } else {
        audioAmp = lerp(audioAmp, 0, 0.05)
      }

      const pulse = lPulse * audioAmp

      // Rotate sphere
      rotY += lRotSpeed
      group.rotation.y = rotY + mouse.x * 0.35
      group.rotation.x = Math.sin(simT * 0.15) * 0.06 - mouse.y * 0.18

      // ── Per-node position with state-reactive displacement ───────────
      for (let i = 0; i < N; i++) {
        const ix  = i * 3
        let   r   = lRadius

        if (state === 'listening' || state === 'transcribing') {
          // Sphere breathes hard with mic — uniform + per-node jitter
          r += audioAmp * 45
          r += bass * 12 * Math.sin(sTheta[i] * 3 + sPhi[i] + simT * 6)
          // Node size also pulses — stored in sizes for glow effect
          sizes[i] = baseGlow[i] > 0.3
            ? (6.0 + audioAmp * 8)
            : (2.5 + audioAmp * 5)

        } else if (state === 'speaking') {
          // Latitude-band audio visualizer
          const lat   = sTheta[i] - Math.PI * 0.5
          const bassW = Math.exp(-lat * lat * 3)
          const midW  = 1 - bassW
          const az    = Math.sin(sPhi[i] * 3 + simT * 8)
          r += bass * 50 * bassW + mid * 32 * midW + az * bass * 12
          sizes[i] = baseGlow[i] > 0.3
            ? (6.0 + bass * 6 * bassW)
            : (2.5 + bass * 3 * bassW)

        } else if (state === 'thinking') {
          // Electric ripple across whole sphere
          const wave = Math.sin(sTheta[i] * 5 + simT * 3.5)
                     + Math.cos(sPhi[i]   * 4 + simT * 2.4) * 0.7
                     + Math.sin(sTheta[i] * 2 + sPhi[i] + simT * 1.8) * 0.4
          r += wave * 18 + audioAmp * 15
          sizes[i] = baseGlow[i] > 0.3
            ? (6.0 + Math.abs(wave) * 3)
            : (2.5 + Math.abs(wave) * 1.5)

        } else {
          // Idle — tiny organic drift, reset sizes
          r += Math.sin(sTheta[i] * 2 + simT * 0.8 + sPhi[i]) * 2
          sizes[i] = baseGlow[i] > 0.3 ? 6.0 : 2.5
        }

        positions[ix]   = ux[i] * r
        positions[ix+1] = uy[i] * r
        positions[ix+2] = uz[i] * r
      }

      // ── Spawn new pulses — rate scales with audio per state ──────────
      const audioBoost = state === 'thinking'   ? audioAmp * 2.5 + 1.2
                       : state === 'speaking'   ? audioAmp * 2.0
                       : state === 'listening'  ? audioAmp * 3.0
                       : 0
      spawnRandom(lSpawn, audioBoost)

      // ── Advance pulses + cascade ────────────────────────────────────
      for (let p = pulses.length - 1; p >= 0; p--) {
        const pulse = pulses[p]
        pulse.t += pulse.speed

        // Flash the axon this pulse is on
        connFlash[pulse.c] = Math.max(connFlash[pulse.c], pulse.bright * (1 - pulse.t) * 0.85)

        if (pulse.t >= 1.0) {
          // Arrived — fire the destination node
          const dest = pulse.fwd ? connB[pulse.c] : connA[pulse.c]
          nodeFlash[dest] = Math.min(1, nodeFlash[dest] + pulse.bright * 0.9)

          // Cascade: spawn pulses on adjacent connections
          if (pulse.cascades > 0) {
            const adj = nodeAdj[dest]
            for (const nc of adj) {
              if (nc === pulse.c) continue
              if (Math.random() < 0.28) {
                const fwd2 = connA[nc] === dest
                spawnPulse(nc, fwd2, pulse.bright * 0.65, pulse.cascades - 1)
              }
            }
          }
          pulses.splice(p, 1)
        }
      }

      // ── Write synapse dot positions ──────────────────────────────────
      const nPulses = pulses.length
      for (let p = 0; p < nPulses; p++) {
        const { c, t, bright, fwd } = pulses[p]
        const iA = connA[c], iB = connB[c]
        const ai = iA * 3, bi = iB * 3
        const tt = fwd ? t : 1 - t
        const sp = p * 3
        synPos[sp]   = positions[ai]   + (positions[bi]   - positions[ai])   * tt
        synPos[sp+1] = positions[ai+1] + (positions[bi+1] - positions[ai+1]) * tt
        synPos[sp+2] = positions[ai+2] + (positions[bi+2] - positions[ai+2]) * tt
        // Pulse brightens as it approaches destination (depolarization)
        synBright[p] = bright * (0.5 + t * 0.5)
      }
      synGeo.setDrawRange(0, nPulses)
      synPosAttr.needsUpdate = true
      synBrtAttr.needsUpdate = true

      // ── Decay flashes — thinking keeps axons lit longer ───────────────
      const connDecay = state === 'thinking' ? 0.955 : state === 'speaking' ? 0.90 : 0.91
      const nodeDecay = state === 'thinking' ? 0.940 : 0.88
      for (let c = 0; c < nConn; c++)  connFlash[c] *= connDecay
      for (let i = 0; i < N; i++)      nodeFlash[i] *= nodeDecay

      // ── Update node glow (base + soma flash) ─────────────────────────
      for (let i = 0; i < N; i++) {
        glows[i] = Math.min(1, baseGlow[i] + nodeFlash[i])
      }
      glowAttr.needsUpdate = true

      // ── Build axon lines ─────────────────────────────────────────────
      let drawn = 0
      for (let c = 0; c < nConn; c++) {
        if (connAng[c] > lConnAngle) continue
        const i  = connA[c], j = connB[c]
        const str  = 1 - connAng[c] / lConnAngle
        const baseA = str * 0.48 * lBright
        const alp   = Math.min(1, baseA + connFlash[c] * 0.90 + pulse * 0.10)
        const ix = i * 3, jx = j * 3
        const li = drawn * 6

        linePos[li]   = positions[ix];   linePos[li+1] = positions[ix+1]; linePos[li+2] = positions[ix+2]
        linePos[li+3] = positions[jx];   linePos[li+4] = positions[jx+1]; linePos[li+5] = positions[jx+2]
        lineAlpha[drawn*2]   = alp
        lineAlpha[drawn*2+1] = alp * 0.45
        drawn++
      }
      lineGeo.setDrawRange(0, drawn * 2)
      linePosAttr.needsUpdate = true
      lineAlpAttr.needsUpdate = true

      ptGeo.getAttribute('position').needsUpdate = true
      sizeAttr.needsUpdate = true

      // Uniforms
      const col  = lColor.clone()
      const warm = lerp(synMat.uniforms.uWarm.value, state === 'thinking' ? 1.0 : 0.0, 0.05)
      ptMat.uniforms.uColor.value.copy(col)
      ptMat.uniforms.uBright.value = lBright * bloomRef.current * 0.85
      lineMat.uniforms.uColor.value.copy(col)
      synMat.uniforms.uColor.value.copy(col)
      synMat.uniforms.uWarm.value  = warm

      // ── Orbital rings ─────────────────────────────────────────────
      const ringTarget =
        state === 'thinking'     ? 0.28 :
        state === 'speaking'     ? 0.20 :
        state === 'listening'    ? 0.18 :
        state === 'transcribing' ? 0.14 :
        state === 'idle'         ? 0.08 :
        state === 'connected'    ? 0.05 :
        0.0
      lRingOpacity = lerp(lRingOpacity, ringTarget, 0.04)

      for (let ri = 0; ri < ringLoops.length; ri++) {
        ringLoops[ri].rotation.z += RING_DEFS[ri].dZ * speedRef.current
        ringMats[ri].opacity = lRingOpacity
        ringMats[ri].color.copy(lColor)
      }
      // Ring group follows the sphere's Y-axis rotation at a slower rate
      ringGroup.rotation.y = rotY * 0.25
      ringGroup.rotation.x = group.rotation.x * 0.4

      renderer.render(scene, camera)
    }

    animate()

    return () => {
      cancelAnimationFrame(rafId)
      ro.disconnect()
      window.removeEventListener('mousemove', onMouse)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      ptGeo.dispose();   ptMat.dispose()
      lineGeo.dispose(); lineMat.dispose()
      synGeo.dispose();  synMat.dispose()
      ringLoops.forEach(l => l.geometry.dispose())
      ringMats.forEach(m => m.dispose())
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={mountRef} className="w-full h-full" />
}
