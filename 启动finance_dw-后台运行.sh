#!/bin/zsh
set -e

cd "$(dirname "$0")"

PID_FILE="data/streamlit_desktop.pid"
LOG_FILE="data/streamlit_desktop.log"
URL="http://localhost:8501"

mkdir -p data

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    python3 -m webbrowser "$URL" >/dev/null 2>&1 || true
    exit 0
  fi
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

nohup streamlit run app.py > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

sleep 2
python3 -m webbrowser "$URL" >/dev/null 2>&1 || true
