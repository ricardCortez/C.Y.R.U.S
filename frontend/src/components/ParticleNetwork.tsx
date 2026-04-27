// frontend/src/components/ParticleNetwork.tsx
//
// Sphere-surface neural network with synaptic firing.
// — Nodes on sphere shell with hub/dendrite structure
// — Synapse pulses travel along axons (connections)
// — Arriving pulses trigger cascades on adjacent connections
// — THINKING state: storm bursts, 5-level cascades, pulse rings, camera zoom

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useJARVISStore, SystemState } from '../store/useJARVISStore'
import { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'

// ── Per-state parameters ──────────────────────────────────────────────────

interface StateParams {
  rotSpeed:    number
  radius:      number
  connAngle:   number
  brightness:  number
  pulseAmt:    number
  spawnRate:   number
  color:       [number, number, number]
  camZ:        number   // camera Z target
  cascadeDepth: number  // max cascade levels
  cascadeProb:  number  // probability per adjacent connection
  connDecay:   number
  nodeDecay:   number
}

const STATE_PARAMS: Record<SystemState, StateParams> = {
  offline:      { rotSpeed: 0.0008, radius: 100, connAngle: 0.65, brightness: 0.50, pulseAmt: 0,    spawnRate: 0.005, color: [0.45, 0.55, 0.65], camZ: 260, cascadeDepth: 1, cascadeProb: 0.15, connDecay: 0.90, nodeDecay: 0.88 },
  connected:    { rotSpeed: 0.0012, radius: 100, connAngle: 0.72, brightness: 0.70, pulseAmt: 0,    spawnRate: 0.012, color: [0.70, 0.88, 1.00], camZ: 260, cascadeDepth: 2, cascadeProb: 0.20, connDecay: 0.91, nodeDecay: 0.88 },
  idle:         { rotSpeed: 0.0014, radius: 100, connAngle: 0.75, brightness: 0.75, pulseAmt: 0,    spawnRate: 0.014, color: [0.75, 0.90, 1.00], camZ: 260, cascadeDepth: 2, cascadeProb: 0.22, connDecay: 0.91, nodeDecay: 0.88 },
  listening:    { rotSpeed: 0.0022, radius: 100, connAngle: 0.88, brightness: 1.10, pulseAmt: 0.60, spawnRate: 0.055, color: [0.00, 1.00, 0.55], camZ: 255, cascadeDepth: 2, cascadeProb: 0.28, connDecay: 0.90, nodeDecay: 0.88 },
  transcribing: { rotSpeed: 0.0026, radius: 100, connAngle: 0.90, brightness: 1.10, pulseAmt: 0.40, spawnRate: 0.060, color: [0.00, 0.95, 0.75], camZ: 255, cascadeDepth: 2, cascadeProb: 0.28, connDecay: 0.90, nodeDecay: 0.88 },
  // THINKING: maximum neural activity
  thinking:     { rotSpeed: 0.0055, radius: 100, connAngle: 0.98, brightness: 1.55, pulseAmt: 0.70, spawnRate: 0.190, color: [1.00, 0.55, 0.10], camZ: 205, cascadeDepth: 5, cascadeProb: 0.44, connDecay: 0.972, nodeDecay: 0.962 },
  speaking:     { rotSpeed: 0.0030, radius: 100, connAngle: 0.90, brightness: 1.20, pulseAmt: 0.70, spawnRate: 0.070, color: [0.30, 0.90, 1.00], camZ: 250, cascadeDepth: 3, cascadeProb: 0.30, connDecay: 0.90, nodeDecay: 0.88 },
  error:        { rotSpeed: 0.0028, radius: 100, connAngle: 0.68, brightness: 1.00, pulseAmt: 0.25, spawnRate: 0.025, color: [1.00, 0.25, 0.25], camZ: 260, cascadeDepth: 1, cascadeProb: 0.15, connDecay: 0.91, nodeDecay: 0.88 },
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
    gl_PointSize = aSize * (350.0 / -mv.z) * (1.0 + aGlow * 2.5);
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
    vec3  col  = mix(uColor, vec3(1.0), vGlow * 0.65 + core * 0.25);
    gl_FragColor = vec4(col * (1.0 + vGlow * 1.1), a);
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
  attribute float aThink;   // 1.0 = thinking pulse, larger + warmer
  varying   float vBright;
  varying   float vThink;
  void main() {
    vBright  = aBright;
    vThink   = aThink;
    vec4 mv  = modelViewMatrix * vec4(position, 1.0);
    float sz = (10.0 + aThink * 8.0) * aBright * (300.0 / -mv.z);
    gl_PointSize = sz;
    gl_Position  = projectionMatrix * mv;
  }
`
const SYN_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uWarm;
  varying float vBright;
  varying float vThink;
  void main() {
    vec2  uv = gl_PointCoord - 0.5;
    float d  = length(uv);
    if (d > 0.5) discard;
    float core  = 1.0 - smoothstep(0.00, 0.12, d);
    float halo  = 1.0 - smoothstep(0.00, 0.50, d);
    float a     = (core + halo * 0.55) * vBright;
    // Thinking: amber-white hot center, normal: electric cyan-blue
    vec3  hotcol = mix(uColor, vec3(1.00, 0.85, 0.50), uWarm * 0.80);
    hotcol = mix(hotcol, vec3(1.0), core * (0.35 + uWarm * 0.30));
    gl_FragColor = vec4(hotcol, a);
  }
`

// ── GLSL — Thinking pulse rings ───────────────────────────────────────────

const RING_VERT = /* glsl */`
  attribute float aAlpha;
  varying   float vAlpha;
  void main() {
    vAlpha      = aAlpha;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`
const RING_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uWarm;
  varying float vAlpha;
  void main() {
    // Amber-tinted rings during thinking
    vec3 col = mix(uColor, vec3(1.0, 0.65, 0.2), uWarm * 0.6);
    gl_FragColor = vec4(col, vAlpha);
  }
`

// ── Synapse pulse data ────────────────────────────────────────────────────

interface Pulse {
  c:        number
  t:        number
  speed:    number
  bright:   number
  cascades: number
  fwd:      boolean
  isThink:  boolean  // larger, hotter electron
}

// ── Thinking pulse ring ───────────────────────────────────────────────────

interface ThinkRing {
  radius: number   // current radius (100 → 160)
  alpha:  number   // fades as it expands
  speed:  number
}

// ── Component ─────────────────────────────────────────────────────────────

interface Props { analyser?: AudioAnalyserHandle }

const MAX_PULSES   = 220
const MAX_RINGS    = 6
const STORM_PERIOD = 42   // frames between thinking storm bursts

export function ParticleNetwork({ analyser }: Props) {
  const mountRef       = useRef<HTMLDivElement>(null)
  const systemState    = useJARVISStore(s => s.systemState)
  const particleCount  = useJARVISStore(s => s.particleCount)
  const bloomIntensity = useJARVISStore(s => s.bloomIntensity)
  const orbSpeed       = useJARVISStore(s => s.orbSpeed)

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
    const glows     = new Float32Array(N)
    const baseGlow  = new Float32Array(N)
    const nodeFlash = new Float32Array(N)

    for (let i = 0; i < N; i++) {
      const theta = Math.acos(2 * Math.random() - 1)
      const phi   = Math.random() * Math.PI * 2
      const r     = BASE_R + (Math.random() - 0.5) * 8

      sTheta[i] = theta
      sPhi[i]   = phi
      positions[i*3]   = r * Math.sin(theta) * Math.cos(phi)
      positions[i*3+1] = r * Math.cos(theta)
      positions[i*3+2] = r * Math.sin(theta) * Math.sin(phi)

      const isHub = Math.random() < 0.14
      sizes[i]    = isHub ? 6.0 + Math.random() * 4.0 : 2.5 + Math.random() * 2.5
      baseGlow[i] = isHub ? 0.7 + Math.random() * 0.3 : 0.05
      glows[i]    = baseGlow[i]
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

    const MAX_CONN  = N * 3
    const connA     = new Int32Array(MAX_CONN)
    const connB     = new Int32Array(MAX_CONN)
    const connAng   = new Float32Array(MAX_CONN)
    let   nConn     = 0

    const LOCAL_ANGLE = 0.42
    for (let i = 0; i < N && nConn < Math.floor(MAX_CONN * 0.80); i++) {
      for (let j = i + 1; j < N && nConn < Math.floor(MAX_CONN * 0.80); j++) {
        const dot = Math.max(-1, Math.min(1, ux[i]*ux[j] + uy[i]*uy[j] + uz[i]*uz[j]))
        const ang = Math.acos(dot)
        if (ang < LOCAL_ANGLE) {
          connA[nConn] = i; connB[nConn] = j; connAng[nConn] = ang
          nConn++
        }
      }
    }
    const localCount   = nConn
    const randomTarget = Math.floor(localCount * 0.15)
    for (let attempt = 0; attempt < randomTarget * 8 && nConn < MAX_CONN - 1; attempt++) {
      const i = Math.floor(Math.random() * N)
      const j = Math.floor(Math.random() * N)
      if (i === j) continue
      const a = Math.min(i, j), b = Math.max(i, j)
      connA[nConn] = a; connB[nConn] = b; connAng[nConn] = 0.30 + Math.random() * 0.35
      nConn++
    }

    const nodeAdj: number[][] = Array.from({ length: N }, () => [])
    for (let c = 0; c < nConn; c++) {
      nodeAdj[connA[c]].push(c)
      nodeAdj[connB[c]].push(c)
    }

    // Hub node list for storm bursts
    const hubNodes: number[] = []
    for (let i = 0; i < N; i++) if (baseGlow[i] > 0.3) hubNodes.push(i)

    // ── Axon line geometry ─────────────────────────────────────────────
    const connFlash = new Float32Array(nConn)
    const linePos   = new Float32Array(nConn * 6)
    const lineAlpha = new Float32Array(nConn * 2)

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
    const synThink  = new Float32Array(MAX_PULSES)   // per-pulse isThink flag

    const synGeo     = new THREE.BufferGeometry()
    const synPosAttr = new THREE.BufferAttribute(synPos,    3)
    const synBrtAttr = new THREE.BufferAttribute(synBright, 1)
    const synThkAttr = new THREE.BufferAttribute(synThink,  1)
    synPosAttr.setUsage(THREE.DynamicDrawUsage)
    synBrtAttr.setUsage(THREE.DynamicDrawUsage)
    synThkAttr.setUsage(THREE.DynamicDrawUsage)
    synGeo.setAttribute('position', synPosAttr)
    synGeo.setAttribute('aBright',  synBrtAttr)
    synGeo.setAttribute('aThink',   synThkAttr)

    const synMat = new THREE.ShaderMaterial({
      vertexShader: SYN_VERT, fragmentShader: SYN_FRAG,
      uniforms: {
        uColor: { value: new THREE.Color(0.80, 0.92, 1.0) },
        uWarm:  { value: 0.0 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const synPoints = new THREE.Points(synGeo, synMat)

    // ── Thinking pulse ring geometry ───────────────────────────────────
    // Three rings — each expands outward when spawned during thinking
    const RING_SEGS  = 96
    const ringBuf    = new Float32Array(MAX_RINGS * RING_SEGS * 3)
    const ringAlpBuf = new Float32Array(MAX_RINGS * RING_SEGS)
    const rings: ThinkRing[] = []

    const ringGeo    = new THREE.BufferGeometry()
    const ringPosA   = new THREE.BufferAttribute(ringBuf,    3)
    const ringAlpA   = new THREE.BufferAttribute(ringAlpBuf, 1)
    ringPosA.setUsage(THREE.DynamicDrawUsage)
    ringAlpA.setUsage(THREE.DynamicDrawUsage)
    ringGeo.setAttribute('position', ringPosA)
    ringGeo.setAttribute('aAlpha',   ringAlpA)

    const ringMat = new THREE.ShaderMaterial({
      vertexShader: RING_VERT, fragmentShader: RING_FRAG,
      uniforms: {
        uColor: { value: new THREE.Color(1.0, 0.55, 0.10) },
        uWarm:  { value: 0.0 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    // Ring draws as LineLoop per ring — use LineSegments with manual pairs
    const ringLines = new THREE.LineSegments(ringGeo, ringMat)

    // ── Scene group ────────────────────────────────────────────────────
    const group = new THREE.Group()
    group.add(points)
    group.add(lineSegs)
    group.add(synPoints)
    group.add(ringLines)
    scene.add(group)

    // ── Pulse helpers ──────────────────────────────────────────────────
    const pulses: Pulse[] = []

    function spawnPulse(c: number, fwd: boolean, bright: number, cascades: number, isThink: boolean) {
      if (pulses.length >= MAX_PULSES) return
      pulses.push({
        c, t: 0,
        speed:    isThink ? 0.010 + Math.random() * 0.018 : 0.008 + Math.random() * 0.014,
        bright:   Math.min(1, bright),
        cascades,
        fwd,
        isThink,
      })
      connFlash[c] = Math.max(connFlash[c], bright * 0.9)
    }

    function spawnRandom(rate: number, audioBoost: number) {
      if (Math.random() > rate || pulses.length >= MAX_PULSES) return
      let origin = Math.floor(Math.random() * N)
      if (Math.random() < 0.6 && hubNodes.length > 0) {
        origin = hubNodes[Math.floor(Math.random() * hubNodes.length)]
      }
      const adj = nodeAdj[origin]
      if (adj.length === 0) return
      const c      = adj[Math.floor(Math.random() * adj.length)]
      const fwd    = connA[c] === origin
      const st     = stateRef.current
      const think  = st === 'thinking'
      const bright = think ? 0.90 + Math.random() * 0.10 : 0.65 + Math.random() * 0.30 + audioBoost * 0.1
      const tgt    = STATE_PARAMS[st]
      spawnPulse(c, fwd, bright, tgt.cascadeDepth, think)
    }

    // Storm burst: fire pulses simultaneously from many hubs
    function stormBurst() {
      const count = 10 + Math.floor(Math.random() * 8)
      for (let k = 0; k < count; k++) {
        const hub = hubNodes[Math.floor(Math.random() * hubNodes.length)]
        const adj = nodeAdj[hub]
        if (adj.length === 0) continue
        const c   = adj[Math.floor(Math.random() * adj.length)]
        const fwd = connA[c] === hub
        spawnPulse(c, fwd, 0.92 + Math.random() * 0.08, 5, true)
      }
    }

    // Spawn thinking pulse ring
    function spawnRing() {
      if (rings.length >= MAX_RINGS) return
      rings.push({
        radius: BASE_R * 0.98,
        alpha:  0.60,
        speed:  0.9 + Math.random() * 0.4,
      })
    }

    // ── Resize ─────────────────────────────────────────────────────────
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
    let lCamZ      = 260
    let lWarm      = 0.0
    let lColor     = new THREE.Color(0.80, 0.92, 1.0)
    let audioAmp   = 0
    let rotY       = 0
    let rotX       = 0
    let simT       = 0
    let frameN     = 0
    let rafId      = 0

    // ── Animation loop ─────────────────────────────────────────────────
    function animate() {
      rafId = requestAnimationFrame(animate)
      simT += 0.016
      frameN++

      const state = stateRef.current
      const tgt   = STATE_PARAMS[state]
      const think = state === 'thinking'

      lRotSpeed  = lerp(lRotSpeed,  tgt.rotSpeed  * speedRef.current, 0.03)
      lConnAngle = lerp(lConnAngle, tgt.connAngle,                    0.025)
      lBright    = lerp(lBright,    tgt.brightness,                   0.03)
      lPulse     = lerp(lPulse,     tgt.pulseAmt,                     0.04)
      lRadius    = lerp(lRadius,    tgt.radius,                       0.02)
      lSpawn     = lerp(lSpawn,     tgt.spawnRate,                    0.05)
      lCamZ      = lerp(lCamZ,      tgt.camZ,                         0.02)
      lWarm      = lerp(lWarm,      think ? 1.0 : 0.0,                0.04)
      lColor.lerp(new THREE.Color(...tgt.color), 0.04)

      // Camera zoom toward sphere during thinking
      camera.position.z = lCamZ

      // ── Audio input per state ────────────────────────────────────────
      const an = analyserRef.current
      let bass = 0, mid = 0

      if (state === 'listening' || state === 'transcribing') {
        bass = an ? an.getBass() : 0
        mid  = an ? an.getMid()  : 0
        audioAmp = lerp(audioAmp, bass, 0.18)
      } else if (state === 'speaking') {
        bass = 0.25 + 0.55 * Math.abs(Math.sin(simT * 5.1) * Math.cos(simT * 2.3))
        mid  = 0.15 + 0.40 * Math.abs(Math.sin(simT * 8.7 + 1.2))
        audioAmp = lerp(audioAmp, bass, 0.10)
      } else if (think) {
        // Neural oscillation — multi-frequency to simulate brain waves
        bass = 0.20 + 0.35 * Math.abs(Math.sin(simT * 2.1)) + 0.10 * Math.abs(Math.sin(simT * 5.7))
        mid  = 0.12 + 0.25 * Math.abs(Math.sin(simT * 3.4 + 0.8))
        audioAmp = lerp(audioAmp, bass * 0.7, 0.06)
      } else {
        audioAmp = lerp(audioAmp, 0, 0.05)
      }

      const pulse = lPulse * audioAmp

      // ── Storm burst during thinking ──────────────────────────────────
      if (think && frameN % STORM_PERIOD === 0) stormBurst()

      // ── Spawn thinking rings periodically ───────────────────────────
      if (think && frameN % 55 === 0) spawnRing()

      // Rotate sphere
      rotY += lRotSpeed
      rotX  = Math.sin(simT * 0.15) * 0.06
      group.rotation.y = rotY
      group.rotation.x = rotX

      // ── Per-node position with state-reactive displacement ───────────
      for (let i = 0; i < N; i++) {
        const ix = i * 3
        let   r  = lRadius

        if (state === 'listening' || state === 'transcribing') {
          r += audioAmp * 45
          r += bass * 12 * Math.sin(sTheta[i] * 3 + sPhi[i] + simT * 6)
          sizes[i] = baseGlow[i] > 0.3 ? (6.0 + audioAmp * 8) : (2.5 + audioAmp * 5)

        } else if (state === 'speaking') {
          const lat  = sTheta[i] - Math.PI * 0.5
          const bassW = Math.exp(-lat * lat * 3)
          const midW  = 1 - bassW
          const az    = Math.sin(sPhi[i] * 3 + simT * 8)
          r += bass * 50 * bassW + mid * 32 * midW + az * bass * 12
          sizes[i] = baseGlow[i] > 0.3 ? (6.0 + bass * 6 * bassW) : (2.5 + bass * 3 * bassW)

        } else if (think) {
          // Complex multi-frequency neural ripple
          const wave1 = Math.sin(sTheta[i] * 5 + simT * 3.5)
          const wave2 = Math.cos(sPhi[i]   * 4 + simT * 2.4) * 0.7
          const wave3 = Math.sin(sTheta[i] * 2 + sPhi[i] + simT * 1.8) * 0.4
          const wave4 = Math.sin(sTheta[i] * 7 + sPhi[i] * 3 + simT * 5.2) * 0.25
          const wave  = wave1 + wave2 + wave3 + wave4
          r += wave * 20 + audioAmp * 18
          // Hub nodes pulse brighter and larger during thinking
          sizes[i] = baseGlow[i] > 0.3
            ? (6.0 + Math.abs(wave) * 3.5 + audioAmp * 4)
            : (2.5 + Math.abs(wave) * 1.8)

        } else {
          r += Math.sin(sTheta[i] * 2 + simT * 0.8 + sPhi[i]) * 2
          sizes[i] = baseGlow[i] > 0.3 ? 6.0 : 2.5
        }

        positions[ix]   = ux[i] * r
        positions[ix+1] = uy[i] * r
        positions[ix+2] = uz[i] * r
      }

      // ── Spawn new pulses ────────────────────────────────────────────
      const audioBoost = think            ? audioAmp * 3.0 + 1.5
                       : state==='speaking'   ? audioAmp * 2.0
                       : state==='listening'  ? audioAmp * 3.0
                       : 0
      spawnRandom(lSpawn, audioBoost)

      // ── Advance pulses + cascade ────────────────────────────────────
      for (let p = pulses.length - 1; p >= 0; p--) {
        const pu = pulses[p]
        pu.t += pu.speed
        connFlash[pu.c] = Math.max(connFlash[pu.c], pu.bright * (1 - pu.t) * 0.85)

        if (pu.t >= 1.0) {
          const dest = pu.fwd ? connB[pu.c] : connA[pu.c]
          nodeFlash[dest] = Math.min(1, nodeFlash[dest] + pu.bright * 0.95)

          if (pu.cascades > 0) {
            const adj = nodeAdj[dest]
            const prob = tgt.cascadeProb
            for (const nc of adj) {
              if (nc === pu.c) continue
              if (Math.random() < prob) {
                const fwd2 = connA[nc] === dest
                spawnPulse(nc, fwd2, pu.bright * 0.68, pu.cascades - 1, pu.isThink)
              }
            }
          }
          pulses.splice(p, 1)
        }
      }

      // ── Write synapse dot positions ──────────────────────────────────
      const nPulses = pulses.length
      for (let p = 0; p < nPulses; p++) {
        const { c, t, bright, fwd, isThink: itk } = pulses[p]
        const iA = connA[c], iB = connB[c]
        const ai = iA * 3, bi = iB * 3
        const tt = fwd ? t : 1 - t
        const sp = p * 3
        synPos[sp]   = positions[ai]   + (positions[bi]   - positions[ai])   * tt
        synPos[sp+1] = positions[ai+1] + (positions[bi+1] - positions[ai+1]) * tt
        synPos[sp+2] = positions[ai+2] + (positions[bi+2] - positions[ai+2]) * tt
        synBright[p] = bright * (0.45 + t * 0.55)
        synThink[p]  = itk ? 1.0 : 0.0
      }
      synGeo.setDrawRange(0, nPulses)
      synPosAttr.needsUpdate = true
      synBrtAttr.needsUpdate = true
      synThkAttr.needsUpdate = true

      // ── Update + write thinking rings ────────────────────────────────
      let ringDrawn = 0
      for (let r = rings.length - 1; r >= 0; r--) {
        const rg = rings[r]
        rg.radius += rg.speed
        rg.alpha  -= 0.010

        if (rg.alpha <= 0) { rings.splice(r, 1); continue }

        // Write ring as line segments (pairs of adjacent points)
        const y    = Math.sin(simT * 0.3 + r * 1.2) * 10   // slight tilt per ring
        for (let s = 0; s < RING_SEGS; s++) {
          const a0 = (s       / RING_SEGS) * Math.PI * 2
          const a1 = ((s + 1) / RING_SEGS) * Math.PI * 2
          const base = (ringDrawn * RING_SEGS + s) * 2
          const pi0  = base * 3, pi1 = (base + 1) * 3
          const ai0  = base, ai1 = base + 1

          ringBuf[pi0]   = Math.cos(a0) * rg.radius
          ringBuf[pi0+1] = y
          ringBuf[pi0+2] = Math.sin(a0) * rg.radius
          ringBuf[pi1]   = Math.cos(a1) * rg.radius
          ringBuf[pi1+1] = y
          ringBuf[pi1+2] = Math.sin(a1) * rg.radius
          ringAlpBuf[ai0] = rg.alpha * lWarm
          ringAlpBuf[ai1] = rg.alpha * lWarm * 0.5
        }
        ringDrawn++
      }
      ringGeo.setDrawRange(0, ringDrawn * RING_SEGS * 2)
      ringPosA.needsUpdate = true
      ringAlpA.needsUpdate = true

      // ── Decay flashes ────────────────────────────────────────────────
      for (let c = 0; c < nConn; c++)  connFlash[c] *= tgt.connDecay
      for (let i = 0; i < N; i++)      nodeFlash[i] *= tgt.nodeDecay

      // ── Update node glow ─────────────────────────────────────────────
      for (let i = 0; i < N; i++) {
        const thinkBoost = think ? nodeFlash[i] * 0.4 : 0
        glows[i] = Math.min(1, baseGlow[i] + nodeFlash[i] + thinkBoost)
      }
      glowAttr.needsUpdate = true

      // ── Build axon lines ─────────────────────────────────────────────
      let drawn = 0
      for (let c = 0; c < nConn; c++) {
        if (connAng[c] > lConnAngle) continue
        const i  = connA[c], j = connB[c]
        const str  = 1 - connAng[c] / lConnAngle
        // During thinking, base alpha is higher (more connections visible)
        const baseAlpha = think ? str * 0.45 * lBright : str * 0.30 * lBright
        const alp   = Math.min(1, baseAlpha + connFlash[c] * 0.92 + pulse * 0.10)
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

      // ── Uniforms ─────────────────────────────────────────────────────
      const col = lColor.clone()
      ptMat.uniforms.uColor.value.copy(col)
      ptMat.uniforms.uBright.value = lBright * bloomRef.current * 0.85
      lineMat.uniforms.uColor.value.copy(col)
      synMat.uniforms.uColor.value.copy(col)
      synMat.uniforms.uWarm.value  = lWarm
      // Ring color — amber during thinking, matches color otherwise
      ringMat.uniforms.uColor.value.copy(new THREE.Color(1.0, 0.60, 0.15))
      ringMat.uniforms.uWarm.value = lWarm

      renderer.render(scene, camera)
    }

    animate()

    return () => {
      cancelAnimationFrame(rafId)
      ro.disconnect()
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      ptGeo.dispose();   ptMat.dispose()
      lineGeo.dispose(); lineMat.dispose()
      synGeo.dispose();  synMat.dispose()
      ringGeo.dispose(); ringMat.dispose()
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={mountRef} className="w-full h-full" />
}
