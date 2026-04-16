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

export interface TranscriptEntry {
  id:        number
  role:      'user' | 'cyrus'
  text:      string
  timestamp: Date
  language?: string
}

export interface SystemStats {
  cpu:        number
  ram:        number
  vram:       number
  gpuTemp:    number
  gpuName:    string
  uptime:     number
  ttsBackend: string
}

interface CYRUSStore {
  // Connection
  systemState:   SystemState
  wsConnected:   boolean
  statusMessage: string

  // Conversation
  transcript:        TranscriptEntry[]
  currentTranscript: string
  currentResponse:   string
  lastResponse:      string

  // Vision
  cameraFrame: string | null

  // Logs / debug
  logs: LogEntry[]

  // Wake words (synced from backend)
  wakeWords: string[]

  // Enrollment
  enrollmentStep:    string
  enrollmentSample:  number
  enrollmentTotal:   number
  enrollmentResults: string[]

  // System stats (real — from backend)
  systemStats: SystemStats | null

  // TTS speed (local copy — synced to backend)
  ttsSpeed: number

  // Visual params
  particleCount:  number
  bloomIntensity: number
  orbSpeed:       number

  // Actions
  setSystemState:       (s: SystemState) => void
  setWsConnected:       (v: boolean) => void
  setStatusMessage:     (m: string) => void
  addEntry:             (entry: { role: 'user' | 'cyrus'; text: string; language?: string }) => void
  addTranscript:        (entry: { role: 'user' | 'assistant'; text: string }) => void
  setCurrentTranscript: (t: string) => void
  setCurrentResponse:   (t: string) => void
  setLastResponse:      (t: string) => void
  setCameraFrame:       (frame: string | null) => void
  addLog:               (level: LogLevel, message: string) => void
  clearLogs:            () => void
  setWakeWords:         (words: string[]) => void
  setEnrollment:        (data: { step?: string; sample?: number; total?: number; heard?: string; added?: string[] }) => void
  setSystemStats:       (s: SystemStats) => void
  setTtsSpeed:          (v: number) => void
  setParticleCount:     (n: number) => void
  setBloomIntensity:    (v: number) => void
  setOrbSpeed:          (v: number) => void
}

let seq = 0

export const useCYRUSStore = create<CYRUSStore>((set) => ({
  // Connection
  systemState:   'offline',
  wsConnected:   false,
  statusMessage: '',

  // Conversation
  transcript:        [],
  currentTranscript: '',
  currentResponse:   '',
  lastResponse:      '',

  // Vision
  cameraFrame: null,

  // Logs
  logs: [],

  // Wake words
  wakeWords: [],

  // Enrollment
  enrollmentStep:    'idle',
  enrollmentSample:  0,
  enrollmentTotal:   5,
  enrollmentResults: [],

  // System stats
  systemStats: null,

  // TTS speed
  ttsSpeed: 0.92,

  // Visual params
  particleCount:  200,
  bloomIntensity: 1.4,
  orbSpeed:       1.0,

  // Actions
  setSystemState:   (s) => set({ systemState: s }),
  setWsConnected:   (v) => set({ wsConnected: v }),
  setStatusMessage: (m) => set({ statusMessage: m }),

  addEntry: (entry) => set((st) => ({
    transcript: [...st.transcript, {
      id:        ++seq,
      role:      entry.role,
      text:      entry.text,
      timestamp: new Date(),
      language:  entry.language,
    }],
  })),

  addTranscript: (entry) => set((st) => ({
    transcript: [...st.transcript, {
      id:        ++seq,
      role:      entry.role === 'assistant' ? 'cyrus' : 'user',
      text:      entry.text,
      timestamp: new Date(),
    }],
  })),

  setCurrentTranscript: (t) => set({ currentTranscript: t }),
  setCurrentResponse:   (t) => set({ currentResponse: t, lastResponse: t }),
  setLastResponse:      (t) => set({ lastResponse: t }),
  setCameraFrame:       (f) => set({ cameraFrame: f }),

  addLog: (level, message) => set((st) => {
    const entry: LogEntry = {
      id:        ++seq,
      timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false }),
      level,
      message,
    }
    const logs = [...st.logs, entry]
    return { logs: logs.length > 200 ? logs.slice(-200) : logs }
  }),

  clearLogs:    () => set({ logs: [] }),
  setWakeWords: (words) => set({ wakeWords: words }),

  setEnrollment: (data) => set((st) => {
    const next: Partial<typeof st> = {}
    if (data.step   !== undefined) next.enrollmentStep   = data.step
    if (data.total  !== undefined) next.enrollmentTotal  = data.total
    if (data.sample !== undefined) next.enrollmentSample = data.sample
    if (data.step === 'start') next.enrollmentResults = []
    if (data.step === 'result' && data.heard)
      next.enrollmentResults = [...st.enrollmentResults, data.heard]
    return next
  }),

  setSystemStats: (s) => set({ systemStats: s }),
  setTtsSpeed:    (v) => set({ ttsSpeed: Math.min(2.0, Math.max(0.5, v)) }),

  setParticleCount:  (n) => set({ particleCount: Math.min(400, Math.max(100, n)) }),
  setBloomIntensity: (v) => set({ bloomIntensity: Math.min(2.5, Math.max(0.5, v)) }),
  setOrbSpeed:       (v) => set({ orbSpeed: Math.min(3, Math.max(0.1, v)) }),
}))
