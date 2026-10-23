#!/bin/bash
# Builds the suite installer from the per-app downloads in $1:
#   Limitless-Sound-Suite-<arch>.pkg  the standard Mac installer, with every app
#   Limitless-Sound-Suite-<arch>.dmg  the same installer in a disk image ($3)
# Each app arrives as a .dmg (or .zip / .app); every .app inside is copied in.
#
# Signing (SIGNING.md), after .github/scripts/mac-sign.sh keychain:
#   SIGN_APPS=true  every app is signed with the Developer ID (an app whose own build already
#                   was is kept as it is); otherwise apps get an ad-hoc signature, as before
#   SIGN_PKG=true   the installer is signed with the Developer ID Installer certificate and,
#                   with APPLE_ID, APPLE_TEAM_ID and APPLE_APP_PASSWORD, notarized
set -euo pipefail
IN="$1"; ARCH="$2"; OUT="$3"
PKG="${OUT%.dmg}.pkg"
HERE="$(cd "$(dirname "$0")" && pwd)"
SIGN="$HERE/../../.github/scripts/mac-sign.sh"
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

if [ "${SIGN_APPS:-}" = true ]; then
  # The Developer ID: an app built before the certificates existed is signed here.
  for app in "$STAGE"/*.app; do
    "$SIGN" app --keep-signed "$app"
  done
else
  # Unsigned builds still need an ad-hoc signature to run on Apple Silicon.
  for app in "$STAGE"/*.app; do
    codesign --verify "$app" 2>/dev/null || codesign --force --deep --sign - "$app"
  done
fi

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
if [ "${SIGN_PKG:-}" = true ]; then
  "$SIGN" pkg "$PKG"
  "$SIGN" notarize "$PKG"  # Apple checks every app inside too; the ticket is stapled to the .pkg
fi
echo "Built $PKG"

# The same installer in a disk image, for the download links that point at the .dmg. The image
# itself stays unsigned: the installer in it carries the signature and Apple's ticket.
DMG_STAGE="$WORK/Limitless Sound"
mkdir -p "$DMG_STAGE"
cp "$PKG" "$DMG_STAGE/Install Limitless Sound.pkg"
cp "$HERE/READ-ME-FIRST.txt" "$DMG_STAGE/"
retry hdiutil create -volname "Limitless Sound" -srcfolder "$DMG_STAGE" -ov -format UDZO "$OUT"
echo "Built $OUT"
