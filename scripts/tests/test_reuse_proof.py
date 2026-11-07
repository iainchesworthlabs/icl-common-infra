# SPDX-License-Identifier: GPL-3.0-or-later
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_gate  # noqa: E402
import reuse_proof as r  # noqa: E402

REPO = "o/r"
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
G, B, T, H, FIRST = "1" * 40, "2" * 40, "3" * 40, "4" * 40, "5" * 40
FAST = ["Build (fast) / linux-gcc-release", "Build (fast) / linux-clang-asan-ubsan"]
CFG = dict(plan_gate.DEFAULT, groups={
    "build-fast": {"home": "pull_request", "jobs": FAST, "skips": ["**/*.mm"]},
    "coverage": {"home": "pull_request", "jobs": ["Coverage"], "skips": ["**/*.mm"]},
    "build-linux-full": {"home": "queue", "jobs": ["Build (Linux full) / linux-gcc-debug"], "skips": []},
    "build-macos": {"home": "post_merge", "jobs": ["Build (macOS) / macos-debug"], "skips": []},
})
ALL_GREEN = {n: "success" for n in FAST + ["Coverage", "Build (Linux full) / linux-gcc-debug", "Build (macOS) / macos-debug",
                                          "Plan", "CI Status"]}


def run(id_, event="pull_request", head=H, age_h=1, path=".github/workflows/ci.yml", repo=REPO, **kw):
    d = {"id": id_, "event": event, "head_sha": head, "path": path, "head_repository": {"full_name": repo},
         "created_at": (NOW - timedelta(hours=age_h)).isoformat(), "html_url": f"https://x/{id_}",
         "head_branch": "feature/x"}
    d.update(kw)
    return d


def proof_zip(run_id, tested=T, repository=REPO, schema=1):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ci-proof.json", json.dumps({"schema": schema, "repository": repository, "run_id": run_id,
                                                "tested_sha": tested}))
    return buf.getvalue()


class FakeApi:
    def __init__(self, runs=(), jobs=None, artifacts=True, zips=None, fail=None):
        self.runs, self.jobs, self.artifacts, self.zips, self.fail = list(runs), jobs or {}, artifacts, zips or {}, fail
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if self.fail and self.fail in path:
            raise r.Refused(f"API {path}: 500")
        params = params or {}
        if path == "rate_limit":
            return {"resources": {"core": {"remaining": 5000}}}
        if path == "repos/{r}/actions/runs":
            out = [x for x in self.runs if all(
                (k not in ("head_sha", "event") or x.get(k) == v) and (k != "branch" or x.get("head_branch") == v)
                for k, v in params.items())]
            return {"workflow_runs": out}
        if path.endswith("/jobs"):
            rid = int(path.split("/")[-2])
            return {"jobs": [{"name": n, "conclusion": c} for n, c in self.jobs.get(rid, ALL_GREEN).items()]}
        if path.endswith("/artifacts"):
            rid = int(path.split("/")[-2])
            return {"artifacts": [{"id": rid}] if self.artifacts else []}
        if "/pulls/" in path:
            return {"head": {"sha": H, "ref": "feature/x", "repo": {"full_name": REPO}}}
        raise AssertionError(path)

    def download(self, path):
        return self.zips[int(path.split("/")[-2])]


class FakeRepo:
    def __init__(self, trees=None, diffs=None, barrier=None, parents=None, ancestors=(FIRST,), committed=NOW - timedelta(hours=2),
                 files=None):
        self.trees = trees or {G: "tree-g", T: "tree-g", H: "tree-h", B: "tree-b"}
        self.diffs, self.barrier = diffs or {}, barrier or {}
        self._parents = parents or {T: [FIRST, H]}
        self.ancestors, self.committed, self.files = set(ancestors), committed, files or {}
        self.fetched = []

    def fetch(self, *shas):
        self.fetched += shas

    def tree(self, sha):
        return self.trees[sha]

    def object_id(self, sha, path):
        return self.barrier.get((sha, path), "same")

    def diff_names(self, a, b):
        return self.diffs[(a, b)]

    def parents(self, sha):
        return self._parents[sha]

    def committed_at(self, sha):
        return self.committed

    def is_ancestor(self, a, b):
        return a in self.ancestors and b == B

    def show(self, sha, path):
        return self.files.get((sha, path))


def ctx(event="merge_group", **kw):
    d = {"event": event, "repository": REPO, "sha": G, "run_id": 99, "head_sha": H, "base_sha": B,
         "head_ref": f"refs/heads/gh-readonly-queue/develop/pr-7-{G}", "pr_number": "7", "fork": False, "now": NOW,
         "workflow": ".github/workflows/ci.yml", "max_age_hours": 48, "branch": "feature/x"}
    d.update(kw)
    return d


def decide(api, repo, required=("build-fast", "coverage"), **kw):
    return r.decide(api, repo, ctx(**kw), CFG, plan_gate.groups_plan, list(required))


class Reuse(unittest.TestCase):
    def pr_run(self, rid=1, **kw):
        return run(rid, **kw), proof_zip(rid)

    def test_equal_tree_reuses_every_green_group(self):
        pr, z = self.pr_run()
        res = decide(FakeApi([pr], zips={1: z}), FakeRepo())
        self.assertEqual(sorted(res["reused"]), ["build-fast", "coverage"])
        self.assertEqual(res["reused"]["coverage"]["kind"], "equal-tree")
        self.assertEqual(res["reused"]["coverage"]["tested_sha"], T)

    def test_delta_that_asks_for_a_group_runs_it(self):
        pr, z = self.pr_run()
        repo = FakeRepo(trees={G: "g", T: "t", H: "h", B: "b"}, diffs={(T, G): ["a.mm"], })
        # a .mm file is in every skip list here, so nothing is asked and both are reused
        res = decide(FakeApi([pr], zips={1: z}), repo)
        self.assertEqual((sorted(res["reused"]), res["reused"]["coverage"]["kind"], res["reused"]["coverage"]["delta"]),
                         (["build-fast", "coverage"], "delta", 1))
        repo = FakeRepo(trees={G: "g", T: "t", H: "h", B: "b"}, diffs={(T, G): ["libs/core/src/a.cpp"]})
        res = decide(FakeApi([pr], zips={1: z}), repo)
        self.assertEqual(res["reused"], {})
        self.assertIn("asks for it", "; ".join(res["notes"]))

    def test_dispatch_on_the_head_is_a_candidate_without_an_artifact(self):
        d = run(5, event="workflow_dispatch", head=H)
        res = decide(FakeApi([d], artifacts=False), FakeRepo(trees={G: "g", H: "g", B: "b"}))
        self.assertEqual(sorted(res["reused"]), ["build-fast", "coverage"])
        self.assertEqual(res["reused"]["build-fast"]["tested_sha"], H)

    def test_dispatch_on_an_earlier_commit_of_the_branch_is_found_by_branch(self):
        d = run(5, event="workflow_dispatch", head="e" * 40, head_branch="feature/x")
        res = decide(FakeApi([d]), FakeRepo(trees={G: "g", "e" * 40: "g", B: "b"}))
        self.assertEqual(len(res["reused"]), 2)

    def test_a_skipped_group_is_no_evidence(self):
        pr, z = self.pr_run()
        jobs = dict(ALL_GREEN, Coverage="skipped")
        res = decide(FakeApi([pr], jobs={1: jobs}, zips={1: z}), FakeRepo())
        self.assertEqual(sorted(res["reused"]), ["build-fast"])

    def test_a_group_with_an_extra_or_missing_leg_is_not_green(self):
        pr, z = self.pr_run()
        extra = dict(ALL_GREEN, **{"Build (fast) / linux-clang-tsan": "success"})
        self.assertNotIn("build-fast", decide(FakeApi([pr], jobs={1: extra}, zips={1: z}), FakeRepo())["reused"])
        missing = {k: v for k, v in ALL_GREEN.items() if k != FAST[0]}
        self.assertNotIn("build-fast", decide(FakeApi([pr], jobs={1: missing}, zips={1: z}), FakeRepo())["reused"])

    def test_a_failed_leg_is_not_green(self):
        pr, z = self.pr_run()
        failed = dict(ALL_GREEN, **{FAST[1]: "failure"})
        res = decide(FakeApi([pr], jobs={1: failed}, zips={1: z}), FakeRepo())
        self.assertEqual(sorted(res["reused"]), ["coverage"])

    def test_a_run_of_another_workflow_file_is_ignored(self):
        pr, z = self.pr_run(path=".github/workflows/evil.yml")
        self.assertEqual(decide(FakeApi([pr], zips={1: z}), FakeRepo())["reused"], {})

    def test_a_workflow_path_with_a_ref_suffix_is_accepted(self):
        pr, z = self.pr_run(path=".github/workflows/ci.yml@refs/pull/7/merge")
        self.assertEqual(len(decide(FakeApi([pr], zips={1: z}), FakeRepo())["reused"]), 2)

    def test_a_run_from_a_fork_repository_is_ignored(self):
        pr, z = self.pr_run(repo="fork/r")
        self.assertEqual(decide(FakeApi([pr], zips={1: z}), FakeRepo())["reused"], {})

    def test_a_fork_pull_request_never_reuses(self):
        pr, z = self.pr_run()
        res = decide(FakeApi([pr], zips={1: z}), FakeRepo(), fork=True)
        self.assertEqual((res["reused"], res["notes"]), ({}, ["fork: no reuse"]))

    def test_a_stale_proof_is_ignored(self):
        pr, z = self.pr_run(age_h=49)
        self.assertEqual(decide(FakeApi([pr], zips={1: z}), FakeRepo())["reused"], {})

    def test_a_changed_barrier_refuses(self):
        pr, z = self.pr_run()
        for changed in ((T, "vcpkg.json"), (G, ".github/workflows"), (B, "cmake")):
            res = decide(FakeApi([pr], zips={1: z}), FakeRepo(barrier={changed: "other"}))
            self.assertEqual(res["reused"], {}, changed)
            self.assertIn("barrier path", "; ".join(res["notes"]))

    def test_a_bad_parent_refuses(self):
        pr, z = self.pr_run()
        for parents in ({T: [FIRST]}, {T: [FIRST, "x" * 40]}):
            res = decide(FakeApi([pr], zips={1: z}), FakeRepo(parents=parents))
            self.assertEqual(res["reused"], {})
        res = decide(FakeApi([pr], zips={1: z}), FakeRepo(ancestors=()))
        self.assertIn("base's history", "; ".join(res["notes"]))

    def test_a_tested_commit_newer_than_the_run_refuses(self):
        pr, z = self.pr_run()
        res = decide(FakeApi([pr], zips={1: z}), FakeRepo(committed=NOW))
        self.assertEqual(res["reused"], {})

    def test_a_missing_or_wrong_artifact_refuses(self):
        pr, z = self.pr_run()
        self.assertEqual(decide(FakeApi([pr], artifacts=False), FakeRepo())["reused"], {})
        for bad in (proof_zip(2), proof_zip(1, repository="x/y"), proof_zip(1, schema=2), proof_zip(1, tested="short"),
                    b"not a zip"):
            res = decide(FakeApi([pr], zips={1: bad}), FakeRepo())
            self.assertEqual(res["reused"], {})

    def test_the_newest_candidate_wins_and_the_rest_fill_the_gaps(self):
        new, zn = run(2, age_h=1), proof_zip(2)
        old, zo = run(1, age_h=5), proof_zip(1)
        jobs = {2: dict(ALL_GREEN, Coverage="failure"), 1: ALL_GREEN}
        res = decide(FakeApi([old, new], jobs=jobs, zips={1: zo, 2: zn}),
                     FakeRepo(committed=NOW - timedelta(hours=6)))
        self.assertEqual((res["reused"]["build-fast"]["run_id"], res["reused"]["coverage"]["run_id"]), (2, 1))

    def test_the_current_run_is_not_a_candidate(self):
        d = run(99, event="workflow_dispatch")
        self.assertEqual(decide(FakeApi([d]), FakeRepo())["reused"], {})

    def test_nothing_required_nothing_to_find(self):
        api = FakeApi([run(1)])
        self.assertEqual(decide(api, FakeRepo(), required=())["reused"], {})
        self.assertEqual(api.calls, [])

    def test_a_dispatch_reuses_the_pull_request_run_of_the_same_head(self):
        pr, z = self.pr_run()
        res = decide(FakeApi([pr], zips={1: z}), FakeRepo(), event="workflow_dispatch", head_sha=H)
        self.assertEqual(len(res["reused"]), 2)

    def test_a_push_reuses_the_queue_run_of_the_same_commit(self):
        mg = run(3, event="merge_group", head=G)
        res = decide(FakeApi([mg]), FakeRepo(trees={G: "g", B: "b"}), event="push")
        self.assertEqual(res["reused"]["build-fast"]["kind"], "equal-tree")


class Required(unittest.TestCase):
    def test_stage_filters_by_home(self):
        paths = ["libs/core/src/a.cpp"]
        self.assertEqual(r.required_groups(paths, CFG, "pull_request", plan_gate.groups_plan), ["build-fast", "coverage"])
        self.assertEqual(r.required_groups(paths, CFG, "queue", plan_gate.groups_plan),
                         ["build-fast", "build-linux-full", "coverage"])
        self.assertEqual(len(r.required_groups(paths, CFG, "post_merge", plan_gate.groups_plan)), 4)

    def test_a_promoted_group_is_required_early(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["groups"]["build-macos"]["promote"] = ["libs/*/src/platform/macos/**"]
        got = r.required_groups(["libs/core/src/platform/macos/a.cpp"], cfg, "queue", plan_gate.groups_plan)
        self.assertIn("build-macos", got)

    def test_documentation_requires_nothing(self):
        self.assertEqual(r.required_groups(["docs/a.md"], CFG, "post_merge", plan_gate.groups_plan), [])


class Job(unittest.TestCase):
    def files(self):
        return {(B, ".github/ci/plan.json"): json.dumps({"groups": CFG["groups"]})}

    def run_job(self, mode, api=None, event="merge_group"):
        pr, z = run(1), proof_zip(1)
        no_linux_full = {k: v for k, v in ALL_GREEN.items() if "Linux full" not in k}
        api = api or FakeApi([pr], jobs={1: no_linux_full}, zips={1: z})
        repo = FakeRepo(files=self.files(), diffs={(B, G): ["libs/core/src/a.cpp"]})
        c = ctx(event)
        c.pop("branch")
        return r.run_job(api, repo, c, mode, ".github/ci/plan.json")

    def test_on_skips_what_is_reused(self):
        out = self.run_job("on")
        self.assertEqual(sorted(out["reused"]), ["build-fast", "coverage"])
        self.assertEqual(out["run"], ["build-linux-full"])

    def test_shadow_computes_and_skips_nothing(self):
        out = self.run_job("shadow")
        self.assertEqual(out["reused"], {})
        self.assertEqual(sorted(out["would_reuse"]), ["build-fast", "coverage"])
        self.assertEqual(out["run"], ["build-fast", "build-linux-full", "coverage"])

    def test_off_does_not_call_the_api(self):
        api = FakeApi()
        out = self.run_job("off", api=api)
        self.assertEqual((out["reused"], out["would_reuse"], api.calls), ({}, {}, []))

    def test_policy_comes_from_the_base_not_the_tree_under_test(self):
        repo = FakeRepo(files={(G, ".github/ci/plan.json"): json.dumps({"groups": CFG["groups"]})},
                        diffs={(B, G): ["libs/core/src/a.cpp"]})
        out = r.run_job(FakeApi([run(1)], zips={1: proof_zip(1)}), repo, ctx(), "on", ".github/ci/plan.json")
        self.assertEqual(out["run"], [])  # no groups in the base policy: nothing required


class Main(unittest.TestCase):
    def test_an_api_error_is_a_fallback_not_a_failure(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            event = Path(d) / "event.json"
            event.write_text(json.dumps({"merge_group": {"base_sha": B, "head_ref": "refs/heads/x/pr-7-abc"}}),
                             encoding="utf-8")
            env = {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": "merge_group", "GITHUB_EVENT_PATH": str(event),
                   "GITHUB_SHA": G}
            from unittest import mock
            with mock.patch.dict("os.environ", env, clear=False), \
                    mock.patch.object(r, "Repo", side_effect=r.Refused("git is broken")):
                code = r.main(["--output", str(out), "--root", d])
            text = out.read_text(encoding="utf-8")
            self.assertEqual(code, 0)
            self.assertIn("mode=fallback", text)
            self.assertIn("reused={}", text)
            self.assertIn("git is broken", text)

    def test_event_context(self):
        pr = {"pull_request": {"number": 4, "head": {"sha": H, "repo": {"full_name": "fork/r"}}, "base": {"sha": B}}}
        c = r.event_context("pull_request", pr, {"GITHUB_REPOSITORY": REPO, "GITHUB_SHA": G, "GITHUB_RUN_ID": "5"})
        self.assertEqual((c["head_sha"], c["base_sha"], c["fork"], c["run_id"]), (H, B, True, 5))
        gone = {"pull_request": {"number": 4, "head": {"sha": H, "repo": None}, "base": {"sha": B}}}
        self.assertTrue(r.event_context("pull_request", gone, {"GITHUB_REPOSITORY": REPO})["fork"])
        mg = {"merge_group": {"base_sha": B, "head_ref": f"refs/heads/gh-readonly-queue/develop/pr-12-{G}"}}
        self.assertEqual(r.event_context("merge_group", mg, {"GITHUB_REPOSITORY": REPO})["pr_number"], "12")


if __name__ == "__main__":
    unittest.main()
