# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_action_pinning as pin  # noqa: E402
import check_branch_name as branch  # noqa: E402
import check_changelog_fragment as frag  # noqa: E402
import check_text_policy as text  # noqa: E402

SHA = "a" * 40


class TextPolicy(unittest.TestCase):
    def test_clean_message(self):
        self.assertEqual(text.check_message("Fix the parser\n\nHandles empty input.", "m"), [])

    def test_signed_off_by_allowed(self):
        self.assertEqual(text.check_message("Fix\n\nBody.\n\nSigned-off-by: A B <a@b.c>", "m"), [])

    def test_coauthor_rejected(self):
        self.assertTrue(text.check_message("Fix\n\nBody.\n\nCo-Authored-By: X <x@y.z>", "m"))

    def test_other_trailer_rejected(self):
        problems = text.check_message("Fix\n\nBody.\n\nReviewed-by: X <x@y.z>", "m")
        self.assertTrue(any("not allowed" in p for p in problems))

    def test_generated_line_and_tool_names(self):
        self.assertTrue(text.check_message("Fix\n\nGenerated with a tool", "m"))
        self.assertTrue(text.check_message("Fix with Claude", "m"))
        self.assertTrue(text.check_message("Fix\n\n\U0001F916 done", "m"))

    def test_word_boundaries(self):
        self.assertEqual(text.check_message("Fix the codex of rules", "m") != [], True)  # 'codex' is a listed name
        self.assertEqual(text.check_message("Adjust Geminid spacing", "m"), [])


class Pinning(unittest.TestCase):
    def scan(self, body):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.yml"
            p.write_text(body)
            return pin.scan(p)

    def test_pinned_passes(self):
        problems, warnings = self.scan(f"steps:\n  - uses: actions/checkout@{SHA} # v7.0.1\n")
        self.assertEqual((problems, warnings), ([], []))

    def test_tag_fails(self):
        problems, _ = self.scan("steps:\n  - uses: actions/checkout@v4\n")
        self.assertEqual(len(problems), 1)

    def test_local_and_docker(self):
        self.assertEqual(self.scan("steps:\n  - uses: ./.github/actions/x\n")[0], [])
        self.assertEqual(self.scan("steps:\n  - uses: $/actions/x\n")[0], [])
        self.assertEqual(len(self.scan("steps:\n  - uses: docker://alpine:3\n")[0]), 1)

    def test_missing_comment_warns(self):
        problems, warnings = self.scan(f"steps:\n  - uses: a/b@{SHA}\n")
        self.assertEqual((problems, len(warnings)), ([], 1))

    def test_reusable_workflow_call(self):
        problems, _ = self.scan("jobs:\n  x:\n    uses: o/r/.github/workflows/w.yml@main\n")
        self.assertEqual(len(problems), 1)


class Branch(unittest.TestCase):
    def test_names(self):
        for good in ("develop", "main", "feature/a-b", "agent/fix-parser/part-2", "release/1.2",
                     "dependabot/npm/x", "gh-readonly-queue/develop/pr-1"):
            self.assertTrue(branch.ok(good), good)
        for bad in ("Feature/A", "fix/x", "feature/", "feature/a_b", "release/1", "wip"):
            self.assertFalse(branch.ok(bad), bad)


class Fragment(unittest.TestCase):
    GOOD = "**Parser accepts empty input.** It returns an empty list."

    def test_valid(self):
        self.assertEqual(frag.check({"changelog.d/empty-input.fixed.md": self.GOOD}, ["src/a.cpp"], False), [])

    def test_missing_for_source_change(self):
        self.assertEqual(len(frag.check({}, ["src/a.cpp"], False)), 1)

    def test_label_waives(self):
        self.assertEqual(frag.check({}, ["src/a.cpp"], True), [])

    def test_docs_only_needs_none(self):
        self.assertEqual(frag.check({}, ["docs/a.md", ".github/workflows/x.yml"], False), [])

    def test_bad_name_and_shape(self):
        self.assertTrue(frag.check({"changelog.d/x.md": self.GOOD}, [], False))
        self.assertTrue(frag.check({"changelog.d/x.fixed.md": "no bold"}, [], False))
        self.assertTrue(frag.check({"changelog.d/x.fixed.md": "**a**\n\nb"}, [], False))

    def test_changelog_edit_rejected(self):
        self.assertTrue(frag.check({}, ["CHANGELOG.md"], True))


if __name__ == "__main__":
    unittest.main()
