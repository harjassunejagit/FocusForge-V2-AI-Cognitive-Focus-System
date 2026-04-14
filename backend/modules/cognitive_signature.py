"""
cognitive_signature.py
Module 4: Personal Cognitive Signature
Learns individual patterns: switch style, recovery speed, procrastination triggers.
Uses rolling 7-day window with exponential decay for older data.
"""

import time
import math
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from .context_switch import SwitchEvent
from .procrastination import ProcrastinationOutput

logger = logging.getLogger("cognitive_signature")


@dataclass
class CognitiveSignature:
    """Personalized behavioral profile."""
    user_id: str = "default"

    # Switch patterns
    avg_switch_duration: float     = 0.0   # seconds typically away
    avg_recovery_duration: float   = 0.0   # seconds to re-engage
    switch_frequency_per_hr: float = 0.0
    switches_total: int            = 0
    fast_switcher: bool            = False  # switches fast, recovers slow
    rare_heavy_switcher: bool      = False  # rare but high cost

    # Procrastination patterns
    peak_procrastination_hour: int   = -1     # hour of day (0–23)
    primary_trigger: str             = "unknown"
    avg_risk_score: float            = 0.0
    high_risk_pct: float             = 0.0    # % of time at high risk

    # Recovery
    recovery_improving: bool         = False
    recovery_trend_pct: float        = 0.0    # + = improving

    # Trend (vs last week)
    procrastination_trend_pct: float = 0.0    # - = improving

    # Insights
    insights: List[str]              = field(default_factory=list)
    last_updated: float              = 0.0
    sessions_recorded: int           = 0


class CognitiveSignatureModel:
    """
    Builds and updates a personal cognitive signature from session data.
    Implements 7-day rolling window with exponential decay.
    """

    DECAY_LAMBDA = 0.1    # decay per day (older = less weight)

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._switch_events:    List[dict] = []
        self._risk_samples:     List[dict] = []
        self._session_summaries: List[dict] = []
        self._signature = CognitiveSignature(user_id=user_id)

    def record_switch(self, event: SwitchEvent):
        self._switch_events.append({
            "t":                event.switch_started_at,
            "switch_duration":  event.switch_duration,
            "recovery_duration":event.recovery_duration,
            "total_cost":       event.total_cost_seconds,
        })

    def record_risk(self, score: float):
        self._risk_samples.append({"t": time.time(), "score": score})

    def record_session(self, summary: dict):
        self._session_summaries.append({"t": time.time(), **summary})
        self._prune_old_data()
        self._rebuild_signature()

    def get_signature(self) -> CognitiveSignature:
        return self._signature

    # ── Internal ──────────────────────────────────────────────────────────────

    def _prune_old_data(self, window_days: int = 7):
        cutoff = time.time() - window_days * 86400
        self._switch_events    = [e for e in self._switch_events    if e["t"] > cutoff]
        self._risk_samples     = [e for e in self._risk_samples     if e["t"] > cutoff]
        self._session_summaries= [e for e in self._session_summaries if e["t"] > cutoff]

    def _decay_weight(self, timestamp: float) -> float:
        age_days = (time.time() - timestamp) / 86400.0
        return math.exp(-self.DECAY_LAMBDA * age_days)

    def _rebuild_signature(self):
        sig = CognitiveSignature(user_id=self.user_id)
        sig.sessions_recorded = len(self._session_summaries)
        sig.last_updated      = time.time()

        if self._switch_events:
            weights = [self._decay_weight(e["t"]) for e in self._switch_events]
            w_total = sum(weights) + 1e-9

            sig.avg_switch_duration   = sum(
                e["switch_duration"] * w for e, w in zip(self._switch_events, weights)
            ) / w_total
            sig.avg_recovery_duration = sum(
                e["recovery_duration"] * w for e, w in zip(self._switch_events, weights)
            ) / w_total
            sig.switches_total        = len(self._switch_events)

            # Classify switch style
            sig.fast_switcher       = sig.avg_switch_duration < 10 and sig.avg_recovery_duration > 30
            sig.rare_heavy_switcher = sig.switches_total < 5 and sig.avg_recovery_duration > 60

        if self._risk_samples:
            weights = [self._decay_weight(s["t"]) for s in self._risk_samples]
            w_total = sum(weights) + 1e-9
            sig.avg_risk_score = sum(
                s["score"] * w for s, w in zip(self._risk_samples, weights)
            ) / w_total
            sig.high_risk_pct = sum(
                1 for s in self._risk_samples if s["score"] > 0.65
            ) / max(len(self._risk_samples), 1) * 100

        # Trigger analysis from session summaries
        trigger_counts: Dict[str, float] = defaultdict(float)
        for s in self._session_summaries:
            tb = s.get("trigger_breakdown", {})
            for trig, cnt in tb.items():
                w = self._decay_weight(s["t"])
                trigger_counts[trig] += cnt * w
        if trigger_counts:
            sig.primary_trigger = max(trigger_counts, key=trigger_counts.get)

        # Recovery trend (compare last 3 sessions to previous 3)
        if len(self._session_summaries) >= 6:
            recent = self._session_summaries[-3:]
            earlier = self._session_summaries[-6:-3]
            recent_recov  = sum(e.get("avg_recovery_sec", 30) for e in recent) / 3
            earlier_recov = sum(e.get("avg_recovery_sec", 30) for e in earlier) / 3
            if earlier_recov > 0:
                sig.recovery_trend_pct   = (earlier_recov - recent_recov) / earlier_recov * 100
                sig.recovery_improving   = sig.recovery_trend_pct > 0

        # Procrastination trend
        if len(self._session_summaries) >= 4:
            recent_risk  = sum(s.get("avg_procrastination", 50) for s in self._session_summaries[-2:]) / 2
            earlier_risk = sum(s.get("avg_procrastination", 50) for s in self._session_summaries[-4:-2]) / 2
            if earlier_risk > 0:
                sig.procrastination_trend_pct = (earlier_risk - recent_risk) / earlier_risk * 100

        sig.insights = self._generate_insights(sig)
        self._signature = sig
        logger.info(f"Signature rebuilt for {self.user_id}: {len(sig.insights)} insights")

    def _generate_insights(self, sig: CognitiveSignature) -> List[str]:
        insights = []

        if sig.fast_switcher:
            insights.append("⚡ You switch contexts quickly but take longer to recover.")
        if sig.rare_heavy_switcher:
            insights.append("🏋️  Your switches are rare but very costly — worth protecting flow.")
        if sig.avg_recovery_duration > 45:
            insights.append(f"⏱️  Average recovery time: {sig.avg_recovery_duration:.0f}s. Working on reducing it.")
        if sig.recovery_improving and abs(sig.recovery_trend_pct) > 5:
            insights.append(f"📈 Recovery improving by {sig.recovery_trend_pct:.0f}% vs last sessions!")
        if sig.procrastination_trend_pct > 10:
            insights.append(f"✅ Procrastination down {sig.procrastination_trend_pct:.0f}% vs previous sessions.")
        elif sig.procrastination_trend_pct < -10:
            insights.append(f"⚠️  Procrastination trending up. Consider reviewing work environment.")
        if sig.high_risk_pct > 30:
            insights.append(f"🔴 You're in high-risk state {sig.high_risk_pct:.0f}% of the time.")
        if sig.primary_trigger not in ("unknown", "none", ""):
            insights.append(f"🧠 Primary procrastination trigger: {sig.primary_trigger.replace('_', ' ').title()}")

        return insights