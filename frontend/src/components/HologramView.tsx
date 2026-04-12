/**
 * C.Y.R.U.S — Hologram visual indicator.
 * Animates based on system state (idle pulse / listening ripple / speaking wave).
 */

import { useMemo } from 'react'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'

const STATE_COLORS: Record<SystemState, string> = {
  offline:      '#406080',
  connected:    '#00d4ff',
  idle:         '#0088ff',
  listening:    '#00ff88',
  transcribing: '#00d4ff',
  thinking:     '#ff8800',
  speaking:     '#00d4ff',
  error:        '#ff4444',
}

const STATE_LABELS: Record<SystemState, string> = {
  offline:      'OFFLINE',
  connected:    'ONLINE',
  idle:         'IDLE — LISTENING',
  listening:    'CAPTURING VOICE',
  transcribing: 'TRANSCRIBING',
  thinking:     'PROCESSING',
  speaking:     'RESPONDING',
  error:        'ERROR',
}

function Ring({ radius, opacity, rotate = 0 }: { radius: number; opacity: number; rotate?: number }) {
  return (
    <div
      className="absolute rounded-full border"
      style={{
        width:  radius * 2,
        height: radius * 2,
        left:   `calc(50% - ${radius}px)`,
        top:    `calc(50% - ${radius}px)`,
        borderColor: 'rgba(0,212,255,0.3)',
        transform: `rotate(${rotate}deg)`,
        opacity,
      }}
    />
  )
}

export function HologramView() {
  const systemState = useCYRUSStore((s) => s.systemState)
  const color = STATE_COLORS[systemState]
  const label = STATE_LABELS[systemState]

  const isActive  = systemState === 'listening' || systemState === 'speaking'
  const isThinking = systemState === 'thinking' || systemState === 'transcribing'

  return (
    <div className="relative flex items-center justify-center w-full" style={{ height: 280 }}>
      {/* Background rings */}
      <Ring radius={120} opacity={0.15} />
      <Ring radius={100} opacity={0.2} rotate={45} />
      <Ring radius={80}  opacity={0.25} />

      {/* Animated outer ring */}
      <div
        className={`absolute rounded-full border-2 transition-all duration-500 ${isActive ? 'animate-ping' : ''}`}
        style={{
          width: 140, height: 140,
          left: 'calc(50% - 70px)',
          top:  'calc(50% - 70px)',
          borderColor: color,
          opacity: isActive ? 0.4 : 0.2,
        }}
      />

      {/* Core circle */}
      <div
        className={`relative rounded-full flex items-center justify-center transition-all duration-300 ${isThinking ? 'animate-pulse' : ''}`}
        style={{
          width: 120, height: 120,
          background: `radial-gradient(circle, ${color}22 0%, ${color}08 70%, transparent 100%)`,
          border: `2px solid ${color}`,
          boxShadow: `0 0 30px ${color}66, inset 0 0 20px ${color}11`,
        }}
      >
        {/* Inner symbol */}
        <div className="flex flex-col items-center gap-1">
          <span
            className="font-mono text-lg font-bold tracking-widest"
            style={{ color, textShadow: `0 0 10px ${color}` }}
          >
            C.Y.R.U.S
          </span>
          <div
            className="w-8 h-px"
            style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
          />
          <span className="font-mono text-xs" style={{ color: `${color}99` }}>
            v1.0
          </span>
        </div>
      </div>

      {/* Status label below */}
      <div className="absolute bottom-0 w-full text-center">
        <span
          className="font-mono text-xs tracking-widest uppercase"
          style={{ color: `${color}cc` }}
        >
          {label}
        </span>
      </div>

      {/* Crosshair lines */}
      <div className="absolute" style={{ width: 260, height: 260, left: 'calc(50% - 130px)', top: 'calc(50% - 130px)' }}>
        <div className="absolute top-1/2 w-full h-px" style={{ background: `linear-gradient(90deg, transparent, ${color}33, transparent)` }} />
        <div className="absolute left-1/2 h-full w-px" style={{ background: `linear-gradient(180deg, transparent, ${color}33, transparent)` }} />
      </div>
    </div>
  )
}
