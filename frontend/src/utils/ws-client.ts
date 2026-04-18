/**
 * C.Y.R.U.S — WebSocket client utility.
 * Manages connection, reconnection, and message parsing.
 */

export type WSEvent =
  | { event: 'transcript';  data: { text: string; language: string } }
  | { event: 'response';    data: { text: string; language: string } }
  | { event: 'status';      data: { state: string; message?: string } }
  | { event: 'error';       data: { message: string } }
  | { event: 'metrics';     data: Record<string, unknown> }
  | { event: 'vision';      data: { frame?: string } }
  | { event: 'debug';       data: { text: string; level?: 'info' | 'warn' | 'ok' } }
  | { event: 'wake_words';  data: { words: string[] } }
  | { event: 'enrollment';   data: { step: string; sample?: number; total?: number; heard?: string; added?: string[] } }
  | { event: 'available_models'; data: { models: { name: string; compatible: boolean; compatibility: string }[]; current: string } }
  | { event: 'system_stats'; data: { cpu: number; ram: number; vram: number; gpu_temp: number; gpu_name: string; uptime: number; tts_backend: string } }
  | { event: 'service_status'; data: {
      tts:      { enabled: boolean; online: boolean; host: string }
      asr:      { enabled: boolean; online: boolean; host: string }
      vision:   { enabled: boolean; online: boolean; host: string }
      embedder: { enabled: boolean; online: boolean; host: string }
    }
  }
  | { event: 'speaker_profiles'; data: { speakers: { id: string; role: string }[] } }

export type WSEventHandler = (evt: WSEvent) => void

const RECONNECT_DELAY_MS = 2000
const MAX_RECONNECT_ATTEMPTS = Infinity   // always retry — local backend may start late

export class CYRUSWebSocketClient {
  private ws: WebSocket | null = null
  private handlers: WSEventHandler[] = []
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private shouldReconnect = true
  private queue: object[] = []

  constructor(private readonly url: string = 'ws://localhost:8765') {}

  connect(): void {
    this.shouldReconnect = true
    this._open()
  }

  disconnect(): void {
    this.shouldReconnect = false
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
    this.queue = []
  }

  onMessage(handler: WSEventHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler)
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  send(payload: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    } else {
      this.queue.push(payload)
      console.info('[C.Y.R.U.S] WS not open yet, queued command', payload)
    }
  }

  private _flushQueue(): void {
    while (this.queue.length && this.ws?.readyState === WebSocket.OPEN) {
      const payload = this.queue.shift()!
      this.ws.send(JSON.stringify(payload))
    }
  }

  private _open(): void {
    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.info('[C.Y.R.U.S] WebSocket connected')
        this.reconnectAttempts = 0
        this._flushQueue()
      }

      this.ws.onmessage = (ev: MessageEvent) => {
        try {
          const parsed = JSON.parse(ev.data as string) as WSEvent
          this.handlers.forEach(h => h(parsed))
        } catch {
          console.warn('[C.Y.R.U.S] Could not parse WS message:', ev.data)
        }
      }

      this.ws.onclose = () => {
        console.warn('[C.Y.R.U.S] WebSocket disconnected')
        this._scheduleReconnect()
      }

      this.ws.onerror = () => {
        console.error('[C.Y.R.U.S] WebSocket error')
      }
    } catch (err) {
      console.error('[C.Y.R.U.S] WebSocket open error:', err)
      this._scheduleReconnect()
    }
  }

  private _scheduleReconnect(): void {
    if (!this.shouldReconnect) return
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('[C.Y.R.U.S] Max reconnect attempts reached')
      return
    }
    this.reconnectAttempts++
    const delay = RECONNECT_DELAY_MS * Math.min(this.reconnectAttempts, 5)
    console.info(`[C.Y.R.U.S] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`)
    this.reconnectTimer = setTimeout(() => this._open(), delay)
  }
}
