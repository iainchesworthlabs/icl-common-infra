# SPDX-License-Identifier: GPL-3.0-or-later
"""Shell steps and scripts do not pipe a command into `head`.

`shell: bash` runs a step with `-eo pipefail`, and most of the scripts here set it themselves. A
command that is still writing after `head` has read its lines gets SIGPIPE, the pipeline's status is
141, and the step fails. Whether it does depends on the timing of the writer, so it fails at random:
the setup-vcpkg bootstrap step did it on hosted and self-hosted Linux runners from v0.1.21 on.

Capture the output in a variable and take the lines from the variable instead:

    out="$(tool --version)"
    head -n 1 <<< "$out"

A line that ends in `|| true` throws the status away and may keep the pipe.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
PIPE_INTO_HEAD = re.compile(r"\|\s*head\b")


def find_bash():
    """bash, and on Windows Git's: the bash.exe on PATH there may be the WSL launcher."""
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            candidate = Path(base) / "Git" / "bin" / "bash.exe"
            if base and candidate.is_file():
                return str(candidate)
        return None
    return shutil.which("bash")


BASH = find_bash()


def shell_sources():
    """Every file that holds shell: workflows, actions, scripts and the files that carry them."""
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith((".yml", ".yaml", ".sh")):
                yield Path(folder) / name


def step_script(action: Path, step: str) -> str:
    """The `run:` script of one step of a composite action, as bash receives it."""
    text = action.read_text(encoding="utf-8")
    block = re.search(rf"(?m)^    - name: {re.escape(step)}\n(.*?)(?=^    (?:#|- )|\Z)", text, re.S)
    assert block, step
    run = re.search(r"(?m)^      run: [|>][^\n]*\n((?:        .*\n|\n)+)", block.group(1))
    assert run, step
    return textwrap.dedent(run.group(1))


class NoPipeIntoHead(unittest.TestCase):
    def test_no_shell_pipes_into_head(self):
        found = []
        for path in shell_sources():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#") or "|| true" in line:
                    continue
                if PIPE_INTO_HEAD.search(line):
                    found.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}")
        self.assertEqual(
            found, [], "a pipe into head fails under pipefail when the writer outlives head (SIGPIPE); "
            "capture the output in a variable and use `head -n N <<< \"$out\"`")


@unittest.skipUnless(BASH, "needs bash")
class BootstrapVcpkg(unittest.TestCase):
    """The step that runs the cached vcpkg tool prints its first line and exits 0 when the tool
    keeps writing after that line."""

    ACTION = ROOT / "actions" / "setup-vcpkg" / "action.yml"

    # The first line at once, the rest after a pause, as vcpkg's licence notice follows its
    # version line. A reader that stops after one line has closed the pipe by then.
    FAKE_TOOL = textwrap.dedent("""\
        #!/usr/bin/env bash
        echo "vcpkg package management program version 2099-01-01-fake"
        sleep 0.3
        for i in $(seq 1 400); do echo "See LICENSE.txt for license information. ($i)"; done
        """)

    def test_cached_tool_that_keeps_writing_does_not_fail_the_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            vcpkg = Path(tmp) / "vcpkg"
            tool = home / ".cache" / "vcpkg" / "tool" / "vcpkg"
            tool.parent.mkdir(parents=True)
            vcpkg.mkdir()
            tool.write_text(self.FAKE_TOOL, encoding="utf-8", newline="\n")
            script = Path(tmp) / "bootstrap.sh"
            script.write_text(step_script(self.ACTION, "Bootstrap vcpkg"), encoding="utf-8", newline="\n")
            env = dict(os.environ, HOME=home.as_posix(), VCPKG_DIR=vcpkg.as_posix(), TOOL="vcpkg",
                       RETRY="/nonexistent/retry.sh", RUNNER_OS="Linux")
            done = subprocess.run([BASH, "-eo", "pipefail", script.as_posix()], env=env,
                                  capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertIn("vcpkg tool restored from the Actions cache; no bootstrap download", lines)
        self.assertIn("vcpkg package management program version 2099-01-01-fake", lines)
        self.assertFalse([ln for ln in lines if "LICENSE" in ln], "only the first line is printed")


if __name__ == "__main__":
    unittest.main()
