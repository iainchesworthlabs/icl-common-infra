# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks of the token permissions of the reusable codeql.yml and of the caller block that
docs/using.md tells a caller to write.

The CodeQL action reads the workflow run through the API, and a private repository refuses that with
"Resource not accessible by integration" unless the token has `actions: read`. A called job cannot
have more than its caller grants, so the workflow and the documented caller block must name the same
permissions: when they drift apart, the caller's run fails to start or fails in the action."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
USING = (ROOT / "docs" / "using.md").read_text(encoding="utf-8")

NEEDED = {
    "security-events": "write",  # analyze uploads the results
    "contents": "read",  # the checkout
    "actions": "read",  # the CodeQL action reads this workflow run
    "issues": "write",  # the nightly-analysis issue
}


def permissions_block(text: str, indent: int) -> dict[str, str]:
    """The `permissions:` mapping that sits at `indent` spaces, with trailing comments removed."""
    pad = " " * indent
    match = re.search(rf"(?m)^{pad}permissions:\n((?:{pad}  \S.*\n)+)", text)
    assert match, f"no permissions block at indent {indent}"
    granted = {}
    for line in match.group(1).splitlines():
        key, _, value = line.strip().partition(":")
        granted[key] = value.split("#")[0].strip()
    return granted


class CodeqlPermissions(unittest.TestCase):
    def test_the_workflow_grants_nothing_at_the_top(self):
        self.assertRegex(WORKFLOW, r"(?m)^permissions: \{\}$")

    def test_the_analyze_job_has_the_permissions_the_action_needs_and_no_more(self):
        self.assertEqual(permissions_block(WORKFLOW, 4), NEEDED)

    def test_the_job_has_only_the_one_block(self):
        self.assertEqual(len(re.findall(r"(?m)^ +permissions:", WORKFLOW)), 1)

    def test_the_documented_caller_grants_the_same_permissions(self):
        section = re.search(r"(?ms)^## CodeQL permissions\n(.*?)(?=^## )", USING)
        self.assertIsNotNone(section, "docs/using.md has no 'CodeQL permissions' section")
        caller = re.search(r"(?ms)^```yaml\n(.*?)^```", section.group(1))
        self.assertIsNotNone(caller, "the section has no caller example")
        self.assertIn("/.github/workflows/codeql.yml@", caller.group(1))
        self.assertRegex(caller.group(1), r"(?m)^permissions: \{\}$")
        self.assertEqual(permissions_block(caller.group(1), 4), NEEDED)

    def test_the_docs_say_the_caller_must_grant_them(self):
        section = re.search(r"(?ms)^## CodeQL permissions\n(.*?)(?=^## )", USING).group(1)
        self.assertIn("The calling job must therefore grant the same four", section)
        for name, level in NEEDED.items():
            self.assertIn(f"`{name}: {level}`", section)


if __name__ == "__main__":
    unittest.main()
