#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Preprocessor policy check for C and C++ project code.

    python3 check_no_preprocessor.py [--root DIR] [--baseline FILE] [--allowlist FILE]
                                     [--update-baseline] [paths...]

Two levels (standard section 4.4):

  Hard rule   A preprocessor conditional that tests a platform, operating system,
              architecture, compiler or standard-library version fails the check.
              The only exemptions are generated and third-party directories.
  Soft rule   Every other #if, #ifdef, #ifndef, #elif, #else, #endif, #define and
              #undef is counted per file. A file outside the allowlist may not have
              more directives than its recorded baseline (a file with no entry has a
              baseline of zero). Fewer is a pass; --update-baseline records the lower
              numbers and refuses to raise any. The baseline is per file so that two
              pull requests touching different files never conflict on it.

#include, #pragma and #error are always allowed.

Files:
  tools/preprocessor-baseline.json   {"files": {"path": count, ...}}
  tools/preprocessor-allowlist.txt   one "glob  # reason" per line. A line without
                                     a reason is an error. Entries exempt a path from
                                     the soft rule only.
  tools/preprocessor-exclude.txt     one glob per line: generated and third-party
                                     directories, exempt from both rules.

Exit status 0 on pass, 1 on failure, 2 on a usage or file error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".mm", ".m"}
DIRECTIVE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|elifdef|elifndef|else|endif|define|undef)\b(.*)$")
CONDITIONAL = {"if", "ifdef", "ifndef", "elif", "elifdef", "elifndef"}

# Names that identify a platform, compiler, architecture or standard-library version.
PLATFORM_TOKEN = re.compile(
    r"""\b(
        _WIN32|_WIN64|WIN32|_WINDOWS|__CYGWIN__|__MINGW32__|__MINGW64__|
        __linux__|__linux|__gnu_linux__|__unix__|__unix|__APPLE__|__MACH__|
        __ANDROID__|__EMSCRIPTEN__|__FreeBSD__|__NetBSD__|__OpenBSD__|__wasm__|__wasm32__|
        TARGET_OS_[A-Z_]+|TARGET_CPU_[A-Z0-9_]+|
        _MSC_VER|_MSC_FULL_VER|__GNUC__|__GNUC_MINOR__|__clang__|__clang_major__|__INTEL_COMPILER|
        __cplusplus|_MSVC_LANG|__STDC_VERSION__|__has_include|__has_cpp_attribute|__has_builtin|
        __has_feature|__has_extension|__cpp_[a-z0-9_]+|__cpp_lib_[a-z0-9_]+|
        _LIBCPP_VERSION|__GLIBCXX__|_GLIBCXX_RELEASE|_MSVC_STL_VERSION|
        __x86_64__|__amd64__|__i386__|_M_X64|_M_IX86|_M_ARM64|_M_ARM|__aarch64__|__arm__|
        __ARM_ARCH|__riscv|__powerpc__|__s390x__|__SSE2__|__AVX__|__AVX2__|__ARM_NEON
    )\b""",
    re.VERBOSE,
)


def strip_comments_and_strings(text: str) -> str:
    """Blank out comments and string literals, keeping line structure."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and nxt == "*":
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            i += 2
        elif c == '"':
            out.append('"')
            i += 1
            while i < n and text[i] != '"' and text[i] != "\n":
                i += 2 if text[i] == "\\" else 1
            out.append('"')
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def logical_lines(text: str):
    """Yield (line_number, text) with backslash continuations joined."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        start = i + 1
        joined = lines[i]
        while joined.endswith("\\") and i + 1 < len(lines):
            i += 1
            joined = joined[:-1] + " " + lines[i]
        yield start, joined
        i += 1


def scan_text(text: str):
    """Return (hard, soft): lists of (line, directive, detail)."""
    hard, soft = [], []
    for number, line in logical_lines(strip_comments_and_strings(text)):
        m = DIRECTIVE.match(line)
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        if name in CONDITIONAL and PLATFORM_TOKEN.search(rest):
            hard.append((number, name, rest.strip()))
            continue
        soft.append((number, name, rest.strip()))
    return hard, soft


def read_patterns(path: Path, need_reason: bool):
    patterns, errors = [], []
    if not path.exists():
        return patterns, errors
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        glob, _, reason = line.partition("#")
        glob, reason = glob.strip(), reason.strip()
        if need_reason and not reason:
            errors.append(f"{path}:{number}: allowlist entry '{glob}' has no reason (write '# reason')")
        patterns.append(glob)
    return patterns, errors


def matches(rel: str, patterns) -> bool:
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, p.rstrip("/") + "/*") for p in patterns)


def tracked_files(root: Path):
    res = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    return res.stdout.splitlines()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--baseline", default="tools/preprocessor-baseline.json")
    ap.add_argument("--allowlist", default="tools/preprocessor-allowlist.txt")
    ap.add_argument("--exclude", default="tools/preprocessor-exclude.txt")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("paths", nargs="*", help="limit the scan to these repo-relative paths")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    allow, errors = read_patterns(root / args.allowlist, need_reason=True)
    exclude, _ = read_patterns(root / args.exclude, need_reason=False)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2

    files = args.paths or tracked_files(root)
    hard_failures, soft_total, per_file = [], 0, {}
    for rel in files:
        path = root / rel
        if path.suffix.lower() not in SOURCE_SUFFIXES or not path.is_file() or matches(rel, exclude):
            continue
        hard, soft = scan_text(path.read_text(encoding="utf-8", errors="replace"))
        hard_failures += [(rel, *h) for h in hard]
        if not matches(rel, allow) and soft:
            per_file[rel] = len(soft)
            soft_total += len(soft)

    for rel, number, name, detail in hard_failures:
        print(f"{rel}:{number}: #{name} {detail}  <- tests a platform, compiler or standard version; "
              f"move this into src/platform/<os>/ and let CMake choose the file", file=sys.stderr)

    baseline_path = root / args.baseline
    baseline = None
    if baseline_path.exists():
        baseline = {k: int(v) for k, v in json.loads(baseline_path.read_text(encoding="utf-8"))["files"].items()}

    if args.update_baseline:
        raised = [(rel, baseline.get(rel, 0) if baseline else 0, n) for rel, n in per_file.items()
                  if baseline is not None and n > baseline.get(rel, 0)]
        if raised:
            for rel, old, new in raised:
                print(f"refusing to raise {rel} from {old} to {new}; remove directives or add an "
                      f"allowlist entry with a reason", file=sys.stderr)
            return 1
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps({"files": dict(sorted(per_file.items()))}, indent=2) + "\n",
                                 encoding="utf-8")
        print(f"baseline written: {soft_total} directives in {len(per_file)} files")
        return 1 if hard_failures else 0

    status = 1 if hard_failures else 0
    if baseline is None:
        print(f"no baseline at {baseline_path}; run with --update-baseline to create it", file=sys.stderr)
        return 1
    over = [(rel, baseline.get(rel, 0), n) for rel, n in sorted(per_file.items()) if n > baseline.get(rel, 0)]
    for rel, old, new in over:
        print(f"{rel}: {new} preprocessor directives, baseline {old}. Remove the new ones, or add an "
              f"allowlist entry with a reason.", file=sys.stderr)
        status = 1
    lowered = sum(1 for rel, old in baseline.items() if per_file.get(rel, 0) < old)
    if status == 0:
        note = f"; {lowered} file(s) are below their baseline, run --update-baseline" if lowered else ""
        print(f"preprocessor check passed ({soft_total} directives outside the allowlist, "
              f"{len(hard_failures)} hard violations{note})")
    return status


if __name__ == "__main__":
    sys.exit(main())
