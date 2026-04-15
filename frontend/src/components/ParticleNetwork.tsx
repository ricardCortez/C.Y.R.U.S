// frontend/src/components/ParticleNetwork.tsx
//
// Visual: sphere-surface particle network — ethanplusai / JARVIS style.
// Particles sit ON the sphere shell (not volumetric).
// White/silver nodes connected by constellation lines.
// Slow auto-rotation + mouse tilt.

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'
import { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'

// ── Per-state parameters ──────────────────────────────────────────────────

interface StateParams {
  rotSpeed:  number   // Y rotation speed
  radius:    number   // sphere base radius
  connAngle: number   // max connection angle (radians)
  brightness:number   // overall brightness multiplier
  pulseAmt:  number   // audio-reactive pulse
  color:     [number, number, number]  // RGB 0-1
}

const STATE_PARAMS: Record<SystemState, StateParams> = {
  offline:      { rotSpeed: 0.0008, radius: 110, connAngle: 0.72, brightness: 0.45, pulseAmt: 0,    color: [0.55, 0.65, 0.75] },
  connected:    { rotSpeed: 0.0012, radius: 112, connAngle: 0.75, brightness: 0.60, pulseAmt: 0,    color: [0.75, 0.90, 1.00] },
  idle:         { rotSpeed: 0.0014, radius: 112, connAngle: 0.75, brightness: 0.65, pulseAmt: 0,    color: [0.80, 0.92, 1.00] },
  listening:    { rotSpeed: 0.0022, radius: 118, connAngle: 0.82, brightness: 0.82, pulseAmt: 0.20, color: [0.70, 0.95, 1.00] },
  transcribing: { rotSpeed: 0.0026, radius: 120, connAngle: 0.85, brightness: 0.88, pulseAmt: 0.25, color: [0.65, 0.92, 1.00] },
  thinking:     { rotSpeed: 0.0040, radius: 122, connAngle: 0.90, brightness: 1.00, pulseAmt: 0.35, color: [0.80, 0.88, 1.00] },
  speaking:     { rotSpeed: 0.0032, radius: 120, connAngle: 0.88, brightness: 0.95, pulseAmt: 0.55, color: [0.70, 0.95, 1.00] },
  error:        { rotSpeed: 0.0030, radius: 115, connAngle: 0.70, brightness: 0.80, pulseAmt: 0.20, color: [1.00, 0.35, 0.35] },
}

// ── GLSL shaders ──────────────────────────────────────────────────────────

const VERT = /* glsl */`
  attribute float aSize;
  attribute float aGlow;
  varying   float vGlow;
  varying   float vDepth;

  void main() {
    vGlow = aGlow;
    vec4 mv  = modelViewMatrix * vec4(position, 1.0);
    vDepth   = clamp((-mv.z - 60.0) / 280.0, 0.0, 1.0);
    float sz = aSize * (350.0 / -mv.z);
    gl_PointSize = sz * (1.0 + aGlow * 2.5);
    gl_Position  = projectionMatrix * mv;
  }
`

const FRAG = /* glsl */`
  uniform vec3  uColor;
  uniform float uBright;
  varying float vGlow;
  varying float vDepth;

  void main() {
    vec2  uv = gl_PointCoord - 0.5;
    float d  = length(uv);
    if (d > 0.5) discard;

    // Sharp core + soft halo
    float core = 1.0 - smoothstep(0.0, 0.18, d);
    float halo = 1.0 - smoothstep(0.0, 0.50, d);
    float a    = (core * 0.95 + halo * 0.30) * uBright * (0.35 + vDepth * 0.65);

    // Hub nodes glow warmer/brighter
    vec3 col = mix(uColor, vec3(1.0), vGlow * 0.55 + core * 0.25);

    gl_FragColor = vec4(col * (1.0 + vGlow * 0.8), a);
  }
`

// ── Component ─────────────────────────────────────────────────────────────

interface Props { analyser?: AudioAnalyserHandle }

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
    const camera   = new THREE.PerspectiveCamera(55, W / H, 0.1, 2000)
    camera.position.set(0, 0, 300)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(W, H)
    renderer.setClearColor(0x000000, 0)
    renderer.domElement.style.cssText = 'width:100%;height:100%;display:block;'
    mount.appendChild(renderer.domElement)

    // ── Sphere surface particles ───────────────────────────────────────
    const N        = countRef.current            // e.g. 200
    const BASE_R   = 110

    // Spherical coords stored for angular-distance connections
    const sTheta   = new Float32Array(N)         // polar   [0, π]
    const sPhi     = new Float32Array(N)         // azimuth [0, 2π]
    const positions = new Float32Array(N * 3)
    const sizes     = new Float32Array(N)
    const glows     = new Float32Array(N)        // 0=normal, 1=hub node

    for (let i = 0; i < N; i++) {
      // Uniform sphere surface distribution
      const theta = Math.acos(2 * Math.random() - 1)
      const phi   = Math.random() * Math.PI * 2
      // Slight radius jitter for organic feel
      const r     = BASE_R + (Math.random() - 0.5) * 8

      sTheta[i] = theta
      sPhi[i]   = phi

      positions[i*3]   = r * Math.sin(theta) * Math.cos(phi)
      positions[i*3+1] = r * Math.cos(theta)
      positions[i*3+2] = r * Math.sin(theta) * Math.sin(phi)

      // ~12% chance of being a hub node (larger, brighter)
      const isHub  = Math.random() < 0.12
      sizes[i]     = isHub ? 4.5 + Math.random() * 3.0 : 1.8 + Math.random() * 1.8
      glows[i]     = isHub ? 0.7 + Math.random() * 0.3 : 0.0
    }

    // ── Points mesh ───────────────────────────────────────────────────
    const ptGeo = new THREE.BufferGeometry()
    ptGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    ptGeo.setAttribute('aSize',    new THREE.BufferAttribute(sizes,     1))
    ptGeo.setAttribute('aGlow',    new THREE.BufferAttribute(glows,     1))

    const ptMat = new THREE.ShaderMaterial({
      vertexShader:   VERT,
      fragmentShader: FRAG,
      uniforms: {
        uColor:  { value: new THREE.Color(0.80, 0.92, 1.0) },
        uBright: { value: 0.65 },
      },
      transparent: true,
      blending:    THREE.AdditiveBlending,
      depthWrite:  false,
    })

    const points = new THREE.Points(ptGeo, ptMat)

    // ── Pre-compute connection index pairs ────────────────────────────
    // Only connect pairs within connAngle — computed once at startup
    // We store a "base" connectivity graph and filter dynamically by angle
    const MAX_CONN = N * 6
    const connA    = new Int32Array(MAX_CONN)
    const connB    = new Int32Array(MAX_CONN)
    let   nConn    = 0

    const BASE_ANGLE = 0.78  // ~45°
    for (let i = 0; i < N && nConn < MAX_CONN - 1; i++) {
      for (let j = i + 1; j < N && nConn < MAX_CONN - 1; j++) {
        // Angular distance via dot product of unit vectors
        const ax = Math.sin(sTheta[i]) * Math.cos(sPhi[i])
        const ay = Math.cos(sTheta[i])
        const az = Math.sin(sTheta[i]) * Math.sin(sPhi[i])
        const bx = Math.sin(sTheta[j]) * Math.cos(sPhi[j])
        const by = Math.cos(sTheta[j])
        const bz = Math.sin(sTheta[j]) * Math.sin(sPhi[j])
        const dot = Math.max(-1, Math.min(1, ax*bx + ay*by + az*bz))
        if (Math.acos(dot) < BASE_ANGLE) {
          connA[nConn] = i
          connB[nConn] = j
          nConn++
        }
      }
    }

    // ── Line geometry ─────────────────────────────────────────────────
    const linePositions = new Float32Array(nConn * 6)
    const lineAlphas    = new Float32Array(nConn * 2)

    const lineGeo     = new THREE.BufferGeometry()
    const linePosAttr = new THREE.BufferAttribute(linePositions, 3)
    const lineAlpAttr = new THREE.BufferAttribute(lineAlphas,    1)
    linePosAttr.setUsage(THREE.DynamicDrawUsage)
    lineAlpAttr.setUsage(THREE.DynamicDrawUsage)
    lineGeo.setAttribute('position', linePosAttr)
    lineGeo.setAttribute('alpha',    lineAlpAttr)

    // Line shader — uses per-vertex alpha attribute
    const lineVert = /* glsl */`
      attribute float alpha;
      varying   float vAlpha;
      void main() {
        vAlpha      = alpha;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `
    const lineFrag = /* glsl */`
      uniform vec3  uColor;
      varying float vAlpha;
      void main() {
        gl_FragColor = vec4(uColor, vAlpha);
      }
    `
    const lineMat = new THREE.ShaderMaterial({
      vertexShader:   lineVert,
      fragmentShader: lineFrag,
      uniforms: { uColor: { value: new THREE.Color(0.80, 0.92, 1.0) } },
      transparent: true,
      blending:    THREE.AdditiveBlending,
      depthWrite:  false,
    })

    const lineSegs = new THREE.LineSegments(lineGeo, lineMat)

    // ── Group (rotates together) ───────────────────────────────────────
    const group = new THREE.Group()
    group.add(points)
    group.add(lineSegs)
    scene.add(group)

    // ── Mouse ──────────────────────────────────────────────────────────
    const mouse = { tx: 0, ty: 0, x: 0, y: 0 }
    const onMouse = (e: MouseEvent) => {
      mouse.tx = (e.clientX / window.innerWidth  - 0.5) * 2
      mouse.ty = (e.clientY / window.innerHeight - 0.5) * 2
    }
    window.addEventListener('mousemove', onMouse)

    // ── Resize ────────────────────────────────────────────────────────
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
    let lBright    = 0.65
    let lPulse     = 0.0
    let lRadius    = BASE_R
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
      const spd   = speedRef.current

      // Lerp params
      lRotSpeed  = lerp(lRotSpeed,  tgt.rotSpeed * spd, 0.03)
      lConnAngle = lerp(lConnAngle, tgt.connAngle,      0.025)
      lBright    = lerp(lBright,    tgt.brightness,     0.03)
      lPulse     = lerp(lPulse,     tgt.pulseAmt,       0.04)
      lRadius    = lerp(lRadius,    tgt.radius,         0.02)
      lColor.lerp(new THREE.Color(...tgt.color), 0.04)

      // Mouse smooth
      mouse.x = lerp(mouse.x, mouse.tx, 0.06)
      mouse.y = lerp(mouse.y, mouse.ty, 0.06)

      // Audio
      if (analyserRef.current && (state === 'speaking' || state === 'listening')) {
        audioAmp = lerp(audioAmp, analyserRef.current.getBass(), 0.15)
      } else if (state === 'speaking') {
        audioAmp = lerp(audioAmp, 0.3 + 0.5 * Math.abs(Math.sin(simT * 4.2)), 0.08)
      } else {
        audioAmp = lerp(audioAmp, 0, 0.06)
      }

      const pulse  = lPulse * audioAmp
      const curR   = lRadius + pulse * 18

      // Rotate group
      rotY += lRotSpeed
      group.rotation.y = rotY + mouse.x * 0.35
      group.rotation.x = Math.sin(simT * 0.15) * 0.06 - mouse.y * 0.18

      // Expand/contract sphere radius
      for (let i = 0; i < N; i++) {
        const ix = i * 3
        const r  = curR + (Math.random() < 0.004 ? (Math.random() - 0.5) * 4 : 0)
        const nx = Math.sin(sTheta[i]) * Math.cos(sPhi[i])
        const ny = Math.cos(sTheta[i])
        const nz = Math.sin(sTheta[i]) * Math.sin(sPhi[i])
        positions[ix]   = nx * r
        positions[ix+1] = ny * r
        positions[ix+2] = nz * r
      }

      // Update connections
      let drawn = 0
      for (let c = 0; c < nConn; c++) {
        const i = connA[c], j = connB[c]
        // Angular distance dot product
        const ax = Math.sin(sTheta[i]) * Math.cos(sPhi[i])
        const ay = Math.cos(sTheta[i])
        const az = Math.sin(sTheta[i]) * Math.sin(sPhi[i])
        const bx = Math.sin(sTheta[j]) * Math.cos(sPhi[j])
        const by = Math.cos(sTheta[j])
        const bz = Math.sin(sTheta[j]) * Math.sin(sPhi[j])
        const dot  = Math.max(-1, Math.min(1, ax*bx + ay*by + az*bz))
        const ang  = Math.acos(dot)
        if (ang > lConnAngle) continue

        const str  = 1 - ang / lConnAngle
        const alp  = str * 0.55 * lBright + pulse * 0.15
        const ix = i * 3, jx = j * 3
        const li = drawn * 6

        linePositions[li]   = positions[ix];   linePositions[li+1] = positions[ix+1]; linePositions[li+2] = positions[ix+2]
        linePositions[li+3] = positions[jx];   linePositions[li+4] = positions[jx+1]; linePositions[li+5] = positions[jx+2]
        lineAlphas[drawn*2]   = alp
        lineAlphas[drawn*2+1] = alp * 0.6
        drawn++
      }

      lineGeo.setDrawRange(0, drawn * 2)
      linePosAttr.needsUpdate = true
      lineAlpAttr.needsUpdate = true

      ptGeo.getAttribute('position').needsUpdate = true

      // Shader uniforms
      ptMat.uniforms.uColor.value.copy(lColor)
      ptMat.uniforms.uBright.value = lBright * bloomRef.current * 0.7
      lineMat.uniforms.uColor.value.copy(lColor)

      renderer.render(scene, camera)
    }

    animate()

    return () => {
      cancelAnimationFrame(rafId)
      ro.disconnect()
      window.removeEventListener('mousemove', onMouse)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      ptGeo.dispose()
      ptMat.dispose()
      lineGeo.dispose()
      lineMat.dispose()
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={mountRef} className="w-full h-full" />
}
