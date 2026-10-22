#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run the PR gate's static checks locally, before a push.

    python3 precheck.py                    # the diff against origin/develop
    python3 precheck.py --base <ref>
    python3 precheck.py --root <repo>      # check another working tree

These are the checks the policy workflow runs, minus the ones that need a tool this
machine may not have (each says SKIP and why). A push that would fail one costs a round
trip of minutes; this costs seconds. It also prints what the gate will plan for the diff.

Exit status is 1 if a check fails. A SKIP is not a failure.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_branch_name  # noqa: E402
import plan_gate  # noqa: E402

CPP_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".mm")


@dataclass(frozen=True)
class Result:
    name: str
    status: str  # pass | fail | skip
    detail: str = ""
    seconds: float = 0.0


def render(results: list[Result]) -> str:
    width = max(len(r.name) for r in results)
    return "\n".join(f"{r.status.upper():4}  {r.name:<{width}}  {r.seconds:5.1f}s"
                     f"{('  ' + r.detail) if r.detail else ''}" for r in results)


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.status == "fail" for r in results) else 0


def run(root: Path, name: str, cmd: list[str]) -> Result:
    start = time.monotonic()
    try:
        res = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    except OSError as e:
        return Result(name, "skip", f"could not run {cmd[0]}: {e}")
    took = time.monotonic() - start
    if res.returncode == 0:
        return Result(name, "pass", "", took)
    tail = (res.stdout + res.stderr).strip().splitlines()[-20:]
    return Result(name, "fail", "\n" + "\n".join(f"      {ln}" for ln in tail), took)


def git(root: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return res.stdout.strip() if res.returncode == 0 else ""


def default_base(root: Path) -> str:
    for ref in ("origin/develop", "develop", "origin/main", "main"):
        if git(root, "rev-parse", "--verify", "--quiet", ref):
            return ref
    return "HEAD~1"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    base = args.base or default_base(root)
    py = sys.executable
    results: list[Result] = []

    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    results.append(Result("branch name", "pass" if check_branch_name.ok(branch) else "fail",
                          "" if check_branch_name.ok(branch) else f"'{branch}' is not an allowed branch name"))
    results.append(run(root, "commit text", [py, str(HERE / "check_text_policy.py"), "commits", f"{base}..HEAD"]))
    results.append(run(root, "committed files text", [py, str(HERE / "check_text_policy.py"), "files"]))
    if (root / "tools/preprocessor-baseline.json").exists():
        results.append(run(root, "preprocessor", [py, str(HERE / "check_no_preprocessor.py")]))
    else:
        results.append(Result("preprocessor", "skip", "no tools/preprocessor-baseline.json"))
    results.append(run(root, "action pinning", [py, str(HERE / "check_action_pinning.py")]))
    results.append(run(root, "changelog fragment", [py, str(HERE / "check_changelog_fragment.py"), "--base", base]))
    if not ((root / "REUSE.toml").exists() or (root / ".reuse").exists()):
        results.append(Result("reuse lint", "skip", "no REUSE.toml"))
    elif shutil.which("reuse"):
        results.append(run(root, "reuse lint", ["reuse", "lint"]))
    else:
        results.append(Result("reuse lint", "skip", "reuse is not installed (pip install reuse)"))

    changed = git(root, "diff", "--name-only", f"{base}...HEAD").splitlines()
    cpp = [p for p in changed if p.endswith(CPP_SUFFIXES) and (root / p).exists()]
    if cpp and shutil.which("clang-format"):
        results.append(run(root, "clang-format", ["clang-format", "--dry-run", "--Werror", *cpp]))
    elif cpp:
        results.append(Result("clang-format", "skip", "clang-format is not installed"))

    print(render(results))
    cfg = dict(plan_gate.DEFAULT)
    plan_path = root / ".github/ci/plan.json"
    if plan_path.exists():
        import json
        cfg.update(json.loads(plan_path.read_text(encoding="utf-8")))
    plan = plan_gate.plan(changed, cfg)
    print("\nThe gate will plan: " + ", ".join(f"{k}={v}" for k, v in plan.items() if v))
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
