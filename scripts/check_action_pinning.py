#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every external action and reusable workflow is pinned to a full commit SHA.

    check_action_pinning.py [--root DIR]

Scans .github/workflows/*.yml and .github/actions/**/action.yml for `uses:`.
Local references (./path and the self-repository form $/path, which resolves to the running commit) pass. A docker:// reference must carry @sha256:<digest>.
Anything else must end in @<40 hex characters>. A trailing `# vX.Y.Z` comment is
expected so that Dependabot can keep the pin current, and its absence is a warning.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>[^\s#]+)\s*(?P<comment>#.*)?$")
SHA = re.compile(r"@[0-9a-f]{40}$")


def scan(path: Path):
    problems, warnings = [], []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = USES.match(line)
        if not m:
            continue
        ref = m.group("ref").strip("'\"")
        if ref.startswith(("./", "$/")):
            continue
        if ref.startswith("docker://"):
            if "@sha256:" not in ref:
                problems.append(f"{path}:{number}: {ref} is not pinned to a digest")
            continue
        if not SHA.search(ref):
            problems.append(f"{path}:{number}: {ref} is not pinned to a 40-character commit SHA")
        elif not m.group("comment"):
            warnings.append(f"{path}:{number}: {ref} has no '# vX.Y.Z' comment")
    return problems, warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.root)
    files = sorted(list((root / ".github/workflows").glob("*.y*ml")) + list((root / ".github/actions").glob("**/action.y*ml"))
                   + list(root.glob("actions/**/action.y*ml")))
    problems, warnings = [], []
    for f in files:
        p, w = scan(f)
        problems += p
        warnings += w
    for w in warnings:
        print("warning:", w)
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    print(f"action pinning passed ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
