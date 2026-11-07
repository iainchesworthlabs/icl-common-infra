# SPDX-License-Identifier: GPL-3.0-or-later
import json
import sys
import tempfile
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


class FloorFiles(unittest.TestCase):
    def tree(self, d, root_floors, component_floors):
        root = Path(d)
        (root / "tools").mkdir()
        (root / "tools" / "coverage-floors.json").write_text(json.dumps(root_floors), encoding="utf-8")
        for comp, content in component_floors.items():
            (root / comp).mkdir(parents=True)
            (root / comp / "coverage-floor.json").write_text(json.dumps(content), encoding="utf-8")
        return root

    def load(self, root):
        return g.load_floors(root / "tools" / "coverage-floors.json",
                             ["libs/*/coverage-floor.json", "apps/*/coverage-floor.json"], root)

    def test_component_files_are_merged_in(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {"default": {"line": 90, "branch": 80}},
                             {"libs/core": {"line": 95, "branch": 85}, "apps/app": {}})
            floors, sources, problems = self.load(root)
        self.assertEqual(problems, [])
        self.assertEqual(floors["components"], {"libs/core": {"line": 95, "branch": 85}, "apps/app": {}})
        self.assertEqual(sorted(sources), ["apps/app", "libs/core"])

    def test_a_component_in_both_places_is_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {"components": {"libs/core": {}}}, {"libs/core": {"line": 95}})
            _, _, problems = self.load(root)
        self.assertEqual(len(problems), 1)
        self.assertIn("libs/core: has more than one floor", problems[0])

    def test_a_bad_file_is_a_problem_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {}, {"libs/core": {}})
            (root / "libs" / "core" / "coverage-floor.json").write_text("{", encoding="utf-8")
            _, _, problems = self.load(root)
        self.assertEqual(len(problems), 1)

    def run_main(self, root, report, *extra):
        rep = root / "coverage.json"
        rep.write_text(json.dumps(report), encoding="utf-8")
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return g.main(["--report", str(rep), "--floors", str(root / "tools" / "coverage-floors.json"),
                           "--floors-glob", "libs/*/coverage-floor.json", "--root", str(root), *extra])

    def test_the_gate_uses_the_component_floor(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {"default": {"line": 90, "branch": 80}}, {"libs/core": {"line": 99, "branch": 0}})
            self.assertEqual(self.run_main(root, {"files": [file("libs/core/a.cpp", 95, 100)]}), 1)
            self.assertEqual(self.run_main(root, {"files": [file("libs/core/a.cpp", 99, 100)]}), 0)

    def test_a_file_outside_every_component_still_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {}, {"libs/core": {}})
            self.assertEqual(self.run_main(root, {"files": [file("libs/new/a.cpp", 100, 100)]}), 1)

    def test_write_floors_goes_to_the_component_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {"default": {"line": 90, "branch": 80}}, {"libs/core": {"line": 90, "branch": 80}})
            self.assertEqual(self.run_main(root, {"files": [file("libs/core/a.cpp", 97, 100, 9, 10)]}, "--write-floors"), 0)
            own = json.loads((root / "libs" / "core" / "coverage-floor.json").read_text(encoding="utf-8"))
            top = json.loads((root / "tools" / "coverage-floors.json").read_text(encoding="utf-8"))
        self.assertEqual(own, {"line": 97, "branch": 90})
        self.assertNotIn("libs/core", top["components"])

    def test_without_globs_nothing_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.tree(d, {"components": {"libs/core": {}}}, {})
            floors, sources, problems = g.load_floors(root / "tools" / "coverage-floors.json", [], root)
        self.assertEqual((floors["components"], sources, problems), ({"libs/core": {}}, {}, []))


if __name__ == "__main__":
    unittest.main()
