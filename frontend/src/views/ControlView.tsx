/**
 * C.Y.R.U.S — Control Panel View (route "/control")
 * Futuristic dashboard: AI state, system stats, logs, configuration.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate }                  from 'react-router-dom'
import { motion, AnimatePresence }      from 'framer-motion'
import { useCYRUSStore, SystemState, LogEntry } from '../store/useCYRUSStore'
import { useWebSocket } from '../hooks/useWebSocket'

// ── Color map ───────────────────────────────────────────────────────────────
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

// ── Shared section wrapper ──────────────────────────────────────────────────
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

const SectionTitle = ({ label }: { label: string }) => (
  <div className="flex items-center gap-3 mb-3">
    <div style={{ flex: 1, height: 1, background: 'linear-gradient(90deg, #00f0ff22, transparent)' }} />
    <span className="font-mono" style={{ fontSize: 8, letterSpacing: '0.3em', color: '#00f0ff55' }}>
      {label}
    </span>
    <div style={{ flex: 1, height: 1, background: 'linear-gradient(270deg, #00f0ff22, transparent)' }} />
  </div>
)

// ── 1. AI State Badge ───────────────────────────────────────────────────────
function AIStateBadge() {
  const systemState = useCYRUSStore(s => s.systemState)
  const wsConnected = useCYRUSStore(s => s.wsConnected)
  const statusMsg   = useCYRUSStore(s => s.statusMessage)
  const color = STATE_COLOR[systemState]

  return (
    <Section delay={0.1}>
      <SectionTitle label="AI STATE" />
      <div className="flex items-center gap-4">
        <motion.div
          key={systemState}
          animate={{ scale: [1, 1.15, 1] }}
          transition={{ duration: 0.4 }}
          className="relative flex-shrink-0"
        >
          <div
            className="w-4 h-4 rounded-full"
            style={{ background: color, boxShadow: `0 0 12px ${color}, 0 0 24px ${color}44` }}
          />
          {wsConnected && (
            <div
              className="absolute inset-0 rounded-full animate-ping"
              style={{ background: color, opacity: 0.3 }}
            />
          )}
        </motion.div>
        <div>
          <div
            className="font-mono font-bold"
            style={{ fontSize: 18, letterSpacing: '0.25em', color, textShadow: `0 0 16px ${color}66` }}
          >
            {STATE_LABEL[systemState]}
          </div>
          {statusMsg && (
            <div className="font-mono mt-0.5" style={{ fontSize: 9, color: '#00f0ff55', letterSpacing: '0.1em' }}>
              {statusMsg}
            </div>
          )}
        </div>
        <div className="ml-auto text-right">
          <div className="font-mono" style={{ fontSize: 8, color: '#00f0ff33', letterSpacing: '0.15em' }}>
            WEBSOCKET
          </div>
          <div
            className="font-mono"
            style={{ fontSize: 9, color: wsConnected ? '#00ff88' : '#ff3333', letterSpacing: '0.1em' }}
          >
            {wsConnected ? 'CONNECTED' : 'OFFLINE'}
          </div>
        </div>
      </div>
    </Section>
  )
}

// ── 2. System Stats ─────────────────────────────────────────────────────────
function StatBar({ label, value, color = '#00f0ff', unit = '%' }: { label: string; value: number; color?: string; unit?: string }) {
  return (
    <div className="mb-2">
      <div className="flex justify-between mb-1">
        <span className="font-mono" style={{ fontSize: 9, color: '#405060', letterSpacing: '0.15em' }}>{label}</span>
        <span className="font-mono" style={{ fontSize: 9, color }}>{value}{unit}</span>
      </div>
      <div className="rounded-full overflow-hidden" style={{ height: 3, background: '#0a1a28' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 1, ease: 'easeOut', delay: 0.3 }}
          className="h-full rounded-full"
          style={{ background: `linear-gradient(90deg, ${color}88, ${color})`, boxShadow: `0 0 6px ${color}44` }}
        />
      </div>
    </div>
  )
}

function SystemStats() {
  const [uptime, setUptime] = useState(0)
  const [cpu, setCpu] = useState(18)
  const [ram, setRam] = useState(52)
  const [vram, setVram] = useState(31)

  // Simulated fluctuation
  useEffect(() => {
    const id = setInterval(() => {
      setCpu(v  => Math.max(5,  Math.min(85, v  + (Math.random() - 0.5) * 4)))
      setRam(v  => Math.max(30, Math.min(90, v  + (Math.random() - 0.5) * 2)))
      setVram(v => Math.max(20, Math.min(65, v  + (Math.random() - 0.5) * 1.5)))
    }, 3000)
    const uptimeId = setInterval(() => setUptime(t => t + 1), 1000)
    return () => { clearInterval(id); clearInterval(uptimeId) }
  }, [])

  const uptimeStr = [
    String(Math.floor(uptime / 3600)).padStart(2, '0'),
    String(Math.floor((uptime % 3600) / 60)).padStart(2, '0'),
    String(uptime % 60).padStart(2, '0'),
  ].join(':')

  return (
    <Section delay={0.2}>
      <SectionTitle label="SYSTEM METRICS" />
      <StatBar label="CPU" value={Math.round(cpu)} />
      <StatBar label="GPU  RTX 2070S" value={Math.round(vram)} color="#a855f7" unit="% VRAM" />
      <StatBar label="RAM" value={Math.round(ram)} color="#00ff88" />
      <div className="flex gap-4 mt-3">
        <div>
          <div className="font-mono" style={{ fontSize: 8, color: '#203040', letterSpacing: '0.2em' }}>UPTIME</div>
          <div className="font-mono" style={{ fontSize: 11, color: '#00f0ff77' }}>{uptimeStr}</div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: 8, color: '#203040', letterSpacing: '0.2em' }}>LOCATION</div>
          <div className="font-mono" style={{ fontSize: 11, color: '#00f0ff77' }}>LIMA, PE</div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: 8, color: '#203040', letterSpacing: '0.2em' }}>WEATHER</div>
          <div className="font-mono" style={{ fontSize: 11, color: '#00f0ff77' }}>17°C  CLEAR</div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: 8, color: '#203040', letterSpacing: '0.2em' }}>GPU TEMP</div>
          <div className="font-mono" style={{ fontSize: 11, color: '#00f0ff77' }}>62°C</div>
        </div>
      </div>
    </Section>
  )
}

// ── 3. System Log ───────────────────────────────────────────────────────────
const LOG_COLOR: Record<string, string> = {
  info:  '#00f0ff',
  warn:  '#ff8c00',
  error: '#ff3333',
}

function SystemLog() {
  const logs    = useCYRUSStore(s => s.logs)
  const clearLogs = useCYRUSStore(s => s.clearLogs)
  const endRef  = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <Section delay={0.3}>
      <div className="flex items-center justify-between mb-3">
        <SectionTitle label="SYSTEM LOG" />
        <button
          onClick={clearLogs}
          className="font-mono"
          style={{ fontSize: 8, color: '#00f0ff33', background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '0.15em' }}
        >
          CLEAR
        </button>
      </div>
      <div
        className="overflow-y-auto rounded"
        style={{ height: 180, background: 'rgba(0,10,20,0.6)', border: '1px solid #05151f', padding: '8px 10px' }}
      >
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

// ── 4. Configuration ────────────────────────────────────────────────────────
function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
      <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>{label}</span>
      <button
        onClick={() => onChange(!value)}
        className="relative rounded-full transition-all"
        style={{
          width: 32, height: 16,
          background: value ? '#00f0ff44' : '#0a1e2a',
          border: `1px solid ${value ? '#00f0ff66' : '#102030'}`,
        }}
      >
        <motion.div
          animate={{ x: value ? 16 : 2 }}
          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
          className="absolute top-0.5 rounded-full"
          style={{ width: 11, height: 11, background: value ? '#00f0ff' : '#203040', boxShadow: value ? '0 0 6px #00f0ff' : 'none' }}
        />
      </button>
    </div>
  )
}

function Slider({ label, value, min, max, step = 0.1, onChange }: {
  label: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
      <div className="flex justify-between mb-1.5">
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>{label}</span>
        <span className="font-mono" style={{ fontSize: 10, color: '#00f0ff77' }}>{value.toFixed(1)}</span>
      </div>
      <div className="relative" style={{ height: 4, background: '#0a1a28', borderRadius: 2 }}>
        <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${pct}%`, background: 'linear-gradient(90deg, #00f0ff44, #00f0ff)', borderRadius: 2 }} />
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          className="absolute inset-0 opacity-0 cursor-pointer w-full"
          style={{ margin: 0 }}
        />
      </div>
    </div>
  )
}

function Configuration() {
  const particleCount   = useCYRUSStore(s => s.particleCount)
  const bloomIntensity  = useCYRUSStore(s => s.bloomIntensity)
  const orbSpeed        = useCYRUSStore(s => s.orbSpeed)
  const setParticleCount  = useCYRUSStore(s => s.setParticleCount)
  const setBloomIntensity = useCYRUSStore(s => s.setBloomIntensity)
  const setOrbSpeed       = useCYRUSStore(s => s.setOrbSpeed)

  const [vadEnabled, setVadEnabled]   = useState(true)
  const [llmModel, setLlmModel]       = useState('phi3:latest')
  const [ttsEngine, setTtsEngine]     = useState('kokoro')
  const [wakeWord, setWakeWord]       = useState('hola cyrus')
  const [editingModel, setEditingModel] = useState(false)

  return (
    <Section delay={0.4}>
      <SectionTitle label="CONFIGURATION" />

      {/* LLM Model */}
      <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>LLM MODEL</span>
        {editingModel ? (
          <input
            autoFocus
            value={llmModel}
            onChange={e => setLlmModel(e.target.value)}
            onBlur={() => setEditingModel(false)}
            onKeyDown={e => e.key === 'Enter' && setEditingModel(false)}
            className="font-mono rounded px-2 py-0.5 outline-none"
            style={{ fontSize: 10, background: '#0a1e2a', border: '1px solid #00f0ff44', color: '#00f0ff', width: 130 }}
          />
        ) : (
          <button
            onClick={() => setEditingModel(true)}
            className="font-mono px-2 py-0.5 rounded"
            style={{ fontSize: 10, background: '#00f0ff11', border: '1px solid #00f0ff33', color: '#00f0ffaa', cursor: 'pointer' }}
          >
            {llmModel}
          </button>
        )}
      </div>

      {/* TTS Engine */}
      <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>TTS ENGINE</span>
        <select
          value={ttsEngine}
          onChange={e => setTtsEngine(e.target.value)}
          className="font-mono rounded px-2 py-0.5 outline-none"
          style={{ fontSize: 10, background: '#0a1e2a', border: '1px solid #00f0ff33', color: '#00f0ffaa', cursor: 'pointer' }}
        >
          <option value="kokoro">kokoro</option>
          <option value="edge-tts">edge-tts</option>
          <option value="voiceforge">voiceforge</option>
        </select>
      </div>

      {/* Wake word */}
      <div className="flex items-center justify-between py-2" style={{ borderBottom: '1px solid #0a1e2a' }}>
        <span className="font-mono" style={{ fontSize: 10, color: '#305060', letterSpacing: '0.1em' }}>WAKE WORD</span>
        <input
          value={wakeWord}
          onChange={e => setWakeWord(e.target.value)}
          className="font-mono rounded px-2 py-0.5 outline-none"
          style={{ fontSize: 10, background: '#0a1e2a', border: '1px solid #00f0ff22', color: '#00f0ff88', width: 120 }}
        />
      </div>

      {/* Toggles */}
      <Toggle label="VAD ENABLED" value={vadEnabled} onChange={setVadEnabled} />

      {/* Sliders */}
      <Slider
        label="BLOOM INTENSITY"
        value={bloomIntensity} min={0.5} max={2.5} step={0.05}
        onChange={setBloomIntensity}
      />
      <Slider
        label="PARTICLE COUNT"
        value={particleCount} min={100} max={400} step={10}
        onChange={setParticleCount}
      />
      <Slider
        label="NEURAL SPEED"
        value={orbSpeed} min={0.1} max={3.0} step={0.05}
        onChange={setOrbSpeed}
      />
    </Section>
  )
}

// ── Conversation History ────────────────────────────────────────────────────
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
      <div className="overflow-y-auto flex flex-col gap-2" style={{ maxHeight: 200 }}>
        {transcript.map(entry => (
          <div key={entry.id} className={`flex flex-col ${entry.role === 'user' ? 'items-end' : 'items-start'}`}>
            <span className="font-mono mb-0.5" style={{ fontSize: 8, color: '#203040', letterSpacing: '0.2em' }}>
              {entry.role === 'user' ? 'YOU' : 'C.Y.R.U.S'}{' '}
              {entry.timestamp.toLocaleTimeString('en-GB', { hour12: false })}
            </span>
            <div
              className="px-3 py-1.5 rounded font-mono"
              style={{
                fontSize: 10, maxWidth: '85%', lineHeight: 1.5,
                ...(entry.role === 'user'
                  ? { background: 'rgba(0,100,160,0.2)', border: '1px solid #0a4060', color: '#80c8e8' }
                  : { background: 'rgba(0,40,80,0.4)', border: '1px solid #004060', color: '#b0e8ff' }),
              }}
            >
              {entry.text}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </Section>
  )
}

// ── Voice Enrollment ───────────────────────────────────────────────────────
function VoiceCalibration({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const wakeWords       = useCYRUSStore(s => s.wakeWords)
  const logs            = useCYRUSStore(s => s.logs)
  const enrollStep      = useCYRUSStore(s => s.enrollmentStep)
  const enrollSample    = useCYRUSStore(s => s.enrollmentSample)
  const enrollTotal     = useCYRUSStore(s => s.enrollmentTotal)
  const enrollResults   = useCYRUSStore(s => s.enrollmentResults)
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

      {/* ── Enrollment wizard ── */}
      <div className="mb-4 rounded p-3" style={{ background: 'rgba(0,255,136,0.04)', border: '1px solid #00ff8820' }}>
        <p className="font-mono mb-2" style={{ fontSize: 9, color: '#00ff8877', letterSpacing: '0.15em' }}>
          ENROLLAR MI VOZ
        </p>
        <p className="font-mono mb-3" style={{ fontSize: 9, color: '#304050', lineHeight: 1.6 }}>
          CYRUS grabará {enrollTotal} muestras de cómo pronuncias su nombre y aprenderá esas variantes.
          Habla de forma natural.
        </p>

        {/* Progress bar during enrollment */}
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
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${(enrollSample / enrollTotal) * 100}%`, background: 'linear-gradient(90deg, #00ff8844, #00ff88)' }}
              />
            </div>
            {/* Results so far */}
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
            <p className="font-mono" style={{ fontSize: 9, color: '#00ff88' }}>✓ Enrollamiento completado</p>
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
          {isEnrolling ? `GRABANDO ${enrollSample}/${enrollTotal}…` : '🎤 INICIAR ENROLLAMIENTO DE VOZ'}
        </button>
      </div>

      {/* ── Recent ASR log ── */}
      <div className="mb-3">
        <p className="font-mono mb-1.5" style={{ fontSize: 8, color: '#304050', letterSpacing: '0.2em' }}>
          LO QUE CYRUS ESCUCHÓ (últimas frases) — clic para agregar
        </p>
        <div className="rounded" style={{ background: 'rgba(0,8,16,0.7)', border: '1px solid #0a1e2a', padding: '6px 8px', minHeight: 40 }}>
          {asrLines.length === 0
            ? <p className="font-mono" style={{ fontSize: 9, color: '#0a2030' }}>Habla para ver transcripciones en tiempo real…</p>
            : asrLines.map(l => {
                const m = l.message.match(/"([^"]+)"/)
                const word = m?.[1] ?? ''
                return (
                  <div key={l.id} className="flex gap-2 font-mono leading-relaxed"
                    onClick={() => word && setNewWord(word)} style={{ cursor: word ? 'pointer' : 'default', fontSize: 9 }}>
                    <span style={{ color: '#203040', flexShrink: 0 }}>{l.timestamp}</span>
                    <span style={{ color: '#00ff8877', wordBreak: 'break-word' }}>{l.message}</span>
                  </div>
                )
              })
          }
        </div>
      </div>

      {/* ── Manual add ── */}
      <div className="flex gap-2 mb-4">
        <input
          value={newWord}
          onChange={e => setNewWord(e.target.value)}
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

      {/* ── Wake words chips ── */}
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

  return (
    <motion.div
      initial={{ opacity: 0, filter: 'blur(8px)' }}
      animate={{ opacity: 1, filter: 'blur(0px)' }}
      transition={{ duration: 0.6, ease: 'easeOut' }}
      className="page-scroll"
      style={{ background: '#05070d', minHeight: '100vh' }}
    >
      <div className="mx-auto px-4 pb-12" style={{ maxWidth: 480 }}>

        {/* ── Header ── */}
        <div
          className="flex items-center justify-between py-5 mb-1 sticky top-0"
          style={{ background: '#05070d', zIndex: 10, borderBottom: '1px solid #0a1e2a' }}
        >
          <button
            onClick={() => navigate('/')}
            className="font-mono flex items-center gap-2 cursor-pointer"
            style={{ fontSize: 10, color: '#00f0ff55', background: 'none', border: 'none', letterSpacing: '0.2em' }}
          >
            ← BACK
          </button>
          <div className="flex items-center gap-2">
            <span
              className="font-mono font-bold"
              style={{ fontSize: 14, letterSpacing: '0.4em', color: '#00f0ff', textShadow: '0 0 16px #00f0ff44' }}
            >
              C.Y.R.U.S
            </span>
            <span className="font-mono" style={{ fontSize: 8, color: '#00f0ff33', letterSpacing: '0.15em' }}>CONTROL</span>
          </div>
          <div style={{ width: 60 }} />
        </div>

        {/* ── Sections ── */}
        <div className="pt-4">
          <AIStateBadge />
          <SystemStats />
          <SystemLog />
          <VoiceCalibration sendCommand={sendCommand} />
          <ConversationHistory />
          <Configuration />
        </div>

        {/* ── Footer ── */}
        <div className="text-center mt-4">
          <span className="font-mono" style={{ fontSize: 7, color: '#05101a', letterSpacing: '0.2em' }}>
            C.Y.R.U.S v1.0 — COGNITIVE SYSTEM FOR REAL-TIME UTILITY & SERVICES
          </span>
        </div>
      </div>
    </motion.div>
  )
}
