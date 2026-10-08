#!/usr/bin/env bash
# Run the standalone studio from a checkout, without the Mac app shell.
#
#   bash app/run_dev.sh            → http://127.0.0.1:8731 (dev port, leaves 8730 for the app)
#   bash app/run_dev.sh stop
#
# The web server needs only Python 3.12+ and Pillow; it makes a small venv at
# app/.venv on first run. Renders go through the ComfyUI set under Paths.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

RUN="$PWD/.cache"
PIDFILE="$RUN/dev-server.pid"
DATA="${QWEN_STUDIO_DATA:-$HOME/Qwen Image Studio}"
PORT="${PORT:-8731}"

stop() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "stopping the studio started before ($pid)"
    kill -TERM "$pid" 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do sleep 0.2; done
  fi
  rm -f "$PIDFILE"
}
if [ "${1:-}" = "stop" ]; then stop; exit 0; fi
stop

PYTHON="${PYTHON:-python3}"
VENV="$PWD/app/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "making the studio's venv at app/.venv"
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check pillow websocket-client
fi

if ! "$VENV/bin/python" -c "import websocket" >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check websocket-client 2>/dev/null || true
fi

mkdir -p "$RUN"
nohup "$VENV/bin/python" "$PWD/app/web/server.py" \
  --port "$PORT" \
  --data-dir "$DATA" \
  ${QWEN_COMFYUI:+--comfyui "$QWEN_COMFYUI"} \
  >"$RUN/dev-server.log" 2>&1 &
echo $! >"$PIDFILE"

for _ in $(seq 1 50); do
  if curl -sf "http://127.0.0.1:$PORT/api/config" >/dev/null 2>&1; then
    echo "qwen image studio (dev) on http://127.0.0.1:$PORT  (log: $RUN/dev-server.log)"
    exit 0
  fi
  sleep 0.2
done
echo "the studio did not come up — log follows" >&2
cat "$RUN/dev-server.log" >&2
exit 1
