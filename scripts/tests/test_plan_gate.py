# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_gate as g  # noqa: E402

CFG = g.DEFAULT


class Plan(unittest.TestCase):
    def test_docs_only(self):
        r = g.plan(["docs/a.md", "README.md", "changelog.d/x.fixed.md"], CFG)
        self.assertEqual((r["docs_only"], r["build"], r["gui"]), ("true", "false", "false"))

    def test_library_change_builds_without_qt(self):
        r = g.plan(["libs/core/src/a.cpp"], CFG)
        self.assertEqual((r["build"], r["gui"]), ("true", "false"))
        self.assertEqual(r["reason"], "libs/core/src/a.cpp")

    def test_gui_change_pulls_qt(self):
        r = g.plan(["apps/main/qml/Main.qml"], CFG)
        self.assertEqual((r["build"], r["gui"]), ("true", "true"))

    def test_top_level_build_file_pulls_qt(self):
        self.assertEqual(g.plan(["vcpkg.json"], CFG)["gui"], "true")

    def test_no_build_paths_do_nothing(self):
        r = g.plan([".github/CODEOWNERS", ".github/labels.yml"], CFG)
        self.assertEqual((r["build"], r["docs_only"]), ("false", "false"))

    def test_machinery_builds_everything(self):
        r = g.plan([".github/workflows/ci.yml"], CFG)
        self.assertEqual((r["machinery"], r["build"], r["gui"]), ("true", "true", "true"))

    def test_unrecognised_path_builds_everything(self):
        r = g.plan(["weird/thing.bin"], CFG)
        self.assertEqual((r["build"], r["gui"]), ("true", "true"))
        self.assertIn("unrecognised", r["reason"])

    def test_empty_list_builds_everything(self):
        self.assertEqual(g.plan([], CFG)["build"], "true")

    def test_mixed_docs_and_code(self):
        r = g.plan(["docs/a.md", "src/x.cpp"], CFG)
        self.assertEqual((r["docs_only"], r["build"], r["gui"]), ("false", "true", "false"))


if __name__ == "__main__":
    unittest.main()
