# SPDX-License-Identifier: GPL-3.0-or-later
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_needs as c  # noqa: E402


def needs(**kw):
    return {k: {"result": v} for k, v in kw.items()}


class Evaluate(unittest.TestCase):
    def test_all_success(self):
        self.assertEqual(c.evaluate(needs(a="success", b="success"), {}), [])

    def test_failure_and_cancelled_fail(self):
        self.assertEqual(len(c.evaluate(needs(a="failure", b="cancelled"), {})), 2)

    def test_skipped_but_expected_fails(self):
        self.assertEqual(len(c.evaluate(needs(build="skipped"), {"build": True})), 1)

    def test_skipped_and_not_expected_passes(self):
        self.assertEqual(c.evaluate(needs(build="skipped", policy="success"), {"build": False}), [])

    def test_expected_job_missing_from_needs_fails(self):
        self.assertEqual(c.evaluate(needs(policy="success"), {"macos": True}), ["macos: no result, but the plan asked for it"])

    def test_unexpected_job_missing_from_needs_passes(self):
        self.assertEqual(c.evaluate(needs(policy="success"), {"macos": False}), [])

    def test_unlisted_job_is_expected(self):
        self.assertEqual(len(c.evaluate(needs(x="skipped"), {})), 1)


REUSED = {"coverage": {"run_id": 42, "event": "pull_request", "tested_sha": "0241cdd5" + "0" * 32, "delta": 2,
                       "kind": "delta", "url": "https://x/42"}}


class Reused(unittest.TestCase):
    def test_a_reused_group_may_be_skipped(self):
        n = needs(reuse="success", coverage="skipped")
        self.assertEqual(c.evaluate(n, {"coverage": True}, REUSED), [])

    def test_a_reused_group_that_is_absent_is_fine(self):
        self.assertEqual(c.evaluate(needs(reuse="success"), {"coverage": True}, REUSED), [])

    def test_a_reused_group_that_ran_and_failed_still_fails(self):
        self.assertEqual(len(c.evaluate(needs(reuse="success", coverage="failure"), {}, REUSED)), 1)

    def test_reused_is_ignored_when_the_reuse_job_did_not_succeed(self):
        for result in ("failure", "cancelled", "skipped"):
            n = needs(reuse=result, coverage="skipped")
            self.assertIn("coverage: skipped, but the plan asked for it", c.evaluate(n, {"coverage": True}, REUSED), result)

    def test_reused_is_ignored_without_a_reuse_job(self):
        self.assertEqual(len(c.evaluate(needs(coverage="skipped"), {"coverage": True}, REUSED)), 1)

    def test_other_groups_are_still_checked(self):
        n = needs(reuse="success", coverage="skipped", build="skipped")
        self.assertEqual(c.evaluate(n, {"build": True, "coverage": True}, REUSED),
                         ["build: skipped, but the plan asked for it"])

    def test_cli_writes_notice_and_summary(self):
        import contextlib
        import io
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            summary = Path(d) / "s.md"
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}), contextlib.redirect_stdout(out):
                code = c.main(["--needs", json.dumps(needs(reuse="success", coverage="skipped")),
                               "--expected", '{"coverage": true}', "--reused", json.dumps(REUSED)])
            self.assertEqual(code, 0)
            self.assertIn("::notice::coverage reused from run 42 (pull_request, tested 0241cdd5, delta 2 file(s)",
                          out.getvalue())
            self.assertIn("| coverage | [42](https://x/42) |", summary.read_text(encoding="utf-8"))

    def test_cli_with_bad_json_ignores_it(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(c.main(["--needs", json.dumps(needs(a="success")), "--reused", "nope"]), 0)


if __name__ == "__main__":
    unittest.main()
