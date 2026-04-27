/**
 * JARVIS — Root Application Component
 * HashRouter with two routes:
 *   /          → AgentView  (full-screen particle network)
 *   /control   → ControlView (dashboard)
 *
 * Navigation:
 *   Tab            → toggle between views
 *   Ctrl+,         → jump to /control
 *   ← button       → back to /
 */

import { useEffect }                                              from 'react'
import { HashRouter, Routes, Route, useNavigate, useLocation }   from 'react-router-dom'
import { AgentView }                                              from './views/AgentView'
import { ControlView }                                            from './views/ControlView'
import { useWebSocket }                                           from './hooks/useWebSocket'

// ── Global keyboard navigation ─────────────────────────────────────────────
function KeyboardNav() {
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return

      if (e.key === 'Tab' && !e.ctrlKey && !e.shiftKey && !e.altKey) {
        e.preventDefault()
        navigate(location.pathname === '/' ? '/control' : '/')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate, location.pathname])

  return null
}

// ── App inner (needs Router context) ───────────────────────────────────────
function AppInner() {
  useWebSocket()
  return (
    <>
      <KeyboardNav />
      <Routes>
        <Route path="/"        element={<AgentView />} />
        <Route path="/control" element={<ControlView />} />
      </Routes>
    </>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppInner />
    </HashRouter>
  )
}
