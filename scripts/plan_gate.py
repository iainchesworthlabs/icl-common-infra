#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide what the PR gate builds.

    git diff --name-only origin/develop...HEAD | python3 plan_gate.py --config .github/ci/plan.json
    python3 plan_gate.py --config .github/ci/plan.json --force-all

Reads one repo-relative path per line from stdin and prints key=value lines for
$GITHUB_OUTPUT:

    build       true when the change can alter what the C++ build or the tests do
    gui         true when Qt is needed: the change touches the GUI, shared UI code, cmake/
                or the top-level build files
    docs_only   true when every path is documentation
    machinery   true when the change touches the gate itself, so everything runs
    reason      the first path that forced build
    gui_reason  the first path that pulled Qt in

Rules (standard section 11.5.2):
  * an empty list, or a path that matches no rule, builds everything (a false skip is
    silent and wrong, a false build costs minutes)
  * documentation-only changes run static checks and no build
  * a change that no Linux build reads runs static checks only
  * a change to the gate's own files builds everything

Config (.github/ci/plan.json), all lists of path globs (fnmatch, '**' matches '/'):
    docs         documentation: no build
    no_build     paths no build reads (issue templates, funding files, ...)
    build        paths that need the non-GUI build and tests
    gui          paths that need Qt and the GUI build
    machinery    the gate's own files: build and gui both true
Paths in `gui` imply `build`. Unlisted paths build everything.

Groups (docs/ci-many-agents.md sections 3 and 4), optional:

    git diff --name-only A B | python3 plan_gate.py --config .github/ci/plan.json --groups

adds two lines to the output:

    groups      JSON list of the groups the path list asks for
    promoted    JSON list of the groups the paths promote to an earlier stage

`groups` in the config maps a group name to {home, skips, promote, jobs}. `home` is the stage by
which the group must have passed (pull_request, queue, post_merge or nightly). `skips` are globs the
group provably does not read, in addition to `docs` and `no_build`; `promote` are globs that pull a
post-merge group into the queue. `jobs` lists the job names that must all succeed for the group to
count as proved. A group is asked for unless every path is documentation, a `no_build` path or in
its `skips`. The gate's own files, the barrier paths (`reuse.barrier`) and an empty list ask for every
group. The default is to run. A glob may use {a,b} alternatives.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

DEFAULT = {
    "docs": ["docs/**", "*.md", "mkdocs.yml", "LICENSE*", "notices/**", "changelog.d/**"],
    "no_build": [".github/ISSUE_TEMPLATE/**", ".github/PULL_REQUEST_TEMPLATE*", ".github/CODEOWNERS",
                 ".github/FUNDING.yml", ".github/dependabot.yml", ".github/labels.yml", ".github/rulesets/**",
                 ".github/repo-settings.yml", "REUSE.toml", ".editorconfig"],
    "build": ["libs/**", "tests/**", "tools/**", "CMakeLists.txt", "CMakePresets.json", "vcpkg.json",
              "cmake/**", "apps/**/src/**", "src/**"],
    "gui": ["apps/**/qml/**", "apps/**/gui/**", "apps/**/viewmodel/**", "**/*.qml", "**/*.ui", "**/*.ts",
            "cmake/**", "CMakeLists.txt", "CMakePresets.json", "vcpkg.json", "libs/ui/**"],
    "machinery": [".github/workflows/**", ".github/actions/**", ".github/ci/**", ".github/toolchain-versions.json",
                  "tools/ci/**", "tools/checks/**"],
    "groups": {},
}

# Paths that define how results are produced (section 3.6). A consumer can add to them, not remove these.
MANDATORY_BARRIER = [".github/workflows", ".github/actions", ".github/ci", ".github/toolchain-versions.json"]
DEFAULT_BARRIER = MANDATORY_BARRIER + [
    "cmake", "CMakePresets.json", "CMakeLists.txt", "vcpkg.json", "vcpkg-configuration.json",
    "vcpkg-overlay-ports", "tools/ci", "tools/checks", "tools/sanitizers"]
DEFAULT_MAX_AGE_HOURS = 48


def reuse_config(cfg: dict) -> dict:
    """The reuse section with its defaults. The mandatory barrier paths cannot be removed."""
    section = cfg.get("reuse") or {}
    barrier = list(MANDATORY_BARRIER)
    for path in section.get("barrier", DEFAULT_BARRIER[len(MANDATORY_BARRIER):]):
        path = path.rstrip("/")
        if path not in barrier:
            barrier.append(path)
    return {"barrier": barrier, "max_age_hours": int(section.get("max_age_hours", DEFAULT_MAX_AGE_HOURS))}


def in_barrier(path: str, barrier) -> bool:
    return any(path == b or path.startswith(b + "/") for b in barrier)


def expand(pattern: str) -> list[str]:
    """Expand {a,b} alternatives, recursively."""
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    return [x for alt in m.group(1).split(",") for x in expand(pattern[:m.start()] + alt + pattern[m.end():])]


def match(path: str, patterns) -> str | None:
    for pat in (e for p in patterns for e in expand(p)):
        regex_pat = pat.replace("**/", "*").replace("/**", "/*")
        if fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path, regex_pat):
            return pat
    return None


def plan(paths: list[str], cfg: dict) -> dict[str, str]:
    paths = [p.strip() for p in paths if p.strip()]
    out = {"build": "false", "gui": "false", "docs_only": "false", "machinery": "false", "reason": "", "gui_reason": ""}

    def everything(reason: str):
        out.update(build="true", gui="true", reason=reason, gui_reason=out["gui_reason"] or reason)

    if not paths:
        everything("empty file list")
        return out
    if all(match(p, cfg["docs"]) for p in paths):
        out["docs_only"] = "true"
        return out
    for p in paths:
        if match(p, cfg["machinery"]):
            out["machinery"] = "true"
            everything(p)
            return out
    for p in paths:
        if match(p, cfg["docs"]) or match(p, cfg["no_build"]):
            continue
        in_gui, in_build = match(p, cfg["gui"]), match(p, cfg["build"])
        if not in_gui and not in_build:
            everything(f"{p} (unrecognised path)")
            return out
        if out["build"] == "false":
            out["build"], out["reason"] = "true", p
        if in_gui and out["gui"] == "false":
            out["gui"], out["gui_reason"] = "true", p
    return out


def groups_plan(paths: list[str], cfg: dict) -> dict[str, list[str]]:
    """Which groups the path list asks for, and which it promotes to an earlier stage."""
    paths = [p.strip() for p in paths if p.strip()]
    groups = cfg.get("groups") or {}
    names = sorted(groups)
    barrier = reuse_config(cfg)["barrier"]
    if not paths or any(match(p, cfg["machinery"]) or in_barrier(p, barrier) for p in paths):
        asked = names
    else:
        asked = []
        for name in names:
            skips = groups[name].get("skips", [])
            if any(not (match(p, cfg["docs"]) or match(p, cfg["no_build"]) or match(p, skips)) for p in paths):
                asked.append(name)
    promoted = [n for n in asked if any(match(p, groups[n].get("promote", [])) for p in paths)]
    return {"groups": asked, "promoted": promoted}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    ap.add_argument("--force-all", action="store_true")
    ap.add_argument("--groups", action="store_true", help="also print the groups and promoted lines")
    args = ap.parse_args(argv)
    cfg = dict(DEFAULT)
    if args.config and Path(args.config).exists():
        cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    lines = [] if args.force_all else sys.stdin.read().splitlines()
    result = plan(lines, cfg)
    if args.force_all:
        result["reason"] = "forced"
    if args.groups:
        for key, value in groups_plan(lines, cfg).items():
            result[key] = json.dumps(value, separators=(",", ":"))
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
