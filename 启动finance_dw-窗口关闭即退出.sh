#!/bin/zsh
set -e

cd "$(dirname "$0")"

cleanup() {
  if [ -n "${APP_PID:-}" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$APP_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT HUP INT TERM

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py &
APP_PID=$!
wait "$APP_PID"
