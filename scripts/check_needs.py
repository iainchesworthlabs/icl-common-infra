#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Aggregate the results of the jobs a workflow depends on into one required check.

    check_needs.py --needs "$NEEDS_JSON" [--expected "$EXPECTED_JSON"]

NEEDS_JSON is toJSON(needs). EXPECTED_JSON maps a job id to true or false: whether the plan
asked for that job. Rules:

  * a job that failed or was cancelled fails the aggregate
  * a job the plan asked for that was skipped fails the aggregate (a skipped job that
    should have run means the check silently did not happen)
  * a job the plan did not ask for may be skipped
  * a job with no entry in EXPECTED_JSON is expected to run

The aggregator is the one required status check, so a matrix leg is never named in branch
protection.
"""

from __future__ import annotations

import argparse
import json
import sys


def evaluate(needs: dict, expected: dict) -> list[str]:
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
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--needs", required=True)
    ap.add_argument("--expected", default="{}")
    args = ap.parse_args(argv)
    needs = json.loads(args.needs)
    expected = json.loads(args.expected or "{}")
    problems = evaluate(needs, expected)
    for job, info in sorted(needs.items()):
        print(f"{info.get('result', '?'):10} {job}")
    if problems:
        print("\n" + "\n".join(problems), file=sys.stderr)
        return 1
    print("\nAll required jobs succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
