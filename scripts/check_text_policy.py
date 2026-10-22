#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Commit message and pull request text check.

Flags trailers other than Signed-off-by (DCO), "generated with/by" lines, authorship
statements that name a tool, and tool or assistant names, in commit messages, pull request
titles and bodies, and committed files.

    check_text_policy.py commits <base>..<head>     # every commit message in the range
    check_text_policy.py text --title T --body-file F   # a pull request
    check_text_policy.py message-file <path>        # a commit-msg hook argument
    check_text_policy.py files [paths...]           # committed files (authorship lines only)

Exit status 0 when clean, 1 when something is flagged.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

TRAILER = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):\s+\S", re.MULTILINE)
ALLOWED_TRAILERS = {"signed-off-by"}

ATTRIBUTION_LINES = [
    (re.compile(r"co-authored-by\s*:", re.I), "Co-authored-by trailer"),
    (re.compile(r"\bgenerated\s+(with|by|using)\b", re.I), "'generated with/by' line"),
    (re.compile(r"\b(written|created|authored|assisted)\s+(with|by)\s+(an?\s+)?(ai|llm|assistant)\b", re.I),
     "AI authorship statement"),
    (re.compile(r"[\U0001F916]"), "robot emoji"),
]
TOOL_NAMES = re.compile(r"\b(claude|anthropic|copilot|chatgpt|openai|codex|gemini)\b", re.I)


def check_message(text: str, where: str) -> list[str]:
    problems = []
    for pattern, label in ATTRIBUTION_LINES:
        if pattern.search(text):
            problems.append(f"{where}: {label}")
    m = TOOL_NAMES.search(text)
    if m:
        problems.append(f"{where}: tool or assistant name '{m.group(0)}'")
    # Trailers: the final paragraph, when every line looks like "Key: value".
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paragraphs) > 1:
        lines = [ln for ln in paragraphs[-1].splitlines() if ln.strip()]
        if lines and all(TRAILER.match(ln) for ln in lines):
            for ln in lines:
                key = ln.split(":", 1)[0].strip().lower()
                if key not in ALLOWED_TRAILERS:
                    problems.append(f"{where}: trailer '{ln.split(':', 1)[0]}' is not allowed (only Signed-off-by)")
    return problems


def commits_in_range(rng: str) -> list[tuple[str, str]]:
    out = subprocess.run(["git", "log", "--format=%H%x00%B%x01", rng], capture_output=True, text=True, check=True)
    commits = []
    for chunk in out.stdout.split("\x01"):
        chunk = chunk.strip("\n")
        if "\x00" in chunk:
            sha, body = chunk.split("\x00", 1)
            commits.append((sha.strip(), body))
    return commits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("commits")
    p.add_argument("range")
    p = sub.add_parser("text")
    p.add_argument("--title", default="")
    p.add_argument("--body-file")
    p = sub.add_parser("message-file")
    p.add_argument("path")
    p = sub.add_parser("files")
    p.add_argument("paths", nargs="*")
    args = ap.parse_args(argv)

    problems: list[str] = []
    if args.cmd == "commits":
        for sha, body in commits_in_range(args.range):
            problems += check_message(body, f"commit {sha[:10]}")
    elif args.cmd == "text":
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else ""
        problems += check_message(args.title, "pull request title")
        problems += check_message(body, "pull request body")
    elif args.cmd == "message-file":
        lines = [ln for ln in Path(args.path).read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
        problems += check_message("\n".join(lines), "commit message")
    else:
        paths = args.paths or subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                                             check=True).stdout.splitlines()
        skip = {"tests/test_check_text_policy.py", "check_text_policy.py"}
        for rel in paths:
            path = Path(rel)
            if path.name in skip or not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern, label in ATTRIBUTION_LINES:
                m = pattern.search(text)
                if m:
                    line = text.count("\n", 0, m.start()) + 1
                    problems.append(f"{rel}:{line}: {label}")

    for line in problems:
        print(line, file=sys.stderr)
    if problems:
        print("\nRemove the lines listed above.", file=sys.stderr)
        return 1
    print("text policy passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
