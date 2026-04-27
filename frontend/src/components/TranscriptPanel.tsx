/**
 * JARVIS — Transcript panel.
 * Displays the conversation history (user input + JARVIS responses).
 */

import { useEffect, useRef } from 'react'
import { useJARVISStore, TranscriptEntry } from '../store/useJARVISStore'

function EntryRow({ entry }: { entry: TranscriptEntry }) {
  const isUser = entry.role === 'user'
  return (
    <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
      {/* Role label */}
      <span className="font-mono text-xs tracking-widest" style={{ color: '#406080' }}>
        {isUser ? 'YOU' : 'JARVIS'}{' '}
        <span style={{ color: '#203040' }}>
          {entry.timestamp.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      </span>
      {/* Bubble */}
      <div
        className="max-w-xs lg:max-w-sm px-3 py-2 rounded font-mono text-sm leading-relaxed"
        style={
          isUser
            ? { background: 'rgba(0,100,160,0.2)', border: '1px solid #0a4060', color: '#80c8e8' }
            : { background: 'rgba(0,40,80,0.4)', border: '1px solid #004060', color: '#b0e8ff',
                boxShadow: '0 0 8px rgba(0,212,255,0.1)' }
        }
      >
        {entry.text}
      </div>
    </div>
  )
}

export function TranscriptPanel() {
  const transcript = useJARVISStore((s) => s.transcript)
  const systemState = useJARVISStore((s) => s.systemState)
  const currentTranscript = useJARVISStore((s) => s.currentTranscript)
  const endRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript])

  return (
    <div className="flex flex-col h-full" style={{ minHeight: 0 }}>
      {/* Panel header */}
      <div
        className="flex items-center justify-between px-4 py-2 shrink-0"
        style={{ borderBottom: '1px solid #0a4060' }}
      >
        <span className="font-mono text-xs tracking-widest" style={{ color: '#004060' }}>
          ── TRANSCRIPT LOG
        </span>
        <span className="font-mono text-xs" style={{ color: '#203040' }}>
          {transcript.length} entries
        </span>
      </div>

      {/* Entries */}
      <div className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3" style={{ minHeight: 0 }}>
        {transcript.length === 0 ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="font-mono text-xs text-center" style={{ color: '#203040' }}>
              Say <span style={{ color: '#00d4ff' }}>"Hola JARVIS"</span> to begin
            </p>
          </div>
        ) : (
          transcript.map((entry) => <EntryRow key={entry.id} entry={entry} />)
        )}

        {/* Live indicator while listening */}
        {systemState === 'listening' && (
          <div className="flex items-start gap-2">
            <span className="font-mono text-xs" style={{ color: '#406080' }}>YOU</span>
            <div
              className="px-3 py-2 rounded font-mono text-sm"
              style={{ background: 'rgba(0,100,160,0.15)', border: '1px dashed #0a4060', color: '#406080' }}
            >
              <span className="animate-pulse">●</span> Listening…
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Current transcript preview */}
      {currentTranscript && systemState !== 'idle' && (
        <div
          className="px-4 py-2 shrink-0 font-mono text-xs"
          style={{ borderTop: '1px solid #0a4060', color: '#00d4ff88' }}
        >
          ▶ {currentTranscript}
        </div>
      )}
    </div>
  )
}
