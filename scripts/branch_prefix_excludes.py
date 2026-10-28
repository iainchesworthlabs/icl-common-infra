#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Add a project's extra branch prefixes to the branch-names ruleset.

    branch_prefix_excludes.py <branch-prefixes.txt> < ruleset.json > ruleset.json

Reads the ruleset on stdin and writes it with, for every prefix in the file, the same three
exclude patterns the built-in prefixes have (one, two and three levels below the prefix). The
file is the one scripts/check_branch_name.py reads. Exit status 2 on a bad prefix file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_branch_name as names  # noqa: E402


def add_excludes(ruleset: dict, prefixes: list[str]) -> dict:
    exclude = ruleset["conditions"]["ref_name"]["exclude"]
    for prefix in prefixes:
        for depth in range(1, 4):
            pattern = "refs/heads/" + "/".join([prefix] + ["*"] * depth)
            if pattern not in exclude:
                exclude.append(pattern)
    return ruleset


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        prefixes = names.read_prefixes(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as problem:
        print(f"{argv[1]}: {problem}", file=sys.stderr)
        return 2
    json.dump(add_excludes(json.load(sys.stdin), prefixes), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
