#!/bin/bash
# Setup Render Environment — one-time, for actually rendering.
#
# The app itself runs out of the box (its UI, sessions, references and gallery
# need nothing but a small Python). Rendering needs the model environment:
# torch, diffusers and friends, plus the weights (~30 GB model, ~18 GB per
# enhancer). This script prepares both.
#
#   Double-click me in Finder, or run in Terminal:
#     "Setup Render Environment.command"                  # environment only
#     "Setup Render Environment.command" --with-weights   # + download the three weights
#
# After it finishes, open the app's ⚙ Paths and point them at the weights
# (or let --with-weights do that for you).
set -uo pipefail

WITH_WEIGHTS=0
for arg in "$@"; do
  [ "$arg" = "--with-weights" ] && WITH_WEIGHTS=1
done

APP="$(cd "$(dirname "$0")" && pwd)"
# next to the .app, or inside it
if [ -d "$APP/Contents/Resources/project" ]; then
  RESOURCES="$APP/Contents/Resources"
elif [ -d "$APP/Qwen Image Studio.app/Contents/Resources/project" ]; then
  RESOURCES="$APP/Qwen Image Studio.app/Contents/Resources"
else
  echo "Run me from the folder that holds “Qwen Image Studio.app”." >&2
  exit 1
fi

DATA="$HOME/Library/Application Support/Qwen Image Studio"
mkdir -p "$DATA"

UV="$RESOURCES/uv/uv"
if [ ! -x "$UV" ]; then
  UV="$(command -v uv || true)"
  if [ -z "$UV" ]; then
    echo "uv is missing. Install it first:  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
  fi
fi

echo "── copying the project into $DATA/project"
rm -rf "$DATA/project.tmp"
cp -R "$RESOURCES/project" "$DATA/project.tmp"
rm -rf "$DATA/project"
mv "$DATA/project.tmp" "$DATA/project"

echo "── installing the model environment (torch, diffusers, transformers … this downloads several GB)"
"$UV" sync --project "$DATA/project" --locked || exit 1

echo "── render environment ready: $DATA/project/.venv/bin/python"

if [ "$WITH_WEIGHTS" = "1" ]; then
  MODELS="${QWEN_MODELS:-$HOME/models}"
  mkdir -p "$MODELS"
  echo "── downloading the weights into $MODELS (about 67 GB in total; grab a coffee)"
  "$DATA/project/.venv/bin/python" -m huggingface_hub.commands.huggingface_cli download Qwen/Qwen-Image-2.1 \
    --include "model_index.json" "processor/*" "scheduler/*" "text_encoder/*" "transformer/*" "vae/*" \
    --local-dir "$MODELS/Qwen-Image-2.1" || exit 1
  "$DATA/project/.venv/bin/python" -m huggingface_hub.commands.huggingface_cli download Qwen/Qwen-Image-2.1-PE-T2I \
    --local-dir "$MODELS/Qwen-Image-2.1-PE-T2I" || exit 1
  "$DATA/project/.venv/bin/python" -m huggingface_hub.commands.huggingface_cli download Qwen/Qwen-Image-2.1-PE-I2I \
    --local-dir "$MODELS/Qwen-Image-2.1-PE-I2I" || exit 1

  echo "── filling the app's ⚙ Paths"
  "$DATA/project/.venv/bin/python" - "$DATA/store.json" "$MODELS" <<'EOF'
import json, pathlib, sys
store_path, models = pathlib.Path(sys.argv[1]), sys.argv[2]
store = json.loads(store_path.read_text()) if store_path.exists() else {}
paths = store.setdefault("paths", {})
paths["model"] = f"{models}/Qwen-Image-2.1"
paths["pe_t2i"] = f"{models}/Qwen-Image-2.1-PE-T2I"
paths["pe_i2i"] = f"{models}/Qwen-Image-2.1-PE-I2I"
store_path.write_text(json.dumps(store, ensure_ascii=False, indent=1))
EOF
fi

echo
echo "Done. Open “Qwen Image Studio” — ${WITH_WEIGHTS:+the paths are set, }press Generate."
[ "$WITH_WEIGHTS" = "0" ] && echo "Then use ⚙ Paths to point at your weights, or run me again with --with-weights."
