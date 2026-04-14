"""
backend/database/db.py
═══════════════════════════════════════════════════════════════
FocusForge v2 — Async SQLite database

Unchanged tables from v1:
  sessions, switch_events, procrastination_events,
  cognitive_snapshots, user_baselines, insights

New in v2:
  get_cognitive_history()   — time-series for React charts
  get_switch_history()      — switch event list for timeline
  get_full_dashboard_data() — single-call summary for React
"""

import aiosqlite
import json
import time
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("database")

DB_PATH = "data/cognitive_data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    REAL NOT NULL,
    ended_at      REAL,
    duration_min  REAL,
    stats_json    TEXT
);

CREATE TABLE IF NOT EXISTS switch_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER,
    switch_id         INTEGER,
    started_at        REAL,
    switch_duration   REAL,
    recovery_duration REAL,
    total_cost        REAL,
    productivity_drop REAL,
    cognitive_state   TEXT,
    trigger_signals   TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS procrastination_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER,
    timestamp   REAL,
    score       REAL,
    risk_level  TEXT,
    trigger     TEXT,
    components  TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS cognitive_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER,
    timestamp   REAL,
    state       TEXT,
    focus       REAL,
    load        REAL,
    fatigue     REAL,
    confusion   REAL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS user_baselines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL,
    created_at    REAL,
    baseline_json TEXT
);

CREATE TABLE IF NOT EXISTS insights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER,
    timestamp   REAL,
    category    TEXT,
    message     TEXT,
    data_json   TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_cog_session  ON cognitive_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_sw_session   ON switch_events(session_id);
CREATE INDEX IF NOT EXISTS idx_proc_session ON procrastination_events(session_id);
"""


class CognitiveDB:
    """Async SQLite database manager for FocusForge v2."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._session_id: Optional[int] = None

    async def connect(self):
        import os
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        logger.info(f"Database connected: {self.db_path}")

    async def disconnect(self):
        if self._conn:
            await self._conn.close()
        logger.info("Database disconnected.")

    # ── Session ───────────────────────────────────────────────────────────────

    async def start_session(self) -> int:
        async with self._conn.execute(
            "INSERT INTO sessions (started_at) VALUES (?)", (time.time(),)
        ) as cur:
            self._session_id = cur.lastrowid
        await self._conn.commit()
        logger.info(f"Session #{self._session_id} started")
        return self._session_id

    async def end_session(self, stats: dict):
        if not self._session_id:
            return
        now = time.time()
        async with self._conn.execute(
            "SELECT started_at FROM sessions WHERE id=?", (self._session_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            dur = (now - row["started_at"]) / 60.0
            await self._conn.execute(
                "UPDATE sessions SET ended_at=?, duration_min=?, stats_json=? WHERE id=?",
                (now, dur, json.dumps(stats), self._session_id),
            )
            await self._conn.commit()
        logger.info(f"Session #{self._session_id} ended.")

    # ── Inserts ───────────────────────────────────────────────────────────────

    async def insert_switch_event(self, event_dict: dict):
        if not self._session_id:
            return
        await self._conn.execute(
            """INSERT INTO switch_events
               (session_id,switch_id,started_at,switch_duration,
                recovery_duration,total_cost,productivity_drop,
                cognitive_state,trigger_signals)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                self._session_id,
                event_dict.get("id"),
                event_dict.get("switch_started_at"),
                event_dict.get("switch_duration"),
                event_dict.get("recovery_duration"),
                event_dict.get("total_cost_seconds"),
                event_dict.get("productivity_drop_pct"),
                event_dict.get("cognitive_state_at_switch"),
                json.dumps(event_dict.get("trigger_signals", {})),
            ),
        )
        await self._conn.commit()

    async def insert_procrastination_sample(
        self, score: float, risk_level: str, trigger: Optional[str], components: dict
    ):
        if not self._session_id:
            return
        await self._conn.execute(
            """INSERT INTO procrastination_events
               (session_id,timestamp,score,risk_level,trigger,components)
               VALUES (?,?,?,?,?,?)""",
            (self._session_id, time.time(), score, risk_level,
             trigger, json.dumps(components)),
        )
        await self._conn.commit()

    async def insert_cognitive_snapshot(
        self, state: str, focus: float, load: float, fatigue: float, confusion: float
    ):
        if not self._session_id:
            return
        await self._conn.execute(
            """INSERT INTO cognitive_snapshots
               (session_id,timestamp,state,focus,load,fatigue,confusion)
               VALUES (?,?,?,?,?,?,?)""",
            (self._session_id, time.time(), state, focus, load, fatigue, confusion),
        )
        await self._conn.commit()

    async def insert_insight(self, category: str, message: str, data: dict):
        if not self._session_id:
            return
        await self._conn.execute(
            """INSERT INTO insights (session_id,timestamp,category,message,data_json)
               VALUES (?,?,?,?,?)""",
            (self._session_id, time.time(), category, message, json.dumps(data)),
        )
        await self._conn.commit()

    # ── Baseline ──────────────────────────────────────────────────────────────

    async def save_baseline(self, user_id: str, baseline_dict: dict):
        await self._conn.execute(
            """INSERT OR REPLACE INTO user_baselines (user_id, created_at, baseline_json)
               VALUES (?,?,?)""",
            (user_id, time.time(), json.dumps(baseline_dict)),
        )
        await self._conn.commit()

    async def load_baseline(self, user_id: str) -> Optional[dict]:
        async with self._conn.execute(
            """SELECT baseline_json FROM user_baselines
               WHERE user_id=? ORDER BY created_at DESC LIMIT 1""",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        return json.loads(row["baseline_json"]) if row else None

    # ── Analytics (v1) ────────────────────────────────────────────────────────

    async def get_session_summary(self, session_id: Optional[int] = None) -> dict:
        sid = session_id or self._session_id
        if not sid:
            return {}
        async with self._conn.execute(
            "SELECT COUNT(*) as n FROM switch_events WHERE session_id=?", (sid,)
        ) as cur:
            sw = await cur.fetchone()
        async with self._conn.execute(
            "SELECT AVG(score) as avg, MAX(score) as peak FROM procrastination_events WHERE session_id=?",
            (sid,),
        ) as cur:
            proc = await cur.fetchone()
        async with self._conn.execute(
            "SELECT AVG(focus) as avg_focus FROM cognitive_snapshots WHERE session_id=?", (sid,)
        ) as cur:
            cog = await cur.fetchone()
        return {
            "session_id":     sid,
            "n_switches":     sw["n"]                      if sw   else 0,
            "avg_proc_risk":  round((proc["avg"]  or 0) * 100, 1) if proc else 0,
            "peak_proc_risk": round((proc["peak"] or 0) * 100, 1) if proc else 0,
            "avg_focus":      round((cog["avg_focus"] or 0.5) * 100, 1) if cog else 50,
        }

    async def get_recent_sessions(self, limit: int = 10) -> List[dict]:
        async with self._conn.execute(
            """SELECT id, started_at, duration_min, stats_json
               FROM sessions ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for r in rows:
            item = dict(r)
            if item.get("stats_json"):
                item["stats"] = json.loads(item["stats_json"])
                del item["stats_json"]
            result.append(item)
        return result

    # ── Analytics (v2 — for React dashboard) ─────────────────────────────────

    async def get_cognitive_history(
        self, session_id: Optional[int] = None, limit: int = 200
    ) -> List[dict]:
        """Time-series of cognitive snapshots for Recharts line charts."""
        sid = session_id or self._session_id
        if not sid:
            return []
        async with self._conn.execute(
            """SELECT timestamp, state, focus, load, fatigue, confusion
               FROM cognitive_snapshots WHERE session_id=?
               ORDER BY timestamp DESC LIMIT ?""",
            (sid, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "timestamp": r["timestamp"],
                "state":     r["state"],
                "focus":     round((r["focus"]    or 0) * 100, 1),
                "load":      round((r["load"]     or 0) * 100, 1),
                "fatigue":   round((r["fatigue"]  or 0) * 100, 1),
                "confusion": round((r["confusion"]or 0) * 100, 1),
            }
            for r in reversed(rows)
        ]

    async def get_switch_history(
        self, session_id: Optional[int] = None, limit: int = 50
    ) -> List[dict]:
        """List of switch events for the timeline panel."""
        sid = session_id or self._session_id
        if not sid:
            return []
        async with self._conn.execute(
            """SELECT switch_id, started_at, switch_duration, recovery_duration,
                      total_cost, productivity_drop, cognitive_state
               FROM switch_events WHERE session_id=?
               ORDER BY started_at DESC LIMIT ?""",
            (sid, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_full_dashboard_data(self) -> dict:
        """Single call that returns everything the React dashboard needs."""
        summary    = await self.get_session_summary()
        cog_hist   = await self.get_cognitive_history(limit=100)
        sw_hist    = await self.get_switch_history(limit=20)
        sessions   = await self.get_recent_sessions(limit=5)
        return {
            "summary":       summary,
            "cognitive_history": cog_hist,
            "switch_history": sw_hist,
            "recent_sessions": sessions,
        }
