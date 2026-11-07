#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate the results of the jobs a workflow depends on into one required check.

    check_needs.py --needs "$NEEDS_JSON" [--expected "$EXPECTED_JSON"] [--reused "$REUSED_JSON"]

NEEDS_JSON is toJSON(needs). EXPECTED_JSON maps a job id to true or false: whether the plan
asked for that job. Rules:

  * a job that failed or was cancelled fails the aggregate
  * a job the plan asked for that was skipped fails the aggregate (a skipped job that
    should have run means the check silently did not happen)
  * a job the plan asked for that has no entry in NEEDS_JSON fails the aggregate (GitHub leaves out
    a job that never got a runner and was cancelled, so its absence is the only sign it did not run)
  * a job the plan did not ask for may be skipped
  * a job with no entry in EXPECTED_JSON is expected to run
  * REUSED_JSON (optional) maps a group to the earlier run that proved it (the `reuse` job's
    `reused` output). A named group is not expected to run, so it may be skipped; one that ran and
    failed still fails. The map is ignored unless the `reuse` job is in NEEDS_JSON and succeeded.
    A summary table and one ::notice per reused group are written.

The aggregator is the one required status check, so a matrix leg is never named in branch
protection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def valid_reused(needs: dict, reused) -> dict:
    """The reused map, or {} when the reuse job did not succeed (its output is then not trusted)."""
    if not isinstance(reused, dict) or not reused:
        return {}
    if needs.get("reuse", {}).get("result") != "success":
        return {}
    return dict(reused)


def notice(group: str, info) -> str:
    if not isinstance(info, dict):
        return f"{group} reused from {info}"
    return (f"{group} reused from run {info.get('run_id', '?')} ({info.get('event', '?')}, "
            f"tested {str(info.get('tested_sha', ''))[:8]}, delta {info.get('delta', '?')} file(s), "
            f"{info.get('kind', '?')})")


def summary_table(reused: dict) -> str:
    rows = ["### Reused results", "", "| Group | Run | Event | Tested | Delta | Kind |", "|---|---|---|---|---|---|"]
    for group, info in sorted(reused.items()):
        info = info if isinstance(info, dict) else {"run_id": info}
        link = f"[{info.get('run_id', '?')}]({info['url']})" if info.get("url") else str(info.get("run_id", "?"))
        rows.append(f"| {group} | {link} | {info.get('event', '')} | {str(info.get('tested_sha', ''))[:8]} | "
                    f"{info.get('delta', '')} | {info.get('kind', '')} |")
    return "\n".join(rows) + "\n"


def evaluate(needs: dict, expected: dict, reused=None) -> list[str]:
    expected = dict(expected)
    for group in valid_reused(needs, reused):
        expected[group] = False
    problems = []
    for job, info in sorted(needs.items()):
        result = info.get("result", "")
        wanted = expected.get(job, True)
        if result in ("failure", "cancelled"):
            problems.append(f"{job}: {result}")
        elif result == "skipped" and wanted:
            problems.append(f"{job}: skipped, but the plan asked for it")
        elif result == "success" and not wanted:
            pass  # ran anyway: fine
    for job, wanted in sorted(expected.items()):
        if wanted is True and job not in needs:
            problems.append(f"{job}: no result, but the plan asked for it")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--needs", required=True)
    ap.add_argument("--expected", default="{}")
    ap.add_argument("--reused", default="")
    args = ap.parse_args(argv)
    needs = json.loads(args.needs)
    expected = json.loads(args.expected or "{}")
    try:
        reused = json.loads(args.reused) if args.reused.strip() else {}
    except ValueError:
        print("::warning::the reused input is not JSON; ignoring it", file=sys.stderr)
        reused = {}
    problems = evaluate(needs, expected, reused)
    trusted = valid_reused(needs, reused)
    if reused and not trusted:
        print("::notice::reuse job did not succeed; its reused map is ignored")
    for group, info in sorted(trusted.items()):
        print(f"::notice::{notice(group, info)}")
    if trusted and os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary_table(trusted))
    for job, info in sorted(needs.items()):
        print(f"{info.get('result', '?'):10} {job}")
    if problems:
        print("\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("\nAll required jobs succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
