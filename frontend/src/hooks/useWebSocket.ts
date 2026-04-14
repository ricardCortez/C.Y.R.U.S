/**
 * C.Y.R.U.S — React hook for WebSocket lifecycle management.
 * Connects on mount, cleans up on unmount, and drives the Zustand store.
 */

import { useEffect, useRef } from 'react'
import { CYRUSWebSocketClient, WSEvent } from '../utils/ws-client'
import { useCYRUSStore, SystemState } from '../store/useCYRUSStore'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8765'

export function useWebSocket(): boolean {
  const clientRef = useRef<CYRUSWebSocketClient | null>(null)
  const {
    setWsConnected,
    setSystemState,
    setStatusMessage,
    addEntry,
    setCurrentTranscript,
    setCurrentResponse,
    setCameraFrame,
  } = useCYRUSStore()

  useEffect(() => {
    const client = new CYRUSWebSocketClient(WS_URL)
    clientRef.current = client

    const unsubscribe = client.onMessage((evt: WSEvent) => {
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
          if (evt.data.message) setStatusMessage(evt.data.message)
          break
        }
        case 'transcript':
          setCurrentTranscript(evt.data.text)
          addEntry({ role: 'user', text: evt.data.text, language: evt.data.language })
          break

        case 'response':
          setCurrentResponse(evt.data.text)
          addEntry({ role: 'cyrus', text: evt.data.text, language: evt.data.language })
          break

        case 'vision':
          if (evt.data.frame) setCameraFrame(evt.data.frame)
          break

        case 'error':
          setStatusMessage(evt.data.message)
          setSystemState('error')
          break
      }
    })

    // Poll connection state for the status indicator
    const interval = setInterval(() => {
      const connected = client.isConnected
      setWsConnected(connected)
      if (!connected) {
        setSystemState('offline')
        setStatusMessage('Reconnecting to C.Y.R.U.S…')
      }
    }, 1500)

    client.connect()

    return () => {
      clearInterval(interval)
      unsubscribe()
      client.disconnect()
    }
  }, [
    setWsConnected, setSystemState, setStatusMessage,
    addEntry, setCurrentTranscript, setCurrentResponse, setCameraFrame,
  ])

  return useCYRUSStore((s) => s.wsConnected)
}
