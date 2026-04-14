// frontend/src/hooks/useAudioAnalyser.ts
import { useEffect, useRef, useCallback } from 'react'

export interface AudioAnalyserHandle {
  /** 0–1 bass amplitude (bins 0-8) */
  getBass: () => number
  /** 0–1 mid amplitude (bins 8-24) */
  getMid:  () => number
  /** Connect to an HTMLAudioElement (TTS output) */
  connectElement: (el: HTMLAudioElement) => void
  /** Connect to microphone */
  connectMic: () => Promise<void>
  disconnect: () => void
}

/**
 * Returns a stable handle with getBass/getMid that read the latest
 * FFT data each call. Safe to call from a Three.js render loop.
 */
export function useAudioAnalyser(): AudioAnalyserHandle {
  const ctxRef      = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const dataRef     = useRef<Uint8Array | null>(null)
  const sourceRef   = useRef<MediaStreamAudioSourceNode | MediaElementAudioSourceNode | null>(null)

  const ensureCtx = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new AudioContext()
      const analyser = ctxRef.current.createAnalyser()
      analyser.fftSize = 64
      analyser.connect(ctxRef.current.destination)
      analyserRef.current = analyser
      dataRef.current = new Uint8Array(analyser.frequencyBinCount)
    }
    return { ctx: ctxRef.current, analyser: analyserRef.current! }
  }, [])

  const getFreqData = useCallback(() => {
    if (analyserRef.current && dataRef.current && dataRef.current.length > 0) {
      analyserRef.current.getByteFrequencyData(dataRef.current as any)
    }
    return dataRef.current || new Uint8Array(0)
  }, [])

  const getBass = useCallback(() => {
    const d = getFreqData()
    if (d.length === 0) return 0
    let sum = 0
    const end = Math.min(8, d.length)
    for (let i = 0; i < end; i++) sum += d[i]
    return sum / (end * 255)
  }, [getFreqData])

  const getMid = useCallback(() => {
    const d = getFreqData()
    if (d.length === 0) return 0
    let sum = 0
    const start = Math.min(8, d.length)
    const end   = Math.min(24, d.length)
    for (let i = start; i < end; i++) sum += d[i]
    return sum / (Math.max(1, end - start) * 255)
  }, [getFreqData])

  const connectElement = useCallback((el: HTMLAudioElement) => {
    const { ctx, analyser } = ensureCtx()
    sourceRef.current?.disconnect()
    const src = ctx.createMediaElementSource(el)
    src.connect(analyser)
    sourceRef.current = src
  }, [ensureCtx])

  const connectMic = useCallback(async () => {
    const { ctx, analyser } = ensureCtx()
    sourceRef.current?.disconnect()
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const src = ctx.createMediaStreamSource(stream)
    src.connect(analyser)
    sourceRef.current = src
  }, [ensureCtx])

  const disconnect = useCallback(() => {
    sourceRef.current?.disconnect()
    sourceRef.current = null
    ctxRef.current?.close()
    ctxRef.current = null
    analyserRef.current = null
  }, [])

  useEffect(() => () => { disconnect() }, [disconnect])

  return { getBass, getMid, connectElement, connectMic, disconnect }
}
