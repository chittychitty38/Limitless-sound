#!/usr/bin/env bash
# Downloads every app's newest successful build on main for one platform, for the suite:
#
#   .github/scripts/newest-builds.sh <platform> <folder> [--list]
#
# <platform> is the end of the build's artifact name: mac-apple-silicon, mac-intel or windows.
# --list only prints what it would download. Stops with an error if any app has no build, so
# a suite is never made with an app missing.
#
# Runs are listed unfiltered and chosen here. GitHub's runs API sometimes answers a branch= or
# status= query with no runs at all (on 2026-10-22 the same query gave 6 runs, then 0), which
# once left Limitless Sound and four apps out of a suite build.
set -euo pipefail

platform=$1
out=$2
list_only=${3:-}
repo=${GITHUB_REPOSITORY:?}

api() {  # gh api, asked again after a network hiccup
  local i
  for i in 1 2 3; do
    gh api "$@" && return 0
    sleep $((i * 5))
  done
  return 1
}

# The same build from the app's release, for when GitHub's artifact storage refuses a download
# for a while ("HTTP 503: Egress is over the account limit": on 2026-10-23 it held Control's
# builds back for over an hour). An app's release is made by the run that built it, from these
# same files, at that run's commit. A build with no release (no new version) has no fallback.
from_release() {  # <workflow> <run> <folder>
  local prefix=${1%.yml}-v sha tag page files id name file
  local wanted
  case $platform in
    mac-apple-silicon) wanted='(mac-apple-silicon|mac-arm64)\\.dmg$' ;;
    mac-intel) wanted='(mac-intel|mac-x64)\\.dmg$' ;;
    windows) wanted='\\.exe$' ;;
    *) return 1 ;;
  esac
  sha=$(api "repos/$repo/actions/runs/$2" -q .head_sha) || return 1
  for page in 1 2 3; do
    tag=$(api "repos/$repo/releases?per_page=100&page=$page" -q "[.[] | select((.tag_name | startswith(\"$prefix\"))
      and .target_commitish == \"$sha\") | .tag_name] | first // empty") || return 1
    [ -n "$tag" ] && break
  done
  [ -n "$tag" ] || return 1
  files=$(api "repos/$repo/releases/tags/$tag" -q ".assets[] | select(.name | test(\"$wanted\")) | \"\\(.id) \\(.name)\"") || return 1
  [ -n "$files" ] || return 1
  echo "  its build couldn't be downloaded; taking the same files from its release $tag"
  mkdir -p "$3"
  while read -r id name; do
    file="$3/$name"
    gh api -H "Accept: application/octet-stream" "repos/$repo/releases/assets/$id" > "$file" || return 1
    echo "  $name: $(wc -c < "$file") bytes"
  done <<<"$files"
}

# A build with no release to take it from (Limitless Sound itself releases only on a hub-v tag):
# the storage's refusals have passed within minutes before, so ask again a few times.
download_again() {  # <run> <artifact name> <folder>
  local wait
  for wait in 30 60 120; do
    echo "  asking for $2 again in ${wait}s"
    sleep "$wait"
    rm -rf "${3:?}"
    gh run download "$1" -R "$repo" -n "$2" -D "$3" && return 0
  done
  return 1
}

mkdir -p "$out"
for wf in shared.yml voice.yml one-hand.yml zoom.yml color.yml control.yml gazestage.yml; do
  found=""
  for page in 1 2 3 4 5; do
    # Newest first: this repository's own pushes to main (and manual runs) that succeeded,
    # then "end" when this was the last page.
    runs=$(api "repos/$repo/actions/workflows/$wf/runs?per_page=100&page=$page" -q "
      (.workflow_runs[]
        | select(.head_branch == \"main\" and (.event == \"push\" or .event == \"workflow_dispatch\")
                 and (.head_repository.full_name | ascii_downcase) == (\"$repo\" | ascii_downcase)
                 and .conclusion == \"success\")
        | .id),
      (if (.workflow_runs | length) < 100 then \"end\" else empty end)")
    for run in $runs; do
      [ "$run" = end ] && break 2
      name=$(api "repos/$repo/actions/runs/$run/artifacts?per_page=100" -q \
        "[.artifacts[] | select((.expired | not) and (.name | endswith(\"-$platform\"))) | .name] | first // empty")
      if [ -n "$name" ]; then
        found="$run $name"
        break 2
      fi
    done
  done
  if [ -z "$found" ]; then
    echo "::error::No successful $wf build on main has a $platform download"
    exit 1
  fi
  read -r run name <<<"$found"
  echo "$wf: $name (run $run)"
  [ "$list_only" = --list ] && continue
  if ! gh run download "$run" -R "$repo" -n "$name" -D "$out/$wf"; then
    rm -rf "${out:?}/$wf"
    if ! from_release "$wf" "$run" "$out/$wf" && ! download_again "$run" "$name" "$out/$wf"; then
      echo "::error::Couldn't download $name (run $run) after asking four times, and it has no release to take it from"
      exit 1
    fi
  fi
done
