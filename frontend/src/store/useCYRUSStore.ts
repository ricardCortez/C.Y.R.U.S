/**
 * C.Y.R.U.S — Zustand global state store.
 */

import { create } from 'zustand'

export type SystemState =
  | 'offline'
  | 'connected'
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'thinking'
  | 'speaking'
  | 'error'

export interface TranscriptEntry {
  id: string
  role: 'user' | 'cyrus'
  text: string
  language: string
  timestamp: Date
}

interface CYRUSStore {
  // Connection
  wsConnected: boolean
  setWsConnected: (v: boolean) => void

  // System state
  systemState: SystemState
  setSystemState: (s: SystemState) => void
  statusMessage: string
  setStatusMessage: (m: string) => void

  // Conversation
  transcript: TranscriptEntry[]
  addEntry: (entry: Omit<TranscriptEntry, 'id' | 'timestamp'>) => void
  clearTranscript: () => void

  // Current processing
  currentTranscript: string
  setCurrentTranscript: (t: string) => void
  currentResponse: string
  setCurrentResponse: (r: string) => void
}

let _entryCounter = 0

export const useCYRUSStore = create<CYRUSStore>((set) => ({
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),

  systemState: 'offline',
  setSystemState: (s) => set({ systemState: s }),
  statusMessage: 'Connecting…',
  setStatusMessage: (m) => set({ statusMessage: m }),

  transcript: [],
  addEntry: (entry) =>
    set((state) => ({
      transcript: [
        ...state.transcript,
        {
          ...entry,
          id: `entry-${++_entryCounter}`,
          timestamp: new Date(),
        },
      ].slice(-50), // keep last 50 entries
    })),
  clearTranscript: () => set({ transcript: [] }),

  currentTranscript: '',
  setCurrentTranscript: (t) => set({ currentTranscript: t }),
  currentResponse: '',
  setCurrentResponse: (r) => set({ currentResponse: r }),
}))
