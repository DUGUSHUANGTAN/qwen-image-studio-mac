#!/bin/bash
# Prepare the studio's small server environment: Python 3.11+ with Pillow
# (Pillow for image checks and thumbnails) and, optionally, websocket-client
# (for fine-grained ComfyUI progress; without it the backend polls instead).
# Idempotent; exits 0 when the environment already works.
#
#   bootstrap.sh --data-dir DIR --resources DIR
set -uo pipefail

DATA_DIR=""
RESOURCES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --resources) RESOURCES="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$DATA_DIR" ] || { echo "bootstrap: --data-dir is required" >&2; exit 64; }
[ -n "$RESOURCES" ] || { echo "bootstrap: --resources is required" >&2; exit 64; }

mkdir -p "$DATA_DIR"
LOG="$DATA_DIR/bootstrap.log"
ENV_PY="$DATA_DIR/server-env/bin/python"

log() { echo "[bootstrap $(date '+%H:%M:%S')] $*" >>"$LOG"; }

# websocket-client is a nice-to-have: never let it fail the bootstrap.
add_websocket() {
  "$ENV_PY" -c "import websocket" >/dev/null 2>&1 && return 0
  if [ -x "$RESOURCES/uv/uv" ]; then
    # a uv-made venv has no pip of its own
    "$RESOURCES/uv/uv" pip install --python "$ENV_PY" websocket-client >>"$LOG" 2>&1 && return 0
  fi
  "$ENV_PY" -m pip install --quiet --disable-pip-version-check websocket-client >>"$LOG" 2>&1 \
    || log "websocket-client not installed — ComfyUI progress will poll instead"
  return 0
}

# Already usable? Only Pillow is required.
if [ -x "$ENV_PY" ] && "$ENV_PY" -c "import PIL" >/dev/null 2>&1; then
  add_websocket
  log "server environment already ready"
  exit 0
fi

log "preparing the server environment in $DATA_DIR/server-env"

# A venv left half-built by an earlier run has to give way.
VENV_ARGS=(venv --python 3.12)
[ -e "$DATA_DIR/server-env" ] && VENV_ARGS+=(--clear)

UV="$RESOURCES/uv/uv"
if [ -x "$UV" ]; then
  log "trying the bundled uv for a managed Python"
  if "$UV" "${VENV_ARGS[@]}" "$DATA_DIR/server-env" >>"$LOG" 2>&1; then
    "$UV" pip install --python "$ENV_PY" pillow websocket-client >>"$LOG" 2>&1 || log "uv pip install failed"
  else
    log "uv venv failed (no managed Python and no network?)"
  fi
fi

if [ ! -x "$ENV_PY" ] || ! "$ENV_PY" -c "import PIL" >/dev/null 2>&1; then
  log "falling back to a system Python 3.11+"
  for candidate in \
    "${PYTHON:-}" \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/*/bin/python3 \
    /usr/bin/python3; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      log "using $candidate"
      "$candidate" -m venv --clear "$DATA_DIR/server-env" >>"$LOG" 2>&1 || { log "venv failed with $candidate"; continue; }
      "$ENV_PY" -m pip install --quiet --disable-pip-version-check pillow websocket-client >>"$LOG" 2>&1 || log "pip install failed"
      "$ENV_PY" -c "import PIL" >/dev/null 2>&1 && break
    fi
  done
fi

if [ -x "$ENV_PY" ] && "$ENV_PY" -c "import PIL" >/dev/null 2>&1; then
  add_websocket
  log "server environment ready ($("$ENV_PY" -c 'import sys; print(sys.version.split()[0])'))"
  exit 0
fi

log "FAILED: no Python 3.11+ with Pillow could be prepared"
echo "bootstrap: could not prepare a Python with Pillow — see $LOG" >&2
exit 1
