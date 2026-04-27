// frontend/src/components/AudioVisualizer.tsx
import { motion, AnimatePresence } from 'framer-motion'
import { useJARVISStore } from '../store/useJARVISStore'
import { AudioAnalyserHandle } from '../hooks/useAudioAnalyser'
import { useEffect, useRef, useState } from 'react'

interface Props {
  analyser?: AudioAnalyserHandle
}

const BARS = 30
const STATE_COLOR: Record<string, string> = {
  listening:    '#00ff88',
  transcribing: '#00f0ff',
  thinking:     '#ff8c00',
  speaking:     '#00f0ff',
}

export function AudioVisualizer({ analyser }: Props) {
  const systemState = useJARVISStore((s) => s.systemState)
  const [heights, setHeights] = useState<number[]>(Array(BARS).fill(2))
  const [audioAmp, setAudioAmp] = useState(0)
  const rafRef  = useRef<number>(0)
  const simT    = useRef(0)
  const active  = systemState !== 'idle' && systemState !== 'offline' && systemState !== 'connected'
  const visible = active && audioAmp > 0.04

  useEffect(() => {
    if (!active) {
      setHeights(Array(BARS).fill(2))
      setAudioAmp(0)
      return
    }

    const tick = () => {
      simT.current += 0.016
      const bass = analyser?.getBass() ?? 0
      const sim  = 0.12 + 0.88 * Math.abs(Math.sin(simT.current * 4.1) * Math.cos(simT.current * 2.3))
      const amp  = analyser ? bass : sim * (systemState === 'speaking' ? 1 : 0.35)

      setAudioAmp(amp)
      setHeights(Array.from({ length: BARS }, (_, i) => {
        const raw = 2 + (4 + amp * 22) * Math.abs(Math.sin(simT.current * (2.6 + i * 0.33) + i * 0.6))
        return Math.min(32, raw)
      }))
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [active, analyser, systemState])

  const color = STATE_COLOR[systemState] ?? '#00f0ff'

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="flex items-end justify-center gap-[2.5px]"
          style={{ height: 36 }}
          initial={{ opacity: 0, scaleY: 0 }}
          animate={{ opacity: 1, scaleY: 1 }}
          exit={{   opacity: 0, scaleY: 0 }}
          transition={{ duration: 0.3 }}
        >
          {heights.map((h, i) => (
            <div
              key={i}
              style={{
                width:        '2.8px',
                height:       `${h}px`,
                background:   `linear-gradient(180deg, ${color}, ${color}55)`,
                boxShadow:    `0 0 4px ${color}66`,
                borderRadius: '2px',
                transition:   'height 0.05s ease',
              }}
            />
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
