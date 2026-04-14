/**
 * C.Y.R.U.S — Main Application Component.
 * CSS Grid layout: equal side panels (280px) + flex-1 center.
 * Hologram is geometrically centered on screen.
 */

import { useState, useEffect } from 'react'
import { useWebSocket }       from './hooks/useWebSocket'
import { HologramView }       from './components/HologramView'
import { TranscriptPanel }    from './components/TranscriptPanel'
import { DebugPanel }         from './components/DebugPanel'
import { CameraStream }       from './components/CameraStream'
import { WaveformVisualizer } from './components/WaveformVisualizer'
import { useCYRUSStore }      from './store/useCYRUSStore'

const SIDE_W = 280   // px — both panels equal → hologram truly centered

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

const STATE_LABEL: Record<string, string> = {
  offline:      'OFFLINE',
  connected:    'STANDBY',
  idle:         'IDLE',
  listening:    'LISTENING',
  transcribing: 'TRANSCRIBING',
  thinking:     'PROCESSING',
  speaking:     'SPEAKING',
  error:        'ERROR',
}

// ── Scrolling ticker ──────────────────────────────────────────────────────

function Ticker() {
  const [pos, setPos] = useState(0)
  const SEG = '  ·  '
  const text = [
    'COGNITIVE SYSTEM v1.0', 'AUDIO PIPELINE',
    'WHISPER ASR', 'OLLAMA LLM BACKEND',
    'PHASE 3 — AUDIO · VISION · MEMORY',
    'QDRANT VECTOR DB', 'EDGE-TTS SYNTHESIS',
  ].join(SEG) + SEG

  useEffect(() => {
    const id = setInterval(() => setPos(p => (p + 1) % (text.length * 8)), 60)
    return () => clearInterval(id)
  }, [text.length])

  return (
    <div className="overflow-hidden" style={{ width: 220, WebkitMaskImage: 'linear-gradient(90deg,transparent,#000 18%,#000 82%,transparent)' }}>
      <span
        className="font-mono whitespace-nowrap inline-block"
        style={{ fontSize: 8, letterSpacing: '0.18em', color: '#0d2030', transform: `translateX(-${pos}px)` }}
      >
        {text + text}
      </span>
    </div>
  )
}

// ── Backend-offline banner ────────────────────────────────────────────────

function OfflineBanner() {
  return (
    <div
      className="flex items-center justify-center gap-3 py-1.5 font-mono shrink-0"
      style={{ background: '#1a000a', borderBottom: '1px solid #3a0020' }}
    >
      <span style={{ fontSize: 9, color: '#ff3333', letterSpacing: '0.2em' }}>
        ⚠ BACKEND OFFLINE
      </span>
      <span style={{ fontSize: 8, color: '#6a2030', letterSpacing: '0.1em' }}>
        Iniciar:  python -m backend.core.cyrus_engine
      </span>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────

type Tab = 'hologram' | 'vision'

export default function App() {
  useWebSocket()
  const systemState = useCYRUSStore(s => s.systemState)
  const wsConnected = useCYRUSStore(s => s.wsConnected)
  const entryCount  = useCYRUSStore(s => s.transcript.length)
  const [tab, setTab] = useState<Tab>('hologram')

  const sc  = STATE_COLOR[systemState]  ?? '#0077bb'
  const dot = wsConnected && systemState !== 'offline'

  return (
    <div
      className="h-screen flex flex-col overflow-hidden select-none"
      style={{ background: '#040d1a', color: '#b0e8ff', fontFamily: '"Exo 2", sans-serif' }}
    >

      {/* ═══════════════════════ HEADER ══════════════════════════════ */}
      <header
        className="flex items-center shrink-0 px-4 gap-4"
        style={{ height: 40, background: '#030810', borderBottom: '1px solid #07111a' }}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5" style={{ width: SIDE_W - 16, flexShrink: 0 }}>
          <div className="relative w-2 h-2">
            <div className="w-2 h-2 rounded-full" style={{ background: dot ? '#00ff88' : '#ff3333', boxShadow: dot ? '0 0 8px #00ff88' : '0 0 6px #ff3333' }} />
            {dot && <div className="absolute inset-0 rounded-full animate-ping" style={{ background: '#00ff8818' }} />}
          </div>
          <span className="font-mono font-bold tracking-[0.35em] text-sm" style={{ color: '#00d4ff', textShadow: '0 0 12px #00d4ff55' }}>
            C.Y.R.U.S
          </span>
          <span className="font-mono" style={{ fontSize: 8, color: '#071520', letterSpacing: '0.15em' }}>AI CORE</span>
        </div>

        {/* Center ticker */}
        <div className="flex-1 flex justify-center">
          <Ticker />
        </div>

        {/* State badge */}
        <div className="flex items-center justify-end gap-3" style={{ width: SIDE_W - 16, flexShrink: 0 }}>
          <div
            className="flex items-center gap-1.5 px-3 py-1 rounded font-mono"
            style={{ fontSize: 10, letterSpacing: '0.2em', background: `${sc}10`, border: `1px solid ${sc}30`, color: sc, boxShadow: `0 0 12px ${sc}15` }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: sc, boxShadow: `0 0 4px ${sc}` }} />
            {STATE_LABEL[systemState]}
          </div>
        </div>
      </header>

      {/* Backend offline banner */}
      {!wsConnected && <OfflineBanner />}

      {/* ═══════════════════════ MAIN GRID ═══════════════════════════ */}
      <main
        className="flex-1 overflow-hidden"
        style={{
          display: 'grid',
          gridTemplateColumns: `${SIDE_W}px 1fr ${SIDE_W}px`,
          minHeight: 0,
        }}
      >
        {/* ── LEFT — Transcript ─────────────────────────────────────── */}
        <div
          className="flex flex-col overflow-hidden"
          style={{ borderRight: '1px solid #07111a', background: '#030810' }}
        >
          <div className="flex items-center justify-between px-3 py-2 shrink-0" style={{ borderBottom: '1px solid #07111a' }}>
            <span className="font-mono" style={{ fontSize: 8, letterSpacing: '0.25em', color: '#0a1e2a' }}>CONVERSATION LOG</span>
            <span className="font-mono" style={{ fontSize: 8, color: '#0a1e2a' }}>{entryCount} entries</span>
          </div>
          <div className="flex-1 overflow-hidden">
            <TranscriptPanel />
          </div>
        </div>

        {/* ── CENTER — Hologram + Waveform ──────────────────────────── */}
        <div
          className="flex flex-col overflow-hidden"
          style={{ background: 'radial-gradient(ellipse 80% 70% at 50% 38%, #061020 0%, #040d1a 100%)' }}
        >
          {/* Tab bar */}
          <div className="flex shrink-0" style={{ borderBottom: '1px solid #07111a' }}>
            {(['hologram', 'vision'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="flex-1 py-2 font-mono transition-colors"
                style={{
                  fontSize: 8, letterSpacing: '0.3em', textTransform: 'uppercase',
                  background:   tab === t ? '#00d4ff08' : 'transparent',
                  color:        tab === t ? '#00d4ff'   : '#0a1e2a',
                  borderBottom: tab === t ? '1px solid #00d4ff40' : '1px solid transparent',
                  marginBottom: -1,
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === 'vision' ? (
            <div className="flex-1 flex items-center justify-center p-4">
              <CameraStream />
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center overflow-hidden" style={{ padding: '16px 24px 12px' }}>

              {/* ── Hologram — centered, square, max 420px ── */}
              <div className="flex-1 flex items-center justify-center w-full" style={{ minHeight: 0 }}>
                <div
                  style={{
                    width:  'min(420px, min(100%, calc(100vh - 280px)))',
                    height: 'min(420px, min(100%, calc(100vh - 280px)))',
                  }}
                >
                  <HologramView />
                </div>
              </div>

              {/* ── Waveform ── */}
              <div className="w-full shrink-0 mt-3" style={{ maxWidth: 460 }}>
                <div className="px-3 py-2.5 rounded" style={{ background: '#020810', border: '1px solid #07111a' }}>
                  <WaveformVisualizer />
                </div>
              </div>

              {/* ── Wake words ── */}
              <div className="w-full shrink-0 mt-2" style={{ maxWidth: 460 }}>
                <p className="font-mono text-center mb-1" style={{ fontSize: 7, letterSpacing: '0.25em', color: '#071420' }}>
                  WAKE WORDS · SAY TO ACTIVATE MICROPHONE
                </p>
                <div className="flex gap-2 justify-center flex-wrap">
                  {['"Hola C.Y.R.U.S"', '"Hey C.Y.R.U.S"', '"Oye C.Y.R.U.S"'].map(w => (
                    <div
                      key={w}
                      className="px-2.5 py-1 rounded font-mono text-center"
                      style={{ fontSize: 9, background: '#020810', border: '1px solid #06101a', color: '#0d1e2a' }}
                    >
                      {w}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT — Diagnostics HUD ───────────────────────────────── */}
        <div
          className="overflow-hidden"
          style={{ borderLeft: '1px solid #07111a', background: '#030810' }}
        >
          <DebugPanel />
        </div>
      </main>

      {/* ═══════════════════════ FOOTER ══════════════════════════════ */}
      <footer
        className="flex items-center justify-between px-4 shrink-0"
        style={{ height: 24, background: '#030810', borderTop: '1px solid #07111a' }}
      >
        <span className="font-mono" style={{ fontSize: 7, color: '#06101a' }}>© 2025 Ricardo — Personal Automation</span>
        <span className="font-mono" style={{ fontSize: 7, color: '#06101a' }}>Cognitive sYstem for Real-time Utility &amp; Services</span>
      </footer>
    </div>
  )
}
