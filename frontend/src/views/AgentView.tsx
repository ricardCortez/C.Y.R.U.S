/**
 * C.Y.R.U.S — Agent View (route "/")
 * Full-screen immersive particle network. No panels, no distractions.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate }                               from 'react-router-dom'
import { motion, AnimatePresence }                   from 'framer-motion'
import { ParticleNetwork }                           from '../components/ParticleNetwork'
import { AudioVisualizer }                           from '../components/AudioVisualizer'
import { useAudioAnalyser }                          from '../hooks/useAudioAnalyser'
import { useCYRUSStore }                             from '../store/useCYRUSStore'

// ── State color map ────────────────────────────────────────────────────────
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

// ── Response overlay ───────────────────────────────────────────────────────
function ResponseOverlay() {
  const currentResponse = useCYRUSStore(s => s.currentResponse)
  const systemState     = useCYRUSStore(s => s.systemState)
  const visible = systemState === 'speaking' && !!currentResponse

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key={currentResponse}
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

// ── Transcript preview ─────────────────────────────────────────────────────
function TranscriptPreview() {
  const currentTranscript = useCYRUSStore(s => s.currentTranscript)
  const systemState       = useCYRUSStore(s => s.systemState)
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
          <p
            className="font-mono"
            style={{ fontSize: 11, color: '#00ff8888', letterSpacing: '0.06em' }}
          >
            ▶ {currentTranscript}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── State badge ────────────────────────────────────────────────────────────
function StateBadge() {
  const systemState = useCYRUSStore(s => s.systemState)
  const wsConnected = useCYRUSStore(s => s.wsConnected)
  const color = STATE_COLOR[systemState] ?? '#0077bb'

  return (
    <motion.div
      key={systemState}
      animate={{ scale: [1, 1.06, 1] }}
      transition={{ duration: 0.3 }}
      className="absolute top-5 left-1/2 -translate-x-1/2 flex items-center gap-2 pointer-events-none"
    >
      <div
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: color, boxShadow: `0 0 6px ${color}` }}
      />
      <span
        className="font-mono"
        style={{ fontSize: 9, letterSpacing: '0.3em', color: `${color}bb` }}
      >
        {wsConnected ? systemState.toUpperCase() : 'OFFLINE'}
      </span>
    </motion.div>
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

  const color = status === 'active' ? '#00ff88'
              : status === 'error'  ? '#ff3333'
              : '#00d4ff'

  const label = status === 'active' ? 'MIC ON'
              : status === 'error'  ? 'MIC ERR'
              : '🎤 MIC TEST'

  return (
    <button
      onClick={handleClick}
      style={{
        position: 'fixed',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 9999,
        fontFamily: '"Share Tech Mono", monospace',
        fontSize: 11,
        letterSpacing: '0.2em',
        color,
        background: `${color}22`,
        border: `1px solid ${color}`,
        boxShadow: `0 0 14px ${color}55`,
        borderRadius: 4,
        padding: '8px 20px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        pointerEvents: 'all',
      }}
    >
      {status === 'active' && (
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: color, display: 'inline-block',
          animation: 'pulse 1s infinite',
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
  const systemState = useCYRUSStore(s => s.systemState)
  const setSystemState = useCYRUSStore(s => s.setSystemState)

  useEffect(() => { analyserRef.current = analyser }, [analyser])

  // Auto-connect mic when backend sends listening state
  useEffect(() => {
    if (systemState === 'listening') {
      analyserRef.current.connectMic().catch(err => {
        console.warn('[MIC] auto-connect failed:', err)
      })
    }
  }, [systemState])

  // Manual mic test — forces listening state for visual testing
  const handleMicTest = useCallback(async () => {
    await analyserRef.current.connectMic()   // throws on denial → caught in button
    setSystemState('listening')
  }, [setSystemState])

  // Tab hint fades after 4s
  useEffect(() => {
    const id = setTimeout(() => setShowHint(false), 4000)
    return () => clearTimeout(id)
  }, [])

  // Ctrl+, shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === ',' && e.ctrlKey) { e.preventDefault(); navigate('/control') }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  return (
    <div
      className="relative w-screen h-screen overflow-hidden"
      style={{ background: '#05070d' }}
    >
      {/* ── Particle network ── */}
      <div className="absolute inset-0">
        <ParticleNetwork analyser={analyser} />
      </div>

      {/* ── State badge ── */}
      <StateBadge />

      {/* ── Overlays ── */}
      <ResponseOverlay />
      <TranscriptPreview />

      {/* ── Audio visualizer bar — bottom center ── */}
      <div className="absolute bottom-20 left-1/2 -translate-x-1/2 w-full max-w-sm px-6">
        <AudioVisualizer analyser={analyser} />
      </div>

      {/* ── Mic test button ── */}
      <MicTestButton onActivate={handleMicTest} />

      {/* ── Wordmark ── */}
      <div className="absolute bottom-3 left-5 pointer-events-none">
        <span
          className="font-mono font-bold"
          style={{ fontSize: 9, letterSpacing: '0.4em', color: '#00f0ff14' }}
        >
          C.Y.R.U.S
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
