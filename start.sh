#!/bin/bash
# FocusForge AI v2 — macOS/Linux launcher

echo ""
echo " ╔══════════════════════════════════════════════╗"
echo " ║        ⚡ FocusForge AI v2 — Starting        ║"
echo " ╚══════════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo " ❌ Python3 not found. Install from https://python.org"; exit 1
fi

# Check Node
if ! command -v node &> /dev/null; then
    echo " ❌ Node.js not found. Install from https://nodejs.org"; exit 1
fi

# Install Python deps
pip3 show fastapi &> /dev/null || pip3 install -r requirements.txt

# Install Node deps
[ -d "dashboard/node_modules" ] || (cd dashboard && npm install && cd ..)

echo " Starting backend on port 8765..."
python3 run.py &
BACKEND_PID=$!

sleep 2

echo " Starting frontend on port 3000..."
cd dashboard && npm run dev &
FRONTEND_PID=$!

echo ""
echo " ✅ Both services started!"
echo " 📊 Dashboard: http://localhost:3000"
echo ""
echo " Press Ctrl+C to stop both services"
echo ""

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ' Stopped.'" INT
wait
