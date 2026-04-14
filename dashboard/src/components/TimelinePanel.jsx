import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar, Legend } from 'recharts'

export default function TimelinePanel({ history, metrics }) {
  // ── Safe defaults — NEVER let these be undefined ──────────────────────────
  const safeHistory = Array.isArray(history) ? history : []
  const timeline    = Array.isArray(metrics?.timeline) ? metrics.timeline : []

  return (
    <div style={S.root}>
      {/* Live signal area chart */}
      <Section title="📈 Focus · Load · Procrastination Risk (Live)">
        {safeHistory.length === 0 ? (
          <Empty text="Waiting for live data stream… (start backend and allow camera)" />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={safeHistory.slice(-120)} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gFocus" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gProc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gLoad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#a855f7" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#a855f7" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#111a2e" strokeDasharray="3 3" />
              <XAxis dataKey="t" hide />
              <YAxis domain={[0, 100]} tick={{ fill: '#334155', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                formatter={(v, n) => [`${(v ?? 0).toFixed(1)}%`, n]}
              />
              <Area type="monotone" dataKey="focus"   stroke="#22c55e" fill="url(#gFocus)" strokeWidth={2} name="Focus" />
              <Area type="monotone" dataKey="proc"    stroke="#ef4444" fill="url(#gProc)"  strokeWidth={2} name="Proc Risk" />
              <Area type="monotone" dataKey="load"    stroke="#a855f7" fill="url(#gLoad)"  strokeWidth={1.5} name="Cog Load" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Section>

      {/* Prediction timeline strip */}
      <Section title="🎯 Prediction Timeline — Focus | Drift | Switch | Recover">
        <div style={S.strip}>
          {timeline.length === 0
            ? <div style={S.empty}>No timeline events yet — session is starting…</div>
            : timeline.slice(-60).map((ev, i) => (
              <TimelineBlock key={i} event={ev} />
            ))
          }
        </div>
        <div style={S.stripLegend}>
          {[['#22c55e','focus'],['#64748b','drift'],['#ef4444','switch'],['#eab308','recover']].map(([c,l]) => (
            <span key={l} style={S.legendItem}>
              <span style={{ ...S.legendDot, background: c }} />{l}
            </span>
          ))}
        </div>
      </Section>

      {/* State bar chart */}
      {safeHistory.length > 10 && (
        <Section title="📊 Cognitive Signal Comparison (last 60 frames)">
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={safeHistory.slice(-60)} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid stroke="#111a2e" strokeDasharray="3 3" />
              <XAxis dataKey="t" hide />
              <YAxis domain={[0, 100]} tick={{ fill: '#334155', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                formatter={(v, n) => [`${(v ?? 0).toFixed(1)}%`, n]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#475569' }} />
              <Bar dataKey="focus"   fill="#22c55e" opacity={0.85} name="Focus"    radius={[2,2,0,0]} />
              <Bar dataKey="fatigue" fill="#a855f7" opacity={0.75} name="Fatigue"  radius={[2,2,0,0]} />
              <Bar dataKey="proc"    fill="#ef4444" opacity={0.75} name="Proc Risk" radius={[2,2,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
      )}
    </div>
  )
}

function TimelineBlock({ event }) {
  if (!event || !event.state) return null
  const color = {
    focus:   '#22c55e',
    drift:   '#64748b',
    switch:  '#ef4444',
    recover: '#eab308',
  }[event.state] || '#334155'

  const width = Math.min(Math.max((event.duration ?? 1) * 8, 12), 120)

  return (
    <div
      title={`${event.state}: ${event.duration ?? 0}s\n${event.label ?? ''}`}
      style={{ ...S.block, width, background: color, opacity: 0.8 }}
    >
      {width > 30 && (
        <span style={S.blockLabel}>{(event.duration ?? 0).toFixed(0)}s</span>
      )}
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

function Empty({ text }) {
  return <div style={S.empty}>{text}</div>
}

const S = {
  root:        { display: 'flex', flexDirection: 'column', gap: 16 },
  section:     { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12, padding: 16 },
  sectionTitle:{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'uppercase',
                 letterSpacing: 0.8, marginBottom: 12 },
  strip:       { display: 'flex', gap: 2, overflowX: 'auto', padding: '8px 0',
                 minHeight: 48, alignItems: 'stretch' },
  block:       { borderRadius: 4, minWidth: 12, flexShrink: 0, display: 'flex',
                 alignItems: 'center', justifyContent: 'center', cursor: 'default' },
  blockLabel:  { fontSize: 9, color: '#fff', fontWeight: 600 },
  stripLegend: { display: 'flex', gap: 12, marginTop: 8, flexWrap: 'wrap' },
  legendItem:  { display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#64748b' },
  legendDot:   { width: 8, height: 8, borderRadius: 2, display: 'inline-block' },
  empty:       { color: '#334155', fontSize: 13, textAlign: 'center', padding: '16px 0', width: '100%' },
}
