#!/bin/bash
# Builds Limitless-Sound-Suite-<arch>.dmg from the per-app downloads in $1.
# Each app arrives as a .dmg (or .zip / .app); every .app inside is copied in.
set -euo pipefail
IN="$1"; ARCH="$2"; OUT="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
STAGE="$(mktemp -d)/Limitless Sound"
mkdir -p "$STAGE"

# hdiutil on the hosted Mac runners sometimes fails with "Resource busy"; try again.
retry() {
  local n
  for n in 1 2 3 4; do
    "$@" && return 0
    echo "  $1 failed (try $n), retrying in $((n * 5)) s"
    sleep $((n * 5))
  done
  "$@"
}

copy_apps() {  # copy every top-level .app from a folder
  find "$1" -maxdepth 2 -name "*.app" -type d -prune | while read -r app; do
    echo "  + $(basename "$app")"
    ditto "$app" "$STAGE/$(basename "$app")"
  done
}

find "$IN" -name "*.dmg" | while read -r dmg; do
  echo "From $(basename "$dmg"):"
  mnt="$(mktemp -d)"
  retry hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$mnt" "$dmg" >/dev/null
  copy_apps "$mnt"
  hdiutil detach "$mnt" -quiet || hdiutil detach "$mnt" -force -quiet
done
find "$IN" -name "*.zip" | while read -r z; do
  echo "From $(basename "$z"):"
  tmp="$(mktemp -d)"; ditto -x -k "$z" "$tmp"; copy_apps "$tmp"
done
copy_apps "$IN"

count=$(find "$STAGE" -maxdepth 1 -name "*.app" | wc -l | tr -d ' ')
echo "$count apps staged"
[ "$count" -ge 1 ] || { echo "No apps found"; exit 1; }

# Unsigned builds still need an ad-hoc signature to run on Apple Silicon.
for app in "$STAGE"/*.app; do
  codesign --verify "$app" 2>/dev/null || codesign --force --deep --sign - "$app"
done

cp "$HERE/Install Limitless Sound.command" "$HERE/READ-ME-FIRST.txt" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
retry hdiutil create -volname "Limitless Sound" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Built $OUT"
