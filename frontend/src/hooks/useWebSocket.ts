/**
 * JARVIS — React hook for WebSocket lifecycle management.
 * Singleton client — safe to call from multiple components.
 */

import { useEffect, useCallback } from 'react'
import { JARVISWebSocketClient, WSEvent } from '../utils/ws-client'
import { useJARVISStore, SystemState, SystemStats, ServiceStatus, LogLevel } from '../store/useJARVISStore'

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8765'

// Module-level singleton — shared across all hook instances
const _client = new JARVISWebSocketClient(WS_URL)
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
    setSystemStats,
    setAvailableModels,
    setCurrentModel,
    setServiceStatus,
  } = useJARVISStore()

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
          addEntry({ role: 'jarvis', text: evt.data.text, language: evt.data.language })
          addLog('info', `JARVIS: ${evt.data.text}`)
          break

        case 'vision':
          if (evt.data.frame) setCameraFrame(evt.data.frame)
          break

        case 'debug': {
          const lvl: string = evt.data.level ?? 'info'
          const level: LogLevel = lvl === 'warn' ? 'warn' : lvl === 'error' ? 'error' : lvl === 'ok' ? 'ok' : 'info'
          addLog(level, evt.data.text)
          break
        }

        case 'wake_words':
          setWakeWords(evt.data.words)
          break

        case 'enrollment':
          setEnrollment(evt.data)
          break

        case 'available_models':
          setAvailableModels(evt.data.models)
          setCurrentModel(evt.data.current)
          break

        case 'system_stats': {
          const d = evt.data
          setSystemStats({
            cpu:        d.cpu        ?? 0,
            ram:        d.ram        ?? 0,
            vram:       d.vram       ?? 0,
            gpuTemp:    d.gpu_temp   ?? 0,
            gpuName:    d.gpu_name   ?? 'GPU',
            uptime:     d.uptime     ?? 0,
            ttsBackend: d.tts_backend ?? 'unknown',
          } as SystemStats)
          break
        }

        case 'service_status':
          setServiceStatus(evt.data as ServiceStatus)
          break

        case 'speaker_profiles':
          useJARVISStore.getState().setSpeakerProfiles(evt.data.speakers ?? [])
          break

        case 'planner_tasks':
          ;(window as any).__jarvis_planner_tasks = evt.data.tasks ?? []
          // Trigger re-render by adding a silent debug entry
          addLog('info', `📋 Tareas: ${(evt.data.tasks ?? []).length} pendientes`)
          break

        case 'scheduler_jobs':
          ;(window as any).__jarvis_scheduler_jobs = evt.data.jobs ?? []
          addLog('info', `☀ Scheduler: ${(evt.data.jobs ?? []).length} jobs`)
          break

        case 'scheduler_event':
          if (evt.data.event === 'start') addLog('info', `☀ Iniciando: ${evt.data.label}`)
          if (evt.data.event === 'done')  addLog('ok', `☀ Completado: ${evt.data.label} (run #${evt.data.run_count})`)
          if (evt.data.event === 'error') addLog('warn', `☀ Error: ${evt.data.label} — ${evt.data.last_error}`)
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
        const cur = useJARVISStore.getState().systemState
        if (!manualStates.has(cur)) {
          setSystemState('offline')
          setStatusMessage('Reconnecting to JARVIS…')
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

  const connected = useJARVISStore((s) => s.wsConnected)
  return { connected, sendCommand }
}
