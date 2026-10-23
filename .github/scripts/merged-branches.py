#!/usr/bin/env python3
"""Deletes the branches whose pull request was merged and that have no commits since, and lists
every branch it keeps and why. Uses the gh command line (GH_TOKEN, REPO=owner/name).

Kept whatever happens: the default branch, gh-pages, the proof's results, zoom-view-control (the
old default), and any branch never merged, with an open pull request, or with commits added
after its merge.

  merged-branches.py            delete
  merged-branches.py --dry-run  only list
"""
import json
import os
import subprocess
import sys

KEEP = {"main", "gh-pages", "proof-results", "proof-results-test", "zoom-view-control"}


def api(path, *args):
    out = subprocess.run(["gh", "api", *args, path], check=True, capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else None


def every(path):
    """All pages of a list (gh's own --paginate follows links some proxies refuse)."""
    items, page = [], 1
    while True:
        batch = api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        items += batch
        if len(batch) < 100:
            return items
        page += 1


def sort(repo, branches, prs, default):
    """(to delete: [(branch, pr number)], to keep: [(branch, why)])."""
    keep_always = KEEP | {default}
    ours = [p for p in prs if (p["head"]["repo"] or {}).get("full_name") == repo]
    delete, keep = [], []
    for b in sorted(branches, key=lambda b: b["name"]):
        name, sha = b["name"], b["commit"]["sha"]
        its = [p for p in ours if p["head"]["ref"] == name]
        merged = [p for p in its if p["merged_at"]]
        if name in keep_always:
            keep.append((name, "kept on purpose"))
        elif any(p["state"] == "open" for p in its):
            keep.append((name, "has an open pull request"))
        elif not merged:
            keep.append((name, "never merged"))
        elif not any(p["head"]["sha"] == sha for p in merged):
            keep.append((name, "has commits after its merge"))
        else:
            delete.append((name, max(p["number"] for p in merged if p["head"]["sha"] == sha)))
    return delete, keep


def main(argv):
    dry = "--dry-run" in argv
    repo = os.environ["REPO"]
    default = api(f"repos/{repo}")["default_branch"]
    delete, keep = sort(repo, every(f"repos/{repo}/branches"), every(f"repos/{repo}/pulls?state=all"), default)
    print(f"Keeping {len(keep)}:")
    for name, why in keep:
        print(f"  {name}: {why}")
    print(f"\n{'Would delete' if dry else 'Deleting'} {len(delete)}, each merged as it stands:")
    failed = 0
    for name, pr in delete:
        if dry:
            print(f"  {name} (#{pr})")
            continue
        try:
            api(f"repos/{repo}/git/refs/heads/{name}", "-X", "DELETE")
            print(f"  deleted {name} (#{pr})")
        except subprocess.CalledProcessError as e:
            failed += 1
            print(f"  couldn't delete {name} (#{pr}): {e.stderr.strip()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
