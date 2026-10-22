# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coverage_gate as g  # noqa: E402


def file(name, covered, total, bcov=0, btotal=0):
    lines = [{"line_number": i, "count": 1 if i < covered else 0,
              "branches": [{"count": 1 if j < bcov else 0} for j in range(btotal)] if i == 0 else []}
             for i in range(total)]
    return {"file": name, "lines": lines}


class Gate(unittest.TestCase):
    FLOORS = {"default": {"line": 90, "branch": 80},
              "components": {"libs/core": {}, "libs/legacy": {"line": 60, "branch": 40}}}

    def test_pass(self):
        report = {"files": [file("libs/core/a.cpp", 95, 100, 9, 10), file("libs/legacy/b.cpp", 70, 100, 5, 10)]}
        _, problems, _, _ = g.evaluate(report, self.FLOORS)
        self.assertEqual(problems, [])

    def test_below_floor_fails(self):
        report = {"files": [file("libs/core/a.cpp", 80, 100, 9, 10)]}
        _, problems, _, _ = g.evaluate(report, self.FLOORS)
        self.assertTrue(any("statement coverage 80.0%" in p for p in problems))

    def test_branch_below_floor_fails(self):
        report = {"files": [file("libs/core/a.cpp", 100, 100, 5, 10)]}
        _, problems, _, _ = g.evaluate(report, self.FLOORS)
        self.assertTrue(any("branch coverage 50.0%" in p for p in problems))

    def test_unassigned_file_fails(self):
        report = {"files": [file("libs/core/a.cpp", 100, 100, 10, 10), file("apps/x/y.cpp", 1, 1)]}
        _, problems, _, _ = g.evaluate(report, self.FLOORS)
        self.assertEqual(problems, ["apps/x/y.cpp: not covered by any component in the floors file"])

    def test_ratchet_hint(self):
        report = {"files": [file("libs/legacy/b.cpp", 90, 100, 9, 10)]}
        _, problems, hints, _ = g.evaluate(report, self.FLOORS)
        self.assertEqual(problems, [])
        self.assertTrue(any("raise the floor" in h for h in hints))

    def test_longest_prefix_wins(self):
        floors = {"components": {"libs": {"line": 90}, "libs/legacy": {"line": 10, "branch": 0}}}
        report = {"files": [file("libs/legacy/b.cpp", 20, 100)]}
        _, problems, _, _ = g.evaluate(report, floors)
        self.assertEqual(problems, [])

    def test_excluded_lines_ignored(self):
        f = {"file": "libs/core/a.cpp", "lines": [{"line_number": 1, "count": 1}, {"line_number": 2, "count": 0, "gcovr/excluded": True}]}
        rows, problems, _, _ = g.evaluate({"files": [f]}, {"components": {"libs/core": {}}})
        self.assertEqual(problems, [])
        self.assertEqual(rows[0][1], 100.0)


if __name__ == "__main__":
    unittest.main()
