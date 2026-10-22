#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""A pull request that moves vcpkg.json's builtin-baseline must name a commit that the
organisation's vcpkg fork has on its master branch, because CI and developers check the
baseline out from the fork (standard section 4.2). Dependabot bumps point at upstream
commits; this check fails until the fork's sync workflow has brought that commit over.

A fork shares its objects with its parent, so GitHub's commit lookup answers yes for an
upstream commit the fork has not synced. The check therefore asks whether the commit is an
ancestor of the fork's master (the compare API reports "ahead" or "identical").

    check_vcpkg_baseline_in_fork.py --base <ref> [--fork iainchesworthlabs/vcpkg] [--branch master]

Uses GH_TOKEN when set (rate limits), otherwise anonymous. Exit 0 when the baseline is
unchanged or present in the fork.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def baseline_at(ref: str) -> str | None:
    res = subprocess.run(["git", "show", f"{ref}:vcpkg.json"], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return None
    return json.loads(res.stdout).get("builtin-baseline")


def commit_in_fork(fork: str, sha: str, branch: str = "master") -> bool:
    req = urllib.request.Request(f"https://api.github.com/repos/{fork}/compare/{sha}...{branch}",
                                 headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp).get("status") in ("ahead", "identical")
    except urllib.error.HTTPError as e:
        if e.code in (404, 422):
            return False
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--fork", default="iainchesworthlabs/vcpkg")
    ap.add_argument("--branch", default="master")
    args = ap.parse_args(argv)
    before, after = baseline_at(args.base), baseline_at(args.head)
    if after is None or before == after:
        print("builtin-baseline unchanged")
        return 0
    if commit_in_fork(args.fork, after, args.branch):
        print(f"baseline {after[:12]} is on {args.fork} {args.branch}")
        return 0
    print(f"baseline {after} is not on {args.fork} {args.branch}. Run the fork's sync workflow, then re-run this check.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
