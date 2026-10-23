#!/bin/bash
# Signs the Mac apps and the suite installer with the project's Apple Developer ID certificates,
# and has Apple notarize them. SIGNING.md says how to set it up. The workflows call this only
# when the Apple secrets exist; without them every build stays as it was.
#
#   mac-sign.sh keychain                 put the certificates from the secrets in a keychain of
#                                        their own (once per job, before the others)
#   mac-sign.sh app [--keep-signed] X.app
#                                        sign an app inside out with the Developer ID Application
#                                        certificate, the hardened runtime, a timestamp and the
#                                        app's entitlements (the table below), then check it.
#                                        --keep-signed leaves an app already signed this way as it is.
#   mac-sign.sh verify X.app             check every program and library in an app is signed the
#                                        way notarization needs
#   mac-sign.sh notarize FILE            have Apple notarize an .app, .pkg, .dmg or .zip and staple
#                                        the ticket to it; skipped, with a note, without APPLE_ID
#   mac-sign.sh pkg X.pkg                sign an installer package with the Developer ID Installer
#                                        certificate (an app certificate can't sign a .pkg)
#   mac-sign.sh cleanup                  delete the keychain
#
# Reads these environment variables, named like the repository secrets:
#   APPLE_CERT_P12, APPLE_CERT_PASSWORD, APPLE_SIGNING_IDENTITY        Developer ID Application (apps)
#   APPLE_INSTALLER_CERT_P12, APPLE_INSTALLER_CERT_PASSWORD, APPLE_INSTALLER_IDENTITY
#                                                                      Developer ID Installer (.pkg)
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD                        notarization
# A *_P12 is the .p12 file in base64. An *_IDENTITY is the certificate's name, like
# "Developer ID Application: Name (TEAMID)"; left empty, the one in the .p12 is used.
set -euo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
ROOT="$(cd "$(dirname "$SELF")/../.." && pwd)"
STATE_DIR="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/limitless-signing"
STATE="$STATE_DIR/state"
JOBS="${MAC_SIGN_JOBS:-8}"

# Each app's entitlements, by bundle identifier, from the repository root. The hardened runtime
# that notarization requires turns off what these turn back on:
#   PyInstaller apps (Python): com.apple.security.cs.allow-unsigned-executable-memory, for the
#     callbacks Python's ctypes and PyObjC build at run time (pynput's key and mouse taps, Qt),
#     and com.apple.security.cs.disable-library-validation, so Python can load its extension
#     modules and Qt plug-ins. Plus the microphone (device.audio-input) for Voice and Zoom, and
#     Apple Events (automation.apple-events) for Voice, which clicks menu items through System Events.
#   GazeStage (Electron): allow-jit and allow-unsigned-executable-memory for V8 and
#     disable-library-validation (electron-builder's own defaults), plus the camera and microphone.
#   Limitless Color (Tauri, Rust and Swift): none. Screen Recording is a permission, not an entitlement.
entitlements_for() {  # <bundle identifier>
  case $1 in
    org.limitlesssound.voice) echo "apps/voice/installer/mac-entitlements.plist" ;;
    org.limitlesssound.zoom) echo "apps/zoom/packaging/mac-entitlements.plist" ;;
    org.limitlesssound.onehand) echo "apps/one-hand/mac-entitlements.plist" ;;
    org.limitlesssound.control) echo "apps/control/packaging/mac-entitlements.plist" ;;
    org.limitlesssound.hub) echo "shared/hub/packaging/mac-entitlements.plist" ;;
    org.limitlesssound.gazestage) echo "apps/gazestage/packaging/mac-entitlements.plist" ;;
    org.limitlesssound.color) echo "" ;;
    *) return 1 ;;
  esac
}

die() { echo "::error title=Signing::$*" >&2; exit 1; }
note() { echo "$*"; [ -z "${GITHUB_ACTIONS:-}" ] || echo "::notice title=Signing::$*"; }

load_state() {
  KEYCHAIN="" APP_IDENTITY="" APP_NAME="" PKG_IDENTITY="" PKG_NAME=""
  # shellcheck disable=SC1090
  [ -f "$STATE" ] && . "$STATE"
  return 0
}

need_app_identity() {
  load_state
  [ -n "$APP_IDENTITY" ] || die "No Developer ID Application certificate: run 'mac-sign.sh keychain' with APPLE_CERT_P12 set first"
}

# ---- keychain ------------------------------------------------------------------------------

identities() {  # <keychain>: "HASH name" for each signing identity in it, valid or not
  security find-identity -p basic "$1" | sed -nE 's/^ *[0-9]+\) ([0-9A-Fa-f]{40}) "(.*)".*$/\1 \2/p' | sort -u
}

import_p12() {  # <base64> <password> <secret name> <keychain>
  local file="$STATE_DIR/$3.p12" out
  printf '%s' "$1" | tr -d ' \r\n\t' | base64 --decode > "$file" 2>/dev/null \
    || die "$3 isn't base64. Make it with: base64 -i certificate.p12 | pbcopy"
  if ! out=$(security import "$file" -k "$4" -f pkcs12 -P "$2" -T /usr/bin/codesign -T /usr/bin/productsign 2>&1); then
    rm -f "$file"
    case $out in
      *"already exists"*) echo "  (its certificate was already in the keychain)" ;;
      *) die "Couldn't open $3 with the password in ${3%_P12}_PASSWORD: $out" ;;
    esac
  fi
  rm -f "$file"
}

pick_identity() {  # <candidates "HASH name"> <wanted name or hash> <expected prefix> <secret name>
  local candidates=$1 wanted=$2 prefix=$3 secret=$4 hash name n names
  names=$(sed -E 's/^[^ ]+ //; s/.*/"&"/' <<<"$candidates" | paste -sd, - | sed 's/,/, /g')
  if [ -n "$wanted" ]; then
    while read -r hash name; do
      if [ "$name" = "$wanted" ] || [ "$(tr a-f A-F <<<"$hash")" = "$(tr a-f A-F <<<"$wanted")" ]; then
        echo "$hash $name"
        return
      fi
    done <<<"$candidates"
    die "$secret is \"$wanted\", but the certificate holds $names. Copy that name, exactly, into the $secret secret."
  fi
  n=$(grep -c . <<<"$candidates" || true)
  if [ "$n" = 1 ]; then echo "$candidates"; return; fi
  if [ "$(grep -c " $prefix:" <<<"$candidates" || true)" = 1 ]; then grep " $prefix:" <<<"$candidates"; return; fi
  die "The certificates hold $names. Put the one to use in the $secret secret."
}

make_keychain() {
  [ -n "${APPLE_CERT_P12:-}${APPLE_INSTALLER_CERT_P12:-}" ] || die "Neither APPLE_CERT_P12 nor APPLE_INSTALLER_CERT_P12 is set"
  local kc="$STATE_DIR/signing.keychain-db" password before after list=() line cer chosen
  local app_identity="" app_name="" pkg_identity="" pkg_name=""
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  password=$(uuidgen)$(uuidgen)
  security delete-keychain "$kc" 2>/dev/null || true
  security create-keychain -p "$password" "$kc"
  security set-keychain-settings -lut 21600 "$kc"  # stays unlocked for 6 hours, the longest job
  security unlock-keychain -p "$password" "$kc"
  # codesign and productsign only find identities in keychains on the search list.
  while IFS= read -r line; do
    line=${line#*\"}; line=${line%\"*}
    [ -n "$line" ] && [ "$line" != "$kc" ] && list+=("$line")
  done < <(security list-keychains -d user)
  security list-keychains -d user -s "$kc" ${list[@]+"${list[@]}"}
  # Apple's intermediate certificates link a Developer ID certificate to Apple's root (a .p12
  # exported from Keychain Access usually leaves them out).
  for cer in DeveloperIDG2CA.cer DeveloperIDCA.cer; do
    if curl -sSfL --retry 3 -o "$STATE_DIR/$cer" "https://www.apple.com/certificateauthority/$cer"; then
      security import "$STATE_DIR/$cer" -k "$kc" >/dev/null 2>&1 || true
    else
      echo "::warning title=Signing::Couldn't download Apple's $cer; signing relies on the Mac having it"
    fi
  done

  if [ -n "${APPLE_CERT_P12:-}" ]; then
    echo "Developer ID Application certificate (APPLE_CERT_P12):"
    before=$(identities "$kc")
    import_p12 "$APPLE_CERT_P12" "${APPLE_CERT_PASSWORD:-}" APPLE_CERT_P12 "$kc"
    after=$(comm -13 <(echo "$before") <(identities "$kc"))
    [ -n "$after" ] || after=$(identities "$kc")
    [ -n "$after" ] || die "APPLE_CERT_P12 holds no signing identity. Export the certificate together with its private key (in Keychain Access, open the certificate's arrow and select both)."
    chosen=$(pick_identity "$after" "${APPLE_SIGNING_IDENTITY:-}" "Developer ID Application" APPLE_SIGNING_IDENTITY)
    app_identity=${chosen%% *}; app_name=${chosen#* }
    echo "  $app_name ($app_identity)"
  fi
  if [ -n "${APPLE_INSTALLER_CERT_P12:-}" ]; then
    echo "Developer ID Installer certificate (APPLE_INSTALLER_CERT_P12):"
    before=$(identities "$kc")
    import_p12 "$APPLE_INSTALLER_CERT_P12" "${APPLE_INSTALLER_CERT_PASSWORD:-}" APPLE_INSTALLER_CERT_P12 "$kc"
    after=$(comm -13 <(echo "$before") <(identities "$kc"))
    # The same .p12 can hold both certificates: then choose among everything in the keychain.
    [ -n "$after" ] || after=$(identities "$kc" | grep -v "^$app_identity " || true)
    [ -n "$after" ] || after=$(identities "$kc")
    chosen=$(pick_identity "$after" "${APPLE_INSTALLER_IDENTITY:-}" "Developer ID Installer" APPLE_INSTALLER_IDENTITY)
    pkg_identity=${chosen%% *}; pkg_name=${chosen#* }
    echo "  $pkg_name ($pkg_identity)"
  fi
  # Lets codesign and productsign use the keys without a password prompt.
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$password" "$kc" >/dev/null
  {
    printf 'KEYCHAIN=%q\n' "$kc"
    printf 'APP_IDENTITY=%q\nAPP_NAME=%q\n' "$app_identity" "$app_name"
    printf 'PKG_IDENTITY=%q\nPKG_NAME=%q\n' "$pkg_identity" "$pkg_name"
  } > "$STATE"
  echo "Keychain ready: $kc"
}

cleanup() {
  load_state
  [ -n "$KEYCHAIN" ] && security delete-keychain "$KEYCHAIN" 2>/dev/null || true
  rm -rf "$STATE_DIR"
}

# ---- apps ----------------------------------------------------------------------------------

# Lists what's inside an app, for signing inside out: <out>/exe and <out>/lib (every Mach-O
# program and library, NUL-separated) and <out>/bundles (nested bundles, deepest first).
scan() {  # <app> <out dir>
  python3 - "$1" "$2" <<'PY'
import os, struct, sys

app, out = sys.argv[1], sys.argv[2]
THIN = {b'\xcf\xfa\xed\xfe': '<', b'\xce\xfa\xed\xfe': '<', b'\xfe\xed\xfa\xcf': '>', b'\xfe\xed\xfa\xce': '>'}
SIGNABLE = {2: 'exe', 6: 'lib', 8: 'lib'}  # MH_EXECUTE, MH_DYLIB, MH_BUNDLE (Python's .so files)
NESTED = ('.app', '.framework', '.appex', '.xpc', '.bundle', '.plugin')


def macho(path):
    """'exe', 'lib' or None, from the file's Mach-O header."""
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
            if head[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):  # universal binary
                count = struct.unpack('>I', head[4:8])[0]
                if not 0 < count < 32:  # a Java class file starts the same way
                    return None
                wide = head[3] == 0xbf
                offset = struct.unpack('>Q', head[16:24])[0] if wide else struct.unpack('>I', head[16:20])[0]
                f.seek(offset)
                head = f.read(32)
    except OSError:
        return None
    if len(head) < 16 or head[:4] not in THIN:
        return None
    return SIGNABLE.get(struct.unpack(THIN[head[:4]] + 'I', head[12:16])[0])


def is_bundle(path):
    if path.endswith('.framework'):
        return os.path.isfile(os.path.join(path, 'Resources', 'Info.plist'))
    return os.path.isfile(os.path.join(path, 'Contents', 'Info.plist'))


found = {'exe': [], 'lib': []}
bundles = []
for folder, dirs, files in os.walk(app):
    for name in dirs:
        path = os.path.join(folder, name)
        if name.endswith(NESTED) and not os.path.islink(path):
            if is_bundle(path):
                bundles.append(path)
            else:
                print(f'  {os.path.relpath(path, app)} has no Info.plist: signing what is in it file by file')
    for name in files:
        path = os.path.join(folder, name)
        kind = None if os.path.islink(path) else macho(path)
        if kind:
            found[kind].append(path)
bundles.sort(key=lambda p: p.count(os.sep), reverse=True)
for kind, paths in (('exe', found['exe']), ('lib', found['lib']), ('bundles', bundles)):
    with open(os.path.join(out, kind), 'w') as f:
        f.write(''.join(p + '\0' for p in paths))
print(f"  {len(found['exe'])} programs, {len(found['lib'])} libraries, {len(bundles)} nested bundles")
PY
}

sign_one() {  # <entitlements or ""> <path>: codesign, tried again when the timestamp server fails
  local ent=$1 path=$2 out n
  local args=(--force --sign "$APP_IDENTITY" --keychain "$KEYCHAIN" --options runtime --timestamp)
  [ -n "$ent" ] && args+=(--entitlements "$ent")
  for n in 1 2 3 4; do
    out=$(codesign "${args[@]}" "$path" 2>&1) && return 0
    echo "  codesign failed on ${path#"$ROOT"/} (try $n): $out" >&2
    sleep $((n * 3))
  done
  return 1
}

signed_by_us() {  # <app>: valid, hardened, timestamped and signed with our certificate already?
  local info
  codesign --verify --deep --strict "$1" 2>/dev/null || return 1
  info=$(codesign -dvv "$1" 2>&1) || return 1
  grep -qxF "Authority=$APP_NAME" <<<"$info" && grep -q '^CodeDirectory .*flags=.*runtime' <<<"$info" &&
    grep -q '^Timestamp=' <<<"$info"
}

sign_app() {
  local keep="" app id ent work name
  if [ "${1:-}" = --keep-signed ]; then keep=1; shift; fi
  app=${1:?usage: mac-sign.sh app [--keep-signed] X.app}
  app=${app%/}
  [ -f "$app/Contents/Info.plist" ] || die "$app isn't an app"
  need_app_identity
  name=$(basename "$app")
  id=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$app/Contents/Info.plist")
  ent=$(entitlements_for "$id") || die "$name ($id) has no line in the entitlements table in .github/scripts/mac-sign.sh: add one"
  [ -z "$ent" ] || ent="$ROOT/$ent"
  [ -z "$ent" ] || [ -f "$ent" ] || die "$name's entitlements file $ent is missing"
  if [ -n "$keep" ] && signed_by_us "$app"; then
    echo "$name: already signed with $APP_NAME and the hardened runtime; kept as it is"
    return 0
  fi
  echo "Signing $name ($id) with $APP_NAME${ent:+, entitlements ${ent#"$ROOT"/}}"
  xattr -cr "$app"  # Finder information and the like make codesign refuse a file
  work=$(mktemp -d)
  scan "$app" "$work"
  export -f sign_one
  export APP_IDENTITY KEYCHAIN ROOT
  # Programs and libraries first, then the bundles holding them (deepest first), the app last.
  SIGN_ENT=$ent xargs -0 -n 1 -P "$JOBS" bash -c 'sign_one "$SIGN_ENT" "$1"' _ < "$work/exe"
  SIGN_ENT="" xargs -0 -n 1 -P "$JOBS" bash -c 'sign_one "$SIGN_ENT" "$1"' _ < "$work/lib"
  while IFS= read -r -d '' b; do
    case $b in
      *.app | *.appex | *.xpc) sign_one "$ent" "$b" ;;  # a helper process: same entitlements
      *) sign_one "" "$b" ;;
    esac
  done < "$work/bundles"
  sign_one "$ent" "$app"
  rm -rf "$work"
  verify "$app"
}

# Everything notarization checks: a valid signature all through, and every program and library
# signed with the same certificate, with the hardened runtime and a secure timestamp.
verify() {
  local app=${1:?usage: mac-sign.sh verify X.app} work authority info path bad=0 count=0
  app=${app%/}
  codesign --verify --deep --strict --verbose=2 "$app"
  info=$(codesign -dvv "$app" 2>&1)
  authority=$(sed -n 's/^Authority=//p' <<<"$info" | head -1)
  [ -n "$authority" ] || die "$(basename "$app") is ad-hoc signed, not signed with a certificate"
  work=$(mktemp -d)
  scan "$app" "$work" >/dev/null
  while IFS= read -r -d '' path; do
    count=$((count + 1))
    info=$(codesign -dvv "$path" 2>&1) || { echo "  not signed: ${path#"$app"/}"; bad=1; continue; }
    grep -qxF "Authority=$authority" <<<"$info" || { echo "  signed by someone else: ${path#"$app"/}"; bad=1; }
    grep -q '^CodeDirectory .*flags=.*runtime' <<<"$info" || { echo "  no hardened runtime: ${path#"$app"/}"; bad=1; }
    grep -q '^Timestamp=' <<<"$info" || { echo "  no secure timestamp: ${path#"$app"/}"; bad=1; }
  done < <(cat "$work/exe" "$work/lib" "$work/bundles"; printf '%s\0' "$app")
  rm -rf "$work"
  [ "$bad" = 0 ] || die "$(basename "$app") isn't signed the way notarization needs (above)"
  info=$(codesign -dvv "$app" 2>&1)
  echo "$(basename "$app"): $count signatures checked, all by $authority, hardened, timestamped"
  grep -E '^(Identifier|TeamIdentifier|Timestamp)=' <<<"$info" | sed 's/^/  /'
  codesign -d --entitlements - "$app" 2>/dev/null | grep -Eo 'com\.apple\.[a-z.-]+' | sed 's/^/  entitlement: /' || true
}

# ---- installer and notarization -------------------------------------------------------------

sign_pkg() {
  local pkg=${1:?usage: mac-sign.sh pkg X.pkg} tmp check
  load_state
  [ -n "$PKG_NAME" ] || die "No Developer ID Installer certificate: run 'mac-sign.sh keychain' with APPLE_INSTALLER_CERT_P12 set first"
  echo "Signing $(basename "$pkg") with $PKG_NAME ($PKG_IDENTITY)"
  tmp="${pkg%.pkg}.unsigned.pkg"
  mv -f "$pkg" "$tmp"
  productsign --sign "$PKG_NAME" --keychain "$KEYCHAIN" --timestamp "$tmp" "$pkg"
  rm -f "$tmp"
  check=$(pkgutil --check-signature "$pkg")
  echo "$check"
  grep -q "Status: signed" <<<"$check" || die "$(basename "$pkg") isn't signed after productsign"
}

notarize() {
  local file=${1:?usage: mac-sign.sh notarize FILE} upload out status id n
  file=${file%/}
  if [ -z "${APPLE_ID:-}" ]; then
    note "Notarization skipped for $(basename "$file"): APPLE_ID isn't set. It is signed, but a Mac will still ask before opening it until it's notarized."
    return 0
  fi
  [ -n "${APPLE_TEAM_ID:-}" ] || die "APPLE_ID is set but APPLE_TEAM_ID isn't"
  [ -n "${APPLE_APP_PASSWORD:-}" ] || die "APPLE_ID is set but APPLE_APP_PASSWORD (the app-specific password) isn't"
  case $file in
    *.app) upload="$(mktemp -d)/$(basename "$file" .app).zip"; ditto -c -k --keepParent "$file" "$upload" ;;
    *.pkg | *.dmg | *.zip) upload=$file ;;
    *) die "Can't notarize $file: give an .app, .pkg, .dmg or .zip" ;;
  esac
  echo "Sending $(basename "$file") to Apple for notarization (this usually takes a few minutes)"
  id="" status=""
  for n in 1 2 3; do
    out=$(xcrun notarytool submit "$upload" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" \
      --password "$APPLE_APP_PASSWORD" --wait --output-format json 2>&1) || true
    # The answer's last JSON line has the submission's id and status.
    read -r id status < <(python3 -c '
import json, sys
for line in reversed(sys.stdin.read().splitlines()):
    try:
        answer = json.loads(line)
    except ValueError:
        continue
    if isinstance(answer, dict) and answer.get("id"):
        print(answer["id"], answer.get("status", "").replace(" ", "_"))
        break
' <<<"$out") || true
    [ -n "$id" ] && break
    echo "  the upload didn't go through (try $n): $out"
    sleep $((n * 20))
  done
  [ -n "$id" ] || die "Couldn't send $(basename "$file") to Apple: $out"
  echo "  $status ($id)"
  if [ "$status" != Accepted ]; then
    xcrun notarytool log "$id" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_PASSWORD" || true
    die "Apple didn't notarize $(basename "$file"): $status. Apple's reasons are just above."
  fi
  [ "$upload" = "$file" ] && [ "${file%.zip}" != "$file" ] && return 0  # a .zip can't hold a ticket
  for n in 1 2 3 4 5; do  # the ticket can take a moment to reach Apple's servers
    xcrun stapler staple "$file" && break
    [ "$n" = 5 ] && die "Couldn't staple the ticket to $(basename "$file")"
    sleep $((n * 10))
  done
  xcrun stapler validate "$file"
}

case ${1:-} in
  keychain) make_keychain ;;
  app) shift; sign_app "$@" ;;
  verify) shift; load_state; verify "$@" ;;
  notarize) shift; notarize "$@" ;;
  pkg) shift; sign_pkg "$@" ;;
  cleanup) cleanup ;;
  *) sed -n '2,29p' "$SELF" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
