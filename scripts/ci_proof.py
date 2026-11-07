#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the proof of a CI run (docs/ci-many-agents.md section 3.2).

    ci_proof.py --needs "$NEEDS_JSON" --out ci-proof.json [--config .github/ci/plan.json]
                [--reused "$REUSED_JSON"] [--root .]

The run's identity comes from the arguments, defaulting to the GitHub environment:
GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT, GITHUB_EVENT_NAME and GITHUB_SHA (the tested
commit). --head-sha and --base-sha are the pull request's head and base (or the merge group's base).

The file holds the result of each group job from toJSON(needs), the object id of every barrier path
at the tested commit, and the groups this run reused rather than ran (always the original run).
It holds no secrets: artifacts of a public repository are public. It is a convenience, not the
evidence: the finder reads the conclusions again from the Actions API and uses the file only for the
tested commit of a pull request run.

It runs only infra code and reads object ids with `git rev-parse`; it executes nothing from the tree.
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

SCHEMA = 1


def rev_parse(root: str, commit: str, path: str) -> str | None:
    """Object id of `path` at `commit`, or None when it does not exist there."""
    res = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "--quiet", f"{commit}:{path}"],
                         capture_output=True, text=True, check=False)
    return res.stdout.strip() or None if res.returncode == 0 else None


def build_proof(*, repository: str, run_id: str, run_attempt: str, event: str, tested_sha: str,
                head_sha: str, base_sha: str, needs: dict, cfg: dict, reused: dict | None = None,
                object_id=rev_parse, root: str = ".") -> dict:
    groups_cfg = cfg.get("groups") or {}
    groups = {}
    for job, info in sorted(needs.items()):
        if job not in groups_cfg:
            continue
        entry = {"result": info.get("result", "")}
        if groups_cfg[job].get("jobs"):
            entry["legs"] = list(groups_cfg[job]["jobs"])
        groups[job] = entry
    barrier = {path: object_id(root, tested_sha, path) for path in plan_gate.reuse_config(cfg)["barrier"]}
    return {
        "schema": SCHEMA,
        "repository": repository,
        "run_id": int(run_id) if str(run_id).isdigit() else run_id,
        "run_attempt": int(run_attempt) if str(run_attempt).isdigit() else run_attempt,
        "event": event,
        "tested_sha": tested_sha,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "barrier": barrier,
        "groups": groups,
        "reused": reused or {},
    }


def main(argv=None) -> int:
    env = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--needs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config")
    ap.add_argument("--reused", default="")
    ap.add_argument("--root", default=".")
    ap.add_argument("--repository", default=env("GITHUB_REPOSITORY", ""))
    ap.add_argument("--run-id", default=env("GITHUB_RUN_ID", ""))
    ap.add_argument("--run-attempt", default=env("GITHUB_RUN_ATTEMPT", "1"))
    ap.add_argument("--event", default=env("GITHUB_EVENT_NAME", ""))
    ap.add_argument("--tested-sha", default=env("GITHUB_SHA", ""))
    ap.add_argument("--head-sha", default="")
    ap.add_argument("--base-sha", default="")
    args = ap.parse_args(argv)

    cfg = dict(plan_gate.DEFAULT)
    if args.config and Path(args.config).exists():
        cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    reused = None
    if args.reused.strip():
        try:
            parsed = json.loads(args.reused)
            reused = parsed.get("reused", parsed) if isinstance(parsed, dict) else None
        except ValueError:
            print("::warning::ci_proof: the reused input is not JSON; recording none", file=sys.stderr)
    proof = build_proof(repository=args.repository, run_id=args.run_id, run_attempt=args.run_attempt,
                        event=args.event, tested_sha=args.tested_sha, head_sha=args.head_sha or args.tested_sha,
                        base_sha=args.base_sha, needs=json.loads(args.needs), cfg=cfg, reused=reused,
                        root=args.root)
    Path(args.out).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(proof['groups'])} group(s), {len(proof['reused'])} reused")
    return 0


if __name__ == "__main__":
    sys.exit(main())
