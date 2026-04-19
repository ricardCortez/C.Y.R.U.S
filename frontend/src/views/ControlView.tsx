/**
 * C.Y.R.U.S — Control Panel  (route "/control")
 * Redesigned: 2-column dashboard, real-time pipeline monitor, full-width layout
 */

import { useEffect, useRef, useState, useMemo } from 'react'
import { useNavigate }          from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown            from 'react-markdown'
import { useCYRUSStore, SystemState, LogEntry, ServiceStatus } from '../store/useCYRUSStore'
import { useWebSocket }         from '../hooks/useWebSocket'

// ── Design tokens ────────────────────────────────────────────────────────────

const C = {
  bg:       '#030508',
  panel:    'rgba(6,12,22,0.92)',
  border:   '#0d1f30',
  borderHi: '#1a3a55',
  text:     '#8ab8cc',
  textDim:  '#2a4a5a',
  textBright:'#c8e8f4',
  cyan:     '#00d8ff',
  green:    '#00e87a',
  amber:    '#ff9020',
  purple:   '#a855f7',
  red:      '#ff3c3c',
  blue:     '#2a8aff',
}

const STATE_COLOR: Record<SystemState, string> = {
  offline: C.red, connected: C.cyan, idle: C.blue,
  listening: C.green, transcribing: C.cyan, thinking: C.amber,
  speaking: C.purple, error: C.red,
}
const STATE_LABEL: Record<SystemState, string> = {
  offline:'OFFLINE', connected:'STANDBY', idle:'IDLE',
  listening:'ESCUCHANDO', transcribing:'TRANSCRIBIENDO',
  thinking:'PROCESANDO', speaking:'HABLANDO', error:'ERROR',
}

// ── Primitives ───────────────────────────────────────────────────────────────

const mono = (size = 9, color = C.text): React.CSSProperties => ({
  fontFamily: '"Share Tech Mono", "Courier New", monospace',
  fontSize: size, color, letterSpacing: '0.08em',
})

function Panel({ children, style, accent }: { children: React.ReactNode; style?: React.CSSProperties; accent?: string }) {
  return (
    <div style={{
      background: C.panel,
      border: `1px solid ${accent ? accent + '40' : C.border}`,
      borderRadius: 10,
      padding: '14px 16px',
      ...style,
    }}>
      {children}
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      ...mono(8, C.textDim),
      letterSpacing: '0.25em',
      textTransform: 'uppercase',
      marginBottom: 10,
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    }}>
      <div style={{ flex: 1, height: 1, background: C.border }} />
      <span>{children}</span>
      <div style={{ flex: 1, height: 1, background: C.border }} />
    </div>
  )
}

function MetricBar({ label, value, color = C.cyan, unit = '%', warn = 80, crit = 95 }: {
  label: string; value: number; color?: string; unit?: string; warn?: number; crit?: number
}) {
  const col = value >= crit ? C.red : value >= warn ? C.amber : color
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={mono(9, C.textDim)}>{label}</span>
        <span style={mono(9, col)}>{value.toFixed(0)}{unit}</span>
      </div>
      <div style={{ height: 4, background: '#060e18', borderRadius: 2, overflow: 'hidden' }}>
        <motion.div
          animate={{ width: `${Math.min(100, value)}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          style={{ height: '100%', background: `linear-gradient(90deg, ${col}44, ${col})`, borderRadius: 2 }}
        />
      </div>
    </div>
  )
}

function Btn({ children, onClick, color = C.cyan, disabled = false, small = false, style }: {
  children: React.ReactNode; onClick?: () => void; color?: string;
  disabled?: boolean; small?: boolean; style?: React.CSSProperties
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        ...mono(small ? 9 : 10, disabled ? C.textDim : color),
        letterSpacing: '0.18em',
        padding: small ? '5px 10px' : '8px 14px',
        borderRadius: 7,
        border: `1px solid ${disabled ? C.border : color + '55'}`,
        background: disabled ? 'transparent' : `${color}12`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s',
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {children}
    </button>
  )
}

function Select({ value, onChange, options, style }: {
  value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]
  style?: React.CSSProperties
}) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{
      ...mono(10, C.textBright),
      background: '#040c18', border: `1px solid ${C.border}`,
      borderRadius: 7, padding: '8px 10px', cursor: 'pointer', outline: 'none',
      width: '100%', ...style,
    }}>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

function Input({ value, onChange, placeholder, onKeyDown, type = 'text', style }: {
  value: string; onChange: (v: string) => void; placeholder?: string
  onKeyDown?: (e: React.KeyboardEvent) => void; type?: string; style?: React.CSSProperties
}) {
  return (
    <input
      type={type} value={value} placeholder={placeholder}
      onChange={e => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      style={{
        ...mono(10, C.textBright),
        background: '#040c18', border: `1px solid ${C.border}`,
        borderRadius: 7, padding: '8px 10px', outline: 'none', width: '100%', ...style,
      }}
    />
  )
}

function SliderRow({ label, value, min, max, step = 0.05, unit = '', onChange, onCommit }: {
  label: string; value: number; min: number; max: number
  step?: number; unit?: string; onChange: (v: number) => void; onCommit?: (v: number) => void
}) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={mono(9, C.textDim)}>{label}</span>
        <span style={mono(9, C.cyan)}>{value.toFixed(2)}{unit}</span>
      </div>
      <div style={{ position: 'relative', height: 4, background: '#060e18', borderRadius: 2 }}>
        <div style={{ position:'absolute',top:0,left:0,bottom:0,width:`${pct}%`,background:`linear-gradient(90deg,${C.cyan}33,${C.cyan})`,borderRadius:2 }} />
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(parseFloat(e.target.value))}
          onMouseUp={e => onCommit?.(parseFloat((e.target as HTMLInputElement).value))}
          onTouchEnd={e => onCommit?.(parseFloat((e.target as HTMLInputElement).value))}
          style={{ position:'absolute',inset:0,opacity:0,cursor:'pointer',width:'100%',margin:0 }}
        />
      </div>
    </div>
  )
}

// ── Uptime formatter ──────────────────────────────────────────────────────────

function uptime(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return [h, m, sec].map(n => String(n).padStart(2, '0')).join(':')
}

// ── Log color map ─────────────────────────────────────────────────────────────

const LOG_COL: Record<string, string> = { info: C.cyan, warn: C.amber, error: C.red, ok: C.green }

// ── Tab bar ───────────────────────────────────────────────────────────────────

const TABS = ['SISTEMA', 'CONFIG', 'VOZ', 'API', 'AGENDA'] as const
type Tab = typeof TABS[number]

const TAB_ICON: Record<Tab, string> = {
  SISTEMA: '◉', CONFIG: '⚙', VOZ: '◎', API: '⬡', AGENDA: '◈'
}

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div style={{ display: 'flex', gap: 4, padding: '3px', background: '#050c16', border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 16 }}>
      {TABS.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
          padding: '8px 4px', borderRadius: 8, cursor: 'pointer', transition: 'all 0.2s',
          background: active === t ? `${C.cyan}14` : 'transparent',
          border: active === t ? `1px solid ${C.cyan}44` : '1px solid transparent',
        }}>
          <span style={{ fontSize: 12, color: active === t ? C.cyan : C.textDim }}>{TAB_ICON[t]}</span>
          <span style={mono(7, active === t ? C.cyan : C.textDim)}>{t}</span>
        </button>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// PIPELINE MONITOR — parses logs to show live pipeline stages
// ═══════════════════════════════════════════════════════════════════════════

interface StageInfo { label: string; state: 'idle'|'active'|'done'|'error'; latency?: string; detail?: string }

function usePipelineInfo() {
  const state = useCYRUSStore(s => s.systemState)
  const logs  = useCYRUSStore(s => s.logs)

  return useMemo(() => {
    const recent = logs.slice(-60)

    const find = (pattern: RegExp) => recent.slice().reverse().find(l => pattern.test(l.message))

    const asrLog   = find(/ASR.*transcript=/)
    const llmLog   = find(/LLM.*responded|LLM.*failed/)
    const ttsLog   = find(/TTS playback: actual=/)
    const muteLog  = find(/mute_for\(/)
    const toolLog  = find(/Respondió via Tools/)
    const trigLog  = find(/Trigger detected/)

    // Parse latencies from log messages
    const asrTime  = asrLog?.message.match(/(\d+\.\d+)s/)
    const ttsMatch = ttsLog?.message.match(/actual=([\d.]+)s/)
    const muteMatch= muteLog?.message.match(/mute_for\(([\d.]+)s\)/)

    const mic: StageInfo = {
      label: 'MICRÓFONO',
      state: state === 'listening' || state === 'transcribing' ? 'active'
           : state === 'speaking' ? 'idle' : 'idle',
      detail: muteMatch ? `muted ${parseFloat(muteMatch[1]).toFixed(1)}s` : undefined,
    }

    const asr: StageInfo = {
      label: 'ASR',
      state: state === 'transcribing' ? 'active'
           : asrLog ? 'done' : 'idle',
      latency: asrTime ? `${asrTime[1]}s` : undefined,
      detail:  trigLog?.message.match(/'(.+)' in/)?.[1]?.slice(0, 24),
    }

    const llm: StageInfo = {
      label: 'LLM',
      state: state === 'thinking' ? 'active'
           : llmLog?.message.includes('failed') ? 'error'
           : llmLog ? 'done' : 'idle',
      detail: toolLog ? '🔧 tools' : undefined,
    }

    const tts: StageInfo = {
      label: 'TTS',
      state: state === 'speaking' ? 'active'
           : ttsLog ? 'done' : 'idle',
      latency: ttsMatch ? `${parseFloat(ttsMatch[1]).toFixed(1)}s` : undefined,
    }

    return [mic, asr, llm, tts]
  }, [state, logs])
}

function PipelineMonitor() {
  const stages = usePipelineInfo()
  const state  = useCYRUSStore(s => s.systemState)

  const stageColor = (s: StageInfo['state']) =>
    s === 'active' ? C.amber : s === 'done' ? C.green : s === 'error' ? C.red : C.textDim

  return (
    <Panel style={{ marginBottom: 12 }} accent={C.amber}>
      <SectionLabel>PIPELINE EN TIEMPO REAL</SectionLabel>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
        {stages.map((stage, i) => (
          <div key={stage.label} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            {/* Stage box */}
            <div style={{
              flex: 1,
              padding: '8px 6px',
              borderRadius: 7,
              border: `1px solid ${stageColor(stage.state)}44`,
              background: stage.state === 'active' ? `${stageColor(stage.state)}12` : '#04080e',
              textAlign: 'center',
              position: 'relative',
              overflow: 'hidden',
            }}>
              {stage.state === 'active' && (
                <motion.div
                  style={{ position:'absolute',top:0,left:0,height:'100%',width:'30%',background:`linear-gradient(90deg,transparent,${C.amber}22,transparent)` }}
                  animate={{ left: ['0%', '120%'] }}
                  transition={{ duration: 1.2, repeat: Infinity, ease: 'linear' }}
                />
              )}
              <div style={mono(8, stageColor(stage.state))}>{stage.label}</div>
              {stage.latency && <div style={mono(8, C.green)}>{stage.latency}</div>}
              {stage.detail && <div style={{ ...mono(7, C.textDim), marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{stage.detail}</div>}
              {/* Active dot */}
              {stage.state === 'active' && (
                <div style={{ position:'absolute',top:4,right:4,width:5,height:5,borderRadius:'50%',background:C.amber,boxShadow:`0 0 6px ${C.amber}` }} />
              )}
            </div>
            {/* Arrow */}
            {i < stages.length - 1 && (
              <div style={{ ...mono(10, C.border), padding: '0 3px', flexShrink: 0 }}>→</div>
            )}
          </div>
        ))}
      </div>
      {/* State label */}
      <div style={{ display:'flex', justifyContent:'flex-end', marginTop:8 }}>
        <span style={{ ...mono(8, STATE_COLOR[state]), letterSpacing:'0.2em' }}>
          ● {STATE_LABEL[state]}
        </span>
      </div>
    </Panel>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 1 — SISTEMA (2-column dashboard)
// ═══════════════════════════════════════════════════════════════════════════

function TabSistema() {
  const state    = useCYRUSStore(s => s.systemState)
  const wsOn     = useCYRUSStore(s => s.wsConnected)
  const stats    = useCYRUSStore(s => s.systemStats)
  const logs     = useCYRUSStore(s => s.logs)
  const clearLogs= useCYRUSStore(s => s.clearLogs)
  const endRef   = useRef<HTMLDivElement>(null)

  const [sim, setSim] = useState({ cpu: 18, ram: 55 })
  useEffect(() => {
    if (stats) return
    const id = setInterval(() => setSim(v => ({
      cpu: Math.max(5, Math.min(90, v.cpu + (Math.random()-0.5)*5)),
      ram: Math.max(30, Math.min(85, v.ram + (Math.random()-0.5)*2)),
    })), 2500)
    return () => clearInterval(id)
  }, [stats])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs])

  const cpu   = stats?.cpu   ?? sim.cpu
  const ram   = stats?.ram   ?? sim.ram
  const vram  = stats?.vram  ?? 0
  const temp  = stats?.gpuTemp ?? 0
  const ut    = stats?.uptime  ?? 0
  const tts   = stats?.ttsBackend?.toUpperCase() ?? '—'
  const live  = !!stats
  const col   = STATE_COLOR[state]

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
      {/* Pipeline monitor — full width at top */}
      <PipelineMonitor />

      {/* 2-column layout below */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

        {/* LEFT — Status + Metrics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

          {/* State card */}
          <Panel accent={col}>
            <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:12 }}>
              <div style={{ position:'relative', width:14, height:14, flexShrink:0 }}>
                <div style={{ width:'100%',height:'100%',borderRadius:'50%',background:col,boxShadow:`0 0 10px ${col}` }} />
                {wsOn && <div style={{ position:'absolute',inset:0,borderRadius:'50%',background:col,opacity:0.25,animation:'ping 1.5s infinite' }} />}
              </div>
              <div>
                <div style={{ ...mono(15, col), letterSpacing:'0.2em', textShadow:`0 0 14px ${col}44` }}>
                  {STATE_LABEL[state]}
                </div>
                <div style={mono(8, C.textDim)}>WebSocket: {wsOn ? 'CONECTADO' : 'DESCONECTADO'}</div>
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8, paddingTop:10, borderTop:`1px solid ${C.border}` }}>
              {[
                { k:'UPTIME',   v: uptime(ut),      c: C.cyan },
                { k:'TTS',      v: tts,             c: C.purple },
                { k:'DATOS',    v: live ? 'LIVE' : 'SIM', c: live ? C.green : C.textDim },
              ].map(({ k, v, c }) => (
                <div key={k} style={{ textAlign:'center' }}>
                  <div style={mono(7, C.textDim)}>{k}</div>
                  <div style={{ ...mono(10, c), marginTop:3 }}>{v}</div>
                </div>
              ))}
            </div>
          </Panel>

          {/* Metrics */}
          <Panel>
            <SectionLabel>MÉTRICAS DEL SISTEMA</SectionLabel>
            <MetricBar label="CPU" value={cpu} color={C.cyan} />
            <MetricBar label="RAM" value={ram} color={C.green} />
            {vram > 0 && <MetricBar label="VRAM" value={vram} color={C.purple} />}
            {temp > 0 && (
              <div style={{ display:'flex', justifyContent:'space-between', paddingTop:8, borderTop:`1px solid ${C.border}`, marginTop:4 }}>
                <span style={mono(9, C.textDim)}>GPU TEMP</span>
                <span style={mono(9, temp > 80 ? C.red : temp > 70 ? C.amber : C.textDim)}>{temp}°C</span>
              </div>
            )}
          </Panel>

          {/* Tool catalog */}
          <Panel>
            <SectionLabel>HERRAMIENTAS ACTIVAS</SectionLabel>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:5 }}>
              {['buscar_web','clima','hora_ciudad','calculadora','listar_archivos','leer_archivo','sistema_info','abrir_app'].map(t => (
                <div key={t} style={{ display:'flex', alignItems:'center', gap:5, padding:'4px 6px', borderRadius:5, background:'#04080e', border:`1px solid ${C.border}` }}>
                  <div style={{ width:5,height:5,borderRadius:'50%',background:C.green,boxShadow:`0 0 4px ${C.green}`,flexShrink:0 }} />
                  <span style={mono(8, C.text)}>{t}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        {/* RIGHT — Log */}
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <Panel style={{ flex: 1, display:'flex', flexDirection:'column' }}>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:8 }}>
              <SectionLabel>LOG EN TIEMPO REAL</SectionLabel>
              <Btn onClick={clearLogs} small color={C.textDim}>LIMPIAR</Btn>
            </div>
            <div style={{
              flex: 1, minHeight: 380, maxHeight: 500, overflowY:'auto',
              background:'#02060c', borderRadius:6, border:`1px solid #060e18`,
              padding:'8px 10px', display:'flex', flexDirection:'column', gap:1,
            }}>
              {logs.length === 0 ? (
                <div style={mono(9, C.textDim)}>Esperando eventos del sistema…</div>
              ) : logs.map((e: LogEntry) => (
                <div key={e.id} style={{ display:'flex', gap:8, alignItems:'baseline' }}>
                  <span style={mono(8, C.textDim)}>{e.timestamp}</span>
                  <span style={{ ...mono(9, LOG_COL[e.level] ?? C.cyan), opacity:0.85, wordBreak:'break-word', flex:1 }}>
                    {e.message}
                  </span>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          </Panel>
        </div>
      </div>
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 2 — CONFIG (clean grid layout)
// ═══════════════════════════════════════════════════════════════════════════

function TabConfig({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const ttsSpeed       = useCYRUSStore(s => s.ttsSpeed)
  const setTtsSpeed    = useCYRUSStore(s => s.setTtsSpeed)
  const availModels    = useCYRUSStore(s => s.availableModels)
  const currentModel   = useCYRUSStore(s => s.currentModel)
  const sysStats       = useCYRUSStore(s => s.systemStats)
  const particleCount  = useCYRUSStore(s => s.particleCount)
  const bloomIntensity = useCYRUSStore(s => s.bloomIntensity)
  const orbSpeed       = useCYRUSStore(s => s.orbSpeed)
  const setParticleCount  = useCYRUSStore(s => s.setParticleCount)
  const setBloomIntensity = useCYRUSStore(s => s.setBloomIntensity)
  const setOrbSpeed       = useCYRUSStore(s => s.setOrbSpeed)

  const [llmModel,    setLlmModel]   = useState(currentModel || '')
  const [ttsEngine,   setTtsEngine]  = useState('edge-tts')
  const [voicePreset, setVoicePreset]= useState('natural')
  const [testText,    setTestText]   = useState('')
  const [testing,     setTesting]    = useState(false)
  const [ollamaOk,    setOllamaOk]   = useState<boolean|null>(null)

  useEffect(() => { sendCommand('list_ollama_models') }, [sendCommand])
  useEffect(() => { if (currentModel) setLlmModel(currentModel) }, [currentModel])

  const probeOllama = () => {
    setOllamaOk(null)
    sendCommand('probe_local_ai_detector', { detector: 'ollama' })
    setTimeout(() => setOllamaOk(true), 1800)
  }

  const testTts = () => {
    setTesting(true)
    sendCommand('test_tts', { text: testText.trim() || 'Sistema CYRUS operativo.', engine: ttsEngine })
    setTimeout(() => setTesting(false), 4000)
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

        {/* LEFT column */}
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>

          {/* LLM Model */}
          <Panel accent={C.amber}>
            <SectionLabel>MODELO LLM (OLLAMA)</SectionLabel>
            <div style={{ display:'flex', gap:8, marginBottom:10 }}>
              <Btn onClick={() => sendCommand('list_ollama_models')} small color={C.cyan} style={{flex:1}}>REFRESCAR</Btn>
              <Btn onClick={probeOllama} small color={ollamaOk === true ? C.green : ollamaOk === false ? C.red : C.amber} style={{flex:1}}>
                {ollamaOk === null ? 'PROBAR' : ollamaOk ? 'ACTIVO ✓' : 'ERROR ✗'}
              </Btn>
            </div>
            {availModels.length > 0 ? (
              <>
                <Select
                  value={llmModel}
                  onChange={v => { setLlmModel(v); sendCommand('set_llm_model', { model: v }) }}
                  options={availModels.map(m => ({
                    value: m.name,
                    label: `${m.name}${m.name === currentModel ? ' ●' : ''}`,
                  }))}
                />
                {availModels.map(m => m.name === llmModel && (
                  <div key={m.name} style={{ display:'flex', justifyContent:'space-between', marginTop:8 }}>
                    <span style={mono(8, C.textDim)}>Compatibilidad</span>
                    <span style={mono(8, m.compatible ? C.green : C.red)}>{m.compatibility}</span>
                  </div>
                ))}
              </>
            ) : (
              <div style={{ ...mono(9, C.textDim), padding:'10px', textAlign:'center', border:`1px dashed ${C.border}`, borderRadius:6 }}>
                Sin modelos — verifica Ollama
              </div>
            )}
          </Panel>

          {/* IA Detector */}
          <Panel>
            <SectionLabel>DETECTOR IA LOCAL</SectionLabel>
            <Select
              value="ollama"
              onChange={() => {}}
              options={[{ value:'ollama', label:'Ollama local (activo)' }]}
            />
            <div style={{ marginTop:8, padding:'8px 10px', background:'#02060c', borderRadius:6, border:`1px solid ${C.border}` }}>
              <span style={mono(8, C.textDim)}>
                Whisper small/cpu/int8 → qwen3:8b → Edge-TTS es-PE
              </span>
            </div>
          </Panel>

          {/* Visual */}
          <Panel>
            <SectionLabel>VISUALIZACIÓN NEURONAL</SectionLabel>
            <SliderRow label="BLOOM" value={bloomIntensity} min={0.5} max={2.5} step={0.05} onChange={setBloomIntensity} />
            <SliderRow label="PARTÍCULAS" value={particleCount} min={100} max={400} step={10} onChange={setParticleCount} unit="" />
            <SliderRow label="VELOCIDAD ORB" value={orbSpeed} min={0.1} max={3.0} step={0.05} onChange={setOrbSpeed} />
          </Panel>
        </div>

        {/* RIGHT column */}
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>

          {/* TTS Engine */}
          <Panel accent={C.purple}>
            <SectionLabel>SÍNTESIS DE VOZ</SectionLabel>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:10 }}>
              <div>
                <div style={{ ...mono(8, C.textDim), marginBottom:5 }}>MOTOR</div>
                <Select
                  value={ttsEngine}
                  onChange={v => { setTtsEngine(v); sendCommand('set_tts_engine', { engine: v }) }}
                  options={[
                    { value:'edge-tts',  label:'Edge-TTS (es-PE) ●' },
                    { value:'kokoro',    label:'Kokoro (offline)' },
                    { value:'piper',     label:'Piper (local)' },
                    { value:'remote-tts',label:'Remote TTS' },
                  ]}
                />
              </div>
              <div>
                <div style={{ ...mono(8, C.textDim), marginBottom:5 }}>PRESET</div>
                <Select
                  value={voicePreset}
                  onChange={v => { setVoicePreset(v); sendCommand('set_voice_preset', { preset: v }) }}
                  options={[
                    { value:'natural',  label:'Natural' },
                    { value:'dramatic', label:'Dramática' },
                    { value:'suave',    label:'Suave' },
                  ]}
                />
              </div>
            </div>

            <div style={{ marginBottom:10 }}>
              <div style={{ ...mono(8, C.textDim), marginBottom:5 }}>VELOCIDAD</div>
              <SliderRow label="" value={ttsSpeed} min={0.5} max={2.0} step={0.05}
                onChange={setTtsSpeed} onCommit={v => sendCommand('set_tts_speed', { speed: v })} />
            </div>

            {sysStats?.ttsBackend && (
              <div style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 10px', background:'#02060c', borderRadius:6, border:`1px solid ${C.border}` }}>
                <div style={{ width:6,height:6,borderRadius:'50%',background:C.green,boxShadow:`0 0 5px ${C.green}` }} />
                <span style={mono(8, C.green)}>ACTIVO: {sysStats.ttsBackend.toUpperCase()}</span>
              </div>
            )}
          </Panel>

          {/* TTS Test */}
          <Panel>
            <SectionLabel>PRUEBA DE VOZ</SectionLabel>
            <Input
              value={testText}
              onChange={setTestText}
              placeholder="Texto para sintetizar…"
              onKeyDown={e => e.key === 'Enter' && testTts()}
              style={{ marginBottom: 8 }}
            />
            <div style={{ display:'flex', gap:8 }}>
              <Btn onClick={testTts} disabled={testing} color={C.purple} style={{ flex:1, justifyContent:'center' }}>
                {testing ? '◈ REPRODUCIENDO…' : '▶ PROBAR'}
              </Btn>
              <Btn onClick={() => setTestText('Hola Ricardo. Sistema CYRUS operativo al cien por ciento.')} small color={C.textDim}>
                DEMO
              </Btn>
            </div>
          </Panel>

          {/* Audio config summary */}
          <Panel>
            <SectionLabel>AUDIO — CONFIG ACTUAL</SectionLabel>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {[
                { k:'Dispositivo mic', v:'default (laptop)' },
                { k:'Sample rate',    v:'16 kHz' },
                { k:'VAD',           v:'WebRTC agresividad 3' },
                { k:'Echo tail',     v:'5.0s post-TTS' },
                { k:'Silence thresh',v:'400 RMS' },
              ].map(({ k, v }) => (
                <div key={k} style={{ display:'flex', justifyContent:'space-between', padding:'5px 0', borderBottom:`1px solid #06101a` }}>
                  <span style={mono(9, C.textDim)}>{k}</span>
                  <span style={mono(9, C.text)}>{v}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// VOICE PROFILES
// ═══════════════════════════════════════════════════════════════════════════

function VoiceProfilesSection({ sendCommand }: { sendCommand: (cmd: string, payload?: object) => void }) {
  const profiles   = useCYRUSStore(s => s.speakerProfiles)
  const enrollStep = useCYRUSStore(s => s.enrollmentStep)
  const enrollN    = useCYRUSStore(s => s.enrollmentSample)
  const enrollT    = useCYRUSStore(s => s.enrollmentTotal)
  const [guest, setGuest] = useState('')
  const busy = enrollStep !== 'idle' && enrollStep !== 'done'

  return (
    <Panel accent={C.green}>
      <SectionLabel>PERFILES DE HABLANTE</SectionLabel>

      {/* Enrolled list */}
      {profiles.length > 0 ? (
        <div style={{ display:'flex', flexDirection:'column', gap:5, marginBottom:10 }}>
          {profiles.map(sp => (
            <div key={sp.id} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 10px', background:'#020c08', borderRadius:6, border:`1px solid ${C.green}22` }}>
              <span style={{ fontSize:12, color: sp.role === 'owner' ? C.green : C.cyan }}>
                {sp.role === 'owner' ? '★' : '◆'}
              </span>
              <span style={{ ...mono(10, C.text), flex:1 }}>{sp.id}</span>
              <span style={mono(8, C.textDim)}>{sp.role}</span>
              <button disabled={busy} onClick={() => sendCommand('remove_speaker', { speaker_id: sp.id })}
                style={{ ...mono(10, C.red), background:'none', border:'none', cursor:'pointer', opacity: busy ? 0.3 : 1 }}>
                ✕
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ ...mono(9, C.textDim), textAlign:'center', padding:'10px', marginBottom:10 }}>
          Sin perfiles enrollados
        </div>
      )}

      {/* Enrollment progress */}
      {busy && (
        <div style={{ marginBottom:10 }}>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
            <span style={mono(9, C.green)}>Muestra {enrollN}/{enrollT}</span>
          </div>
          <div style={{ height:3, background:'#04080e', borderRadius:2 }}>
            <div style={{ height:'100%', width:`${(enrollN/enrollT)*100}%`, background:`linear-gradient(90deg,${C.green}44,${C.green})`, borderRadius:2, transition:'width 0.3s' }} />
          </div>
        </div>
      )}

      {/* Enroll buttons */}
      <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
        <Btn disabled={busy} color={C.green} onClick={() => sendCommand('start_owner_enrollment', { samples:8 })} style={{ justifyContent:'center' }}>
          ENROLLAR PROPIETARIO (8 muestras)
        </Btn>

        <div style={{ display:'flex', gap:6 }}>
          <Input value={guest} onChange={setGuest} placeholder="nombre del invitado…" />
          <Btn disabled={busy || !guest.trim()} color={C.cyan} onClick={() => { sendCommand('start_guest_enrollment',{name:guest,samples:5}); setGuest('') }}>
            ENROLLAR
          </Btn>
        </div>

        <Btn disabled={busy} color={C.amber} onClick={() => sendCommand('record_tts_reference')} style={{ justifyContent:'center' }}>
          GRABAR VOZ REFERENCIA TTS (20s)
        </Btn>
      </div>
    </Panel>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 3 — VOZ
// ═══════════════════════════════════════════════════════════════════════════

const mdComponents = {
  p:      ({ children }: any) => <p style={{ margin:'2px 0', lineHeight:1.5 }}>{children}</p>,
  strong: ({ children }: any) => <strong style={{ color:C.cyan }}>{children}</strong>,
  code:   ({ children }: any) => <code style={{ fontFamily:'inherit', fontSize:'0.9em', background:'rgba(0,100,160,0.2)', borderRadius:2, padding:'0 3px', color:'#80d4ff' }}>{children}</code>,
}

function TabVoz({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const wakeWords  = useCYRUSStore(s => s.wakeWords)
  const transcript = useCYRUSStore(s => s.transcript)
  const logs       = useCYRUSStore(s => s.logs)
  const wsOn       = useCYRUSStore(s => s.wsConnected)
  const [newWord, setNewWord] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { if (wsOn) sendCommand('list_speakers') }, [wsOn, sendCommand])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior:'smooth' }) }, [transcript])

  const recentASR = logs.filter(l => l.message.includes('ASR [')).slice(-6).reverse()

  const addWord = () => {
    const w = newWord.trim().toLowerCase()
    if (!w) return
    sendCommand('add_wake_word', { word: w })
    setNewWord('')
  }

  return (
    <motion.div initial={{ opacity:0 }} animate={{ opacity:1 }} transition={{ duration:0.25 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:12 }}>

        {/* LEFT — Voice profiles */}
        <VoiceProfilesSection sendCommand={sendCommand} />

        {/* RIGHT — Wake words + ASR */}
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <Panel>
            <SectionLabel>PALABRAS CLAVE</SectionLabel>
            <div style={{ display:'flex', flexWrap:'wrap', gap:6, minHeight:32, marginBottom:10 }}>
              {wakeWords.map(w => (
                <span key={w} onClick={() => sendCommand('remove_wake_word',{word:w})} style={{
                  ...mono(9, C.cyan), padding:'4px 10px', borderRadius:999,
                  background:`${C.cyan}12`, border:`1px solid ${C.cyan}33`, cursor:'pointer',
                }}>
                  {w} ×
                </span>
              ))}
            </div>
            <div style={{ display:'flex', gap:6 }}>
              <Input value={newWord} onChange={setNewWord} onKeyDown={e => e.key==='Enter'&&addWord()} placeholder="agregar variante…" />
              <Btn onClick={addWord} small color={C.cyan}>+ ADD</Btn>
            </div>
          </Panel>

          {/* Recent ASR */}
          <Panel>
            <SectionLabel>ASR RECIENTE</SectionLabel>
            <div style={{ display:'flex', flexDirection:'column', gap:4 }}>
              {recentASR.length === 0 ? (
                <div style={mono(9, C.textDim)}>Sin transcripciones recientes</div>
              ) : recentASR.map(l => {
                const m = l.message.match(/"([^"]+)"/)
                return (
                  <div key={l.id} onClick={() => m?.[1] && setNewWord(m[1])} style={{
                    display:'flex', gap:8, padding:'5px 8px', borderRadius:5,
                    background:'#02060c', border:`1px solid ${C.border}`,
                    cursor: m?.[1] ? 'pointer' : 'default',
                  }}>
                    <span style={mono(8, C.textDim)}>{l.timestamp}</span>
                    <span style={mono(9, C.green)}>{l.message.replace('ASR [es]: ','')}</span>
                  </div>
                )
              })}
            </div>
            {recentASR.length > 0 && (
              <div style={{ ...mono(8, C.textDim), marginTop:6 }}>↑ clic para agregar como wake word</div>
            )}
          </Panel>
        </div>
      </div>

      {/* Conversation history — full width */}
      {transcript.length > 0 && (
        <Panel>
          <SectionLabel>HISTORIAL DE CONVERSACIÓN</SectionLabel>
          <div style={{ maxHeight:280, overflowY:'auto', display:'flex', flexDirection:'column', gap:8 }}>
            {transcript.map(e => (
              <div key={e.id} style={{ display:'flex', flexDirection:'column', alignItems: e.role==='user'?'flex-end':'flex-start' }}>
                <span style={{ ...mono(7, C.textDim), marginBottom:3 }}>
                  {e.role==='user'?'TÚ':'CYRUS'} · {e.timestamp.toLocaleTimeString('es-PE',{hour12:false})}
                </span>
                <div style={{
                  ...mono(10, e.role==='user' ? '#70b8d8' : '#a0d8f0'),
                  maxWidth:'90%', lineHeight:1.5,
                  padding:'8px 12px', borderRadius:8,
                  background: e.role==='user' ? 'rgba(0,80,130,0.2)' : 'rgba(0,30,60,0.4)',
                  border: `1px solid ${e.role==='user' ? '#0a3a5588' : '#0a284088'}`,
                }}>
                  {e.role==='cyrus' ? <ReactMarkdown components={mdComponents}>{e.text}</ReactMarkdown> : e.text}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        </Panel>
      )}
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 4 — API
// ═══════════════════════════════════════════════════════════════════════════

function TabAPI({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const svc = useCYRUSStore(s => s.serviceStatus)
  useEffect(() => { sendCommand('probe_services') }, [sendCommand])

  const services: { key: keyof ServiceStatus; label: string; port: string; note: string }[] = [
    { key:'tts',      label:'TTS Server',    port:'8020', note:'Kokoro / Piper / XTTS' },
    { key:'asr',      label:'ASR Server',    port:'8000', note:'faster-whisper large' },
    { key:'vision',   label:'Vision Server', port:'8001', note:'YOLO + DeepFace' },
    { key:'embedder', label:'Embedder',      port:'8002', note:'sentence-transformers' },
  ]

  return (
    <motion.div initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.25 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
        <div>
          <Panel>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
              <SectionLabel>MICROSERVICIOS</SectionLabel>
              <Btn onClick={() => sendCommand('probe_services')} small color={C.cyan}>VERIFICAR</Btn>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {services.map(({ key, label, port, note }) => {
                const info = svc?.[key]
                const online = info?.online
                const enabled = info?.enabled
                const col2 = !info ? C.textDim : online && enabled ? C.green : online ? C.amber : C.red
                const status = !info ? 'DESCONOCIDO' : online && enabled ? 'ACTIVO' : online ? 'DISPONIBLE' : 'OFFLINE'
                return (
                  <div key={key} style={{ padding:'10px 12px', borderRadius:8, background:'#02060c', border:`1px solid ${col2}22` }}>
                    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
                      <div style={{ width:7,height:7,borderRadius:'50%',background:col2,boxShadow:online?`0 0 5px ${col2}`:'none',flexShrink:0 }} />
                      <span style={mono(10, C.text)}>{label}</span>
                      <span style={{ ...mono(7, col2), marginLeft:'auto', letterSpacing:'0.2em' }}>{status}</span>
                    </div>
                    <div style={{ display:'flex', justifyContent:'space-between' }}>
                      <span style={mono(8, C.textDim)}>:{port}</span>
                      <span style={mono(8, C.textDim)}>{note}</span>
                    </div>
                  </div>
                )
              })}
            </div>
            <div style={{ ...mono(8, C.textDim), marginTop:10 }}>
              DISPONIBLE = activo pero desactivado en config · ACTIVO = en uso
            </div>
          </Panel>
        </div>

        <div>
          <Panel>
            <SectionLabel>ESTADO DEL BACKEND</SectionLabel>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              {[
                { k:'WebSocket', v:'ws://localhost:8765', ok:true },
                { k:'Backend',  v:'Python 3.11 asyncio', ok:true },
                { k:'Ollama',   v:'http://localhost:11434', ok:true },
                { k:'Modelo',   v:'qwen3:8b Q4_K_M', ok:true },
                { k:'ASR',      v:'Whisper small/cpu/int8', ok:true },
                { k:'TTS',      v:'Edge-TTS es-PE-AlexNeural', ok:true },
                { k:'Qdrant',   v:'disabled (no vector DB)', ok:false },
                { k:'HomeAssist',v:'disabled (no token)', ok:false },
              ].map(({ k, v, ok }) => (
                <div key={k} style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0', borderBottom:`1px solid #06101a` }}>
                  <div style={{ width:5,height:5,borderRadius:'50%',background:ok?C.green:C.textDim,flexShrink:0 }} />
                  <span style={{ ...mono(9, C.textDim), width:88, flexShrink:0 }}>{k}</span>
                  <span style={mono(9, C.text)}>{v}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel style={{ marginTop:12 }}>
            <SectionLabel>ACCIONES RÁPIDAS</SectionLabel>
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              <Btn onClick={() => sendCommand('probe_services')} color={C.cyan} style={{ justifyContent:'center' }}>
                VERIFICAR TODOS LOS SERVICIOS
              </Btn>
              <Btn onClick={() => sendCommand('list_ollama_models')} color={C.amber} style={{ justifyContent:'center' }}>
                LISTAR MODELOS OLLAMA
              </Btn>
            </div>
          </Panel>
        </div>
      </div>
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 5 — AGENDA
// ═══════════════════════════════════════════════════════════════════════════

interface PlannerTask { id: number; description: string; status: string; due_hint?: string }

function TabAgenda({ sendCommand }: { sendCommand: (cmd: string, extra?: object) => void }) {
  const [tasks,        setTasks]        = useState<PlannerTask[]>([])
  const [newTask,      setNewTask]      = useState('')
  const [dueHint,      setDueHint]      = useState('')
  const [briefingTime, setBriefingTime] = useState('07:00')
  const [jobs,         setJobs]         = useState<any[]>([])
  const wsOn   = useCYRUSStore(s => s.wsConnected)
  const logs   = useCYRUSStore(s => s.logs)

  useEffect(() => { if (!wsOn) return; sendCommand('planner_list'); sendCommand('scheduler_list') }, [wsOn, sendCommand])
  useEffect(() => { const raw = (window as any).__cyrus_planner_tasks;  if (raw) setTasks(raw) }, [logs])
  useEffect(() => { const raw = (window as any).__cyrus_scheduler_jobs; if (raw) setJobs(raw)  }, [logs])

  const addTask = () => {
    if (!newTask.trim()) return
    sendCommand('planner_add', { description: newTask.trim(), due_hint: dueHint.trim() || undefined })
    setNewTask(''); setDueHint('')
    setTimeout(() => sendCommand('planner_list'), 400)
  }

  const pending = tasks.filter(t => t.status === 'pending')

  return (
    <motion.div initial={{ opacity:0, y:10 }} animate={{ opacity:1, y:0 }} transition={{ duration:0.25 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>

        {/* LEFT — Briefing scheduler */}
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
          <Panel accent={C.amber}>
            <SectionLabel>BRIEFING MATUTINO</SectionLabel>

            <Btn onClick={() => sendCommand('briefing_now')} color={C.amber} style={{ justifyContent:'center', width:'100%', marginBottom:12 }}>
              ☀ EJECUTAR BRIEFING AHORA
            </Btn>

            <div style={{ marginBottom:10 }}>
              <div style={{ ...mono(8, C.textDim), marginBottom:6 }}>HORA DE EJECUCIÓN DIARIA</div>
              <div style={{ display:'flex', gap:8 }}>
                <input type="time" value={briefingTime} onChange={e => setBriefingTime(e.target.value)} style={{
                  ...mono(12, C.textBright), background:'#04080e', border:`1px solid ${C.border}`,
                  borderRadius:7, padding:'8px 10px', outline:'none', flex:1,
                }} />
                <Btn onClick={() => sendCommand('scheduler_set_time',{time:briefingTime})} color={C.cyan}>
                  GUARDAR
                </Btn>
              </div>
            </div>

            {/* Job status */}
            {jobs.map((j: any) => (
              <div key={j.job_id} style={{ padding:'10px 12px', background:'#04080e', borderRadius:8, border:`1px solid ${C.amber}22` }}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                  <span style={mono(9, C.text)}>{j.label}</span>
                  <span style={mono(8, j.status==='running'?C.amber:C.green)}>{j.status.toUpperCase()}</span>
                </div>
                <div style={{ display:'flex', justifyContent:'space-between' }}>
                  <span style={mono(8, C.textDim)}>Ejecuciones: {j.run_count}</span>
                  {j.next_fire && (
                    <span style={mono(8, C.textDim)}>
                      Próximo: {new Date(j.next_fire).toLocaleTimeString('es',{hour:'2-digit',minute:'2-digit'})}
                    </span>
                  )}
                </div>
              </div>
            ))}

            {/* Briefing content preview */}
            <div style={{ marginTop:10, padding:'10px', background:'#02060c', borderRadius:8, border:`1px solid ${C.border}` }}>
              <div style={{ ...mono(8, C.textDim), marginBottom:6 }}>CONTENIDO DEL BRIEFING</div>
              {[
                '📅 Fecha y hora actual',
                '⛅ Clima en Lima (wttr.in)',
                '📋 Tareas pendientes del planner',
                '💻 Estado del sistema (CPU/RAM)',
              ].map(item => (
                <div key={item} style={{ ...mono(9, C.text), padding:'3px 0', borderBottom:`1px solid #060e18` }}>{item}</div>
              ))}
            </div>
          </Panel>
        </div>

        {/* RIGHT — Task planner */}
        <div>
          <Panel accent={C.green}>
            <SectionLabel>PLANIFICADOR DE TAREAS</SectionLabel>

            {/* Add task form */}
            <div style={{ display:'flex', flexDirection:'column', gap:6, marginBottom:12 }}>
              <Input value={newTask} onChange={setNewTask} placeholder="Descripción de la tarea…" onKeyDown={e => e.key==='Enter'&&addTask()} />
              <div style={{ display:'flex', gap:6 }}>
                <Input value={dueHint} onChange={setDueHint} placeholder="Fecha / hint (mañana, viernes…)" style={{ fontSize:9 }} />
                <Btn onClick={addTask} color={C.green} style={{ flexShrink:0 }}>+ AGREGAR</Btn>
              </div>
            </div>

            {/* Stats row */}
            <div style={{ display:'flex', gap:8, marginBottom:10 }}>
              <div style={{ flex:1, textAlign:'center', padding:'8px', background:'#02060c', borderRadius:7, border:`1px solid ${C.border}` }}>
                <div style={mono(18, C.green)}>{pending.length}</div>
                <div style={mono(7, C.textDim)}>PENDIENTES</div>
              </div>
              <div style={{ flex:1, textAlign:'center', padding:'8px', background:'#02060c', borderRadius:7, border:`1px solid ${C.border}` }}>
                <div style={mono(18, C.textDim)}>{tasks.filter(t=>t.status==='done').length}</div>
                <div style={mono(7, C.textDim)}>COMPLETADAS</div>
              </div>
            </div>

            {/* Task list */}
            <div style={{ maxHeight:280, overflowY:'auto', display:'flex', flexDirection:'column', gap:5 }}>
              {pending.length === 0 ? (
                <div style={{ ...mono(10, C.textDim), textAlign:'center', padding:'20px 0' }}>
                  Sin tareas pendientes
                </div>
              ) : pending.map(t => (
                <div key={t.id} style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 10px', borderRadius:7, background:'#020c08', border:`1px solid ${C.green}22` }}>
                  <button onClick={() => { sendCommand('planner_complete',{task_id:t.id}); setTimeout(()=>sendCommand('planner_list'),400) }}
                    title="Marcar completada"
                    style={{ width:16, height:16, borderRadius:'50%', border:`1px solid ${C.green}55`, background:'none', cursor:'pointer', flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
                    <span style={{ fontSize:8, color:C.green }}>✓</span>
                  </button>
                  <span style={{ ...mono(10, C.text), flex:1 }}>#{t.id} {t.description}</span>
                  {t.due_hint && <span style={mono(8, C.amber)}>{t.due_hint}</span>}
                </div>
              ))}
            </div>

            <div style={{ display:'flex', justifyContent:'flex-end', marginTop:10 }}>
              <Btn onClick={() => sendCommand('planner_list')} small color={C.textDim}>ACTUALIZAR</Btn>
            </div>
          </Panel>
        </div>
      </div>
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
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') navigate('/') }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [navigate])

  return (
    <motion.div
      initial={{ opacity:0, filter:'blur(8px)' }}
      animate={{ opacity:1, filter:'blur(0px)' }}
      transition={{ duration:0.4, ease:'easeOut' }}
      style={{ background: C.bg, minHeight:'100vh' }}
    >
      {/* ── Header ── */}
      <div style={{
        position:'sticky', top:0, zIndex:20,
        background: C.bg,
        borderBottom:`1px solid ${C.border}`,
        padding:'12px 24px',
        display:'flex', alignItems:'center', justifyContent:'space-between',
      }}>
        <button onClick={() => navigate('/')} style={{ ...mono(10, C.textDim), background:'none', border:'none', cursor:'pointer', letterSpacing:'0.2em' }}>
          ← VOLVER  <span style={{ ...mono(7, C.textDim) }}>ESC</span>
        </button>

        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <span style={{ ...mono(14, C.cyan), letterSpacing:'0.5em', textShadow:`0 0 18px ${C.cyan}44` }}>C.Y.R.U.S</span>
          <span style={mono(8, C.textDim)}>CONTROL PANEL</span>
        </div>

        <div style={{ width:80 }} />
      </div>

      {/* ── Content ── */}
      <div style={{ maxWidth:960, margin:'0 auto', padding:'16px 20px 40px' }}>
        <TabBar active={tab} onChange={setTab} />

        <AnimatePresence mode="wait">
          {tab === 'SISTEMA' && <TabSistema key="sistema" />}
          {tab === 'CONFIG'  && <TabConfig  key="config"  sendCommand={sendCommand} />}
          {tab === 'VOZ'     && <TabVoz     key="voz"     sendCommand={sendCommand} />}
          {tab === 'API'     && <TabAPI     key="api"     sendCommand={sendCommand} />}
          {tab === 'AGENDA'  && <TabAgenda  key="agenda"  sendCommand={sendCommand} />}
        </AnimatePresence>

        <div style={{ textAlign:'center', marginTop:24 }}>
          <span style={mono(7, C.textDim)}>
            C.Y.R.U.S v1.0 · COGNITIVE SYSTEM FOR REAL-TIME UTILITY & SERVICES
          </span>
        </div>
      </div>
    </motion.div>
  )
}
