/**
 * C.Y.R.U.S — Control Panel  (route "/control")
 *
 * Layout: tabbed — SISTEMA | CONFIG | VOZ
 * Each tab groups related controls to avoid the long single-column scroll.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate }                  from 'react-router-dom'
import { motion, AnimatePresence }      from 'framer-motion'
import ReactMarkdown                    from 'react-markdown'
import { useCYRUSStore, SystemState, LogEntry, ServiceStatus } from '../store/useCYRUSStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { PRESETS, VisualPresetId } from '../types/presets'

// ── Color maps ──────────────────────────────────────────────────────────────
const STATE_COLOR: Record<SystemState, string> = {
  offline:      '#ff3333',
  connected:    '#00d4ff',
  idle:         '#0077bb',
  listening:    '#00ff88',
  transcribing: '#00d4ff',
  thinking:     '#ff8c00',
  speaking:     '#a855f7',
  error:        '#ff3333',
}
const STATE_LABEL: Record<SystemState, string> = {
  offline:      'OFFLINE',
  connected:    'STANDBY',
  idle:         'IDLE',
  listening:    'LISTENING',
  transcribing: 'TRANSCRIBING',
  thinking:     'PROCESSING',
  speaking:     'SPEAKING',
  error:        'ERROR',
}

// ── Primitives ───────────────────────────────────────────────────────────────

function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: 'rgba(0,16,32,0.7)',
      border: '1px solid #0a2030',
      borderRadius: 8,
      padding: '12px 14px',
      ...style,
    }}>
      {children}
    </div>
  )
}

function Label({ children, dim }: { children: React.ReactNode; dim?: boolean }) {
  return (
    <span className="font-mono" style={{
      fontSize: 8,
      letterSpacing: '0.25em',
      color: dim ? '#152530' : '#1e3a4a',
    }}>
      {children}
    </span>
  )
}

function Divider() {
  return <div style={{ height: 1, background: '#081820', margin: '2px 0' }} />
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span className="font-mono" style={{
      fontSize: 8,
      letterSpacing: '0.18em',
      padding: '4px 10px',
      borderRadius: 999,
      background: color,
      color: '#f8ffff',
      textTransform: 'uppercase',
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  )
}

// ── Stat bar ─────────────────────────────────────────────────────────────────

function StatBar({ label, value, color = '#00f0ff', unit = '%' }: {
  label: string; value: number; color?: string; unit?: string
}) {
  return (
    <div className="mb-3">
      <div className="flex justify-between mb-1">
        <span className="font-mono" style={{ fontSize: 9, color: '#2a4050', letterSpacing: '0.12em' }}>{label}</span>
        <span className="font-mono" style={{ fontSize: 9, color }}>{value.toFixed(0)}{unit}</span>
      </div>
      <div style={{ height: 3, background: '#071218', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, value)}%` }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
          style={{ height: '100%', background: `linear-gradient(90deg, ${color}66, ${color})`, borderRadius: 2 }}
        />
      </div>
    </div>
  )
}

// ── Slider ───────────────────────────────────────────────────────────────────

function Slider({ label, value, min, max, step = 0.05, unit = '', onChange, onCommit }: {
  label: string; value: number; min: number; max: number
  step?: number; unit?: string; onChange: (v: number) => void; onCommit?: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="mb-4">
      <div className="flex justify-between mb-2">
        <Label>{label}</Label>
        <span className="font-mono" style={{ fontSize: 9, color: '#00f0ff66' }}>{value.toFixed(2)}{unit}</span>
      </div>
      <div style={{ position: 'relative', height: 4, background: '#071218', borderRadius: 2 }}>
        <div style={{
          position: 'absolute', top: 0, left: 0, bottom: 0,
          width: `${pct}%`,
          background: 'linear-gradient(90deg, #00f0ff33, #00f0ff)',
          borderRadius: 2,
        }} />
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          onMouseUp={e => onCommit?.(parseFloat((e.target as HTMLInputElement).value))}
          onTouchEnd={e => onCommit?.(parseFloat((e.target as HTMLInputElement).value))}
          style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%', margin: 0 }}
        />
      </div>
    </div>
  )
}

// ── Tab bar ──────────────────────────────────────────────────────────────────

const TABS = ['SISTEMA', 'CONFIG', 'VOZ', 'API'] as const
type Tab = typeof TABS[number]

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div className="flex gap-1 mb-4" style={{
      background: 'rgba(0,10,20,0.8)',
      border: '1px solid #0a1e2a',
      borderRadius: 8,
      padding: 3,
    }}>
      {TABS.map(t => (
        <button key={t} onClick={() => onChange(t)}
          className="font-mono flex-1 rounded"
          style={{
            fontSize: 9,
            letterSpacing: '0.2em',
            padding: '6px 0',
            cursor: 'pointer',
            transition: 'all 0.2s',
            background:   active === t ? 'rgba(0,240,255,0.10)' : 'transparent',
            border:       active === t ? '1px solid #00f0ff33'  : '1px solid transparent',
            color:        active === t ? '#00f0ff'              : '#1e3a4a',
          }}
        >
          {t}
        </button>
      ))}
    </div>
  )
}

// ── Helper ───────────────────────────────────────────────────────────────────

function uptimeStr(s: number) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return [h, m, sec].map(n => String(n).padStart(2, '0')).join(':')
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 1 — SISTEMA
// ═══════════════════════════════════════════════════════════════════════════

const LOG_COLOR: Record<string, string> = {
  info:  '#00f0ff',
  warn:  '#ff8c00',
  error: '#ff3333',
  ok:    '#00ff88',
}

function TabSistema() {
  const systemState = useCYRUSStore(s => s.systemState)
  const wsConnected = useCYRUSStore(s => s.wsConnected)
  const statusMsg   = useCYRUSStore(s => s.statusMessage)
  const stats       = useCYRUSStore(s => s.systemStats)
  const logs        = useCYRUSStore(s => s.logs)
  const clearLogs   = useCYRUSStore(s => s.clearLogs)
  const endRef      = useRef<HTMLDivElement>(null)

  const [fake, setFake] = useState({ cpu: 18, ram: 52, vram: 31 })
  useEffect(() => {
    if (stats) return
    const id = setInterval(() => setFake(v => ({
      cpu:  Math.max(5,  Math.min(85, v.cpu  + (Math.random() - 0.5) * 4)),
      ram:  Math.max(30, Math.min(90, v.ram  + (Math.random() - 0.5) * 2)),
      vram: Math.max(20, Math.min(65, v.vram + (Math.random() - 0.5) * 1.5)),
    })), 3000)
    return () => clearInterval(id)
  }, [stats])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs])

  const color   = STATE_COLOR[systemState]
  const cpu     = stats?.cpu     ?? fake.cpu
  const ram     = stats?.ram     ?? fake.ram
  const vram    = stats?.vram    ?? fake.vram
  const temp    = stats?.gpuTemp ?? 62
  const gpu     = (stats?.gpuName ?? 'RTX 2070S').replace('NVIDIA GeForce ', '').replace('NVIDIA ', '')
  const uptime  = stats?.uptime  ?? 0
  const tts     = stats?.ttsBackend?.toUpperCase() ?? '—'
  const isReal  = !!stats

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>

      {/* ── Status row ── */}
      <div className="grid gap-2 mb-2" style={{ gridTemplateColumns: '1fr auto' }}>

        {/* State card */}
        <Card>
          <div className="flex items-center gap-3">
            <div style={{ position: 'relative', width: 12, height: 12, flexShrink: 0 }}>
              <div style={{
                width: '100%', height: '100%', borderRadius: '50%',
                background: color, boxShadow: `0 0 8px ${color}`,
              }} />
              {wsConnected && (
                <div className="absolute inset-0 rounded-full animate-ping"
                  style={{ background: color, opacity: 0.2 }} />
              )}
            </div>
            <div className="min-w-0">
              <div className="font-mono font-bold truncate"
                style={{ fontSize: 14, letterSpacing: '0.18em', color, textShadow: `0 0 12px ${color}44` }}>
                {STATE_LABEL[systemState]}
              </div>
              {statusMsg && (
                <div className="font-mono truncate"
                  style={{ fontSize: 8, color: '#1e3a4a', letterSpacing: '0.1em', marginTop: 1 }}>
                  {statusMsg}
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Quick pills */}
        <Card style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6, minWidth: 80 }}>
          <div className="font-mono text-right" style={{ fontSize: 8, letterSpacing: '0.1em', color: '#1e3a4a' }}>
            WS&nbsp;<span style={{ color: wsConnected ? '#00ff88' : '#ff3333' }}>{wsConnected ? 'ON' : 'OFF'}</span>
          </div>
          <div className="font-mono text-right" style={{ fontSize: 8, letterSpacing: '0.1em', color: '#1e3a4a' }}>
            TTS&nbsp;<span style={{ color: '#00f0ff66' }}>{tts}</span>
          </div>
          <div className="font-mono text-right" style={{ fontSize: 8, letterSpacing: '0.1em', color: '#1e3a4a' }}>
            {isReal ? <span style={{ color: '#00ff8866' }}>● LIVE</span> : <span>○ SIM</span>}
          </div>
        </Card>
      </div>

      {/* ── Metrics ── */}
      <Card style={{ marginBottom: 8 }}>
        <div className="flex items-center justify-between mb-3">
          <Label>MÉTRICAS DEL SISTEMA</Label>
          <span className="font-mono" style={{ fontSize: 8, color: '#1e3a4a' }}>{uptimeStr(uptime)}</span>
        </div>

        <StatBar label="CPU" value={cpu} />
        <StatBar label={`GPU  ${gpu.slice(0, 14)}`} value={vram} color="#a855f7" unit="% VRAM" />
        <StatBar label="RAM" value={ram} color="#00ff88" />

        {/* Meta row */}
        <div className="grid mt-3" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: '0 8px' }}>
          {[
            { k: 'GPU TEMP', v: `${temp}°C`,  c: temp > 80 ? '#ff3333' : temp > 70 ? '#ff8c00' : '#00f0ff66' },
            { k: 'LOCATION', v: 'LIMA, PE',   c: '#1e3a4a' },
            { k: 'MODE',     v: isReal ? 'LIVE' : 'SIM', c: isReal ? '#00ff8866' : '#1e3a4a' },
          ].map(({ k, v, c }) => (
            <div key={k}>
              <div className="font-mono" style={{ fontSize: 7, color: '#0e1e28', letterSpacing: '0.15em' }}>{k}</div>
              <div className="font-mono" style={{ fontSize: 10, color: c, marginTop: 2 }}>{v}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── System log ── */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <Label>LOG DEL SISTEMA</Label>
          <button onClick={clearLogs} className="font-mono"
            style={{ fontSize: 7, color: '#1e3a4a', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.15em' }}>
            LIMPIAR
          </button>
        </div>
        <div style={{
          height: 220, overflowY: 'auto', overflowX: 'hidden',
          background: 'rgba(0,6,12,0.8)', borderRadius: 4,
          border: '1px solid #071218', padding: '6px 8px',
        }}>
          {logs.length === 0 ? (
            <p className="font-mono" style={{ fontSize: 9, color: '#0a1e2a', letterSpacing: '0.1em' }}>
              Esperando eventos…
            </p>
          ) : logs.map((entry: LogEntry) => (
            <div key={entry.id} className="flex gap-2 font-mono" style={{ fontSize: 9, lineHeight: 1.6 }}>
              <span style={{ color: '#152530', flexShrink: 0 }}>{entry.timestamp}</span>
              <span style={{ color: LOG_COLOR[entry.level] ?? '#00f0ff', opacity: 0.75, wordBreak: 'break-word' }}>
                {entry.message}
              </span>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      </Card>

    </motion.div>
  )
}

// ── Preset selector ──────────────────────────────────────────────────────────

function PresetSelector() {
  const visualPreset    = useCYRUSStore(s => s.visualPreset)
  const setVisualPreset = useCYRUSStore(s => s.setVisualPreset)

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gap: 6,
        marginTop: 6,
      }}>
        {(Object.values(PRESETS) as typeof PRESETS[VisualPresetId][]).map((p) => {
          const active = visualPreset === p.id
          const [r, g, b] = p.palette.node
          const hex = `rgb(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)})`
          return (
            <button
              key={p.id}
              onClick={() => setVisualPreset(p.id as VisualPresetId)}
              style={{
                background: active
                  ? `rgba(${Math.round(r*255)},${Math.round(g*255)},${Math.round(b*255)},0.18)`
                  : 'rgba(0,16,32,0.6)',
                border: `1px solid ${active ? hex : '#0a2030'}`,
                borderRadius: 6,
                padding: '8px 4px',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 4,
                transition: 'all 0.2s',
              }}
            >
              <div style={{
                width: 28, height: 28,
                borderRadius: '50%',
                background: `radial-gradient(circle, ${hex} 0%, transparent 70%)`,
                boxShadow: active ? `0 0 10px ${hex}` : 'none',
              }} />
              <span style={{
                fontFamily: 'monospace',
                fontSize: 7,
                letterSpacing: '0.15em',
                color: active ? hex : '#1e3a4a',
                textTransform: 'uppercase',
              }}>
                {p.name}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 2 — CONFIG
// ═══════════════════════════════════════════════════════════════════════════

function TabConfig({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const ttsSpeed        = useCYRUSStore(s => s.ttsSpeed)
  const setTtsSpeed     = useCYRUSStore(s => s.setTtsSpeed)
  const availableModels = useCYRUSStore(s => s.availableModels)
  const currentModel    = useCYRUSStore(s => s.currentModel)
  const systemStats     = useCYRUSStore(s => s.systemStats)
  const particleCount   = useCYRUSStore(s => s.particleCount)
  const bloomIntensity  = useCYRUSStore(s => s.bloomIntensity)
  const orbSpeed        = useCYRUSStore(s => s.orbSpeed)
  const setParticleCount  = useCYRUSStore(s => s.setParticleCount)
  const setBloomIntensity = useCYRUSStore(s => s.setBloomIntensity)
  const setOrbSpeed       = useCYRUSStore(s => s.setOrbSpeed)

  const [llmModel, setLlmModel]   = useState('phi3:latest')
  const [ttsEngine, setTtsEngine] = useState('piper')
  const [testText, setTestText]   = useState('')
  const [testing, setTesting]     = useState(false)

  const commitLlm = (m: string) => { if (m.trim()) sendCommand('set_llm_model', { model: m.trim() }) }
  const commitSpeed = (v: number) => sendCommand('set_tts_speed', { speed: v })
  const refreshModels = () => sendCommand('list_ollama_models')

  const [detectorEngine, setDetectorEngine] = useState<'auto' | 'ollama'>('auto')
  const [detectorStatus, setDetectorStatus] = useState('DESCONOCIDO')
  const [voicePreset, setVoicePreset]       = useState('natural')

  const commitDetector = (engine: 'auto' | 'ollama') => {
    setDetectorEngine(engine)
    if (engine === 'auto') {
      checkDetector()
    } else {
      sendCommand('set_local_ai_detector', { detector: engine })
      setDetectorStatus('INSTALADO')
    }
  }

  const commitTtsEngine = (engine: string) => {
    setTtsEngine(engine)
    sendCommand('set_tts_engine', { engine })
  }

  const commitVoicePreset = (preset: string) => {
    setVoicePreset(preset)
    sendCommand('set_voice_preset', { preset })
  }

  const checkDetector = () => {
    setDetectorStatus('COMPROBANDO')
    sendCommand('probe_local_ai_detector', { detector: 'ollama' })
    setTimeout(() => setDetectorStatus('INSTALADO'), 1400)
  }

  useEffect(() => {
    if (detectorEngine === 'auto') {
      checkDetector()
    }
  }, [detectorEngine])

  useEffect(() => {
    sendCommand('list_ollama_models')
  }, [sendCommand])

  useEffect(() => {
    if (availableModels.length) {
      const active = currentModel || availableModels[0].name
      setLlmModel(active)
    }
  }, [availableModels, currentModel])

  useEffect(() => {
    if (currentModel && llmModel !== currentModel) {
      setLlmModel(currentModel)
    }
  }, [currentModel, llmModel])

  const testTts = () => {
    const text = testText.trim() || 'Sistema de voz CYRUS operativo.'
    setTesting(true)
    sendCommand('test_tts', { text, engine: ttsEngine, preset: voicePreset })
    setTimeout(() => setTesting(false), 3000)
  }

  const selectStyle: React.CSSProperties = {
    fontSize: 10, fontFamily: 'monospace',
    background: '#040c14', border: '1px solid #0a2030',
    color: '#00f0ffcc', borderRadius: 6,
    padding: '8px 10px', cursor: 'pointer', outline: 'none',
  }

  const actionButton: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 10, letterSpacing: '0.14em',
    padding: '10px 14px', borderRadius: 8,
    border: '1px solid #00f0ff33', background: 'rgba(0,240,255,0.07)',
    color: '#b5f7ff', cursor: 'pointer', transition: 'transform 0.2s ease, background 0.2s ease',
  }

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>

      {/* ── Detector local ── */}
      <Card style={{ marginBottom: 10, border: '1px solid #00445a', background: 'rgba(0,16,28,0.86)' }}>
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label>DETECTOR IA LOCAL</Label>
            <p className="font-mono" style={{ fontSize: 10, color: '#0f3043', marginTop: 8, lineHeight: 1.6 }}>
              Autodetección disponible para el back-end local con Ollama. Elige el modo automático para usar la conexión local cuando esté activa.
            </p>
          </div>
          <Badge
            label={detectorStatus}
            color={detectorStatus === 'INSTALADO' ? '#008272cc' : detectorStatus === 'COMPROBANDO' ? '#0f5c91cc' : '#a52a2acc'}
          />
        </div>

        <div className="grid gap-3 mt-5" style={{ gridTemplateColumns: '1.35fr auto' }}>
          <div>
            <Label dim>MOTOR LOCAL</Label>
            <select value={detectorEngine} onChange={e => commitDetector(e.target.value as 'auto' | 'ollama')} style={{ ...selectStyle, width: '100%' }}>
              <option value="auto">Autodetectar (Ollama)</option>
              <option value="ollama">Ollama local</option>
            </select>
          </div>
          <button onClick={checkDetector} style={actionButton}>
            {detectorStatus === 'COMPROBANDO' ? 'COMPROBANDO…' : 'DETECTAR'}
          </button>
        </div>

        <div style={{ marginTop: 14, padding: '12px 14px', borderRadius: 10, background: 'rgba(0,12,18,0.9)', border: '1px dashed #0a3e5d' }}>
          <p className="font-mono" style={{ fontSize: 9, color: '#00d8ff99', lineHeight: 1.6, margin: 0 }}>
            Sistemas conocidos: <strong>Whisper</strong>, <strong>VOSK</strong>, <strong>GPT4All</strong>. Selecciona el que esté instalado y disponible en el backend.
          </p>
        </div>
      </Card>

      {/* ── Síntesis de voz ── */}
      <Card style={{ marginBottom: 10, border: '1px solid #003a68', background: 'rgba(0,16,28,0.88)' }}>
        <div className="flex items-center justify-between gap-4">
          <Label>SÍNTESIS DE VOZ</Label>
          <div className="flex items-center gap-2">
            {systemStats?.ttsBackend && (
              <span className="font-mono" style={{ fontSize: 8, letterSpacing: '0.15em', color: '#00ff88cc' }}>
                ACTIVO: {systemStats.ttsBackend.toUpperCase()}
              </span>
            )}
            <Badge label="PRUEBA" color="#00a2d8cc" />
          </div>
        </div>

        <div className="grid gap-3 mt-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div>
            <Label dim>MOTOR</Label>
            <select value={ttsEngine} onChange={e => commitTtsEngine(e.target.value)} style={{ ...selectStyle, width: '100%' }}>
              <option value="piper">Piper</option>
              <option value="remote-tts">Remote TTS (servidor)</option>
              <option value="xtts">XTTS v2 (local)</option>
              <option value="kokoro">Kokoro</option>
              <option value="edge-tts">Edge TTS</option>
            </select>
          </div>
          <div>
            <Label dim>PERSONALIDAD</Label>
            <select value={voicePreset} onChange={e => commitVoicePreset(e.target.value)} style={{ ...selectStyle, width: '100%' }}>
              <option value="natural">Natural</option>
              <option value="dramatic">Dramática</option>
              <option value="suave">Suave</option>
            </select>
          </div>
        </div>

        <div className="grid gap-3 mt-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div>
            <Label dim>VELOCIDAD</Label>
            <Slider label="" value={ttsSpeed} min={0.5} max={2.0} step={0.05} onChange={setTtsSpeed} onCommit={commitSpeed} />
          </div>
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label dim>MODELO</Label>
              <button onClick={refreshModels} style={{ ...actionButton, padding: '8px 12px', fontSize: 9, background: 'rgba(0,240,255,0.10)' }}>
                REFRESCAR
              </button>
            </div>
            {availableModels.length > 0 ? (
              <div style={{ display: 'grid', gap: 6 }}>
                <select value={llmModel} onChange={e => { setLlmModel(e.target.value); commitLlm(e.target.value) }}
                  style={{ ...selectStyle, width: '100%' }}>
                  {availableModels.map(model => (
                    <option key={model.name} value={model.name}>
                      {model.name}{model.name === currentModel ? ' • ACTIVO' : ''}
                    </option>
                  ))}
                </select>
                <div className="font-mono" style={{ fontSize: 9, color: '#00d8ff99' }}>
                  Modelo activo: <strong>{currentModel || 'No seleccionado'}</strong><br />
                  {availableModels.length} modelo{availableModels.length === 1 ? '' : 's'} detectado{availableModels.length === 1 ? '' : 's'} — 
                  <span style={{
                    color: (() => {
                      const model = availableModels.find(m => m.name === llmModel)
                      if (!model) return '#ffaa00'
                      return model.compatible ? '#00ff88' : '#ff4444'
                    })(),
                    fontWeight: 'bold'
                  }}>
                    {(() => {
                      const model = availableModels.find(m => m.name === llmModel)
                      const compat = model?.compatibility ?? 'Desconocida'
                      const icon = compat.includes('GPU') ? '🖥️' : compat.includes('CPU') ? '💻' : '❓'
                      return `${icon} ${compat}`
                    })()}
                  </span>
                </div>
              </div>
            ) : (
              <div className="font-mono" style={{ fontSize: 9, color: '#00f0ff', padding: '10px 12px', borderRadius: 8, background: '#040c14', border: '1px solid #0a2030' }}>
                No se encontraron modelos. Pulsa REFRESCAR o verifica Ollama.
              </div>
            )}
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <Label dim>PRUEBA DE VOZ</Label>
          <div className="flex flex-col gap-3 mt-3" style={{ minWidth: 0 }}>
            <input
              value={testText}
              onChange={e => setTestText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && testTts()}
              placeholder="Escribe un texto para escuchar cómo suena…"
              className="font-mono rounded px-3 py-2 outline-none"
              style={{ fontSize: 10, background: '#040c14', border: '1px solid #0a2030', color: '#b5f7ff', width: '100%' }}
            />
            <div className="flex gap-2 flex-wrap">
              <button onClick={testTts} disabled={testing} style={{ ...actionButton, flex: '1 1 160px', justifyContent: 'center' }}>
                {testing ? 'REPRODUCIENDO…' : 'PROBAR VOZ'}
              </button>
              <button onClick={() => setTestText('Hola, estoy usando CYRUS con voz local.')} style={{ ...actionButton, background: 'rgba(0,255,136,0.08)' }}>
                TEXTO DE DEMO
              </button>
            </div>
          </div>
        </div>
      </Card>

      {/* ── Visualización ── */}
      <Card>
        <Label>VISUALIZACIÓN DEL HOLOGRAMA</Label>
        <div style={{ marginTop: 14 }}>
          <Slider label="BLOOM" value={bloomIntensity} min={0.5} max={2.5} step={0.05} onChange={setBloomIntensity} />
          <Slider label="PARTÍCULAS" value={particleCount} min={100} max={400} step={10} onChange={setParticleCount} />
          <Slider label="VELOCIDAD" value={orbSpeed} min={0.1} max={3.0} step={0.05} onChange={setOrbSpeed} />
        </div>
        <div style={{ marginTop: 14 }}>
          <Label>PRESET</Label>
          <PresetSelector />
        </div>
      </Card>

    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 3 — VOZ
// ═══════════════════════════════════════════════════════════════════════════

const mdComponents = {
  p:      ({ children }: any) => <p style={{ margin: '2px 0', lineHeight: 1.5 }}>{children}</p>,
  strong: ({ children }: any) => <strong style={{ color: '#00f0ffcc' }}>{children}</strong>,
  em:     ({ children }: any) => <em style={{ color: '#00f0ff99' }}>{children}</em>,
  code:   ({ children }: any) => (
    <code style={{ fontFamily: 'inherit', fontSize: '0.9em', background: 'rgba(0,100,160,0.2)', borderRadius: 2, padding: '0 3px', color: '#80d4ff' }}>
      {children}
    </code>
  ),
  ul: ({ children }: any) => <ul style={{ margin: '2px 0', paddingLeft: 14 }}>{children}</ul>,
  li: ({ children }: any) => <li style={{ margin: '1px 0' }}>{children}</li>,
}

function TabVoz({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const wakeWords     = useCYRUSStore(s => s.wakeWords)
  const logs          = useCYRUSStore(s => s.logs)
  const transcript    = useCYRUSStore(s => s.transcript)
  const enrollStep    = useCYRUSStore(s => s.enrollmentStep)
  const enrollSample  = useCYRUSStore(s => s.enrollmentSample)
  const enrollTotal   = useCYRUSStore(s => s.enrollmentTotal)
  const enrollResults = useCYRUSStore(s => s.enrollmentResults)
  const [newWord, setNewWord] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const isEnrolling = enrollStep !== 'idle' && enrollStep !== 'done'

  const asrLines = logs.filter(l => l.message.startsWith('ASR ')).slice(-5).reverse()

  const addWord = () => {
    const w = newWord.trim().toLowerCase()
    if (!w) return
    sendCommand('add_wake_word', { word: w })
    setNewWord('')
  }

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [transcript])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>

      {/* ── Enrollamiento ── */}
      <Card style={{ marginBottom: 8, border: '1px solid #00ff881a' }}>
        <div className="flex items-center justify-between mb-3">
          <Label>PERFIL DE VOZ</Label>
          {enrollStep === 'done' && (
            <span className="font-mono" style={{ fontSize: 8, color: '#00ff8877', letterSpacing: '0.15em' }}>✓ ACTIVO</span>
          )}
        </div>

        <p className="font-mono mb-3" style={{ fontSize: 9, color: '#1e3a4a', lineHeight: 1.6 }}>
          Graba {enrollTotal} muestras de tu voz para que CYRUS solo responda a ti
          y el barge-in no se active con otros sonidos.
        </p>

        {/* Progress */}
        {isEnrolling && (
          <div className="mb-3">
            <div className="flex justify-between mb-1.5">
              <span className="font-mono" style={{ fontSize: 9, color: '#00ff88' }}>
                {enrollStep === 'prompt' ? `Escuchando muestra ${enrollSample}…` : 'Procesando…'}
              </span>
              <span className="font-mono" style={{ fontSize: 9, color: '#00ff8866' }}>
                {enrollSample}/{enrollTotal}
              </span>
            </div>
            <div style={{ height: 3, background: '#071218', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{
                height: '100%', borderRadius: 2,
                width: `${(enrollSample / enrollTotal) * 100}%`,
                background: 'linear-gradient(90deg, #00ff8844, #00ff88)',
                transition: 'width 0.4s ease',
              }} />
            </div>
            <div className="flex flex-wrap gap-1 mt-2">
              {enrollResults.map((r, i) => (
                <span key={i} className="font-mono rounded px-1.5 py-0.5"
                  style={{ fontSize: 8, background: '#001810', border: '1px solid #00ff8820', color: '#00ff8866' }}>
                  {r || '(silencio)'}
                </span>
              ))}
            </div>
          </div>
        )}

        {enrollStep === 'done' && (
          <div className="mb-3 rounded p-2" style={{ background: '#001810', border: '1px solid #00ff8825' }}>
            <p className="font-mono" style={{ fontSize: 9, color: '#00ff8899' }}>Perfil guardado — barge-in personalizado activo</p>
          </div>
        )}

        <button
          disabled={isEnrolling}
          onClick={() => sendCommand('start_enrollment', { samples: 5 })}
          className="font-mono w-full rounded py-2"
          style={{
            fontSize: 10, letterSpacing: '0.18em',
            background: isEnrolling ? 'transparent' : '#00ff8815',
            border: `1px solid ${isEnrolling ? '#00ff8815' : '#00ff8855'}`,
            color: isEnrolling ? '#00ff8833' : '#00ff88',
            cursor: isEnrolling ? 'not-allowed' : 'pointer',
          }}
        >
          {isEnrolling ? `GRABANDO ${enrollSample}/${enrollTotal}…` : 'INICIAR ENROLLAMIENTO'}
        </button>
      </Card>

      {/* ── Palabras activas + ASR ── */}
      <Card style={{ marginBottom: 8 }}>
        <Label>PALABRAS ACTIVAS</Label>

        {/* Wake words chips */}
        <div className="flex flex-wrap gap-1.5 mt-3 mb-4" style={{ minHeight: 28 }}>
          {wakeWords.length === 0
            ? <span className="font-mono" style={{ fontSize: 9, color: '#0e1e28' }}>Cargando…</span>
            : wakeWords.map(w => (
              <span key={w} className="font-mono rounded px-2 py-1 cursor-pointer"
                style={{
                  fontSize: 9, background: '#001828',
                  border: '1px solid #00f0ff1a', color: '#00f0ff55',
                  transition: 'border-color 0.15s, color 0.15s',
                }}
                onClick={() => sendCommand('remove_wake_word', { word: w })}>
                {w} ×
              </span>
            ))
          }
        </div>

        <Divider />

        {/* Manual add */}
        <div className="flex gap-2 mt-3 mb-3">
          <input value={newWord} onChange={e => setNewWord(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addWord()}
            placeholder="agregar variante…"
            className="font-mono flex-1 rounded px-2 py-1 outline-none"
            style={{ fontSize: 10, background: '#040c14', border: '1px solid #0a2030', color: '#00f0ff77' }}
          />
          <button onClick={addWord} className="font-mono rounded px-3"
            style={{ fontSize: 9, background: '#00f0ff0d', border: '1px solid #00f0ff22', color: '#00f0ff66', cursor: 'pointer' }}>
            + ADD
          </button>
        </div>

        {/* Recent ASR */}
        {asrLines.length > 0 && (
          <>
            <Label dim>TRANSCRIPCIONES RECIENTES — clic para agregar</Label>
            <div style={{ marginTop: 6, background: '#040c14', borderRadius: 4, border: '1px solid #071218', padding: '6px 8px' }}>
              {asrLines.map(l => {
                const m = l.message.match(/"([^"]+)"/)
                const word = m?.[1] ?? ''
                return (
                  <div key={l.id} className="flex gap-2 font-mono"
                    onClick={() => word && setNewWord(word)}
                    style={{ fontSize: 9, lineHeight: 1.6, cursor: word ? 'pointer' : 'default' }}>
                    <span style={{ color: '#152530', flexShrink: 0 }}>{l.timestamp}</span>
                    <span style={{ color: '#00ff8866' }}>{l.message}</span>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </Card>

      {/* ── Historial ── */}
      {transcript.length > 0 && (
        <Card>
          <Label>HISTORIAL DE CONVERSACIÓN</Label>
          <div style={{ marginTop: 10, maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {transcript.map(entry => (
              <div key={entry.id} style={{ display: 'flex', flexDirection: 'column', alignItems: entry.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <span className="font-mono" style={{ fontSize: 8, color: '#152530', letterSpacing: '0.18em', marginBottom: 3 }}>
                  {entry.role === 'user' ? 'TÚ' : 'CYRUS'}{' '}
                  {entry.timestamp.toLocaleTimeString('es-PE', { hour12: false })}
                </span>
                <div className="font-mono rounded px-3 py-1.5"
                  style={{
                    fontSize: 10, maxWidth: '90%', lineHeight: 1.5,
                    ...(entry.role === 'user'
                      ? { background: 'rgba(0,80,130,0.25)', border: '1px solid #0a3a55', color: '#70b8d8' }
                      : { background: 'rgba(0,30,60,0.5)',  border: '1px solid #0a2840', color: '#a0d8f0' }),
                  }}>
                  {entry.role === 'cyrus'
                    ? <ReactMarkdown components={mdComponents}>{entry.text}</ReactMarkdown>
                    : entry.text}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        </Card>
      )}

    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 4 — API
// ═══════════════════════════════════════════════════════════════════════════

function TabAPI({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const serviceStatus = useCYRUSStore(s => s.serviceStatus)

  useEffect(() => {
    sendCommand('probe_services')
  }, [sendCommand])

  const services: { key: keyof ServiceStatus; label: string; port: string }[] = [
    { key: 'tts',      label: 'TTS Server',    port: '8020' },
    { key: 'asr',      label: 'ASR Server',    port: '8000' },
    { key: 'vision',   label: 'Vision Server', port: '8001' },
    { key: 'embedder', label: 'Embedder',       port: '8002' },
  ]

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>

      <Card style={{ marginBottom: 10, border: '1px solid #003a5a', background: 'rgba(0,14,26,0.9)' }}>
        <div className="flex items-center justify-between gap-4 mb-4">
          <Label>SERVICIOS API</Label>
          <button
            onClick={() => sendCommand('probe_services')}
            style={{
              fontSize: 9, letterSpacing: '0.14em', fontFamily: 'monospace',
              padding: '6px 12px', borderRadius: 6,
              border: '1px solid #00f0ff33', background: 'rgba(0,240,255,0.07)',
              color: '#b5f7ff', cursor: 'pointer',
            }}
          >
            COMPROBAR
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {services.map(({ key, label, port }) => {
            const info = serviceStatus?.[key]
            const isActive    = info?.enabled && info?.online
            const isAvailable = !info?.enabled && info?.online
            const isOffline   = info?.enabled && !info?.online
            const dotColor = !info ? '#2a3a4a'
              : isActive    ? '#00ff88'
              : isAvailable ? '#ffaa00'
              : isOffline   ? '#ff4444'
              : '#2a3a4a'
            const statusLabel = !info ? 'DESCONOCIDO'
              : isActive    ? 'ACTIVO'
              : isAvailable ? 'DISPONIBLE'
              : isOffline   ? 'OFFLINE'
              : 'DESACTIVADO'
            const statusColor = !info ? '#1e3a4acc'
              : isActive    ? '#008272cc'
              : isAvailable ? '#7a5a00cc'
              : isOffline   ? '#8b1a1acc'
              : '#1e3a4acc'
            const host = info?.host ?? `http://localhost:${port}`

            return (
              <div key={key} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px', borderRadius: 6,
                background: 'rgba(0,8,16,0.6)', border: '1px solid #071828',
              }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: dotColor, flexShrink: 0,
                  boxShadow: info?.online ? `0 0 6px ${dotColor}` : 'none',
                }} />
                <span className="font-mono" style={{ fontSize: 9, color: '#7ab8cc', letterSpacing: '0.12em', minWidth: 94 }}>
                  {label}
                </span>
                <span className="font-mono" style={{ fontSize: 8, color: '#1e3a4a', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {host}
                </span>
                <span className="font-mono" style={{
                  fontSize: 7, letterSpacing: '0.18em',
                  padding: '3px 8px', borderRadius: 999,
                  background: statusColor, color: '#e8f8ff',
                  flexShrink: 0,
                }}>
                  {statusLabel}
                </span>
              </div>
            )
          })}
        </div>

        <p className="font-mono" style={{ fontSize: 8, color: '#1e3a4a', marginTop: 10, lineHeight: 1.6 }}>
          {!serviceStatus
            ? 'Pulsa COMPROBAR para verificar el estado de los servicios'
            : 'DISPONIBLE = servidor activo pero desactivado en config.yaml · ACTIVO = en uso por CYRUS'}
        </p>
      </Card>

      {/* ── Port reference ── */}
      <Card style={{ border: '1px solid #001a2a', background: 'rgba(0,10,20,0.85)' }}>
        <Label>REFERENCIA DE PUERTOS</Label>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {[
            { port: '8020', service: 'TTS Server',    cmd: 'services/tts_server/start.bat',      note: 'Kokoro / Piper' },
            { port: '8000', service: 'ASR Server',    cmd: 'services/asr_server/start.bat',      note: 'faster-whisper' },
            { port: '8001', service: 'Vision Server', cmd: 'services/vision_server/start.bat',   note: 'YOLO + DeepFace' },
            { port: '8002', service: 'Embedder',      cmd: 'services/embedder_server/start.bat', note: 'sentence-transformers' },
          ].map(({ port, service, cmd, note }) => (
            <div key={port} style={{ display: 'grid', gridTemplateColumns: '40px 90px 1fr', gap: 8, alignItems: 'start' }}>
              <span className="font-mono" style={{ fontSize: 9, color: '#00f0ff55' }}>{port}</span>
              <span className="font-mono" style={{ fontSize: 9, color: '#4a8a9a' }}>{service}</span>
              <div>
                <div className="font-mono" style={{ fontSize: 8, color: '#1e3a4a', wordBreak: 'break-all' }}>{cmd}</div>
                <div className="font-mono" style={{ fontSize: 7, color: '#0e2230', marginTop: 1 }}>{note}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// ROOT
// ═══════════════════════════════════════════════════════════════════════════

export function ControlView() {
  const navigate = useNavigate()
  const { sendCommand } = useWebSocket()
  const [tab, setTab] = useState<Tab>('SISTEMA')

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); navigate('/') }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  return (
    <motion.div
      initial={{ opacity: 0, filter: 'blur(8px)' }}
      animate={{ opacity: 1, filter: 'blur(0px)' }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="page-scroll"
      style={{ background: '#03050a', minHeight: '100vh' }}
    >
      <div className="mx-auto px-4 pb-12" style={{ maxWidth: 520 }}>

        {/* ── Header ── */}
        <div className="flex items-center justify-between py-4 mb-3 sticky top-0"
          style={{ background: '#03050a', zIndex: 10, borderBottom: '1px solid #081820' }}>
          <button onClick={() => navigate('/')} className="font-mono"
            style={{ fontSize: 10, color: '#00f0ff44', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.2em' }}>
            ← BACK
            <span style={{ fontSize: 7, color: '#00f0ff1a', marginLeft: 6 }}>ESC</span>
          </button>
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold"
              style={{ fontSize: 13, letterSpacing: '0.4em', color: '#00f0ff', textShadow: '0 0 14px #00f0ff33' }}>
              C.Y.R.U.S
            </span>
            <span className="font-mono" style={{ fontSize: 8, color: '#00f0ff22', letterSpacing: '0.12em' }}>CONTROL</span>
          </div>
          <div style={{ width: 70 }} />
        </div>

        {/* ── Tabs ── */}
        <TabBar active={tab} onChange={setTab} />

        {/* ── Content ── */}
        <AnimatePresence mode="wait">
          {tab === 'SISTEMA' && <TabSistema key="sistema" />}
          {tab === 'CONFIG'  && <TabConfig  key="config"  sendCommand={sendCommand} />}
          {tab === 'VOZ'     && <TabVoz     key="voz"     sendCommand={sendCommand} />}
          {tab === 'API'     && <TabAPI     key="api"     sendCommand={sendCommand} />}
        </AnimatePresence>

        {/* ── Footer ── */}
        <div className="text-center mt-6">
          <span className="font-mono" style={{ fontSize: 7, color: '#06101a', letterSpacing: '0.2em' }}>
            C.Y.R.U.S v1.0 — COGNITIVE SYSTEM FOR REAL-TIME UTILITY & SERVICES
          </span>
        </div>

      </div>
    </motion.div>
  )
}
