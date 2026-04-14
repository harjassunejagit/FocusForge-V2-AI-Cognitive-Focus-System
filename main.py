"""
main.py — FocusForge v2
═══════════════════════════════════════════════════════════════
FastAPI server + WebSocket real-time streaming.

8-stage processing pipeline per frame:
  Stage 1  Calibration
  Stage 2  Kalman-filtered signal processing
  Stage 3  Cognitive modules (state, switch, procrastination…)
  Stage 4  ML Model Layer   (LSTM temporal_model.py)        ← NEW v2
  Stage 5  Event Bus        (event_bus.py)                  ← NEW v2
  Stage 6  Metrics Dashboard (metrics.py)                   ← NEW v2
  Stage 7  Periodic DB + Feature Logging                    ← NEW v2
  Stage 8  Build WebSocket payload

New REST endpoints (v2):
  GET  /api/metrics              — full session metrics
  GET  /api/metrics/timeline     — prediction timeline
  GET  /api/metrics/graph        — time-series for Recharts
  GET  /api/metrics/cards        — summary card data
  GET  /api/model/stats          — LSTM stats
  GET  /api/model/predictions    — last 50 predictions
  GET  /api/events               — recent event bus events
  GET  /api/events/stats         — subscriber counts
  GET  /api/feature-log/stats    — logging pipeline stats
  GET  /api/db/dashboard         — full DB snapshot for React
  POST /api/model/save-weights   — persist LSTM weights
"""

import asyncio
import json
import logging
import time
import os
from pathlib import Path
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── Original module imports ───────────────────────────────────────────────────
from backend.camera.webcam_capture import WebcamCapture
from backend.camera.mediapipe_analyzer import RawSignals
from backend.modules.signal_processor import (
    SignalProcessor, CalibrationBuffer, UserBaseline, ProcessedSignals,
)
from backend.modules.cognitive_state import CognitiveStateModel, CognitiveSnapshot
from backend.modules.context_switch import ContextSwitchDetector, SwitchDetectorOutput
from backend.modules.procrastination import ProcrastinationAnalyzer, ProcrastinationOutput
from backend.modules.cognitive_signature import CognitiveSignatureModel
from backend.modules.temporal_impact import TemporalImpactTracker, MetaCognitionModule
from backend.modules.recovery_optimizer import RecoveryOptimizer
from backend.database.db import CognitiveDB

# ── v2 imports ────────────────────────────────────────────────────────────────
from backend.models.temporal_model import CognitiveLSTMModel, build_feature_vector
from backend.models.feature_logger import FeatureLogger
from backend.events.event_bus import (
    EventBus, EventType, Event,
    emit_switch, emit_high_procrastination, emit_recovery,
    emit_model_prediction, emit_focus_lost,
)
from backend.api.metrics import MetricsDashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

# ── Config ────────────────────────────────────────────────────────────────────
CONFIG: dict = {}
CONFIG_PATH = Path(__file__).parent / "config" / "config.yaml"
if CONFIG_PATH.exists():
    import yaml
    with open(CONFIG_PATH) as f:
        CONFIG = yaml.safe_load(f) or {}

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI(title="FocusForge AI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR  = Path(__file__).parent / "frontend"
DASHBOARD_DIR = Path(__file__).parent / "dashboard" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


@app.get("/")
async def root():
    if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
        return FileResponse(str(FRONTEND_DIR / "index.html"))
    return {"status": "FocusForge API v2 running", "docs": "/docs", "dashboard": "/dashboard"}


# ── Pipeline ──────────────────────────────────────────────────────────────────

class Pipeline:
    """Owns all modules and runs the frame-by-frame processing loop."""

    def __init__(self):
        self.config     = CONFIG
        self.cam_config = CONFIG.get("camera", {})
        self.cal_config = CONFIG.get("calibration", {})

        # ── Camera + DB ───────────────────────────────────────────────────────
        self.webcam = WebcamCapture(self.cam_config)
        self.db     = CognitiveDB(
            CONFIG.get("database", {}).get("path", "data/cognitive_data.db")
        )

        # ── Signal pipeline ───────────────────────────────────────────────────
        self.calibration = CalibrationBuffer(
            self.cal_config.get("required_frames", 200)
        )
        self.calibrated = False
        self.baseline   = UserBaseline()
        self.processor  = SignalProcessor(CONFIG, self.baseline)

        # ── Cognitive modules (original) ──────────────────────────────────────
        self.cog_model     = CognitiveStateModel(CONFIG)
        self.sw_detector   = ContextSwitchDetector(CONFIG)
        self.proc_analyzer = ProcrastinationAnalyzer(CONFIG)
        self.sig_model     = CognitiveSignatureModel("default")
        self.ripple        = TemporalImpactTracker()
        self.meta_cog      = MetaCognitionModule()
        self.recovery      = RecoveryOptimizer()

        # ── v2: ML Model Layer ────────────────────────────────────────────────
        weights_path = CONFIG.get("model", {}).get(
            "weights_path", "data/lstm_weights.json"
        )
        self.lstm_model = CognitiveLSTMModel(weights_path=weights_path)

        # ── v2: Feature Logger ────────────────────────────────────────────────
        feat_log_path = CONFIG.get("database", {}).get(
            "feature_log_path", "data/feature_log.db"
        )
        self.feat_logger = FeatureLogger(db_path=feat_log_path)

        # ── v2: Event Bus ─────────────────────────────────────────────────────
        self.event_bus = EventBus()
        self._register_bus_handlers()

        # ── v2: Metrics Dashboard ─────────────────────────────────────────────
        self.metrics = MetricsDashboard()

        # ── Runtime state ─────────────────────────────────────────────────────
        self.session_id:    Optional[int] = None
        self.frame_count    = 0
        self._score_history = []
        self._last_db_write = 0.0
        self._last_log_write= 0.0
        self._db_interval   = 5.0    # seconds between DB snapshots
        self._log_interval  = 2.0    # seconds between feature log writes
        self._prev_focus    = 0.5

        # WebSocket clients
        self.clients: Set[WebSocket] = set()

    def _register_bus_handlers(self):
        async def on_switch(ev: Event):
            logger.info(f"[Bus] SWITCH_DETECTED  cost={ev.data.get('cost_sec', '?')}s")

        async def on_proc(ev: Event):
            logger.warning(f"[Bus] HIGH_PROC  score={ev.data.get('score', '?'):.2f}")

        async def on_deep_work(ev: Event):
            logger.info("[Bus] DEEP_WORK_ENTERED")

        self.event_bus.subscribe(EventType.SWITCH_DETECTED,      on_switch)
        self.event_bus.subscribe(EventType.HIGH_PROCRASTINATION,  on_proc)
        self.event_bus.subscribe(EventType.DEEP_WORK_ENTERED,     on_deep_work)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> bool:
        await self.db.connect()
        self.session_id = await self.db.start_session()
        await self.feat_logger.connect(self.session_id)

        saved = await self.db.load_baseline("default")
        if saved:
            try:
                self.baseline   = UserBaseline(**saved)
                self.calibrated = self.baseline.calibrated
                self.processor.update_baseline(self.baseline)
                logger.info("Loaded saved baseline from DB.")
            except Exception as e:
                logger.warning(f"Could not restore baseline: {e}")

        if not self.webcam.start():
            logger.error("Could not start webcam.")
            return False

        await self.event_bus.publish(Event(
            EventType.SESSION_STARTED, {"session_id": self.session_id}
        ))
        logger.info("FocusForge v2 pipeline started.")
        return True

    async def stop(self):
        self.webcam.stop()
        try:
            stats = self.proc_analyzer.learner.get_session_stats()
        except Exception:
            stats = {}
        await self.db.end_session(stats)
        await self.feat_logger.disconnect()
        await self.db.disconnect()
        await self.event_bus.publish(Event(EventType.SESSION_ENDED, {}))
        logger.info("Pipeline stopped.")

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run_loop(self):
        while True:
            try:
                if not self.webcam.signal_queue.empty():
                    raw: RawSignals = self.webcam.signal_queue.get_nowait()
                    payload = await self._process(raw)
                    if payload and self.clients:
                        await self._broadcast(payload)
                await asyncio.sleep(0.033)   # ~30 fps
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pipeline loop error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    # ── Per-frame processing ──────────────────────────────────────────────────

    async def _process(self, raw: RawSignals) -> Optional[dict]:
        self.frame_count += 1

        # ── Stage 1: Calibration ──────────────────────────────────────────────
        if not self.calibrated:
            self.calibration.add(raw)
            progress = (
                len(self.calibration.buffers["head_yaw"])
                / self.calibration.required * 100
            )
            if self.calibration.is_complete:
                await self._complete_calibration()
            return {
                "type":      "calibrating",
                "progress":  round(progress, 1),
                "message":   f"Calibrating… {progress:.0f}%",
                "timestamp": raw.timestamp,
            }

        # ── Stage 2: Signal processing ────────────────────────────────────────
        sig: ProcessedSignals = self.processor.process(raw)
        if not sig.face_visible:
            return {
                "type":      "no_face",
                "message":   "Face not detected. Look at the camera.",
                "timestamp": sig.timestamp,
            }

        # ── Stage 3: Cognitive modules ────────────────────────────────────────
        cog: CognitiveSnapshot      = self.cog_model.update(sig)
        sw:  SwitchDetectorOutput   = self.sw_detector.update(sig, cog)
        proc: ProcrastinationOutput = self.proc_analyzer.update(sig, cog, sw)
        ripple                      = self.ripple.update(sw, cog)
        recovery_plan               = self.recovery.update(sw, cog)

        self._score_history.append(proc.score.score)
        if len(self._score_history) > 300:
            self._score_history.pop(0)
        meta_insight = self.meta_cog.update(sw, cog, self._score_history)

        # ── Stage 4: ML Model Layer ───────────────────────────────────────────
        features = build_feature_vector(sig, cog, proc.score.score)
        ml_pred  = self.lstm_model.predict(features)

        # ── Stage 5: Event Bus ────────────────────────────────────────────────
        if sw.last_completed_event:
            ev = sw.last_completed_event
            await self.db.insert_switch_event(ev.__dict__)
            self.sig_model.record_switch(ev)
            await emit_switch(self.event_bus, {
                "phase":            sw.phase.value,
                "cost_sec":         getattr(ev, "total_cost_seconds", 0),
                "switch_confidence":ml_pred.switch_confidence,
            })

        if proc.score.score > 0.7:
            await emit_high_procrastination(
                self.event_bus, proc.score.score, proc.score.risk_level.value
            )

        if cog.focus_score > 0.65 and self._prev_focus <= 0.65:
            await self.event_bus.publish(
                Event(EventType.DEEP_WORK_ENTERED, {"focus": cog.focus_score})
            )
        if cog.focus_score < 0.35 and self._prev_focus >= 0.35:
            await emit_focus_lost(self.event_bus, cog.focus_score)

        await emit_model_prediction(self.event_bus, ml_pred)
        self._prev_focus = cog.focus_score

        # ── Stage 6: Metrics Dashboard ────────────────────────────────────────
        self.metrics.update(
            cognitive_state = cog.state.value,
            focus_score     = cog.focus_score,
            proc_score      = proc.score.score,
            switch_phase    = sw.phase.value,
            switch_cost_sec = (
                getattr(sw.last_completed_event, "total_cost_seconds", None)
                if sw.last_completed_event else None
            ),
            recovery_sec    = (
                getattr(sw.last_completed_event, "recovery_duration", None)
                if sw.last_completed_event else None
            ),
        )

        # ── Stage 7: Periodic DB + Feature Logging ────────────────────────────
        now = time.time()

        if now - self._last_db_write >= self._db_interval:
            self._last_db_write = now
            await self.db.insert_cognitive_snapshot(
                cog.state.value, cog.focus_score,
                cog.cognitive_load, cog.fatigue_score, cog.confusion_score,
            )
            await self.db.insert_procrastination_sample(
                proc.score.score,
                proc.score.risk_level.value,
                proc.trigger.trigger.value if proc.trigger else None,
                proc.score.components,
            )

        if now - self._last_log_write >= self._log_interval:
            self._last_log_write = now
            await self.feat_logger.log_features(
                features_dict      = features.to_dict(),
                n_switches_session = sw.total_switches_session,
                hand_speed         = sig.hand_speed,
            )
            await self.feat_logger.log_prediction(ml_pred)

        # ── Stage 8: Build WebSocket payload ──────────────────────────────────
        m_snap = self.metrics.get_metrics()
        sig_obj = self.sig_model.get_signature()

        return {
            "type":      "data",
            "timestamp": sig.timestamp,
            "frame":     self.frame_count,

            # ── Signals ──────────────────────────────────────────────────────
            "signals": {
                "head_yaw_dev":     round(sig.head_yaw_dev,     2),
                "gaze_instability": round(sig.gaze_instability, 3),
                "ear":              round(sig.ear,              3),
                "blink_rate":       round(sig.blink_rate,       1),
                "brow_furrow":      round(sig.brow_furrow,      3),
                "forward_lean":     round(sig.forward_lean,     3),
                "body_stability":   round(sig.body_stability,   3),
                "face_touch":       sig.face_touch,
                "hand_speed":       round(sig.hand_speed,       3),
                "quality":          round(sig.signal_quality,   2),
            },

            # ── Cognitive ────────────────────────────────────────────────────
            "cognitive": {
                "state":       cog.state.value,
                "label":       cog.label,
                "focus":       cog.focus_score,
                "confusion":   cog.confusion_score,
                "load":        cog.cognitive_load,
                "fatigue":     cog.fatigue_score,
                "distraction": cog.distraction_score,
                "confidence":  cog.confidence,   # rule-based confidence
            },

            # ── Switch ───────────────────────────────────────────────────────
            "switch": {
                "phase":          sw.phase.value,
                "label":          sw.label,
                "predicted":      sw.switch_predicted,
                "pred_conf":      sw.prediction_confidence,
                "pred_in_sec":    sw.switch_predicted_in_sec,
                "total_switches": sw.total_switches_session,
                "rate_per_hr":    sw.switch_rate_per_hour,
            },

            # ── Procrastination ───────────────────────────────────────────────
            "procrastination": {
                "score":      round(proc.score.score * 100, 1),
                "risk_level": proc.score.risk_level.value,
                "label":      proc.score.label,
                "rising":     proc.score.rising,
                "components": proc.score.components,
                "stats":      proc.session_stats,
            },

            # ── Intervention ──────────────────────────────────────────────────
            "intervention": (
                {
                    "active":  True,
                    "message": proc.intervention.message,
                    "type":    proc.intervention.type,
                    "urgency": proc.intervention.urgency,
                }
                if proc.intervention else {"active": False}
            ),

            # ── Recovery ──────────────────────────────────────────────────────
            "recovery": {
                "active":        recovery_plan is not None,
                "plan_label":    recovery_plan.label if recovery_plan else None,
                "actions":       [
                    {"instruction": a.instruction, "duration": a.duration_sec}
                    for a in recovery_plan.actions
                ] if recovery_plan else [],
                "predicted_sec": recovery_plan.predicted_recovery_sec if recovery_plan else None,
            },

            # ── Ripple ────────────────────────────────────────────────────────
            "ripple": {
                "active":           ripple is not None,
                "focus_drop_pct":   ripple.focus_drop_pct   if ripple else 0,
                "error_likelihood": ripple.error_likelihood  if ripple else 0,
                "label":            ripple.label             if ripple else None,
            },

            # ── Meta insight ──────────────────────────────────────────────────
            "meta_insight": {
                "active":   meta_insight is not None,
                "message":  meta_insight.message  if meta_insight else None,
                "category": meta_insight.category if meta_insight else None,
            },

            # ── Cognitive signature ───────────────────────────────────────────
            "signature": {
                "avg_switch_duration":   round(sig_obj.avg_switch_duration,   1),
                "avg_recovery_duration": round(sig_obj.avg_recovery_duration, 1),
                "recovery_improving":    sig_obj.recovery_improving,
                "insights":              sig_obj.insights[:3],
            },

            # ── ML Model (v2) ─────────────────────────────────────────────────
            "ml_model": {
                "switch_probability":    ml_pred.switch_probability,
                "procrastination_score": ml_pred.procrastination_score,
                "cognitive_state":       ml_pred.cognitive_state,
                "cognitive_state_probs": ml_pred.cognitive_state_probs,
                "switch_confidence":     ml_pred.switch_confidence,
                "state_confidence":      ml_pred.state_confidence,
                "label":                 ml_pred.label,
                "model_version":         ml_pred.model_version,
            },

            # ── Live metrics snapshot (v2) ────────────────────────────────────
            "metrics_snapshot": {
                "focus_percentage":     m_snap.focus_percentage,
                "procrastination_rate": round(m_snap.procrastination_rate * 100, 1),
                "switch_count":         m_snap.switch_count,
                "deep_work_duration":   m_snap.deep_work_duration,
                "avg_switch_cost":      m_snap.avg_switch_cost,
                "session_duration_min": m_snap.session_duration_min,
            },
        }

    async def _complete_calibration(self):
        self.baseline   = self.calibration.build_baseline()
        self.calibrated = True
        self.processor.update_baseline(self.baseline)
        await self.db.save_baseline("default", self.baseline.__dict__)
        await self.event_bus.publish(
            Event(EventType.CALIBRATION_DONE, {"timestamp": time.time()})
        )
        logger.info("Calibration complete and saved.")

    async def _broadcast(self, data: dict):
        dead = set()
        msg  = json.dumps(data)
        for ws in self.clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self.clients -= dead


# ── Singleton ─────────────────────────────────────────────────────────────────
pipeline = Pipeline()
_bg_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def startup():
    global _bg_task
    ok = await pipeline.start()
    if ok:
        _bg_task = asyncio.create_task(pipeline.run_loop())
        logger.info("Background pipeline task started.")


@app.on_event("shutdown")
async def shutdown():
    global _bg_task
    if _bg_task:
        _bg_task.cancel()
    await pipeline.stop()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    pipeline.clients.add(ws)
    logger.info(f"WS connected. Total: {len(pipeline.clients)}")
    try:
        await ws.send_json({
            "type":       "connected",
            "calibrated": pipeline.calibrated,
            "session_id": pipeline.session_id,
        })
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        pipeline.clients.discard(ws)
        logger.info(f"WS disconnected. Total: {len(pipeline.clients)}")


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":      "ok",
        "version":     "2.0.0",
        "webcam":      pipeline.webcam.is_running,
        "calibrated":  pipeline.calibrated,
        "frame_count": pipeline.frame_count,
        "clients":     len(pipeline.clients),
    }

# ── v1 endpoints (kept for backward compat) ───────────────────────────────────

@app.get("/api/session/summary")
async def session_summary():
    return await pipeline.db.get_session_summary()

@app.get("/api/sessions")
async def recent_sessions():
    return await pipeline.db.get_recent_sessions()

@app.get("/api/signature")
async def cognitive_signature():
    sig = pipeline.sig_model.get_signature()
    return {
        "avg_switch_duration":   sig.avg_switch_duration,
        "avg_recovery_duration": sig.avg_recovery_duration,
        "switch_frequency":      sig.switch_frequency_per_hr,
        "primary_trigger":       sig.primary_trigger,
        "insights":              sig.insights,
        "recovery_improving":    sig.recovery_improving,
        "procrastination_trend": sig.procrastination_trend_pct,
    }

@app.post("/api/recalibrate")
async def recalibrate():
    pipeline.calibrated  = False
    pipeline.calibration = CalibrationBuffer(
        pipeline.cal_config.get("required_frames", 200)
    )
    return {"status": "calibration_started"}

# ── v2 endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    return pipeline.metrics.get_metrics().to_dict()

@app.get("/api/metrics/timeline")
async def get_timeline(last_n: int = 100):
    return pipeline.metrics.get_timeline_for_api(last_n)

@app.get("/api/metrics/graph")
async def get_graph_data(points: int = 60):
    return pipeline.metrics.get_graph_data(points)

@app.get("/api/metrics/cards")
async def get_cards():
    return pipeline.metrics.get_summary_cards()

@app.get("/api/model/stats")
async def model_stats():
    return pipeline.lstm_model.get_model_stats()

@app.get("/api/model/predictions")
async def recent_predictions():
    preds = list(pipeline.lstm_model._pred_history)[-50:]
    return [
        {
            "timestamp":          p.timestamp,
            "switch_probability": p.switch_probability,
            "procrastination":    p.procrastination_score,
            "cognitive_state":    p.cognitive_state,
            "switch_confidence":  p.switch_confidence,
            "state_confidence":   p.state_confidence,
            "label":              p.label,
        }
        for p in preds
    ]

@app.post("/api/model/save-weights")
async def save_weights():
    path = CONFIG.get("model", {}).get("weights_path", "data/lstm_weights.json")
    pipeline.lstm_model.save_weights(path)
    return {"status": "saved", "path": path}

@app.get("/api/events")
async def recent_events(n: int = 50):
    events = pipeline.event_bus.get_recent_events(n)
    return [
        {
            "type":      e.type.value,
            "data":      e.data,
            "timestamp": e.timestamp,
            "severity":  e.severity,
            "age_sec":   round(e.age_seconds, 1),
        }
        for e in events
    ]

@app.get("/api/events/stats")
async def event_stats():
    return pipeline.event_bus.get_stats()

@app.get("/api/feature-log/stats")
async def feature_log_stats():
    return await pipeline.feat_logger.get_stats()

@app.get("/api/db/dashboard")
async def db_dashboard():
    return await pipeline.db.get_full_dashboard_data()

@app.get("/api/db/cognitive-history")
async def cognitive_history(limit: int = 200):
    return await pipeline.db.get_cognitive_history(limit=limit)

@app.get("/api/db/switch-history")
async def switch_history(limit: int = 50):
    return await pipeline.db.get_switch_history(limit=limit)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = CONFIG.get("app", {}).get("host", "127.0.0.1")
    port = CONFIG.get("app", {}).get("port", 8765)
    uvicorn.run("main:app", host=host, port=port, reload=False)
