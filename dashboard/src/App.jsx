import { useState, useEffect } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import LivePanel     from './components/LivePanel'
import TimelinePanel from './components/TimelinePanel'
import MLPanel       from './components/MLPanel'
import MetricsPanel  from './components/MetricsPanel'
import EventPanel    from './components/EventPanel'

const TABS = [
  { id: 'live',     label: '⚡ Live' },
  { id: 'timeline', label: '📊 Timeline' },
  { id: 'ml',       label: '🧠 ML Model' },
  { id: 'metrics',  label: '📈 Analytics' },
  { id: 'events',   label: '🔔 Events' },
]

export default function App() {
  const { data, status, history } = useWebSocket()
  const [tab, setTab]         = useState('live')
  const [metrics, setMetrics] = useState(null)
  const [events, setEvents]   = useState([])
  const [cards, setCards]     = useState([])

  // Guard: always an array regardless of hook output
  const safeHistory = Array.isArray(history) ? history : []

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [mRes, eRes, cRes] = await Promise.all([
          fetch('/api/metrics'),
          fetch('/api/events?n=40'),
          fetch('/api/metrics/cards'),
        ])
        if (mRes.ok) {
          const mData = await mRes.json()
          // Ensure timeline is always an array
          if (mData && !Array.isArray(mData.timeline)) mData.timeline = []
          setMetrics(mData)
        }
        if (eRes.ok) {
          const eData = await eRes.json()
          setEvents(Array.isArray(eData) ? eData : [])
        }
        if (cRes.ok) {
          const cData = await cRes.json()
          setCards(Array.isArray(cData) ? cData : [])
        }
      } catch (err) {
        console.warn('[App] API fetch error (backend may not be running):', err)
      }
    }
    fetchAll()
    const id = setInterval(fetchAll, 4000)
    return () => clearInterval(id)
  }, [])

  const statusColor = {
    connected: '#22c55e', disconnected: '#ef4444',
    error: '#f97316', connecting: '#eab308',
  }[status] || '#64748b'

  return (
    <div style={S.root}>
      {/* ── Header ── */}
      <header style={S.header}>
        <div style={S.brand}>
          <span style={S.brandIcon}>⚡</span>
          <span style={S.brandName}>FocusForge</span>
          <span style={S.brandBadge}>AI v2</span>
        </div>

        <nav style={S.nav}>
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{ ...S.navBtn, ...(tab === t.id ? S.navBtnActive : {}) }}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div style={S.statusBar}>
          <span style={{ ...S.dot, background: statusColor }} />
          <span style={S.statusText}>{status.toUpperCase()}</span>
          {data?.cognitive && <>
            <span style={S.pipe}>|</span>
            <Chip color={focusColor(data.cognitive.focus)}>
              Focus {pct(data.cognitive.focus)}
            </Chip>
            <Chip color="#6366f1">{data.cognitive.state}</Chip>
            {data.ml_model && (
              <Chip color="#f59e0b">
                ML {pct(data.ml_model.switch_probability)} switch
              </Chip>
            )}
          </>}
        </div>
      </header>

      {/* ── Content ── */}
      <main style={S.main}>
        {tab === 'live'     && <LivePanel    data={data} history={safeHistory} />}
        {tab === 'timeline' && <TimelinePanel history={safeHistory} metrics={metrics} />}
        {tab === 'ml'       && <MLPanel      data={data} history={safeHistory} />}
        {tab === 'metrics'  && <MetricsPanel metrics={metrics} cards={cards} />}
        {tab === 'events'   && <EventPanel   events={events} />}
      </main>
    </div>
  )
}

function Chip({ color, children }) {
  return (
    <span style={{
      background: color + '20', border: `1px solid ${color}40`, color,
      padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
    }}>
      {children}
    </span>
  )
}

const focusColor = f => f > 0.65 ? '#22c55e' : f > 0.40 ? '#eab308' : '#ef4444'
const pct = v => `${Math.round((v || 0) * 100)}%`

const S = {
  root:   { display: 'flex', flexDirection: 'column', minHeight: '100vh', background: '#070b14' },
  header: {
    display: 'flex', alignItems: 'center', gap: 20, padding: '10px 24px',
    background: '#0d1220', borderBottom: '1px solid #1a2744',
    flexWrap: 'wrap', position: 'sticky', top: 0, zIndex: 100,
  },
  brand:     { display: 'flex', alignItems: 'center', gap: 8 },
  brandIcon: { fontSize: 20 },
  brandName: { fontSize: 17, fontWeight: 700, color: '#60a5fa', letterSpacing: '-0.3px' },
  brandBadge:{ fontSize: 10, background: '#172554', color: '#93c5fd', padding: '2px 6px',
               borderRadius: 8, fontWeight: 600, border: '1px solid #1e40af' },
  nav:       { display: 'flex', gap: 3 },
  navBtn:    {
    background: 'transparent', border: 'none', color: '#475569', padding: '6px 14px',
    borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 500, transition: 'all .15s',
  },
  navBtnActive: { background: '#172554', color: '#60a5fa' },
  statusBar: { display: 'flex', alignItems: 'center', gap: 7, marginLeft: 'auto', flexWrap: 'wrap' },
  dot:       { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  statusText:{ fontSize: 11, fontWeight: 600, color: '#475569', letterSpacing: 1 },
  pipe:      { color: '#1e293b' },
  main:      { flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' },
}
