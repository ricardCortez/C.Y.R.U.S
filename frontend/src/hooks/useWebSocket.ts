/**
 * C.Y.R.U.S — React hook for WebSocket lifecycle management.
 * Singleton client — safe to call from multiple components.
 */

import { useEffect, useCallback } from 'react'
import { CYRUSWebSocketClient, WSEvent } from '../utils/ws-client'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8765'

// Module-level singleton — shared across all hook instances
const _client = new CYRUSWebSocketClient(WS_URL)
let _bootstrapped = false

export function useWebSocket(): { connected: boolean; sendCommand: (cmd: string, extra?: object) => void } {
  const {
    setWsConnected,
    setSystemState,
    setStatusMessage,
    addEntry,
    setCurrentTranscript,
    setCurrentResponse,
    setCameraFrame,
    addLog,
    setWakeWords,
    setEnrollment,
  } = useCYRUSStore()

  useEffect(() => {
    if (_bootstrapped) return   // only wire up once
    _bootstrapped = true

    _client.onMessage((evt: WSEvent) => {
      switch (evt.event) {
        case 'status': {
          const stateMap: Record<string, SystemState> = {
            connected:    'connected',
            idle:         'idle',
            listening:    'listening',
            transcribing: 'transcribing',
            thinking:     'thinking',
            speaking:     'speaking',
            error:        'error',
          }
          const mapped = stateMap[evt.data.state] ?? 'idle'
          setSystemState(mapped)
          setWsConnected(true)
          if (evt.data.message) {
            setStatusMessage(evt.data.message)
            addLog('info', evt.data.message)
          } else {
            addLog('info', `STATE → ${evt.data.state.toUpperCase()}`)
          }
          break
        }
        case 'transcript':
          setCurrentTranscript(evt.data.text)
          addEntry({ role: 'user', text: evt.data.text, language: evt.data.language })
          addLog('info', `YOU: ${evt.data.text}`)
          break

        case 'response':
          setCurrentResponse(evt.data.text)
          addEntry({ role: 'cyrus', text: evt.data.text, language: evt.data.language })
          addLog('info', `CYRUS: ${evt.data.text}`)
          break

        case 'vision':
          if (evt.data.frame) setCameraFrame(evt.data.frame)
          break

        case 'debug': {
          const lvl = evt.data.level ?? 'info'
          addLog(lvl === 'warn' ? 'warn' : 'info', evt.data.text)
          break
        }

        case 'wake_words':
          setWakeWords(evt.data.words)
          break

        case 'enrollment':
          setEnrollment(evt.data)
          break

        case 'error':
          setStatusMessage(evt.data.message)
          setSystemState('error')
          addLog('error', evt.data.message)
          break
      }
    })

    // Poll connection state
    const manualStates = new Set(['listening', 'transcribing', 'thinking', 'speaking'])
    const interval = setInterval(() => {
      const connected = _client.isConnected
      setWsConnected(connected)
      if (!connected) {
        const cur = useCYRUSStore.getState().systemState
        if (!manualStates.has(cur)) {
          setSystemState('offline')
          setStatusMessage('Reconnecting to C.Y.R.U.S…')
        }
      }
    }, 1500)

    _client.connect()

    return () => {
      clearInterval(interval)
      // Don't disconnect the singleton on unmount — it lives for the app lifetime
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const sendCommand = useCallback((cmd: string, extra: object = {}) => {
    _client.send({ type: 'command', cmd, ...extra })
  }, [])

  const connected = useCYRUSStore((s) => s.wsConnected)
  return { connected, sendCommand }
}
