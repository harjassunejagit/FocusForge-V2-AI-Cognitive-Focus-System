"""
recovery_optimizer.py
Module 7: Predictive Recovery Optimizer
Goes beyond detecting recovery — actively optimizes it with micro-action suggestions.
Learns which recovery actions work best for this user.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from .context_switch import SwitchDetectorOutput, SwitchPhase
from .cognitive_state import CognitiveSnapshot, CognitiveState

logger = logging.getLogger("recovery_optimizer")


@dataclass
class RecoveryAction:
    """A micro-action suggested to accelerate re-engagement."""
    id: str
    instruction: str
    duration_sec: float    # how long to do it
    action_type: str       # "visual" | "cognitive" | "physical" | "breathing"
    evidence_score: float  # 0–1 how well this worked historically


@dataclass
class RecoveryPlan:
    """Personalized recovery plan for this specific return."""
    switch_duration: float
    state_at_return: str
    actions: List[RecoveryAction]
    predicted_recovery_sec: float
    label: str
    timestamp: float


# ── Action Library ────────────────────────────────────────────────────────────

RECOVERY_ACTIONS: Dict[str, RecoveryAction] = {
    "look_at_last_line": RecoveryAction(
        id            = "look_at_last_line",
        instruction   = "👁️  Look at the last line/element you worked on.",
        duration_sec  = 3,
        action_type   = "visual",
        evidence_score= 0.85,
    ),
    "reread_3_lines": RecoveryAction(
        id            = "reread_3_lines",
        instruction   = "📖 Re-read the last 3 lines of code/text from top.",
        duration_sec  = 10,
        action_type   = "cognitive",
        evidence_score= 0.80,
    ),
    "whisper_task": RecoveryAction(
        id            = "whisper_task",
        instruction   = "🗣️  Whisper: 'I was doing ___' to restore context.",
        duration_sec  = 5,
        action_type   = "cognitive",
        evidence_score= 0.78,
    ),
    "deep_breath": RecoveryAction(
        id            = "deep_breath",
        instruction   = "🫁 Take one slow breath in (4s) → out (6s).",
        duration_sec  = 10,
        action_type   = "breathing",
        evidence_score= 0.72,
    ),
    "close_tabs": RecoveryAction(
        id            = "close_tabs",
        instruction   = "🗂️  Close any new tabs you opened during the distraction.",
        duration_sec  = 5,
        action_type   = "cognitive",
        evidence_score= 0.75,
    ),
    "write_where_left_off": RecoveryAction(
        id            = "write_where_left_off",
        instruction   = "✍️  Write: 'I was at [exact step]' before moving.",
        duration_sec  = 15,
        action_type   = "cognitive",
        evidence_score= 0.88,
    ),
    "posture_reset": RecoveryAction(
        id            = "posture_reset",
        instruction   = "🪑 Sit up straight, plant both feet on the floor.",
        duration_sec  = 5,
        action_type   = "physical",
        evidence_score= 0.65,
    ),
    "micro_break": RecoveryAction(
        id            = "micro_break",
        instruction   = "⏸️  Stand up for 30 seconds, then return fresh.",
        duration_sec  = 30,
        action_type   = "physical",
        evidence_score= 0.70,
    ),
}


class RecoveryOptimizer:
    """
    Predicts recovery needs and prescribes an optimized micro-action plan.
    Learns which actions reduce recovery time for this specific user.
    """

    def __init__(self):
        # Track action effectiveness per user
        self._action_scores: Dict[str, float] = {
            k: v.evidence_score for k, v in RECOVERY_ACTIONS.items()
        }
        self._recovery_observations: List[dict] = []
        self._active_plan: Optional[RecoveryPlan] = None
        self._plan_start: Optional[float]         = None
        self._was_switched = False

    def update(
        self,
        sw:  SwitchDetectorOutput,
        cog: CognitiveSnapshot,
    ) -> Optional[RecoveryPlan]:
        """Call each frame; returns a recovery plan on switch return."""

        # Detect moment of return
        just_returned = (
            self._was_switched and
            sw.phase in (SwitchPhase.RETURNING, SwitchPhase.RECOVERING)
        )
        self._was_switched = sw.phase == SwitchPhase.SWITCHED

        if just_returned and not self._active_plan:
            ev = sw.last_completed_event
            switch_dur = ev.switch_duration if ev else 5.0

            plan = self._build_plan(switch_dur, cog)
            self._active_plan  = plan
            self._plan_start   = time.time()
            logger.info(
                f"Recovery plan built: {len(plan.actions)} actions, "
                f"~{plan.predicted_recovery_sec:.0f}s predicted"
            )
            return plan

        # Clear plan once focus restored
        if (self._active_plan and
            sw.phase == SwitchPhase.FOCUSED and
            cog.focus_score > 0.55
        ):
            if self._plan_start:
                actual_recovery = time.time() - self._plan_start
                self._learn_from_recovery(self._active_plan, actual_recovery)
            self._active_plan = None
            self._plan_start  = None

        return self._active_plan

    def _build_plan(
        self,
        switch_duration: float,
        cog: CognitiveSnapshot,
    ) -> RecoveryPlan:
        """Select 2–4 high-efficacy actions tailored to the current state."""
        selected_ids: List[str] = []

        # Always start with visual re-anchoring
        selected_ids.append("look_at_last_line")

        # Long switch → need context recall
        if switch_duration > 30:
            selected_ids.append("write_where_left_off")
        else:
            selected_ids.append("reread_3_lines")

        # Fatigue state → breathing + posture
        if cog.state == CognitiveState.FATIGUED:
            selected_ids.append("deep_breath")
            selected_ids.append("posture_reset")
        # High load → close distractions
        elif cog.state == CognitiveState.HIGH_LOAD:
            selected_ids.append("close_tabs")
        # Distracted → verbal re-anchoring
        elif cog.state == CognitiveState.DISTRACTED:
            selected_ids.append("whisper_task")

        # Sort by learned user-specific score
        selected_ids = sorted(
            list(dict.fromkeys(selected_ids)),  # deduplicate preserving order
            key=lambda aid: self._action_scores.get(aid, 0.5),
            reverse=True
        )[:4]  # max 4 actions

        actions = [RECOVERY_ACTIONS[aid] for aid in selected_ids if aid in RECOVERY_ACTIONS]

        # Estimate recovery time
        base_recovery = max(switch_duration * 0.8, 15.0)
        action_benefit = sum(a.evidence_score * 5 for a in actions)
        predicted = max(base_recovery - action_benefit, 10.0)

        return RecoveryPlan(
            switch_duration      = switch_duration,
            state_at_return      = cog.state.value,
            actions              = actions,
            predicted_recovery_sec = round(predicted, 1),
            label                = f"🔁 Recovery Plan ({len(actions)} steps, ~{predicted:.0f}s)",
            timestamp            = time.time(),
        )

    def _learn_from_recovery(self, plan: RecoveryPlan, actual_recovery: float):
        """Update action scores based on actual recovery speed."""
        predicted = plan.predicted_recovery_sec
        if predicted <= 0:
            return

        ratio = predicted / max(actual_recovery, 1.0)
        # If actual < predicted → actions were effective → boost scores
        # If actual > predicted → less effective → reduce scores
        delta = (ratio - 1.0) * 0.05   # small update

        for action in plan.actions:
            old = self._action_scores.get(action.id, 0.7)
            self._action_scores[action.id] = max(0.1, min(0.99, old + delta))

        self._recovery_observations.append({
            "timestamp":       time.time(),
            "predicted_sec":   predicted,
            "actual_sec":      actual_recovery,
            "actions":         [a.id for a in plan.actions],
        })
        logger.info(
            f"Recovery learning: pred={predicted:.0f}s actual={actual_recovery:.0f}s "
            f"delta={delta:+.3f}"
        )

    def get_stats(self) -> dict:
        if not self._recovery_observations:
            return {"message": "No recovery data yet"}
        preds   = [o["predicted_sec"] for o in self._recovery_observations]
        actuals = [o["actual_sec"]    for o in self._recovery_observations]
        return {
            "n_recoveries":        len(self._recovery_observations),
            "avg_predicted_sec":   round(sum(preds) / len(preds), 1),
            "avg_actual_sec":      round(sum(actuals) / len(actuals), 1),
            "top_actions":         sorted(
                self._action_scores.items(), key=lambda x: x[1], reverse=True
            )[:3],
        }