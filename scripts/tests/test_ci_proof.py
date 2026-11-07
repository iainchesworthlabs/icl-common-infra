# SPDX-License-Identifier: GPL-3.0-or-later
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_proof as p  # noqa: E402
import plan_gate  # noqa: E402

CFG = dict(plan_gate.DEFAULT, groups={
    "build-fast": {"jobs": ["Build (fast) / linux-gcc-release", "Build (fast) / linux-clang-asan-ubsan"]},
    "coverage": {"jobs": ["Coverage"]},
})
NEEDS = {
    "plan": {"result": "success"},
    "build-fast": {"result": "success"},
    "coverage": {"result": "skipped"},
    "zizmor": {"result": "success"},
}
ARGS = dict(repository="o/r", run_id="42", run_attempt="1", event="pull_request", tested_sha="t" * 40,
            head_sha="h" * 40, base_sha="b" * 40)


class Proof(unittest.TestCase):
    def build(self, **kw):
        args = dict(ARGS, needs=NEEDS, cfg=CFG, object_id=lambda root, commit, path: f"id:{path}")
        args.update(kw)
        return p.build_proof(**args)

    def test_records_only_configured_groups(self):
        proof = self.build()
        self.assertEqual(sorted(proof["groups"]), ["build-fast", "coverage"])
        self.assertEqual(proof["groups"]["coverage"], {"result": "skipped", "legs": ["Coverage"]})
        self.assertEqual(proof["groups"]["build-fast"]["result"], "success")

    def test_identity_and_numbers(self):
        proof = self.build()
        self.assertEqual((proof["schema"], proof["run_id"], proof["run_attempt"]), (1, 42, 1))
        self.assertEqual((proof["tested_sha"], proof["head_sha"], proof["base_sha"]),
                         ("t" * 40, "h" * 40, "b" * 40))

    def test_barrier_covers_the_mandatory_paths(self):
        proof = self.build()
        for path in plan_gate.MANDATORY_BARRIER:
            self.assertEqual(proof["barrier"][path], f"id:{path}")

    def test_absent_barrier_path_is_null(self):
        proof = self.build(object_id=lambda root, commit, path: None)
        self.assertTrue(all(v is None for v in proof["barrier"].values()))

    def test_reused_is_recorded_as_given(self):
        reused = {"coverage": {"run_id": 7, "tested_sha": "a" * 40}}
        self.assertEqual(self.build(reused=reused)["reused"], reused)
        self.assertEqual(self.build()["reused"], {})

    def test_proof_is_json_and_has_no_environment(self):
        text = json.dumps(self.build())
        self.assertNotIn("token", text.lower())


class Cli(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True,
                              env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
                                   "PATH": __import__("os").environ["PATH"],
                                   "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}).stdout.strip()

    def test_reads_object_ids_from_a_real_repository(self):
        with tempfile.TemporaryDirectory() as d:
            self.git(d, "init", "-q")
            (Path(d) / "vcpkg.json").write_text("{}", encoding="utf-8")
            (Path(d) / "cmake").mkdir()
            (Path(d) / "cmake" / "a.cmake").write_text("x", encoding="utf-8")
            self.git(d, "add", "-A")
            self.git(d, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")
            sha = self.git(d, "rev-parse", "HEAD")
            out = Path(d) / "proof.json"
            cfg = Path(d) / "plan.json"
            cfg.write_text(json.dumps({"groups": {"coverage": {}}}), encoding="utf-8")
            code = p.main(["--needs", json.dumps(NEEDS), "--out", str(out), "--config", str(cfg), "--root", d,
                           "--repository", "o/r", "--run-id", "9", "--event", "merge_group",
                           "--tested-sha", sha, "--reused", '{"reused": {"coverage": {"run_id": 3}}}'])
            self.assertEqual(code, 0)
            proof = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(proof["barrier"]["vcpkg.json"], self.git(d, "rev-parse", f"{sha}:vcpkg.json"))
            self.assertEqual(proof["barrier"]["cmake"], self.git(d, "rev-parse", f"{sha}:cmake"))
            self.assertIsNone(proof["barrier"][".github/workflows"])
            self.assertEqual(proof["reused"], {"coverage": {"run_id": 3}})
            self.assertEqual(proof["head_sha"], sha)

    def test_bad_reused_input_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "proof.json"
            code = p.main(["--needs", "{}", "--out", str(out), "--root", d, "--reused", "not json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["reused"], {})


if __name__ == "__main__":
    unittest.main()
