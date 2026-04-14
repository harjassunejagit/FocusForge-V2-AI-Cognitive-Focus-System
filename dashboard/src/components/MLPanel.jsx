import { useState, useEffect } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, RadarChart, PolarGrid, PolarAngleAxis, Radar, AreaChart, Area
} from 'recharts'

export default function MLPanel({ data, history }) {
  const [modelStats,   setModelStats]   = useState(null)
  const [predictions,  setPredictions]  = useState([])
  const [statsLoading, setStatsLoading] = useState(true)

  useEffect(() => {
    const fetch_ = async () => {
      try {
        const [sRes, pRes] = await Promise.all([
          fetch('/api/model/stats'),
          fetch('/api/model/predictions'),
        ])
        if (sRes.ok) setModelStats(await sRes.json())
        if (pRes.ok) {
          const pData = await pRes.json()
          setPredictions(Array.isArray(pData) ? pData : [])
        }
      } catch (err) {
        console.warn('[MLPanel] API error:', err)
      } finally {
        setStatsLoading(false)
      }
    }
    fetch_()
    const id = setInterval(fetch_, 5000)
    return () => clearInterval(id)
  }, [])

  const safeHistory = Array.isArray(history) ? history : []
  const ml  = data?.ml_model  || {}
  const cog = data?.cognitive || {}

  const radarData = ml.cognitive_state_probs
    ? Object.entries(ml.cognitive_state_probs).map(([k, v]) => ({
        state: k, value: Math.round((v || 0) * 100),
      }))
    : []

  const predHistory = safeHistory.slice(-90).map((h, i) => ({
    i,
    switchProb: h.mlSwitch ?? 0,
    focus:      h.focus    ?? 0,
  }))

  return (
    <div style={S.root}>

      {/* Top row */}
      <div style={S.row3}>
        <MetricCard
          title="Switch Probability"
          value={`${((ml.switch_probability || 0) * 100).toFixed(1)}%`}
          sub={ml.label || 'Warming up…'}
          color={switchColor(ml.switch_probability || 0)}
          icon="🔄"
          confidence={ml.switch_confidence}
          confLabel="Switch confidence"
        />
        <MetricCard
          title="Procrastination Score"
          value={`${((ml.procrastination_score || 0) * 100).toFixed(1)}%`}
          sub="ML-estimated risk"
          color="#a855f7"
          icon="😶"
          confidence={null}
        />
        <MetricCard
          title="Predicted Cognitive State"
          value={ml.cognitive_state || '—'}
          sub={ml.cognitive_state ? 'LSTM output' : 'Needs ~30 frames'}
          color="#60a5fa"
          icon="🧠"
          confidence={ml.state_confidence}
          confLabel="State confidence"
        />
      </div>

      {/* Switch probability timeline */}
      <Section title="📈 LSTM Switch Probability vs Focus (Live)">
        {predHistory.length === 0
          ? <Empty text="Collecting data stream… (backend must be running)" />
          : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={predHistory} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="gSwitch" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#f97316" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gFocus2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#111a2e" strokeDasharray="3 3" />
                <XAxis dataKey="i" hide />
                <YAxis domain={[0, 100]} tick={{ fill: '#334155', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                  formatter={(v, n) => [`${(v ?? 0).toFixed(1)}%`, n]}
                />
                <Area type="monotone" dataKey="switchProb" stroke="#f97316" fill="url(#gSwitch)" strokeWidth={2} name="ML Switch Prob %" />
                <Area type="monotone" dataKey="focus"      stroke="#22c55e" fill="url(#gFocus2)" strokeWidth={1.5} name="Focus %" />
              </AreaChart>
            </ResponsiveContainer>
          )
        }
      </Section>

      {/* Radar + Stats */}
      <div style={S.row2}>
        <Section title="🎯 Cognitive State Probability Distribution">
          {radarData.length > 0
            ? (
              <ResponsiveContainer width="100%" height={220}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#1a2744" />
                  <PolarAngleAxis dataKey="state" tick={{ fill: '#64748b', fontSize: 11 }} />
                  <Radar dataKey="value" stroke="#60a5fa" fill="#60a5fa" fillOpacity={0.25} strokeWidth={2} />
                  <Tooltip
                    contentStyle={{ background: '#0d1220', border: '1px solid #1a2744', borderRadius: 8, fontSize: 11 }}
                    formatter={(v) => [`${v}%`, 'Probability']}
                  />
                </RadarChart>
              </ResponsiveContainer>
            )
            : <Empty text="Waiting for LSTM output… (~30 frames needed)" />
          }
        </Section>

        <Section title="📊 Model Stats">
          {statsLoading
            ? <Empty text="Loading model stats…" />
            : modelStats
            ? (
              <div style={S.statsList}>
                <StatRow k="Total Predictions"     v={(modelStats.n_predictions ?? 0).toLocaleString()} />
                <StatRow k="Avg Switch Probability" v={`${((modelStats.avg_switch_probability || 0) * 100).toFixed(1)}%`} />
                <StatRow k="Buffer Fill"            v={`${modelStats.buffer_fill ?? 0} / ${modelStats.sequence_len ?? 30}`} />
                <StatRow k="Model Version"          v={modelStats.model_version || 'lstm-v1-numpy'} />
                <StatRow k="Architecture"           v="NumPy LSTM · no PyTorch" />
                <StatRow k="Feature Dim"            v="12 normalised features" />
                <StatRow k="Hidden Size"            v="64 units" />
                <StatRow k="Sequence Length"        v="30 frames (~1 sec)" />
              </div>
            )
            : <Empty text="Model not initialised yet — start the backend first." />
          }
          <button style={S.saveBtn} onClick={async () => {
            try {
              const r = await fetch('/api/model/save-weights', { method: 'POST' })
              const j = await r.json()
              alert(`Weights saved → ${j.path}`)
            } catch { alert('Save failed — is the backend running?') }
          }}>
            💾 Save Weights
          </button>
        </Section>
      </div>

      {/* Prediction log */}
      <Section title="🗂️ Recent LSTM Predictions (last 10)">
        <div style={S.table}>
          <div style={S.tableHead}>
            {['Time','Switch Prob','Proc Score','State','Sw Conf','St Conf','Label'].map(h => (
              <span key={h} style={S.th}>{h}</span>
            ))}
          </div>
          {predictions.length === 0
            ? <div style={S.emptyTable}>No predictions yet — waiting for data stream…</div>
            : predictions.slice(-10).reverse().map((p, i) => (
              <div key={i} style={S.tableRow(i)}>
                <span style={S.td}>{new Date((p.timestamp || 0) * 1000).toLocaleTimeString()}</span>
                <span style={{ ...S.td, color: switchColor(p.switch_probability) }}>
                  {((p.switch_probability || 0) * 100).toFixed(1)}%
                </span>
                <span style={{ ...S.td, color: '#a855f7' }}>
                  {((p.procrastination || 0) * 100).toFixed(1)}%
                </span>
                <span style={{ ...S.td, color: '#60a5fa' }}>{p.cognitive_state || '—'}</span>
                <span style={S.td}>{((p.switch_confidence || 0) * 100).toFixed(0)}%</span>
                <span style={S.td}>{((p.state_confidence  || 0) * 100).toFixed(0)}%</span>
                <span style={{ ...S.td, color: switchColor(p.switch_probability) }}>{p.label || '—'}</span>
              </div>
            ))
          }
        </div>
      </Section>

      {/* Architecture */}
      <Section title="🏗️ Model Architecture">
        <div style={S.arch}>
          {[
            { label: 'Input Layer',    detail: '12 normalised feature signals per frame',           color: '#334155' },
            { label: 'Rolling Buffer', detail: 'Last 30 frames (~1 second) kept in memory',        color: '#1e3a5f' },
            { label: 'LSTM Cell',      detail: '64 hidden units — learns temporal patterns',        color: '#1d4ed8' },
            { label: 'Output Head',    detail: 'Linear → switch_prob + proc_score + 5 state logits', color: '#7c3aed' },
            { label: 'Confidence',     detail: 'Entropy-based uncertainty estimate per output',     color: '#065f46' },
          ].map((a, i) => (
            <div key={i} style={{ ...S.archBlock, background: a.color }}>
              <div style={S.archLabel}>{a.label}</div>
              <div style={S.archDetail}>{a.detail}</div>
            </div>
          ))}
        </div>
        <div style={S.archNote}>
          ℹ️ No PyTorch or TensorFlow required — runs on pure NumPy.
          Weights initialised with Xavier uniform; train offline using collected pseudo-labels.
        </div>
      </Section>
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

function MetricCard({ title, value, sub, color, icon, confidence, confLabel }) {
  return (
    <div style={{ ...S.metCard, borderColor: color + '40' }}>
      <div style={S.metIcon}>{icon}</div>
      <div style={S.metTitle}>{title}</div>
      <div style={{ ...S.metValue, color }}>{value}</div>
      <div style={S.metSub}>{sub}</div>
      {confidence != null && (
        <div style={S.confWrap}>
          <div style={S.confLabel}>{confLabel}: {((confidence || 0) * 100).toFixed(0)}%</div>
          <div style={S.confTrack}>
            <div style={{ ...S.confFill, width: `${(confidence || 0) * 100}%`, background: color }} />
          </div>
        </div>
      )}
    </div>
  )
}

function StatRow({ k, v }) {
  return (
    <div style={S.statRow}>
      <span style={S.statKey}>{k}</span>
      <span style={S.statVal}>{v}</span>
    </div>
  )
}

function Empty({ text }) {
  return <div style={S.empty}>{text}</div>
}

const switchColor = p => (p || 0) > 0.65 ? '#ef4444' : (p || 0) > 0.35 ? '#eab308' : '#22c55e'

const S = {
  root:        { display: 'flex', flexDirection: 'column', gap: 14 },
  row3:        { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 },
  row2:        { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 },
  section:     { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12, padding: 16 },
  sectionTitle:{ fontSize: 12, fontWeight: 600, color: '#475569', textTransform: 'uppercase',
                 letterSpacing: 0.8, marginBottom: 12 },
  metCard:     { background: '#0d1220', border: '1px solid #1a2744', borderRadius: 12, padding: 16,
                 display: 'flex', flexDirection: 'column', gap: 4 },
  metIcon:     { fontSize: 22, marginBottom: 4 },
  metTitle:    { fontSize: 11, color: '#475569', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.6 },
  metValue:    { fontSize: 26, fontWeight: 700 },
  metSub:      { fontSize: 11, color: '#334155' },
  confWrap:    { marginTop: 8 },
  confLabel:   { fontSize: 11, color: '#475569', marginBottom: 3 },
  confTrack:   { height: 4, background: '#1a2744', borderRadius: 2, overflow: 'hidden' },
  confFill:    { height: '100%', borderRadius: 2, transition: 'width 0.5s ease' },
  statsList:   { display: 'flex', flexDirection: 'column', gap: 0 },
  statRow:     { display: 'flex', justifyContent: 'space-between', padding: '6px 0',
                 borderBottom: '1px solid #0f1829' },
  statKey:     { color: '#475569', fontSize: 12 },
  statVal:     { color: '#94a3b8', fontSize: 12, fontWeight: 500 },
  saveBtn:     { marginTop: 12, width: '100%', padding: '8px 0', background: '#172554',
                 border: '1px solid #1d4ed8', borderRadius: 8, color: '#93c5fd',
                 cursor: 'pointer', fontSize: 12, fontWeight: 600 },
  table:       { overflowX: 'auto' },
  tableHead:   { display: 'grid', gridTemplateColumns: '80px repeat(6,1fr)',
                 gap: 4, padding: '6px 8px', background: '#0a0f1e', borderRadius: 6, marginBottom: 4 },
  tableRow:    i => ({
    display: 'grid', gridTemplateColumns: '80px repeat(6,1fr)',
    gap: 4, padding: '5px 8px', borderRadius: 4,
    background: i % 2 === 0 ? '#0a0f1e' : 'transparent',
  }),
  th:          { fontSize: 10, fontWeight: 600, color: '#334155', textTransform: 'uppercase', letterSpacing: 0.5 },
  td:          { fontSize: 11, color: '#94a3b8' },
  emptyTable:  { textAlign: 'center', color: '#334155', padding: 16, fontSize: 13 },
  arch:        { display: 'flex', flexDirection: 'column', gap: 4 },
  archBlock:   { borderRadius: 8, padding: '8px 12px' },
  archLabel:   { fontSize: 12, fontWeight: 700, color: '#e2e8f0', marginBottom: 2 },
  archDetail:  { fontSize: 11, color: '#94a3b8' },
  archNote:    { marginTop: 10, fontSize: 11, color: '#475569', lineHeight: 1.6,
                 background: '#0a0f1e', borderRadius: 8, padding: '8px 12px' },
  empty:       { textAlign: 'center', color: '#334155', padding: '24px 0', fontSize: 13 },
}
