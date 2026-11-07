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


GROUPS_CFG = dict(g.DEFAULT, groups={
    "build-fast": {"home": "pull_request", "skips": ["libs/*/src/platform/{macos,ios}/**", "**/*.mm"]},
    "build-macos": {"home": "post_merge", "skips": ["libs/*/src/platform/{linux,windows}/**"],
                    "promote": ["libs/*/src/platform/macos/**", "**/*.mm"]},
})
BOTH = ["build-fast", "build-macos"]


class Groups(unittest.TestCase):
    def asked(self, paths, cfg=GROUPS_CFG):
        return g.groups_plan(paths, cfg)

    def test_documentation_asks_for_nothing(self):
        self.assertEqual(self.asked(["docs/a.md", ".github/CODEOWNERS"])["groups"], [])

    def test_shared_code_asks_for_every_group(self):
        self.assertEqual(self.asked(["libs/core/src/a.cpp"])["groups"], BOTH)

    def test_skip_list_leaves_a_group_out(self):
        r = self.asked(["libs/core/src/platform/macos/a.cpp"])
        self.assertEqual((r["groups"], r["promoted"]), (["build-macos"], ["build-macos"]))
        self.assertEqual(self.asked(["libs/core/src/platform/linux/a.cpp"])["groups"], ["build-fast"])

    def test_one_unskipped_path_asks(self):
        r = self.asked(["libs/core/src/platform/linux/a.cpp", "libs/core/src/b.cpp"])
        self.assertEqual(r["groups"], BOTH)

    def test_unrecognised_path_asks_for_every_group_without_a_skip(self):
        self.assertEqual(self.asked(["weird/thing.bin"])["groups"], BOTH)

    def test_barrier_and_machinery_ask_for_everything(self):
        for path in ("cmake/IclX.cmake", "vcpkg.json", ".github/ci/plan.json", "tools/sanitizers/tsan.supp"):
            self.assertEqual(self.asked(["libs/core/src/platform/linux/a.cpp", path])["groups"], BOTH, path)

    def test_empty_list_asks_for_everything(self):
        self.assertEqual(self.asked([])["groups"], BOTH)

    def test_no_groups_configured(self):
        self.assertEqual(self.asked(["libs/a.cpp"], g.DEFAULT), {"groups": [], "promoted": []})

    def test_consumer_cannot_remove_the_mandatory_barrier(self):
        r = g.reuse_config(dict(GROUPS_CFG, reuse={"barrier": ["extra"], "max_age_hours": 12}))
        self.assertEqual(r["max_age_hours"], 12)
        for path in g.MANDATORY_BARRIER + ["extra"]:
            self.assertIn(path, r["barrier"])
        self.assertNotIn("cmake", r["barrier"])

    def test_reuse_defaults(self):
        r = g.reuse_config(g.DEFAULT)
        self.assertEqual(r["max_age_hours"], 48)
        self.assertIn("vcpkg.json", r["barrier"])

    def test_cli_prints_groups_lines_only_when_asked(self):
        import contextlib
        import io
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "plan.json"
            cfg.write_text('{"groups": {"a": {"skips": ["x/**"]}}}', encoding="utf-8")
            for flag, expect in (([], False), (["--groups"], True)):
                out = io.StringIO()
                with mock.patch("sys.stdin", io.StringIO("x/1.cpp\n")), contextlib.redirect_stdout(out):
                    g.main(["--config", str(cfg), *flag])
                self.assertEqual("groups=" in out.getvalue(), expect)
                if expect:
                    self.assertIn("groups=[]", out.getvalue())


if __name__ == "__main__":
    unittest.main()
