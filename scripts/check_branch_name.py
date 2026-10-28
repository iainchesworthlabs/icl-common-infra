#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Branch names: develop, main, quality-history, gh-pages, release/x.y, gh-readonly-queue/**,
dependabot/**, and feature|bugfix|docs|chore|agent/<lower-case-words-with-dashes-or-slashes>.

A project may add prefixes of its own (for example spike/) in .github/branch-prefixes.txt, one
lower-case word per line, blank lines and # comments allowed. admin/apply.sh reads the same file
when it builds the branch-names ruleset, so the check and the ruleset agree."""

import re
import sys
from pathlib import Path

PREFIX_FILE = Path(".github/branch-prefixes.txt")
PREFIX = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
BUILT_IN = ("feature", "bugfix", "docs", "chore", "agent")
RESERVED = BUILT_IN + ("release", "dependabot", "gh-readonly-queue", "develop", "main",
                       "quality-history", "gh-pages")
RELEASE = re.compile(r"^release/[0-9]+\.[0-9]+$")


def read_prefixes(text: str) -> list[str]:
    """The extra prefixes in the text of a prefix file. Raises ValueError on a bad line."""
    prefixes = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not PREFIX.match(line):
            raise ValueError(f"line {number}: '{line}' is not a lower-case word")
        if line in RESERVED:
            raise ValueError(f"line {number}: '{line}' is already a prefix of the standard")
        if line not in prefixes:
            prefixes.append(line)
    return prefixes


def work_pattern(extra: list[str]) -> re.Pattern:
    names = "|".join(BUILT_IN + tuple(extra))
    return re.compile(rf"^({names})/[a-z0-9]+([-/][a-z0-9]+)*$")


def ok(name: str, extra: list[str] | None = None) -> bool:
    return (name in ("develop", "main", "quality-history", "gh-pages")
            or name.startswith(("dependabot/", "gh-readonly-queue/"))
            or bool(work_pattern(extra or []).match(name)) or bool(RELEASE.match(name)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    extra: list[str] = []
    if PREFIX_FILE.is_file():
        try:
            extra = read_prefixes(PREFIX_FILE.read_text(encoding="utf-8"))
        except ValueError as problem:
            print(f"{PREFIX_FILE}: {problem}", file=sys.stderr)
            sys.exit(2)
    if ok(sys.argv[1], extra):
        print(f"branch name '{sys.argv[1]}' is allowed")
        sys.exit(0)
    prefixes = ", ".join(f"{p}/" for p in BUILT_IN + tuple(extra))
    print(f"branch name '{sys.argv[1]}' is not allowed. Use one of {prefixes} "
          f"followed by lower-case words joined by '-'.", file=sys.stderr)
    sys.exit(1)
