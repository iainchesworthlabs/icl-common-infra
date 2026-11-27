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

    def precheck_on_branch(self, branch, prefixes=None):
        """Run precheck on a repository whose one commit is on `branch`; `prefixes` is the text of .github/branch-prefixes.txt."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "develop")
            git(root, "config", "user.name", "T")
            git(root, "config", "user.email", "t@example.com")
            (root / "README.md").write_text("x\n")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "init")
            git(root, "checkout", "-q", "-b", branch)
            if prefixes is not None:
                (root / ".github").mkdir()
                (root / ".github/branch-prefixes.txt").write_text(prefixes)
            (root / "docs").mkdir()
            (root / "docs/a.md").write_text("doc\n")
            git(root, "add", ".")
            git(root, "commit", "-q", "-m", "Add doc")
            return subprocess.run([sys.executable, str(HERE / "precheck.py"), "--root", str(root), "--base", "develop"],
                                  capture_output=True, text=True)

    def test_branch_prefixes_of_the_project_are_allowed(self):
        # check_branch_name.py, which the policy workflow runs, reads .github/branch-prefixes.txt; precheck says it runs the
        # same checks, so a branch that the workflow allows must not fail it.
        res = self.precheck_on_branch("spike/try-it", "# ours\nspike\n")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("PASS  branch name", res.stdout)

    def test_a_prefix_that_the_project_did_not_add_is_refused(self):
        res = self.precheck_on_branch("spike/try-it")
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL  branch name", res.stdout)
        res = self.precheck_on_branch("spike/try-it", "other\n")
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL  branch name", res.stdout)

    def test_a_bad_prefix_file_fails_the_branch_check(self):
        res = self.precheck_on_branch("spike/try-it", "Spike\n")
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAIL  branch name", res.stdout)
        self.assertIn("branch-prefixes.txt: line 1: 'Spike' is not a lower-case word", res.stdout)

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
