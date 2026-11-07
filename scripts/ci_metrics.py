#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Weekly CI metrics for one repository (docs/ci-many-agents.md section 8.2).

    ci_metrics.py --repo owner/name [--days 7] [--workflow ci.yml] [--max-runs 300]
                  [--summary FILE] [--json]

Reads the Actions API with the gh CLI (`actions: read`) and prints a markdown table, also appended
to --summary (the job summary) when given. Computed from runs and jobs:

  * runner-minutes by event, split Linux / macOS / Windows (job duration, started to completed,
    so waiting for a runner is excluded)
  * median and p95 wall time of ready pull request runs
  * queue time per merge: the first merge_group run of a pull request to the push run on the commit
    that landed it, matched on SHA
  * runner-minutes and macOS minutes per merged change
  * runner wait: p90 of a job's start minus its run's creation, queue entries and push runs
  * wasted share: runner-minutes in runs that did not succeed over the total
  * the age of each refs/ci/green/<group>

Reuse rate and false reuse are not computed here: they need the shadow-mode and reuse job
summaries, which the API does not expose as data. Read them from the `Reuse` section of the job
summary of a run.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def parse(t: str | None):
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def minutes(a, b) -> float:
    return max(0.0, (b - a).total_seconds() / 60) if a and b else 0.0


def os_of(job: dict) -> str:
    labels = " ".join(job.get("labels") or []).lower()
    if "macos" in labels:
        return "macos"
    if "windows" in labels:
        return "windows"
    return "linux"


def percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def median(values: list[float]):
    return statistics.median(values) if values else None


def run_cost(jobs: list[dict]) -> dict:
    cost = defaultdict(float)
    for j in jobs:
        d = minutes(parse(j.get("started_at")), parse(j.get("completed_at")))
        cost[os_of(j)] += d
        cost["total"] += d
    return cost


def wall(run: dict, jobs: list[dict]) -> float:
    ends = [parse(j.get("completed_at")) for j in jobs if j.get("completed_at")]
    return minutes(parse(run["created_at"]), max(ends)) if ends else 0.0


def compute(runs: list[dict], jobs_by_run: dict, green_refs: dict | None = None, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    by_event = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(int)
    wasted = total = 0.0
    waits = defaultdict(list)
    pr_walls = []
    for run in runs:
        jobs = jobs_by_run.get(run["id"], [])
        cost = run_cost(jobs)
        ev = run["event"]
        counts[ev] += 1
        for k, v in cost.items():
            by_event[ev][k] += v
        total += cost["total"]
        if run.get("conclusion") != "success":
            wasted += cost["total"]
        if ev == "pull_request" and run.get("conclusion") == "success" and not run.get("draft"):
            pr_walls.append(wall(run, jobs))
        if ev in ("merge_group", "push"):
            created = parse(run["created_at"])
            for j in jobs:
                if j.get("started_at"):
                    waits[os_of(j)].append(minutes(created, parse(j["started_at"])))

    first_queue = {}
    for run in sorted((r for r in runs if r["event"] == "merge_group"), key=lambda r: r["created_at"]):
        m = re.search(r"/pr-(\d+)-", run.get("head_branch") or "")
        if m:
            first_queue.setdefault(m.group(1), run)
    queue_times = []
    pushes = {r["head_sha"]: r for r in runs if r["event"] == "push"}
    for pr, entry in first_queue.items():
        landed = pushes.get(entry["head_sha"])
        if landed:
            queue_times.append(minutes(parse(entry["created_at"]), parse(landed["updated_at"])))
    merged = len(first_queue)
    mac_total = sum(v.get("macos", 0.0) for v in by_event.values())
    out = {
        "runs": dict(counts),
        "runner_minutes": {ev: {k: round(v, 1) for k, v in d.items()} for ev, d in sorted(by_event.items())},
        "pr_wall": {"n": len(pr_walls), "median": median(pr_walls), "p95": percentile(pr_walls, 0.95)},
        "queue_time": {"n": len(queue_times), "median": median(queue_times), "p90": percentile(queue_times, 0.9)},
        "merged_changes": merged,
        "minutes_per_merged_change": round(total / merged, 1) if merged else None,
        "macos_minutes_per_merged_change": round(mac_total / merged, 1) if merged else None,
        "runner_wait_p90": {k: percentile(v, 0.9) for k, v in sorted(waits.items())},
        "wasted_share": round(wasted / total, 3) if total else None,
        "green_refs": {},
    }
    for group, (sha, when) in sorted((green_refs or {}).items()):
        out["green_refs"][group] = {"sha": sha, "age_hours": round((now - when).total_seconds() / 3600, 1)}
    return out


def fmt(v, digits=1):
    return "n/a" if v is None else f"{v:.{digits}f}"


def render(repo: str, days: int, m: dict) -> str:
    wasted = "n/a" if m["wasted_share"] is None else f"{m['wasted_share'] * 100:.0f}%"
    rows = [f"### CI metrics for {repo}, last {days} days", ""]
    rows += ["| Event | Runs | Runner-min | Linux | macOS | Windows |", "|---|---|---|---|---|---|"]
    for ev, cost in m["runner_minutes"].items():
        rows.append(f"| {ev} | {m['runs'].get(ev, 0)} | {fmt(cost.get('total', 0))} | {fmt(cost.get('linux', 0))} | "
                    f"{fmt(cost.get('macos', 0))} | {fmt(cost.get('windows', 0))} |")
    rows += ["", "| Metric | Value |", "|---|---|",
             f"| Ready pull request run, wall median / p95 (min), n={m['pr_wall']['n']} | "
             f"{fmt(m['pr_wall']['median'])} / {fmt(m['pr_wall']['p95'])} |",
             f"| Queue time per merge, median / p90 (min), n={m['queue_time']['n']} | "
             f"{fmt(m['queue_time']['median'])} / {fmt(m['queue_time']['p90'])} |",
             f"| Merged changes seen in the queue | {m['merged_changes']} |",
             f"| Runner-minutes per merged change | {fmt(m['minutes_per_merged_change'])} |",
             f"| macOS minutes per merged change | {fmt(m['macos_minutes_per_merged_change'])} |",
             f"| Runner wait p90 (min) | {', '.join(f'{k} {fmt(v)}' for k, v in m['runner_wait_p90'].items()) or 'n/a'} |",
             f"| Wasted share (runner-minutes in runs that did not succeed) | "
             f"{wasted} |"]
    if m["green_refs"]:
        rows += ["", "| Group | Green commit | Age (hours) |", "|---|---|---|"]
        rows += [f"| {g} | {r['sha'][:10]} | {r['age_hours']} |" for g, r in m["green_refs"].items()]
    rows += ["", "Reuse rate and false reuse: read the `Reuse` section of the job summaries; not available as data."]
    return "\n".join(rows) + "\n"


def gh_json(args: list[str]):
    res = subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=False)
    if res.returncode:
        raise RuntimeError(res.stderr.strip()[:300])
    return json.loads(res.stdout or "null")


def fetch(repo: str, days: int, workflow: str, max_runs: int, now=None):
    since = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).strftime("%Y-%m-%d")
    data = gh_json(["--paginate", "--slurp", f"repos/{repo}/actions/workflows/{workflow}/runs?per_page=100&status=completed&created=>={since}"])
    runs = [r for page in data for r in page.get("workflow_runs", [])][:max_runs]
    jobs = {}
    for r in runs:
        page = gh_json([f"repos/{repo}/actions/runs/{r['id']}/jobs?per_page=100"])
        jobs[r["id"]] = page.get("jobs", [])
    refs = {}
    try:
        for ref in gh_json([f"repos/{repo}/git/matching-refs/ci/green/"]) or []:
            sha = ref["object"]["sha"]
            when = parse(gh_json([f"repos/{repo}/commits/{sha}"])["commit"]["committer"]["date"])
            refs[ref["ref"].rsplit("/", 1)[-1]] = (sha, when)
    except (RuntimeError, KeyError):
        pass
    return runs, jobs, refs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--workflow", default="ci.yml")
    ap.add_argument("--max-runs", type=int, default=300)
    ap.add_argument("--summary")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        runs, jobs, refs = fetch(args.repo, args.days, args.workflow, args.max_runs)
    except (RuntimeError, ValueError) as e:
        print(f"::warning::could not read the Actions API: {e}")
        return 0
    m = compute(runs, jobs, refs)
    text = json.dumps(m, indent=2) if args.json else render(args.repo, args.days, m)
    print(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
