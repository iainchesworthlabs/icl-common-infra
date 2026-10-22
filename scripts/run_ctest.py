#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run CTest in phases, re-run failures by name, and report flakes.

    run_ctest.py --build-dir build [--config Release] [--phases phases.json] [--summary FILE]

Each phase is {"name", "label" (regex or ""), "jobs" (int, 0 = all cores)}. Default phases:

    parallel   label unit|integration|system   all cores
    ui         label ui                        2 jobs
    perf       label perf                      1 job, last

For a phase that fails, the failed test names are read from
Testing/Temporary/LastTestsFailed.log and re-run once, one at a time, with
`ctest --tests-from-file` (never --rerun-failed, which depends on state that a
concurrent phase can overwrite). A test that fails and then passes is reported as a
flaky pass (warning, exit 0). A test that fails twice fails the run. The run also fails
if the re-run did not run exactly the tests that failed. A phase that matches no tests
is a failure unless it is optional ("optional": true), because a mistyped label would
otherwise pass with nothing run.

Exit status 0 on success, 1 on any real failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_PHASES = [
    {"name": "parallel", "label": "unit|integration|system", "jobs": 0, "optional": False},
    {"name": "ui", "label": "ui", "jobs": 2, "optional": True},
    {"name": "perf", "label": "perf", "jobs": 1, "optional": True},
]


def failed_names(build_dir: Path) -> list[str]:
    log = build_dir / "Testing" / "Temporary" / "LastTestsFailed.log"
    if not log.exists():
        return []
    names = []
    for line in log.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\d+:(.+)$", line.strip())
        if m:
            names.append(m.group(1))
    return names


def ctest_cmd(ctest: str, build_dir: Path, config: str, jobs: int, extra: list[str]) -> list[str]:
    cmd = [ctest, "--test-dir", str(build_dir), "--output-on-failure", "--no-tests=error", "-j", str(jobs or os.cpu_count() or 1)]
    if config:
        cmd += ["-C", config]
    return cmd + extra


def run_phase(phase: dict, args, summary: list[str]) -> tuple[bool, list[str]]:
    """Return (ok, flaky_names)."""
    build_dir = Path(args.build_dir)
    extra = ["-L", phase["label"]] if phase.get("label") else []
    res = subprocess.run(ctest_cmd(args.ctest, build_dir, args.config, phase.get("jobs", 0), extra))
    if res.returncode == 0:
        summary.append(f"- {phase['name']}: passed")
        return True, []
    names = failed_names(build_dir)
    if not names:
        if phase.get("optional") and res.returncode != 0 and _no_tests(build_dir, args, extra):
            summary.append(f"- {phase['name']}: no tests match label '{phase.get('label')}' (optional)")
            return True, []
        summary.append(f"- {phase['name']}: FAILED with no recorded failing tests (build or configuration problem)")
        return False, []
    list_file = build_dir / f"rerun-{phase['name']}.txt"
    list_file.write_text("\n".join(names) + "\n", encoding="utf-8")
    print(f"::warning::{phase['name']}: {len(names)} failed; re-running by name: {', '.join(names)}")
    rerun = subprocess.run(ctest_cmd(args.ctest, build_dir, args.config, 1, ["--tests-from-file", str(list_file)]))
    still = failed_names(build_dir) if rerun.returncode != 0 else []
    if rerun.returncode != 0 and not still:
        summary.append(f"- {phase['name']}: re-run failed without a failure list")
        return False, []
    if set(still) - set(names):
        summary.append(f"- {phase['name']}: re-run failed tests that were not in the first failure list: {sorted(set(still) - set(names))}")
        return False, []
    flaky = [n for n in names if n not in still]
    if still:
        summary.append(f"- {phase['name']}: FAILED twice: {', '.join(still)}")
        if flaky:
            summary.append(f"  flaky (failed then passed): {', '.join(flaky)}")
        return False, flaky
    summary.append(f"- {phase['name']}: passed after re-run. Flaky: {', '.join(flaky)}")
    return True, flaky


def _no_tests(build_dir: Path, args, extra: list[str]) -> bool:
    res = subprocess.run(ctest_cmd(args.ctest, build_dir, args.config, 1, extra + ["-N"]),
                         capture_output=True, text=True)
    return "Total Tests: 0" in res.stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-dir", required=True)
    ap.add_argument("--config", default="")
    ap.add_argument("--phases", help="JSON file overriding the default phases")
    ap.add_argument("--summary", help="file to append a markdown summary to")
    ap.add_argument("--ctest", default="ctest")
    args = ap.parse_args(argv)

    phases = json.loads(Path(args.phases).read_text(encoding="utf-8")) if args.phases else DEFAULT_PHASES
    summary = ["### CTest"]
    ok_all, all_flaky = True, []
    for phase in phases:
        ok, flaky = run_phase(phase, args, summary)
        all_flaky += flaky
        if not ok:
            ok_all = False
            break  # fail early: later phases would only repeat the same environment problem
    if all_flaky:
        summary.append(f"\nFlaky tests this run: {', '.join(all_flaky)}")
    text = "\n".join(summary) + "\n"
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
