"""
signal_processor.py
Kalman filtering + exponential moving average smoothing for raw signals.
Also handles baseline calibration per user.
"""

import numpy as np
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional
from ..camera.mediapipe_analyzer import RawSignals

logger = logging.getLogger("signal_processor")


# ─── 1D Kalman Filter ────────────────────────────────────────────────────────

class KalmanFilter1D:
    """Simple 1D Kalman filter for scalar signal smoothing."""

    def __init__(self, process_noise: float = 0.01, measurement_noise: float = 0.1):
        self.Q = process_noise       # Process noise variance
        self.R = measurement_noise   # Measurement noise variance
        self.x = 0.0                 # State estimate
        self.P = 1.0                 # Estimation uncertainty
        self._initialized = False

    def update(self, measurement: float) -> float:
        if not self._initialized:
            self.x = measurement
            self._initialized = True
            return self.x

        # Predict
        P_pred = self.P + self.Q

        # Update
        K = P_pred / (P_pred + self.R)       # Kalman gain
        self.x = self.x + K * (measurement - self.x)
        self.P = (1.0 - K) * P_pred

        return self.x


# ─── Baseline Calibration ────────────────────────────────────────────────────

@dataclass
class UserBaseline:
    """Personal neutral-state baseline established during calibration."""
    head_yaw_mean: float   = 0.0
    head_yaw_std: float    = 5.0
    head_pitch_mean: float = 0.0
    head_pitch_std: float  = 5.0
    gaze_x_mean: float     = 0.0
    gaze_x_std: float      = 0.1
    gaze_y_mean: float     = 0.0
    gaze_y_std: float      = 0.1
    ear_mean: float        = 0.28
    blink_rate_mean: float = 15.0
    forward_lean_mean: float = 0.3
    body_stability_mean: float = 0.85
    calibrated: bool       = False
    calibrated_at: float   = 0.0
    n_samples: int         = 0


class CalibrationBuffer:
    """Accumulates N frames to establish baseline."""

    def __init__(self, required_frames: int = 200):
        self.required = required_frames
        self.buffers: Dict[str, list] = {
            "head_yaw":   [], "head_pitch":    [],
            "gaze_x":     [], "gaze_y":        [],
            "ear":        [], "forward_lean":   [],
            "body_stability": [],
        }
        self._done = False

    def add(self, signals: RawSignals):
        if self._done:
            return
        f = signals.face
        p = signals.posture
        if f.face_visible:
            self.buffers["head_yaw"].append(f.head_yaw)
            self.buffers["head_pitch"].append(f.head_pitch)
            self.buffers["gaze_x"].append(f.gaze_x)
            self.buffers["gaze_y"].append(f.gaze_y)
            ear = (f.ear_left + f.ear_right) / 2.0
            self.buffers["ear"].append(ear)
        if p.posture_visible:
            self.buffers["forward_lean"].append(p.forward_lean)
            self.buffers["body_stability"].append(p.body_stability)

    @property
    def is_complete(self) -> bool:
        return len(self.buffers["head_yaw"]) >= self.required

    def build_baseline(self) -> UserBaseline:
        def safe_mean(lst): return float(np.mean(lst)) if lst else 0.0
        def safe_std(lst):  return float(np.std(lst))  if lst else 1.0

        bl = UserBaseline(
            head_yaw_mean   = safe_mean(self.buffers["head_yaw"]),
            head_yaw_std    = max(safe_std(self.buffers["head_yaw"]), 3.0),
            head_pitch_mean = safe_mean(self.buffers["head_pitch"]),
            head_pitch_std  = max(safe_std(self.buffers["head_pitch"]), 3.0),
            gaze_x_mean     = safe_mean(self.buffers["gaze_x"]),
            gaze_x_std      = max(safe_std(self.buffers["gaze_x"]), 0.05),
            gaze_y_mean     = safe_mean(self.buffers["gaze_y"]),
            gaze_y_std      = max(safe_std(self.buffers["gaze_y"]), 0.05),
            ear_mean        = safe_mean(self.buffers["ear"]),
            blink_rate_mean = 15.0,
            forward_lean_mean    = safe_mean(self.buffers["forward_lean"]),
            body_stability_mean  = safe_mean(self.buffers["body_stability"]),
            calibrated      = True,
            calibrated_at   = time.time(),
            n_samples       = len(self.buffers["head_yaw"]),
        )
        logger.info(
            f"Baseline built: yaw={bl.head_yaw_mean:.1f}±{bl.head_yaw_std:.1f} "
            f"gaze_x={bl.gaze_x_mean:.2f}±{bl.gaze_x_std:.2f}"
        )
        return bl


# ─── Processed Signals ───────────────────────────────────────────────────────

@dataclass
class ProcessedSignals:
    """Smoothed, baseline-normalized signals ready for cognitive modules."""
    # Head pose deviation from baseline
    head_yaw_dev: float   = 0.0   # z-score from calibrated neutral
    head_pitch_dev: float = 0.0
    head_roll: float      = 0.0

    # Gaze
    gaze_x_dev: float     = 0.0   # deviation from neutral gaze
    gaze_y_dev: float     = 0.0
    gaze_instability: float = 0.0 # rolling std of gaze

    # Eyes
    ear: float            = 0.28
    blink_rate: float     = 15.0
    brow_furrow: float    = 0.0

    # Posture
    shoulder_slope: float  = 0.0
    forward_lean: float    = 0.0
    head_droop: float      = 0.0
    body_stability: float  = 1.0

    # Hands
    hand_visible: bool     = False
    hand_speed: float      = 0.0
    face_touch: bool       = False

    # Meta
    face_visible: bool     = False
    signal_quality: float  = 0.0   # 0–1 reliability
    timestamp: float       = field(default_factory=time.time)


# ─── Main Signal Processor ───────────────────────────────────────────────────

class SignalProcessor:
    """
    Stage 2 of the pipeline:
    Raw signals → Kalman filtered → baseline normalized → ProcessedSignals
    """

    def __init__(self, config: dict, baseline: Optional[UserBaseline] = None):
        self.config   = config
        self.baseline = baseline or UserBaseline()

        # Kalman filters for each signal
        self._kf: Dict[str, KalmanFilter1D] = {
            "yaw":            KalmanFilter1D(0.05, 0.5),
            "pitch":          KalmanFilter1D(0.05, 0.5),
            "roll":           KalmanFilter1D(0.05, 0.5),
            "gaze_x":         KalmanFilter1D(0.02, 0.2),
            "gaze_y":         KalmanFilter1D(0.02, 0.2),
            "ear":            KalmanFilter1D(0.01, 0.05),
            "shoulder_slope": KalmanFilter1D(0.01, 0.3),
            "forward_lean":   KalmanFilter1D(0.01, 0.2),
            "body_stability": KalmanFilter1D(0.005, 0.1),
            "brow_furrow":    KalmanFilter1D(0.01, 0.15),
            "head_droop":     KalmanFilter1D(0.01, 0.15),
            "hand_speed":     KalmanFilter1D(0.02, 0.3),
        }

        # Gaze history for instability calculation
        self._gaze_history_x: list = []
        self._gaze_history_y: list = []
        self._gaze_history_window = 30   # frames (~1 sec at 30fps)

    def update_baseline(self, baseline: UserBaseline):
        self.baseline = baseline
        logger.info("Signal processor baseline updated.")

    def process(self, raw: RawSignals) -> ProcessedSignals:
        f = raw.face
        p = raw.posture
        h = raw.hands

        # Apply Kalman filtering
        yaw   = self._kf["yaw"].update(f.head_yaw)
        pitch = self._kf["pitch"].update(f.head_pitch)
        roll  = self._kf["roll"].update(f.head_roll)
        gx    = self._kf["gaze_x"].update(f.gaze_x)
        gy    = self._kf["gaze_y"].update(f.gaze_y)
        ear   = self._kf["ear"].update((f.ear_left + f.ear_right) / 2.0)
        brow  = self._kf["brow_furrow"].update(f.brow_furrow)

        slope   = self._kf["shoulder_slope"].update(p.shoulder_slope)
        lean    = self._kf["forward_lean"].update(p.forward_lean)
        droop   = self._kf["head_droop"].update(p.head_droop)
        stab    = self._kf["body_stability"].update(p.body_stability)
        h_speed = self._kf["hand_speed"].update(h.hand_movement_speed)

        # Normalize to baseline z-scores
        bl = self.baseline
        yaw_dev   = (yaw   - bl.head_yaw_mean)   / (bl.head_yaw_std   + 1e-6)
        pitch_dev = (pitch - bl.head_pitch_mean) / (bl.head_pitch_std + 1e-6)
        gx_dev    = (gx    - bl.gaze_x_mean)     / (bl.gaze_x_std    + 1e-6)
        gy_dev    = (gy    - bl.gaze_y_mean)     / (bl.gaze_y_std    + 1e-6)

        # Gaze instability (rolling std)
        self._gaze_history_x.append(gx)
        self._gaze_history_y.append(gy)
        if len(self._gaze_history_x) > self._gaze_history_window:
            self._gaze_history_x.pop(0)
            self._gaze_history_y.pop(0)
        gaze_instability = float(
            np.std(self._gaze_history_x) + np.std(self._gaze_history_y)
        ) if len(self._gaze_history_x) > 5 else 0.0

        # Signal quality
        quality = 0.0
        weights = []
        if f.face_visible:
            weights.append(f.face_confidence)
        if p.posture_visible:
            weights.append(p.posture_confidence)
        quality = float(np.mean(weights)) if weights else 0.0

        return ProcessedSignals(
            head_yaw_dev    = float(np.clip(yaw_dev,   -5, 5)),
            head_pitch_dev  = float(np.clip(pitch_dev, -5, 5)),
            head_roll       = float(roll),
            gaze_x_dev      = float(np.clip(gx_dev,   -5, 5)),
            gaze_y_dev      = float(np.clip(gy_dev,   -5, 5)),
            gaze_instability= float(np.clip(gaze_instability, 0, 1)),
            ear             = float(ear),
            blink_rate      = float(f.blink_rate),
            brow_furrow     = float(brow),
            shoulder_slope  = float(slope),
            forward_lean    = float(np.clip(lean, 0, 1)),
            head_droop      = float(np.clip(droop, 0, 1)),
            body_stability  = float(np.clip(stab, 0, 1)),
            hand_visible    = h.hand_visible,
            hand_speed      = float(np.clip(h_speed, 0, 1)),
            face_touch      = h.face_touch_detected,
            face_visible    = f.face_visible,
            signal_quality  = quality,
            timestamp       = raw.timestamp,
        )