/**
 * C.Y.R.U.S — Main Application Component.
 * Layout: Transcript left | Hologram center | Diagnostics right.
 */

import { useState, useEffect } from 'react'
import { useWebSocket }       from './hooks/useWebSocket'
import { HologramView }       from './components/HologramView'
import { TranscriptPanel }    from './components/TranscriptPanel'
import { DebugPanel }         from './components/DebugPanel'
import { CameraStream }       from './components/CameraStream'
import { WaveformVisualizer } from './components/WaveformVisualizer'
import { useCYRUSStore }      from './store/useCYRUSStore'

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

// ── Scrolling header ticker ───────────────────────────────────────────────

function HeaderTicker() {
  const [offset, setOffset] = useState(0)
  const items = [
    'COGNITIVE SYSTEM v1.0',
    '///',
    'AUDIO PIPELINE ACTIVE',
    '///',
    'WHISPER ASR ENGINE',
    '///',
    'OLLAMA LLM BACKEND',
    '///',
    'PHASE 3 — AUDIO · VISION · MEMORY',
    '///',
  ]
  const text = items.join('  ·  ')

  useEffect(() => {
    const id = setInterval(() => setOffset(o => (o + 1) % (text.length * 7)), 50)
    return () => clearInterval(id)
  }, [text.length])

  return (
    <div
      className="overflow-hidden flex-1"
      style={{ maxWidth: 280, mask: 'linear-gradient(90deg, transparent, black 20%, black 80%, transparent)' }}
    >
      <span
        className="font-mono text-[9px] tracking-widest whitespace-nowrap inline-block"
        style={{
          color: '#0a2030',
          transform: `translateX(-${offset}px)`,
          transition: 'transform 50ms linear',
        }}
      >
        {text + '  ·  ' + text}
      </span>
    </div>
  )
}

// ── Wake word badge ───────────────────────────────────────────────────────

function WakeWordRow({ word }: { word: string }) {
  return (
    <div
      className="px-3 py-1 rounded font-mono text-[10px] text-center"
      style={{ background: 'rgba(0,30,60,0.3)', border: '1px solid #05151f', color: '#0a2030' }}
    >
      {word}
    </div>
  )
}

// ── Vision tab toggle ─────────────────────────────────────────────────────

type CenterTab = 'hologram' | 'vision'

// ── Main App ──────────────────────────────────────────────────────────────

export default function App() {
  useWebSocket()
  const systemState  = useCYRUSStore(s => s.systemState)
  const wsConnected  = useCYRUSStore(s => s.wsConnected)
  const entryCount   = useCYRUSStore(s => s.transcript.length)
  const [tab, setTab] = useState<CenterTab>('hologram')

  const stateColor    = STATE_COLOR[systemState] ?? '#0077bb'
  const dotConnected  = wsConnected && systemState !== 'offline'

  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{ background: '#040d1a', color: '#b0e8ff', fontFamily: '"Exo 2", sans-serif' }}
    >
      {/* ══════════════════════════ HEADER ════════════════════════════ */}
      <header
        className="flex items-center justify-between px-5 shrink-0"
        style={{
          height: 42,
          borderBottom: '1px solid #080e1a',
          background: 'rgba(4,8,20,0.97)',
          boxShadow: '0 1px 0 #0a1a28',
        }}
      >
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background: dotConnected ? '#00ff88' : '#ff3333',
                boxShadow:  dotConnected ? '0 0 8px #00ff88' : '0 0 8px #ff3333',
              }}
            />
            {dotConnected && (
              <div
                className="absolute inset-0 rounded-full animate-ping"
                style={{ background: '#00ff8822', animationDuration: '2s' }}
              />
            )}
          </div>
          <span
            className="font-mono font-bold tracking-[0.4em] text-sm"
            style={{ color: '#00d4ff', textShadow: '0 0 10px #00d4ff66' }}
          >
            C.Y.R.U.S
          </span>
        </div>

        {/* Scrolling ticker */}
        <HeaderTicker />

        {/* State badge */}
        <div
          className="flex items-center gap-2 px-3 py-1 rounded font-mono text-[10px] tracking-widest"
          style={{
            background: `${stateColor}0d`,
            border:     `1px solid ${stateColor}33`,
            color:       stateColor,
            boxShadow:  `0 0 10px ${stateColor}18`,
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: stateColor, boxShadow: `0 0 4px ${stateColor}` }}
          />
          {STATE_LABEL[systemState] ?? systemState.toUpperCase()}
        </div>
      </header>

      {/* ══════════════════════════ MAIN ══════════════════════════════ */}
      <main className="flex-1 flex overflow-hidden" style={{ minHeight: 0 }}>

        {/* ── LEFT — Transcript ───────────────────────────────────── */}
        <div
          className="flex flex-col shrink-0 overflow-hidden"
          style={{
            width: 300,
            borderRight: '1px solid #080e1a',
            background: 'linear-gradient(180deg, #040d1a 0%, #03090f 100%)',
          }}
        >
          {/* Panel label */}
          <div
            className="flex items-center justify-between px-4 py-2 shrink-0"
            style={{ borderBottom: '1px solid #08101a' }}
          >
            <span className="font-mono text-[9px] tracking-[0.25em]" style={{ color: '#0a2030' }}>
              CONVERSATION LOG
            </span>
            <span className="font-mono text-[9px]" style={{ color: '#0a2030' }}>
              {entryCount} entries
            </span>
          </div>
          <div className="flex-1 overflow-hidden">
            <TranscriptPanel />
          </div>
        </div>

        {/* ── CENTER — Hologram ───────────────────────────────────── */}
        <div
          className="flex-1 flex flex-col items-center overflow-hidden"
          style={{
            background: 'radial-gradient(ellipse 70% 60% at 50% 40%, #060f1e 0%, #040d1a 100%)',
            borderRight: '1px solid #080e1a',
            minWidth: 0,
          }}
        >
          {/* Tab bar */}
          <div className="flex w-full shrink-0" style={{ borderBottom: '1px solid #08101a' }}>
            {(['hologram', 'vision'] as CenterTab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="flex-1 py-2 font-mono text-[9px] tracking-widest uppercase transition-colors"
                style={{
                  background:   tab === t ? 'rgba(0,212,255,0.04)' : 'transparent',
                  color:        tab === t ? '#00d4ff' : '#0a2030',
                  borderBottom: tab === t ? '1px solid #00d4ff44' : '1px solid transparent',
                  marginBottom: -1,
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === 'vision' ? (
            <div className="flex-1 flex flex-col items-center justify-center p-6 w-full">
              <CameraStream />
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-between p-4 w-full overflow-hidden">

              {/* Hologram — fills available space, max 420px */}
              <div className="flex-1 flex items-center justify-center w-full" style={{ minHeight: 0 }}>
                <div style={{ width: 'min(420px, 100%)', height: 'min(420px, 100%)' }}>
                  <HologramView />
                </div>
              </div>

              {/* Waveform + wake words pinned to bottom */}
              <div className="w-full flex flex-col gap-3 shrink-0" style={{ maxWidth: 440 }}>
                {/* Waveform */}
                <div
                  className="w-full px-3 py-3 rounded"
                  style={{ background: 'rgba(0,10,25,0.7)', border: '1px solid #08101a' }}
                >
                  <WaveformVisualizer />
                </div>

                {/* Wake words */}
                <div>
                  <p className="font-mono text-[8px] tracking-widest text-center mb-1.5" style={{ color: '#08101a' }}>
                    WAKE WORDS
                  </p>
                  <div className="flex gap-2 justify-center flex-wrap">
                    {['"Hola C.Y.R.U.S"', '"Hey C.Y.R.U.S"', '"Oye C.Y.R.U.S"'].map(w => (
                      <WakeWordRow key={w} word={w} />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT — Diagnostics HUD ─────────────────────────────── */}
        <div
          className="shrink-0 overflow-hidden"
          style={{ width: 260 }}
        >
          <DebugPanel />
        </div>
      </main>

      {/* ══════════════════════════ FOOTER ════════════════════════════ */}
      <footer
        className="flex items-center justify-between px-5 shrink-0"
        style={{
          height: 28,
          borderTop: '1px solid #080e1a',
          background: 'rgba(4,8,20,0.97)',
        }}
      >
        <span className="font-mono text-[8px]" style={{ color: '#05101a' }}>
          © 2025 · Personal Automation · Ricardo
        </span>
        <span className="font-mono text-[8px]" style={{ color: '#05101a' }}>
          Cognitive sYstem for Real-time Utility &amp; Services
        </span>
      </footer>
    </div>
  )
}
