# SPDX-License-Identifier: GPL-3.0-or-later
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

    def test_unlisted_job_is_expected(self):
        self.assertEqual(len(c.evaluate(needs(x="skipped"), {})), 1)


if __name__ == "__main__":
    unittest.main()
