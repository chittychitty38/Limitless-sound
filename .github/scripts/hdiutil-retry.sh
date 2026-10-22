#!/bin/bash
# hdiutil, tried again when the Mac says the disk image is busy ("Resource busy"): on
# GitHub's Mac runners a background scan sometimes holds the new image for a few seconds.
#   .github/scripts/hdiutil-retry.sh create -volname ... -srcfolder ... out.dmg
for n in 1 2 3 4; do
  hdiutil "$@" && exit 0
  echo "hdiutil $1 failed (try $n), trying again in $((n * 5)) s"
  sleep $((n * 5))
done
exec hdiutil "$@"
