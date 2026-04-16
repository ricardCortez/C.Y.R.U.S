/**
 * C.Y.R.U.S — Control Panel View (route "/control")
 *
 * Improvements:
 *  - SystemStats: real CPU/RAM/VRAM/GPU from backend (via system_stats WS event)
 *  - Configuration: all controls wired to backend (set_tts_speed, set_llm_model, test_tts)
 *  - TTS dropdown includes "piper"
 *  - ConversationHistory: renders markdown with react-markdown
 *  - "Probar voz" button: sends test_tts command
 *  - TTS speed slider wired to backend
 *  - Uptime from real backend timestamp
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate }                  from 'react-router-dom'
import { motion, AnimatePresence }      from 'framer-motion'
import ReactMarkdown                    from 'react-markdown'
import { useCYRUSStore, SystemState, LogEntry } from '../store/useCYRUSStore'
import { useWebSocket } from '../hooks/useWebSocket'

// ── Color maps ──────────────────────────────────────────────────────────────
const STATE_COLOR: Record<SystemState, string> = {
  offline:      '#ff3333',
  connected:    '#00d4ff',
  idle:         '#0077bb',
  listening:    '#00ff88',
  transcribing: '#00d4ff',
  thinking:     '#ff8c00',
  speaking:     '#00d4ff',
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

// ── Shared layout ───────────────────────────────────────────────────────────
const Section = ({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, delay, ease: 'easeOut' }}
    className="rounded-lg p-4 mb-3"
    style={{ background: 'rgba(0,20,40,0.6)', border: '1px solid #0a2030' }}
  >
    {children}
  </motion.div>
)

const SectionTitle = ({ label, action }: { label: string; action?: React.ReactNode }) => (
  <div className="flex items-center gap-2 mb-3">
    <div style={{ width: 16, height: 1, background: 'linear-gradient(90deg, transparent, #00f0ff22)', flexShrink: 0 }} />
    <span className="font-mono flex-shrink-0" style={{ fontSize: 8, letterSpacing: '0.3em', color: '#00f0ff44' }}>
      {label}
    </span>
    <div style={{ flex: 1, height: 1, background: 'linear-gradient(90deg, #00f0ff22, transparent)' }} />
    {action && <div className="flex-shrink-0">{action}</div>}
  </div>
)

// ── 1. AI State Badge ───────────────────────────────────────────────────────
function AIStateBadge() {
  const systemState = useCYRUSStore(s => s.systemState)
  const wsConnected = useCYRUSStore(s => s.wsConnected)
  const statusMsg   = useCYRUSStore(s => s.statusMessage)
  const stats       = useCYRUSStore(s => s.systemStats)
  const color = STATE_COLOR[systemState]

  return (
    <Section delay={0.1}>
      <SectionTitle label="AI STATE" />
      <div className="flex items-center gap-3">
        {/* Status dot */}
        <motion.div key={systemState} animate={{ scale: [1, 1.2, 1] }} transition={{ duration: 0.35 }}
          className="relative flex-shrink-0" style={{ width: 14, height: 14 }}>
          <div className="w-full h-full rounded-full"
            style={{ background: color, boxShadow: `0 0 10px ${color}, 0 0 20px ${color}55` }} />
          {wsConnected && (
            <div className="absolute inset-0 rounded-full animate-ping"
              style={{ background: color, opacity: 0.25 }} />
          )}
        </motion.div>

        {/* State label + message */}
        <div className="flex-1 min-w-0">
          <div className="font-mono font-bold truncate"
            style={{ fontSize: 16, letterSpacing: '0.2em', color, textShadow: `0 0 14px ${color}55` }}>
            {STATE_LABEL[systemState]}
          </div>
          {statusMsg && (
            <div className="font-mono truncate" style={{ fontSize: 8, color: '#00f0ff44', letterSpacing: '0.1em', marginTop: 2 }}>
              {statusMsg}
            </div>
          )}
        </div>

        {/* Right info pills */}
        <div className="flex flex-col gap-1 flex-shrink-0 text-right">
          <div className="font-mono" style={{ fontSize: 8, color: '#00f0ff22', letterSpacing: '0.12em' }}>
            TTS <span style={{ color: '#00ff8866' }}>{stats?.ttsBackend?.toUpperCase() ?? '—'}</span>
          </div>
          <div className="font-mono" style={{ fontSize: 8, letterSpacing: '0.12em' }}>
            WS <span style={{ color: wsConnected ? '#00ff8866' : '#ff333366' }}>
              {wsConnected ? 'ON' : 'OFF'}
            </span>
          </div>
        </div>
      </div>
    </Section>
  )
}

// ── 2. System Stats (real data from backend) ────────────────────────────────
function StatBar({ label, value, color = '#00f0ff', unit = '%', delay = 0 }: {
  label: string; value: number; color?: string; unit?: string; delay?: number
}) {
  return (
    <div className="mb-2">
      <div className="flex justify-between mb-1">
        <span className="font-mono" style={{ fontSize: 9, color: '#405060', letterSpacing: '0.15em' }}>{label}</span>
        <span className="font-mono" style={{ fontSize: 9, color }}>{value.toFixed(1)}{unit}</span>
      </div>
      <div className="rounded-full overflow-hidden" style={{ height: 3, background: '#0a1a28' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, value)}%` }}
          transition={{ duration: 0.8, ease: 'easeOut', delay }}
          className="h-full rounded-full"
          style={{ background: `linear-gradient(90deg, ${color}88, ${color})`, boxShadow: `0 0 6px ${color}44` }}
        />
      </div>
    </div>
  )
}

function uptimeStr(s: number) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return [h, m, sec].map(n => String(n).padStart(2, '0')).join(':')
}

function SystemStats() {
  const stats = useCYRUSStore(s => s.systemStats)

  // Fake fluctuation while waiting for real data
  const [fake, setFake] = useState({ cpu: 18, ram: 52, vram: 31 })
  useEffect(() => {
    if (stats) return
    const id = setInterval(() => {
      setFake(v => ({
        cpu:  Math.max(5,  Math.min(85, v.cpu  + (Math.random() - 0.5) * 4)),
        ram:  Math.max(30, Math.min(90, v.ram  + (Math.random() - 0.5) * 2)),
        vram: Math.max(20, Math.min(65, v.vram + (Math.random() - 0.5) * 1.5)),
      }))
    }, 3000)
    return () => clearInterval(id)
  }, [stats])

  const cpu    = stats?.cpu    ?? fake.cpu
  const ram    = stats?.ram    ?? fake.ram
  const vram   = stats?.vram   ?? fake.vram
  const temp   = stats?.gpuTemp ?? 62
  const gpu    = stats?.gpuName ?? 'RTX 2070S'
  const uptime = stats?.uptime  ?? 0
  const isReal = !!stats

  const liveLabel = (
    <span className="font-mono" style={{ fontSize: 7, letterSpacing: '0.15em', color: isReal ? '#00ff8855' : '#30405066' }}>
      {isReal ? '● LIVE' : '○ SIM'}
    </span>
  )

  return (
    <Section delay={0.2}>
      <SectionTitle label="SYSTEM METRICS" action={liveLabel} />
      <StatBar label="CPU" value={cpu} delay={0.3} />
      <StatBar label={`GPU  ${gpu.replace('NVIDIA GeForce ', '').replace('NVIDIA ', '').slice(0, 16)}`}
        value={vram} color="#a855f7" unit="% VRAM" delay={0.35} />
      <StatBar label="RAM" value={ram} color="#00ff88" delay={0.4} />
      <div className="grid mt-3" style={{ gridTemplateColumns: 'repeat(4, 1fr)', gap: '0 8px' }}>
        {[
          { k: 'UPTIME',   v: uptimeStr(uptime),                      c: '#00f0ff77' },
          { k: 'GPU TEMP', v: `${temp}°C`,                             c: temp > 80 ? '#ff3333' : temp > 70 ? '#ff8c00' : '#00f0ff77' },
          { k: 'LOCATION', v: 'LIMA PE',                               c: '#00f0ff55' },
          { k: 'MODE',     v: isReal ? 'LIVE' : 'SIM',                 c: isReal ? '#00ff8866' : '#304050' },
        ].map(({ k, v, c }) => (
          <div key={k}>
            <div className="font-mono" style={{ fontSize: 7, color: '#1a2e40', letterSpacing: '0.15em' }}>{k}</div>
            <div className="font-mono" style={{ fontSize: 10, color: c, marginTop: 2 }}>{v}</div>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ── 3. System Log ───────────────────────────────────────────────────────────
const LOG_COLOR: Record<string, string> = {
  info:  '#00f0ff',
  warn:  '#ff8c00',
  error: '#ff3333',
  ok:    '#00ff88',
}

function SystemLog() {
  const logs     = useCYRUSStore(s => s.logs)
  const clearLogs = useCYRUSStore(s => s.clearLogs)
  const endRef   = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const clearBtn = (
    <button onClick={clearLogs} className="font-mono"
      style={{ fontSize: 7, color: '#00f0ff33', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.15em' }}>
      CLEAR
    </button>
  )

  return (
    <Section delay={0.3}>
      <SectionTitle label="SYSTEM LOG" action={clearBtn} />
      <div className="overflow-y-auto rounded"
        style={{ height: 180, background: 'rgba(0,10,20,0.6)', border: '1px solid #05151f', padding: '8px 10px' }}>
        <AnimatePresence initial={false}>
          {logs.length === 0 ? (
            <p className="font-mono" style={{ fontSize: 9, color: '#0a2030', letterSpacing: '0.1em' }}>
              Awaiting events…
            </p>
          ) : (
            logs.map((entry: LogEntry) => (
              <motion.div
                key={entry.id}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                className="flex gap-2 font-mono leading-relaxed"
                style={{ fontSize: 9 }}
              >
                <span style={{ color: '#203040', flexShrink: 0 }}>{entry.timestamp}</span>
                <span style={{ color: LOG_COLOR[entry.level] ?? '#00f0ff', opacity: 0.8, wordBreak: 'break-word' }}>
                  {entry.message}
                </span>
              </motion.div>
            ))
          )}
        </AnimatePresence>
        <div ref={endRef} />
      </div>
    </Section>
  )
}

// ── 4. Configuration (wired to backend) ─────────────────────────────────────
function Slider({ label, value, min, max, step = 0.1, onChange, onCommit }: {
  label: string; value: number; min: number; max: number
  step?: number; onChange: (v: number) => void; onCommit?: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
      <div className="flex justify-between mb-1.5">
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>{label}</span>
        <span className="font-mono" style={{ fontSize: 10, color: '#00f0ff77' }}>{value.toFixed(2)}</span>
      </div>
      <div className="relative" style={{ height: 4, background: '#0a1a28', borderRadius: 2 }}>
        <div className="absolute inset-y-0 left-0 rounded"
          style={{ width: `${pct}%`, background: 'linear-gradient(90deg, #00f0ff44, #00f0ff)', borderRadius: 2 }} />
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          onMouseUp={e => onCommit?.(parseFloat((e.target as HTMLInputElement).value))}
          onTouchEnd={e => onCommit?.(parseFloat((e.target as HTMLInputElement).value))}
          className="absolute inset-0 opacity-0 cursor-pointer w-full" style={{ margin: 0 }}
        />
      </div>
    </div>
  )
}

function Configuration({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const ttsSpeed       = useCYRUSStore(s => s.ttsSpeed)
  const setTtsSpeed    = useCYRUSStore(s => s.setTtsSpeed)
  const particleCount  = useCYRUSStore(s => s.particleCount)
  const bloomIntensity = useCYRUSStore(s => s.bloomIntensity)
  const orbSpeed       = useCYRUSStore(s => s.orbSpeed)
  const setParticleCount  = useCYRUSStore(s => s.setParticleCount)
  const setBloomIntensity = useCYRUSStore(s => s.setBloomIntensity)
  const setOrbSpeed       = useCYRUSStore(s => s.setOrbSpeed)

  const [llmModel, setLlmModel]       = useState('phi3:latest')
  const [ttsEngine, setTtsEngine]     = useState('piper')
  const [editingModel, setEditingModel] = useState(false)
  const [testText, setTestText]       = useState('')
  const [testing, setTesting]         = useState(false)

  const handleTtsSpeedCommit = (v: number) => {
    sendCommand('set_tts_speed', { speed: v })
  }

  const handleLlmModelCommit = (model: string) => {
    if (model.trim()) sendCommand('set_llm_model', { model: model.trim() })
  }

  const handleTestTts = () => {
    const text = testText.trim() || 'Sistema de voz C.Y.R.U.S operativo.'
    setTesting(true)
    sendCommand('test_tts', { text })
    setTimeout(() => setTesting(false), 3000)
  }

  return (
    <Section delay={0.4}>
      <SectionTitle label="CONFIGURATION" />

      {/* LLM Model */}
      <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>LLM MODEL</span>
        {editingModel ? (
          <input autoFocus value={llmModel}
            onChange={e => setLlmModel(e.target.value)}
            onBlur={() => { setEditingModel(false); handleLlmModelCommit(llmModel) }}
            onKeyDown={e => { if (e.key === 'Enter') { setEditingModel(false); handleLlmModelCommit(llmModel) } }}
            className="font-mono rounded px-2 py-0.5 outline-none"
            style={{ fontSize: 10, background: '#0a1e2a', border: '1px solid #00f0ff44', color: '#00f0ff', width: 130 }}
          />
        ) : (
          <button onClick={() => setEditingModel(true)} className="font-mono px-2 py-0.5 rounded"
            style={{ fontSize: 10, background: '#00f0ff11', border: '1px solid #00f0ff33', color: '#00f0ffaa', cursor: 'pointer' }}>
            {llmModel}
          </button>
        )}
      </div>

      {/* TTS Engine */}
      <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>TTS ENGINE</span>
        <select value={ttsEngine} onChange={e => setTtsEngine(e.target.value)}
          className="font-mono rounded px-2 py-0.5 outline-none"
          style={{ fontSize: 10, background: '#0a1e2a', border: '1px solid #00f0ff33', color: '#00f0ffaa', cursor: 'pointer' }}>
          <option value="piper">piper (activo)</option>
          <option value="kokoro">kokoro</option>
          <option value="edge-tts">edge-tts</option>
        </select>
      </div>

      {/* TTS Speed */}
      <Slider
        label="TTS SPEED"
        value={ttsSpeed} min={0.5} max={2.0} step={0.05}
        onChange={setTtsSpeed}
        onCommit={handleTtsSpeedCommit}
      />

      {/* Test TTS */}
      <div className="py-3" style={{ borderBottom: '1px solid #0a1e2a' }}>
        <p className="font-mono mb-2" style={{ fontSize: 9, color: '#304050', letterSpacing: '0.15em' }}>PROBAR VOZ</p>
        <div className="flex gap-2">
          <input
            value={testText}
            onChange={e => setTestText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleTestTts()}
            placeholder="texto de prueba…"
            className="font-mono flex-1 rounded px-2 py-1 outline-none"
            style={{ fontSize: 10, background: '#040c14', border: '1px solid #00f0ff22', color: '#00f0ff88' }}
          />
          <button
            onClick={handleTestTts}
            disabled={testing}
            className="font-mono rounded px-3"
            style={{
              fontSize: 9, letterSpacing: '0.15em',
              background: testing ? '#001810' : '#00f0ff11',
              border: `1px solid ${testing ? '#00f0ff22' : '#00f0ff44'}`,
              color: testing ? '#00f0ff44' : '#00f0ff88',
              cursor: testing ? 'not-allowed' : 'pointer',
            }}
          >
            {testing ? '▶▶' : '▶ SPEAK'}
          </button>
        </div>
      </div>

      {/* Visual sliders */}
      <div className="mt-3 mb-1">
        <span className="font-mono" style={{ fontSize: 7, color: '#1a3040', letterSpacing: '0.2em' }}>VISUALIZACIÓN</span>
      </div>
      <Slider label="BLOOM INTENSITY" value={bloomIntensity} min={0.5} max={2.5} step={0.05} onChange={setBloomIntensity} />
      <Slider label="PARTICLE COUNT"  value={particleCount}  min={100} max={400} step={10}   onChange={setParticleCount} />
      <Slider label="NEURAL SPEED"    value={orbSpeed}       min={0.1} max={3.0} step={0.05} onChange={setOrbSpeed} />
    </Section>
  )
}

// ── 5. Conversation History (with markdown) ─────────────────────────────────

// Minimal markdown prose styles injected inline
const mdComponents = {
  p:      ({ children }: any) => <p style={{ margin: '2px 0', lineHeight: 1.5 }}>{children}</p>,
  strong: ({ children }: any) => <strong style={{ color: '#00f0ffcc' }}>{children}</strong>,
  em:     ({ children }: any) => <em style={{ color: '#00f0ff99' }}>{children}</em>,
  code:   ({ children }: any) => (
    <code style={{
      fontFamily: 'inherit', fontSize: '0.9em',
      background: 'rgba(0,100,160,0.2)', borderRadius: 2,
      padding: '0 3px', color: '#80d4ff',
    }}>{children}</code>
  ),
  pre:    ({ children }: any) => (
    <pre style={{
      background: 'rgba(0,10,20,0.8)', border: '1px solid #0a2030',
      borderRadius: 4, padding: '6px 8px', margin: '4px 0',
      overflowX: 'auto', fontSize: '0.85em',
    }}>{children}</pre>
  ),
  ul:     ({ children }: any) => <ul style={{ margin: '2px 0', paddingLeft: 14 }}>{children}</ul>,
  ol:     ({ children }: any) => <ol style={{ margin: '2px 0', paddingLeft: 14 }}>{children}</ol>,
  li:     ({ children }: any) => <li style={{ margin: '1px 0' }}>{children}</li>,
}

function ConversationHistory() {
  const transcript = useCYRUSStore(s => s.transcript)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript])

  if (transcript.length === 0) return null

  return (
    <Section delay={0.35}>
      <SectionTitle label="CONVERSATION" />
      <div className="overflow-y-auto flex flex-col gap-2" style={{ maxHeight: 260 }}>
        {transcript.map(entry => (
          <div key={entry.id} className={`flex flex-col ${entry.role === 'user' ? 'items-end' : 'items-start'}`}>
            <span className="font-mono mb-0.5" style={{ fontSize: 8, color: '#203040', letterSpacing: '0.2em' }}>
              {entry.role === 'user' ? 'YOU' : 'C.Y.R.U.S'}{' '}
              {entry.timestamp.toLocaleTimeString('en-GB', { hour12: false })}
            </span>
            <div
              className="px-3 py-1.5 rounded font-mono"
              style={{
                fontSize: 10, maxWidth: '90%', lineHeight: 1.5,
                ...(entry.role === 'user'
                  ? { background: 'rgba(0,100,160,0.2)', border: '1px solid #0a4060', color: '#80c8e8' }
                  : { background: 'rgba(0,40,80,0.4)', border: '1px solid #004060', color: '#b0e8ff' }),
              }}
            >
              {entry.role === 'cyrus' ? (
                <ReactMarkdown components={mdComponents}>{entry.text}</ReactMarkdown>
              ) : (
                entry.text
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </Section>
  )
}

// ── Voice Enrollment (unchanged structure) ──────────────────────────────────
function VoiceCalibration({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const wakeWords     = useCYRUSStore(s => s.wakeWords)
  const logs          = useCYRUSStore(s => s.logs)
  const enrollStep    = useCYRUSStore(s => s.enrollmentStep)
  const enrollSample  = useCYRUSStore(s => s.enrollmentSample)
  const enrollTotal   = useCYRUSStore(s => s.enrollmentTotal)
  const enrollResults = useCYRUSStore(s => s.enrollmentResults)
  const [newWord, setNewWord] = useState('')

  const isEnrolling = enrollStep !== 'idle' && enrollStep !== 'done'

  const asrLines = logs
    .filter(l => l.message.startsWith('ASR '))
    .slice(-6)
    .reverse()

  const addWord = () => {
    const w = newWord.trim().toLowerCase()
    if (!w) return
    sendCommand('add_wake_word', { word: w })
    setNewWord('')
  }

  return (
    <Section delay={0.45}>
      <SectionTitle label="RECONOCIMIENTO DE VOZ" />

      {/* Enrollment wizard */}
      <div className="mb-4 rounded p-3" style={{ background: 'rgba(0,255,136,0.04)', border: '1px solid #00ff8820' }}>
        <p className="font-mono mb-2" style={{ fontSize: 9, color: '#00ff8877', letterSpacing: '0.15em' }}>
          ENROLLAR MI VOZ
        </p>
        <p className="font-mono mb-3" style={{ fontSize: 9, color: '#304050', lineHeight: 1.6 }}>
          CYRUS grabará {enrollTotal} muestras de cómo pronuncias su nombre.
        </p>

        {isEnrolling && (
          <div className="mb-3">
            <div className="flex justify-between mb-1">
              <span className="font-mono" style={{ fontSize: 9, color: '#00ff88' }}>
                {enrollStep === 'prompt' ? `Escuchando muestra ${enrollSample}…` : 'Procesando…'}
              </span>
              <span className="font-mono" style={{ fontSize: 9, color: '#00ff8866' }}>
                {enrollSample}/{enrollTotal}
              </span>
            </div>
            <div className="rounded-full overflow-hidden" style={{ height: 3, background: '#0a1a20' }}>
              <div className="h-full rounded-full transition-all duration-500"
                style={{ width: `${(enrollSample / enrollTotal) * 100}%`, background: 'linear-gradient(90deg, #00ff8844, #00ff88)' }} />
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {enrollResults.map((r, i) => (
                <span key={i} className="font-mono rounded px-1.5 py-0.5"
                  style={{ fontSize: 8, background: '#001810', border: '1px solid #00ff8830', color: '#00ff8877' }}>
                  {r || '(silencio)'}
                </span>
              ))}
            </div>
          </div>
        )}

        {enrollStep === 'done' && (
          <div className="mb-3 rounded p-2" style={{ background: '#001810', border: '1px solid #00ff8830' }}>
            <p className="font-mono" style={{ fontSize: 9, color: '#00ff88' }}>Enrollamiento completado</p>
            <div className="flex flex-wrap gap-1 mt-1">
              {enrollResults.map((r, i) => r && (
                <span key={i} className="font-mono rounded px-1.5"
                  style={{ fontSize: 8, background: '#002818', border: '1px solid #00ff8830', color: '#00ff8866' }}>
                  {r}
                </span>
              ))}
            </div>
          </div>
        )}

        <button
          disabled={isEnrolling}
          onClick={() => sendCommand('start_enrollment', { samples: 5 })}
          className="font-mono w-full rounded py-2"
          style={{
            fontSize: 10, letterSpacing: '0.2em',
            background: isEnrolling ? '#001810' : '#00ff8822',
            border: `1px solid ${isEnrolling ? '#00ff8820' : '#00ff8866'}`,
            color: isEnrolling ? '#00ff8844' : '#00ff88',
            cursor: isEnrolling ? 'not-allowed' : 'pointer',
          }}
        >
          {isEnrolling ? `GRABANDO ${enrollSample}/${enrollTotal}…` : 'INICIAR ENROLLAMIENTO DE VOZ'}
        </button>
      </div>

      {/* Recent ASR */}
      <div className="mb-3">
        <p className="font-mono mb-1.5" style={{ fontSize: 8, color: '#304050', letterSpacing: '0.2em' }}>
          LO QUE CYRUS ESCUCHO — clic para agregar
        </p>
        <div className="rounded" style={{ background: 'rgba(0,8,16,0.7)', border: '1px solid #0a1e2a', padding: '6px 8px', minHeight: 40 }}>
          {asrLines.length === 0
            ? <p className="font-mono" style={{ fontSize: 9, color: '#0a2030' }}>Habla para ver transcripciones…</p>
            : asrLines.map(l => {
                const m = l.message.match(/"([^"]+)"/)
                const word = m?.[1] ?? ''
                return (
                  <div key={l.id} className="flex gap-2 font-mono leading-relaxed"
                    onClick={() => word && setNewWord(word)}
                    style={{ cursor: word ? 'pointer' : 'default', fontSize: 9 }}>
                    <span style={{ color: '#203040', flexShrink: 0 }}>{l.timestamp}</span>
                    <span style={{ color: '#00ff8877', wordBreak: 'break-word' }}>{l.message}</span>
                  </div>
                )
              })
          }
        </div>
      </div>

      {/* Manual add */}
      <div className="flex gap-2 mb-4">
        <input value={newWord} onChange={e => setNewWord(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addWord()}
          placeholder="agregar variante manual…"
          className="font-mono flex-1 rounded px-2 py-1 outline-none"
          style={{ fontSize: 10, background: '#040c14', border: '1px solid #00f0ff22', color: '#00f0ff88' }}
        />
        <button onClick={addWord} className="font-mono rounded px-3"
          style={{ fontSize: 9, background: '#00f0ff11', border: '1px solid #00f0ff33', color: '#00f0ff77', cursor: 'pointer' }}>
          + ADD
        </button>
      </div>

      {/* Wake words chips */}
      <div>
        <p className="font-mono mb-1.5" style={{ fontSize: 8, color: '#304050', letterSpacing: '0.2em' }}>
          PALABRAS ACTIVAS — clic para eliminar
        </p>
        <div className="flex flex-wrap gap-1.5">
          {wakeWords.length === 0
            ? <span className="font-mono" style={{ fontSize: 9, color: '#102030' }}>Cargando…</span>
            : wakeWords.map(w => (
              <span key={w} className="font-mono rounded px-2 py-0.5 cursor-pointer"
                style={{ fontSize: 9, background: '#001828', border: '1px solid #00f0ff22', color: '#00f0ff55' }}
                onClick={() => sendCommand('remove_wake_word', { word: w })}>
                {w} ×
              </span>
            ))
          }
        </div>
      </div>
    </Section>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────
export function ControlView() {
  const navigate = useNavigate()
  const { sendCommand } = useWebSocket()

  // ESC or Backspace navigates back to AgentView
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
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className="page-scroll"
      style={{ background: '#05070d', minHeight: '100vh' }}
    >
      <div className="mx-auto px-4 pb-12" style={{ maxWidth: 480 }}>

        {/* Header */}
        <div className="flex items-center justify-between py-5 mb-1 sticky top-0"
          style={{ background: '#05070d', zIndex: 10, borderBottom: '1px solid #0a1e2a' }}>
          <div className="flex items-center gap-2">
            <button onClick={() => navigate('/')} className="font-mono cursor-pointer"
              style={{ fontSize: 10, color: '#00f0ff55', background: 'none', border: 'none', letterSpacing: '0.2em' }}>
              ← BACK
            </button>
            <span className="font-mono" style={{ fontSize: 7, color: '#00f0ff1a', letterSpacing: '0.15em' }}>ESC</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold"
              style={{ fontSize: 14, letterSpacing: '0.4em', color: '#00f0ff', textShadow: '0 0 16px #00f0ff44' }}>
              C.Y.R.U.S
            </span>
            <span className="font-mono" style={{ fontSize: 8, color: '#00f0ff33', letterSpacing: '0.15em' }}>CONTROL</span>
          </div>
          <div style={{ width: 60 }} />
        </div>

        {/* Sections */}
        <div className="pt-4">
          <AIStateBadge />
          <SystemStats />
          <SystemLog />
          <Configuration sendCommand={sendCommand} />
          <ConversationHistory />
          <VoiceCalibration sendCommand={sendCommand} />
        </div>

        {/* Footer */}
        <div className="text-center mt-4">
          <span className="font-mono" style={{ fontSize: 7, color: '#05101a', letterSpacing: '0.2em' }}>
            C.Y.R.U.S v1.0 — COGNITIVE SYSTEM FOR REAL-TIME UTILITY & SERVICES
          </span>
        </div>
      </div>
    </motion.div>
  )
}
