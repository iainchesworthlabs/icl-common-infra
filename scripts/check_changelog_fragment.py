#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Changelog fragment check.

    check_changelog_fragment.py --base <ref> [--head HEAD] [--no-changelog]

A pull request adds at least one changelog.d/<slug>.<type>.md unless it carries the
no-changelog label (--no-changelog) or changes only documentation, tests, CI
or tooling. Every fragment it adds must be well formed. CHANGELOG.md is never edited
by a pull request (it is assembled from the fragments at release time).

<type> is one of added, changed, deprecated, removed, fixed, security.
The content is one bold-led paragraph.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TYPES = ("added", "changed", "deprecated", "removed", "fixed", "security")
NAME = re.compile(r"^changelog\.d/([A-Za-z0-9][A-Za-z0-9._-]*)\.(" + "|".join(TYPES) + r")\.md$")
NOT_USER_VISIBLE = ("docs/", ".github/", "tools/", "tests/", "changelog.d/README.md", ".editorconfig",
                    ".clang-format", ".clang-tidy", "AGENTS.md", "CONTRIBUTING.md", "README.md", "REUSE.toml")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def user_visible(path: str) -> bool:
    return not path.startswith(NOT_USER_VISIBLE) and not path.endswith((".md", ".txt")) or path.startswith("CHANGELOG")


def check(added_fragments: dict[str, str], changed: list[str], no_changelog: bool) -> list[str]:
    problems = []
    if "CHANGELOG.md" in changed:
        problems.append("CHANGELOG.md is assembled at release time; add a fragment in changelog.d/ instead")
    for rel, text in added_fragments.items():
        if not NAME.match(rel):
            problems.append(f"{rel}: name must be changelog.d/<slug>.<type>.md with type in {', '.join(TYPES)}")
            continue
        body = text.strip()
        if not body:
            problems.append(f"{rel}: empty")
        elif "\n\n" in body:
            problems.append(f"{rel}: must be one paragraph")
        elif not body.startswith("**"):
            problems.append(f"{rel}: must open with a **bold lead-in**")
        elif body.startswith("- "):
            problems.append(f"{rel}: write the paragraph without the leading dash")
    visible = [p for p in changed if user_visible(p) and not p.startswith("changelog.d/")]
    if visible and not added_fragments and not no_changelog:
        problems.append("this change touches user-visible code but adds no changelog.d/<slug>.<type>.md "
                        "(or apply the no-changelog label)")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--no-changelog", action="store_true")
    args = ap.parse_args(argv)

    changed = [ln for ln in git("diff", "--name-only", f"{args.base}...{args.head}").splitlines() if ln]
    added = [ln for ln in git("diff", "--name-only", "--diff-filter=A", f"{args.base}...{args.head}").splitlines()
             if ln.startswith("changelog.d/") and ln != "changelog.d/README.md"]
    fragments = {rel: Path(rel).read_text(encoding="utf-8") for rel in added if Path(rel).exists()}
    problems = check(fragments, changed, args.no_changelog)
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    print("changelog fragment check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
