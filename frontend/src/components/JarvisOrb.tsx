/**
 * JARVIS — JarvisOrb
 *
 * Faithful port of the JARVIS orb.ts to React + JARVIS state system.
 *
 * Visual model:
 *   2000 particles distributed inside a sphere volume (not surface).
 *   Each particle drifts with low-frequency noise velocity, pulled back
 *   toward a radius target.  Nearby particles connect with line segments
 *   whose opacity scales with lineAmount (state-driven).
 *   During "thinking", slow electrons travel along connections.
 *   On state change a tumble impulse spins the whole cloud.
 *   The camera drifts sinusoidally; the cloud breathes in Z.
 */

import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { useJARVISStore, SystemState } from '../store/useJARVISStore'
import type { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'

// ── JARVIS state → Jarvis orb state ────────────────────────────────────────

type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking'

function toOrbState(s: SystemState): OrbState {
  switch (s) {
    case 'listening':
    case 'transcribing': return 'listening'
    case 'thinking':     return 'thinking'
    case 'speaking':     return 'speaking'
    default:             return 'idle'
  }
}

// ── State target colors (hex) ─────────────────────────────────────────────

const STATE_COLOR: Record<OrbState, number> = {
  idle:      0x4ca8e8,   // original Jarvis blue
  listening: 0x4ceba8,   // JARVIS green-tinted
  thinking:  0x6ec4ff,   // Jarvis bright blue
  speaking:  0x5ab8f0,   // Jarvis cyan
}

// ── Component ─────────────────────────────────────────────────────────────

interface Props { analyser?: AudioAnalyserHandle }

export function JarvisOrb({ analyser }: Props) {
  const canvasRef   = useRef<HTMLCanvasElement>(null)
  const systemState = useJARVISStore(s => s.systemState)

  // Stable refs for the animation loop (avoids restart on every render)
  const stateRef    = useRef<OrbState>('idle')
  const analyserRef = useRef<AudioAnalyserHandle | undefined>(analyser)

  useEffect(() => { stateRef.current = toOrbState(systemState) }, [systemState])
  useEffect(() => { analyserRef.current = analyser }, [analyser])

  // ── One-time Three.js setup ──────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let destroyed = false
    const N = 2000

    // Renderer
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(canvas.clientWidth || window.innerWidth, canvas.clientHeight || window.innerHeight)
    renderer.setClearColor(0x050508, 1)

    const scene  = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(
      45,
      (canvas.clientWidth || window.innerWidth) / (canvas.clientHeight || window.innerHeight),
      1, 1000,
    )
    camera.position.z = 80

    // ── Particle geometry ────────────────────────────────────────────────
    const geo   = new THREE.BufferGeometry()
    const pos   = new Float32Array(N * 3)
    const vel   = new Float32Array(N * 3)
    const phase = new Float32Array(N)

    for (let i = 0; i < N; i++) {
      const theta = Math.random() * Math.PI * 2
      const phi   = Math.acos(2 * Math.random() - 1)
      const r     = Math.pow(Math.random(), 0.5) * 25
      pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
      pos[i * 3 + 2] = r * Math.cos(phi)
      phase[i] = Math.random() * 1000
    }

    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))

    const mat = new THREE.PointsMaterial({
      color: 0x4ca8e8, size: 0.4, transparent: true, opacity: 0.6,
      sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const points = new THREE.Points(geo, mat)
    scene.add(points)

    // ── Connection lines ─────────────────────────────────────────────────
    const MAX_LINES = 8000
    const linePos   = new Float32Array(MAX_LINES * 6)
    const lineGeo   = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3))
    lineGeo.setDrawRange(0, 0)

    const lineMat = new THREE.LineBasicMaterial({
      color: 0x4ca8e8, transparent: true, opacity: 0.0,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const lines = new THREE.LineSegments(lineGeo, lineMat)
    scene.add(lines)

    // ── Electrons (travel along connections during thinking) ─────────────
    const MAX_ELECTRONS = 200
    const electronGeo   = new THREE.BufferGeometry()
    const electronPos   = new Float32Array(MAX_ELECTRONS * 3)
    electronGeo.setAttribute('position', new THREE.BufferAttribute(electronPos, 3))
    electronGeo.setDrawRange(0, 0)

    const electronMat = new THREE.PointsMaterial({
      color: 0xffffff, size: 0.8, transparent: true, opacity: 1.0,
      sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const electrons = new THREE.Points(electronGeo, electronMat)
    scene.add(electrons)

    interface Electron {
      sx: number; sy: number; sz: number
      ex: number; ey: number; ez: number
      t: number; speed: number
    }
    const activeElectrons: Electron[] = []
    let electronSpawnRate   = 0
    let targetElectronRate  = 0
    let lastElectronSpawn   = 0
    let activeConnections: { x1: number; y1: number; z1: number; x2: number; y2: number; z2: number }[] = []

    // ── Lerped state values ──────────────────────────────────────────────
    let targetRadius    = 25, currentRadius = 25
    let targetSpeed     = 0.3, currentSpeed = 0.3
    let targetBright    = 0.6, currentBright = 0.6
    let targetSize      = 0.4, currentSize = 0.4
    let lineAmount      = 0, targetLineAmount = 0
    const lineDistance  = 8

    // Transition tumble
    let spinX = 0, spinY = 0, spinZ = 0
    let transitionEnergy = 0
    let lastState: OrbState = 'idle'

    // Z-axis breathing
    let cloudZ = 0, cloudZVel = 0

    const clock = new THREE.Clock()

    // ── Animation loop ───────────────────────────────────────────────────
    function animate() {
      if (destroyed) return
      requestAnimationFrame(animate)
      const t     = clock.getElapsedTime()
      const state = stateRef.current

      // State targets — faithful to Jarvis
      switch (state) {
        case 'idle':
          targetRadius = 28; targetSpeed = 0.2; targetBright = 0.5; targetSize = 0.35
          targetLineAmount = 0.15; targetElectronRate = 0; break
        case 'listening':
          targetRadius = 22; targetSpeed = 0.3; targetBright = 0.65; targetSize = 0.4
          targetLineAmount = 0.4; targetElectronRate = 0; break
        case 'thinking':
          targetRadius = 16; targetSpeed = 0.5; targetBright = 0.7; targetSize = 0.3
          targetLineAmount = 1.0; targetElectronRate = 0.015; break
        case 'speaking':
          targetRadius = 18; targetSpeed = 0.2; targetBright = 0.7; targetSize = 0.4
          targetLineAmount = 0.8; targetElectronRate = 0; break
      }

      const L = 0.02
      currentRadius     += (targetRadius    - currentRadius)    * L
      currentSpeed      += (targetSpeed     - currentSpeed)     * L
      currentBright     += (targetBright    - currentBright)    * L
      currentSize       += (targetSize      - currentSize)      * L
      lineAmount        += (targetLineAmount - lineAmount)       * L
      electronSpawnRate += (targetElectronRate - electronSpawnRate) * L

      // Tumble on state change
      if (state !== lastState) { transitionEnergy = 1.0; lastState = state }
      transitionEnergy *= 0.985
      if (transitionEnergy > 0.05) {
        spinX += transitionEnergy * 0.012 * Math.sin(t * 1.7)
        spinY += transitionEnergy * 0.015
        spinZ += transitionEnergy * 0.008 * Math.cos(t * 1.3)
      }

      // Audio — listening uses real mic data; speaking simulates waveform
      const an = analyserRef.current
      let bass = 0, mid = 0
      if (state === 'listening') {
        bass = an ? an.getBass() : 0
        mid  = an ? an.getMid()  : 0
      } else if (state === 'speaking') {
        // Simulate expressive audio so particles react even without TTS analyser
        bass = 0.18 + 0.40 * Math.abs(Math.sin(t * 4.1) * Math.cos(t * 2.3))
        mid  = 0.10 + 0.28 * Math.abs(Math.sin(t * 7.3 + 1.2))
      }

      // Z-axis breathing (cloud depth movement)
      let zTarget = Math.sin(t * 0.12) * 8
      if (state === 'thinking')  zTarget = Math.sin(t * 0.3) * 15 + Math.sin(t * 0.9) * 6
      else if (state === 'speaking') zTarget = Math.sin(t * 0.15) * 6 - bass * 10
      cloudZVel += (zTarget - cloudZ) * 0.008
      cloudZVel *= 0.94
      cloudZ    += cloudZVel

      // Apply rotation + Z offset to all meshes
      const meshes = [points, lines, electrons]
      for (const m of meshes) {
        m.rotation.x = spinX
        m.rotation.y = spinY
        m.rotation.z = spinZ
        m.position.z = cloudZ
      }

      // ── Update particle positions (velocity physics) ─────────────────
      const pAttr = geo.getAttribute('position') as THREE.BufferAttribute
      const a     = pAttr.array as Float32Array

      for (let i = 0; i < N; i++) {
        const i3 = i * 3
        const x  = a[i3], y = a[i3 + 1], z = a[i3 + 2]
        const px = phase[i]

        // Multi-octave noise force
        vel[i3]     += Math.sin(t * 0.05 + px) * 0.001 * currentSpeed
        vel[i3 + 1] += Math.cos(t * 0.06 + px * 1.3) * 0.001 * currentSpeed
        vel[i3 + 2] += Math.sin(t * 0.055 + px * 0.7) * 0.001 * currentSpeed
        vel[i3]     += Math.sin(t * 0.02 + px * 2.1 + y * 0.1) * 0.0008 * currentSpeed
        vel[i3 + 1] += Math.cos(t * 0.025 + px * 1.7 + z * 0.1) * 0.0008 * currentSpeed
        vel[i3 + 2] += Math.sin(t * 0.022 + px * 0.9 + x * 0.1) * 0.0008 * currentSpeed

        // Radius pull
        const dist = Math.sqrt(x * x + y * y + z * z) || 0.01
        const pull = Math.max(0, dist - currentRadius) * 0.002 + 0.0003
        vel[i3]     -= (x / dist) * pull
        vel[i3 + 1] -= (y / dist) * pull
        vel[i3 + 2] -= (z / dist) * pull

        // Bass expansion
        if (bass > 0.05) {
          vel[i3]     += (x / dist) * bass * 0.02
          vel[i3 + 1] += (y / dist) * bass * 0.02
          vel[i3 + 2] += (z / dist) * bass * 0.02
        }
        // Mid radial pulse (speaking)
        if (state === 'speaking' && mid > 0.1) {
          const pulse = Math.sin(t * 8 + px)
          vel[i3]     += (x / dist) * mid * 0.012 * pulse
          vel[i3 + 1] += (y / dist) * mid * 0.012 * pulse
        }

        // Damping
        vel[i3] *= 0.992; vel[i3 + 1] *= 0.992; vel[i3 + 2] *= 0.992

        a[i3]     += vel[i3]
        a[i3 + 1] += vel[i3 + 1]
        a[i3 + 2] += vel[i3 + 2]
      }
      pAttr.needsUpdate = true

      // ── Build proximity connection lines ─────────────────────────────
      if (lineAmount > 0.01) {
        const lAttr    = lineGeo.getAttribute('position') as THREE.BufferAttribute
        const la       = lAttr.array as Float32Array
        let lineCount  = 0
        const maxDist  = lineDistance * (1 + bass * 0.5)
        const maxDistSq = maxDist * maxDist
        const step     = Math.max(1, Math.floor(N / 600))

        for (let i = 0; i < N && lineCount < MAX_LINES; i += step) {
          const i3 = i * 3
          const x1 = a[i3], y1 = a[i3 + 1], z1 = a[i3 + 2]
          for (let j = i + step; j < N && lineCount < MAX_LINES; j += step) {
            const j3 = j * 3
            const dx = a[j3] - x1, dy = a[j3 + 1] - y1, dz = a[j3 + 2] - z1
            if (dx * dx + dy * dy + dz * dz < maxDistSq) {
              const idx = lineCount * 6
              la[idx] = x1;    la[idx + 1] = y1;    la[idx + 2] = z1
              la[idx + 3] = a[j3]; la[idx + 4] = a[j3 + 1]; la[idx + 5] = a[j3 + 2]
              lineCount++
            }
          }
        }
        lineGeo.setDrawRange(0, lineCount * 2)
        lAttr.needsUpdate = true
        lineMat.opacity = lineAmount * 0.12

        // Cache up to 500 connections for electron spawning
        activeConnections = []
        for (let c = 0; c < Math.min(lineCount, 500); c++) {
          const ci = c * 6
          activeConnections.push({
            x1: la[ci], y1: la[ci + 1], z1: la[ci + 2],
            x2: la[ci + 3], y2: la[ci + 4], z2: la[ci + 5],
          })
        }
      } else {
        lineGeo.setDrawRange(0, 0)
        activeConnections = []
      }

      // ── Electrons — one per ~1s, max 3 alive, thinking only ──────────
      if (activeConnections.length > 0 && electronSpawnRate > 0.005) {
        if (activeElectrons.length < 3 && (t - lastElectronSpawn) > 1.0) {
          const conn = activeConnections[Math.floor(Math.random() * activeConnections.length)]
          activeElectrons.push({
            sx: conn.x1, sy: conn.y1, sz: conn.z1,
            ex: conn.x2, ey: conn.y2, ez: conn.z2,
            t: 0, speed: 0.003 + Math.random() * 0.003,
          })
          lastElectronSpawn = t
        }
      }

      const eAttr  = electronGeo.getAttribute('position') as THREE.BufferAttribute
      const ea     = eAttr.array as Float32Array
      let aliveCount = 0

      for (let e = activeElectrons.length - 1; e >= 0; e--) {
        const el = activeElectrons[e]
        el.t += el.speed
        if (el.t >= 1) { activeElectrons.splice(e, 1); continue }
        const ei  = aliveCount * 3
        ea[ei]     = el.sx + (el.ex - el.sx) * el.t
        ea[ei + 1] = el.sy + (el.ey - el.sy) * el.t
        ea[ei + 2] = el.sz + (el.ez - el.sz) * el.t
        aliveCount++
      }
      electronGeo.setDrawRange(0, aliveCount)
      eAttr.needsUpdate = true

      // ── Material updates ─────────────────────────────────────────────
      mat.opacity = currentBright + bass * 0.08
      mat.size    = currentSize   + bass * 0.05

      const targetCol = new THREE.Color(STATE_COLOR[state])
      mat.color.lerp(targetCol, 0.015)
      lineMat.color.lerp(targetCol, 0.015)

      // ── Camera drift ─────────────────────────────────────────────────
      camera.position.x = Math.sin(t * 0.02) * 5
      camera.position.y = Math.cos(t * 0.03) * 3
      camera.lookAt(0, 0, cloudZ * 0.2)

      renderer.render(scene, camera)
    }

    // ── Resize handler ──────────────────────────────────────────────────
    const onResize = () => {
      const w = canvas.clientWidth  || window.innerWidth
      const h = canvas.clientHeight || window.innerHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    const ro = new ResizeObserver(onResize)
    ro.observe(canvas)
    window.addEventListener('resize', onResize)

    animate()

    return () => {
      destroyed = true
      ro.disconnect()
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      geo.dispose();         mat.dispose()
      lineGeo.dispose();     lineMat.dispose()
      electronGeo.dispose(); electronMat.dispose()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  )
}
