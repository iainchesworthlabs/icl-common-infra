#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-component coverage gate over a gcovr JSON report.

    gcovr --root . --json coverage.json --exclude-throw-branches --exclude-unreachable-branches \\
          --filter 'libs/' --filter 'apps/' --exclude 'tests/' --exclude 'build/'
    coverage_gate.py --report coverage.json --floors tools/coverage-floors.json [--summary FILE]

Floors file:

    {
      "default": {"line": 90, "branch": 80},
      "components": {
        "libs/core": {},                                  # uses the default
        "libs/legacy_import": {"line": 62, "branch": 41}  # migrated code: a lower floor that ratchets up
      }
    }

A component is a path prefix. Every file belongs to the longest matching prefix; a file
that matches none is reported and fails the gate, so new code cannot hide outside the table.
Statement coverage is measured as lines with a count above zero over lines that can execute.
A component with no executable lines is skipped. Floors are minimums:

  * below the floor fails the gate
  * more than 1 point above the floor prints a hint to raise it (the ratchet). Raising the
    floor is a pull request like any other; --write-floors rewrites the file with the
    current figures rounded down for components above their floor, never lowering one.

Exit status 0 on pass, 1 on a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def measure(report: dict, components: list[str]):
    totals = {c: [0, 0, 0, 0] for c in components}  # lines covered, lines total, branches covered, branches total
    unassigned = []
    ordered = sorted(components, key=len, reverse=True)
    for f in report.get("files", []):
        name = f["file"].replace("\\", "/")
        comp = next((c for c in ordered if name.startswith(c.rstrip("/") + "/") or name == c), None)
        if comp is None:
            unassigned.append(name)
            continue
        t = totals[comp]
        for line in f.get("lines", []):
            if line.get("gcovr/noncode") or line.get("gcovr/excluded"):
                continue
            t[1] += 1
            if line.get("count", 0) > 0:
                t[0] += 1
            for b in line.get("branches", []):
                if b.get("gcovr/excluded"):
                    continue
                t[3] += 1
                if b.get("count", 0) > 0:
                    t[2] += 1
    return totals, sorted(set(unassigned))


def pct(covered: int, total: int) -> float | None:
    return None if total == 0 else 100.0 * covered / total


def evaluate(report: dict, floors: dict):
    default = floors.get("default", {"line": 90, "branch": 80})
    comps = floors.get("components", {})
    totals, unassigned = measure(report, list(comps))
    rows, problems, hints = [], [], []
    for comp in sorted(comps):
        want = {**default, **comps[comp]}
        lc, lt, bc, bt = totals[comp]
        line, branch = pct(lc, lt), pct(bc, bt)
        if lt == 0:
            rows.append((comp, None, None, want, "no executable lines"))
            continue
        status = "ok"
        if line is not None and line + 1e-9 < want["line"]:
            problems.append(f"{comp}: statement coverage {line:.1f}% is below the floor {want['line']}%")
            status = "FAIL"
        if branch is not None and branch + 1e-9 < want["branch"]:
            problems.append(f"{comp}: branch coverage {branch:.1f}% is below the floor {want['branch']}%")
            status = "FAIL"
        if status == "ok" and ((line or 0) > want["line"] + 1 or (branch or 0) > want["branch"] + 1):
            hints.append(f"{comp}: coverage is above its floor ({line:.1f}% / {branch if branch is not None else 0:.1f}% against "
                         f"{want['line']}% / {want['branch']}%); raise the floor")
        rows.append((comp, line, branch, want, status))
    for name in unassigned:
        problems.append(f"{name}: not covered by any component in the floors file")
    return rows, problems, hints, totals


def render(rows) -> str:
    out = ["| Component | Statement | Branch | Floor (stmt/branch) | Result |", "|---|---|---|---|---|"]
    for comp, line, branch, want, status in rows:
        fmt = lambda v: "n/a" if v is None else f"{v:.1f}%"  # noqa: E731
        out.append(f"| {comp} | {fmt(line)} | {fmt(branch)} | {want['line']}% / {want['branch']}% | {status} |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True)
    ap.add_argument("--floors", required=True)
    ap.add_argument("--summary")
    ap.add_argument("--write-floors", action="store_true")
    args = ap.parse_args(argv)
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    floors = json.loads(Path(args.floors).read_text(encoding="utf-8"))
    rows, problems, hints, _ = evaluate(report, floors)
    table = render(rows)
    print(table)
    for h in hints:
        print("hint:", h)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write("### Coverage\n\n" + table + "\n")
    if args.write_floors and not problems:
        default = floors.get("default", {"line": 90, "branch": 80})
        for comp, line, branch, want, status in rows:
            if status != "ok" or line is None:
                continue
            new = dict(floors["components"][comp])
            new["line"] = max(want["line"], math.floor(line))
            new["branch"] = max(want["branch"], math.floor(branch if branch is not None else want["branch"]))
            if new["line"] == default["line"] and new["branch"] == default["branch"]:
                new = {}
            floors["components"][comp] = new
        Path(args.floors).write_text(json.dumps(floors, indent=2) + "\n", encoding="utf-8")
        print("floors updated")
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
