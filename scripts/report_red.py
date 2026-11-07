#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Name the suspects when a group fails after a merge (docs/ci-many-agents.md section 4.4).

    report_red.py --needs "$NEEDS_JSON" --sha "$GITHUB_SHA" --run-id "$GITHUB_RUN_ID"
                  --plan-config .github/ci/plan.json [--reused "$REUSED_JSON"] [--dry-run]

For each group whose job failed, the commits between refs/ci/green/<group> and the failing commit
are the suspects (squash subjects end in `(#N)`, so each gives a pull request). One issue per
group, `main-red: <group>`, label `main-red`, is opened or updated with the failed jobs, the
suspects and whether the group had been reused for any of them; each suspect pull request gets one
comment. One suspect gets the revert command, several get a bisect recipe. Nothing is reverted and
nothing blocks the queue. A group that passes closes its issue.

Needs `issues: write` and `pull-requests: write`; it never fails the job.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mark_green  # noqa: E402
import plan_gate  # noqa: E402

LABEL = "main-red"
PR_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
MAX_SUSPECTS = 50


def title(group: str) -> str:
    return f"{LABEL}: {group}"


def suspects(gh, group: str, sha: str) -> tuple[list[dict], str]:
    """Commits after the group's green ref up to sha, oldest first, and a note when they are unknown."""
    try:
        green = gh.call("GET", f"git/ref/ci/green/{group}")["object"]["sha"]
    except RuntimeError:
        return [], "no green commit is recorded for this group yet, so the suspects are unknown"
    if green == sha:
        return [], "the group was green on this very commit before; this is a re-run"
    commits = gh.call("GET", f"compare/{green}...{sha}").get("commits", [])
    out = []
    for c in commits[-MAX_SUSPECTS:]:
        subject = c["commit"]["message"].splitlines()[0]
        m = PR_SUBJECT.search(subject)
        out.append({"sha": c["sha"], "subject": subject, "pr": int(m.group(1)) if m else None})
    return out, ""


def failed_jobs(gh, run_id: str, group: str, cfg: dict) -> list[str]:
    listed = (cfg.get("groups") or {}).get(group, {}).get("jobs") or []
    prefixes = {j.split(" / ", 1)[0] for j in listed}
    try:
        jobs = gh.call("GET", f"actions/runs/{run_id}/jobs?per_page=100")["jobs"]
    except (RuntimeError, KeyError):
        return []
    return [f"{j['name']} ({j['html_url']})" for j in jobs
            if j.get("conclusion") == "failure" and (not prefixes or j["name"].split(" / ", 1)[0] in prefixes)]


def recipe(group: str, found: list[dict]) -> str:
    if len(found) == 1:
        return f"One suspect. Revert it if it is the cause:\n\n    git revert {found[0]['sha']}"
    if not found:
        return ""
    mid = found[len(found) // 2]["sha"]
    return ("Several suspects. `workflow_dispatch` needs a branch, so bisect with one group per probe "
            f"(about {max(1, (len(found) - 1).bit_length())} probes):\n\n"
            f"    git push origin {mid}:refs/heads/agent/bisect-{group}-{mid[:7]}\n"
            f"    gh workflow run ci.yml --ref agent/bisect-{group}-{mid[:7]} -f groups={group}\n\n"
            "Green means the cause is after that commit, red means at or before it. Delete the branch afterwards.")


def body(group: str, sha: str, run_url: str, found: list[dict], note: str, jobs: list[str], reused) -> str:
    lines = [f"Group `{group}` failed on {sha} after a merge ([run]({run_url})).", ""]
    if jobs:
        lines += ["Failed jobs:", *[f"- {j}" for j in jobs], ""]
    if isinstance(reused, dict) and group in reused and isinstance(reused[group], dict):
        r = reused[group]
        lines += [f"This group was reused for this commit from run {r.get('run_id')} (tested {str(r.get('tested_sha', ''))[:8]}, "
                  f"{r.get('kind')}, delta {r.get('delta')}). If that run was green, this is a false reuse: "
                  "record it for the metrics and look at the skip tables.", ""]
    if found:
        lines += ["Suspects since the last green commit of this group, oldest first:"]
        lines += [f"- {c['sha'][:10]} {c['subject']}" for c in found]
        lines += ["", recipe(group, found)]
    elif note:
        lines += [note]
    lines += ["", "Opened by the post-merge run. Nothing is reverted or blocked automatically; the issue closes when the group next passes."]
    return "\n".join(lines)


def open_issue(gh, group: str) -> int | None:
    issues = gh.call("GET", f"issues?labels={LABEL}&state=open&per_page=100") or []
    for i in issues:
        if i["title"] == title(group) and "pull_request" not in i:
            return i["number"]
    return None


def report(gh, group: str, sha: str, run_id: str, cfg: dict, reused, dry_run: bool) -> str:
    run_url = f"https://github.com/{gh.repo}/actions/runs/{run_id}"
    found, note = suspects(gh, group, sha)
    text = body(group, sha, run_url, found, note, failed_jobs(gh, run_id, group, cfg), reused)
    if dry_run:
        return text
    try:
        gh.call("POST", "labels", {"name": LABEL, "color": "B60205", "description": "A group failed after a merge"})
    except RuntimeError:
        pass  # already exists
    number = open_issue(gh, group)
    if number:
        gh.call("POST", f"issues/{number}/comments", {"body": text})
    else:
        number = gh.call("POST", "issues", {"title": title(group), "body": text, "labels": [LABEL]})["number"]
    marker = f"<!-- {LABEL}:{group}:{sha} -->"
    for pr in sorted({c["pr"] for c in found if c["pr"]}):
        existing = gh.call("GET", f"issues/{pr}/comments?per_page=100") or []
        if any(marker in c.get("body", "") for c in existing):
            continue
        gh.call("POST", f"issues/{pr}/comments", {
            "body": f"{marker}\nGroup `{group}` failed after a merge that includes this pull request "
                    f"([run]({run_url})); it is one of {len(found)} suspect(s). See #{number}."})
    return f"#{number}"


def close_if_open(gh, group: str, sha: str, dry_run: bool) -> str:
    number = open_issue(gh, group)
    if not number:
        return "no open issue"
    if not dry_run:
        gh.call("POST", f"issues/{number}/comments", {"body": f"Group `{group}` passed on {sha}. Closing."})
        gh.call("PATCH", f"issues/{number}", {"state": "closed", "state_reason": "completed"})
    return f"closed #{number}"


def main(argv=None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--needs", required=True)
    ap.add_argument("--sha", default=env.get("GITHUB_SHA", ""))
    ap.add_argument("--run-id", default=env.get("GITHUB_RUN_ID", ""))
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
    gh = mark_green.Gh(args.repo)
    for group in sorted(cfg.get("groups") or {}):
        result = needs.get(group, {}).get("result")
        try:
            if result == "failure":
                out = report(gh, group, args.sha, args.run_id, cfg, reused, args.dry_run)
                print(f"{group}: failed, reported in {out}" if not args.dry_run else out)
            elif result == "success":
                print(f"{group}: passed, {close_if_open(gh, group, args.sha, args.dry_run)}")
        except (RuntimeError, KeyError, ValueError) as e:
            print(f"::warning::could not report on {group}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
