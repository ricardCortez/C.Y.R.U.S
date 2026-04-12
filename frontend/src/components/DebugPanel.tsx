/**
 * C.Y.R.U.S — Debug / metrics panel.
 * Shows connection status, system state, and basic operational metrics.
 */

import { useCYRUSStore } from '../store/useCYRUSStore'
import { Wifi, WifiOff, Activity, Cpu, Mic } from 'lucide-react'

interface MetricRowProps {
  label: string
  value: string
  ok?: boolean
}

function MetricRow({ label, value, ok }: MetricRowProps) {
  return (
    <div className="flex justify-between items-center py-1" style={{ borderBottom: '1px solid #0a2030' }}>
      <span className="font-mono text-xs" style={{ color: '#406080' }}>{label}</span>
      <span
        className="font-mono text-xs"
        style={{ color: ok === undefined ? '#80a0b0' : ok ? '#00ff88' : '#ff4444' }}
      >
        {value}
      </span>
    </div>
  )
}

export function DebugPanel() {
  const wsConnected  = useCYRUSStore((s) => s.wsConnected)
  const systemState  = useCYRUSStore((s) => s.systemState)
  const statusMessage = useCYRUSStore((s) => s.statusMessage)
  const transcript   = useCYRUSStore((s) => s.transcript)

  const turnCount = transcript.filter(e => e.role === 'user').length

  return (
    <div
      className="p-4 font-mono"
      style={{ background: '#040d1a', border: '1px solid #0a4060' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <Activity size={12} style={{ color: '#00d4ff' }} />
        <span className="text-xs tracking-widest" style={{ color: '#004060' }}>SYSTEM DIAGNOSTICS</span>
      </div>

      {/* Connection */}
      <div className="flex items-center gap-2 mb-3 pb-2" style={{ borderBottom: '1px solid #0a2030' }}>
        {wsConnected
          ? <Wifi size={14} style={{ color: '#00ff88' }} />
          : <WifiOff size={14} style={{ color: '#ff4444' }} />
        }
        <span className="text-xs" style={{ color: wsConnected ? '#00ff88' : '#ff4444' }}>
          {wsConnected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      {/* Metrics */}
      <div className="space-y-0">
        <MetricRow label="STATE"       value={systemState.toUpperCase()} />
        <MetricRow label="TURNS"       value={String(turnCount)} />
        <MetricRow label="WS ENDPOINT" value="ws://localhost:8765" ok={wsConnected} />
        <MetricRow label="LLM"         value="Ollama / Mistral 7B" />
        <MetricRow label="ASR"         value="Whisper TINY" />
        <MetricRow label="TTS"         value="Kokoro → Edge-TTS" />
      </div>

      {/* Status message */}
      {statusMessage && (
        <div
          className="mt-3 px-2 py-1 text-xs"
          style={{ background: 'rgba(0,40,80,0.4)', color: '#406080', borderLeft: '2px solid #0a4060' }}
        >
          {statusMessage}
        </div>
      )}
    </div>
  )
}
