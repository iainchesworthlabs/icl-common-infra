# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "nightly_report.sh"


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


@unittest.skipUnless(BASH and shutil.which("jq"), "needs bash and jq")
class Report(unittest.TestCase):
    def run_report(self, needs, **env):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        summary = Path(tmp.name) / "summary.md"
        full_env = {
            **os.environ,
            "REPO": "o/r",
            "RUN_URL": "https://example.invalid/run/1",
            "NEEDS_JSON": json.dumps({name: {"result": result} for name, result in needs.items()}),
            "GATING_JOBS": "sanitizers full-ci",
            "INFORMATIONAL_JOBS": "sanitizers-app",
            "DRY_RUN": "1",
            "GITHUB_STEP_SUMMARY": summary.as_posix(),
            **env,
        }
        done = subprocess.run([BASH, SCRIPT.as_posix()], env=full_env, capture_output=True, text=True, check=False)
        text = summary.read_text(encoding="utf-8") if summary.exists() else ""
        return done, text

    def test_all_green_has_no_failures(self):
        done, text = self.run_report({"sanitizers": "success", "full-ci": "success", "sanitizers-app": "success"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("gating failures: 0, informational: 0", done.stdout)
        self.assertIn("### Nightly on develop", text)
        self.assertNotIn("Gating, red", text)

    def test_a_red_gating_job_is_listed(self):
        done, text = self.run_report({"sanitizers": "failure", "full-ci": "success", "sanitizers-app": "success"})
        self.assertIn("gating failures: 1, informational: 0", done.stdout)
        self.assertIn("**Gating, red:** sanitizers (failure)", text)

    def test_a_red_informational_job_does_not_gate(self):
        done, text = self.run_report({"sanitizers": "success", "full-ci": "success", "sanitizers-app": "failure"})
        self.assertIn("gating failures: 0, informational: 1", done.stdout)
        self.assertIn("**Informational, red:** sanitizers-app (failure)", text)
        self.assertNotIn("Gating, red", text)

    def test_a_job_that_did_not_run_is_skipped_not_red(self):
        done, _ = self.run_report({"sanitizers": "success"})
        self.assertIn("gating failures: 0, informational: 0", done.stdout)

    def test_branch_names_the_heading(self):
        _, text = self.run_report({"sanitizers": "success", "full-ci": "success"}, BRANCH="main")
        self.assertIn("### Nightly on main", text)


if __name__ == "__main__":
    unittest.main()
