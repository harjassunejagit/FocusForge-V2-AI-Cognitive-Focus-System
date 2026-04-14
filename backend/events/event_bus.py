"""
backend/events/event_bus.py
═══════════════════════════════════════════════════════════════
FocusForge v2 — Centralised Async Event Bus

Decouples all pipeline modules via typed publish-subscribe events.

Events emitted
──────────────
  SWITCH_DETECTED        — context switch confirmed by FSM
  HIGH_PROCRASTINATION   — risk score exceeded threshold
  RECOVERY_COMPLETE      — user returned to focused state after switch
  FOCUS_LOST             — focus score fell below threshold
  CALIBRATION_DONE       — baseline calibration finished
  MODEL_PREDICTION       — LSTM made a new prediction
  INTERVENTION_TRIGGERED — system delivered an intervention message
  DEEP_WORK_ENTERED      — sustained focus block started
  FATIGUE_DETECTED       — fatigue score exceeded threshold
  SESSION_STARTED        — session opened
  SESSION_ENDED          — session closed

Architecture benefit
────────────────────
  Without event bus: Module A calls Module B directly (tight coupling).
  With event bus: Module A publishes an event; any subscriber handles it.
  This makes the system scalable (add subscribers without touching publishers).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger("event_bus")


class EventType(str, Enum):
    SWITCH_DETECTED        = "SWITCH_DETECTED"
    HIGH_PROCRASTINATION   = "HIGH_PROCRASTINATION"
    RECOVERY_COMPLETE      = "RECOVERY_COMPLETE"
    FOCUS_LOST             = "FOCUS_LOST"
    CALIBRATION_DONE       = "CALIBRATION_DONE"
    MODEL_PREDICTION       = "MODEL_PREDICTION"
    INTERVENTION_TRIGGERED = "INTERVENTION_TRIGGERED"
    DEEP_WORK_ENTERED      = "DEEP_WORK_ENTERED"
    FATIGUE_DETECTED       = "FATIGUE_DETECTED"
    SESSION_STARTED        = "SESSION_STARTED"
    SESSION_ENDED          = "SESSION_ENDED"


@dataclass
class Event:
    type:      EventType
    data:      Dict[str, Any] = field(default_factory=dict)
    timestamp: float          = field(default_factory=time.time)
    severity:  str            = "info"    # info | warning | critical

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp


Handler = Callable[[Event], Any]


class EventBus:
    """
    Lightweight async pub/sub event bus.

    Usage
    ─────
        bus = EventBus()

        async def on_switch(event: Event):
            print(f"Switch! data={event.data}")

        bus.subscribe(EventType.SWITCH_DETECTED, on_switch)
        await bus.publish(Event(EventType.SWITCH_DETECTED, data={"cost": 12.3}))
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[Handler]] = {}
        self._history:  List[Event] = []
        self._max_history = 500
        self._n_published = 0

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, event_type: EventType, handler: Handler):
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug(f"Subscribed '{getattr(handler, '__name__', handler)}' to {event_type}")

    def unsubscribe(self, event_type: EventType, handler: Handler):
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h is not handler
            ]

    # ── Publishing ────────────────────────────────────────────────────────────

    async def publish(self, event: Event):
        # Store in history ring-buffer
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self._n_published += 1

        # Dispatch to all subscribers
        for handler in self._handlers.get(event.type, []):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Handler failed for {event.type}: {e}")

    async def publish_many(self, events: List[Event]):
        for ev in events:
            await self.publish(ev)

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_recent_events(
        self,
        n: int = 50,
        event_type: Optional[EventType] = None,
    ) -> List[Event]:
        events = self._history[-n:]
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events

    def get_stats(self) -> dict:
        return {
            "total_published":   self._n_published,
            "history_size":      len(self._history),
            "subscriber_counts": {
                k.value: len(v) for k, v in self._handlers.items()
            },
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


# ── Convenience emitters (used by main.py) ────────────────────────────────────

async def emit_switch(bus: EventBus, switch_data: dict):
    await bus.publish(Event(
        type     = EventType.SWITCH_DETECTED,
        data     = switch_data,
        severity = "warning",
    ))


async def emit_high_procrastination(bus: EventBus, score: float, risk_level: str):
    await bus.publish(Event(
        type     = EventType.HIGH_PROCRASTINATION,
        data     = {"score": score, "risk_level": risk_level},
        severity = "critical" if score > 0.8 else "warning",
    ))


async def emit_recovery(bus: EventBus, recovery_sec: float):
    await bus.publish(Event(
        type     = EventType.RECOVERY_COMPLETE,
        data     = {"recovery_duration_sec": recovery_sec},
        severity = "info",
    ))


async def emit_model_prediction(bus: EventBus, prediction):
    await bus.publish(Event(
        type     = EventType.MODEL_PREDICTION,
        data     = {
            "switch_probability":  prediction.switch_probability,
            "procrastination":     prediction.procrastination_score,
            "cognitive_state":     prediction.cognitive_state,
            "switch_confidence":   prediction.switch_confidence,
            "state_confidence":    prediction.state_confidence,
            "label":               prediction.label,
        },
        severity = "info",
    ))


async def emit_focus_lost(bus: EventBus, focus_score: float):
    await bus.publish(Event(
        type     = EventType.FOCUS_LOST,
        data     = {"focus_score": focus_score},
        severity = "warning",
    ))
