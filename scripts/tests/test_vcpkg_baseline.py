# SPDX-License-Identifier: GPL-3.0-or-later
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_vcpkg_baseline_in_fork as fork  # noqa: E402


def reply(status):
    return io.BytesIO(json.dumps({"status": status}).encode())


class CommitInFork(unittest.TestCase):
    def test_ancestor_of_master_is_present(self):
        for status in ("ahead", "identical"):
            with mock.patch("urllib.request.urlopen", return_value=reply(status)):
                self.assertTrue(fork.commit_in_fork("o/vcpkg", "a" * 40), status)

    def test_commit_only_in_the_parent_is_absent(self):
        for status in ("diverged", "behind"):
            with mock.patch("urllib.request.urlopen", return_value=reply(status)):
                self.assertFalse(fork.commit_in_fork("o/vcpkg", "a" * 40), status)

    def test_unknown_commit_is_absent(self):
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            self.assertFalse(fork.commit_in_fork("o/vcpkg", "a" * 40))

    def test_compare_url_names_the_commit_and_branch(self):
        with mock.patch("urllib.request.urlopen", return_value=reply("ahead")) as op:
            fork.commit_in_fork("o/vcpkg", "abc", "master")
        self.assertTrue(op.call_args[0][0].full_url.endswith("/repos/o/vcpkg/compare/abc...master"))


if __name__ == "__main__":
    unittest.main()
