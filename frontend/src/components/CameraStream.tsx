/**
 * JARVIS — Live camera feed with detection overlay.
 * Renders base64 JPEG frames pushed from the vision pipeline via WebSocket.
 */

import { useJARVISStore } from '../store/useJARVISStore'

export function CameraStream() {
  const frame = useJARVISStore((s) => s.cameraFrame)

  if (!frame) {
    return (
      <div
        className="flex flex-col items-center justify-center h-48 rounded"
        style={{ border: '1px solid #0a4060', background: 'rgba(0,0,0,0.4)' }}
      >
        <div
          className="w-3 h-3 rounded-full mb-3"
          style={{ background: '#1a3040', boxShadow: '0 0 6px #1a3040' }}
        />
        <span
          className="font-mono text-xs tracking-widest"
          style={{ color: '#1a3040' }}
        >
          CAMERA OFFLINE
        </span>
      </div>
    )
  }

  return (
    <div className="relative rounded overflow-hidden" style={{ border: '1px solid #0a4060' }}>
      <img
        src={`data:image/jpeg;base64,${frame}`}
        alt="JARVIS vision feed"
        className="w-full object-contain"
        style={{ display: 'block' }}
      />
      <div className="absolute top-2 left-2 flex items-center gap-1">
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: '#00ff88', boxShadow: '0 0 4px #00ff88' }}
        />
        <span
          className="font-mono text-xs px-1 rounded"
          style={{ background: 'rgba(0,0,0,0.6)', color: '#00ff88' }}
        >
          LIVE
        </span>
      </div>
    </div>
  )
}
