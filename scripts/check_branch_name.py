#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Branch names: develop, main, release/x.y, gh-readonly-queue/**, dependabot/**, and
feature|bugfix|docs|chore|agent/<lower-case-words-with-dashes-or-slashes>."""

import re
import sys

WORK = re.compile(r"^(feature|bugfix|docs|chore|agent)/[a-z0-9]+([-/][a-z0-9]+)*$")
RELEASE = re.compile(r"^release/[0-9]+\.[0-9]+$")


def ok(name: str) -> bool:
    return (name in ("develop", "main") or name.startswith(("dependabot/", "gh-readonly-queue/"))
            or bool(WORK.match(name)) or bool(RELEASE.match(name)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    if ok(sys.argv[1]):
        print(f"branch name '{sys.argv[1]}' is allowed")
        sys.exit(0)
    print(f"branch name '{sys.argv[1]}' is not allowed. Use feature/, bugfix/, docs/, chore/ or agent/ "
          f"followed by lower-case words joined by '-'.", file=sys.stderr)
    sys.exit(1)
