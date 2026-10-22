#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble changelog fragments and extract release notes.

    changelog_tool.py assemble --version 1.4.0 --date 2026-10-22 [--root .]
        Move every changelog.d/<slug>.<type>.md into a new "## [1.4.0] - 2026-10-22"
        section of CHANGELOG.md (above the previous release), grouped under
        ### Added / Changed / Deprecated / Removed / Fixed / Security, then delete the
        fragments. changelog.d/README.md stays. Exit 1 when there are no fragments.

    changelog_tool.py notes --version 1.4.0 [--root .]
        Print the body of that version's section of CHANGELOG.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ORDER = ["added", "changed", "deprecated", "removed", "fixed", "security"]
NAME = re.compile(r"^(?P<slug>.+)\.(?P<type>added|changed|deprecated|removed|fixed|security)\.md$")
HEADER = "# Changelog\n\nAll notable changes are listed here. Each release section is assembled from the\nfragments in `changelog.d/`.\n\n"


def collect(root: Path):
    groups = {t: [] for t in ORDER}
    files = []
    for path in sorted((root / "changelog.d").glob("*.md")):
        m = NAME.match(path.name)
        if not m:
            continue
        groups[m.group("type")].append(path.read_text(encoding="utf-8").strip())
        files.append(path)
    return groups, files


def render_section(version: str, date: str, groups: dict) -> str:
    out = [f"## [{version}] - {date}\n"]
    for t in ORDER:
        if groups[t]:
            out.append(f"### {t.capitalize()}\n")
            out.extend(f"- {item}\n" for item in groups[t])
    return "\n".join(out) + "\n"


def assemble(root: Path, version: str, date: str) -> int:
    groups, files = collect(root)
    if not files:
        print("no changelog fragments", file=sys.stderr)
        return 1
    changelog = root / "CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else HEADER
    if f"## [{version}]" in existing:
        print(f"CHANGELOG.md already has {version}", file=sys.stderr)
        return 1
    section = render_section(version, date, groups)
    m = re.search(r"^## \[", existing, re.MULTILINE)
    new = existing[: m.start()] + section + existing[m.start():] if m else existing.rstrip("\n") + "\n\n" + section
    changelog.write_text(new, encoding="utf-8")
    for f in files:
        f.unlink()
    print(f"assembled {len(files)} fragment(s) into {version}")
    return 0


def notes(root: Path, version: str) -> int:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8") if (root / "CHANGELOG.md").exists() else ""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(?P<body>.*?)(?=^## \[|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        print(f"no section for {version} in CHANGELOG.md", file=sys.stderr)
        return 1
    print(m.group("body").strip())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("assemble")
    a.add_argument("--version", required=True)
    a.add_argument("--date", required=True)
    a.add_argument("--root", default=".")
    n = sub.add_parser("notes")
    n.add_argument("--version", required=True)
    n.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.root)
    return assemble(root, args.version, args.date) if args.cmd == "assemble" else notes(root, args.version)


if __name__ == "__main__":
    sys.exit(main())
