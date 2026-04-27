/**
 * JARVIS — System diagnostics HUD panel.
 * Right-side panel: live metrics, neural data stream, pipeline status.
 */

import { useEffect, useState } from 'react'
import { useJARVISStore, SystemState } from '../store/useJARVISStore'

// ── Pipeline stages ────────────────────────────────────────────────────────

const PIPELINE_STAGES: { id: string; label: string; active: SystemState[] }[] = [
  { id: 'audio',  label: 'AUDIO INPUT',  active: ['listening', 'idle', 'connected'] },
  { id: 'wake',   label: 'WAKE DETECT',  active: ['listening', 'idle', 'connected'] },
  { id: 'asr',    label: 'TRANSCRIBE',   active: ['transcribing'] },
  { id: 'llm',    label: 'REASONING',    active: ['thinking'] },
  { id: 'tts',    label: 'SYNTHESIS',    active: ['speaking'] },
]

const STATE_COLOR: Record<string, string> = {
  offline:      '#ff3333',
  connected:    '#00d4ff',
  idle:         '#0077bb',
  listening:    '#00ff88',
  transcribing: '#00d4ff',
  thinking:     '#ff8c00',
  speaking:     '#00d4ff',
  error:        '#ff3333',
}

// ── Hex data stream generator ──────────────────────────────────────────────

function rndHex(bytes: number) {
  return Array.from({ length: bytes }, () =>
    Math.floor(Math.random() * 256).toString(16).toUpperCase().padStart(2, '0')
  ).join('')
}

function genStreamLine() {
  return `${rndHex(2)} ${rndHex(3)} ${rndHex(2)} ${rndHex(4)} ${rndHex(2)} ${rndHex(3)}`
}

// ── Sub-components ─────────────────────────────────────────────────────────

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <div className="flex-1" style={{ height: 1, background: 'linear-gradient(90deg, #0a3050, transparent)' }} />
      <span className="font-mono text-[9px] tracking-[0.25em]" style={{ color: '#0a3050' }}>{label}</span>
    </div>
  )
}

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-center py-[3px]">
      <span className="font-mono text-[10px]" style={{ color: '#1a3040' }}>{label}</span>
      <span className="font-mono text-[10px]" style={{ color: color ?? '#405060' }}>{value}</span>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export function DebugPanel() {
  const wsConnected   = useJARVISStore(s => s.wsConnected)
  const systemState   = useJARVISStore(s => s.systemState)
  const statusMessage = useJARVISStore(s => s.statusMessage)
  const transcript    = useJARVISStore(s => s.transcript)

  const [streamLines, setStreamLines] = useState<string[]>(() =>
    Array.from({ length: 10 }, genStreamLine)
  )
  const [uptime, setUptime] = useState(0)
  const [tick, setTick] = useState(0)

  // Uptime counter
  useEffect(() => {
    const id = setInterval(() => setUptime(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  // Data stream — update 2 random lines every 180ms
  useEffect(() => {
    const id = setInterval(() => {
      setStreamLines(prev => {
        const next = [...prev]
        const idx1 = Math.floor(Math.random() * next.length)
        const idx2 = Math.floor(Math.random() * next.length)
        next[idx1] = genStreamLine()
        next[idx2] = genStreamLine()
        return next
      })
      setTick(t => t + 1)
    }, 160)
    return () => clearInterval(id)
  }, [])

  const stateColor = STATE_COLOR[systemState] ?? '#0077bb'
  const turnCount  = transcript.filter(e => e.role === 'user').length

  const uptimeStr = [
    String(Math.floor(uptime / 3600)).padStart(2, '0'),
    String(Math.floor((uptime % 3600) / 60)).padStart(2, '0'),
    String(uptime % 60).padStart(2, '0'),
  ].join(':')

  return (
    <div
      className="h-full flex flex-col overflow-y-auto"
      style={{
        background: 'linear-gradient(180deg, #040d1a 0%, #04101e 100%)',
        borderLeft: '1px solid #0a2030',
        padding: '12px 14px',
        gap: 0,
      }}
    >
      {/* ── Connection status ─────────────────────────────────────── */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-1">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              background: wsConnected ? '#00ff88' : '#ff3333',
              boxShadow:  wsConnected ? '0 0 8px #00ff88' : '0 0 8px #ff3333',
            }}
          />
          <span className="font-mono text-[10px] tracking-widest" style={{ color: wsConnected ? '#00ff88' : '#ff3333' }}>
            {wsConnected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
        <div className="font-mono text-[9px] pl-4" style={{ color: '#0a2030' }}>
          ws://localhost:8765
        </div>
      </div>

      {/* ── System metrics ────────────────────────────────────────── */}
      <SectionHeader label="SYSTEM METRICS" />
      <div className="mb-4">
        <MetricRow label="STATE"  value={systemState.toUpperCase()} color={stateColor} />
        <MetricRow label="UPTIME" value={uptimeStr} />
        <MetricRow label="TURNS"  value={String(turnCount)} />
        <MetricRow label="LLM"    value="phi3:latest" />
        <MetricRow label="ASR"    value="WHISPER TINY" />
        <MetricRow label="TTS"    value="EDGE-TTS" />
        <MetricRow label="MEM"    value="QDRANT + SQLite" />
      </div>

      {/* ── Pipeline status ───────────────────────────────────────── */}
      <SectionHeader label="PIPELINE" />
      <div className="mb-4 flex flex-col gap-[6px]">
        {PIPELINE_STAGES.map(stage => {
          const active = stage.active.includes(systemState)
          return (
            <div key={stage.id} className="flex items-center gap-2">
              <div
                style={{
                  width: 6, height: 6,
                  borderRadius: '50%',
                  background: active ? stateColor : '#0a2030',
                  boxShadow:  active ? `0 0 6px ${stateColor}` : 'none',
                  flexShrink: 0,
                }}
              />
              <div
                className="flex-1"
                style={{
                  height: 1,
                  background: active
                    ? `linear-gradient(90deg, ${stateColor}66, transparent)`
                    : 'linear-gradient(90deg, #0a2030, transparent)',
                }}
              />
              <span
                className="font-mono text-[9px] tracking-widest"
                style={{ color: active ? stateColor : '#0a2030', minWidth: 80, textAlign: 'right' }}
              >
                {stage.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* ── Neural data stream ────────────────────────────────────── */}
      <SectionHeader label="NEURAL STREAM" />
      <div
        className="mb-4 rounded p-2"
        style={{ background: 'rgba(0,10,20,0.6)', border: '1px solid #05151f' }}
      >
        {streamLines.map((line, i) => (
          <div
            key={i}
            className="font-mono leading-[1.55]"
            style={{
              fontSize: 8,
              color: '#00d4ff',
              opacity: 0.08 + (i / streamLines.length) * 0.35,
              letterSpacing: '0.05em',
            }}
          >
            {line}
          </div>
        ))}
      </div>

      {/* ── Tick counter ─────────────────────────────────────────── */}
      <div className="flex justify-between mb-4">
        <span className="font-mono text-[8px]" style={{ color: '#05151f' }}>CYCLE</span>
        <span className="font-mono text-[8px]" style={{ color: '#0a2030' }}>
          {String(tick).padStart(6, '0')}
        </span>
      </div>

      {/* ── Status message ───────────────────────────────────────── */}
      {statusMessage && (
        <div
          className="rounded px-2 py-1.5 font-mono text-[9px] leading-relaxed"
          style={{
            background: 'rgba(0,20,40,0.5)',
            borderLeft: `2px solid ${stateColor}44`,
            color: `${stateColor}99`,
          }}
        >
          {statusMessage}
        </div>
      )}
    </div>
  )
}
