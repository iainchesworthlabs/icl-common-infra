# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks of the `runner` input of the reusable workflows: a caller can route every job
of a workflow to its own runners, and the default is the hosted ubuntu-24.04 job every caller had
before the input existed. A reusable workflow that hard-codes a runner must be named here, with the
reason, so that a new one cannot do it by accident."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

ROUTED = "${{ fromJSON(inputs.runner) }}"
DEFAULT = """'["ubuntu-24.04"]'"""

# Reusable workflows whose jobs all run on the runner the caller names.
ROUTABLE = (
    "codeql.yml",
    "dependabot-auto-merge.yml",
    "docs-deploy-aws.yml",
    "docs-deploy.yml",
    "docs.yml",
    "policy.yml",
    "zizmor.yml",
)
# Reusable workflows that choose the runner some other way.
OTHER = {
    "build.yml": "each leg names its runner (`runner` in the leg)",
    "release-publish.yml": "holds the signing key and the release bot; a hosted runner until the owner decides",
}
JOBS_WITH_A_RUNNER = {
    "codeql.yml": 1,
    "dependabot-auto-merge.yml": 1,
    "docs-deploy-aws.yml": 2,
    "docs-deploy.yml": 1,
    "docs.yml": 1,
    "policy.yml": 1,
    "zizmor.yml": 1,
}


def reusable() -> list[str]:
    return sorted(p.name for p in WORKFLOWS.glob("*.yml")
                  if re.search(r"(?m)^  workflow_call:", p.read_text(encoding="utf-8")))


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def runner_input(name: str) -> str:
    """The lines of the `runner` input of a workflow_call."""
    match = re.search(r"(?m)^      runner:\n((?:        .*\n)+)", text(name))
    assert match, f"{name} has no `runner` input"
    return match.group(1)


class RunnerInput(unittest.TestCase):
    def test_every_reusable_workflow_is_accounted_for(self):
        self.assertEqual(reusable(), sorted(ROUTABLE + tuple(OTHER)))

    def test_the_input_is_a_string_that_defaults_to_the_hosted_runner(self):
        for name in ROUTABLE:
            lines = runner_input(name).splitlines()
            self.assertIn("        type: string", lines, name)
            self.assertIn(f"        default: {DEFAULT}", lines, name)

    def test_the_input_is_described_the_same_way_in_each_workflow(self):
        # codeql.yml had the input before it had the description.
        for name in set(ROUTABLE) - {"codeql.yml"}:
            self.assertIn("        description: JSON array of runner labels.", runner_input(name).splitlines(), name)

    def test_the_input_is_declared_once_and_under_workflow_call(self):
        for name in ROUTABLE:
            body = text(name)
            self.assertEqual(len(re.findall(r"(?m)^      runner:$", body)), 1, name)
            on = body.split("\npermissions:")[0]
            self.assertIn("  workflow_call:", on, name)
            self.assertIn("    inputs:", on, name)
            self.assertIn("      runner:", on, name)

    def test_every_job_runs_on_the_runner_the_caller_names(self):
        for name in ROUTABLE:
            found = re.findall(r"(?m)^    runs-on: (.*)$", text(name))
            self.assertEqual(found, [ROUTED] * JOBS_WITH_A_RUNNER[name], name)

    def test_no_job_of_a_routable_workflow_has_a_runner_of_its_own(self):
        for name in ROUTABLE:
            self.assertNotRegex(text(name), r"(?m)^\s+runs-on: (?!\$\{\{ fromJSON\(inputs\.runner\) \}\}$)", name)

    def test_the_input_reaches_runs_on_only(self):
        # A label list in a script would be shell code, and the input has no other use.
        for name in ROUTABLE:
            uses = re.findall(r"(?m)^.*inputs\.runner.*$", text(name))
            self.assertTrue(all(line.strip().startswith("runs-on:") for line in uses), name)

    def test_build_routes_each_leg_by_its_own_runner(self):
        self.assertEqual(re.findall(r"(?m)^    runs-on: (.*)$", text("build.yml")), ["${{ matrix.runner }}"])


if __name__ == "__main__":
    unittest.main()
