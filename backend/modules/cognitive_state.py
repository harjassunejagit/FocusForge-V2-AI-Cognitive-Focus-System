"""
cognitive_state.py
Module 2: Cognitive State Modeling
Estimates Focus / Confusion / Cognitive Load / Fatigue from processed signals.
Uses a weighted evidence accumulation approach with temporal smoothing.
"""

import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List
from .signal_processor import ProcessedSignals

logger = logging.getLogger("cognitive_state")


class CognitiveState(str, Enum):
    FOCUSED      = "focused"
    CONFUSED     = "confused"
    HIGH_LOAD    = "high_load"
    FATIGUED     = "fatigued"
    DISTRACTED   = "distracted"
    UNKNOWN      = "unknown"


@dataclass
class CognitiveSnapshot:
    """Instantaneous cognitive state assessment."""
    state: CognitiveState     = CognitiveState.UNKNOWN
    focus_score: float        = 0.5    # 0=none, 1=deep focus
    confusion_score: float    = 0.0
    cognitive_load: float     = 0.3    # 0=low, 1=overloaded
    fatigue_score: float      = 0.0
    distraction_score: float  = 0.0
    confidence: float         = 0.0
    label: str                = "Analyzing..."
    timestamp: float          = 0.0


class CognitiveStateModel:
    """
    Continuously estimates cognitive state.

    Evidence sources:
      - FOCUS:   stable gaze + stable posture + normal blink + straight posture
      - CONFUSION: gaze scatter + brow furrow + head tilt + forward lean
      - HIGH LOAD: low blink + forward lean + reduced movement
      - FATIGUE:   high blink + head droop + slouch + slow movement
      - DISTRACTED: high gaze deviation + high head yaw + face away
    """

    ALPHA = 0.15    # EMA smoothing factor for scores

    def __init__(self, config: dict):
        self.config = config
        # Smoothed scores
        self._focus      = 0.5
        self._confusion  = 0.2
        self._load       = 0.3
        self._fatigue    = 0.1
        self._distracted = 0.2

        self._history: List[CognitiveSnapshot] = []
        self._max_history = 300

        # Threshold from config
        t = config.get("thresholds", {})
        self._blink_overload = t.get("blink_rate_overload", 8.0)
        self._blink_fatigue  = t.get("blink_rate_fatigue", 22.0)
        self._yaw_thresh     = t.get("yaw_switch_threshold", 25.0)
        self._gaze_thresh    = t.get("gaze_drift_threshold", 0.3)

    def update(self, sig: ProcessedSignals) -> CognitiveSnapshot:
        if not sig.face_visible:
            snap = CognitiveSnapshot(
                state=CognitiveState.UNKNOWN,
                label="Face not detected",
                timestamp=sig.timestamp
            )
            return snap

        # ── Raw evidence signals ─────────────────────────────────────────────

        # Gaze instability: 0=stable, 1=scattered
        gaze_scatter = min(sig.gaze_instability * 3.0, 1.0)
        gaze_away    = min((abs(sig.gaze_x_dev) + abs(sig.gaze_y_dev)) / 4.0, 1.0)
        head_away    = min(abs(sig.head_yaw_dev) / 2.5, 1.0)   # z-scores

        # Blink evidence
        blink_rate  = sig.blink_rate
        low_blink   = max(0.0, 1.0 - blink_rate / self._blink_overload) if blink_rate < self._blink_overload else 0.0
        high_blink  = max(0.0, (blink_rate - self._blink_fatigue) / 10.0) if blink_rate > self._blink_fatigue else 0.0

        # Posture evidence
        slouch      = min(sig.head_droop * 2.0, 1.0)
        forward     = min(sig.forward_lean, 1.0)
        instability = 1.0 - sig.body_stability
        shoulder_asym = min(sig.shoulder_slope / 15.0, 1.0)

        # Hand / face touch
        fidget = 1.0 if sig.face_touch else min(sig.hand_speed * 2.0, 0.6)

        # ── Score computation (weighted evidence) ────────────────────────────

        # FOCUS: all signals calm
        raw_focus = (
            (1.0 - gaze_scatter)    * 0.30 +
            (1.0 - gaze_away)       * 0.20 +
            (1.0 - head_away)       * 0.20 +
            sig.body_stability      * 0.15 +
            (1.0 - slouch)          * 0.10 +
            (1.0 - fidget)          * 0.05
        )

        # CONFUSION: gaze scatter + brow furrow + head tilt
        raw_confusion = (
            gaze_scatter            * 0.35 +
            sig.brow_furrow         * 0.30 +
            min(abs(sig.head_roll) / 20.0, 1.0) * 0.15 +
            forward                 * 0.20
        )

        # HIGH LOAD: low blink + forward lean + reduced instability
        raw_load = (
            low_blink               * 0.40 +
            forward                 * 0.30 +
            (1.0 - instability)     * 0.15 +   # very still = focused strain
            sig.brow_furrow         * 0.15
        )

        # FATIGUE: high blink + droop + slouch
        raw_fatigue = (
            high_blink              * 0.35 +
            slouch                  * 0.30 +
            instability             * 0.20 +
            shoulder_asym           * 0.15
        )

        # DISTRACTED: head away + gaze away
        raw_distracted = (
            head_away               * 0.50 +
            gaze_away               * 0.35 +
            fidget                  * 0.15
        )

        # ── EMA smoothing ────────────────────────────────────────────────────
        a = self.ALPHA
        self._focus      = a * raw_focus      + (1 - a) * self._focus
        self._confusion  = a * raw_confusion  + (1 - a) * self._confusion
        self._load       = a * raw_load       + (1 - a) * self._load
        self._fatigue    = a * raw_fatigue    + (1 - a) * self._fatigue
        self._distracted = a * raw_distracted + (1 - a) * self._distracted

        # ── Dominant state selection ─────────────────────────────────────────
        scores = {
            CognitiveState.FOCUSED:    self._focus,
            CognitiveState.CONFUSED:   self._confusion,
            CognitiveState.HIGH_LOAD:  self._load,
            CognitiveState.FATIGUED:   self._fatigue,
            CognitiveState.DISTRACTED: self._distracted,
        }
        dominant = max(scores, key=scores.get)
        confidence = scores[dominant]

        label = self._make_label(dominant, scores)

        snap = CognitiveSnapshot(
            state           = dominant,
            focus_score     = round(self._focus, 3),
            confusion_score = round(self._confusion, 3),
            cognitive_load  = round(self._load, 3),
            fatigue_score   = round(self._fatigue, 3),
            distraction_score = round(self._distracted, 3),
            confidence      = round(confidence, 3),
            label           = label,
            timestamp       = sig.timestamp,
        )

        self._history.append(snap)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        return snap

    def _make_label(self, state: CognitiveState, scores: dict) -> str:
        labels = {
            CognitiveState.FOCUSED:    "Deep Focus 🟢",
            CognitiveState.CONFUSED:   "Confusion Detected 🟡",
            CognitiveState.HIGH_LOAD:  "High Cognitive Load 🔴",
            CognitiveState.FATIGUED:   "Fatigue Rising 😴",
            CognitiveState.DISTRACTED: "Distracted ⚡",
        }
        base = labels.get(state, "Analyzing...")
        load_hint = ""
        if scores[CognitiveState.HIGH_LOAD] > 0.6:
            load_hint = " • Load critical"
        elif scores[CognitiveState.FATIGUE] > 0.5:
            load_hint = " • Take a break"
        return base + load_hint

    def get_recent_history(self, n: int = 60) -> List[CognitiveSnapshot]:
        return self._history[-n:]

    @property
    def current_load(self) -> float:
        return self._load

    @property
    def current_focus(self) -> float:
        return self._focus