#!/usr/bin/env python3
"""
run.py — FocusForge v2 Entry Point
════════════════════════════════════════════════════════════════
Usage:
    python run.py                      # default (127.0.0.1:8765)
    python run.py --host 0.0.0.0       # expose on LAN
    python run.py --port 9000          # custom port
    python run.py --reload             # dev mode with hot-reload
    python run.py --no-camera          # run without webcam (API only)
    python run.py --open-browser       # auto-open browser on start
    python run.py --log-level debug    # verbose logging

Dashboard:
    OpenCV HUD  →  runs in a separate terminal via backend (live overlay)
    React UI    →  http://localhost:3000  (cd dashboard && npm run dev)
                   or built: http://localhost:8765/dashboard
"""

import sys
import os
import argparse
import time
import webbrowser
import threading
from pathlib import Path


def check_dependencies():
    """Check all required packages are installed."""
    required = {
        "fastapi":    "fastapi",
        "uvicorn":    "uvicorn",
        "cv2":        "opencv-python",
        "mediapipe":  "mediapipe",
        "numpy":      "numpy",
        "aiosqlite":  "aiosqlite",
        "yaml":       "pyyaml",
        "scipy":      "scipy",
    }
    missing = []
    for module, pkg in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)

    if missing:
        print("\n❌  Missing packages:")
        for p in missing:
            print(f"     pip install {p}")
        print("\n  Install all at once:")
        print("     pip install -r requirements.txt\n")
        sys.exit(1)


def check_data_dir():
    """Ensure data/ directory exists."""
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(exist_ok=True)


def open_browser_delayed(url: str, delay: float = 2.5):
    """Open browser after a short delay (server needs time to start)."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main():
    parser = argparse.ArgumentParser(
        description="FocusForge v2 — Cognitive AI Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host",         default=None,    help="Bind host (default: from config)")
    parser.add_argument("--port",         default=None,    type=int, help="Port (default: from config)")
    parser.add_argument("--reload",       action="store_true", help="Enable hot-reload (dev mode)")
    parser.add_argument("--no-camera",    action="store_true", help="Start without webcam")
    parser.add_argument("--open-browser", action="store_true", help="Auto-open browser on start")
    parser.add_argument("--log-level",    default="info",  choices=["debug","info","warning","error"],
                        help="Uvicorn log level")
    args = parser.parse_args()

    # ── Dependency check ─────────────────────────────────────────────────────
    check_dependencies()
    check_data_dir()

    # ── Load config ───────────────────────────────────────────────────────────
    config_path = Path(__file__).parent / "config" / "config.yaml"
    if not config_path.exists():
        print(f"❌  config/config.yaml not found at {config_path}")
        sys.exit(1)

    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    host = args.host or config.get("app", {}).get("host", "127.0.0.1")
    port = args.port or config.get("app", {}).get("port", 8765)
    url  = f"http://{host}:{port}"

    # ── No-camera mode ────────────────────────────────────────────────────────
    if args.no_camera:
        os.environ["FOCUSFORGE_NO_CAMERA"] = "1"

    # ── Banner ────────────────────────────────────────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          ⚡  FocusForge AI  v2.0  ⚡                    ║")
    print("║      Real-time Cognitive Intelligence System            ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Server    →  {url:<43}║")
    print(f"║  Docs      →  {url + '/docs':<43}║")
    print(f"║  Dashboard →  {url + '/dashboard':<43}║")
    print(f"║  Dev UI    →  http://localhost:3000  (npm run dev)      ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  ORIGINAL MODULES (v1)                                  ║")
    print("║    ✅ Module 1 · Context Switch Intelligence (FSM)       ║")
    print("║    ✅ Module 2 · Cognitive State Modeling                ║")
    print("║    ✅ Module 3 · Procrastination Analysis (5 layers)     ║")
    print("║    ✅ Module 4 · Personal Cognitive Signature            ║")
    print("║    ✅ Module 5 · Temporal Impact & Ripple Tracker        ║")
    print("║    ✅ Module 6 · Meta-Cognition Module                   ║")
    print("║    ✅ Module 7 · Predictive Recovery Optimizer           ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  NEW FEATURES (v2)                                      ║")
    print("║    🧠 LSTM Model Layer   (temporal_model.py)            ║")
    print("║    📦 Feature Logger     (feature_logger.py)            ║")
    print("║    🔔 Event Bus          (event_bus.py)                 ║")
    print("║    📊 Metrics Dashboard  (metrics.py)                   ║")
    print("║    ⚛️  React Dashboard   (dashboard/)                   ║")
    print("║    🔢 Confidence Scores  (all modules)                  ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Camera    : {'DISABLED (--no-camera)' if args.no_camera else 'enabled (device_id=' + str(config.get('camera',{}).get('device_id',0)) + ')':<40}║")
    print(f"║  Reload    : {'yes' if args.reload else 'no':<43}║")
    print(f"║  Log level : {args.log_level:<43}║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("  How to use:")
    print("  1. Allow camera access when prompted")
    print("  2. Sit in front of camera and wait for calibration (~30s)")
    print("  3. Open the React dashboard: cd dashboard && npm run dev")
    print("  4. Or use the built-in dashboard at /dashboard")
    print()
    print("  Press Ctrl+C to stop")
    print()

    # ── Auto-open browser ─────────────────────────────────────────────────────
    if args.open_browser:
        open_browser_delayed(url)

    # ── Start server ──────────────────────────────────────────────────────────
    import uvicorn
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
