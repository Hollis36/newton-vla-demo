#!/usr/bin/env bash
# Build assets/app_icon.icns from the 1024² master assets/app_icon.png using
# macOS sips + iconutil. Called by `make icon` after regenerating the PNG.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
M=app_icon.png
[ -f "$M" ] || { echo "missing $M — run: python3 assets/app_icon.py"; exit 1; }
SET=/tmp/newton_app.iconset
rm -rf "$SET"; mkdir -p "$SET"
sips -z 16 16   "$M" --out "$SET/icon_16x16.png"      >/dev/null
sips -z 32 32   "$M" --out "$SET/icon_16x16@2x.png"   >/dev/null
sips -z 32 32   "$M" --out "$SET/icon_32x32.png"      >/dev/null
sips -z 64 64   "$M" --out "$SET/icon_32x32@2x.png"   >/dev/null
sips -z 128 128 "$M" --out "$SET/icon_128x128.png"    >/dev/null
sips -z 256 256 "$M" --out "$SET/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "$M" --out "$SET/icon_256x256.png"    >/dev/null
sips -z 512 512 "$M" --out "$SET/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "$M" --out "$SET/icon_512x512.png"    >/dev/null
cp "$M" "$SET/icon_512x512@2x.png"
iconutil -c icns "$SET" -o app_icon.icns
echo "built assets/app_icon.icns"
