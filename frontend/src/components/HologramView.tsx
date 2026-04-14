/**
 * C.Y.R.U.S — JARVIS-style holographic display.
 * SVG rings + orbital dots + reactive glow — all driven by WebSocket state.
 */

import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'

// ── State → visual mapping ─────────────────────────────────────────────────

const COLOR: Record<SystemState, string> = {
  offline:      '#1a3050',
  connected:    '#00d4ff',
  idle:         '#0077bb',
  listening:    '#00ff88',
  transcribing: '#00d4ff',
  thinking:     '#ff8c00',
  speaking:     '#00d4ff',
  error:        '#ff3333',
}

const LABEL: Record<SystemState, string> = {
  offline:      'OFFLINE',
  connected:    'STANDBY',
  idle:         'IDLE — AWAITING TRIGGER',
  listening:    'CAPTURING VOICE INPUT',
  transcribing: 'PROCESSING AUDIO',
  thinking:     'REASONING',
  speaking:     'TRANSMITTING RESPONSE',
  error:        'SYSTEM ERROR',
}

// ── Ring speed classes per state ───────────────────────────────────────────

function ringClasses(state: SystemState) {
  const fast  = state === 'thinking' || state === 'transcribing'
  const med   = state === 'listening' || state === 'speaking'

  return {
    outer:  fast ? 'holo-ring-cw-fast'  : med ? 'holo-ring-cw-med'  : 'holo-ring-cw-slow',
    outer2: fast ? 'holo-ring-ccw-slow' : med ? 'holo-ring-ccw-med' : 'holo-ring-ccw-slow',
    orbitA: fast ? 'holo-orbit-a-fast'  : 'holo-orbit-a',
    orbitB: fast ? 'holo-orbit-b-fast'  : 'holo-orbit-b',
    core:   state === 'speaking' ? 'holo-pulse-fast' : 'holo-pulse-slow',
  }
}

// ── Tick marks around a ring ───────────────────────────────────────────────

function Ticks({ r, count = 32, color }: { r: number; count?: number; color: string }) {
  const ticks = Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * 2 * Math.PI
    const major = i % (count / 4) === 0
    const len = major ? 8 : 4
    const x1 = 160 + (r - len) * Math.cos(angle)
    const y1 = 160 + (r - len) * Math.sin(angle)
    const x2 = 160 + r * Math.cos(angle)
    const y2 = 160 + r * Math.sin(angle)
    return { x1, y1, x2, y2, major }
  })
  return (
    <>
      {ticks.map((t, i) => (
        <line key={i} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
          stroke={color} strokeWidth={t.major ? 1.5 : 0.75}
          strokeOpacity={t.major ? 0.7 : 0.3} />
      ))}
    </>
  )
}

// ── Hex segment arc decorations ────────────────────────────────────────────

function ArcSegments({ r, color, count = 6 }: { r: number; color: string; count?: number }) {
  const segs = Array.from({ length: count }, (_, i) => {
    const start = ((i / count) * 2 * Math.PI) - 0.15
    const end   = start + (2 * Math.PI / count) * 0.55
    const x1 = 160 + r * Math.cos(start)
    const y1 = 160 + r * Math.sin(start)
    const x2 = 160 + r * Math.cos(end)
    const y2 = 160 + r * Math.sin(end)
    const large = end - start > Math.PI ? 1 : 0
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`
  })
  return (
    <>
      {segs.map((d, i) => (
        <path key={i} d={d} fill="none"
          stroke={color} strokeWidth="2.5" strokeOpacity="0.6"
          strokeLinecap="round" />
      ))}
    </>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export function HologramView() {
  const state = useCYRUSStore(s => s.systemState)
  const c     = COLOR[state]
  const label = LABEL[state]
  const cls   = ringClasses(state)
  const isListening = state === 'listening'
  const isSpeaking  = state === 'speaking'
  const isThinking  = state === 'thinking' || state === 'transcribing'
  const isOffline   = state === 'offline'

  return (
    <div className="relative flex flex-col items-center select-none w-full">
      {/* ── SVG hologram — fills parent container ── */}
      <div className="relative w-full" style={{ aspectRatio: '1' }}>
        <svg
          viewBox="0 0 320 320"
          style={{ width: '100%', height: '100%', overflow: 'visible' }}
        >
          <defs>
            {/* Core radial gradient */}
            <radialGradient id="holo-core-grad" cx="50%" cy="50%" r="50%">
              <stop offset="0%"   stopColor={c} stopOpacity="0.35" />
              <stop offset="50%"  stopColor={c} stopOpacity="0.08" />
              <stop offset="100%" stopColor={c} stopOpacity="0" />
            </radialGradient>
            {/* Glow filter */}
            <filter id="holo-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="holo-glow-strong" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {/* Clip to circle */}
            <clipPath id="holo-clip">
              <circle cx="160" cy="160" r="155" />
            </clipPath>
          </defs>

          {/* Background ambient glow */}
          <circle cx="160" cy="160" r="150" fill="url(#holo-core-grad)" />

          {/* ── Outer dashed ring (rotates CW) ── */}
          <g className={cls.outer}>
            <circle cx="160" cy="160" r="148"
              fill="none" stroke={c} strokeWidth="0.5" strokeOpacity="0.2"
              strokeDasharray="2 8" />
            <Ticks r={148} count={64} color={c} />
          </g>

          {/* ── Second ring (rotates CCW) with arc segments ── */}
          <g className={cls.outer2}>
            <circle cx="160" cy="160" r="132"
              fill="none" stroke={c} strokeWidth="0.5" strokeOpacity="0.15"
              strokeDasharray="60 30 5 30" />
            <ArcSegments r={132} color={c} count={4} />
          </g>

          {/* ── Tilted elliptical orbit path A ── */}
          <ellipse cx="160" cy="160" rx="108" ry="42"
            fill="none" stroke={c} strokeWidth="0.4" strokeOpacity="0.18"
            transform="rotate(-35, 160, 160)" />

          {/* ── Tilted elliptical orbit path B ── */}
          <ellipse cx="160" cy="160" rx="108" ry="42"
            fill="none" stroke={c} strokeWidth="0.4" strokeOpacity="0.15"
            transform="rotate(35, 160, 160)" />

          {/* ── Orbiting dot A ── */}
          <g className={cls.orbitA}>
            <circle cx="160" cy="160" r="5"
              fill={c} filter="url(#holo-glow-strong)" />
            {/* Dot trail */}
            <circle cx="148" cy="160" r="2.5"
              fill={c} fillOpacity="0.4" />
            <circle cx="136" cy="160" r="1.5"
              fill={c} fillOpacity="0.2" />
          </g>

          {/* ── Orbiting dot B ── */}
          <g className={cls.orbitB}>
            <circle cx="160" cy="160" r="3.5"
              fill={c} filter="url(#holo-glow)" fillOpacity="0.85" />
          </g>

          {/* ── Inner primary ring with arc segments ── */}
          <g className="holo-ring-cw-slow" style={{ transformOrigin: '160px 160px', animationDuration: isThinking ? '3s' : '10s' }}>
            <circle cx="160" cy="160" r="90"
              fill="none" stroke={c} strokeWidth="0.6" strokeOpacity="0.25"
              strokeDasharray="5 10" />
            <ArcSegments r={90} color={c} count={6} />
          </g>

          {/* ── Scanner line (only when listening or thinking) ── */}
          {(isListening || isThinking) && (
            <g clipPath="url(#holo-clip)">
              <line x1="10" y1="160" x2="310" y2="160"
                stroke={c} strokeWidth="1" strokeOpacity="0.5"
                className="holo-scan" />
            </g>
          )}

          {/* ── Core glow circle ── */}
          <circle cx="160" cy="160" r="68"
            fill={c} fillOpacity="0.04" />
          <circle cx="160" cy="160" r="68"
            fill="none" stroke={c} strokeWidth="1.5" strokeOpacity={isOffline ? 0.15 : 0.5}
            filter="url(#holo-glow)"
            className={cls.core} />

          {/* ── Inner solid ring ── */}
          <circle cx="160" cy="160" r="55"
            fill="none" stroke={c} strokeWidth="1" strokeOpacity="0.3" />

          {/* ── Crosshair ── */}
          <line x1="75"  y1="160" x2="108" y2="160" stroke={c} strokeWidth="0.6" strokeOpacity="0.4" />
          <line x1="212" y1="160" x2="245" y2="160" stroke={c} strokeWidth="0.6" strokeOpacity="0.4" />
          <line x1="160" y1="75"  x2="160" y2="108" stroke={c} strokeWidth="0.6" strokeOpacity="0.4" />
          <line x1="160" y1="212" x2="160" y2="245" stroke={c} strokeWidth="0.6" strokeOpacity="0.4" />

          {/* ── Corner bracket markers ── */}
          {[[-1,-1],[1,-1],[1,1],[-1,1]].map(([sx, sy], i) => (
            <g key={i} transform={`translate(${160 + sx * 128}, ${160 + sy * 128})`}>
              <line x1="0" y1="0" x2={sx * 12} y2="0"    stroke={c} strokeWidth="1.5" strokeOpacity="0.6" />
              <line x1="0" y1="0" x2="0"       y2={sy * 12} stroke={c} strokeWidth="1.5" strokeOpacity="0.6" />
            </g>
          ))}

          {/* ── Speaking pulse rings (extra rings when speaking) ── */}
          {isSpeaking && (
            <>
              <circle cx="160" cy="160" r="78"
                fill="none" stroke={c} strokeWidth="0.5" strokeOpacity="0.3"
                className="holo-pulse-fast" />
              <circle cx="160" cy="160" r="88"
                fill="none" stroke={c} strokeWidth="0.3" strokeOpacity="0.2"
                className="holo-pulse-fast"
                style={{ animationDelay: '0.2s' }} />
            </>
          )}

          {/* ── Data readout lines (side panels) ── */}
          {[...Array(5)].map((_, i) => (
            <g key={i} className="holo-data-blink"
              style={{ animationDelay: `${i * 0.3}s`,
                       animation: `holo-data-blink ${1.5 + i * 0.4}s ease-in-out infinite` }}>
              <line x1="12" y1={130 + i * 10} x2={30 + (i % 3) * 8} y2={130 + i * 10}
                stroke={c} strokeWidth="0.8" strokeOpacity="0.4" />
            </g>
          ))}
          {[...Array(5)].map((_, i) => (
            <g key={i}
              style={{ animation: `holo-data-blink ${1.2 + i * 0.3}s ease-in-out infinite`,
                       animationDelay: `${i * 0.25}s` }}>
              <line x1={290 - (i % 3) * 8} y1={130 + i * 10} x2={308} y2={130 + i * 10}
                stroke={c} strokeWidth="0.8" strokeOpacity="0.4" />
            </g>
          ))}
        </svg>

        {/* ── Text overlay ── */}
        <div
          className={`absolute inset-0 flex flex-col items-center justify-center pointer-events-none ${isOffline ? '' : 'holo-flicker'}`}
        >
          <span
            className="font-mono font-bold tracking-[0.35em] text-base"
            style={{
              color: c,
              textShadow: `0 0 8px ${c}, 0 0 20px ${c}88`,
            }}
          >
            C.Y.R.U.S
          </span>
          <div
            className="my-1"
            style={{
              width: 48,
              height: 1,
              background: `linear-gradient(90deg, transparent, ${c}, transparent)`,
            }}
          />
          <span
            className="font-mono text-[9px] tracking-[0.25em]"
            style={{ color: `${c}99` }}
          >
            AI CORE
          </span>
        </div>
      </div>

      {/* ── Status label ── */}
      <div className="mt-2 text-center" style={{ minHeight: 20 }}>
        <span
          className="font-mono text-[10px] tracking-widest uppercase"
          style={{ color: `${c}cc` }}
        >
          {label}
        </span>
      </div>
    </div>
  )
}
