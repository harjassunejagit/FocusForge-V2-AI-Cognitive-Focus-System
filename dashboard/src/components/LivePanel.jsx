import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

export default function LivePanel({ data, history }) {
  // Safe defaults
  const safeHistory = Array.isArray(history) ? history : []

  if (!data || data.type !== 'data') {
    return (
      <div style={S.center}>
        <div style={S.pulse}>⚡</div>
        <p style={S.waitText}>
          {data?.type === 'calibrating'
            ? `🎯 Calibrating… ${(data.progress ?? 0).toFixed(0)}%`
            : data?.type === 'no_face'
            ? '👁️ Face not detected — look at the camera'
            : '🔌 Connecting to backend…'}
        </p>
        <p style={{ color: '#334155', fontSize: 12, marginTop: 8 }}>
          {!data
            ? 'Run: python run.py  →  then npm run dev'
            : data.type === 'calibrating'
            ? 'Sit naturally in front of the camera for ~30 seconds'
            : ''}
        </p>
      </div>
    )
  }

  const cog   = data.cognitive          || {}
  const sw    = data.switch             || {}
  const proc  = data.procrastination    || {}
  const ml    = data.ml_model           || {}
  const snap  = data.metrics_snapshot   || {}

  return (
    <div style={S.grid}>
      {/* Focus / State card */}
      <Card title="🧠 Cognitive State" wide>
        <div style={S.stateRow}>
          <BigGauge value={cog.focus}     color={focusColor(cog.focus)} label="Focus" />
          <BigGauge value={cog.load}      color="#f97316"               label="Cognitive Load" />
          <BigGauge value={cog.fatigue}   color="#a855f7"               label="Fatigue" />
          <BigGauge value={cog.confusion} color="#eab308"               label="Confusion" />
        </div>
        <div style={S.stateLabel}>{cog.label || '—'}</div>
        <ConfBar value={cog.confidence} label="Rule confidence" color="#60a5fa" />
      </Card>

      {/* ML Model */}
      <Card title="🤖 LSTM Model Output">
        {ml.model_version
          ? <>
              <MetricRow label="Switch Probability"
                value={pct(ml.switch_probability)} color={switchColor(ml.switch_probability)} />
              <ConfBar value={ml.switch_confidence} label="Switch confidence" color="#f97316" />
              <MetricRow label="Procrastination Score"
                value={pct(ml.procrastination_score)} color="#a855f7" />
              <MetricRow label="Predicted State" value={ml.cognitive_state || '—'} color="#60a5fa" />
              <ConfBar value={ml.state_confidence} label="State confidence" color="#60a5fa" />
              <div style={S.mlBadge(ml.switch_probability)}>{ml.label || 'Stable'}</div>
            </>
          : <div style={S.modelWaiting}>
              🧠 Model warming up… collecting data for LSTM buffer.<br/>
              <span style={{ color: '#334155', fontSize: 11 }}>
                Needs ~30 frames to start predicting.
              </span>
            </div>
        }
      </Card>

      {/* Switch detector */}
      <Card title="🔄 Context Switch">
        <MetricRow label="Phase"          value={sw.label || '—'}        color="#e2e8f0" />
        <MetricRow label="Total Switches" value={sw.total_switches ?? 0} color="#f97316" />
        <MetricRow label="Rate / hr"      value={`${sw.rate_per_hr || 0}`} color="#eab308" />
        {sw.predicted && (
          <div style={S.alert}>
            ⚠️ Switch predicted in {(sw.pred_in_sec ?? 0).toFixed(1)}s
            <br /><small>Confidence: {pct(sw.pred_conf)}</small>
          </div>
        )}
      </Card>

      {/* Procrastination */}
      <Card title="😶 Procrastination Risk">
        <ScoreRing value={proc.score} />
        <div style={S.riskLabel(proc.risk_level)}>{(proc.risk_level || 'low').toUpperCase()}</div>
        <MetricRow label="Status" value={proc.label || '—'} color="#e2e8f0" />
        {proc.rising && <div style={S.rising}>📈 Risk rising</div>}
      </Card>

      {/* Session snapshot */}
      <Card title="📊 Session Metrics">
        <MetricRow label="Focus %"          value={`${(snap.focus_percentage ?? 0).toFixed(0)}%`}       color="#22c55e" />
        <MetricRow label="Avg Switch Cost"  value={`${(snap.avg_switch_cost ?? 0).toFixed(0)}s`}        color="#f97316" />
        <MetricRow label="Longest Focus"    value={`${(snap.deep_work_duration ?? 0).toFixed(0)}s`}     color="#60a5fa" />
        <MetricRow label="Session Duration" value={`${(snap.session_duration_min ?? 0).toFixed(1)} min`} color="#94a3b8" />
      </Card>

      {/* Intervention */}
      {data.intervention?.active && (
        <Card title="💡 Intervention" wide>
          <div style={S.intervention}>{data.intervention.message}</div>
        </Card>
      )}

      {/* Live chart */}
      <Card title="📈 Live Signal Chart" wide>
        {safeHistory.length === 0
          ? <div style={S.chartEmpty}>Collecting data…</div>
          : (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={safeHistory.slice(-60)} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#1a2744" strokeDasharray="3 3" />
                <XAxis dataKey="t" hide />
                <YAxis domain={[0, 100]} tick={{ fill: '#475569', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                  labelFormatter={() => ''}
                  formatter={(v, n) => [`${(v ?? 0).toFixed(1)}%`, n]}
                />
                <Line type="monotone" dataKey="focus"    stroke="#22c55e" dot={false} strokeWidth={2} name="Focus" />
                <Line type="monotone" dataKey="proc"     stroke="#ef4444" dot={false} strokeWidth={2} name="Proc Risk" />
                <Line type="monotone" dataKey="mlSwitch" stroke="#f97316" dot={false} strokeWidth={1.5} strokeDasharray="4 2" name="ML Switch" />
                <Line type="monotone" dataKey="load"     stroke="#a855f7" dot={false} strokeWidth={1.5} name="Load" />
              </LineChart>
            </ResponsiveContainer>
          )
        }
        <div style={S.legend}>
          {[['#22c55e','Focus'],['#ef4444','Proc Risk'],['#f97316','ML Switch (dashed)'],['#a855f7','Load']].map(([c,l]) => (
            <span key={l} style={S.legendItem(c)}><span style={S.legendDot(c)}/>{l}</span>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function Card({ title, children, wide }) {
  return (
    <div style={{ ...S.card, ...(wide ? S.cardWide : {}) }}>
      <div style={S.cardTitle}>{title}</div>
      {children}
    </div>
  )
}

function BigGauge({ value, color, label }) {
  const pctVal = Math.round((value || 0) * 100)
  return (
    <div style={S.gauge}>
      <div style={S.gaugeRing}>
        <svg width="64" height="64" viewBox="0 0 64 64">
          <circle cx="32" cy="32" r="26" fill="none" stroke="#1a2744" strokeWidth="6" />
          <circle cx="32" cy="32" r="26" fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={`${pctVal * 1.634} 163.4`}
            strokeLinecap="round"
            transform="rotate(-90 32 32)"
          />
          <text x="32" y="37" textAnchor="middle" fill={color} fontSize="14" fontWeight="700">
            {pctVal}
          </text>
        </svg>
      </div>
      <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{label}</div>
    </div>
  )
}

function ConfBar({ value, label, color }) {
  const pctVal = Math.round((value || 0) * 100)
  return (
    <div style={{ marginTop: 8 }}>
      <div style={S.confLabel}>{label}: <span style={{ color }}>{pctVal}%</span></div>
      <div style={S.confTrack}>
        <div style={{ ...S.confFill, width: `${pctVal}%`, background: color }} />
      </div>
    </div>
  )
}

function MetricRow({ label, value, color }) {
  return (
    <div style={S.metricRow}>
      <span style={S.metricLabel}>{label}</span>
      <span style={{ ...S.metricValue, color: color || '#e2e8f0' }}>{value ?? '—'}</span>
    </div>
  )
}

function ScoreRing({ value }) {
  const v     = value || 0
  const color = v > 70 ? '#ef4444' : v > 40 ? '#eab308' : '#22c55e'
  const dash  = (v / 100) * 163.4
  return (
    <div style={{ display: 'flex', justifyContent: 'center', margin: '8px 0' }}>
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="34" fill="none" stroke="#1a2744" strokeWidth="8" />
        <circle cx="40" cy="40" r="34" fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} 213.6`} strokeLinecap="round"
          transform="rotate(-90 40 40)" />
        <text x="40" y="44" textAnchor="middle" fill={color} fontSize="18" fontWeight="700">{v.toFixed(0)}</text>
        <text x="40" y="57" textAnchor="middle" fill="#475569" fontSize="10">/ 100</text>
      </svg>
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────
const pct = v => `${Math.round((v || 0) * 100)}%`
const focusColor  = f => f > 0.65 ? '#22c55e' : f > 0.40 ? '#eab308' : '#ef4444'
const switchColor = p => p > 0.65 ? '#ef4444' : p > 0.35 ? '#eab308' : '#22c55e'
const riskColors  = { low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444' }

// ── Styles ─────────────────────────────────────────────────────────────────
const S = {
  grid:      { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 },
  card:      { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12, padding: 16 },
  cardWide:  { gridColumn: '1 / -1' },
  cardTitle: { fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'uppercase',
               letterSpacing: 0.8, marginBottom: 12 },
  center:    { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
               minHeight: 300, gap: 12 },
  pulse:     { fontSize: 48 },
  waitText:  { color: '#475569', fontSize: 16 },
  stateRow:  { display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginBottom: 8 },
  stateLabel:{ textAlign: 'center', fontSize: 13, color: '#94a3b8', marginTop: 4 },
  gauge:     { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  gaugeRing: {},
  metricRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center',
               padding: '5px 0', borderBottom: '1px solid #0f1829' },
  metricLabel:{ color: '#475569', fontSize: 12 },
  metricValue:{ fontSize: 13, fontWeight: 600 },
  confLabel: { fontSize: 11, color: '#475569', marginBottom: 3 },
  confTrack: { height: 4, background: '#1a2744', borderRadius: 2, overflow: 'hidden' },
  confFill:  { height: '100%', borderRadius: 2, transition: 'width 0.5s ease' },
  alert:     { marginTop: 10, background: '#7c2d12', border: '1px solid #c2410c', borderRadius: 8,
               padding: '8px 12px', fontSize: 12, color: '#fed7aa' },
  rising:    { marginTop: 8, color: '#f97316', fontSize: 12, fontWeight: 600 },
  riskLabel: rl => ({
    textAlign: 'center', fontWeight: 700, fontSize: 14,
    color: riskColors[rl] || '#e2e8f0', marginBottom: 6,
  }),
  mlBadge:   p => ({
    marginTop: 10, textAlign: 'center', padding: '6px 12px', borderRadius: 8, fontSize: 12,
    fontWeight: 600,
    background: p > 0.65 ? '#7f1d1d' : p > 0.35 ? '#422006' : '#052e16',
    color:      p > 0.65 ? '#fca5a5' : p > 0.35 ? '#fed7aa' : '#86efac',
    border:     `1px solid ${p > 0.65 ? '#b91c1c' : p > 0.35 ? '#c2410c' : '#15803d'}`,
  }),
  modelWaiting: {
    textAlign: 'center', color: '#475569', fontSize: 13, padding: '16px 0', lineHeight: 1.7,
  },
  intervention:{ background: '#1c1917', border: '1px solid #78350f', borderRadius: 8,
                 padding: '12px 16px', fontSize: 13, color: '#fef3c7', lineHeight: 1.5 },
  chartEmpty:  { textAlign: 'center', color: '#334155', fontSize: 13, padding: '24px 0' },
  legend:    { display: 'flex', gap: 16, justifyContent: 'center', marginTop: 8, flexWrap: 'wrap' },
  legendItem:c=> ({ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#64748b' }),
  legendDot: c=> ({ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0 }),
}
