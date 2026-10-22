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
"""

from __future__ import annotations

import argparse
import fnmatch
import json
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
}


def match(path: str, patterns) -> str | None:
    for pat in patterns:
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config")
    ap.add_argument("--force-all", action="store_true")
    args = ap.parse_args(argv)
    cfg = dict(DEFAULT)
    if args.config and Path(args.config).exists():
        cfg.update(json.loads(Path(args.config).read_text(encoding="utf-8")))
    if args.force_all:
        result = plan([], cfg)
        result["reason"] = "forced"
    else:
        result = plan(sys.stdin.read().splitlines(), cfg)
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
