# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import precheck as p  # noqa: E402


def git(root, *a):
    subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)


class Precheck(unittest.TestCase):
    def test_exit_code_ignores_skip(self):
        self.assertEqual(p.exit_code([p.Result("a", "pass"), p.Result("b", "skip")]), 0)
        self.assertEqual(p.exit_code([p.Result("a", "fail")]), 1)

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "develop")
            git(root, "config", "user.name", "T")
            git(root, "config", "user.email", "t@example.com")
            (root / "README.md").write_text("x\n")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "init")
            git(root, "checkout", "-q", "-b", "feature/x")
            (root / "docs").mkdir()
            (root / "docs/a.md").write_text("doc\n")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "Add doc")
            res = subprocess.run([sys.executable, str(HERE / "precheck.py"), "--root", str(root), "--base", "develop"],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("docs_only=true", res.stdout)
            self.assertNotIn("NOTE", res.stdout)
            (root / "docs/b.md").write_text("uncommitted\n")
            res = subprocess.run([sys.executable, str(HERE / "precheck.py"), "--root", str(root), "--base", "develop"],
                                 capture_output=True, text=True)
            self.assertIn("NOTE  the checks read committed work only: 1 path(s) have uncommitted changes", res.stdout)
            (root / "docs/b.md").unlink()
            git(root, "commit", "-q", "--allow-empty", "-m", "Fix\n\nBody.\n\nCo-Authored-By: X <x@y.z>")
            res = subprocess.run([sys.executable, str(HERE / "precheck.py"), "--root", str(root), "--base", "develop"],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            self.assertIn("FAIL  commit text", res.stdout)


if __name__ == "__main__":
    unittest.main()
