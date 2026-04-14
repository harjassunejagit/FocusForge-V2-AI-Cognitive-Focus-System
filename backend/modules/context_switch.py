"""
context_switch.py
Module 1: Context Switch Intelligence
Detects context switches using FSM with pre-switch signal detection,
dwell time validation, and switch cost estimation.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from .signal_processor import ProcessedSignals
from .cognitive_state import CognitiveSnapshot

logger = logging.getLogger("context_switch")


class SwitchPhase(str, Enum):
    FOCUSED     = "focused"
    PRE_SWITCH  = "pre_switch"     # early disengagement signals
    DISENGAGING = "disengaging"    # confirmed looking away
    SWITCHED    = "switched"       # away from task
    RETURNING   = "returning"      # gaze returning
    RECOVERING  = "recovering"     # back but rebuilding focus


@dataclass
class SwitchEvent:
    """A single detected context switch event."""
    id: int
    phase: SwitchPhase
    pre_switch_detected_at: float   = 0.0
    switch_started_at: float        = 0.0
    switch_ended_at: Optional[float]= None
    recovery_completed_at: Optional[float] = None

    switch_duration: float          = 0.0   # seconds away
    recovery_duration: float        = 0.0   # seconds to regain focus
    total_cost_seconds: float       = 0.0   # switch + recovery
    productivity_drop_pct: float    = 0.0   # estimated %

    trigger_signals: dict           = field(default_factory=dict)
    cognitive_state_at_switch: str  = "unknown"


@dataclass
class SwitchDetectorOutput:
    """Output from the switch detector each frame."""
    phase: SwitchPhase              = SwitchPhase.FOCUSED
    switch_predicted: bool          = False
    prediction_confidence: float    = 0.0
    switch_predicted_in_sec: float  = 0.0

    current_event: Optional[SwitchEvent] = None
    last_completed_event: Optional[SwitchEvent] = None
    total_switches_session: int     = 0
    switch_rate_per_hour: float     = 0.0
    label: str                      = "On Task"


class ContextSwitchDetector:
    """
    FSM-based context switch detector.

    States: FOCUSED → PRE_SWITCH → DISENGAGING → SWITCHED → RETURNING → RECOVERING → FOCUSED

    Pre-switch signals (detected before switch):
    - Head beginning to turn (yaw deviation increasing)
    - Gaze drifting from screen center
    - Slight posture shift

    Switch detection requires dwell time (not a single frame) to avoid false positives.
    """

    def __init__(self, config: dict):
        self.config = config
        t = config.get("thresholds", {})
        self._yaw_thresh   = t.get("yaw_switch_threshold", 25.0)
        self._gaze_thresh  = t.get("gaze_drift_threshold", 0.3)
        self._dwell_sec    = t.get("switch_dwell_seconds", 1.5)
        self._rengagement  = t.get("re_engagement_stability", 3.0)

        # FSM state
        self._phase         = SwitchPhase.FOCUSED
        self._phase_enter   = time.time()
        self._session_start = time.time()

        # Events
        self._event_counter  = 0
        self._current_event: Optional[SwitchEvent] = None
        self._completed_events: List[SwitchEvent] = []

        # Pre-switch tracking
        self._yaw_velocity  = 0.0
        self._prev_yaw      = 0.0
        self._prev_time     = time.time()

        # Re-engagement stability buffer
        self._stable_frames = 0
        self._required_stable_frames = int(self._rengagement * 30)  # @30fps

    def update(
        self,
        sig: ProcessedSignals,
        cog: CognitiveSnapshot
    ) -> SwitchDetectorOutput:
        now  = time.time()
        dt   = max(now - self._prev_time, 0.01)

        # Compute yaw velocity (rate of head turning)
        self._yaw_velocity = (sig.head_yaw_dev - self._prev_yaw) / dt
        self._prev_yaw  = sig.head_yaw_dev
        self._prev_time = now

        # Is user looking away?
        looking_away = (
            abs(sig.head_yaw_dev) > self._yaw_thresh / 5.0 or   # z-score based
            (abs(sig.gaze_x_dev) + abs(sig.gaze_y_dev)) > 3.0
        )

        # Is user looking at screen?
        on_screen = (
            abs(sig.head_yaw_dev) < 1.5 and
            (abs(sig.gaze_x_dev) + abs(sig.gaze_y_dev)) < 2.0 and
            sig.body_stability > 0.5
        )

        # Pre-switch: yaw moving outward but not yet away
        pre_switch_signal = (
            abs(self._yaw_velocity) > 0.5 and
            abs(sig.head_yaw_dev) > 1.0 and
            not looking_away
        )

        # ── FSM Transitions ──────────────────────────────────────────────────
        prev_phase = self._phase

        if self._phase == SwitchPhase.FOCUSED:
            if pre_switch_signal:
                self._transition(SwitchPhase.PRE_SWITCH)
            elif looking_away:
                self._transition(SwitchPhase.DISENGAGING)

        elif self._phase == SwitchPhase.PRE_SWITCH:
            if looking_away:
                self._transition(SwitchPhase.DISENGAGING)
            elif on_screen and self._phase_duration > 1.0:
                self._transition(SwitchPhase.FOCUSED)   # false alarm

        elif self._phase == SwitchPhase.DISENGAGING:
            if self._phase_duration >= self._dwell_sec:
                # Confirmed switch
                self._start_switch(sig, cog)
                self._transition(SwitchPhase.SWITCHED)
            elif on_screen:
                self._transition(SwitchPhase.FOCUSED)   # returned quickly

        elif self._phase == SwitchPhase.SWITCHED:
            if on_screen:
                self._transition(SwitchPhase.RETURNING)

        elif self._phase == SwitchPhase.RETURNING:
            if on_screen:
                self._stable_frames += 1
                if self._stable_frames >= self._required_stable_frames:
                    self._end_switch()
                    self._transition(SwitchPhase.RECOVERING)
                    self._stable_frames = 0
            else:
                self._stable_frames = max(0, self._stable_frames - 2)
                if not on_screen and self._phase_duration > 2.0:
                    self._transition(SwitchPhase.SWITCHED)

        elif self._phase == SwitchPhase.RECOVERING:
            if cog.focus_score > 0.55 and self._phase_duration > 3.0:
                self._complete_recovery()
                self._transition(SwitchPhase.FOCUSED)
            elif looking_away:
                self._transition(SwitchPhase.SWITCHED)

        # ── Predict upcoming switch ───────────────────────────────────────────
        predict = self._phase in (SwitchPhase.PRE_SWITCH, SwitchPhase.DISENGAGING)
        pred_conf = min(abs(self._yaw_velocity) / 2.0, 0.95) if predict else 0.0
        pred_in   = max(0.0, self._dwell_sec - self._phase_duration) if predict else 0.0

        # Session switch rate
        elapsed_hours = (now - self._session_start) / 3600.0
        rate = len(self._completed_events) / max(elapsed_hours, 0.001)

        return SwitchDetectorOutput(
            phase                  = self._phase,
            switch_predicted       = predict,
            prediction_confidence  = round(pred_conf, 3),
            switch_predicted_in_sec= round(pred_in, 2),
            current_event          = self._current_event,
            last_completed_event   = self._completed_events[-1] if self._completed_events else None,
            total_switches_session = len(self._completed_events),
            switch_rate_per_hour   = round(rate, 1),
            label                  = self._make_label(),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _transition(self, new_phase: SwitchPhase):
        logger.debug(f"Switch FSM: {self._phase} → {new_phase}")
        self._phase       = new_phase
        self._phase_enter = time.time()

    @property
    def _phase_duration(self) -> float:
        return time.time() - self._phase_enter

    def _start_switch(self, sig: ProcessedSignals, cog: CognitiveSnapshot):
        self._event_counter += 1
        self._current_event = SwitchEvent(
            id                       = self._event_counter,
            phase                    = SwitchPhase.SWITCHED,
            pre_switch_detected_at   = self._phase_enter,
            switch_started_at        = time.time(),
            trigger_signals          = {
                "head_yaw_dev":   sig.head_yaw_dev,
                "gaze_x_dev":     sig.gaze_x_dev,
                "yaw_velocity":   self._yaw_velocity,
            },
            cognitive_state_at_switch= cog.state.value,
        )
        logger.info(f"Switch #{self._event_counter} started (state={cog.state.value})")

    def _end_switch(self):
        if not self._current_event:
            return
        ev = self._current_event
        now = time.time()
        ev.switch_ended_at  = now
        ev.switch_duration  = now - ev.switch_started_at
        logger.info(f"Switch #{ev.id} returned after {ev.switch_duration:.1f}s")

    def _complete_recovery(self):
        if not self._current_event:
            return
        ev = self._current_event
        now = time.time()
        ev.recovery_completed_at = now
        ev.recovery_duration     = now - (ev.switch_ended_at or now)
        ev.total_cost_seconds    = ev.switch_duration + ev.recovery_duration
        ev.productivity_drop_pct = self._estimate_productivity_drop(ev)
        self._completed_events.append(ev)
        self._current_event = None
        logger.info(
            f"Switch #{ev.id} fully recovered. "
            f"Cost={ev.total_cost_seconds:.1f}s "
            f"Drop={ev.productivity_drop_pct:.0f}%"
        )

    def _estimate_productivity_drop(self, ev: SwitchEvent) -> float:
        """
        Heuristic: brief switches cause disproportionate recovery cost.
        Based on Gloria Mark's research: avg 23 min to full recovery.
        We scale this logarithmically.
        """
        import math
        base = min(ev.total_cost_seconds / 60.0, 1.0)
        drop = 15.0 + base * 30.0 + math.log1p(ev.recovery_duration) * 5.0
        return round(min(drop, 70.0), 1)

    def _make_label(self) -> str:
        labels = {
            SwitchPhase.FOCUSED:     "On Task ✅",
            SwitchPhase.PRE_SWITCH:  "⚠️ Attention drifting...",
            SwitchPhase.DISENGAGING: "🔄 Switching...",
            SwitchPhase.SWITCHED:    "📴 Task Switched",
            SwitchPhase.RETURNING:   "↩️ Returning...",
            SwitchPhase.RECOVERING:  "🔁 Rebuilding Focus",
        }
        return labels.get(self._phase, "...")

    def get_completed_events(self) -> List[SwitchEvent]:
        return list(self._completed_events)

    @property
    def current_phase(self) -> SwitchPhase:
        return self._phase