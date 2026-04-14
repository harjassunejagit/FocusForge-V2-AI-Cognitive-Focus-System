"""
webcam_capture.py
Async-friendly webcam capture loop. Runs in a background thread and feeds
frames to the MediaPipe analyzer.
"""

import cv2
import time
import threading
import logging
from queue import Queue, Full
from typing import Optional, Callable
from .mediapipe_analyzer import MediaPipeAnalyzer, RawSignals

logger = logging.getLogger("webcam_capture")


class WebcamCapture:
    """
    Thread-safe webcam capture with subsampled MediaPipe processing.
    Exposes the latest RawSignals via get_latest_signals().
    """

    def __init__(self, config: dict, on_signals: Optional[Callable] = None):
        self.config = config
        self.on_signals = on_signals           # callback(RawSignals)
        self.device_id  = config.get("device_id", 0)
        self.target_fps = config.get("fps_face", 30)

        self._analyzer = MediaPipeAnalyzer(config)
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._latest_signals: Optional[RawSignals] = None
        self._signal_lock = threading.Lock()
        self._frame_count = 0
        self._running = False

        # Signal queue for async consumption
        self.signal_queue: Queue = Queue(maxsize=5)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open camera and start capture thread. Returns True on success."""
        self._cap = cv2.VideoCapture(self.device_id)
        if not self._cap.isOpened():
            logger.error(f"Cannot open camera device {self.device_id}")
            return False

        w = self.config.get("frame_width", 640)
        h = self.config.get("frame_height", 480)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera started: device={self.device_id} {w}x{h}@{self.target_fps}fps")
        return True

    def stop(self):
        """Stop capture thread and release camera."""
        self._stop_event.set()
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._cap:
            self._cap.release()
        self._analyzer.close()
        logger.info("Camera stopped.")

    # ── Capture Loop ─────────────────────────────────────────────────────────

    def _capture_loop(self):
        interval = 1.0 / self.target_fps
        while not self._stop_event.is_set():
            t0 = time.monotonic()

            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Frame grab failed, retrying...")
                time.sleep(0.1)
                continue

            self._frame_count += 1

            # Mirror frame horizontally for natural feel
            frame = cv2.flip(frame, 1)

            try:
                signals = self._analyzer.process_frame(frame)
                signals.face.blink_rate = self._analyzer.get_blink_rate()

                with self._signal_lock:
                    self._latest_signals = signals

                # Non-blocking queue push
                try:
                    self.signal_queue.put_nowait(signals)
                except Full:
                    # Drop oldest, push new
                    try:
                        self.signal_queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        self.signal_queue.put_nowait(signals)
                    except Exception:
                        pass

                if self.on_signals:
                    self.on_signals(signals)

            except Exception as e:
                logger.error(f"Analysis error: {e}", exc_info=False)

            # Rate limiting
            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_latest_signals(self) -> Optional[RawSignals]:
        with self._signal_lock:
            return self._latest_signals

    @property
    def is_running(self) -> bool:
        return self._running and not self._stop_event.is_set()

    @property
    def frame_count(self) -> int:
        return self._frame_count