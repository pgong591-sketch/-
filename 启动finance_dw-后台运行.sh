#!/bin/zsh
set -e

export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"
export LC_CTYPE="${LC_CTYPE:-en_US.UTF-8}"
ORIGINAL_PATH="${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
export PATH="/opt/homebrew/bin:/usr/local/bin:${ORIGINAL_PATH}:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$(dirname "$0")"

PROJECT_DIR="$(pwd -P)"
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

canonical_path() {
  python3 - "$1" <<'PY'
import pathlib
import sys

if len(sys.argv) < 2 or not sys.argv[1]:
    raise SystemExit(1)
print(pathlib.Path(sys.argv[1]).resolve())
PY
}

decode_lsof_path() {
  python3 - "$1" <<'PY'
import codecs
import re
import sys

value = sys.argv[1]
try:
    if "\\x" in value or re.search(r"\\[0-7]{3}", value):
        value = codecs.decode(value, "unicode_escape").encode("latin1").decode("utf-8")
except Exception:
    pass
print(value)
PY
}

process_command_line() {
  python3 - "$1" <<'PY' 2>/dev/null || ps -p "$1" -o command= 2>/dev/null || true
import ctypes
import ctypes.util
import os
import shlex
import sys

pid = int(sys.argv[1])
libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
mib = (ctypes.c_int * 3)(1, 49, pid)
size = ctypes.c_size_t(8192)
buf = ctypes.create_string_buffer(size.value)
if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
    raise SystemExit(1)
data = buf.raw[: size.value]
argc = int.from_bytes(data[:4], sys.byteorder)
parts = [part.decode("utf-8", "replace") for part in data[4:].split(b"\x00") if part]
argv = parts[1 : 1 + argc]
if not argv:
    raise SystemExit(1)
print(" ".join(shlex.quote(arg) for arg in argv))
PY
}

is_current_project_streamlit() {
  local pid="$1"
  local command_line
  local cwd_raw
  local cwd_path
  local cwd_canonical
  local port_pid

  if ! lsof -p "$pid" >/dev/null 2>&1; then
    return 1
  fi

  command_line="$(process_command_line "$pid")"
  cwd_raw="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true)"
  [[ -n "$cwd_raw" ]] || return 1
  cwd_path="$(decode_lsof_path "$cwd_raw")"
  [[ -n "$cwd_path" ]] || return 1
  cwd_canonical="$(canonical_path "$cwd_path" 2>/dev/null || true)"
  [[ -n "$cwd_canonical" ]] || cwd_canonical="$cwd_path"
  port_pid="$(lsof -nP -iTCP:8502 -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p' | head -n 1 || true)"

  [[ "$command_line" == *"streamlit"* ]] || return 1
  [[ "$command_line" == *"app.py"* ]] || return 1
  [[ "$command_line" == *"8502"* ]] || return 1
  [[ "$cwd_canonical" == "$PROJECT_DIR" ]] || return 1
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
