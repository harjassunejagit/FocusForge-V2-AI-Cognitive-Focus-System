import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, PieChart, Pie, Cell, Legend, BarChart, Bar
} from 'recharts'

const ICON_MAP = {
  'zap': '⚡', 'alert-triangle': '⚠️', 'refresh-cw': '🔁',
  'target': '🎯', 'brain': '🧠', 'git-branch': '🔀',
}

export default function MetricsPanel({ metrics, cards }) {
  const [graphData, setGraphData]   = useState(null)
  const [dbData,    setDbData]      = useState(null)
  const [swHistory, setSwHistory]   = useState([])

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [gRes, dRes, sRes] = await Promise.all([
          fetch('/api/metrics/graph?points=80'),
          fetch('/api/db/dashboard'),
          fetch('/api/db/switch-history?limit=15'),
        ])
        if (gRes.ok) setGraphData(await gRes.json())
        if (dRes.ok) setDbData(await dRes.json())
        if (sRes.ok) setSwHistory(await sRes.json())
      } catch {}
    }
    fetchAll()
    const id = setInterval(fetchAll, 6000)
    return () => clearInterval(id)
  }, [])

  const m = metrics || {}
  const safeSwHistory = Array.isArray(swHistory) ? swHistory : []

  // Pie chart — session state distribution
  const focusPct  = m.focus_percentage || 0
  const driftPct  = Math.max(0, 100 - focusPct - (m.procrastination_rate || 0) * 100)
  const procPct   = Math.min((m.procrastination_rate || 0) * 100, 100 - focusPct)
  const pieData   = [
    { name: 'Focus',        value: Math.round(focusPct),  color: '#22c55e' },
    { name: 'Drift',        value: Math.round(driftPct),  color: '#64748b' },
    { name: 'High Risk',    value: Math.round(procPct),   color: '#ef4444' },
  ].filter(d => d.value > 0)

  return (
    <div style={S.root}>

      {/* Summary cards */}
      <div style={S.cards}>
        {(cards || []).map((c, i) => (
          <SummaryCard key={i} card={c} />
        ))}
        {!cards?.length && (
          <div style={S.empty}>Loading analytics…</div>
        )}
      </div>

      {/* Focus/Proc time-series */}
      <Section title="📈 Focus & Procrastination Risk Over Time">
        {graphData
          ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart
                data={(graphData.labels || []).map((l, i) => ({
                  t:     l,
                  focus: graphData.focus[i],
                  proc:  graphData.procrastination[i],
                }))}
                margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
              >
                <CartesianGrid stroke="#111a2e" strokeDasharray="3 3" />
                <XAxis dataKey="t" tick={{ fill: '#334155', fontSize: 9 }} interval={9} />
                <YAxis domain={[0, 100]} tick={{ fill: '#334155', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                  formatter={(v, n) => [`${v?.toFixed(1)}%`, n]}
                />
                <Line type="monotone" dataKey="focus" stroke="#22c55e" dot={false} strokeWidth={2} name="Focus %" />
                <Line type="monotone" dataKey="proc"  stroke="#ef4444" dot={false} strokeWidth={2} name="Proc Risk %" />
              </LineChart>
            </ResponsiveContainer>
          )
          : <Empty text="Collecting data…" />
        }
      </Section>

      {/* Two-column section */}
      <div style={S.row2}>

        {/* Pie chart */}
        <Section title="🍩 Session State Distribution">
          {pieData.length > 0
            ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                    dataKey="value" label={({ name, value }) => `${name} ${value}%`}
                    labelLine={{ stroke: '#334155' }}
                  >
                    {pieData.map((d, i) => (
                      <Cell key={i} fill={d.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                    formatter={(v) => [`${v}%`]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )
            : <Empty text="Collecting state data…" />
          }
        </Section>

        {/* DB summary */}
        <Section title="🗄️ Session Summary">
          {dbData?.summary
            ? (
              <div style={S.dbSummary}>
                <DbRow k="Session ID"        v={dbData.summary.session_id} />
                <DbRow k="Context Switches"  v={dbData.summary.n_switches} />
                <DbRow k="Avg Proc Risk"     v={`${dbData.summary.avg_proc_risk}%`} />
                <DbRow k="Peak Proc Risk"    v={`${dbData.summary.peak_proc_risk}%`} c="#ef4444" />
                <DbRow k="Avg Focus"         v={`${dbData.summary.avg_focus}%`}      c="#22c55e" />
                <DbRow k="Session Duration"  v={`${m.session_duration_min?.toFixed(1) || 0} min`} />
                <DbRow k="Total Deep Work"   v={`${m.total_deep_work?.toFixed(0) || 0}s`}         c="#22c55e" />
                <DbRow k="Focus Periods"     v={m.focus_periods || 0} />
              </div>
            )
            : <Empty text="Loading DB summary…" />
          }
        </Section>
      </div>

      {/* Switch history bar chart */}
      {safeSwHistory.length > 0 && (
        <Section title="🔀 Recent Context Switches — Cost & Recovery">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={safeSwHistory.slice(0, 15).reverse().map((s, i) => ({
                id:       `#${s.switch_id || i + 1}`,
                switch:   Math.round(s.switch_duration   || 0),
                recovery: Math.round(s.recovery_duration || 0),
                total:    Math.round(s.total_cost        || 0),
              }))}
              margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
            >
              <CartesianGrid stroke="#111a2e" strokeDasharray="3 3" />
              <XAxis dataKey="id" tick={{ fill: '#334155', fontSize: 9 }} />
              <YAxis tick={{ fill: '#334155', fontSize: 10 }} unit="s" />
              <Tooltip
                contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                formatter={(v) => [`${v}s`]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#475569' }} />
              <Bar dataKey="switch"   fill="#f97316" name="Switch"   radius={[2,2,0,0]} />
              <Bar dataKey="recovery" fill="#eab308" name="Recovery" radius={[2,2,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
      )}

      {/* Cognitive history from DB */}
      {dbData?.cognitive_history?.length > 0 && (
        <Section title="🗃️ Cognitive State History (from DB)">
          <ResponsiveContainer width="100%" height={180}>
            <LineChart
              data={dbData.cognitive_history}
              margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
            >
              <CartesianGrid stroke="#111a2e" strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" hide />
              <YAxis domain={[0, 100]} tick={{ fill: '#334155', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                formatter={(v, n) => [`${v?.toFixed(1)}%`, n]}
              />
              <Line type="monotone" dataKey="focus"    stroke="#22c55e" dot={false} strokeWidth={2} name="Focus" />
              <Line type="monotone" dataKey="load"     stroke="#f97316" dot={false} strokeWidth={1.5} name="Load" />
              <Line type="monotone" dataKey="fatigue"  stroke="#a855f7" dot={false} strokeWidth={1.5} name="Fatigue" />
              <Line type="monotone" dataKey="confusion" stroke="#eab308" dot={false} strokeWidth={1} name="Confusion" />
            </LineChart>
          </ResponsiveContainer>
        </Section>
      )}

      {/* Feature logger stats */}
      <Section title="📦 Feature Logging Pipeline">
        <FeatureLogStats />
      </Section>

    </div>
  )
}

function FeatureLogStats() {
  const [stats, setStats] = useState(null)
  useEffect(() => {
    fetch('/api/feature-log/stats')
      .then(r => r.json()).then(setStats).catch(() => {})
    const id = setInterval(() =>
      fetch('/api/feature-log/stats').then(r => r.json()).then(setStats).catch(() => {}),
    8000)
    return () => clearInterval(id)
  }, [])

  if (!stats) return <Empty text="Loading…" />
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', gap: 8 }}>
      {[
        { k: 'Total Features Logged', v: stats.total_features?.toLocaleString(),   c: '#60a5fa' },
        { k: 'Pseudo-labelled',        v: stats.labelled_samples?.toLocaleString(), c: '#22c55e' },
        { k: 'Predictions Logged',     v: stats.total_predictions?.toLocaleString(),c: '#a855f7' },
        { k: 'Write Queue',            v: stats.queue_size,                          c: '#eab308' },
      ].map(({ k, v, c }) => (
        <div key={k} style={S.miniCard}>
          <div style={{ ...S.miniVal, color: c }}>{v ?? '—'}</div>
          <div style={S.miniKey}>{k}</div>
        </div>
      ))}
      <div style={{ ...S.miniCard, gridColumn: '1 / -1' }}>
        <div style={S.miniKey}>DB Path: <span style={{ color: '#60a5fa' }}>{stats.db_path}</span></div>
        <div style={{ ...S.miniKey, marginTop: 4, color: '#334155' }}>
          Pseudo-labels are generated automatically using weak supervision rules.
          Collect data across sessions, then train the LSTM offline.
        </div>
      </div>
    </div>
  )
}

function SummaryCard({ card }) {
  return (
    <div style={{ ...S.card, borderColor: card.color + '33' }}>
      <div style={S.cardIcon}>{ICON_MAP[card.icon] || '📊'}</div>
      <div style={{ ...S.cardValue, color: card.color }}>{card.value}</div>
      <div style={S.cardTitle}>{card.title}</div>
      <div style={S.cardSub}>{card.subtitle}</div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={S.section}>
      <div style={S.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

function DbRow({ k, v, c }) {
  return (
    <div style={S.dbRow}>
      <span style={S.dbKey}>{k}</span>
      <span style={{ ...S.dbVal, color: c || '#94a3b8' }}>{v ?? '—'}</span>
    </div>
  )
}

function Empty({ text }) {
  return <div style={S.empty}>{text}</div>
}

const S = {
  root:      { display: 'flex', flexDirection: 'column', gap: 14 },
  cards:     { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px,1fr))', gap: 10 },
  card:      { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12,
               padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 3 },
  cardIcon:  { fontSize: 20, marginBottom: 4 },
  cardValue: { fontSize: 24, fontWeight: 700 },
  cardTitle: { fontSize: 12, color: '#94a3b8', fontWeight: 600 },
  cardSub:   { fontSize: 11, color: '#334155' },
  section:   { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12, padding: 16 },
  sectionTitle:{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'uppercase',
                 letterSpacing: 0.8, marginBottom: 12 },
  row2:      { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px,1fr))', gap: 12 },
  dbSummary: { display: 'flex', flexDirection: 'column' },
  dbRow:     { display: 'flex', justifyContent: 'space-between', padding: '6px 0',
               borderBottom: '1px solid #0f1829' },
  dbKey:     { color: '#475569', fontSize: 12 },
  dbVal:     { fontSize: 12, fontWeight: 600 },
  miniCard:  { background: '#0a0f1e', borderRadius: 8, padding: '10px 12px' },
  miniVal:   { fontSize: 20, fontWeight: 700, marginBottom: 2 },
  miniKey:   { fontSize: 11, color: '#475569' },
  empty:     { textAlign: 'center', color: '#334155', padding: '20px 0', fontSize: 13 },
}
