#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Platform-isolation check: the operating system is a CMake decision, not a source one.

    python3 check_platform_isolation.py [--root DIR] [--config FILE]

A project that keeps the code for each operating system in one directory per platform
(`src/app/platform/<name>/`, with a `platform.cmake` that says which files that platform
compiles) stays that way only if nobody reaches for an OS header, an OS query or an OS test
in shared code. Three rules, each reported with file:line:

  os-header   No header that exists on one operating system or one family of them
              (<windows.h>, <unistd.h>, <sys/...>, Objective-C, Android, Emscripten, X11),
              and no API whose purpose is to ask which OS this is or to reach one's
              runtime (QSysInfo, QOperatingSystemVersion, Q_OS_*, QJniObject,
              platformName(), QML's Qt.platform), outside the platform section. Code that
              needs an OS service declares an interface and gets one implementation per
              platform. Comments are not code: one that explains why something is not done
              is not a finding.
  unwired     Every directory under the platform directory (other than `not_platforms`)
              has a platform.cmake, and every .cpp/.cc/.cxx/.mm in the platform directory
              (other than `detail/`) is named, outside a comment, by one of the
              platform.cmake files. A file nothing compiles is a platform that was added to
              the source tree and never to CMake.
  cmake-os    No test of the operating system in CMake (WIN32, APPLE, ANDROID, IOS, UNIX,
              LINUX, MINGW, CYGWIN, EMSCRIPTEN, CMAKE_SYSTEM_NAME, $<PLATFORM_ID:...>)
              outside the selector, the platform fragments and the files `cmake_exempt`
              lists. Compiler tests are another axis and are not matched, nor are
              CMAKE_HOST_WIN32 (the machine running CMake), WIN32_EXECUTABLE or
              QT_ANDROID_PACKAGE_SOURCE_DIR.

The preprocessor rule (no conditional on a platform, compiler or library version) is
check_no_preprocessor.py's and is not repeated here.

The project's settings are in a JSON file, `tools/platform-isolation.json` by default; every
key is optional and the values below are the defaults:

    {
      "platform_dir":     "src/app/platform",
      "section_prefixes": ["src/app/platform/", "tests/platform/"],
      "scan_roots":       ["src", "tests", "tools", "cmake"],
      "root_files":       ["CMakeLists.txt"],
      "skip_prefixes":    ["cmake/icl/"],
      "cmake_exempt":     ["cmake/Platform.cmake", "src/app/platform/*/platform.cmake",
                           "cmake/triplets/*.cmake"],
      "not_platforms":    ["detail", "posix"],
      "wired_relative_to": "src/app/",
      "interfaces_hint":  "src/app/interfaces/"
    }

Files git ignores (build output, generated headers) are not scanned. With no git, or no work
tree, everything is, which is noisier and never quieter.

Exit status 0 when clean, 1 on a violation, 2 on a usage or file error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULTS = {
    "platform_dir": "src/app/platform",
    "section_prefixes": ["src/app/platform/", "tests/platform/"],
    "scan_roots": ["src", "tests", "tools", "cmake"],
    "root_files": ["CMakeLists.txt"],
    "skip_prefixes": ["cmake/icl/"],
    "cmake_exempt": ["cmake/Platform.cmake", "src/app/platform/*/platform.cmake", "cmake/triplets/*.cmake"],
    "not_platforms": ["detail", "posix"],
    "wired_relative_to": "src/app/",
    "interfaces_hint": "src/app/interfaces/",
}

CPP_SUFFIXES = {
    ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".tpp", ".inc",
    ".c", ".cc", ".cpp", ".cxx", ".cppm", ".ixx", ".cu", ".cuh", ".m", ".mm",
}
QML_SUFFIXES = {".qml", ".js"}
CPP_TEMPLATE = re.compile(r"\.(h|hh|hpp|hxx|inl|ipp|tpp|c|cc|cpp|cxx|m|mm)\.in$", re.IGNORECASE)
UNIT_SUFFIXES = {".cpp", ".cc", ".cxx", ".mm"}

# Headers that exist on one operating system, or one family of them.
OS_HEADER = re.compile(
    r"^\s*(?:/\*.*?\*/\s*)*#\s*(?:include|import)\s*[<\"]("
    + "|".join(
        [
            # Windows
            r"windows\.h", r"winsock2?\.h", r"ws2tcpip\.h", r"winbase\.h", r"winnt\.h", r"winerror\.h",
            r"shlobj(_core)?\.h", r"shlwapi\.h", r"shellapi\.h", r"psapi\.h", r"tchar\.h", r"comdef\.h",
            r"dshow\.h", r"objbase\.h", r"ole2?\.h", r"oleauto\.h", r"dbghelp\.h", r"io\.h", r"direct\.h",
            r"process\.h", r"d3d\w*\.h", r"dxgi\w*\.h", r"mf\w+\.h", r"wrl(/[^>\"]*)?",
            # POSIX and Unix
            r"unistd\.h", r"dlfcn\.h", r"termios\.h", r"poll\.h", r"fcntl\.h", r"pwd\.h", r"grp\.h",
            r"pthread\.h", r"semaphore\.h", r"sched\.h", r"dirent\.h", r"glob\.h", r"libgen\.h",
            r"netdb\.h", r"ifaddrs\.h", r"execinfo\.h", r"utime\.h", r"syslog\.h", r"jni\.h",
            r"sys/[^>\"]+", r"linux/[^>\"]+", r"arpa/[^>\"]+", r"netinet/[^>\"]+", r"net/[^>\"]+",
            # Apple, Android, X11, the browser (Emscripten)
            r"mach/[^>\"]+", r"mach-o/[^>\"]+", r"android/[^>\"]+", r"TargetConditionals\.h",
            r"emscripten\.h", r"emscripten/[^>\"]+",
            r"AppKit/[^>\"]+", r"Cocoa/[^>\"]+", r"CoreFoundation/[^>\"]+", r"CoreMedia/[^>\"]+",
            r"AVFoundation/[^>\"]+", r"Foundation/[^>\"]+", r"UIKit/[^>\"]+", r"objc/[^>\"]+",
            r"X11/[^>\"]+", r"xcb/[^>\"]+",
        ]
    )
    + r")[>\"]"
)

# APIs whose whole purpose is to ask which OS this is, or to reach one OS's runtime.
OS_API = re.compile(
    r"\b(QSysInfo|QOperatingSystemVersion|QJniObject|QJniEnvironment|QNativeInterface|"
    r"Q_OS_[A-Z0-9_]+|Q_PROCESSOR_[A-Z0-9_]+)\b|\bplatformName\s*\(|\bQt\s*\.\s*platform\b|"
    r"\bQt\s*\[\s*[\"']platform"
)

# A test of the operating system in CMake. The look-arounds keep CMAKE_HOST_WIN32,
# WIN32_EXECUTABLE and QT_ANDROID_PACKAGE_SOURCE_DIR from matching.
CMAKE_OS = re.compile(
    r"(?<![A-Za-z0-9_])(WIN32|APPLE|ANDROID|IOS|UNIX|LINUX|MINGW|CYGWIN|EMSCRIPTEN)(?![A-Za-z0-9_])"
    r"|CMAKE_SYSTEM_NAME|\$<PLATFORM_ID"
)

OS_HINT = "Put the OS service behind an interface{where} with one implementation per platform under {platform}/."
CMAKE_HINT = (
    "Declare it in the platform's {platform}/<name>/platform.cmake and read it as a variable or hook; "
    "only the selector tests the OS."
)


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    text: str
    hint: str


def code_of(line: str, in_block: bool) -> tuple[str, bool]:
    """The code of one line, with block comments (which may span lines) and trailing // removed."""
    out: list[str] = []
    rest = line
    while rest:
        if in_block:
            end = rest.find("*/")
            if end < 0:
                break
            rest = rest[end + 2 :]
            in_block = False
            continue
        block = rest.find("/*")
        line_comment = rest.find("//")
        if line_comment >= 0 and (block < 0 or line_comment < block):
            out.append(rest[:line_comment])
            break
        if block >= 0:
            out.append(rest[:block])
            out.append(" ")
            rest = rest[block + 2 :]
            in_block = True
            continue
        out.append(rest)
        break
    return "".join(out), in_block


def is_cpp(path: Path) -> bool:
    return path.suffix.lower() in CPP_SUFFIXES or bool(CPP_TEMPLATE.search(path.name))


def is_cmake(path: Path) -> bool:
    return path.name.lower() == "cmakelists.txt" or path.suffix.lower() == ".cmake"


def listed_by_git(root: Path, paths: list[str]) -> set[str] | None:
    """The tracked and untracked-but-not-ignored files under `paths`, or None without git."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *paths],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None
    names = {n for n in done.stdout.decode("utf-8", "surrogateescape").split("\0") if n}
    return names or None


def candidates(root: Path, cfg: dict) -> tuple[list[Path], int]:
    """The files to scan, and how many were left out as build output or git-ignored."""
    scan_roots = [r for r in cfg["scan_roots"] if (root / r).is_dir()]
    found: list[Path] = []
    for scan_root in scan_roots:
        for path in sorted((root / scan_root).rglob("*")):
            if path.is_file() and (is_cpp(path) or is_cmake(path) or path.suffix.lower() in QML_SUFFIXES):
                found.append(path)
    for name in cfg["root_files"]:
        if (root / name).is_file():
            found.append(root / name)

    tracked = listed_by_git(root, scan_roots + [n for n in cfg["root_files"] if (root / n).is_file()])
    before = len(found)
    if tracked is not None:
        found = [p for p in found if p.relative_to(root).as_posix() in tracked]
    skipped = before - len(found)
    found = [
        p
        for p in found
        if not any(p.relative_to(root).as_posix().startswith(prefix) for prefix in cfg["skip_prefixes"])
    ]
    return found, skipped


def scan_file(root: Path, path: Path, cfg: dict) -> list[Violation]:
    relative = path.relative_to(root).as_posix()
    in_section = any(relative.lower().startswith(prefix.lower()) for prefix in cfg["section_prefixes"])
    cmake = is_cmake(path)
    cpp = is_cpp(path)
    exempt = any(fnmatch.fnmatch(relative, pattern) for pattern in cfg["cmake_exempt"])
    os_hint = OS_HINT.format(
        where=f" in {cfg['interfaces_hint']}" if cfg["interfaces_hint"] else "", platform=cfg["platform_dir"]
    )
    cmake_hint = CMAKE_HINT.format(platform=cfg["platform_dir"])

    found: list[Violation] = []
    in_block = False
    for number, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if cmake:
            if exempt:
                continue
            text = re.sub(r"\s#.*$", "", raw).strip()
            if not text or text.startswith("#"):
                continue
            if CMAKE_OS.search(text):
                found.append(Violation("cmake-os", relative, number, text, cmake_hint))
            continue
        code, in_block = code_of(raw, in_block)
        code = code.strip()
        if not code or in_section:
            continue
        if cpp and OS_HEADER.search(code):
            found.append(Violation("os-header", relative, number, raw.strip(), os_hint))
        elif OS_API.search(code):
            found.append(Violation("os-header", relative, number, raw.strip(), os_hint))
    return found


def check_wiring(root: Path, cfg: dict) -> list[Violation]:
    platform_root = root / cfg["platform_dir"]
    if not platform_root.is_dir():
        return []
    directories = sorted(p for p in platform_root.iterdir() if p.is_dir())

    fragments = ""
    for directory in directories:
        fragment = directory / "platform.cmake"
        if fragment.is_file():
            # A name that appears only in a comment is not wired.
            lines = fragment.read_text(encoding="utf-8", errors="replace").splitlines()
            fragments += "\n".join(line for line in lines if not line.lstrip().startswith("#")) + "\n"

    found: list[Violation] = []
    for directory in directories:
        if directory.name in cfg["not_platforms"]:
            continue
        if not (directory / "platform.cmake").is_file():
            found.append(
                Violation(
                    "unwired",
                    directory.relative_to(root).as_posix(),
                    1,
                    f"{directory.name}/ has no platform.cmake",
                    "Add platform.cmake and a branch for it in the selector.",
                )
            )
    for directory in directories:
        if directory.name == "detail":
            continue
        for unit in sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in UNIT_SUFFIXES):
            relative = unit.relative_to(root).as_posix()
            needle = relative.removeprefix(cfg["wired_relative_to"])
            if needle not in fragments:
                found.append(
                    Violation(
                        "unwired",
                        relative,
                        1,
                        f"{needle} is named by no platform.cmake",
                        "List it in the platform.cmake of every platform that compiles it, or delete it.",
                    )
                )
    return found


def check(root: Path, cfg: dict) -> tuple[list[Violation], int, int]:
    files, skipped = candidates(root, cfg)
    violations: list[Violation] = []
    for path in files:
        violations.extend(scan_file(root, path, cfg))
    violations.extend(check_wiring(root, cfg))
    return violations, len(files), skipped


def load_config(root: Path, name: str | None) -> dict:
    cfg = dict(DEFAULTS)
    path = Path(name) if name else root / "tools" / "platform-isolation.json"
    if not path.is_absolute():
        path = root / path
    if path.is_file():
        user = json.loads(path.read_text(encoding="utf-8"))
        unknown = sorted(set(user) - set(DEFAULTS))
        if unknown:
            raise ValueError(f"{path}: unknown key(s) {', '.join(unknown)}")
        cfg.update(user)
    elif name:
        raise FileNotFoundError(path)
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--config", help="settings file (default: tools/platform-isolation.json, if present)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    try:
        cfg = load_config(root, args.config)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if not (root / cfg["platform_dir"]).is_dir():
        print(f"error: no {cfg['platform_dir']}/ under '{root}'. Pass --root.", file=sys.stderr)
        return 2

    violations, scanned, skipped = check(root, cfg)
    if violations:
        print()
        print("Platform-isolation violation(s): platform-specific code outside the platform section,")
        print("or a platform CMake does not know about.")
        print()
        for v in violations:
            print(f"  [{v.rule}] {v.path}:{v.line}: {v.text}")
            print(f"::error file={v.path},line={v.line}::[{v.rule}] {v.hint}")
        print()
        print(f"{len(violations)} violation(s) found.")
        return 1

    note = f", {skipped} skipped as build output or git-ignored" if skipped else ""
    print(
        "OK: no platform code outside the platform section, no OS tests in CMake outside the "
        f"selector, and every platform file is wired ({scanned} files scanned{note})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
