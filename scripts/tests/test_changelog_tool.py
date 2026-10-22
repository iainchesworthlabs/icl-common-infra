# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import changelog_tool as t  # noqa: E402


class Tool(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.root = Path(self.d.name)
        (self.root / "changelog.d").mkdir()
        (self.root / "changelog.d/README.md").write_text("readme")
        (self.root / "changelog.d/a.fixed.md").write_text("**Fix A.** Details.\n")
        (self.root / "changelog.d/b.added.md").write_text("**Add B.** Details.\n")

    def tearDown(self):
        self.d.cleanup()

    def test_assemble_groups_and_deletes(self):
        self.assertEqual(t.assemble(self.root, "1.0.0", "2026-10-22"), 0)
        text = (self.root / "CHANGELOG.md").read_text()
        self.assertLess(text.index("### Added"), text.index("### Fixed"))
        self.assertIn("- **Add B.** Details.", text)
        self.assertFalse((self.root / "changelog.d/a.fixed.md").exists())
        self.assertTrue((self.root / "changelog.d/README.md").exists())

    def test_second_release_goes_above_first(self):
        t.assemble(self.root, "1.0.0", "2026-10-22")
        (self.root / "changelog.d/c.changed.md").write_text("**Change C.** Details.\n")
        t.assemble(self.root, "1.1.0", "2026-11-01")
        text = (self.root / "CHANGELOG.md").read_text()
        self.assertLess(text.index("[1.1.0]"), text.index("[1.0.0]"))

    def test_duplicate_version_and_no_fragments_fail(self):
        t.assemble(self.root, "1.0.0", "2026-10-22")
        self.assertEqual(t.assemble(self.root, "1.0.0", "2026-10-22"), 1)

    def test_notes(self):
        t.assemble(self.root, "1.0.0", "2026-10-22")
        self.assertEqual(t.notes(self.root, "1.0.0"), 0)
        self.assertEqual(t.notes(self.root, "9.9.9"), 1)


if __name__ == "__main__":
    unittest.main()
