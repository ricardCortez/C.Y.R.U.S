/**
 * C.Y.R.U.S — Agent View (route "/")
 * Full-screen immersive particle network. No panels, no distractions.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate }                  from 'react-router-dom'
import { motion, AnimatePresence }      from 'framer-motion'
import { ParticleNetwork }              from '../components/ParticleNetwork'
import { AudioVisualizer }              from '../components/AudioVisualizer'
import { useAudioAnalyser }             from '../hooks/useAudioAnalyser'
import { useCYRUSStore }                from '../store/useCYRUSStore'

// ── State color map ─────────────────────────────────────────────────────────
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

// ── Current-turn response overlay ──────────────────────────────────────────
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

// ── Listening transcript preview ────────────────────────────────────────────
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

// ── State badge — minimal, top center ─────────────────────────────────────
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

// ── Main ───────────────────────────────────────────────────────────────────
export function AgentView() {
  const analyser          = useAudioAnalyser()
  const analyserRef       = useRef(analyser)
  const [showHint, setShowHint] = useState(true)
  const navigate          = useNavigate()
  const systemState       = useCYRUSStore(s => s.systemState)

  // Wire mic during listening state
  useEffect(() => {
    analyserRef.current = analyser
  }, [analyser])

  useEffect(() => {
    if (systemState === 'listening') {
      analyserRef.current.connectMic().catch(() => {/* permission denied — fallback to simulation */})
    }
  }, [systemState])

  // Tab hint fades after 4s
  useEffect(() => {
    const id = setTimeout(() => setShowHint(false), 4000)
    return () => clearTimeout(id)
  }, [])

  // Ctrl+, shortcut → /control
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
      {/* ── Particle network — fills entire screen ── */}
      <div className="absolute inset-0">
        <ParticleNetwork analyser={analyser} />
      </div>

      {/* ── State badge — top center ── */}
      <StateBadge />

      {/* ── Response / transcript overlays ── */}
      <ResponseOverlay />
      <TranscriptPreview />

      {/* ── Audio visualizer — bottom center ── */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-full max-w-sm px-6">
        <AudioVisualizer analyser={analyser} />
      </div>

      {/* ── C.Y.R.U.S wordmark — very subtle, bottom left ── */}
      <div className="absolute bottom-5 left-5 pointer-events-none">
        <span
          className="font-mono font-bold"
          style={{ fontSize: 9, letterSpacing: '0.4em', color: '#00f0ff18' }}
        >
          C.Y.R.U.S
        </span>
      </div>

      {/* ── Tab hint — bottom right, fades after 4s ── */}
      <AnimatePresence>
        {showHint && (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 1 } }}
            onClick={() => navigate('/control')}
            className="absolute bottom-5 right-5 font-mono cursor-pointer"
            style={{ fontSize: 8, letterSpacing: '0.2em', color: '#00f0ff33', background: 'none', border: 'none' }}
          >
            TAB — CONTROL PANEL →
          </motion.button>
        )}
      </AnimatePresence>

      {/* ── Persistent control panel button (always visible, minimal) ── */}
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
