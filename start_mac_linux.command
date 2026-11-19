#!/bin/bash
# Double-click this file (Mac) or run ./start_mac_linux.command (Linux) to start the app.
# Keep the window open while you use it. Press Ctrl+C here to stop.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "First-time setup. This takes a few minutes, and needs internet."
  python3 -m venv .venv || { echo "Install Python 3 from python.org first."; read -r -p "Press Enter to close."; exit 1; }
  .venv/bin/python -m pip install -r requirements.txt || { read -r -p "Setup did not finish. Press Enter to close."; exit 1; }
fi

echo "Starting the app. Your browser will open at http://127.0.0.1:8000"
.venv/bin/python run.py
