"""
temporal_impact.py
Module 5: Temporal Impact & Ripple Effect Tracker
Measures what happens AFTER a context switch — focus instability, error likelihood.

meta_cognition.py
Module 6: Meta-Cognition Module
Makes users aware of their behavioral patterns ("you quit after 15s of struggle").
"""

import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .context_switch import SwitchDetectorOutput, SwitchPhase, SwitchEvent
from .cognitive_state import CognitiveSnapshot

logger = logging.getLogger("temporal_impact")


# ═══════════════════════════════════════════════════════════════
# MODULE 5: Temporal Impact Tracker
# ═══════════════════════════════════════════════════════════════

@dataclass
class RippleEffect:
    """Quantifies the downstream impact of a completed switch."""
    switch_id: int
    focus_drop_pct: float       = 0.0   # % focus below baseline
    error_likelihood: float     = 0.0   # 0–1 probability
    time_to_regain_flow: float  = 0.0   # seconds
    productivity_loss_min: float= 0.0   # estimated lost minutes
    observation_window_sec: float = 0.0
    label: str = ""


class TemporalImpactTracker:
    """
    Observes the N minutes after a switch and quantifies ripple effects.
    Uses a sliding window of cognitive snapshots.
    """

    OBSERVATION_WINDOW = 6 * 60    # 6 minutes post-switch
    SAMPLE_INTERVAL    = 1.0       # seconds between samples

    def __init__(self):
        self._tracking_switch: Optional[int]  = None
        self._track_start:     Optional[float]= None
        self._pre_switch_focus: float         = 0.7
        self._post_switch_samples: deque      = deque(maxlen=400)
        self._completed_ripples: List[RippleEffect] = []
        self._last_sample_time: float         = 0.0
        self._current_ripple: Optional[RippleEffect] = None

    def update(
        self,
        sw:  SwitchDetectorOutput,
        cog: CognitiveSnapshot,
    ) -> Optional[RippleEffect]:
        now = time.time()

        # Start tracking when a switch completes (user returns)
        if (sw.last_completed_event and
            sw.last_completed_event.id != self._tracking_switch and
            sw.phase == SwitchPhase.RECOVERING
        ):
            ev = sw.last_completed_event
            self._tracking_switch = ev.id
            self._track_start     = now
            self._post_switch_samples.clear()
            self._pre_switch_focus = max(cog.focus_score, 0.3)
            self._current_ripple   = RippleEffect(switch_id=ev.id)
            logger.info(f"Tracking ripple for switch #{ev.id}")

        # Sample focus during observation window
        if (self._tracking_switch is not None and
            self._track_start is not None and
            now - self._last_sample_time >= self.SAMPLE_INTERVAL
        ):
            elapsed = now - self._track_start
            self._post_switch_samples.append({
                "t":     now,
                "focus": cog.focus_score,
                "load":  cog.cognitive_load,
                "elapsed": elapsed,
            })
            self._last_sample_time = now

            # Check if window complete
            if elapsed >= self.OBSERVATION_WINDOW:
                ripple = self._compute_ripple()
                self._completed_ripples.append(ripple)
                self._tracking_switch = None
                self._current_ripple  = None
                logger.info(
                    f"Ripple complete: drop={ripple.focus_drop_pct:.0f}% "
                    f"loss={ripple.productivity_loss_min:.1f}min"
                )
                return ripple

        # Return in-progress estimate
        if self._current_ripple and len(self._post_switch_samples) > 5:
            return self._compute_partial_ripple()

        return None

    def _compute_ripple(self) -> RippleEffect:
        samples = list(self._post_switch_samples)
        if not samples:
            return RippleEffect(switch_id=self._tracking_switch or 0)

        focus_vals = [s["focus"] for s in samples]
        avg_focus  = sum(focus_vals) / len(focus_vals)
        min_focus  = min(focus_vals)
        focus_drop = max(0, (self._pre_switch_focus - avg_focus) / max(self._pre_switch_focus, 0.1)) * 100

        # Time to regain 90% of baseline focus
        threshold = self._pre_switch_focus * 0.9
        regain_time = self.OBSERVATION_WINDOW
        for s in samples:
            if s["focus"] >= threshold:
                regain_time = s["elapsed"]
                break

        # Error likelihood: higher when focus is low + load is high
        high_risk_pct = sum(1 for s in samples if s["focus"] < 0.4) / len(samples)
        error_likelihood = min(high_risk_pct * 1.5, 0.95)

        # Productivity loss estimate
        loss_min = (focus_drop / 100.0) * 8.0 + regain_time / 60.0 * 1.2

        ripple = RippleEffect(
            switch_id             = self._tracking_switch or 0,
            focus_drop_pct        = round(focus_drop, 1),
            error_likelihood      = round(error_likelihood, 2),
            time_to_regain_flow   = round(regain_time, 1),
            productivity_loss_min = round(loss_min, 1),
            observation_window_sec= len(samples) * self.SAMPLE_INTERVAL,
        )
        ripple.label = self._make_label(ripple)
        return ripple

    def _compute_partial_ripple(self) -> RippleEffect:
        """In-progress estimate during observation window."""
        samples = list(self._post_switch_samples)
        focus_vals = [s["focus"] for s in samples]
        avg_focus  = sum(focus_vals) / len(focus_vals)
        drop_pct   = max(0, (self._pre_switch_focus - avg_focus) / max(self._pre_switch_focus, 0.1)) * 100

        r = RippleEffect(
            switch_id      = self._tracking_switch or 0,
            focus_drop_pct = round(drop_pct, 1),
            observation_window_sec = len(samples) * self.SAMPLE_INTERVAL,
        )
        r.label = f"📊 Switch caused ~{drop_pct:.0f}% focus drop (tracking...)"
        return r

    def _make_label(self, r: RippleEffect) -> str:
        if r.focus_drop_pct > 30:
            return (f"⚠️ This switch caused {r.focus_drop_pct:.0f}% focus drop "
                    f"over next {r.observation_window_sec/60:.0f} min")
        return (f"ℹ️  Switch ripple: {r.focus_drop_pct:.0f}% drop, "
                f"recovered in {r.time_to_regain_flow:.0f}s")

    def get_completed_ripples(self) -> List[RippleEffect]:
        return list(self._completed_ripples)


# ═══════════════════════════════════════════════════════════════
# MODULE 6: Meta-Cognition Module
# ═══════════════════════════════════════════════════════════════

@dataclass
class MetaCognitionInsight:
    """A self-awareness insight delivered to the user."""
    message: str
    category: str     # "pattern" | "timing" | "trigger" | "improvement"
    data: dict
    timestamp: float


class MetaCognitionModule:
    """
    Analyzes behavioral data and generates self-awareness insights.
    "You tend to quit after 15s of struggle."
    "You lose focus after switching tabs twice."
    """

    def __init__(self):
        self._struggle_start:   Optional[float] = None
        self._struggle_durations: List[float]   = []
        self._switch_streak:    int             = 0
        self._tab_switch_count: int             = 0
        self._insights: List[MetaCognitionInsight] = []
        self._last_insight_time: float          = 0.0
        self._insight_cooldown  = 300.0         # 5 min between insights

    def update(
        self,
        sw:  SwitchDetectorOutput,
        cog: CognitiveSnapshot,
        score_history: List[float],
    ) -> Optional[MetaCognitionInsight]:
        now = time.time()

        # Track struggle duration (high load before switch)
        if cog.cognitive_load > 0.65 and sw.phase.value in ("focused", "pre_switch"):
            if self._struggle_start is None:
                self._struggle_start = now
        else:
            if self._struggle_start is not None:
                struggle_dur = now - self._struggle_start
                self._struggle_durations.append(struggle_dur)
                self._struggle_start = None

        # Track consecutive switches
        if sw.phase == SwitchPhase.SWITCHED:
            self._switch_streak += 1
        elif sw.phase == SwitchPhase.FOCUSED:
            self._switch_streak = 0

        # Generate insights if enough data
        if now - self._last_insight_time < self._insight_cooldown:
            return None

        insight = self._analyze(now, score_history)
        if insight:
            self._insights.append(insight)
            self._last_insight_time = now
        return insight

    def _analyze(self, now: float, score_history: List[float]) -> Optional[MetaCognitionInsight]:
        # Pattern: quitting after N seconds of struggle
        if len(self._struggle_durations) >= 3:
            avg_struggle = sum(self._struggle_durations[-5:]) / len(self._struggle_durations[-5:])
            if avg_struggle < 20:
                return MetaCognitionInsight(
                    message  = f"💡 You tend to switch away after ~{avg_struggle:.0f}s of difficulty. "
                               f"Try setting a 60s 'push through' timer.",
                    category = "pattern",
                    data     = {"avg_struggle_sec": avg_struggle},
                    timestamp= now,
                )

        # Pattern: cascading switches
        if self._switch_streak >= 3:
            return MetaCognitionInsight(
                message  = "🔄 You've switched context 3 times in a row — you may be in a spiral. "
                           "Close distracting tabs and start fresh.",
                category = "trigger",
                data     = {"switch_streak": self._switch_streak},
                timestamp= now,
            )

        # Pattern: high-risk score persistence
        if len(score_history) >= 20:
            recent_avg = sum(score_history[-20:]) / 20
            if recent_avg > 0.6:
                return MetaCognitionInsight(
                    message  = f"⚡ Your procrastination risk has averaged {recent_avg*100:.0f}% "
                               f"over the last session. Consider a different task or environment.",
                    category = "timing",
                    data     = {"avg_risk": recent_avg},
                    timestamp= now,
                )

        return None

    def get_insights(self, n: int = 10) -> List[MetaCognitionInsight]:
        return self._insights[-n:]