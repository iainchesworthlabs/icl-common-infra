# SPDX-License-Identifier: GPL-3.0-or-later
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "retry.sh"


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


@unittest.skipUnless(BASH, "needs bash")
class Retry(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.counter = self.dir / "count"

    def flaky(self, fail_times):
        """A command that fails `fail_times` times, then succeeds; it counts its runs."""
        counter = self.counter.as_posix()
        return (
            f'n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "{counter}"; '
            f'[ "$n" -gt {fail_times} ] || exit 7'
        )

    def run_retry(self, *args):
        return subprocess.run([BASH, SCRIPT.as_posix(), *args], capture_output=True, text=True, check=False)

    def runs(self):
        return int(self.counter.read_text().strip())

    def test_succeeds_after_transient_failures(self):
        done = self.run_retry("--attempts", "4", "--delay", "0", "--", "bash", "-c", self.flaky(2))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.runs(), 3)
        self.assertEqual(done.stdout.count("::warning::"), 2)

    def test_gives_up_with_the_commands_status(self):
        done = self.run_retry("--attempts", "3", "--delay", "0", "--", "bash", "-c", self.flaky(10))
        self.assertEqual(done.returncode, 7)
        self.assertEqual(self.runs(), 3)
        self.assertIn("giving up", done.stderr)

    def test_first_success_runs_once(self):
        done = self.run_retry("--delay", "0", "--", "bash", "-c", self.flaky(0))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.runs(), 1)
        self.assertNotIn("::warning::", done.stdout)

    def test_cleanup_path_is_removed_before_a_retry(self):
        partial = self.dir / "partial"
        partial_posix = partial.as_posix()
        command = f'[ ! -e "{partial_posix}" ] && exit 0; exit 1'
        partial.mkdir()
        done = self.run_retry("--attempts", "2", "--delay", "0", "--cleanup", partial_posix, "--", "bash", "-c", command)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(partial.exists())

    def test_needs_a_command(self):
        self.assertEqual(self.run_retry("--").returncode, 2)


if __name__ == "__main__":
    unittest.main()
