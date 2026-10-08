#!/bin/bash
# Build "Qwen Image Studio.app" into dist/.
#
#   bash build/build_app.sh
#
# Everything needed is inside app/ plus build/ (Swift shell, bootstrap,
# icon, Info.plist). uv is downloaded into build/uv/ on the first build when
# the network allows; without it, the app falls back to a system Python 3.11+.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
APP_NAME="Qwen Image Studio"
STAGE="$ROOT/build/stage"
DIST="$ROOT/dist"

# ── uv, best effort (lets the app fetch its own Python on machines without one)
if [ ! -x "$ROOT/build/uv/uv" ]; then
  echo "── fetching uv (best effort)"
  mkdir -p "$ROOT/build/uv.dl" "$ROOT/build/uv"
  if curl -fsSL --max-time 120 -o "$ROOT/build/uv.dl/uv.tar.gz" \
      "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz"; then
    tar -xzf "$ROOT/build/uv.dl/uv.tar.gz" -C "$ROOT/build/uv.dl"
    find "$ROOT/build/uv.dl" -name uv -type f -exec cp {} "$ROOT/build/uv/uv" \;
    chmod +x "$ROOT/build/uv/uv"
  else
    echo "   network unavailable — the app will use a system Python instead"
  fi
  rm -rf "$ROOT/build/uv.dl"
fi

# ── the icon
echo "── icon"
"$ROOT/app/.venv/bin/python" "$ROOT/build/make_icon.py" >/dev/null || \
  python3 -c "import PIL" 2>/dev/null && python3 "$ROOT/build/make_icon.py" >/dev/null || true
[ -f "$ROOT/build/AppIcon.icns" ] || { echo "the icon is missing — install Pillow and rerun" >&2; exit 1; }

# ── stage the bundle
echo "── staging"
rm -rf "$STAGE"
mkdir -p "$STAGE/$APP_NAME.app/Contents/MacOS" \
         "$STAGE/$APP_NAME.app/Contents/Resources/web" \
         "$STAGE/$APP_NAME.app/Contents/Resources/uv" \
         "$DIST"

cp -R "$ROOT/app/web/static" "$STAGE/$APP_NAME.app/Contents/Resources/web/static"
cp "$ROOT/app/web/server.py" "$STAGE/$APP_NAME.app/Contents/Resources/web/server.py"
cp "$ROOT/build/AppIcon.icns" "$STAGE/$APP_NAME.app/Contents/Resources/AppIcon.icns"
cp "$ROOT/build/Info.plist" "$STAGE/$APP_NAME.app/Contents/Info.plist"
cp "$ROOT/build/bootstrap.sh" "$STAGE/$APP_NAME.app/Contents/Resources/bootstrap.sh"
[ -x "$ROOT/build/uv/uv" ] && cp "$ROOT/build/uv/uv" "$STAGE/$APP_NAME.app/Contents/Resources/uv/uv"

chmod +x "$STAGE/$APP_NAME.app/Contents/Resources/bootstrap.sh"

# ── the Swift shell
echo "── compiling the shell"
swiftc -O -o "$STAGE/$APP_NAME.app/Contents/MacOS/QwenImageStudio" "$ROOT/build/main.swift" \
  -framework AppKit -framework WebKit

# ── sign (ad-hoc) and ship
echo "── signing"
codesign --force --deep -s - "$STAGE/$APP_NAME.app" >/dev/null

rm -rf "$DIST/$APP_NAME.app"
mv "$STAGE/$APP_NAME.app" "$DIST/"
rm -f "$DIST/Setup Render Environment.command"
rm -rf "$STAGE"
echo "── zipping"
cd "$DIST"
rm -f "$APP_NAME.zip"
zip -qry "$APP_NAME.zip" "$APP_NAME.app"

echo
echo "Built: $DIST/$APP_NAME.app"
ls -la "$DIST"
