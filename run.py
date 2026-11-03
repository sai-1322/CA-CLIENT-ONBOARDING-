"""Start the app. Run:  python run.py   then open http://127.0.0.1:8000 (it opens by itself)."""
from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex((HOST, port)) != 0


def open_browser_later() -> None:
    time.sleep(1.5)
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    if not port_is_free(PORT):
        print(f"Port {PORT} is already in use. Either close the other program, or run:")
        print(f"    PORT=8001 python run.py   (Windows PowerShell:  $env:PORT=8001; python run.py)")
        raise SystemExit(1)
    print(f"Open http://{HOST}:{PORT} in your browser. Press Ctrl+C here to stop.")
    if os.environ.get("NO_BROWSER") != "1":
        threading.Thread(target=open_browser_later, daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
