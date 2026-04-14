/**
 * C.Y.R.U.S — Main Application Component.
 * JARVIS-style layout: hologram + waveform left | transcript center | diagnostics right.
 */

import { useState } from 'react'
import { useWebSocket }         from './hooks/useWebSocket'
import { HologramView }         from './components/HologramView'
import { TranscriptPanel }      from './components/TranscriptPanel'
import { DebugPanel }           from './components/DebugPanel'
import { CameraStream }         from './components/CameraStream'
import { WaveformVisualizer }   from './components/WaveformVisualizer'
import { useCYRUSStore }        from './store/useCYRUSStore'

type LeftTab = 'hologram' | 'vision'

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

export default function App() {
  useWebSocket()
  const systemState  = useCYRUSStore(s => s.systemState)
  const wsConnected  = useCYRUSStore(s => s.wsConnected)
  const [leftTab, setLeftTab] = useState<LeftTab>('hologram')

  const stateColor   = STATE_COLOR[systemState] ?? '#0077bb'
  const dotConnected = wsConnected && systemState !== 'offline'

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: '#040d1a', color: '#b0e8ff', fontFamily: '"Exo 2", sans-serif' }}
    >
      {/* ═══════════════════════════════ HEADER ════════════════════════════ */}
      <header
        className="flex items-center justify-between px-6 py-2 shrink-0"
        style={{ borderBottom: '1px solid #0a3050', background: 'rgba(4,13,26,0.95)' }}
      >
        {/* Left — brand */}
        <div className="flex items-center gap-4">
          {/* Animated connection dot */}
          <div className="relative">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background:  dotConnected ? '#00ff88' : '#ff3333',
                boxShadow:   dotConnected ? '0 0 6px #00ff88' : '0 0 6px #ff3333',
              }}
            />
            {dotConnected && (
              <div
                className="absolute inset-0 rounded-full animate-ping"
                style={{ background: '#00ff8833' }}
              />
            )}
          </div>

          <h1
            className="font-mono font-bold tracking-[0.4em] text-lg"
            style={{ color: '#00d4ff', textShadow: '0 0 12px #00d4ff88' }}
          >
            C.Y.R.U.S
          </h1>
          <span className="font-mono text-xs" style={{ color: '#1a3040' }}>
            COGNITIVE SYSTEM v1.0
          </span>
        </div>

        {/* Center — live state badge */}
        <div
          className="flex items-center gap-2 px-3 py-1 rounded font-mono text-xs tracking-widest uppercase"
          style={{
            background:  `${stateColor}11`,
            border:      `1px solid ${stateColor}44`,
            color:        stateColor,
            boxShadow:   `0 0 8px ${stateColor}22`,
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: stateColor, boxShadow: `0 0 4px ${stateColor}` }}
          />
          {systemState}
        </div>

        {/* Right — subtitle */}
        <span className="font-mono text-xs" style={{ color: '#0a2030' }}>
          Cognitive sYstem for Real-time Utility &amp; Services
        </span>
      </header>

      {/* ═══════════════════════════════ MAIN ══════════════════════════════ */}
      <main
        className="flex-1 flex overflow-hidden"
        style={{ minHeight: 0 }}
      >
        {/* ── LEFT — Hologram / Vision panel ─────────────────────────────── */}
        <div
          className="flex flex-col shrink-0"
          style={{
            width: 360,
            borderRight: '1px solid #0a3050',
            background: 'linear-gradient(180deg, #040d1a 0%, #060f1e 100%)',
          }}
        >
          {/* Tab bar */}
          <div className="flex shrink-0" style={{ borderBottom: '1px solid #0a3050' }}>
            {(['hologram', 'vision'] as LeftTab[]).map(tab => (
              <button
                key={tab}
                onClick={() => setLeftTab(tab)}
                className="flex-1 py-2 font-mono text-xs tracking-widest uppercase transition-colors"
                style={{
                  background:   leftTab === tab ? 'rgba(0,212,255,0.05)' : 'transparent',
                  color:        leftTab === tab ? '#00d4ff' : '#1a3040',
                  borderBottom: leftTab === tab ? '1px solid #00d4ff' : '1px solid transparent',
                  marginBottom: -1,
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 flex flex-col items-center justify-start pt-4 pb-4 px-4 gap-4 overflow-hidden">
            {leftTab === 'hologram' ? (
              <>
                {/* Hologram */}
                <HologramView />

                {/* Waveform */}
                <div
                  className="w-full px-2 py-3 rounded"
                  style={{ background: 'rgba(0,20,40,0.5)', border: '1px solid #0a3050' }}
                >
                  <WaveformVisualizer />
                </div>

                {/* Wake word hints */}
                <div className="w-full">
                  <p className="font-mono text-[9px] tracking-widest text-center mb-2"
                     style={{ color: '#1a3040' }}>
                    WAKE WORDS
                  </p>
                  <div className="flex flex-col gap-1">
                    {['"Hola C.Y.R.U.S"', '"Hey C.Y.R.U.S"', '"Oye C.Y.R.U.S"'].map(w => (
                      <div
                        key={w}
                        className="px-2 py-1 rounded font-mono text-xs text-center"
                        style={{
                          background: 'rgba(0,40,80,0.2)',
                          border: '1px solid #0a2030',
                          color: '#1a3040',
                        }}
                      >
                        {w}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="w-full flex flex-col gap-3">
                <CameraStream />
                <p className="font-mono text-[9px] tracking-widest text-center"
                   style={{ color: '#1a3040' }}>
                  VISION PIPELINE
                </p>
              </div>
            )}
          </div>
        </div>

        {/* ── CENTER — Transcript ─────────────────────────────────────────── */}
        <div
          className="flex-1 flex flex-col overflow-hidden"
          style={{ background: '#040d1a', borderRight: '1px solid #0a3050', minWidth: 0 }}
        >
          <TranscriptPanel />
        </div>

        {/* ── RIGHT — Diagnostics ─────────────────────────────────────────── */}
        <div
          className="shrink-0 overflow-y-auto"
          style={{ width: 240, background: '#040d1a' }}
        >
          <DebugPanel />
        </div>
      </main>

      {/* ═══════════════════════════════ FOOTER ════════════════════════════ */}
      <footer
        className="flex items-center justify-between px-6 py-1.5 shrink-0"
        style={{ borderTop: '1px solid #0a3050', background: 'rgba(4,13,26,0.95)' }}
      >
        <span className="font-mono text-[10px]" style={{ color: '#0a2030' }}>
          © Personal Automation — Ricardo
        </span>
        <span className="font-mono text-[10px]" style={{ color: '#0a2030' }}>
          Phase 3 — Audio · Vision · Memory
        </span>
      </footer>
    </div>
  )
}
