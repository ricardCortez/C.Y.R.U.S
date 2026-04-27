/**
 * JARVIS — Agent View (route "/")
 *
 * Improvements:
 *  1. ThinkingOverlay — animated dots during "thinking" state
 *  2. PersistentHUD   — last 2 conversation turns always visible
 *  3. IdleHint        — wake-word hint fades in after 30s idle
 *  4. TTS badge       — active backend shown in corner
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate }                               from 'react-router-dom'
import { motion, AnimatePresence }                   from 'framer-motion'
import { JarvisOrb }                                  from '../components/JarvisOrb'
import { AudioVisualizer }                           from '../components/AudioVisualizer'
import { useAudioAnalyser }                          from '../hooks/useAudioAnalyser'
import { useJARVISStore }                             from '../store/useJARVISStore'

// ── 1. Response overlay (speaking) + thinking dots ────────────────────────
function ResponseOverlay() {
  const currentResponse = useJARVISStore(s => s.currentResponse)
  const systemState     = useJARVISStore(s => s.systemState)

  const showResponse = (systemState === 'speaking' || systemState === 'idle') && !!currentResponse
  const showThinking = systemState === 'thinking'

  return (
    <AnimatePresence mode="wait">
      {showThinking && (
        <motion.div
          key="thinking"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.35 }}
          className="absolute bottom-28 left-1/2 -translate-x-1/2 pointer-events-none flex flex-col items-center gap-3"
        >
          {/* Neural activity label */}
          <motion.span
            className="font-mono"
            style={{ fontSize: 8, letterSpacing: '0.4em', color: '#ff8c0066' }}
            animate={{ opacity: [0.4, 0.9, 0.4] }}
            transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
          >
            ACTIVIDAD NEURONAL
          </motion.span>
          {/* Pulse dots — staggered wave */}
          <div className="flex items-center gap-2">
            {[0,1,2,3,4].map(i => (
              <motion.div
                key={i}
                className="rounded-full"
                style={{ width: i === 2 ? 8 : 5, height: i === 2 ? 8 : 5, background: '#ff8c00' }}
                animate={{ opacity: [0.15, 1, 0.15], scale: [0.7, 1.3, 0.7],
                           boxShadow: ['0 0 0px #ff8c0000', '0 0 10px #ff8c00cc', '0 0 0px #ff8c0000'] }}
                transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.22, ease: 'easeInOut' }}
              />
            ))}
          </div>
        </motion.div>
      )}

      {showResponse && (
        <motion.div
          key={currentResponse?.slice(0, 20)}
          initial={{ opacity: 0, y: 12, filter: 'blur(6px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: -8, filter: 'blur(4px)' }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="absolute bottom-28 left-1/2 -translate-x-1/2 w-full max-w-lg px-6 pointer-events-none text-center"
        >
          <p
            className="font-mono leading-relaxed"
            style={{ fontSize: 13, color: '#00f0ffcc', textShadow: '0 0 20px #00f0ff44', letterSpacing: '0.05em' }}
          >
            {currentResponse}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── 2. Persistent HUD — last 2 conversation turns ─────────────────────────
function ConversationHUD() {
  const transcript  = useJARVISStore(s => s.transcript)
  const systemState = useJARVISStore(s => s.systemState)

  // Don't show during active interaction states — response overlay handles that
  const hide = systemState === 'speaking' || systemState === 'thinking' || systemState === 'transcribing'
  const last2 = transcript.slice(-2)

  if (hide || last2.length === 0) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="absolute bottom-28 left-1/2 -translate-x-1/2 w-full max-w-lg px-6 pointer-events-none"
    >
      <div className="flex flex-col gap-1.5">
        {last2.map(entry => (
          <div
            key={entry.id}
            className={`flex gap-2 font-mono ${entry.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <span
              style={{
                fontSize: 10,
                letterSpacing: '0.04em',
                lineHeight: 1.5,
                maxWidth: '80%',
                color: entry.role === 'user' ? '#80c8e866' : '#00f0ff55',
                textAlign: entry.role === 'user' ? 'right' : 'left',
              }}
            >
              {entry.text.length > 90 ? entry.text.slice(0, 90) + '…' : entry.text}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  )
}

// ── Transcript preview (transcribing state) ────────────────────────────────
function TranscriptPreview() {
  const currentTranscript = useJARVISStore(s => s.currentTranscript)
  const systemState       = useJARVISStore(s => s.systemState)
  const visible = systemState === 'transcribing' && !!currentTranscript

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute bottom-28 left-1/2 -translate-x-1/2 w-full max-w-lg px-6 pointer-events-none text-center"
        >
          <p className="font-mono" style={{ fontSize: 11, color: '#00ff8888', letterSpacing: '0.06em' }}>
            ▶ {currentTranscript}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── State badge ────────────────────────────────────────────────────────────
function StateBadge() {
  const systemState = useJARVISStore(s => s.systemState)
  const wsConnected = useJARVISStore(s => s.wsConnected)

  // Jarvis-style: lowercase status, bottom-center above label
  const label: Record<string, string> = {
    idle: 'listening...', listening: 'listening...', transcribing: 'listening...',
    thinking: 'thinking...', speaking: '', connected: '', offline: '', error: 'error',
  }
  const statusText = wsConnected ? (label[systemState] ?? systemState) : ''

  return (
    <div className="absolute bottom-10 left-1/2 -translate-x-1/2 pointer-events-none">
      <span
        className="font-mono"
        style={{
          fontSize: 13,
          letterSpacing: '0.15em',
          color: `rgba(14,165,233,0.5)`,
          transition: 'opacity 0.5s ease',
          opacity: statusText ? 1 : 0,
        }}
      >
        {statusText}
      </span>
    </div>
  )
}

// ── 3. Idle hint — shows after 30s with no activity ───────────────────────
function IdleHint() {
  const systemState = useJARVISStore(s => s.systemState)
  const wakeWords   = useJARVISStore(s => s.wakeWords)
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const primaryWakeWord = wakeWords[0] ?? 'hola jarvis'

  useEffect(() => {
    clearTimeout(timerRef.current)
    setVisible(false)

    if (systemState === 'idle') {
      timerRef.current = setTimeout(() => setVisible(true), 30_000)
    }
    return () => clearTimeout(timerRef.current)
  }, [systemState])

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <div className="text-center">
            <p
              className="font-mono"
              style={{ fontSize: 10, letterSpacing: '0.35em', color: '#00f0ff18' }}
            >
              DI
            </p>
            <p
              className="font-mono font-bold mt-1"
              style={{ fontSize: 14, letterSpacing: '0.4em', color: '#00f0ff28', textShadow: '0 0 30px #00f0ff11' }}
            >
              "{primaryWakeWord.toUpperCase()}"
            </p>
            <p
              className="font-mono mt-1"
              style={{ fontSize: 9, letterSpacing: '0.25em', color: '#00f0ff12' }}
            >
              PARA ACTIVAR
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── 4. TTS backend badge ───────────────────────────────────────────────────
function TTSBadge() {
  const stats = useJARVISStore(s => s.systemStats)
  if (!stats) return null

  const backend = stats.ttsBackend.toUpperCase()
  const color = backend === 'PIPER' ? '#00ff88' : backend === 'KOKORO' ? '#00d4ff' : '#ff8c00'

  return (
    <div
      className="absolute font-mono pointer-events-none"
      style={{
        bottom: 14, right: 14,
        fontSize: 7, letterSpacing: '0.25em',
        color: `${color}55`,
        display: 'flex', alignItems: 'center', gap: 4,
      }}
    >
      <div style={{ width: 4, height: 4, borderRadius: '50%', background: color, opacity: 0.4 }} />
      TTS {backend}
    </div>
  )
}

// ── Mic test button ────────────────────────────────────────────────────────
type MicStatus = 'idle' | 'active' | 'error'

function MicTestButton({ onActivate }: { onActivate: () => Promise<void> }) {
  const [status, setStatus] = useState<MicStatus>('idle')

  const handleClick = async () => {
    if (status === 'active') return
    setStatus('idle')
    try {
      await onActivate()
      setStatus('active')
    } catch (e) {
      console.error('[MIC]', e)
      setStatus('error')
      setTimeout(() => setStatus('idle'), 3000)
    }
  }

  const color = status === 'active' ? '#00ff88' : status === 'error' ? '#ff3333' : '#00d4ff'
  const label = status === 'active' ? 'MIC ON' : status === 'error' ? 'MIC ERR' : 'MIC TEST'

  return (
    <button
      onClick={handleClick}
      style={{
        position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
        zIndex: 9999, fontFamily: '"Share Tech Mono", monospace', fontSize: 11,
        letterSpacing: '0.2em', color, background: `${color}22`, border: `1px solid ${color}`,
        boxShadow: `0 0 14px ${color}55`, borderRadius: 4, padding: '8px 20px',
        cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, pointerEvents: 'all',
      }}
    >
      {status === 'active' && (
        <span style={{
          width: 7, height: 7, borderRadius: '50%', background: color,
          display: 'inline-block', animation: 'pulse 1s infinite',
        }} />
      )}
      {label}
    </button>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────
export function AgentView() {
  const analyser    = useAudioAnalyser()
  const analyserRef = useRef(analyser)
  const [showHint, setShowHint] = useState(true)
  const navigate    = useNavigate()
  const systemState    = useJARVISStore(s => s.systemState)
  const setSystemState = useJARVISStore(s => s.setSystemState)

  useEffect(() => { analyserRef.current = analyser }, [analyser])

  useEffect(() => {
    if (systemState === 'listening') {
      analyserRef.current.connectMic().catch(err => console.warn('[MIC] auto-connect failed:', err))
    }
  }, [systemState])

  const handleMicTest = useCallback(async () => {
    await analyserRef.current.connectMic()
    setSystemState('listening')
  }, [setSystemState])

  useEffect(() => {
    const id = setTimeout(() => setShowHint(false), 4000)
    return () => clearTimeout(id)
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === ',' && e.ctrlKey) { e.preventDefault(); navigate('/control') }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: '#050508' }}>
      {/* ── Jarvis orb — floating particle cloud ── */}
      <div className="absolute inset-0">
        <JarvisOrb analyser={analyser} />
      </div>

      {/* ── State badge ── */}
      <StateBadge />

      {/* ── Idle hint ── */}
      <IdleHint />

      {/* ── Overlays ── */}
      <ResponseOverlay />
      <TranscriptPreview />
      <ConversationHUD />

      {/* ── Audio visualizer bar ── */}
      <div className="absolute bottom-20 left-1/2 -translate-x-1/2 w-full max-w-sm px-6">
        <AudioVisualizer analyser={analyser} />
      </div>

      {/* ── Mic test button ── */}
      <MicTestButton onActivate={handleMicTest} />

      {/* ── TTS backend badge ── */}
      <TTSBadge />

      {/* ── Wordmark — centered bottom, Jarvis-style ── */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 pointer-events-none">
        <span className="font-mono font-bold" style={{ fontSize: 10, letterSpacing: '0.4em', color: 'rgba(14,165,233,0.2)' }}>
          JARVIS
        </span>
      </div>

      {/* ── Tab hint ── */}
      <AnimatePresence>
        {showHint && (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 1 } }}
            onClick={() => navigate('/control')}
            className="absolute top-5 right-14 font-mono cursor-pointer"
            style={{ fontSize: 8, letterSpacing: '0.2em', color: '#00f0ff33', background: 'none', border: 'none' }}
          >
            TAB — CONTROL →
          </motion.button>
        )}
      </AnimatePresence>

      {/* ── Settings button ── */}
      <motion.button
        whileHover={{ opacity: 0.7 }}
        onClick={() => navigate('/control')}
        className="absolute top-5 right-5 font-mono cursor-pointer"
        style={{ fontSize: 8, letterSpacing: '0.2em', color: '#00f0ff22', background: 'none', border: 'none', padding: 0 }}
      >
        ⚙
      </motion.button>
    </div>
  )
}
