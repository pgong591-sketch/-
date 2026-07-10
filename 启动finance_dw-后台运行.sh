#!/bin/zsh
set -e

cd "$(dirname "$0")"

PROJECT_DIR="$(pwd)"
PID_FILE="data/streamlit_desktop_8502.pid"
LOG_FILE="data/streamlit_desktop.log"
URL="http://localhost:8502"

mkdir -p data

open_finance_dw() {
  python3 -m webbrowser "$URL" >/dev/null 2>&1 || true
}

report_launch_error() {
  local message="$1"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $message" >> "$LOG_FILE"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'display dialog "8502 已被其他服务占用或 finance_dw 启动失败，请先关闭占用程序后再试。" with title "finance_dw 启动失败" buttons {"好的"} default button "好的" with icon caution' >/dev/null 2>&1 || true
  fi
}

is_current_project_streamlit() {
  local pid="$1"
  local command_line
  local cwd_path
  local port_pid

  if ! ps -p "$pid" >/dev/null 2>&1; then
    return 1
  fi

  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  cwd_path="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
  port_pid="$(lsof -nP -iTCP:8502 -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -n 1 || true)"

  [[ "$command_line" == *"streamlit"* ]] || return 1
  [[ "$command_line" == *"app.py"* ]] || return 1
  [[ "$command_line" == *"8502"* ]] || return 1
  [[ "$cwd_path" == "$PROJECT_DIR" ]] || return 1
  [[ "$port_pid" == "$pid" ]] || return 1
}

CURRENT_PORT_PID="$(lsof -nP -iTCP:8502 -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -n 1 || true)"

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(tr -d '[:space:]' < "$PID_FILE" 2>/dev/null || true)"
  if [[ "$OLD_PID" =~ '^[1-9][0-9]*$' ]] && is_current_project_streamlit "$OLD_PID"; then
    open_finance_dw
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [[ "$CURRENT_PORT_PID" =~ '^[1-9][0-9]*$' ]] && is_current_project_streamlit "$CURRENT_PORT_PID"; then
  echo "$CURRENT_PORT_PID" > "$PID_FILE"
  open_finance_dw
  exit 0
fi

if [[ "$CURRENT_PORT_PID" =~ '^[1-9][0-9]*$' ]]; then
  report_launch_error "8502 is occupied by another process: pid=$CURRENT_PORT_PID"
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

if [ -x "./.venv/bin/streamlit" ]; then
  STREAMLIT_BIN="./.venv/bin/streamlit"
elif command -v streamlit >/dev/null 2>&1; then
  STREAMLIT_BIN="$(command -v streamlit)"
else
  echo "streamlit command not found" > "$LOG_FILE"
  exit 1
fi

NEW_PID="$(python3 - "$STREAMLIT_BIN" "$LOG_FILE" <<'PY'
import subprocess
import sys

streamlit_bin = sys.argv[1]
log_file = sys.argv[2]
log = open(log_file, "ab", buffering=0)
process = subprocess.Popen(
    [streamlit_bin, "run", "app.py", "--server.port", "8502", "--server.headless", "true"],
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
print(process.pid)
PY
)"

for _ in {1..10}; do
  sleep 1
  if [[ "$NEW_PID" =~ '^[1-9][0-9]*$' ]] && is_current_project_streamlit "$NEW_PID"; then
    echo "$NEW_PID" > "$PID_FILE"
    open_finance_dw
    exit 0
  fi
  CURRENT_PORT_PID="$(lsof -nP -iTCP:8502 -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -n 1 || true)"
  if [[ "$CURRENT_PORT_PID" =~ '^[1-9][0-9]*$' ]]; then
    if is_current_project_streamlit "$CURRENT_PORT_PID"; then
      echo "$CURRENT_PORT_PID" > "$PID_FILE"
      open_finance_dw
      exit 0
    fi
    rm -f "$PID_FILE"
    report_launch_error "8502 is occupied by another process after startup attempt: pid=$CURRENT_PORT_PID"
    exit 1
  fi
done

rm -f "$PID_FILE"
report_launch_error "finance_dw streamlit failed to start on 8502"
exit 1
