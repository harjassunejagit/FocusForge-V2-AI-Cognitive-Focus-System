"""
procrastination.py
Module 3: Procrastination Analysis System — All 5 Layers

Layer 1: Trigger Detection (WHY it happens)
Layer 2: Real-time Probability Engine (HOW LIKELY)
Layer 3: Long-Term Behavior Learning (IMPROVEMENT over time)
Layer 4: Smart Anti-Procrastination Intervention
Layer 5: Recovery Coaching System
"""

import time
import logging
import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict
from .signal_processor import ProcessedSignals
from .cognitive_state import CognitiveSnapshot, CognitiveState
from .context_switch import SwitchDetectorOutput, SwitchPhase

logger = logging.getLogger("procrastination")


# ─── Enums & Structs ─────────────────────────────────────────────────────────

class ProcrastinationTrigger(str, Enum):
    FRUSTRATION   = "frustration"   # stuck, tight face, repeated movement
    BOREDOM       = "boredom"       # low load, high drift
    OVERWHELM     = "overwhelm"     # high load → avoidance
    FATIGUE       = "fatigue"       # tiredness-driven avoidance
    ANXIETY       = "anxiety"       # rapid gaze, fidgeting
    UNKNOWN       = "unknown"


class RiskLevel(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


@dataclass
class ProcrastinationTriggerEvent:
    trigger: ProcrastinationTrigger
    confidence: float
    timestamp: float
    signals: dict


@dataclass
class ProcrastinationScore:
    """Layer 2: Real-time probability score."""
    score: float           = 0.0    # 0–1
    risk_level: RiskLevel  = RiskLevel.LOW
    rising: bool           = False
    delta: float           = 0.0    # score change from last update
    label: str             = "Low Risk"
    components: dict       = field(default_factory=dict)


@dataclass
class InterventionMessage:
    """Layer 4: Intervention to deliver."""
    message: str
    type: str          # "warning" | "delay" | "coaching"
    urgency: float
    timestamp: float


@dataclass
class RecoveryCoachMessage:
    """Layer 5: Recovery guidance."""
    message: str
    action_type: str   # "re-orient" | "micro-break" | "context-recall"
    timestamp: float


@dataclass
class ProcrastinationOutput:
    trigger: Optional[ProcrastinationTriggerEvent]
    score: ProcrastinationScore
    intervention: Optional[InterventionMessage]
    recovery: Optional[RecoveryCoachMessage]
    session_stats: dict


# ─── Layer 1: Trigger Detection ──────────────────────────────────────────────

class TriggerDetector:
    """Detects micro-signals that precede procrastination."""

    def __init__(self):
        self._hesitation_buffer: deque = deque(maxlen=60)  # ~2 sec of frames
        self._fidget_streak     = 0
        self._frustration_streak = 0

    def detect(
        self,
        sig: ProcessedSignals,
        cog: CognitiveSnapshot
    ) -> Optional[ProcrastinationTriggerEvent]:
        now = time.time()

        # Frustration indicators
        micro_frustration = (
            sig.brow_furrow > 0.55 and
            sig.hand_speed > 0.3 and
            sig.gaze_instability > 0.25
        )

        # Fidgeting: repeated face touches or hand movement
        if sig.face_touch or sig.hand_speed > 0.4:
            self._fidget_streak += 1
        else:
            self._fidget_streak = max(0, self._fidget_streak - 1)

        # Hesitation: gaze oscillating (can't decide where to look)
        self._hesitation_buffer.append(sig.gaze_instability)
        avg_hesitation = sum(self._hesitation_buffer) / max(len(self._hesitation_buffer), 1)

        if micro_frustration:
            self._frustration_streak += 1
        else:
            self._frustration_streak = max(0, self._frustration_streak - 1)

        # ── Classify trigger ─────────────────────────────────────────────────

        if self._frustration_streak > 15 and cog.cognitive_load > 0.6:
            return ProcrastinationTriggerEvent(
                trigger    = ProcrastinationTrigger.FRUSTRATION,
                confidence = min(self._frustration_streak / 30.0, 0.95),
                timestamp  = now,
                signals    = {"brow_furrow": sig.brow_furrow, "load": cog.cognitive_load}
            )

        if cog.state == CognitiveState.HIGH_LOAD and avg_hesitation > 0.3:
            return ProcrastinationTriggerEvent(
                trigger    = ProcrastinationTrigger.OVERWHELM,
                confidence = min(cog.cognitive_load * avg_hesitation * 3.0, 0.9),
                timestamp  = now,
                signals    = {"load": cog.cognitive_load, "hesitation": avg_hesitation}
            )

        if cog.state == CognitiveState.FATIGUED and self._fidget_streak > 20:
            return ProcrastinationTriggerEvent(
                trigger    = ProcrastinationTrigger.FATIGUE,
                confidence = min(cog.fatigue_score, 0.9),
                timestamp  = now,
                signals    = {"fatigue": cog.fatigue_score, "fidget": self._fidget_streak}
            )

        if cog.focus_score < 0.3 and cog.cognitive_load < 0.25 and avg_hesitation > 0.2:
            return ProcrastinationTriggerEvent(
                trigger    = ProcrastinationTrigger.BOREDOM,
                confidence = 0.6,
                timestamp  = now,
                signals    = {"focus": cog.focus_score, "load": cog.cognitive_load}
            )

        return None


# ─── Layer 2: Procrastination Probability Engine ─────────────────────────────

class ProcrastinationEngine:
    """
    Core innovation: real-time risk score.

    P_score = f(hesitation + gaze_drift + fidgeting + switch_intent + cognitive_load)
    """

    WEIGHTS = {
        "hesitation":    0.20,
        "gaze_drift":    0.20,
        "fidgeting":     0.15,
        "switch_intent": 0.25,
        "cognitive_load":0.20,
    }
    ALPHA = 0.12   # EMA factor (lower = smoother but slower)

    def __init__(self, config: dict):
        t = config.get("thresholds", {})
        self._thresh_medium   = t.get("risk_medium",   0.45)
        self._thresh_high     = t.get("risk_high",     0.70)
        self._thresh_critical = t.get("risk_critical", 0.85)

        self._score      = 0.0
        self._prev_score = 0.0
        self._history: deque = deque(maxlen=300)

    def compute(
        self,
        sig: ProcessedSignals,
        cog: CognitiveSnapshot,
        sw:  SwitchDetectorOutput,
    ) -> ProcrastinationScore:

        # ── Component signals ─────────────────────────────────────────────────
        hesitation    = min(sig.gaze_instability * 2.5, 1.0)
        gaze_drift    = min((abs(sig.gaze_x_dev) + abs(sig.gaze_y_dev)) / 5.0, 1.0)
        fidgeting     = min(
            (0.6 if sig.face_touch else 0.0) + sig.hand_speed * 0.8, 1.0
        )
        switch_intent = (
            0.9 if sw.phase == SwitchPhase.DISENGAGING else
            0.6 if sw.phase == SwitchPhase.PRE_SWITCH  else
            0.3 if sw.switch_predicted                 else
            0.0
        )
        cognitive_load = cog.cognitive_load    # already 0–1

        W = self.WEIGHTS
        raw = (
            W["hesitation"]    * hesitation    +
            W["gaze_drift"]    * gaze_drift     +
            W["fidgeting"]     * fidgeting      +
            W["switch_intent"] * switch_intent  +
            W["cognitive_load"]* cognitive_load
        )

        # EMA smoothing
        self._prev_score = self._score
        self._score = self.ALPHA * raw + (1 - self.ALPHA) * self._score

        # Risk level
        s = self._score
        if   s >= self._thresh_critical: level = RiskLevel.CRITICAL
        elif s >= self._thresh_high:     level = RiskLevel.HIGH
        elif s >= self._thresh_medium:   level = RiskLevel.MEDIUM
        else:                            level = RiskLevel.LOW

        delta   = self._score - self._prev_score
        rising  = delta > 0.005
        label   = self._make_label(level, rising, s)

        ps = ProcrastinationScore(
            score      = round(self._score, 3),
            risk_level = level,
            rising     = rising,
            delta      = round(delta, 4),
            label      = label,
            components = {
                "hesitation":    round(hesitation,    3),
                "gaze_drift":    round(gaze_drift,    3),
                "fidgeting":     round(fidgeting,     3),
                "switch_intent": round(switch_intent, 3),
                "cognitive_load":round(cognitive_load,3),
            }
        )
        self._history.append({"t": time.time(), "score": self._score, "level": level.value})
        return ps

    def _make_label(self, level: RiskLevel, rising: bool, score: float) -> str:
        pct    = int(score * 100)
        arrow  = "↑ rising rapidly" if rising else ""
        labels = {
            RiskLevel.LOW:      f"✅ Low Risk  ({pct}%) {arrow}",
            RiskLevel.MEDIUM:   f"🟡 Medium Risk ({pct}%) {arrow}",
            RiskLevel.HIGH:     f"🔴 High Risk ({pct}%) {arrow}",
            RiskLevel.CRITICAL: f"🚨 Critical Risk ({pct}%) {arrow}",
        }
        return labels[level]

    @property
    def current_score(self) -> float:
        return self._score

    def get_history(self, n: int = 60) -> list:
        return list(self._history)[-n:]


# ─── Layer 4: Smart Intervention Engine ──────────────────────────────────────

class InterventionEngine:
    """
    Adaptive interventions — only triggers when BOTH risk is high
    AND cognitive state is weak. Respects cooldown to prevent fatigue.
    """

    def __init__(self, config: dict):
        t = config.get("intervention", {})
        self._cooldown   = t.get("cooldown_seconds", 120)
        self._min_risk   = t.get("min_risk_to_trigger", 0.65)
        self._last_fired: float = 0.0

    def evaluate(
        self,
        score:   ProcrastinationScore,
        cog:     CognitiveSnapshot,
        sw:      SwitchDetectorOutput,
        trigger: Optional[ProcrastinationTriggerEvent],
    ) -> Optional[InterventionMessage]:
        now = time.time()

        # Cooldown check
        if now - self._last_fired < self._cooldown:
            return None

        # Threshold check
        if score.score < self._min_risk:
            return None

        # Generate context-aware message
        msg = self._select_message(score, cog, sw, trigger)
        if msg:
            self._last_fired = now
            logger.info(f"Intervention fired: {msg.message}")
        return msg

    def _select_message(
        self,
        score:   ProcrastinationScore,
        cog:     CognitiveSnapshot,
        sw:      SwitchDetectorOutput,
        trigger: Optional[ProcrastinationTriggerEvent],
    ) -> Optional[InterventionMessage]:
        now = time.time()

        if sw.phase == SwitchPhase.PRE_SWITCH:
            return InterventionMessage(
                message    = "⏸️  Take 5 seconds before switching — finish this thought first.",
                type       = "delay",
                urgency    = score.score,
                timestamp  = now,
            )

        if trigger and trigger.trigger.value == "frustration":
            return InterventionMessage(
                message    = "💡 Stuck? Try explaining the problem out loud — rubber duck it.",
                type       = "coaching",
                urgency    = score.score,
                timestamp  = now,
            )

        if trigger and trigger.trigger.value == "overwhelm":
            return InterventionMessage(
                message    = "🧩 This feels big. Break it into the next single action only.",
                type       = "coaching",
                urgency    = score.score,
                timestamp  = now,
            )

        if cog.state == CognitiveState.FATIGUED:
            return InterventionMessage(
                message    = "😴 Your focus is dropping. A 5-min break will pay back 20 mins.",
                type       = "warning",
                urgency    = score.score,
                timestamp  = now,
            )

        if score.risk_level == RiskLevel.CRITICAL:
            return InterventionMessage(
                message    = f"🔴 Procrastination risk: {int(score.score*100)}% — What's the next tiny step?",
                type       = "warning",
                urgency    = score.score,
                timestamp  = now,
            )
        return None


# ─── Layer 5: Recovery Coach ─────────────────────────────────────────────────

class RecoveryCoach:
    """
    Helps user re-engage after a context switch.
    Detects return hesitation and loss of context.
    """

    def __init__(self):
        self._recovery_start: Optional[float] = None
        self._was_switched = False

    def update(
        self,
        sw:  SwitchDetectorOutput,
        cog: CognitiveSnapshot,
    ) -> Optional[RecoveryCoachMessage]:
        now  = time.time()
        phase = sw.phase

        # Detect return from switch
        if self._was_switched and phase == SwitchPhase.RECOVERING:
            if self._recovery_start is None:
                self._recovery_start = now

        if phase == SwitchPhase.SWITCHED:
            self._was_switched = True
        elif phase == SwitchPhase.FOCUSED:
            self._was_switched    = False
            self._recovery_start  = None

        if phase != SwitchPhase.RECOVERING or self._recovery_start is None:
            return None

        elapsed = now - self._recovery_start

        # Progressive coaching messages at different recovery stages
        if elapsed < 5.0 and cog.focus_score < 0.4:
            return RecoveryCoachMessage(
                message    = "↩️  Back! Look at the last line you were working on.",
                action_type= "re-orient",
                timestamp  = now,
            )
        elif 5.0 <= elapsed < 15.0 and cog.focus_score < 0.45:
            return RecoveryCoachMessage(
                message    = "🔁 Re-read your last 3 lines. You had momentum — recapture it.",
                action_type= "context-recall",
                timestamp  = now,
            )
        elif elapsed > 20.0 and cog.focus_score < 0.4:
            return RecoveryCoachMessage(
                message    = f"⏱️  {elapsed:.0f}s re-focusing. Try: write down where you left off.",
                action_type= "micro-break",
                timestamp  = now,
            )
        return None


# ─── Layer 3: Long-Term Behavior Learning ────────────────────────────────────

class BehaviorLearner:
    """
    Tracks procrastination patterns over time.
    Identifies: when it happens, how often, under what conditions.
    """

    def __init__(self):
        self._session_scores: List[float] = []
        self._session_events: List[dict]  = []
        self._session_start = time.time()
        self._peak_score    = 0.0

    def record(self, score: ProcrastinationScore, trigger: Optional[ProcrastinationTriggerEvent]):
        self._session_scores.append(score.score)
        if score.score > self._peak_score:
            self._peak_score = score.score
        if trigger:
            self._session_events.append({
                "trigger":   trigger.trigger.value,
                "score":     score.score,
                "timestamp": trigger.timestamp,
            })

    def get_session_stats(self) -> dict:
        if not self._session_scores:
            return {"message": "Not enough data yet"}

        elapsed_min = (time.time() - self._session_start) / 60.0
        avg_score   = sum(self._session_scores) / len(self._session_scores)
        high_risk_time = sum(
            1 for s in self._session_scores if s > 0.65
        ) / max(len(self._session_scores), 1) * 100

        trigger_counts: Dict[str, int] = {}
        for ev in self._session_events:
            t = ev["trigger"]
            trigger_counts[t] = trigger_counts.get(t, 0) + 1

        top_trigger = max(trigger_counts, key=trigger_counts.get) if trigger_counts else "none"

        return {
            "session_duration_min":  round(elapsed_min, 1),
            "avg_procrastination":   round(avg_score * 100, 1),
            "peak_risk_pct":         round(self._peak_score * 100, 1),
            "high_risk_time_pct":    round(high_risk_time, 1),
            "top_trigger":           top_trigger,
            "trigger_breakdown":     trigger_counts,
            "total_events":          len(self._session_events),
        }


# ─── Master Module ────────────────────────────────────────────────────────────

class ProcrastinationAnalyzer:
    """Combines all 5 layers into one update() call."""

    def __init__(self, config: dict):
        self.trigger_detector = TriggerDetector()
        self.engine           = ProcrastinationEngine(config)
        self.intervention     = InterventionEngine(config)
        self.recovery         = RecoveryCoach()
        self.learner          = BehaviorLearner()

    def update(
        self,
        sig: ProcessedSignals,
        cog: CognitiveSnapshot,
        sw:  SwitchDetectorOutput,
    ) -> ProcrastinationOutput:
        # Layer 1
        trigger = self.trigger_detector.detect(sig, cog)

        # Layer 2
        score = self.engine.compute(sig, cog, sw)

        # Layer 3
        self.learner.record(score, trigger)

        # Layer 4
        intervention = self.intervention.evaluate(score, cog, sw, trigger)

        # Layer 5
        recovery_msg = self.recovery.update(sw, cog)

        return ProcrastinationOutput(
            trigger       = trigger,
            score         = score,
            intervention  = intervention,
            recovery      = recovery_msg,
            session_stats = self.learner.get_session_stats(),
        )