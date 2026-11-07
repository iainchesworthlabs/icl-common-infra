#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Move refs/ci/green/<group> to the commit a run proved (docs/ci-many-agents.md section 4.4).

    mark_green.py --needs "$NEEDS_JSON" --sha "$GITHUB_SHA" --plan-config .github/ci/plan.json
                  [--reused "$REUSED_JSON"] [--repo owner/name] [--dry-run]

A group is green on the pushed tree when its job succeeded, or when it was reused from a run whose
tree was identical (delta 0). Each green group's ref is created or moved forward, never back: a
ref moves only when the new commit is ahead of the old one. The post-merge failure report counts
the commits between a group's green ref and the commit that failed. The ref lives outside
refs/heads and refs/tags, so no branch or tag ruleset applies to it.

It writes refs and nothing else, takes `contents: write`, and never fails the job: an API error
is a warning and the group's ref stays where it was.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_gate  # noqa: E402

PREFIX = "refs/ci/green/"


class Gh:
    """The few GitHub REST calls the post-merge scripts make, through the gh CLI."""

    def __init__(self, repo: str):
        self.repo = repo

    def call(self, method: str, path: str, body: dict | None = None):
        cmd = ["gh", "api", "--method", method, f"repos/{self.repo}/{path}"]
        if body is not None:
            cmd += ["--input", "-"]
        res = subprocess.run(cmd, input=json.dumps(body) if body is not None else None, capture_output=True,
                             text=True, check=False)
        if res.returncode:
            raise RuntimeError(f"{method} {path}: {res.stderr.strip()[:300]}")
        return json.loads(res.stdout) if res.stdout.strip() else None


def green_groups(needs: dict, reused: dict, groups: list[str]) -> list[str]:
    green = []
    for g in groups:
        if needs.get(g, {}).get("result") == "success":
            green.append(g)
        elif isinstance(reused.get(g), dict) and reused[g].get("delta") == 0 and reused[g].get("kind") == "equal-tree":
            green.append(g)
    return sorted(green)


def mark(gh, group: str, sha: str, dry_run: bool = False) -> str:
    """Create or fast-forward the ref. Returns what happened."""
    ref = f"ci/green/{group}"
    try:
        current = gh.call("GET", f"git/ref/{ref}")["object"]["sha"]
    except RuntimeError as e:
        if "404" not in str(e) and "Not Found" not in str(e):
            raise
        current = None
    if current == sha:
        return "unchanged"
    if dry_run:
        return f"would move {current or 'nothing'} -> {sha}"
    if current is None:
        gh.call("POST", "git/refs", {"ref": PREFIX + group, "sha": sha})
        return "created"
    status = gh.call("GET", f"compare/{current}...{sha}")["status"]
    if status not in ("ahead",):
        return f"kept (new commit is {status} of the current one)"
    gh.call("PATCH", f"git/refs/{ref}", {"sha": sha, "force": False})
    return "moved"


def main(argv=None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--needs", required=True)
    ap.add_argument("--sha", default=env.get("GITHUB_SHA", ""))
    ap.add_argument("--plan-config", default=".github/ci/plan.json")
    ap.add_argument("--reused", default="")
    ap.add_argument("--repo", default=env.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    cfg = dict(plan_gate.DEFAULT)
    if Path(args.plan_config).exists():
        cfg.update(json.loads(Path(args.plan_config).read_text(encoding="utf-8")))
    needs = json.loads(args.needs)
    try:
        reused = json.loads(args.reused) if args.reused.strip() else {}
    except ValueError:
        reused = {}
    if needs.get("reuse", {}).get("result") != "success":
        reused = {}
    gh = Gh(args.repo)
    for group in green_groups(needs, reused if isinstance(reused, dict) else {}, sorted(cfg.get("groups") or {})):
        try:
            print(f"{group}: {mark(gh, group, args.sha, args.dry_run)}")
        except (RuntimeError, KeyError, ValueError) as e:
            print(f"::warning::could not move the green ref of {group}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
