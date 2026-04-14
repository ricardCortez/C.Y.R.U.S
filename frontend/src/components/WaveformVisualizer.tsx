/**
 * C.Y.R.U.S — Audio waveform visualizer.
 *
 * Canvas-based spectrum analyzer with 48 bars.
 * Amplitudes are simulated from the WebSocket system state
 * (the actual audio lives in the Python backend).
 *
 * Patterns:
 *   idle/offline  → ultra-quiet noise floor
 *   listening     → randomised mic-input bars (green)
 *   transcribing  → slow settling decay (cyan)
 *   thinking      → low steady rhythmic pulse (orange)
 *   speaking      → voice-like formant wave (cyan, high energy)
 *   error         → flat low red bars
 */

import { useEffect, useRef } from 'react'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'

const BARS        = 48
const BAR_GAP     = 2
const LERP_SPEED  = 0.18   // 0 = instant, 1 = frozen

// ── Color per state ────────────────────────────────────────────────────────
const BAR_COLOR: Record<SystemState, [string, string]> = {
  offline:      ['#0a2030', '#0a2030'],
  connected:    ['#003850', '#00d4ff'],
  idle:         ['#002840', '#0077bb'],
  listening:    ['#004030', '#00ff88'],
  transcribing: ['#003858', '#00d4ff'],
  thinking:     ['#3a2400', '#ff8c00'],
  speaking:     ['#003858', '#00d4ff'],
  error:        ['#3a0000', '#ff3333'],
}

// ── Target amplitude generators ────────────────────────────────────────────
function targetAmplitudes(state: SystemState, t: number): number[] {
  return Array.from({ length: BARS }, (_, i) => {
    const n = i / BARS   // normalised 0→1

    switch (state) {
      case 'listening': {
        // Random mic noise — higher in the mids
        const env = Math.sin(n * Math.PI) * 0.7 + 0.1
        return Math.random() * env * 0.85 + 0.05
      }
      case 'speaking': {
        // Voiced speech: formant bumps at ~15%, ~45%, ~65% + random jitter
        const f1 = 0.55 * Math.exp(-Math.pow((n - 0.15) / 0.08, 2))
        const f2 = 0.75 * Math.exp(-Math.pow((n - 0.42) / 0.10, 2))
        const f3 = 0.45 * Math.exp(-Math.pow((n - 0.65) / 0.08, 2))
        const wave = Math.abs(Math.sin(i * 0.7 + t * 12)) * 0.2
        return Math.min(1, f1 + f2 + f3 + wave + Math.random() * 0.12)
      }
      case 'thinking':
      case 'transcribing': {
        // Slow rhythmic sweep
        const sweep = 0.5 + 0.5 * Math.sin(n * Math.PI * 2 - t * 3)
        return sweep * 0.3 + 0.05 + Math.random() * 0.06
      }
      case 'idle':
      case 'connected': {
        // Nearly silent — just a noise floor
        return Math.random() * 0.06 + 0.01
      }
      case 'error': {
        return 0.08 + Math.random() * 0.04
      }
      default:
        return 0.01
    }
  })
}

// ── Component ──────────────────────────────────────────────────────────────
export function WaveformVisualizer() {
  const state      = useCYRUSStore(s => s.systemState)
  const canvasRef  = useRef<HTMLCanvasElement>(null)
  const barsRef    = useRef<number[]>(Array(BARS).fill(0.02))
  const rafRef     = useRef<number>(0)
  const tRef       = useRef<number>(0)
  const stateRef   = useRef<SystemState>(state)

  // Keep stateRef in sync without triggering re-renders in the loop
  useEffect(() => { stateRef.current = state }, [state])

  useEffect(() => {
    const canvas  = canvasRef.current
    if (!canvas) return
    const ctx     = canvas.getContext('2d')!

    function draw() {
      tRef.current += 0.016   // ~60fps time accumulator

      const W = canvas.width
      const H = canvas.height
      const s = stateRef.current
      const [colorBot, colorTop] = BAR_COLOR[s]

      // Clear
      ctx.clearRect(0, 0, W, H)

      // New targets
      const targets = targetAmplitudes(s, tRef.current)

      // Lerp current bars toward targets
      for (let i = 0; i < BARS; i++) {
        barsRef.current[i] += (targets[i] - barsRef.current[i]) * LERP_SPEED
      }

      const barW = (W - (BARS - 1) * BAR_GAP) / BARS

      for (let i = 0; i < BARS; i++) {
        const amp = barsRef.current[i]
        const x   = i * (barW + BAR_GAP)
        const h   = Math.max(2, amp * H)
        const y   = H - h

        // Gradient per bar
        const grad = ctx.createLinearGradient(x, H, x, y)
        grad.addColorStop(0, colorBot)
        grad.addColorStop(1, colorTop)

        ctx.fillStyle = grad
        ctx.beginPath()
        ctx.roundRect(x, y, barW, h, 1)
        ctx.fill()

        // Top glow cap
        if (amp > 0.15) {
          ctx.fillStyle = colorTop
          ctx.globalAlpha = amp * 0.8
          ctx.fillRect(x, y - 1, barW, 2)
          ctx.globalAlpha = 1
        }
      }

      // Mirror (reflection below) — subtle
      ctx.save()
      ctx.globalAlpha = 0.12
      ctx.scale(1, -0.3)
      ctx.translate(0, -H * (1 / 0.3) - H)
      for (let i = 0; i < BARS; i++) {
        const amp = barsRef.current[i]
        const x   = i * (barW + BAR_GAP)
        const h   = Math.max(2, amp * H)
        ctx.fillStyle = BAR_COLOR[s][1]
        ctx.beginPath()
        ctx.roundRect(x, H - h, barW, h, 1)
        ctx.fill()
      }
      ctx.restore()

      rafRef.current = requestAnimationFrame(draw)
    }

    rafRef.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])   // runs once — state consumed via ref

  const [, colorTop] = BAR_COLOR[state]

  return (
    <div className="flex flex-col gap-1 w-full">
      {/* Label row */}
      <div className="flex items-center justify-between px-1">
        <span className="font-mono text-[9px] tracking-widest" style={{ color: '#1a3040' }}>
          AUDIO SPECTRUM
        </span>
        <span className="font-mono text-[9px] tracking-widest" style={{ color: colorTop + '99' }}>
          {state === 'listening'    ? 'MIC INPUT'
           : state === 'speaking'  ? 'VOICE OUTPUT'
           : state === 'thinking'  ? 'PROCESSING'
           : state === 'transcribing' ? 'DECODING'
           : 'STANDBY'}
        </span>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        width={280}
        height={64}
        style={{ width: '100%', height: 64 }}
      />

      {/* Frequency axis labels */}
      <div className="flex justify-between px-1">
        {['20Hz', '500Hz', '2kHz', '8kHz', '20kHz'].map(f => (
          <span key={f} className="font-mono text-[8px]" style={{ color: '#0a2030' }}>{f}</span>
        ))}
      </div>
    </div>
  )
}
