# SPDX-License-Identifier: GPL-3.0-or-later
"""Structural checks of the reusable docs-deploy-aws.yml: the account details are secrets, minimal
permissions, the OIDC roles, clean skips without secrets, and the rules that keep a preview inside
its own prefix."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/docs-deploy-aws.yml").read_text(encoding="utf-8")
SECRETS = ("DOCS_ROLE_ARN", "DOCS_PREVIEW_ROLE_ARN", "DOCS_BUCKET", "DOCS_DISTRIBUTION_ID")


def job(name: str) -> str:
    """The text of one top-level job."""
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", TEXT, re.S | re.M)
    assert match, name
    return match.group(1)


def steps(name: str) -> list[str]:
    """The steps of a job, each from its `name:` line."""
    return re.split(r"(?m)^      - name: ", job(name))[1:]


class DocsDeployAws(unittest.TestCase):
    def test_no_stored_keys(self):
        self.assertNotIn("aws-access-key-id", TEXT.lower())
        self.assertNotIn("AWS_SECRET", TEXT)

    def test_account_details_are_secrets_not_inputs_or_vars(self):
        declared = re.search(r"(?m)^    secrets:\n((?:      .*\n|        .*\n)+)", TEXT).group(1)
        for name in SECRETS:
            self.assertIn(f"      {name}:", declared)
            self.assertIn(f"secrets.{name}", TEXT)
        for old in ("inputs.role-arn", "inputs.distribution-id", "inputs.bucket", "vars.", "::add-mask::$"):
            self.assertNotIn(old, TEXT)

    def test_workflow_permissions_are_empty(self):
        self.assertRegex(TEXT, r"(?m)^permissions: \{\}$")

    def test_each_job_has_minimal_permissions(self):
        for name in ("deploy", "remove-preview"):
            perms = re.search(r"    permissions:\n((?:      .*\n)+)", job(name))
            self.assertIsNotNone(perms, name)
            granted = dict(line.strip().split(": ") for line in perms.group(1).splitlines())
            self.assertEqual(granted, {"contents": "read", "id-token": "write", "pull-requests": "write"}, name)

    def test_oidc_role_assumed_with_the_right_secret(self):
        deploy, remove = job("deploy"), job("remove-preview")
        self.assertIn("role-to-assume: ${{ secrets.DOCS_ROLE_ARN }}", deploy)
        self.assertIn("role-to-assume: ${{ secrets.DOCS_PREVIEW_ROLE_ARN }}", deploy)
        self.assertIn("role-to-assume: ${{ secrets.DOCS_PREVIEW_ROLE_ARN }}", remove)
        self.assertNotIn("DOCS_ROLE_ARN", remove.replace("DOCS_PREVIEW_ROLE_ARN", ""))
        self.assertRegex(deploy, r"Assume the production role\n        if: [^\n]*!inputs\.preview")
        self.assertRegex(deploy, r"Assume the preview role\n        if: [^\n]*&& inputs\.preview")

    def test_missing_secrets_and_forks_skip_every_later_step(self):
        for name in ("deploy", "remove-preview"):
            self.assertIn("skip=true", job(name))
            self.assertIn('"$HEAD_REPO" != "$REPO"', job(name))
            parts = steps(name)
            self.assertTrue(parts[0].startswith("Check the request"))
            for step in parts[1:]:
                header = step.split("\n        shell:")[0].split("\n        uses:")[0]
                self.assertIn("steps.check.outputs.skip != 'true'", header, step[:40])

    def test_a_skip_is_a_notice_or_warning_not_an_error(self):
        deploy = job("deploy")
        self.assertIn("::notice::No preview: a pull request from a fork", deploy)
        self.assertIn("::warning::Not deployed: secret(s) not available", deploy)
        self.assertIn("::warning::Preview not removed: secret(s) not available", job("remove-preview"))

    def test_inputs_and_secrets_never_expanded_in_run_scripts(self):
        for run in re.findall(r"run: \|\n((?:          .*\n|\n)+)", TEXT):
            self.assertNotIn("${{", run)

    def test_production_syncs_with_delete_to_the_prefix(self):
        self.assertIn('aws --no-cli-pager s3 sync site/ "s3://$BUCKET/$key/" --delete', TEXT)
        self.assertIn('key="$PREFIX"', TEXT)

    def test_preview_goes_under_the_preview_prefix(self):
        self.assertEqual(TEXT.count('key="_preview/$PREFIX/pr-$PR_NUMBER"'), 2)

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

    def test_aws_commands_page_nothing_and_no_echo_prints_a_value(self):
        for line in re.findall(r"^\s+aws .*$", TEXT, re.M):
            self.assertIn("--no-cli-pager", line)
        for line in TEXT.splitlines():
            if re.search(r"echo|body=", line):
                self.assertNotRegex(line, r"\$\{?(ROLE_ARN|BUCKET|DISTRIBUTION_ID)\b")
                self.assertNotIn("secrets.", line)


if __name__ == "__main__":
    unittest.main()
