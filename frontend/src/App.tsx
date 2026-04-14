/**
 * C.Y.R.U.S — Main Application Component.
 * Holographic UI with three-panel layout: hologram | transcript | debug.
 */

import { useState } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { HologramView } from './components/HologramView'
import { TranscriptPanel } from './components/TranscriptPanel'
import { DebugPanel } from './components/DebugPanel'
import { CameraStream } from './components/CameraStream'
import { useCYRUSStore } from './store/useCYRUSStore'

type LeftTab = 'hologram' | 'vision'

export default function App() {
  useWebSocket()
  const systemState = useCYRUSStore((s) => s.systemState)
  const wsConnected = useCYRUSStore((s) => s.wsConnected)
  const [leftTab, setLeftTab] = useState<LeftTab>('hologram')

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: '#040d1a', color: '#b0e8ff', fontFamily: '"Exo 2", sans-serif' }}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header
        className="flex items-center justify-between px-6 py-3 shrink-0"
        style={{ borderBottom: '1px solid #0a4060', background: '#040d1a' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-2 h-2 rounded-full"
            style={{
              background: wsConnected ? '#00ff88' : '#ff4444',
              boxShadow: wsConnected ? '0 0 6px #00ff88' : '0 0 6px #ff4444',
            }}
          />
          <h1
            className="font-mono font-bold tracking-[0.3em] text-lg"
            style={{ color: '#00d4ff', textShadow: '0 0 10px #00d4ff66' }}
          >
            C.Y.R.U.S
          </h1>
          <span className="font-mono text-xs" style={{ color: '#004060' }}>
            COGNITIVE SYSTEM v1.0
          </span>
        </div>

        <div className="flex items-center gap-4">
          <span className="font-mono text-xs uppercase tracking-widest" style={{ color: '#004060' }}>
            {systemState}
          </span>
          <div className="font-mono text-xs" style={{ color: '#203040' }}>
            Cognitive sYstem for Real-time Utility & Services
          </div>
        </div>
      </header>

      {/* ── Main grid ──────────────────────────────────────────────────── */}
      <main className="flex-1 grid" style={{ gridTemplateColumns: '320px 1fr 260px', minHeight: 0 }}>

        {/* Left — Hologram / Vision tabs */}
        <div
          className="flex flex-col shrink-0"
          style={{
            borderRight: '1px solid #0a4060',
            background: 'linear-gradient(180deg, #040d1a 0%, #071224 100%)',
          }}
        >
          {/* Tab bar */}
          <div className="flex shrink-0" style={{ borderBottom: '1px solid #0a4060' }}>
            {(['hologram', 'vision'] as LeftTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setLeftTab(tab)}
                className="flex-1 py-2 font-mono text-xs tracking-widest uppercase transition-colors"
                style={{
                  background: leftTab === tab ? 'rgba(0,212,255,0.06)' : 'transparent',
                  color: leftTab === tab ? '#00d4ff' : '#1a3040',
                  borderBottom: leftTab === tab ? '1px solid #00d4ff' : '1px solid transparent',
                  marginBottom: -1,
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 flex flex-col items-center justify-center p-6">
            {leftTab === 'hologram' ? (
              <>
                <HologramView />
                {/* Wake word hint */}
                <div className="mt-8 text-center w-full">
                  <p className="font-mono text-xs" style={{ color: '#203040' }}>WAKE WORDS</p>
                  <div className="mt-2 flex flex-col gap-1">
                    {['"Hola C.Y.R.U.S"', '"Hey C.Y.R.U.S"', '"C.Y.R.U.S"'].map((w) => (
                      <div
                        key={w}
                        className="px-2 py-1 rounded font-mono text-xs text-center"
                        style={{ background: 'rgba(0,40,80,0.3)', border: '1px solid #0a2030', color: '#004060' }}
                      >
                        {w}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="w-full">
                <CameraStream />
                <p
                  className="mt-3 font-mono text-xs text-center tracking-widest"
                  style={{ color: '#1a3040' }}
                >
                  VISION PIPELINE
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Centre — Transcript */}
        <div
          className="flex flex-col overflow-hidden"
          style={{
            background: '#040d1a',
            borderRight: '1px solid #0a4060',
          }}
        >
          <TranscriptPanel />
        </div>

        {/* Right — Debug */}
        <div
          className="overflow-y-auto"
          style={{ background: '#040d1a' }}
        >
          <DebugPanel />
        </div>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer
        className="flex items-center justify-between px-6 py-2 shrink-0"
        style={{ borderTop: '1px solid #0a4060', background: '#040d1a' }}
      >
        <span className="font-mono text-xs" style={{ color: '#1a3040' }}>
          © Personal Automation | C.Y.R.U.S
        </span>
        <span className="font-mono text-xs" style={{ color: '#1a3040' }}>
          Phase 2 — Vision + Object & Face Detection
        </span>
      </footer>
    </div>
  )
}
