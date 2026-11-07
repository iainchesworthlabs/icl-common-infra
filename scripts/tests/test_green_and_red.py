# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mark_green as mg  # noqa: E402
import report_red as rr  # noqa: E402

A, B, C, D = "a" * 40, "b" * 40, "c" * 40, "d" * 40
CFG = {"groups": {"build-macos": {"jobs": ["Build (macOS) / macos-debug"]}, "coverage": {"jobs": ["Coverage"]}}}


class FakeGh:
    repo = "o/r"

    def __init__(self, refs=None, compare=None, issues=None, comments=None, jobs=None):
        self.refs = dict(refs or {})
        self.compare = compare or {}
        self.issues = issues or []
        self.comments = comments or {}
        self.jobs = jobs or []
        self.calls = []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path.startswith("git/ref/"):
            name = path[len("git/ref/"):]
            if name not in self.refs:
                raise RuntimeError("GET: Not Found (HTTP 404)")
            return {"object": {"sha": self.refs[name]}}
        if method == "POST" and path == "git/refs":
            self.refs[body["ref"][len("refs/"):]] = body["sha"]
            return {}
        if method == "PATCH" and path.startswith("git/refs/"):
            self.refs[path[len("git/refs/"):]] = body["sha"]
            return {}
        if method == "GET" and path.startswith("compare/"):
            return self.compare[path[len("compare/"):]]
        if method == "GET" and path.startswith("issues?"):
            return self.issues
        if method == "POST" and path == "issues":
            self.issues.append({"number": 90, "title": body["title"]})
            return {"number": 90}
        if method == "POST" and path == "labels":
            return {}
        if method == "GET" and path.startswith("issues/") and "/comments" in path:
            return self.comments.get(int(path.split("/")[1]), [])
        if method == "POST" and "/comments" in path:
            return {}
        if method == "PATCH" and path.startswith("issues/"):
            return {}
        if method == "GET" and path.startswith("actions/runs/"):
            return {"jobs": self.jobs}
        raise AssertionError((method, path))


def commit(sha, subject):
    return {"sha": sha, "commit": {"message": subject + "\n\nbody"}}


class Green(unittest.TestCase):
    def test_success_and_equal_tree_reuse_are_green(self):
        needs = {"coverage": {"result": "success"}, "build-macos": {"result": "skipped"}, "reuse": {"result": "success"}}
        reused = {"build-macos": {"delta": 0, "kind": "equal-tree"}}
        self.assertEqual(mg.green_groups(needs, reused, ["build-macos", "coverage"]), ["build-macos", "coverage"])

    def test_a_reuse_with_a_delta_is_not_green(self):
        needs = {"build-macos": {"result": "skipped"}}
        reused = {"build-macos": {"delta": 2, "kind": "delta"}}
        self.assertEqual(mg.green_groups(needs, reused, ["build-macos"]), [])

    def test_a_failure_is_not_green(self):
        self.assertEqual(mg.green_groups({"coverage": {"result": "failure"}}, {}, ["coverage"]), [])

    def test_creates_a_missing_ref(self):
        gh = FakeGh()
        self.assertEqual(mg.mark(gh, "coverage", B), "created")
        self.assertEqual(gh.refs["ci/green/coverage"], B)

    def test_moves_forward(self):
        gh = FakeGh(refs={"ci/green/coverage": A}, compare={f"{A}...{B}": {"status": "ahead"}})
        self.assertEqual(mg.mark(gh, "coverage", B), "moved")
        self.assertEqual(gh.refs["ci/green/coverage"], B)
        self.assertEqual(gh.calls[-1][2]["force"], False)

    def test_never_moves_back_or_sideways(self):
        for status in ("behind", "diverged", "identical"):
            gh = FakeGh(refs={"ci/green/coverage": A}, compare={f"{A}...{B}": {"status": status}})
            self.assertIn("kept", mg.mark(gh, "coverage", B))
            self.assertEqual(gh.refs["ci/green/coverage"], A)

    def test_same_commit_is_unchanged(self):
        self.assertEqual(mg.mark(FakeGh(refs={"ci/green/coverage": A}), "coverage", A), "unchanged")

    def test_dry_run_writes_nothing(self):
        gh = FakeGh()
        mg.mark(gh, "coverage", A, dry_run=True)
        self.assertEqual(gh.refs, {})

    def test_other_api_errors_propagate(self):
        class Broken(FakeGh):
            def call(self, method, path, body=None):
                raise RuntimeError("GET: HTTP 500")
        with self.assertRaises(RuntimeError):
            mg.mark(Broken(), "coverage", A)


class Red(unittest.TestCase):
    def gh(self, **kw):
        base = dict(refs={"ci/green/build-macos": A},
                    compare={f"{A}...{D}": {"commits": [commit(B, "Add thing (#11)"), commit(C, "Fix other (#12)"),
                                                        commit(D, "Docs without a number")]}},
                    jobs=[{"name": "Build (macOS) / macos-debug", "conclusion": "failure", "html_url": "https://x/j"},
                          {"name": "Coverage", "conclusion": "failure", "html_url": "https://x/c"}])
        base.update(kw)
        return FakeGh(**base)

    def test_suspects_are_the_commits_since_the_green_ref(self):
        found, note = rr.suspects(self.gh(), "build-macos", D)
        self.assertEqual([c["pr"] for c in found], [11, 12, None])
        self.assertEqual(note, "")

    def test_no_green_ref_means_unknown_suspects(self):
        found, note = rr.suspects(self.gh(refs={}), "build-macos", D)
        self.assertEqual(found, [])
        self.assertIn("unknown", note)

    def test_opens_an_issue_and_comments_on_each_suspect_once(self):
        gh = self.gh()
        out = rr.report(gh, "build-macos", D, "77", CFG, {}, False)
        self.assertEqual(out, "#90")
        issue = [c for c in gh.calls if c[:2] == ("POST", "issues")][0][2]
        self.assertEqual((issue["title"], issue["labels"]), ("main-red: build-macos", ["main-red"]))
        self.assertIn("Build (macOS) / macos-debug (https://x/j)", issue["body"])
        self.assertNotIn("Coverage (", issue["body"])  # another group's job
        self.assertIn("bisect", issue["body"])
        pr_comments = [c for c in gh.calls if c[0] == "POST" and c[1] in ("issues/11/comments", "issues/12/comments")]
        self.assertEqual(len(pr_comments), 2)

    def test_a_comment_already_made_is_not_repeated(self):
        marker = f"<!-- main-red:build-macos:{D} -->"
        gh = self.gh(comments={11: [{"body": marker + " earlier"}]})
        rr.report(gh, "build-macos", D, "77", CFG, {}, False)
        posted = [c[1] for c in gh.calls if c[0] == "POST" and c[1].endswith("/comments")]
        self.assertEqual(posted, ["issues/12/comments"])

    def test_an_open_issue_is_updated_not_duplicated(self):
        gh = self.gh(issues=[{"number": 5, "title": "main-red: build-macos"}])
        self.assertEqual(rr.report(gh, "build-macos", D, "77", CFG, {}, False), "#5")
        self.assertFalse([c for c in gh.calls if c[:2] == ("POST", "issues")])
        self.assertTrue([c for c in gh.calls if c[:2] == ("POST", "issues/5/comments")])

    def test_one_suspect_gets_the_revert_command(self):
        gh = self.gh(compare={f"{A}...{D}": {"commits": [commit(B, "Add thing (#11)")]}})
        text = rr.report(gh, "build-macos", D, "77", CFG, {}, True)
        self.assertIn(f"git revert {B}", text)

    def test_a_reused_group_is_flagged_as_a_possible_false_reuse(self):
        reused = {"build-macos": {"run_id": 5, "tested_sha": "e" * 40, "kind": "delta", "delta": 3}}
        text = rr.report(self.gh(), "build-macos", D, "77", CFG, reused, True)
        self.assertIn("false reuse", text)

    def test_a_pass_closes_the_open_issue(self):
        gh = self.gh(issues=[{"number": 5, "title": "main-red: build-macos"}])
        self.assertEqual(rr.close_if_open(gh, "build-macos", D, False), "closed #5")
        self.assertIn(("PATCH", "issues/5", {"state": "closed", "state_reason": "completed"}), gh.calls)
        self.assertEqual(rr.close_if_open(self.gh(), "build-macos", D, False), "no open issue")

    def test_pull_requests_are_not_mistaken_for_issues(self):
        gh = self.gh(issues=[{"number": 5, "title": "main-red: build-macos", "pull_request": {}}])
        self.assertIsNone(rr.open_issue(gh, "build-macos"))


if __name__ == "__main__":
    unittest.main()
