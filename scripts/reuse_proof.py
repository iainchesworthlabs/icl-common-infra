#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find earlier results a CI run can reuse (docs/ci-many-agents.md section 3.3).

    reuse_proof.py --stage queue --base-sha B [--plan-config .github/ci/plan.json]
                   [--mode shadow|on|off] [--planner CMD] [--output FILE]

Run in the `reuse` job after `plan`, in every event. It reads the Actions API (never check runs),
the policy from the trusted base commit, and a few git objects, and prints these outputs:

    run       JSON list of the groups to run
    reused    JSON map: group -> {run_id, url, tested_sha, event, delta, kind (equal-tree|delta)}
    would_reuse  the same map, always filled; in shadow mode `reused` stays empty
    mode      on | shadow | off | fallback
    reason    why the mode is `fallback`, or why nothing was reused

It never fails: any exception, API error or missing input emits the fallback, which runs every group
the plan asked for, and logs why. In `shadow` mode everything is computed and logged and nothing is
skipped. Reuse is refused for a fork, for an expired proof and whenever a barrier path differs (3.6).

Environment: GITHUB_REPOSITORY, GITHUB_EVENT_NAME, GITHUB_EVENT_PATH, GITHUB_SHA, GITHUB_OUTPUT,
GITHUB_STEP_SUMMARY, GH_TOKEN (the `gh` CLI does the API calls).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shlex
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_gate  # noqa: E402

STAGE_ORDER = ("pull_request", "queue", "post_merge", "nightly")
EVENT_STAGE = {"pull_request": "pull_request", "merge_group": "queue", "push": "post_merge",
               "workflow_dispatch": "nightly", "schedule": "nightly"}
DEFAULT_WORKFLOW = ".github/workflows/ci.yml"
MAX_CANDIDATES = 8
LOW_RATE_CANDIDATES = 4
LOW_RATE_THRESHOLD = 300


class Refused(Exception):
    """A candidate or the whole reuse is refused. The message is logged."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


# --- GitHub API and git, behind two small classes the tests replace -----------------------------

class Api:
    def __init__(self, repository: str):
        self.repository = repository

    def _gh(self, path: str, params: dict | None, binary: bool = False):
        cmd = ["gh", "api", "--method", "GET", path.format(r=self.repository)]
        for k, v in (params or {}).items():
            cmd += ["-f", f"{k}={v}"]
        res = subprocess.run(cmd, capture_output=True, check=False)
        if res.returncode:
            raise Refused(f"API {path}: {res.stderr.decode(errors='replace').strip()[:200]}")
        return res.stdout if binary else json.loads(res.stdout or b"null")

    def get(self, path: str, params: dict | None = None):
        return self._gh(path, params)

    def download(self, path: str) -> bytes:
        return self._gh(path, None, binary=True)


class Repo:
    def __init__(self, root: str = "."):
        self.root = root

    def _git(self, *args: str, check: bool = True) -> str:
        res = subprocess.run(["git", "-C", self.root, *args], capture_output=True, text=True, check=False)
        if check and res.returncode:
            raise Refused(f"git {' '.join(args[:2])}: {res.stderr.strip()[:200]}")
        return res.stdout.strip() if res.returncode == 0 else ""

    def fetch(self, *shas: str) -> None:
        # The checkout does not persist credentials, so pass the job token for this one command.
        token = os.environ.get("GH_TOKEN", "")
        auth = []
        if token:
            basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
            auth = ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]
        self._git(*auth, "fetch", "--no-tags", "--depth=1", "--filter=blob:none", "origin", *shas)

    def tree(self, sha: str) -> str:
        return self._git("rev-parse", f"{sha}^{{tree}}")

    def object_id(self, sha: str, path: str) -> str | None:
        return self._git("rev-parse", "--verify", "--quiet", f"{sha}:{path}", check=False) or None

    def diff_names(self, a: str, b: str) -> list[str]:
        return self._git("diff", "--name-only", "--no-renames", a, b).splitlines()

    def parents(self, sha: str) -> list[str]:
        return self._git("rev-list", "--parents", "-n", "1", sha).split()[1:]

    def committed_at(self, sha: str) -> datetime:
        return datetime.fromtimestamp(int(self._git("show", "-s", "--format=%ct", sha)), timezone.utc)

    def is_ancestor(self, a: str, b: str) -> bool:
        return subprocess.run(["git", "-C", self.root, "merge-base", "--is-ancestor", a, b],
                              capture_output=True, check=False).returncode == 0

    def show(self, sha: str, path: str) -> str | None:
        return self._git("show", f"{sha}:{path}", check=False) or None


# --- planning ---------------------------------------------------------------------------------------

def command_planner(command: str):
    """A consumer's own planner: paths on stdin, `groups=` and `promoted=` lines on stdout."""
    def plan(paths, cfg):
        res = subprocess.run(shlex.split(command), input="\n".join(paths), capture_output=True, text=True,
                             check=False)
        if res.returncode:
            raise Refused(f"planner failed: {res.stderr.strip()[:200]}")
        out = dict(line.split("=", 1) for line in res.stdout.splitlines() if "=" in line)
        return {"groups": json.loads(out.get("groups", "[]")), "promoted": json.loads(out.get("promoted", "[]"))}
    return plan


def required_groups(paths, cfg, stage, planner) -> list[str]:
    """Groups this stage must have passed for the paths: asked, home at or before the stage, or promoted."""
    plan = planner(paths, cfg)
    groups = cfg.get("groups") or {}
    rank = STAGE_ORDER.index(stage)
    required = []
    for name in plan["groups"]:
        home = (groups.get(name) or {}).get("home", "pull_request")
        if name in plan["promoted"] or (home in STAGE_ORDER and STAGE_ORDER.index(home) <= rank):
            required.append(name)
    return sorted(required)


# --- candidates ---------------------------------------------------------------------------------------

def workflow_path(run: dict) -> str:
    return (run.get("path") or "").split("@", 1)[0]


def gather_candidates(api: Api, ctx: dict, limit: int) -> list[dict]:
    repo, head, found = ctx["repository"], ctx["head_sha"], {}

    def listing(**params):
        data = api.get("repos/{r}/actions/runs", dict(params, status="completed", per_page=100))
        return data.get("workflow_runs", []) if data else []

    if ctx["event"] == "merge_group":
        for run in listing(head_sha=head):
            if run["event"] in ("pull_request", "workflow_dispatch"):
                found[run["id"]] = run
        if ctx.get("branch"):
            for run in listing(branch=ctx["branch"], event="workflow_dispatch"):
                found[run["id"]] = run
        for run in listing(event="merge_group"):
            if f"/pr-{ctx['pr_number']}-" in (run.get("head_branch") or ""):
                found[run["id"]] = run
    elif ctx["event"] == "pull_request":
        for run in listing(head_sha=head, event="workflow_dispatch"):
            found[run["id"]] = run
    elif ctx["event"] == "workflow_dispatch":
        for run in listing(head_sha=head, event="pull_request"):
            found[run["id"]] = run
    elif ctx["event"] == "push":
        for run in listing(head_sha=ctx["sha"], event="merge_group"):
            found[run["id"]] = run
    runs = [r for r in found.values()
            if r["id"] != ctx.get("run_id") and workflow_path(r) == ctx["workflow"]
            and (r.get("head_repository") or {}).get("full_name") == repo
            and parse_time(r["created_at"]) >= ctx["now"] - timedelta(hours=ctx["max_age_hours"])]
    return sorted(runs, key=lambda r: r["created_at"], reverse=True)[:limit]


def green_groups(api: Api, run: dict, groups_cfg: dict) -> set[str]:
    """Groups whose jobs all exist in the run with conclusion success, and no other job of that group."""
    jobs, page = [], 1
    while True:
        data = api.get(f"repos/{{r}}/actions/runs/{run['id']}/jobs", {"per_page": 100, "page": page})
        batch = (data or {}).get("jobs", [])
        jobs += batch
        if len(batch) < 100:
            break
        page += 1
    conclusion = {j["name"]: j.get("conclusion") for j in jobs}
    green = set()
    for name, group in groups_cfg.items():
        listed = group.get("jobs") or []
        if not listed:
            continue
        prefixes = {j.split(" / ", 1)[0] for j in listed}
        found = {n for n in conclusion if n in prefixes or any(n.startswith(p + " / ") for p in prefixes)}
        if found == set(listed) and all(conclusion[n] == "success" for n in listed):
            green.add(name)
    return green


def tested_commit(api: Api, repo: Repo, run: dict, ctx: dict) -> str:
    """The commit a run checked out. A pull request run says so only in its own artifact."""
    if run["event"] != "pull_request":
        return run["head_sha"]
    arts = (api.get(f"repos/{{r}}/actions/runs/{run['id']}/artifacts", {"name": "ci-proof"}) or {}).get("artifacts", [])
    if not arts:
        raise Refused("pull request run has no ci-proof artifact")
    blob = api.download(f"repos/{{r}}/actions/artifacts/{arts[0]['id']}/zip")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            proof = json.loads(z.read("ci-proof.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise Refused(f"ci-proof artifact unreadable: {e}")
    if proof.get("schema") != 1 or proof.get("repository") != ctx["repository"] or proof.get("run_id") != run["id"]:
        raise Refused("ci-proof artifact does not describe this run")
    sha = proof.get("tested_sha") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise Refused("ci-proof has no tested_sha")
    repo.fetch(sha)
    parents = repo.parents(sha)
    if len(parents) != 2 or parents[1] != run["head_sha"]:
        raise Refused("tested commit is not a merge of the run's head")
    if not repo.is_ancestor(parents[0], ctx["base_sha"]):
        raise Refused("tested commit's first parent is not on the base's history")
    if repo.committed_at(sha) > parse_time(run["created_at"]):
        raise Refused("tested commit is newer than the run")
    return sha


def check_barrier(repo: Repo, barrier, *commits: str) -> None:
    for path in barrier:
        ids = {repo.object_id(c, path) for c in commits}
        if len(ids) != 1:
            raise Refused(f"barrier path {path} differs")


def decide(api: Api, repo: Repo, ctx: dict, cfg: dict, planner, required: list[str]) -> dict:
    """The reuse decision for the required groups. Returns {reused, notes}."""
    reused, notes = {}, []
    if not required:
        return {"reused": reused, "notes": ["no group is required"]}
    if ctx.get("fork"):
        return {"reused": reused, "notes": ["fork: no reuse"]}
    groups_cfg = cfg.get("groups") or {}
    barrier = plan_gate.reuse_config(cfg)["barrier"]
    limit = ctx.get("candidate_limit", MAX_CANDIDATES)
    for run in gather_candidates(api, ctx, limit):
        if len(reused) == len(required):
            break
        label = f"run {run['id']} ({run['event']})"
        try:
            green = green_groups(api, run, groups_cfg) & (set(required) - set(reused))
            if not green:
                notes.append(f"{label}: no required group is green")
                continue
            tested = tested_commit(api, repo, run, ctx)
            repo.fetch(tested, ctx["base_sha"])
            check_barrier(repo, barrier, tested, ctx["base_sha"], ctx["sha"])
            if repo.tree(tested) == repo.tree(ctx["sha"]):
                delta, kind, asked = [], "equal-tree", set()
            else:
                delta = repo.diff_names(tested, ctx["sha"])
                kind, asked = "delta", set(planner(delta, cfg)["groups"])
        except Refused as e:
            notes.append(f"{label}: refused: {e}")
            continue
        for name in sorted(green):
            if name in asked:
                notes.append(f"{label}: {name} green but the delta of {len(delta)} file(s) asks for it")
                continue
            reused[name] = {"run_id": run["id"], "url": run.get("html_url", ""), "tested_sha": tested,
                            "event": run["event"], "delta": len(delta), "kind": kind}
    return {"reused": reused, "notes": notes}


# --- the job -------------------------------------------------------------------------------------------

def event_context(event_name: str, payload: dict, env: dict) -> dict:
    ctx = {"event": event_name, "repository": env.get("GITHUB_REPOSITORY", ""), "sha": env.get("GITHUB_SHA", ""),
           "run_id": int(env["GITHUB_RUN_ID"]) if env.get("GITHUB_RUN_ID", "").isdigit() else None,
           "head_sha": env.get("GITHUB_SHA", ""), "head_ref": "", "pr_number": "", "fork": False}
    if event_name == "pull_request":
        pr = payload["pull_request"]
        ctx.update(head_sha=pr["head"]["sha"], base_sha=pr["base"]["sha"], pr_number=pr["number"],
                   fork=(pr["head"].get("repo") or {}).get("full_name") != ctx["repository"])
    elif event_name == "merge_group":
        mg = payload["merge_group"]
        m = re.search(r"/pr-(\d+)-", mg.get("head_ref", ""))
        ctx.update(base_sha=mg["base_sha"], head_ref=mg.get("head_ref", ""), pr_number=m.group(1) if m else "")
    return ctx


def resolve_pull_request(api: Api, ctx: dict) -> None:
    """For a queue entry, the pull request's head (candidates are found by it) and its repository."""
    if ctx["event"] != "merge_group":
        return
    if not ctx["pr_number"]:
        raise Refused("cannot read the pull request number from the merge group")
    pr = api.get(f"repos/{{r}}/pulls/{ctx['pr_number']}")
    ctx["head_sha"] = pr["head"]["sha"]
    ctx["fork"] = (pr["head"].get("repo") or {}).get("full_name") != ctx["repository"]
    ctx["branch"] = pr["head"]["ref"]


def run_job(api: Api, repo: Repo, ctx: dict, mode: str, plan_config: str, planner_command: str = "") -> dict:
    ctx.setdefault("now", datetime.now(timezone.utc))
    ctx.setdefault("workflow", DEFAULT_WORKFLOW)
    stage = EVENT_STAGE.get(ctx["event"], "nightly")
    repo.fetch(ctx["base_sha"])
    text = repo.show(ctx["base_sha"], plan_config)
    cfg = dict(plan_gate.DEFAULT)
    if text:
        cfg.update(json.loads(text))
    ctx["max_age_hours"] = plan_gate.reuse_config(cfg)["max_age_hours"]
    planner = command_planner(planner_command) if planner_command else plan_gate.groups_plan
    repo.fetch(ctx["sha"])
    required = required_groups(repo.diff_names(ctx["base_sha"], ctx["sha"]), cfg, stage, planner)
    out = {"run": required, "reused": {}, "would_reuse": {}, "mode": mode, "reason": ""}
    if mode == "off":
        return out
    resolve_pull_request(api, ctx)
    rate = (api.get("rate_limit") or {}).get("resources", {}).get("core", {}).get("remaining", 5000)
    if rate < LOW_RATE_THRESHOLD:
        ctx["candidate_limit"] = LOW_RATE_CANDIDATES
    result = decide(api, repo, ctx, cfg, planner, required)
    out["would_reuse"] = result["reused"]
    out["reason"] = "; ".join(result["notes"])[:1000]
    if mode == "on":
        out["reused"] = result["reused"]
        out["run"] = [g for g in required if g not in result["reused"]]
    return out


def write_outputs(out: dict, path: str | None) -> None:
    lines = [f"{k}={json.dumps(v, separators=(',', ':')) if isinstance(v, (list, dict)) else v}"
             for k, v in out.items()]
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def summary(out: dict) -> str:
    rows = ["### Reuse (" + out["mode"] + ")", "", f"Run: {', '.join(out['run']) or 'none'}", ""]
    if out["would_reuse"]:
        verb = "Reused" if out["reused"] else "Would reuse (shadow)"
        rows += [f"{verb}:", "", "| Group | Run | Event | Tested | Delta | Kind |", "|---|---|---|---|---|---|"]
        for g, r in sorted(out["would_reuse"].items()):
            rows.append(f"| {g} | [{r['run_id']}]({r['url']}) | {r['event']} | {r['tested_sha'][:8]} | {r['delta']} | {r['kind']} |")
    else:
        rows.append("Nothing to reuse.")
    if out["reason"]:
        rows += ["", out["reason"]]
    return "\n".join(rows) + "\n"


def main(argv=None) -> int:
    env = os.environ
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", help="informational; the stage is taken from the event")
    ap.add_argument("--base-sha", default="")
    ap.add_argument("--plan-config", default=".github/ci/plan.json")
    ap.add_argument("--mode", default=env.get("CI_REUSE_MODE", "shadow") or "shadow")
    ap.add_argument("--planner", default="")
    ap.add_argument("--root", default=".")
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    ap.add_argument("--output", default=env.get("GITHUB_OUTPUT"))
    args = ap.parse_args(argv)
    mode = args.mode if args.mode in ("on", "shadow", "off") else "shadow"
    try:
        payload = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")) if env.get("GITHUB_EVENT_PATH") else {}
        ctx = event_context(env.get("GITHUB_EVENT_NAME", ""), payload, env)
        ctx["workflow"] = args.workflow
        if args.base_sha:
            ctx["base_sha"] = args.base_sha
        if not ctx.get("base_sha"):
            raise Refused("no base commit for this event")
        out = run_job(Api(ctx["repository"]), Repo(args.root), ctx, mode, args.plan_config, args.planner)
    except Exception as e:  # never fail the workflow
        log(f"reuse: fallback, running everything the plan asked for: {e}")
        # `run` is informational: the caller runs every group the plan asked for that `reused` does not name.
        out = {"run": [], "reused": {}, "would_reuse": {}, "mode": "fallback", "reason": str(e)[:500]}
    log(summary(out))
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary(out))
    write_outputs(out, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
