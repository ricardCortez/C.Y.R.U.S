// frontend/src/store/useCYRUSStore.ts
import { create } from 'zustand'

export type SystemState =
  | 'offline' | 'connected' | 'idle'
  | 'listening' | 'transcribing' | 'thinking'
  | 'speaking' | 'error'

export type LogLevel = 'info' | 'warn' | 'error'

export interface LogEntry {
  id:        number
  timestamp: string
  level:     LogLevel
  message:   string
}

interface CYRUSStore {
  // Existing
  systemState:  SystemState
  wsConnected:  boolean
  transcript:   { role: 'user' | 'assistant'; text: string }[]
  lastResponse: string

  // New
  logs:           LogEntry[]
  particleCount:  number
  bloomIntensity: number
  orbSpeed:       number

  // Actions
  setSystemState:    (s: SystemState) => void
  setWsConnected:    (v: boolean) => void
  addTranscript:     (entry: { role: 'user' | 'assistant'; text: string }) => void
  setLastResponse:   (t: string) => void
  addLog:            (level: LogLevel, message: string) => void
  clearLogs:         () => void
  setParticleCount:  (n: number) => void
  setBloomIntensity: (v: number) => void
  setOrbSpeed:       (v: number) => void
}

let logSeq = 0

export const useCYRUSStore = create<CYRUSStore>((set) => ({
  systemState:    'offline',
  wsConnected:    false,
  transcript:     [],
  lastResponse:   '',
  logs:           [],
  particleCount:  200,
  bloomIntensity: 1.4,
  orbSpeed:       1.0,

  setSystemState:  (s) => set({ systemState: s }),
  setWsConnected:  (v) => set({ wsConnected: v }),
  addTranscript:   (e) => set((st) => ({ transcript: [...st.transcript, e] })),
  setLastResponse: (t) => set({ lastResponse: t }),

  addLog: (level, message) => set((st) => {
    const entry: LogEntry = {
      id:        ++logSeq,
      timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false }),
      level,
      message,
    }
    const logs = [...st.logs, entry]
    return { logs: logs.length > 200 ? logs.slice(-200) : logs }
  }),

  clearLogs:         () => set({ logs: [] }),
  setParticleCount:  (n) => set({ particleCount: Math.min(400, Math.max(100, n)) }),
  setBloomIntensity: (v) => set({ bloomIntensity: Math.min(2.5, Math.max(0.5, v)) }),
  setOrbSpeed:       (v) => set({ orbSpeed: Math.min(3, Math.max(0.1, v)) }),
}))
