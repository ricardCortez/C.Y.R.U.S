// frontend/src/components/ParticleNetwork.tsx
//
// C.Y.R.U.S — Neural Network Visualizer v2
// 3-layer volumetric geometry (cortex / gray matter / nucleus)
// 3 connection types (local / hemispheric / long axon)
// WebGL shaders with volumetric glow and per-connection pulse positions
// 5 visual presets with smooth LERP transitions
// Dramatic per-state behaviors

import { useEffect, useRef }                        from 'react'
import * as THREE                                    from 'three'
import { useCYRUSStore, SystemState }                from '../store/useCYRUSStore'
import { PRESETS, PresetConfig, VisualPresetId }     from '../types/presets'

// ── Constants ─────────────────────────────────────────────────────────────────

const TOTAL_NODES       = 400
const MAX_PULSES        = 200
const LERP_FRAMES       = 60
const TARGET_CONNECTIONS = 1800

const LAYERS = [
  { fraction: 0.40, radius: 100 },  // cortex
  { fraction: 0.35, radius: 72  },  // gray matter
  { fraction: 0.25, radius: 45  },  // nucleus
]

const CONN_LOCAL_FRAC = 0.80
const CONN_HEMI_FRAC  = 0.15
// axon = remaining 0.05

// ── Per-state parameters ──────────────────────────────────────────────────────

interface StateParams {
  rotSpeed:    number
  brightness:  number
  spawnRate:   number
  cascadeMode: 'nucleus' | 'cortex' | 'radial' | 'random' | 'erratic'
}

const STATE_PARAMS: Record<SystemState, StateParams> = {
  offline:      { rotSpeed: 0.0006, brightness: 0.40, spawnRate: 0.003, cascadeMode: 'random'   },
  connected:    { rotSpeed: 0.0010, brightness: 0.60, spawnRate: 0.008, cascadeMode: 'random'   },
  idle:         { rotSpeed: 0.0012, brightness: 0.65, spawnRate: 0.020, cascadeMode: 'nucleus'  },
  listening:    { rotSpeed: 0.0022, brightness: 1.10, spawnRate: 0.060, cascadeMode: 'cortex'   },
  transcribing: { rotSpeed: 0.0028, brightness: 1.15, spawnRate: 0.070, cascadeMode: 'cortex'   },
  thinking:     { rotSpeed: 0.0048, brightness: 1.40, spawnRate: 0.130, cascadeMode: 'nucleus'  },
  speaking:     { rotSpeed: 0.0032, brightness: 1.25, spawnRate: 0.090, cascadeMode: 'radial'   },
  error:        { rotSpeed: 0.0030, brightness: 1.00, spawnRate: 0.030, cascadeMode: 'erratic'  },
}

// ── GLSL — Nodes ──────────────────────────────────────────────────────────────

const NODE_VERT = /* glsl */`
  attribute float aSize;
  attribute float aGlow;
  attribute float aLayer;
  varying   float vGlow;
  varying   float vDepth;
  varying   float vLayer;
  void main() {
    vGlow  = aGlow;
    vLayer = aLayer;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth  = clamp((-mv.z - 30.0) / 320.0, 0.0, 1.0);
    float depthFade = 1.0 - vDepth * 0.6;
    gl_PointSize = aSize * (380.0 / -mv.z) * (1.0 + aGlow * 2.5) * depthFade;
    gl_Position  = projectionMatrix * mv;
  }
`

const NODE_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform vec3  uNucleusColor;
  uniform float uBright;
  varying float vGlow;
  varying float vDepth;
  varying float vLayer;
  void main() {
    vec2  uv   = gl_PointCoord - 0.5;
    float d    = length(uv);
    if (d > 0.5) discard;
    float core  = 1.0 - smoothstep(0.0, 0.18, d);
    float halo  = (1.0 - smoothstep(0.15, 0.50, d)) * 0.5;
    float shape = core + halo * (0.5 + vGlow);
    float depthFade = 1.0 - vDepth * 0.55;
    float alpha = shape * uBright * (0.6 + vGlow * 1.4) * depthFade;
    vec3  col = mix(uColor, uNucleusColor, step(1.5, vLayer));
    gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
  }
`

// ── GLSL — Connections ────────────────────────────────────────────────────────

const EDGE_VERT = /* glsl */`
  attribute float aT;
  attribute float aConnType;
  attribute float aBaseAlpha;
  attribute float aPulsePos;
  varying   float vT;
  varying   float vConnType;
  varying   float vBaseAlpha;
  varying   float vPulsePos;
  varying   float vDepth;
  void main() {
    vT = aT; vConnType = aConnType; vBaseAlpha = aBaseAlpha; vPulsePos = aPulsePos;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vDepth = clamp((-mv.z - 30.0) / 320.0, 0.0, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`

const EDGE_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform vec3  uPulseColor;
  uniform float uBright;
  uniform float uPulseWidth;
  varying float vT;
  varying float vConnType;
  varying float vBaseAlpha;
  varying float vPulsePos;
  varying float vDepth;
  void main() {
    float depthFade = 1.0 - vDepth * 0.60;
    float pulse = 0.0;
    if (vPulsePos >= 0.0) {
      float dist = abs(vT - vPulsePos);
      pulse = smoothstep(uPulseWidth, 0.0, dist);
    }
    float typeBoost = (vConnType > 0.5) ? 1.35 : 1.0;
    float alpha = (vBaseAlpha + pulse * 0.65) * uBright * depthFade * typeBoost;
    vec3  col   = mix(uColor, uPulseColor, pulse * 0.8);
    gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0));
  }
`

// ── GLSL — Grid overlay ───────────────────────────────────────────────────────

const GRID_VERT = /* glsl */`
  void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`
const GRID_FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uAlpha;
  void main() { gl_FragColor = vec4(uColor, uAlpha * 0.12); }
`

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodeData {
  x: number; y: number; z: number
  layer: number
  hemisphere: number
}

interface ConnectionData {
  a: number; b: number
  type: number
  baseAlpha: number
}

interface Pulse {
  connIdx: number
  t:       number
  speed:   number
  active:  boolean
}

// ── Geometry builders ─────────────────────────────────────────────────────────

function buildNodes(): NodeData[] {
  const nodes: NodeData[] = []
  const goldenAngle = Math.PI * (1 + Math.sqrt(5))
  for (const [li, layer] of LAYERS.entries()) {
    const count = Math.floor(TOTAL_NODES * layer.fraction)
    for (let i = 0; i < count; i++) {
      const theta  = Math.acos(1 - 2 * (i + 0.5) / count)
      const phi    = goldenAngle * (i + 0.5)
      const jitter = 1 + (Math.random() - 0.5) * 0.16
      const r      = layer.radius * jitter
      const x = Math.sin(theta) * Math.cos(phi) * r
      const y = Math.cos(theta) * r
      const z = Math.sin(theta) * Math.sin(phi) * r
      nodes.push({ x, y, z, layer: li, hemisphere: x >= 0 ? 0 : 1 })
    }
  }
  return nodes
}

function buildConnections(nodes: NodeData[]): ConnectionData[] {
  const N    = nodes.length
  const conns: ConnectionData[] = []
  const localTarget = Math.floor(TARGET_CONNECTIONS * CONN_LOCAL_FRAC)
  const hemiTarget  = Math.floor(TARGET_CONNECTIONS * CONN_HEMI_FRAC)
  const axonTarget  = TARGET_CONNECTIONS - localTarget - hemiTarget

  const dist2 = (a: NodeData, b: NodeData) =>
    (a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2

  let attempts = 0
  while (conns.length < localTarget && attempts++ < localTarget * 8) {
    const a = Math.floor(Math.random() * N)
    const b = Math.floor(Math.random() * N)
    if (a === b || nodes[a].layer !== nodes[b].layer) continue
    if (dist2(nodes[a], nodes[b]) > 50 * 50) continue
    conns.push({ a, b, type: 0, baseAlpha: 0.30 + Math.random() * 0.15 })
  }

  const hStart = conns.length
  attempts = 0
  while (conns.length - hStart < hemiTarget && attempts++ < hemiTarget * 8) {
    const a = Math.floor(Math.random() * N)
    const b = Math.floor(Math.random() * N)
    if (a === b || nodes[a].hemisphere === nodes[b].hemisphere) continue
    if (Math.abs(nodes[a].layer - nodes[b].layer) > 1) continue
    conns.push({ a, b, type: 1, baseAlpha: 0.45 + Math.random() * 0.20 })
  }

  const aStart = conns.length
  attempts = 0
  while (conns.length - aStart < axonTarget && attempts++ < axonTarget * 8) {
    const a = Math.floor(Math.random() * N)
    const b = Math.floor(Math.random() * N)
    if (a === b || Math.abs(nodes[a].layer - nodes[b].layer) < 2) continue
    conns.push({ a, b, type: 2, baseAlpha: 0.18 + Math.random() * 0.10 })
  }

  return conns
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ParticleNetwork() {
  const mountRef     = useRef<HTMLDivElement>(null)
  const systemState  = useCYRUSStore(s => s.systemState)
  const bloomIntensity = useCYRUSStore(s => s.bloomIntensity)
  const visualPreset = useCYRUSStore(s => s.visualPreset)

  const stateRef  = useRef(systemState)
  const bloomRef  = useRef(bloomIntensity)
  const presetRef = useRef<VisualPresetId>(visualPreset)

  useEffect(() => { stateRef.current  = systemState    }, [systemState])
  useEffect(() => { bloomRef.current  = bloomIntensity }, [bloomIntensity])
  useEffect(() => { presetRef.current = visualPreset   }, [visualPreset])

  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    const W = mount.clientWidth  || window.innerWidth
    const H = mount.clientHeight || window.innerHeight

    const scene    = new THREE.Scene()
    const camera   = new THREE.PerspectiveCamera(60, W / H, 0.1, 2000)
    camera.position.set(0, 0, 280)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;'
    mount.appendChild(renderer.domElement)

    // ── Geometry ───────────────────────────────────────────────────────────
    const nodeData = buildNodes()
    const connData = buildConnections(nodeData)
    const N = nodeData.length
    const C = connData.length

    // ── Node buffers ───────────────────────────────────────────────────────
    const positions = new Float32Array(N * 3)
    const sizes     = new Float32Array(N)
    const glows     = new Float32Array(N)
    const baseGlow  = new Float32Array(N)
    const nodeLayer = new Float32Array(N)
    const nodeFlash = new Float32Array(N)

    for (let i = 0; i < N; i++) {
      const nd = nodeData[i]
      positions[i*3]   = nd.x
      positions[i*3+1] = nd.y
      positions[i*3+2] = nd.z
      nodeLayer[i] = nd.layer
      const isHub     = Math.random() < (nd.layer === 2 ? 0.30 : 0.12)
      const layerSize = nd.layer === 2 ? 1.6 : nd.layer === 1 ? 1.2 : 1.0
      sizes[i]    = (isHub ? 7.0 + Math.random() * 4.0 : 2.5 + Math.random() * 2.5) * layerSize
      baseGlow[i] = isHub ? 0.7 + Math.random() * 0.3 : 0.05
      glows[i]    = baseGlow[i]
    }

    const ptGeo = new THREE.BufferGeometry()
    ptGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const sizeAttr = new THREE.BufferAttribute(sizes, 1); sizeAttr.setUsage(THREE.DynamicDrawUsage)
    const glowAttr = new THREE.BufferAttribute(glows, 1); glowAttr.setUsage(THREE.DynamicDrawUsage)
    ptGeo.setAttribute('aSize',  sizeAttr)
    ptGeo.setAttribute('aGlow',  glowAttr)
    ptGeo.setAttribute('aLayer', new THREE.BufferAttribute(nodeLayer, 1))

    const ptMat = new THREE.ShaderMaterial({
      vertexShader: NODE_VERT, fragmentShader: NODE_FRAG,
      uniforms: {
        uColor:        { value: new THREE.Color(0.75, 0.90, 1.0) },
        uNucleusColor: { value: new THREE.Color(0.50, 0.80, 1.0) },
        uBright:       { value: 0.9 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const points = new THREE.Points(ptGeo, ptMat)
    scene.add(points)

    // ── Connection buffers ─────────────────────────────────────────────────
    const edgePositions = new Float32Array(C * 2 * 3)
    const edgeT         = new Float32Array(C * 2)
    const edgeType      = new Float32Array(C * 2)
    const edgeAlpha     = new Float32Array(C * 2)
    const pulsePosArr   = new Float32Array(C * 2).fill(-1.0)

    for (let ci = 0; ci < C; ci++) {
      const { a, b, type, baseAlpha } = connData[ci]
      const na = nodeData[a], nb = nodeData[b]
      const vi = ci * 6
      edgePositions[vi]   = na.x; edgePositions[vi+1] = na.y; edgePositions[vi+2] = na.z
      edgePositions[vi+3] = nb.x; edgePositions[vi+4] = nb.y; edgePositions[vi+5] = nb.z
      edgeT[ci*2] = 0.0; edgeT[ci*2+1] = 1.0
      edgeType[ci*2]  = type;      edgeType[ci*2+1]  = type
      edgeAlpha[ci*2] = baseAlpha; edgeAlpha[ci*2+1] = baseAlpha
    }

    const edgeGeo = new THREE.BufferGeometry()
    edgeGeo.setAttribute('position',   new THREE.BufferAttribute(edgePositions, 3))
    edgeGeo.setAttribute('aT',         new THREE.BufferAttribute(edgeT, 1))
    edgeGeo.setAttribute('aConnType',  new THREE.BufferAttribute(edgeType, 1))
    edgeGeo.setAttribute('aBaseAlpha', new THREE.BufferAttribute(edgeAlpha, 1))
    const pulsePosBuffer = new THREE.BufferAttribute(pulsePosArr, 1)
    pulsePosBuffer.setUsage(THREE.DynamicDrawUsage)
    edgeGeo.setAttribute('aPulsePos', pulsePosBuffer)

    const edgeMat = new THREE.ShaderMaterial({
      vertexShader: EDGE_VERT, fragmentShader: EDGE_FRAG,
      uniforms: {
        uColor:      { value: new THREE.Color(0.30, 0.70, 1.0) },
        uPulseColor: { value: new THREE.Color(0.00, 1.00, 0.85) },
        uBright:     { value: 0.85 },
        uPulseWidth: { value: 0.08 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const lines = new THREE.LineSegments(edgeGeo, edgeMat)
    scene.add(lines)

    // ── Grid overlay ───────────────────────────────────────────────────────
    const gridSize = 220, gridStep = 22
    const gridPoints: number[] = []
    for (let x = -gridSize; x <= gridSize; x += gridStep)
      gridPoints.push(x, -gridSize, -60, x, gridSize, -60)
    for (let y = -gridSize; y <= gridSize; y += gridStep)
      gridPoints.push(-gridSize, y, -60, gridSize, y, -60)
    const gridGeo = new THREE.BufferGeometry()
    gridGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(gridPoints), 3))
    const gridMat = new THREE.ShaderMaterial({
      vertexShader: GRID_VERT, fragmentShader: GRID_FRAG,
      uniforms: {
        uColor: { value: new THREE.Color(0.20, 1.00, 0.60) },
        uAlpha: { value: 0.0 },
      },
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const gridLines = new THREE.LineSegments(gridGeo, gridMat)
    scene.add(gridLines)

    // ── Pulse state ────────────────────────────────────────────────────────
    const pulses: Pulse[] = Array.from({ length: MAX_PULSES }, () => ({
      connIdx: 0, t: 0, speed: 0, active: false,
    }))
    const connToPulseT = new Float32Array(C).fill(-1.0)

    function spawnPulse(state: SystemState, preset: PresetConfig): void {
      const p = pulses.find(p => !p.active)
      if (!p) return
      const sp = STATE_PARAMS[state]
      let ci: number
      if (sp.cascadeMode === 'nucleus') {
        const cands = connData.map((c, i) => ({ c, i }))
          .filter(({ c }) => nodeData[c.a].layer === 2 || nodeData[c.b].layer === 2)
        ci = cands.length ? cands[Math.floor(Math.random() * cands.length)].i : Math.floor(Math.random() * C)
      } else if (sp.cascadeMode === 'cortex') {
        const cands = connData.map((c, i) => ({ c, i }))
          .filter(({ c }) => nodeData[c.a].layer === 0 || nodeData[c.b].layer === 0)
        ci = cands.length ? cands[Math.floor(Math.random() * cands.length)].i : Math.floor(Math.random() * C)
      } else {
        ci = Math.floor(Math.random() * C)
      }
      p.connIdx = ci
      p.t       = 0
      p.speed   = (0.008 + Math.random() * 0.012) * preset.pulseDensity
      p.active  = true
    }

    // ── Preset lerp ────────────────────────────────────────────────────────
    let currentPalette = { ...PRESETS['neural'].palette }
    let targetPresetId = presetRef.current
    let lerpT = 1.0

    function lerp3(a: [number,number,number], b: [number,number,number], t: number): [number,number,number] {
      return [a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t]
    }

    // ── Animation loop ─────────────────────────────────────────────────────
    let rafId = 0

    function animate(): void {
      rafId = requestAnimationFrame(animate)

      const state = stateRef.current
      const sp    = STATE_PARAMS[state]
      const bloom = bloomRef.current
      const pid   = presetRef.current

      if (pid !== targetPresetId) { targetPresetId = pid; lerpT = 0.0 }
      if (lerpT < 1.0) lerpT = Math.min(1.0, lerpT + 1.0 / LERP_FRAMES)
      const preset = PRESETS[targetPresetId]

      const nodePal  = lerp3(currentPalette.node,       preset.palette.node,       lerpT)
      const connPal  = lerp3(currentPalette.connection, preset.palette.connection, lerpT)
      const pulsePal = lerp3(currentPalette.pulse,      preset.palette.pulse,      lerpT)
      const nuclPal  = lerp3(currentPalette.nucleus,    preset.palette.nucleus,    lerpT)
      if (lerpT >= 1.0) currentPalette = { ...preset.palette }

      const bright = sp.brightness * bloom * preset.glowIntensity
      ptMat.uniforms.uColor.value.setRGB(...nodePal)
      ptMat.uniforms.uNucleusColor.value.setRGB(...nuclPal)
      ptMat.uniforms.uBright.value = bright
      edgeMat.uniforms.uColor.value.setRGB(...connPal)
      edgeMat.uniforms.uPulseColor.value.setRGB(...pulsePal)
      edgeMat.uniforms.uBright.value = bright
      gridMat.uniforms.uColor.value.setRGB(...connPal)
      gridMat.uniforms.uAlpha.value = preset.gridOverlay ? 1.0 : 0.0

      const rotSpeed = sp.rotSpeed * preset.rotSpeedMult
      points.rotation.y    += rotSpeed
      lines.rotation.y     += rotSpeed
      gridLines.rotation.y  = points.rotation.y * 0.15

      if (Math.random() < sp.spawnRate * preset.pulseDensity) spawnPulse(state, preset)
      if (state === 'idle' && Math.random() < 0.008) spawnPulse('idle', preset)

      connToPulseT.fill(-1.0)
      const glowArr = glowAttr.array as Float32Array
      for (let i = 0; i < N; i++) {
        nodeFlash[i] = Math.max(0, nodeFlash[i] - 0.03)
        glowArr[i]   = baseGlow[i] + nodeFlash[i]
      }

      for (const p of pulses) {
        if (!p.active) continue
        p.t += p.speed
        if (p.t > 1.0) {
          nodeFlash[connData[p.connIdx].b] = Math.min(1.5, nodeFlash[connData[p.connIdx].b] + 0.8)
          p.active = false
          connToPulseT[p.connIdx] = -1.0
          continue
        }
        connToPulseT[p.connIdx] = p.t
      }

      const pArr = pulsePosBuffer.array as Float32Array
      for (let ci = 0; ci < C; ci++) {
        pArr[ci*2]   = connToPulseT[ci]
        pArr[ci*2+1] = connToPulseT[ci]
      }
      pulsePosBuffer.needsUpdate = true
      glowAttr.needsUpdate = true

      renderer.render(scene, camera)
    }

    animate()

    const onResize = () => {
      const w = mount.clientWidth || window.innerWidth
      const h = mount.clientHeight || window.innerHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      mount.removeChild(renderer.domElement)
    }
  }, [])

  return <div ref={mountRef} style={{ width: '100%', height: '100%' }} />
}
