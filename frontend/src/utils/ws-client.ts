/**
 * C.Y.R.U.S — WebSocket client utility.
 * Manages connection, reconnection, and message parsing.
 */

export type WSEvent =
  | { event: 'transcript'; data: { text: string; language: string } }
  | { event: 'response';   data: { text: string; language: string } }
  | { event: 'status';     data: { state: string; message?: string } }
  | { event: 'error';      data: { message: string } }
  | { event: 'metrics';    data: Record<string, unknown> }
  | { event: 'vision';     data: { frame?: string } }

export type WSEventHandler = (evt: WSEvent) => void

const RECONNECT_DELAY_MS = 2000
const MAX_RECONNECT_ATTEMPTS = 10

export class CYRUSWebSocketClient {
  private ws: WebSocket | null = null
  private handlers: WSEventHandler[] = []
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private shouldReconnect = true

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

  private _open(): void {
    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.info('[C.Y.R.U.S] WebSocket connected')
        this.reconnectAttempts = 0
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
