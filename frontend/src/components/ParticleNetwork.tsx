// frontend/src/components/ParticleNetwork.tsx
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'
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
  const mountRef      = useRef<HTMLDivElement>(null)
  const systemState   = useCYRUSStore((s) => s.systemState)
  const particleCount = useCYRUSStore((s) => s.particleCount)
  const bloomIntensity = useCYRUSStore((s) => s.bloomIntensity)
  const orbSpeed      = useCYRUSStore((s) => s.orbSpeed)

  // Store refs so the render loop always reads latest values
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
    const positions  = new Float32Array(N * 3)
    const velocities = new Float32Array(N * 3)
    const phases     = new Float32Array(N)
    const sizes      = new Float32Array(N)
    const fireAmts   = new Float32Array(N)
    const fireCools  = new Float32Array(N)

    // Organic cloud — Gaussian via Box-Muller, NOT perfect sphere
    for (let i = 0; i < N; i++) {
      const u1  = Math.random(), u2 = Math.random()
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
    const MAX_LINES   = N * 4
    const linePositions = new Float32Array(MAX_LINES * 6)
    const lineColors    = new Float32Array(MAX_LINES * 6)

    const lineGeo     = new THREE.BufferGeometry()
    const linePosAttr = new THREE.BufferAttribute(linePositions, 3)
    const lineColAttr = new THREE.BufferAttribute(lineColors,    3)
    linePosAttr.setUsage(THREE.DynamicDrawUsage)
    lineColAttr.setUsage(THREE.DynamicDrawUsage)
    lineGeo.setAttribute('position', linePosAttr)
    lineGeo.setAttribute('color',    lineColAttr)

    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent:  true,
      blending:     THREE.AdditiveBlending,
      depthWrite:   false,
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

      const state = stateRef.current
      const tgt   = STATE_PARAMS[state]
      const spd   = speedRef.current
      const bloom = bloomRef.current

      // Lerp state params
      lSpeed    = lerpN(lSpeed,    tgt.speed    * spd, 0.03)
      lConnFrac = lerpN(lConnFrac, tgt.connFrac,       0.03)
      lCoreGlow = lerpN(lCoreGlow, tgt.coreGlow,       0.03)
      lFireRate = lerpN(lFireRate, tgt.fireRate,        0.06)
      lPulse    = lerpN(lPulse,    tgt.pulseAmt,        0.04)
      lColor.lerp(new THREE.Color(...tgt.color), 0.04)

      // Mouse parallax
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
        if (state === 'speaking') {
          audioAmp = lerpN(audioAmp, 0.28 + 0.72 * Math.abs(Math.sin(simT * 4.2) * Math.cos(simT * 2.5)), 0.08)
        } else if (state === 'listening') {
          audioAmp = lerpN(audioAmp, 0.05 + 0.12 * Math.abs(Math.sin(simT * 6)), 0.08)
        } else {
          audioAmp = lerpN(audioAmp, 0, 0.05)
        }
      }

      const react   = lPulse * (state === 'speaking' ? audioAmp : 1.0)
      const CONN_DIST = 72 + react * 20

      // ── Update particles ───────────────────────────────────────────────
      for (let i = 0; i < N; i++) {
        const ix = i * 3, iy = ix + 1, iz = ix + 2
        const ph = phases[i]

        velocities[ix] = lerpN(velocities[ix], Math.sin(simT * lSpeed + ph) * 0.40,               0.07)
        velocities[iy] = lerpN(velocities[iy], Math.cos(simT * lSpeed * 0.74 + ph * 1.3) * 0.40,  0.07)
        velocities[iz] = lerpN(velocities[iz], Math.sin(simT * lSpeed * 0.53 + ph * 0.87) * 0.40, 0.07)

        positions[ix] += velocities[ix]
        positions[iy] += velocities[iy]
        positions[iz] += velocities[iz]

        // Audio bass push (radial)
        if (audioAmp > 0.15) {
          const d = Math.sqrt(positions[ix]**2 + positions[iy]**2 + positions[iz]**2)
          if (d > 0) {
            const push = audioAmp * 1.2
            positions[ix] += (positions[ix] / d) * push
            positions[iy] += (positions[iy] / d) * push
            positions[iz] += (positions[iz] / d) * push
          }
        }

        // Soft boundary
        const d = Math.sqrt(positions[ix]**2 + positions[iy]**2 + positions[iz]**2)
        const maxR = 130 + react * 18
        if (d > maxR && d > 0) {
          const f = (maxR / d - 1) * 0.012
          positions[ix] += positions[ix] * f
          positions[iy] += positions[iy] * f
          positions[iz] += positions[iz] * f
        }

        // Neuron lifecycle
        if (fireAmts[i] > 0) fireAmts[i] = Math.max(0, fireAmts[i] - 0.022)
        if (fireCools[i] > 0) fireCools[i]--
        if (lFireRate > 0 && Math.random() < lFireRate && fireCools[i] === 0) {
          fireNeuron(i, 0.7 + Math.random() * 0.3)
        }
      }

      // ── Build connection segments ────────────────────────────────────
      let lineIdx = 0
      const cdSq  = CONN_DIST * CONN_DIST
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

          const str      = 1 - Math.sqrt(dSq) / CONN_DIST
          const avgFire  = (fireAmts[i] + fireAmts[j]) * 0.5

          // Cascade neuron activation
          if (fireAmts[i] > 0.3 && fireCools[j] === 0 && Math.random() < 0.09) fireNeuron(j, fireAmts[i] * 0.55)
          if (fireAmts[j] > 0.3 && fireCools[i] === 0 && Math.random() < 0.09) fireNeuron(i, fireAmts[j] * 0.55)

          const alpha = (str * 0.55 + avgFire * 0.5 + react * 0.08) * lCoreGlow
          const fr    = Math.min(1, cr + avgFire * 0.55)
          const fg    = Math.min(1, cg + avgFire * 0.38)
          const fbC   = Math.min(1, cb + avgFire * 0.22)

          const li = lineIdx * 6
          linePositions[li]   = positions[ix]; linePositions[li+1] = positions[iy]; linePositions[li+2] = positions[iz]
          lineColors[li]      = fr * alpha;    lineColors[li+1]    = fg * alpha;    lineColors[li+2]    = fbC * alpha
          linePositions[li+3] = positions[jx]; linePositions[li+4] = positions[jy]; linePositions[li+5] = positions[jz]
          lineColors[li+3]    = fr * alpha;    lineColors[li+4]    = fg * alpha;    lineColors[li+5]    = fbC * alpha

          lineIdx++

          // Electrons on strong active connections
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

      // Update electrons
      for (let e = electrons.length - 1; e >= 0; e--) {
        electrons[e].t += electrons[e].spd
        if (electrons[e].t >= 1) electrons.splice(e, 1)
      }

      // Update shader uniforms
      ptMat.uniforms.uColor.value.copy(lColor)
      ptMat.uniforms.uBloom.value = bloom

      // Update particle attributes
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
