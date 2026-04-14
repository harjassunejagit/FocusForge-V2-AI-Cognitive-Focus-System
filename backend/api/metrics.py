"""
backend/api/metrics.py
═══════════════════════════════════════════════════════════════
FocusForge v2 — Evaluation Metrics Dashboard

Computes research-grade session analytics and maintains the
prediction timeline used by the React dashboard.

Metrics computed
────────────────
  avg_switch_cost       seconds of productivity lost per switch (switch + recovery)
  procrastination_rate  fraction of time spent in high-risk state (0–1)
  avg_recovery_time     average seconds to return to focus post-switch
  deep_work_duration    longest single uninterrupted focus block (seconds)
  total_deep_work       cumulative focused seconds in session
  focus_percentage      % of session time classified as "focus"
  switch_count          total confirmed context switches
  focus_periods         number of distinct focus blocks entered

Prediction timeline
───────────────────
  Each state transition is recorded as a TimelineEvent with:
    timestamp, state (focus/drift/switch/recover), duration, score, label
  The React dashboard renders this as the visual timeline strip.
"""

import time
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import List, Optional, Dict

logger = logging.getLogger("metrics")


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class TimelineEvent:
    """A single state block in the session timeline."""
    timestamp:  float
    state:      str       # focus | drift | switch | recover
    duration:   float = 0.0
    score:      float = 0.0
    label:      str   = ""


@dataclass
class SessionMetrics:
    avg_switch_cost:      float = 0.0
    procrastination_rate: float = 0.0   # fraction 0-1
    avg_recovery_time:    float = 0.0
    deep_work_duration:   float = 0.0   # longest block seconds
    total_deep_work:      float = 0.0
    switch_count:         int   = 0
    focus_periods:        int   = 0
    session_duration_min: float = 0.0
    focus_percentage:     float = 0.0   # 0-100
    timeline:             List[TimelineEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        base = {k: v for k, v in self.__dict__.items() if k != "timeline"}
        tl = self.timeline if isinstance(self.timeline, list) else []
        base["timeline"] = [
            {
                "timestamp": round(e.timestamp, 2),
                "state":     e.state,
                "duration":  round(e.duration, 1),
                "score":     round(e.score, 3),
                "label":     e.label,
            }
            for e in tl[-300:]    # cap for API response size
        ]
        return base


# ── Dashboard class ───────────────────────────────────────────────────────────

class MetricsDashboard:
    """
    Call update() every frame from the main pipeline.
    Call get_metrics() to get the full SessionMetrics object.
    Call get_graph_data() to get Recharts-ready time-series data.
    """

    DEEP_WORK_FOCUS_THRESHOLD = 0.65
    HIGH_PROC_THRESHOLD       = 0.55

    def __init__(self):
        self._session_start   = time.time()

        # Timeline
        self._timeline: List[TimelineEvent] = []
        self._current_state   = "unknown"
        self._block_start     = time.time()

        # Accumulators
        self._switch_costs:   deque = deque(maxlen=200)
        self._recovery_times: deque = deque(maxlen=200)
        self._proc_flags:     deque = deque(maxlen=1200)   # ~20 min at 1fps

        # Focus tracking
        self._current_focus_run = 0.0
        self._longest_focus_run = 0.0
        self._total_focus_sec   = 0.0
        self._n_switches        = 0
        self._focus_periods     = 0

        # For graph data
        self._graph_buffer: deque = deque(maxlen=120)   # last 2 min

    def update(
        self,
        cognitive_state: str,
        focus_score:     float,
        proc_score:      float,
        switch_phase:    str,
        switch_cost_sec: Optional[float] = None,
        recovery_sec:    Optional[float] = None,
    ):
        now = time.time()

        # Map to 4-way timeline state
        if switch_phase in ("switching", "pre_switch", "disengaging"):
            tl_state = "switch"
        elif switch_phase == "recovering":
            tl_state = "recover"
        elif focus_score >= self.DEEP_WORK_FOCUS_THRESHOLD:
            tl_state = "focus"
        else:
            tl_state = "drift"

        # State transition — close old block, open new one
        if tl_state != self._current_state:
            duration = now - self._block_start

            if self._current_state == "focus":
                self._current_focus_run += duration
                self._total_focus_sec   += duration
                self._longest_focus_run  = max(self._longest_focus_run, self._current_focus_run)
                self._focus_periods     += 1
            else:
                self._current_focus_run = 0.0

            if self._current_state == "switch":
                self._n_switches += 1

            if self._current_state and self._current_state != "unknown":
                self._timeline.append(TimelineEvent(
                    timestamp = round(self._block_start, 2),
                    state     = self._current_state,
                    duration  = round(duration, 2),
                    score     = round(focus_score, 3),
                    label     = self._make_label(self._current_state, focus_score, proc_score),
                ))
                if len(self._timeline) > 3000:
                    self._timeline.pop(0)

            self._current_state = tl_state
            self._block_start   = now

        # Accumulate costs
        if switch_cost_sec and switch_cost_sec > 0:
            self._switch_costs.append(switch_cost_sec)
        if recovery_sec and recovery_sec > 0:
            self._recovery_times.append(recovery_sec)

        # Procrastination flag (1 = high risk)
        self._proc_flags.append(1.0 if proc_score > self.HIGH_PROC_THRESHOLD else 0.0)

        # Graph buffer (one point per call)
        self._graph_buffer.append({
            "t":     round(now - self._session_start, 1),
            "focus": round(focus_score * 100, 1),
            "proc":  round(proc_score * 100, 1),
            "state": tl_state,
        })

    def _make_label(self, state: str, focus: float, proc: float) -> str:
        if state == "focus":
            return f"Deep Work ({focus * 100:.0f}%)"
        if state == "switch":
            return "Context Switch"
        if state == "recover":
            return "Recovery"
        return f"Drifting (risk {proc * 100:.0f}%)"

    # ── Public getters ────────────────────────────────────────────────────────

    def get_metrics(self) -> SessionMetrics:
        now         = time.time()
        session_sec = now - self._session_start

        avg_cost     = (sum(self._switch_costs)   / max(len(self._switch_costs),   1)) if self._switch_costs   else 0.0
        avg_recovery = (sum(self._recovery_times) / max(len(self._recovery_times), 1)) if self._recovery_times else 0.0
        proc_rate    = (sum(self._proc_flags)     / max(len(self._proc_flags),     1)) if self._proc_flags     else 0.0
        focus_pct    = (self._total_focus_sec / max(session_sec, 1)) * 100

        return SessionMetrics(
            avg_switch_cost      = round(avg_cost, 1),
            procrastination_rate = round(proc_rate, 3),
            avg_recovery_time    = round(avg_recovery, 1),
            deep_work_duration   = round(self._longest_focus_run, 1),
            total_deep_work      = round(self._total_focus_sec, 1),
            switch_count         = self._n_switches,
            focus_periods        = self._focus_periods,
            session_duration_min = round(session_sec / 60.0, 1),
            focus_percentage     = round(focus_pct, 1),
            timeline             = list(self._timeline),
        )

    def get_timeline_for_api(self, last_n: int = 100) -> List[dict]:
        events = self._timeline[-last_n:]
        return [
            {
                "timestamp": e.timestamp,
                "state":     e.state,
                "duration":  e.duration,
                "score":     e.score,
                "label":     e.label,
            }
            for e in events
        ]

    def get_graph_data(self, points: int = 60) -> dict:
        """Recharts / Chart.js ready time-series payload."""
        buf = list(self._graph_buffer)[-points:]
        return {
            "labels":        [str(p["t"]) + "s" for p in buf],
            "focus":         [p["focus"]  for p in buf],
            "procrastination":[p["proc"]  for p in buf],
            "states":        [p["state"]  for p in buf],
        }

    def get_summary_cards(self) -> List[dict]:
        """Flat card data for the React analytics panel."""
        m = self.get_metrics()
        return [
            {
                "title":    "Avg Switch Cost",
                "value":    f"{m.avg_switch_cost:.0f}s",
                "subtitle": "productivity lost per switch",
                "color":    "#f97316",
                "icon":     "zap",
            },
            {
                "title":    "Procrastination Rate",
                "value":    f"{m.procrastination_rate * 100:.0f}%",
                "subtitle": "time at high risk",
                "color":    "#ef4444",
                "icon":     "alert-triangle",
            },
            {
                "title":    "Avg Recovery Time",
                "value":    f"{m.avg_recovery_time:.0f}s",
                "subtitle": "to regain focus after switch",
                "color":    "#eab308",
                "icon":     "refresh-cw",
            },
            {
                "title":    "Longest Focus Block",
                "value":    f"{m.deep_work_duration:.0f}s",
                "subtitle": "uninterrupted deep work",
                "color":    "#22c55e",
                "icon":     "target",
            },
            {
                "title":    "Focus Percentage",
                "value":    f"{m.focus_percentage:.0f}%",
                "subtitle": "of session in focus state",
                "color":    "#60a5fa",
                "icon":     "brain",
            },
            {
                "title":    "Context Switches",
                "value":    str(m.switch_count),
                "subtitle": "confirmed switches this session",
                "color":    "#a855f7",
                "icon":     "git-branch",
            },
        ]
