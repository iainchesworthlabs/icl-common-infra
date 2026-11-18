# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks of the reusable docs-deploy-aws.yml: no secrets, minimal permissions, the OIDC
role and the rules that keep a preview inside its own prefix."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/docs-deploy-aws.yml").read_text(encoding="utf-8")


def job(name: str) -> str:
    """The text of one top-level job."""
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", TEXT, re.S | re.M)
    assert match, name
    return match.group(1)


class DocsDeployAws(unittest.TestCase):
    def test_no_secrets(self):
        self.assertNotIn("secrets", TEXT.replace("no secrets", ""))
        self.assertNotIn("aws-access-key-id", TEXT.lower())
        self.assertNotIn("AWS_SECRET", TEXT)

    def test_workflow_permissions_are_empty(self):
        self.assertRegex(TEXT, r"(?m)^permissions: \{\}$")

    def test_each_job_has_minimal_permissions(self):
        for name in ("deploy", "remove-preview"):
            block = job(name)
            perms = re.search(r"    permissions:\n((?:      .*\n)+)", block)
            self.assertIsNotNone(perms, name)
            granted = dict(line.strip().split(": ") for line in perms.group(1).splitlines())
            self.assertEqual(granted, {"contents": "read", "id-token": "write", "pull-requests": "write"}, name)

    def test_oidc_role_assumed_in_both_jobs(self):
        for name in ("deploy", "remove-preview"):
            self.assertIn("aws-actions/configure-aws-credentials@", job(name))
            self.assertIn("role-to-assume: ${{ inputs.role-arn }}", job(name))

    def test_inputs_never_expanded_in_run_scripts(self):
        for run in re.findall(r"run: \|\n((?:          .*\n|\n)+)", TEXT):
            self.assertNotIn("${{", run)

    def test_production_syncs_with_delete_to_the_prefix(self):
        self.assertIn('aws --no-cli-pager s3 sync site/ "s3://$BUCKET/$key/" --delete', TEXT)
        self.assertIn('key="$PREFIX"', TEXT)

    def test_preview_goes_under_the_preview_prefix(self):
        self.assertEqual(TEXT.count('key="_preview/$PREFIX/pr-$PR_NUMBER"'), 2)

    def test_forks_are_refused(self):
        deploy = job("deploy")
        self.assertIn('"$HEAD_REPO" != "$REPO"', deploy)
        self.assertIn("not forks", deploy)

    def test_production_only_from_the_production_ref(self):
        self.assertIn('"$REF" != "$PRODUCTION_REF"', job("deploy"))

    def test_both_jobs_invalidate_and_gate_on_mode(self):
        self.assertIn("if: inputs.mode == 'deploy'", job("deploy"))
        self.assertIn("if: inputs.mode == 'remove-preview'", job("remove-preview"))
        for name in ("deploy", "remove-preview"):
            self.assertIn("aws --no-cli-pager cloudfront create-invalidation", job(name))

    def test_every_uses_is_pinned_to_a_sha(self):
        uses = re.findall(r"uses: (\S+)@(\S+) # (v\S+)", TEXT)
        self.assertEqual(len(uses), TEXT.count("uses:"))
        for _, ref, _ in uses:
            self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_masks_come_first_and_cover_every_value(self):
        for name in ("deploy", "remove-preview"):
            block = job(name)
            first = re.search(r"      - name: (.+)\n", block).group(1)
            self.assertEqual(first, "Mask the account details", name)
            mask = block.index("Mask the account details")
            self.assertLess(mask, block.index("Check the request"), name)
            self.assertLess(mask, block.index("configure-aws-credentials"), name)
            head = block[mask:block.index("Check the request")]
            for needle in ("ROLE_ARN", "BUCKET", "DISTRIBUTION_ID", "cut -d: -f5", "::add-mask::"):
                self.assertIn(needle, head, name)

    def test_aws_commands_never_page_or_print_values(self):
        for line in re.findall(r"^\s+aws .*$", TEXT, re.M):
            self.assertIn("--no-cli-pager", line)
        for line in TEXT.splitlines():
            if re.search(r"echo|body=", line) and "add-mask" not in line:
                self.assertNotRegex(line, r"\$\{?(ROLE_ARN|BUCKET|DISTRIBUTION_ID|account)")


if __name__ == "__main__":
    unittest.main()
