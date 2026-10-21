#!/bin/bash
# Installs every Limitless Sound app into Applications, lets macOS open them,
# and starts Limitless Sound so the apps work together.
set -u
cd "$(dirname "$0")" || exit 1
clear
echo "Installing Limitless Sound…"
echo
installed=()
for app in *.app; do
  [ -d "$app" ] || continue
  echo "  • ${app%.app}"
  rm -rf "/Applications/$app"
  if ! ditto "$app" "/Applications/$app"; then
    echo "    Couldn't copy it. Drag it into Applications yourself."
    continue
  fi
  # These apps aren't signed by Apple yet. This removes the "can't be checked" block
  # for the copies installed here, so each one opens with a normal double-click.
  xattr -dr com.apple.quarantine "/Applications/$app" 2>/dev/null
  installed+=("$app")
done
echo
if [ -d "/Applications/Limitless Sound.app" ]; then
  "/Applications/Limitless Sound.app/Contents/MacOS/Limitless Sound" autostart on >/dev/null 2>&1
  open "/Applications/Limitless Sound.app"
fi
echo "Done: ${#installed[@]} apps are in Applications."
echo "Limitless Sound is open in your web browser, and starts by itself when you sign in."
echo "Each app asks for its permissions (Microphone, Camera, Accessibility) the first time."
say "Limitless Sound is installed." 2>/dev/null &
echo
echo "You can close this window."
