# SPDX-License-Identifier: GPL-3.0-or-later
"""The glibc floor check, on a real binary built here (so it needs a Linux system with gcc and objdump)."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECK = Path(__file__).resolve().parents[2] / "actions" / "check-glibc-floor" / "check.sh"
ON_LINUX = sys.platform.startswith("linux") and all(shutil.which(t) for t in ("gcc", "objdump", "bash"))


def run(folder, allowed=None):
    args = ["bash", str(CHECK), str(folder)] + ([allowed] if allowed else [])
    return subprocess.run(args, capture_output=True, text=True)


@unittest.skipUnless(ON_LINUX, "needs Linux with gcc and objdump")
class GlibcFloor(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.root = Path(self.d.name)
        (self.root / "pkg").mkdir()
        (self.root / "hello.c").write_text('#include <stdio.h>\nint main(void){puts("hi");return 0;}\n')
        subprocess.run(["gcc", str(self.root / "hello.c"), "-o", str(self.root / "pkg" / "hello")], check=True)
        (self.root / "pkg" / "notes.txt").write_text("not an ELF file\n")

    def tearDown(self):
        self.d.cleanup()

    def test_passes_when_the_floor_is_high_enough(self):
        result = run(self.root / "pkg", "99.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("checked 1 files", result.stdout)

    def test_fails_when_a_file_needs_more_and_names_it(self):
        result = run(self.root / "pkg", "2.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("hello needs glibc", result.stderr)

    def test_the_default_floor_is_ubuntu_24_04(self):
        # A program built on this machine passes the default floor only if this machine's glibc is not newer than 2.39.
        result = run(self.root / "pkg")
        self.assertIn("against glibc 2.39", result.stdout + result.stderr)

    def test_a_folder_with_no_program_is_an_error(self):
        empty = self.root / "empty"
        empty.mkdir()
        (empty / "a.txt").write_text("x")
        self.assertNotEqual(run(empty, "99.0").returncode, 0)


if __name__ == "__main__":
    unittest.main()
