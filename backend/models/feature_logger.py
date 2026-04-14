"""
backend/models/feature_logger.py
═══════════════════════════════════════════════════════════════
FocusForge v2 — Feature Logging Pipeline

Stores raw feature vectors, model predictions, and pseudo-labels
to a dedicated SQLite DB for offline training and visualisation.

Pseudo-label / Weak Supervision strategy
─────────────────────────────────────────
  No manual ground-truth annotations are required.  Labels are approximated
  from observable behavioural signals (research-valid approach):

  ┌───────────────────────────────┬───────────────────┐
  │ Observable signal             │ Pseudo-label      │
  ├───────────────────────────────┼───────────────────┤
  │ Hand inactivity > 8 s         │ distracted        │
  │ ≥3 rapid context switches     │ procrastinating   │
  │ Low motion + no typing > 5 s  │ confused          │
  │ Focus > 0.70 + stable gaze    │ focused           │
  └───────────────────────────────┴───────────────────┘

All writes are fire-and-forget via an async queue so the main
inference loop is never blocked.
"""

import json
import time
import logging
import os
import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Optional, List
import aiosqlite

logger = logging.getLogger("feature_logger")

# ── DB schema ─────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS feature_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER,
    timestamp        REAL,
    features_json    TEXT,
    pseudo_label     TEXT,
    label_confidence REAL,
    label_source     TEXT
);

CREATE TABLE IF NOT EXISTS prediction_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER,
    timestamp        REAL,
    switch_prob      REAL,
    proc_score       REAL,
    cognitive_state  TEXT,
    switch_conf      REAL,
    state_conf       REAL,
    model_version    TEXT
);

CREATE TABLE IF NOT EXISTS event_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       INTEGER,
    timestamp        REAL,
    event_type       TEXT,
    severity         TEXT,
    data_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_feature_session ON feature_log(session_id);
CREATE INDEX IF NOT EXISTS idx_pred_session    ON prediction_log(session_id);
CREATE INDEX IF NOT EXISTS idx_event_session   ON event_log(session_id);
"""


# ── Weak label struct ─────────────────────────────────────────────────────────

@dataclass
class PseudoLabel:
    label:      str    # focused / distracted / procrastinating / confused / fatigued
    confidence: float  # 0-1
    source:     str    # which rule fired


# ── Weak label generator ──────────────────────────────────────────────────────

class WeakLabelGenerator:
    """
    Generates pseudo-labels from observable behavioural signals.
    Called each time a feature vector is logged.
    """

    INACTIVITY_THRESHOLD_SEC = 8.0
    RAPID_SWITCH_THRESHOLD   = 3       # switches to trigger procrastination label
    LOW_MOTION_THRESHOLD     = 0.05
    HIGH_FOCUS_THRESHOLD     = 0.70
    HIGH_GAZE_STABLE         = 0.20    # gaze_instability below this = stable

    def __init__(self):
        self._last_motion_time = time.time()
        self._motion_buffer: deque = deque(maxlen=30)

    def generate(
        self,
        features_dict: dict,
        n_switches_session: int,
        hand_speed: float,
    ) -> Optional[PseudoLabel]:
        now = time.time()
        self._motion_buffer.append(hand_speed)

        # Update motion timer
        if hand_speed > 0.02:
            self._last_motion_time = now
        inactivity_sec = now - self._last_motion_time

        # Rule 1: hand inactivity → distracted
        if inactivity_sec > self.INACTIVITY_THRESHOLD_SEC:
            conf = min(inactivity_sec / 30.0, 1.0)
            return PseudoLabel("distracted", round(conf, 3), "keyboard_inactivity")

        # Rule 2: rapid switches → procrastinating
        if n_switches_session >= self.RAPID_SWITCH_THRESHOLD:
            conf = min(n_switches_session / 6.0, 1.0)
            return PseudoLabel("procrastinating", round(conf, 3), "rapid_context_switch")

        # Rule 3: low motion + no typing → confused
        avg_motion = sum(self._motion_buffer) / max(len(self._motion_buffer), 1)
        if avg_motion < self.LOW_MOTION_THRESHOLD and inactivity_sec > 5.0:
            return PseudoLabel("confused", 0.55, "long_pause_low_motion")

        # Rule 4: high focus + stable gaze → focused
        focus = features_dict.get("focus_score", 0.5)
        gaze  = features_dict.get("gaze_instability", 1.0)
        if focus > self.HIGH_FOCUS_THRESHOLD and gaze < self.HIGH_GAZE_STABLE:
            return PseudoLabel("focused", round(min(focus, 1.0), 3), "high_focus_stable_gaze")

        return None   # no confident label this frame


# ── Feature logger (main class) ───────────────────────────────────────────────

class FeatureLogger:
    """
    Async pipeline that logs:
      • Raw feature vectors  (+ pseudo-labels)
      • Model predictions
      • Named events (switch, high-proc, etc.)

    Uses a write-ahead in-memory queue so main inference loop is never blocked.
    """

    def __init__(self, db_path: str = "data/feature_log.db"):
        self.db_path      = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._session_id: Optional[int] = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self._label_gen   = WeakLabelGenerator()
        self._running     = False
        self._writer_task = None

    async def connect(self, session_id: int):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        self._session_id = session_id
        self._running    = True
        self._writer_task = asyncio.create_task(self._writer_loop())
        logger.info(f"FeatureLogger connected → {self.db_path}")

    async def disconnect(self):
        self._running = False
        if self._writer_task:
            self._writer_task.cancel()
        await self._flush_queue()
        if self._conn:
            await self._conn.close()
        logger.info("FeatureLogger disconnected.")

    # ── Public logging API ────────────────────────────────────────────────────

    async def log_features(
        self,
        features_dict: dict,
        n_switches_session: int,
        hand_speed: float,
    ):
        label = self._label_gen.generate(features_dict, n_switches_session, hand_speed)
        await self._enqueue({
            "type":             "feature",
            "session_id":       self._session_id,
            "timestamp":        time.time(),
            "features_json":    json.dumps(features_dict),
            "pseudo_label":     label.label      if label else None,
            "label_confidence": label.confidence if label else None,
            "label_source":     label.source     if label else None,
        })

    async def log_prediction(self, prediction):
        await self._enqueue({
            "type":            "prediction",
            "session_id":      self._session_id,
            "timestamp":       prediction.timestamp,
            "switch_prob":     prediction.switch_probability,
            "proc_score":      prediction.procrastination_score,
            "cognitive_state": prediction.cognitive_state,
            "switch_conf":     prediction.switch_confidence,
            "state_conf":      prediction.state_confidence,
            "model_version":   prediction.model_version,
        })

    async def log_event(self, event_type: str, severity: str, data: dict):
        await self._enqueue({
            "type":       "event",
            "session_id": self._session_id,
            "timestamp":  time.time(),
            "event_type": event_type,
            "severity":   severity,
            "data_json":  json.dumps(data),
        })

    # ── Queue I/O ─────────────────────────────────────────────────────────────

    async def _enqueue(self, record: dict):
        try:
            self._queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.debug("FeatureLogger queue full, dropping record")

    async def _writer_loop(self):
        while self._running:
            try:
                record = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._write(record)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"FeatureLogger write error: {e}")

    async def _write(self, record: dict):
        rtype = record.get("type")
        if rtype == "feature":
            await self._conn.execute(
                """INSERT INTO feature_log
                   (session_id,timestamp,features_json,pseudo_label,label_confidence,label_source)
                   VALUES (?,?,?,?,?,?)""",
                (record["session_id"], record["timestamp"], record["features_json"],
                 record["pseudo_label"], record["label_confidence"], record["label_source"]),
            )
        elif rtype == "prediction":
            await self._conn.execute(
                """INSERT INTO prediction_log
                   (session_id,timestamp,switch_prob,proc_score,cognitive_state,
                    switch_conf,state_conf,model_version)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (record["session_id"], record["timestamp"], record["switch_prob"],
                 record["proc_score"], record["cognitive_state"], record["switch_conf"],
                 record["state_conf"], record["model_version"]),
            )
        elif rtype == "event":
            await self._conn.execute(
                """INSERT INTO event_log
                   (session_id,timestamp,event_type,severity,data_json)
                   VALUES (?,?,?,?,?)""",
                (record["session_id"], record["timestamp"], record["event_type"],
                 record["severity"], record["data_json"]),
            )
        await self._conn.commit()

    async def _flush_queue(self):
        while not self._queue.empty():
            try:
                record = self._queue.get_nowait()
                await self._write(record)
            except Exception:
                break

    # ── Analytics queries ─────────────────────────────────────────────────────

    async def get_labelled_samples(self, limit: int = 1000) -> List[dict]:
        """Return pseudo-labelled feature vectors for offline training."""
        if not self._conn:
            return []
        async with self._conn.execute(
            """SELECT timestamp, features_json, pseudo_label, label_confidence, label_source
               FROM feature_log WHERE pseudo_label IS NOT NULL
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for r in rows:
            item = {
                "timestamp":        r[0],
                "features":         json.loads(r[1]),
                "pseudo_label":     r[2],
                "label_confidence": r[3],
                "label_source":     r[4],
            }
            result.append(item)
        return result

    async def get_stats(self) -> dict:
        if not self._conn:
            return {}
        async with self._conn.execute(
            """SELECT COUNT(*) as n, COUNT(pseudo_label) as labelled
               FROM feature_log WHERE session_id=?""",
            (self._session_id,),
        ) as cur:
            row = await cur.fetchone()

        async with self._conn.execute(
            """SELECT COUNT(*) as n FROM prediction_log WHERE session_id=?""",
            (self._session_id,),
        ) as cur:
            pred_row = await cur.fetchone()

        return {
            "total_features":   row[0]    if row    else 0,
            "labelled_samples": row[1]    if row    else 0,
            "total_predictions":pred_row[0] if pred_row else 0,
            "queue_size":       self._queue.qsize(),
            "db_path":          self.db_path,
        }
