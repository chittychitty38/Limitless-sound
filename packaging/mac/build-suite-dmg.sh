#!/bin/bash
# Builds the suite installer from the per-app downloads in $1:
#   Limitless-Sound-Suite-<arch>.pkg  the standard Mac installer, with every app
#   Limitless-Sound-Suite-<arch>.dmg  the same installer in a disk image ($3)
# Each app arrives as a .dmg (or .zip / .app); every .app inside is copied in.
set -euo pipefail
IN="$1"; ARCH="$2"; OUT="$3"
PKG="${OUT%.dmg}.pkg"
HERE="$(cd "$(dirname "$0")" && pwd)"
VERSION="$(tr -d '[:space:]' < "$HERE/../VERSION")"
WORK="$(mktemp -d)"
STAGE="$WORK/apps"
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

# The installer package. Its apps always go to /Applications: Installer's default is to
# "relocate" an app to wherever another copy of it already is (an old download, say).
pkgbuild --analyze --root "$STAGE" "$WORK/components.plist"
n=$(plutil -convert json -o - "$WORK/components.plist" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)))')
for ((i = 0; i < n; i++)); do
  plutil -replace "$i.BundleIsRelocatable" -bool NO "$WORK/components.plist"
done
pkgbuild --root "$STAGE" --component-plist "$WORK/components.plist" --install-location /Applications \
  --identifier org.limitlesssound.suite --version "$VERSION" --scripts "$HERE/installer/scripts" "$WORK/apps.pkg"
sed -e "s/@VERSION@/$VERSION/g" -e "s/@ARCH@/$ARCH/g" "$HERE/installer/distribution.xml" > "$WORK/distribution.xml"
productbuild --distribution "$WORK/distribution.xml" --resources "$HERE/installer/resources" \
  --package-path "$WORK" "$PKG"
# Installer shows each page in the Mac's language: check both languages made it in.
pkgutil --expand "$PKG" "$WORK/expanded"
for page in en.lproj/welcome en.lproj/conclusion es.lproj/welcome es.lproj/conclusion; do
  [ -f "$WORK/expanded/Resources/$page.html" ] || { echo "The installer is missing $page.html"; exit 1; }
done
echo "Built $PKG"

# The same installer in a disk image, for the download links that point at the .dmg.
DMG_STAGE="$WORK/Limitless Sound"
mkdir -p "$DMG_STAGE"
cp "$PKG" "$DMG_STAGE/Install Limitless Sound.pkg"
cp "$HERE/READ-ME-FIRST.txt" "$DMG_STAGE/"
retry hdiutil create -volname "Limitless Sound" -srcfolder "$DMG_STAGE" -ov -format UDZO "$OUT"
echo "Built $OUT"
