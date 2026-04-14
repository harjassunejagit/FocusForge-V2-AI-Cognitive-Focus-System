import { useState, useEffect } from 'react'

const EVENT_COLORS = {
  SWITCH_DETECTED:        { bg: '#7c2d12', border: '#c2410c', text: '#fed7aa', icon: '🔀' },
  HIGH_PROCRASTINATION:   { bg: '#450a0a', border: '#b91c1c', text: '#fca5a5', icon: '⚠️' },
  RECOVERY_COMPLETE:      { bg: '#052e16', border: '#15803d', text: '#86efac', icon: '✅' },
  FOCUS_LOST:             { bg: '#422006', border: '#c2410c', text: '#fed7aa', icon: '🔴' },
  CALIBRATION_DONE:       { bg: '#172554', border: '#1d4ed8', text: '#93c5fd', icon: '✔️' },
  MODEL_PREDICTION:       { bg: '#1e1b4b', border: '#6d28d9', text: '#c4b5fd', icon: '🤖' },
  INTERVENTION_TRIGGERED: { bg: '#1c1917', border: '#78350f', text: '#fef3c7', icon: '💡' },
  DEEP_WORK_ENTERED:      { bg: '#052e16', border: '#166534', text: '#86efac', icon: '🎯' },
  FATIGUE_DETECTED:       { bg: '#2e1065', border: '#7e22ce', text: '#e9d5ff', icon: '😴' },
  SESSION_STARTED:        { bg: '#172554', border: '#1d4ed8', text: '#93c5fd', icon: '▶️' },
  SESSION_ENDED:          { bg: '#1a1a2e', border: '#334155', text: '#94a3b8', icon: '⏹️' },
}
const DEFAULT_COLOR = { bg: '#0f1829', border: '#1a2744', text: '#94a3b8', icon: '📌' }

export default function EventPanel({ events }) {
  const [busStats, setBusStats]   = useState(null)
  const [flStats,  setFlStats]    = useState(null)
  const [filter,   setFilter]     = useState('ALL')

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [bRes, fRes] = await Promise.all([
          fetch('/api/events/stats'),
          fetch('/api/feature-log/stats'),
        ])
        if (bRes.ok) setBusStats(await bRes.json())
        if (fRes.ok) setFlStats(await fRes.json())
      } catch {}
    }
    fetchStats()
    const id = setInterval(fetchStats, 5000)
    return () => clearInterval(id)
  }, [])

  // Unique event types for filter tabs
  const eventTypes = ['ALL', ...new Set((events || []).map(e => e.type))]

  const filtered = filter === 'ALL'
    ? (events || [])
    : (events || []).filter(e => e.type === filter)

  // Count by type
  const countByType = (events || []).reduce((acc, e) => {
    acc[e.type] = (acc[e.type] || 0) + 1
    return acc
  }, {})

  return (
    <div style={S.root}>

      {/* Stats row */}
      <div style={S.statsRow}>
        <StatCard title="Total Published"  value={busStats?.total_published ?? '—'}   color="#60a5fa" />
        <StatCard title="History Buffer"   value={busStats?.history_size    ?? '—'}   color="#94a3b8" />
        <StatCard title="Features Logged"  value={flStats?.total_features   ?? '—'}   color="#22c55e" />
        <StatCard title="Pseudo-Labelled"  value={flStats?.labelled_samples ?? '—'}   color="#a855f7" />
        <StatCard title="Predictions Saved" value={flStats?.total_predictions ?? '—'} color="#f97316" />
      </div>

      {/* Subscriber map */}
      {busStats?.subscriber_counts && (
        <Section title="📡 Event Bus Subscribers">
          <div style={S.subGrid}>
            {Object.entries(busStats.subscriber_counts).map(([k, v]) => (
              <div key={k} style={S.subChip}>
                <span style={S.subName}>{k}</span>
                <span style={S.subCount}>{v}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Filter tabs */}
      <Section title="🔔 Event Log">
        <div style={S.filterRow}>
          {eventTypes.map(t => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              style={{ ...S.filterBtn, ...(filter === t ? S.filterBtnActive : {}) }}
            >
              {t === 'ALL' ? `ALL (${events?.length || 0})` : `${t.split('_')[0]} (${countByType[t] || 0})`}
            </button>
          ))}
        </div>

        <div style={S.eventList}>
          {filtered.length === 0 && (
            <div style={S.empty}>
              No events yet — events are published as you use the system.
              <br />
              <span style={{ color: '#334155', fontSize: 11 }}>
                Tip: Context switches, high procrastination, and model predictions all emit events.
              </span>
            </div>
          )}
          {[...filtered].reverse().map((ev, i) => {
            const c = EVENT_COLORS[ev.type] || DEFAULT_COLOR
            return (
              <div key={i} style={{ ...S.eventCard, background: c.bg, borderColor: c.border }}>
                <div style={S.eventHeader}>
                  <span style={S.eventIcon}>{c.icon}</span>
                  <span style={{ ...S.eventType, color: c.text }}>{ev.type}</span>
                  <span style={S.eventSeverity(ev.severity)}>{ev.severity}</span>
                  <span style={S.eventTime}>
                    {ev.age_sec != null
                      ? `${ev.age_sec < 60 ? ev.age_sec.toFixed(0) + 's' : (ev.age_sec / 60).toFixed(1) + 'm'} ago`
                      : new Date(ev.timestamp * 1000).toLocaleTimeString()
                    }
                  </span>
                </div>
                {ev.data && Object.keys(ev.data).length > 0 && (
                  <div style={S.eventData}>
                    {Object.entries(ev.data).map(([k, v]) => (
                      <span key={k} style={S.eventPill}>
                        <span style={S.eventPillKey}>{k}:</span>{' '}
                        <span style={{ color: c.text }}>
                          {typeof v === 'number' ? v.toFixed(3) : String(v)}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Section>

      {/* Event type legend */}
      <Section title="📖 Event Type Reference">
        <div style={S.legendGrid}>
          {Object.entries(EVENT_COLORS).map(([type, c]) => (
            <div key={type} style={{ ...S.legendItem, background: c.bg, borderColor: c.border }}>
              <span style={S.legendIcon}>{c.icon}</span>
              <div>
                <div style={{ ...S.legendType, color: c.text }}>{type}</div>
                <div style={S.legendDesc}>{EVENT_DESC[type] || ''}</div>
              </div>
            </div>
          ))}
        </div>
      </Section>

    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div style={S.section}>
      <div style={S.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

function StatCard({ title, value, color }) {
  return (
    <div style={S.statCard}>
      <div style={{ ...S.statVal, color }}>{typeof value === 'number' ? value.toLocaleString() : value}</div>
      <div style={S.statTitle}>{title}</div>
    </div>
  )
}

// ── Event descriptions ────────────────────────────────────────────────────────
const EVENT_DESC = {
  SWITCH_DETECTED:        'Context switch confirmed by FSM detector',
  HIGH_PROCRASTINATION:   'Procrastination risk exceeded 70% threshold',
  RECOVERY_COMPLETE:      'User returned to focused state after switch',
  FOCUS_LOST:             'Focus score dropped below 35%',
  CALIBRATION_DONE:       'Baseline calibration finished successfully',
  MODEL_PREDICTION:       'LSTM made a new cognitive state prediction',
  INTERVENTION_TRIGGERED: 'Anti-procrastination message delivered to user',
  DEEP_WORK_ENTERED:      'Sustained focus block started (focus > 65%)',
  FATIGUE_DETECTED:       'Fatigue score exceeded warning threshold',
  SESSION_STARTED:        'A new tracking session was opened',
  SESSION_ENDED:          'The current tracking session was closed',
}

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  root:        { display: 'flex', flexDirection: 'column', gap: 14 },
  statsRow:    { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px,1fr))', gap: 10 },
  statCard:    { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 10, padding: '12px 14px' },
  statVal:     { fontSize: 22, fontWeight: 700, marginBottom: 2 },
  statTitle:   { fontSize: 11, color: '#475569' },
  section:     { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12, padding: 16 },
  sectionTitle:{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'uppercase',
                 letterSpacing: 0.8, marginBottom: 12 },
  subGrid:     { display: 'flex', gap: 8, flexWrap: 'wrap' },
  subChip:     { background: '#0a0f1e', border: '1px solid #1a2744', borderRadius: 8,
                 padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 6 },
  subName:     { fontSize: 11, color: '#475569' },
  subCount:    { fontSize: 12, fontWeight: 700, color: '#60a5fa' },
  filterRow:   { display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 12 },
  filterBtn:   { background: 'transparent', border: '1px solid #1a2744', borderRadius: 6,
                 color: '#475569', padding: '3px 8px', cursor: 'pointer', fontSize: 10, fontWeight: 500 },
  filterBtnActive: { background: '#172554', border: '1px solid #1d4ed8', color: '#93c5fd' },
  eventList:   { display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 480, overflowY: 'auto' },
  eventCard:   { border: '1px solid', borderRadius: 8, padding: '8px 12px' },
  eventHeader: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 },
  eventIcon:   { fontSize: 14, flexShrink: 0 },
  eventType:   { fontSize: 12, fontWeight: 700, flex: 1 },
  eventSeverity: sev => ({
    fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 6, textTransform: 'uppercase',
    background:
      sev === 'critical' ? '#450a0a' :
      sev === 'warning'  ? '#422006' : '#0a1628',
    color:
      sev === 'critical' ? '#fca5a5' :
      sev === 'warning'  ? '#fed7aa' : '#60a5fa',
  }),
  eventTime:   { fontSize: 10, color: '#334155', flexShrink: 0 },
  eventData:   { display: 'flex', gap: 6, flexWrap: 'wrap' },
  eventPill:   { background: '#00000030', borderRadius: 4, padding: '2px 6px', fontSize: 10 },
  eventPillKey:{ color: '#475569' },
  legendGrid:  { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px,1fr))', gap: 6 },
  legendItem:  { border: '1px solid', borderRadius: 8, padding: '6px 10px',
                 display: 'flex', alignItems: 'flex-start', gap: 8 },
  legendIcon:  { fontSize: 14, marginTop: 1, flexShrink: 0 },
  legendType:  { fontSize: 11, fontWeight: 600, marginBottom: 2 },
  legendDesc:  { fontSize: 10, color: '#475569' },
  empty:       { textAlign: 'center', color: '#334155', padding: '24px 0', fontSize: 13, lineHeight: 1.8 },
}
