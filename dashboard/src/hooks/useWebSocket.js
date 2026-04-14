import { useState, useEffect, useRef, useCallback } from 'react'

// ── DEMO MODE ────────────────────────────────────────────────────────────────
// Set to true to run the UI with fake data (no backend needed for testing)
const DEMO_MODE = false

// ── WebSocket URL ─────────────────────────────────────────────────────────────
// Use window.location.host so the Vite proxy (/ws → ws://localhost:8765) works.
// Do NOT hardcode :8765 here — that bypasses the proxy and causes WS failures.
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss' : 'ws'
const WS_URL = `${WS_PROTOCOL}://${window.location.host}/ws`

// ── Demo data generator ───────────────────────────────────────────────────────
const STATES = ['focused', 'confused', 'high_load', 'fatigued', 'distracted']
let _demoState = 'focused'
let _demoFrame = 0

function makeDemoFrame() {
  _demoFrame++
  const t = Date.now() / 1000
  const focus = 0.4 + 0.3 * Math.sin(_demoFrame / 30) + Math.random() * 0.1
  const load  = 0.3 + 0.2 * Math.cos(_demoFrame / 20) + Math.random() * 0.1
  const proc  = Math.max(0, Math.min(100, 30 + 20 * Math.sin(_demoFrame / 50) + Math.random() * 10))
  if (_demoFrame % 150 === 0)
    _demoState = STATES[Math.floor(Math.random() * STATES.length)]
  return {
    type: 'data',
    timestamp: t,
    frame: _demoFrame,
    cognitive: {
      state: _demoState,
      label: `${_demoState.replace('_', ' ')} 🟢`,
      focus:     Math.max(0, Math.min(1, focus)),
      load:      Math.max(0, Math.min(1, load)),
      fatigue:   Math.random() * 0.3,
      confusion: Math.random() * 0.2,
      distraction: Math.random() * 0.2,
      confidence: 0.75 + Math.random() * 0.2,
    },
    switch: {
      phase: 'focused',
      label: 'On Task ✅',
      predicted: false,
      pred_conf: 0,
      pred_in_sec: 0,
      total_switches: Math.floor(_demoFrame / 200),
      rate_per_hr: 3.2,
    },
    procrastination: {
      score: proc,
      risk_level: proc > 70 ? 'high' : proc > 40 ? 'medium' : 'low',
      label: `Risk ${proc.toFixed(0)}%`,
      rising: Math.random() > 0.7,
      components: {
        hesitation: Math.random() * 0.4,
        gaze_drift: Math.random() * 0.3,
        fidgeting:  Math.random() * 0.2,
        switch_intent: Math.random() * 0.15,
        cognitive_load: Math.max(0, Math.min(1, load)),
      },
      stats: {
        avg_procrastination: proc.toFixed(1),
        top_trigger: 'frustration',
        session_duration_min: (_demoFrame / 30 / 60).toFixed(1),
      },
    },
    ml_model: {
      switch_probability: Math.random() * 0.4,
      procrastination_score: proc / 100,
      cognitive_state: _demoState,
      cognitive_state_probs: { focused: 0.5, confused: 0.2, high_load: 0.15, fatigued: 0.1, distracted: 0.05 },
      switch_confidence: 0.6 + Math.random() * 0.3,
      state_confidence:  0.7 + Math.random() * 0.25,
      label: 'Stable',
      model_version: 'demo-mode',
    },
    intervention: { active: false },
    recovery: { active: false, actions: [] },
    ripple: { active: false },
    meta_insight: { active: false },
    signature: { avg_switch_duration: 12, avg_recovery_duration: 28, recovery_improving: true, insights: ['Demo mode active'] },
    metrics_snapshot: {
      focus_percentage: focus * 100,
      procrastination_rate: proc,
      switch_count: Math.floor(_demoFrame / 200),
      deep_work_duration: 142,
      avg_switch_cost: 35,
      session_duration_min: _demoFrame / 30 / 60,
    },
    signals: {
      head_yaw_dev: (Math.random() - 0.5) * 2,
      gaze_instability: Math.random() * 0.3,
      ear: 0.25 + Math.random() * 0.1,
      blink_rate: 12 + Math.random() * 6,
      brow_furrow: Math.random() * 0.4,
      forward_lean: Math.random() * 0.3,
      body_stability: 0.7 + Math.random() * 0.3,
      face_touch: Math.random() > 0.95,
      hand_speed: Math.random() * 0.2,
      quality: 0.85 + Math.random() * 0.1,
    },
  }
}

// ── Hook ──────────────────────────────────────────────────────────────────────
export function useWebSocket() {
  const [data,    setData]    = useState(null)
  const [status,  setStatus]  = useState(DEMO_MODE ? 'connected' : 'connecting')
  const [history, setHistory] = useState([])
  const wsRef    = useRef(null)
  const timerRef = useRef(null)

  // ── Helper: push a frame into history ─────────────────────────────────────
  const pushFrame = useCallback((msg) => {
    if (!msg || msg.type !== 'data') return
    setData(msg)
    setHistory(prev => {
      const entry = {
        t:        msg.timestamp,
        focus:    (msg.cognitive?.focus ?? 0) * 100,
        proc:     msg.procrastination?.score ?? 0,
        load:     (msg.cognitive?.load  ?? 0) * 100,
        fatigue:  (msg.cognitive?.fatigue ?? 0) * 100,
        mlSwitch: (msg.ml_model?.switch_probability ?? 0) * 100,
        state:    msg.cognitive?.state ?? '',
      }
      const next = [...prev, entry]
      return next.length > 180 ? next.slice(-180) : next
    })
  }, [])

  // ── Demo mode: generate fake frames ──────────────────────────────────────
  useEffect(() => {
    if (!DEMO_MODE) return
    setStatus('connected')
    const id = setInterval(() => pushFrame(makeDemoFrame()), 500)
    return () => clearInterval(id)
  }, [pushFrame])

  // ── Real WebSocket ─────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (DEMO_MODE) return
    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen  = () => { setStatus('connected'); console.log('[WS] Connected to', WS_URL) }
      ws.onclose = () => {
        setStatus('disconnected')
        timerRef.current = setTimeout(connect, 3000)
      }
      ws.onerror = (e) => {
        console.warn('[WS] Error:', e)
        setStatus('error')
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (!msg) return
          if (msg.type === 'data') {
            pushFrame(msg)
          } else {
            // Pass calibrating / no_face / connected messages through
            setData(msg)
          }
        } catch (e) {
          console.error('[WS] Parse error:', e)
        }
      }
    } catch (e) {
      console.error('[WS] Connect failed:', e)
      setStatus('error')
    }
  }, [pushFrame])

  useEffect(() => {
    if (DEMO_MODE) return
    connect()
    return () => {
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  // Always return arrays/objects — never undefined
  return {
    data,
    status,
    history: Array.isArray(history) ? history : [],
  }
}
