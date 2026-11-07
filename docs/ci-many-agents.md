# CI for many parallel agents: reusing results, placing the expensive legs, sizing the queue

Status: design with the owner's decisions recorded (section 9), 2026-11-07. Nothing here is
implemented. It amends `standard.md` sections 11.2, 11.3 and 11.5 (section 7.3 lists the edits) and
is the plan for the pull requests in section 7.

The owner's brief: use `changelog.d` fragments to prevent merge collisions; design CI so many
agents can publish changes quickly; tests that passed on a pull request should be leveraged by
the merge queue.

## 1. Summary

- A change pays for its tests up to four times today: on the pull request, in a manual
  `gh workflow run ci.yml` that agents run before queueing, in the merge queue, and on the push to
  `develop`. In `icl-error-journaling` the two code changes that have been through all four stages
  cost 52.8 and 54.6 runner-minutes, a third is at 40.4 before its push run, against 6.6 for the
  pull request gate alone. The push run also builds in full for documentation-only merges (10.5
  to 14.6 runner-minutes each, six times in one day) because it plans with `--force-all`.
- The design gives every build or test group (one job of `ci.yml`, one or more legs) a home
  stage and makes every run, in any stage, ask first whether the same group already passed on a
  tree that differs from this one only in paths the group does not read. If so the group is not
  run and `CI Status` names the run it reused. Section 3.
- Measured on `icl-error-journaling`: of the 6 pull requests whose own diff asks for a build, the
  tree that passed on the pull request was identical to the tree that landed in 5 and differed only
  in documentation in 1; 3 of the 6 changed the workflow and must not be reused. On `iclforge`, of
  31 such pull requests with a known tested tree, 13 (42%) were identical, 1 differed only in
  files no build reads, 15 differed in build inputs and 2 in the gate's own files. Section 2.4.
- The expensive legs move to the stage where they pay once: Linux debug and TSan to the queue,
  macOS and iOS to the post-merge run (unless the change touches Apple-specific paths or carries
  `deep`), and the post-merge run builds only the groups whose last green commit is older than
  the changes merged since. Section 4.
- A post-merge failure is attributed per group to the merges since that group's last green
  commit (`refs/ci/green/<group>`), by an issue that names the pull requests. Section 4.4.
- Four named files are real collision hotspots (the two `libs/core` CMake source lists,
  `docs/architecture.md`, `docs/plan/stage-N.md`); two open pull requests conflict in the first
  and the third today. Section 5.
- The queue keeps `ALLGREEN`, 4 builds, 5 merges for `icl-error-journaling`; the timeout drops
  from 180 to 45 minutes. Section 6.
- Rollout is `icl-error-journaling` in shadow mode (reuse computed and logged, nothing skipped),
  then enforced, then the other consumers, `iclforge` last. Section 8.

The owner's decisions of 2026-11-07 are recorded in section 9.

## 2. Measurements

### 2.1 Method and limits

All numbers come from `gh run list` and `gh api repos/<repo>/actions/runs/<id>/jobs`, read on
2026-11-07. Job duration is `started_at` to `completed_at`, so it excludes waiting for a runner.
Runner-minutes are the sum of job durations, with no multiplier for macOS (both repositories are
public). Run wall time is the run's `created_at` to the last job's `completed_at`. A leg's cost is
the same whether or not the run passed.

| | `icl-error-journaling` | `iclforge` |
|---|---|---|
| Window | 2026-11-07 only (the repository was created that morning) | 2026-11-04 13:29Z to 2026-11-07 01:31Z (the latest 1000 runs) |
| Volume | 133 runs; 14 merged pull requests (12 by agents, 2 Dependabot); 3 open | 165 `PR Gate` runs, 37 `CI` runs; 49 pull requests merged in the window |
| Queue | `merge-queue-develop`: squash, ALLGREEN, build 4, merge 5, wait 1 min, timeout 180 | `merge-queue-main`: merge commit, ALLGREEN, build 8, merge 5, wait 5 min, timeout 180 |

Limit: `icl-error-journaling` is an empty Qt Quick application, so every leg takes about 2
minutes. Its absolute costs will grow with the code; the ratios between stages, and the shares of
cost, are what carry over. `iclforge` shows what a full-size project looks like.

### 2.2 `icl-error-journaling`

Runner-minutes by event, `CI` workflow (`ci.yml`), all runs including failed ones:

| Event | Runs | Runner-minutes | Linux | macOS | Windows | Share |
|---|---|---|---|---|---|---|
| `pull_request` | 25 | 50.7 | 50.7 | 0 | 0 | 11% |
| `merge_group` | 12 | 96.6 | 62.5 | 31.3 | 2.8 | 21% |
| `push` to `develop` | 12 completed | 174.3 | 106.7 | 54.6 | 12.9 | 38% |
| `workflow_dispatch` | 9 | 139.5 | 89.9 | 49.6 | 0 | 30% |
| Total | | 461.1 | | | | |

The separate `iOS build` workflow (path-filtered, not a required check, one macOS job) added
38.6 macOS minutes on 7 pull request runs, 24.2 on 5 pushes and 49.2 on 5 dispatches.

Median cost of a run, passing runs only:

| Event | Run with builds | Run without builds |
|---|---|---|
| `pull_request` | 6.6 runner-min, 2.7 min wall (6 runs) | 0.6 runner-min, 0.4 min wall (12 runs, drafts and documentation) |
| `merge_group` | 15.3 runner-min, 2.6 min wall (6 runs) | 0.7 runner-min, 0.3 min wall (6 runs) |
| `push` | 13.9 runner-min, 3.3 min wall (11 runs) | none: every push run builds |
| `workflow_dispatch` | 15.2 runner-min, 3.1 min wall (7 runs) | none |

Median job duration (minutes): Linux legs 1.6 to 1.9, macOS legs 1.7 to 2.0 (the `xcode-27`
experimental leg 1.5 to 1.7), `Coverage` 1.7 to 2.0, `Policy` 0.2, every other job 0.1. Wait for a
runner: the first job of a run started at a median of 0.0 minutes; macOS jobs started at a median
of 0.2 to 0.3 minutes and at worst 3.5 (push), 4.6 (queue) and 7.2 (dispatch). From the first
queue run of a pull request to the run on `develop` that landed it: median 2.4 minutes, p90 3.1
(10 pull requests).

Cost of one change across the stages (runner-minutes):

| Change | Pull request | Dispatch | Queue | Push | Total |
|---|---|---|---|---|---|
| #10 share sheet and haptic spikes | 7.8 | 15.7 | 15.4 | 13.9 | 52.8 |
| #12 Uuid, typed ids, golden helper | 8.2 | 15.2 | 15.3 | 16.0 | 54.6 |
| #13 validators, first golden | 7.0 | 17.1 | 16.2 | not yet run | 40.4 so far |
| #6 Qt Quick shell (changes the workflow; 5 dispatches) | 7.5 | 77.0 | 18.5 | 19.9 | 122.9 |
| Six documentation-only pull requests (#4, #7, #8, #9, #11, #14) | 0.6 each | none | 0.5 to 0.8 | 10.5 to 14.6 | 11.6 to 16.0 |

Two things stand out. The push run is the largest single share (38%) and it builds in full for
a documentation-only merge, because `ci.yml` plans a push with `--force-all`. And 9 dispatches in a
day were spent on 5 branches; 2 failed, one of them a TSan failure the pull request gate cannot
see, and the result of none of them was used by the queue.

### 2.3 `iclforge`

`PR Gate` (the required gate; `pr-gate.yml`), by event:

| Event | Runs | Wall median / p90 / max (min), passing runs | Runner-hours |
|---|---|---|---|
| `pull_request` | 63 (51 pass, 9 fail, 3 cancelled) | 10.5 / 13.8 / 61.3 | 16.5 |
| `merge_group` | 68 (58 pass, 10 fail) | 18.0 / 36.8 / 68.0 | 44.4 |
| `push` to `main` | 34 (13 pass, 7 fail, 14 cancelled) | 26.1 / 30.8 / 32.5 (passing) | 23.2 |

Median job duration in the gate: `Linux GCC` 9.2 (pull request), 11.2 (queue), 15.3 (push);
`Windows MSVC` 15.7 (3 pull request runs), 18.2 (queue, p90 44.1), 23.5 (push); `Static checks` 4.0;
ESP32 image size guard 4.6 to 5.0; the two queue comparisons 6.2 (memory) and 8.2 (performance).
A queue run asks for about 35.8 runner-minutes at the median. Of 68 queue runs, 10 failed (15%);
6 of those 10 failed in `Windows MSVC`. From the queue run to the push that landed it: median
19.4 minutes, p90 29.2 (33 matched by commit).

The post-merge `ci.yml` (`CI`, tier `t2` on push, `all` on schedule):

| Event | Runs that started | Runs cancelled while waiting | Runner-hours per run | Wall (min) |
|---|---|---|---|---|
| `push` | 20 (1 pass, 19 fail) | 14 | 7.1 mean (in the 54-job runs: 2.1 to 3.5 on the self-hosted fleet, 1.7 to 2.2 hosted Linux, 1.8 to 2.8 Windows, 0.6 to 1.8 macOS) | 43 to 154, median 74 |
| `schedule` | 3 (all fail) | 0 | 17.5 mean | 117 to 123 |

Across the window the two workflows used 281 runner-hours: 84.7 in `PR Gate` and 196.6 in `ci.yml`
(70%). 19 of the 20 post-merge runs that started ended red, so a new failure is hard to tell from
an old one: the run is red whatever happened in the merges that triggered it. Only 68.2 of the 281
hours (24%) were in runs that passed. An earlier measurement in `ci-agentic.md` (September, 300 runs) found the same shape: 51% of requested time in cancelled
runs, 19% in failed ones and 27% in runs that passed.

### 2.4 How much of this is reusable

For every merged pull request, the tree that passed on the last ready pull request run (the merge
commit `refs/pull/<n>/merge` that run checked out, whose SHA is in the job log) was compared with
the tree that landed, using `git diff --name-only <tested> <landed>` on blobless fetches, and the
difference classified with the planner (`plan_gate.py`; for `iclforge` its own `plan_gate.py`). The
population that matters is the pull requests whose own diff asks for a build, because the planner
already asks for nothing on a documentation-only diff: the six documentation-only pull requests
of `icl-error-journaling` cost 0.5 to 0.8 runner-minutes in the queue.

| Tested tree against the tree that landed | `icl-error-journaling` (6 pull requests whose diff asks for a build) | `iclforge` (31 such pull requests with a tested tree) |
|---|---|---|
| Identical | 5 (#3, #5, #6, #10, #12) | 13 (42%) |
| Differs only in documentation or other non-build paths | 1 (#13, 2 files) | 1 |
| Differs in build inputs | 0 | 15 (median 18 files) |
| Differs in the gate's own files | 0 | 2 |

#3, #5 and #6 changed the workflow and are excluded by the rule in section 3.6, leaving #10, #12
and #13. Each of those three had a `workflow_dispatch` on the same head, so every group the queue
re-ran had a proof; they spent 46.9 of the 92.8 runner-minutes the queue spent on code changes.
Without the dispatch, only the queue-home group `build-linux-full` would have run (section 4.1).

The share of identical trees falls as the merge rate rises (a tree stays identical only while no
other pull request merges between the pull request run and the queue run), which is why the
design does not depend on it: the delta rule and the group skip tables are what keep reuse going
when the repository is busy. The `icl-error-journaling` figure is a ceiling for an idle
repository (merges there were mostly one at a time) and a poor predictor of a busy one; `iclforge`
is the closer guide, and section 8.2 measures it in production.

The claims about GitHub that the design rests on, and how they were checked here:

| Claim | Checked |
|---|---|
| A pull request run's merge commit stays fetchable by SHA after `refs/pull/<n>/merge` moves on | Yes: `0241cdd5` (superseded merge ref of #12) fetched by full SHA |
| A depth-1 blobless fetch of two commits is enough for `git diff --name-only` between them | Yes: 84 KB |
| Actions runs expose `path`, `head_sha`, `head_repository`, `event`, `run_attempt`; jobs expose `name`, `conclusion`, `run_id`, `head_sha` | Yes |
| Checks created by the Actions runner carry app id 15368 | Yes (`CI Status` check run) |
| The live required checks name no integration | Yes: `CI Status` and `Scan dependency diff` in `develop-protection`, no `integration_id` |
| A job with `actions: read` can download an artifact of another run | Documented, not exercised; step 3 of section 7.1 tests it first |
| `GITHUB_TOKEN` with `contents: write` can create a ref under `refs/ci/` | Not exercised; step 5 of section 7.1 tests it first |

## 3. Reusing results in the merge queue

### 3.1 Terms

| Term | Meaning |
|---|---|
| Group | One job of `ci.yml` that builds or tests: `build-fast`, `coverage`, `build-linux-full`, `build-macos`. It may call `build.yml` with several legs. It is the unit of reuse because `needs.<job>.result` is the only per-group result a caller sees. |
| Tested commit | The commit a run checked out: `github.sha`. For `pull_request` that is GitHub's merge of the head into the base, not the head. For `workflow_dispatch`, `merge_group` and `push` it is the run's `head_sha`. |
| Proof | A completed run of `.github/workflows/ci.yml` in which a group's jobs all have conclusion `success`, plus its tested commit. |
| Candidate | A proof for the pull request being queued: a pull request run or a dispatch on its head or on an earlier commit of its branch, or one of its earlier queue entries. |
| Group tree `G` | The tree of the queue entry (`github.sha` of the `merge_group` run, which is also the commit that lands, because the merge method is squash and the queue fast-forwards `develop` to it). |
| Delta | `git diff --name-only --no-renames <tested> <G>`: the paths in which the tree that passed differs from this one. |
| Barrier | The paths that define how results are produced (section 3.6). |

### 3.2 What a run records

The last job of `ci.yml` is `CI Status` (it already runs with `if: always()`). A new step, from a new
action `record-proof`, runs `scripts/ci_proof.py` and uploads one artifact, `ci-proof`, 14 days
retention, containing JSON with no secrets (artifacts of a public repository are public, standard
1.2 rule 12):

```json
{
  "schema": 1,
  "repository": "iainchesworthlabs/icl-error-journaling",
  "run_id": 42336845481, "run_attempt": 1, "event": "pull_request",
  "tested_sha": "0241cdd5edb2346ed6c74e4d7faf79d725d9706b",
  "head_sha": "2515ab38f628d57ff14dda35677b9c5ae7a306cd",
  "base_sha": "2d117d54fdfbd4b12044abd1c6de6d277c77f9b3",
  "barrier": { ".github/workflows": "<tree id>", "cmake": "<tree id>", "vcpkg.json": "<blob id>" },
  "groups": {
    "build-fast": { "result": "success", "legs": ["linux-gcc-release", "linux-clang-asan-ubsan"] },
    "build-linux-full": { "result": "skipped" }
  },
  "reused": { "coverage": { "run_id": "<id of the original run>", "tested_sha": "<its tested commit>" } }
}
```

`groups` comes from `toJSON(needs)`. `barrier` is `git rev-parse <tested_sha>:<path>` for each
barrier path. `reused` lists groups this run did not run and where they came from, always as the
original run, never as a chain, so a result is never trusted through more than one hop. The job
does a depth-1 checkout (`persist-credentials: false`) to read object ids and runs only the pinned
infra script; it executes no code from the tree under test.

The proof is a convenience, not the evidence. The conclusions that matter are read again from the
Actions API when a proof is used (section 3.3); the artifact only supplies `tested_sha` for
`pull_request` runs, the one event where the API does not state it.

### 3.3 Finding and proving an earlier result

A new job `reuse` in `ci.yml` (action `find-proof`, script `scripts/reuse_proof.py`) runs in every
event after `plan`. It never fails the workflow: any exception, API error or missing input makes it
emit the fallback "run every group the plan asked for" and log why. Permissions:
`contents: read`, `actions: read`, `pull-requests: read`.

For a `merge_group` entry, with `G = github.sha`, `B = merge_group.base_sha`, `N` from
`github.event.merge_group.head_ref` (`refs/heads/gh-readonly-queue/develop/pr-<N>-<sha>`):

1. Read the policy from the trusted base, not the tree under test: `git show B:.github/ci/plan.json`
   (groups, skip tables, barrier list, maximum age). The required groups are those the entry's own
   diff asks for (`git diff --name-only B G` through `plan_gate.py --groups`, the decision the
   planner makes today) whose home is the queue or earlier, plus those the diff promotes
   (section 4.1). A group the diff does not ask for is not required and not run, as now.
2. `GET /repos/{r}/pulls/{N}`: `head.sha` is `H`; `head.repo.full_name` must equal the repository (a null head
   repository counts as a fork), or the job stops with "fork: no reuse".
3. Gather candidate runs, newest first, at most 8, each a completed run with `path` equal to
   `.github/workflows/ci.yml`, `head_repository.full_name` equal to the repository and `created_at`
   within the maximum age (default 48 hours):
   - `GET /repos/{r}/actions/runs?head_sha=H&status=completed&per_page=100` filtered to events
     `pull_request` and `workflow_dispatch`;
   - `GET /repos/{r}/actions/runs?branch=<head ref>&event=workflow_dispatch&status=completed`
     (a full-matrix run on an earlier commit of the same branch; the delta rule below accounts for
     what has changed since);
   - `GET /repos/{r}/actions/runs?event=merge_group&status=completed&per_page=50` filtered to
     `head_branch` containing `/pr-<N>-` (this pull request's earlier queue entries, which matter when
     an entry ahead failed and this one was rebuilt).
4. For each candidate `R`: `GET /repos/{r}/actions/runs/{R.id}/jobs?per_page=100` (paginated;
   returns the latest attempt). A group is green in `R` when every job the policy lists for it
   (section 3.4) exists and has conclusion `success`, and the jobs found are exactly those jobs.
5. Tested commit `T(R)`: `R.head_sha` for `workflow_dispatch`, `merge_group` and `push`. For
   `pull_request`, download the `ci-proof` artifact of `R`
   (`GET .../runs/{id}/artifacts?name=ci-proof`, then `GET .../artifacts/{id}/zip`) and take
   `tested_sha`, and accept it only if the commit, fetched by SHA, has the PR head `H` as its second
   parent, has a first parent that is an ancestor of `B` (`git merge-base --is-ancestor`), and was
   committed no later than `R.created_at`. Anything else makes `R` unusable.
6. `git fetch --no-tags --depth=1 --filter=blob:none origin <T> <B>` (a few kilobytes).
7. Barrier check (section 3.6) for `T`, `B` and `G`. Failure makes `R` unusable.
8. Delta: if `rev-parse T^{tree}` equals `rev-parse G^{tree}` the delta is empty and nothing is asked
   for. Otherwise `git diff --name-only --no-renames T G`, then `plan_gate.py --groups` with the
   policy of step 1 returns the groups that delta asks for.
9. A required group `g` is reused from the newest `R` for which `g` is green, `g` is not asked for by
   `delta(T(R), G)`, and steps 5 to 7 passed. The required groups that are not reused run.

Outputs: `run` (JSON list of groups to run), `reused` (map from group to run id, run URL, tested
SHA, delta size and `equal-tree` or `delta`), and `mode` (`on`, `shadow`, `off`,
`fallback`). A repository variable `CI_REUSE_MODE` selects the mode; `shadow` computes and logs
everything and still runs every group, which is how the rollout starts (section 8).

For the `push` event the required groups are those asked for by the diff from `refs/ci/green/<group>`
to the pushed commit, and the candidates are the `merge_group` run with `head_sha` equal to the
pushed commit (identical tree: the squash commit is the entry's commit) and that ref's commit
(section 4.4). For `pull_request` the candidates are earlier
dispatch runs on the same head, so a `deep` run followed by marking the pull request ready does not
pay twice. For `workflow_dispatch` they are the pull request runs of the same head, so a `deep` run
costs only the groups that have not passed.

Cost: about 20 to 30 API calls per entry. The documented `GITHUB_TOKEN` limit is 1,000 requests
per hour per repository, so a burst of 20 entries in 10 minutes (the `iclforge` peak) is about 500;
the job lowers the candidate cap to 4 when the response headers show fewer than 300 requests left.

### 3.4 Which results count

Names are the check names the run reports: the calling job's name, then ` / `, then the leg name
for a called workflow (`build.yml`), or the plain job name for an inline job. Only the following
are evidence:

| Group (job id in `ci.yml`) | Job names that must all be `success` | Reusable |
|---|---|---|
| `build-fast` | `Build (fast) / linux-gcc-release`, `Build (fast) / linux-clang-asan-ubsan` | yes |
| `coverage` | `Coverage` | yes |
| `build-linux-full` (new, split from `build-full`) | `Build (Linux full) / linux-gcc-debug`, `Build (Linux full) / linux-clang-tsan` | yes |
| `build-macos` (new, split from `build-full`) | `Build (macOS) / macos-debug`, `Build (macOS) / macos-release` | yes |
| `ios-device` (new, moved from `ios-build.yml`) | `iOS (device, unsigned compile)` | yes |
| `macos-xcode27-release` | experimental, `continue-on-error` | never reused, never required |
| `policy`, `plan`, `zizmor`, `dependency-scan`, `confidentiality` | read commit text, labels, the range of commits or the base, not just the tree | never reused |

Conclusion `success` only. `skipped`, `neutral`, `cancelled`, `timed_out`, `failure`, `stale` and
`action_required` are not evidence. A group that was skipped because the plan did not ask for it
proves nothing about that group. A run whose overall conclusion is `failure` can still supply a
group whose jobs all succeeded. The group's leg list must equal the list in the policy read from
the base; adding or removing a leg therefore changes `plan.json`, which is on the barrier, and
reuse stops until a run with the new list exists.

### 3.5 Equal tree and different tree

- Equal tree: the entry's tree is `T(R)^{tree}`. Typical when the pull request was the last thing
  merged and is queued while its own run is current, or after a `deep` run on a head that is
  already up to date. Every group green in `R` is reused and the queue run is the cheap jobs only
  (0.6 to 0.7 runner-minutes at `icl-error-journaling`).
- Different tree: other pull requests merged since `T(R)`. The delta is exactly their changes (plus
  any difference in how this pull request applied). `plan_gate.py --groups` maps each path to the
  groups that read it: documentation and `no_build` paths ask for nothing; a path in a group's
  `skips` list does not ask for that group; a path the planner does not recognise, and the barrier
  paths, ask for every group. Groups not asked for are reused; the others run on the full group
  tree `G` (not on the delta, because a build is whole-tree; ccache keeps it cheap).
- No candidate at all (a documentation-only pull request, or the first queue entry of a new
  branch): a group the entry's own diff does not ask for is not run, exactly as the planner decides
  now; a group it asks for and nothing proves runs.

The skip tables are the part with a correctness risk, because a wrong skip is silent. They are
negative lists (paths a group provably does not read) and the default is to run. In
`icl-error-journaling`:

| Groups | `skips` (in addition to documentation and `no_build`) |
|---|---|
| `build-fast`, `coverage`, `build-linux-full` | `libs/*/src/platform/{macos,ios,android,windows,wasm}/**`, `apps/app/packaging/ios/**`, `**/*.mm` |
| `build-macos`, `ios-device` | `libs/*/src/platform/{linux,windows,android,wasm}/**` |

Shared code (`libs/*/src/*.cpp`, `include/**`, `tests/**`) is in no skip list, so it asks for
every group. The tables are tested by replaying the last N merged pull requests of each consumer
(a `scripts/replay_reuse.py`, modelled on `iclforge`'s `compare_planners.py`), and the nightly run
(section 4.1) runs every group on `develop` regardless, so a wrong skip is found within a day.

### 3.6 When reuse is refused

For each candidate, the object id of every barrier path must be identical in `T`, `B` and `G`
(`git rev-parse <commit>:<path>`; absent in all three also counts as equal). Any difference refuses
that candidate and the run asks for every group. The three-way comparison does two things: it
refuses when this pull request changes a barrier path (`T` and `G` differ from `B`), and when
another merge changed one since the proof (`T` differs from `G`).

| Barrier path | Why |
|---|---|
| `.github/workflows` | the workflow file and the reusable-workflow and action pins in it (`uses: ...@<sha>`) are inside these blobs, so equal trees mean equal pins; also the proof is only trusted if the workflow that produced it is the one on the base |
| `.github/actions`, `.github/ci` | local composite actions, `plan.json` (groups, skip tables, leg lists) |
| `.github/toolchain-versions.json` | compiler, Qt, CMake and Xcode pins |
| `cmake`, `CMakePresets.json`, top-level `CMakeLists.txt` | build definition, the vendored infra modules (`cmake/icl/SOURCE`) |
| `vcpkg.json`, `vcpkg-configuration.json`, `vcpkg-overlay-ports` | dependencies and the baseline |
| `tools/ci`, `tools/checks`, `tools/sanitizers` | scripts and suppression files the legs run |

A consumer can add paths in `plan.json` (`reuse.barrier`); it cannot remove the first four rows. A
proof older than `reuse.max_age_hours` (default 48) is refused whatever its trees, because hosted
runner images change weekly and the image is not part of any tree.

### 3.7 Security for a public repository

| Threat | Handling |
|---|---|
| Another GitHub App posts a check run named `CI Status` or a leg name with conclusion `success` | The Checks API accepts any name from any app with `checks: write`. The reuse job does not read check runs: it reads Actions runs and jobs, which only Actions creates, and requires `path` to be `.github/workflows/ci.yml` in this repository. The existing exposure is that the required checks name no integration, so such a check would also satisfy the ruleset today. Fix, an owner action (standard 1.2 rule 2): add `"integration_id": 15368` (GitHub Actions) to both entries of `required_status_checks` in `develop-protection`, in `admin/rulesets/develop-protection.json` and in each repository. |
| A fork pull request edits `ci.yml` so that its jobs pass | `pull_request` runs of a fork execute the fork's workflow file, with a read-only token and no secrets. Reuse is refused for any pull request whose head repository is not this one (step 2), and the barrier check refuses any pull request that changes `.github/workflows`. A fork pull request therefore always runs every group in the queue. |
| A same-repository branch edits `ci.yml` | The barrier refuses. Editing the workflow is already a way to make a pull request's own checks pass; the protection is review of `.github/` changes (`CODEOWNERS` already lists the owner; reviews are not required while there is one maintainer, standard 12.2). Reuse adds no new exposure beyond that. |
| A test or build step forges the proof | Build jobs only get `contents: read`. The proof is written by `CI Status`, which runs no code from the tree. Even a forged `tested_sha` is checked against the API (`H` as second parent, first parent on the base's history, not later than the run). A pull request author controls its own tests, which can already be made to pass; reuse does not widen that, and it never lets one pull request's tests vouch for a different pull request's change, because the delta between the tested tree and `G` is planned afresh. |
| Poisoned caches | Unchanged: caches written by a pull request run are scoped to its ref and invisible to the queue and to `develop`. |
| A stale proof | Age cap; Actions API read of the latest attempt; `refs/ci/green/*` moves only forward. |
| Token scope creep | See the table below. Nothing gets `checks: write`, `statuses: write` or `actions: write`, except the optional `deep` label workflow (`actions: write`, `pull_request` event only, same-repository heads only). |

`GITHUB_TOKEN` scopes (top-level `permissions: {}` stays, standard 11.1):

| Job | Events | Scopes | Used for |
|---|---|---|---|
| `plan` | all | `contents: read` | checkout, planner |
| `reuse` | `pull_request` (same repository), `merge_group`, `push`, `workflow_dispatch` | `contents: read`, `actions: read`, `pull-requests: read` | list runs, jobs and artifacts, read the pull request head |
| build and coverage groups | all | `contents: read` | as today |
| `ci-status` | all | `contents: read` | aggregate, upload `ci-proof` (the artifact service uses the runner's own token) |
| `mark-green` (new, last job of the `push` run) | `push` only | `contents: write` | move `refs/ci/green/<group>` (a ref outside `refs/heads` and `refs/tags`, which none of the five rulesets in use targets; to be confirmed by step 5 of section 7.1) |
| `report-red` (new) | `push` only | `issues: write`, `pull-requests: write` | open or update the failure issue and comment on suspects |

### 3.8 How the required check always reports

- `ci.yml` keeps the `merge_group` trigger and has no path filters, so `CI Status` exists in every
  event. The job keeps `if: always()`, a 5-minute timeout, and the exact name `CI Status`.
- The `reuse` job cannot fail the workflow (section 3.3). If it errors or is cancelled its outputs
  are empty, and every group's `if:` and every `expected` entry treats empty as "run".
- A group that is skipped because it was reused is `expected: false` in the map that `ci-status`
  already takes, so it is allowed to be skipped. A group the plan asked for, not reused and
  skipped, still fails the aggregate, and so does one with no result (standard 11.5 rule 3 and
  `check_needs.py` as it stands). The only change is that `expected` is now
  `plan asked && !reused`.
- `ci-status` takes one new optional input, `reused` (the `reuse` job's JSON). It writes a table
  to the job summary and one `::notice` per reused group, for example `Build (fast) reused from run
  42336845481 (pull_request, tested 0241cdd5, delta 2 files, none of them read)`. If `reused`
  names a group but the `reuse` job's result is not `success`, the entry is ignored.
- The required check names do not change, so no ruleset edit is needed for this.

## 4. Where the expensive legs run

### 4.1 Stage placement

Each group has a home: the earliest stage by which it must have passed on the tree that lands. A
run in a later stage runs the group only if no valid proof exists (section 3.3).

| Group | Home | Also in the queue when the entry's diff touches | Cost today (median, min) |
|---|---|---|---|
| `policy`, `plan`, `zizmor`, `dependency-scan`, `confidentiality` | every pull request and every queue entry; not repeated on push (standard 11.5 rule 4) | | 0.1 to 0.2 each |
| `build-fast` (GCC release, Clang ASan/UBSan) | pull request (ready) | | 1.8 and 1.9 |
| `coverage` | pull request (ready) | | 1.9 |
| `build-linux-full` (GCC debug, Clang TSan) | queue | pull request, if the consumer lists threading paths for it (none yet) | 1.8 and 1.8 |
| `build-macos` (debug, release) | post-merge | `platform/macos`, `platform/ios`, `*.mm`, `libs/ios_bridge`, `apps/app/packaging/ios` | 2.0 and 1.7 |
| `ios-device` | post-merge | same as `build-macos` | 5.6 to 6.5 |
| `macos-xcode27-release` (experimental) | nightly | | 1.7 |

Draft pull requests run the cheap jobs only (standard 11.5 rule 8, unchanged). A ready pull
request runs the home-`pull request` groups. A queue entry runs home `pull request` and
`queue` groups, plus groups promoted by its own diff (`diff(B, G)`). A push to `develop` runs every
group not yet green on the pushed tree and not asked for by the delta since its last green commit
(section 4.4). The nightly run runs everything and moves every `refs/ci/green/*`.

Expected cost, from the measured medians (arithmetic, not measurement):

| Change at `icl-error-journaling` | Today | After, reuse misses | After, reuse hits |
|---|---|---|---|
| Code change, no dispatch | 37 to 40 (7.8 + 15.4 + 13.9; 8.2 + 15.3 + 16.0) | 6.6 + 9.8 + 5.4 = 21.8 | 6.6 + 4.2 + 5.4 = 16.2 |
| Code change with a `deep` dispatch | 53 to 55 | 6.6 + 8.0 + 9.8 + 5.4 = 29.8, if the tree moved and the delta asks for everything | 6.6 + 8.0 + 0.6 + 0 = 15.2 (the dispatch reuses the pull request groups; the queue and the push reuse the dispatch) |
| Documentation-only | 11.6 to 16.0 | 1.5 | 1.5 |
| Change that edits the workflow | 122.9 (#6) | 7.5 + 9.8 + 5.4 = 22.7: no reuse, but one pass | same |

"Miss" is a queue entry that must run all of `build-fast`, `coverage` and `build-linux-full` (9.8
runner-minutes with the cheap jobs). "Hit" is a tree whose pull request run covered the first two,
leaving `build-linux-full` (3.6) and the cheap jobs (0.6); the dispatch of 8.0 is `build-linux-full`
and `build-macos` (3.6 each) and the cheap jobs. The 5.4 for the push is the two macOS groups; it is shared by every change in a batch and is zero for a batch of documentation. The
iOS compile adds 6.5 macOS minutes to the push when the batch touched Apple paths.

### 4.2 The `deep` label and a manual full-matrix run

Both produce a proof for every group. A `workflow_dispatch` of `ci.yml` (default `groups=all`)
checks out the branch tip, so its tested commit is the head itself, known from the API. The `deep`
label (standard 12.4) is wired by a small consumer workflow on `pull_request` `labeled`, same-repository
heads only, that dispatches `ci.yml` on the head ref (the `iclforge` `Deep CI on label` pattern; a `labeled` type on
`ci.yml` itself would cancel the pull request's running gate through its concurrency group, so it
is not used). Because the `reuse` job also runs inside a dispatch, a `deep` run reuses the groups
the pull request run already proved and costs only the others.

For agents (`AGENTS.md` and standard 11.5 rule 12): dispatch only when the branch is final, and
only for a change to threads, the standard library, platform code or CMake; any later push that
touches a path a group reads makes that group's proof unusable, and one that touches only
documentation does not.

### 4.3 The push to `develop`

The run on `develop` stays single-flight with one waiting (standard 11.5 rule 7; `ci.yml`
already has `cancel-in-progress` off for pushes). It changes in three ways:
it no longer plans with `--force-all`; it runs only `plan`, `reuse`, the groups, `mark-green`,
`report-red` and `ci-status` (no policy, zizmor or confidentiality, which the queue ran on the
same commit); and it asks, per group, for the delta since `refs/ci/green/<group>`.

### 4.4 Attributing a post-merge failure

`mark-green` runs after a push run and, for each group green on the pushed tree (run now or
reused with an empty delta), moves `refs/ci/green/<group>` to the pushed commit, fast-forward
only. The nightly run moves them all. Because pushes are batched and a waiting run can be
replaced by a newer one, the commits between two runs of a group are exactly the commits between
its green ref and the tested one.

When group `g` fails on commit `T`:

1. Suspects: `git log --first-parent --format='%H %s' refs/ci/green/g..T`. Squash subjects end in
   `(#N)`, so each commit gives a pull request number.
2. `report-red` opens or updates one issue per group (`main-red: build-macos`), listing the failed
   jobs with a log excerpt, the suspects, and whether `g` was reused for any of them (with the
   source run). A reused group that later fails is the signal for a false reuse and is counted in
   section 8.2. It comments once on each suspect pull request. One suspect: the revert command.
   Several: a bisect recipe. `workflow_dispatch` needs a branch or tag, not a SHA, so the recipe
   creates `agent/bisect-<group>-<sha7>` at the midpoint and runs
   `gh workflow run ci.yml --ref agent/bisect-... -f groups=g`: one group per probe, about 3 probes
   for a batch of 8.
3. Nothing is reverted automatically, and the issue closes when `g` next passes (standard 11.5
   rule 1; `iclforge` `main-health.yml` does the same).

Per-group refs also fix the `iclforge` symptom in section 2.3: a macOS failure no longer hides a
new Linux failure, because the run is judged per group against its own last green commit.

## 5. Merge-collision hotspots

`changelog.d` is already enforced by the Policy job (`check_changelog_fragment.py`) and prevents
the `CHANGELOG.md` collision. The other shared files were found by listing the files of every pull
request of `icl-error-journaling` (#4 to #17; #1 to #3 are Dependabot and bootstrap) and, for scale,
the last 99 merged pull requests of `iclforge`.

### 5.1 What collides

Files touched by more than one pull request in `icl-error-journaling`:

| File | Pull requests | Concurrent pairs sharing it |
|---|---|---|
| `libs/core/CMakeLists.txt` | #6, #12, #13, #15, #16, #17 | 5 |
| `libs/core/tests/CMakeLists.txt` | same six | 5 |
| `docs/architecture.md` | #6, #10, #12, #15, #16 | 1 |
| `docs/testing.md` | #6, #10, #12 | 0 |
| `docs/plan/stage-2.md` | #4, #9, #11 | 0 |
| `docs/plan/stage-1.md` | #7, #8 | 0 |
| `.github/workflows/ci.yml`, `docs/ci.md` | #5, #6 | 1 |
| `config/sample-config.json`, `tools/tests/test_confidentiality.py` | #5, #16 | 0 |

Of 15 pairs of pull requests open at the same time, 6 shared a file, 5 through the two `libs/core`
CMake lists. The conflict is real today: `git merge-tree` of the heads of #15 and #16 reports
content conflicts in `libs/core/CMakeLists.txt` (both insert a source file before
`export_renderer.cpp`: `day_prompt.cpp` against `configuration.cpp`) and in `docs/architecture.md`
(two additions to the same file list). #17 merges cleanly with both. In `iclforge` the most-edited
files over 99 merges are `CHANGELOG.md` (edited directly in 15), `docs/forge/cli/commands.md`
(14), `ROADMAP.md` (10), `.github/workflows/_ci-core.yml` (9), `tools/checks/projects.json` (7),
`docs/projects.md` (7), and the committed Qt translation catalogues (7 each, in at least six
languages). They are the same kinds: lists that grow, tables, a registry, and generated catalogues.

The files you named, checked in `icl-error-journaling`:

| File | Evidence | Verdict |
|---|---|---|
| `tools/coverage-floors.json` | 2 commits since creation. Each new component appends a key at the end of `components`, which also changes the previous last line (the comma). | Will collide when libraries are added in parallel. Fix below. |
| `tools/preprocessor-baseline.json` | Never edited after creation; content `{"files": {}}`. Per-file keys by design (standard 4.4); a file with no entry is zero, so new files add nothing. | Leave. It can only collide when two pull requests lower neighbouring entries. |
| `.github/ci/plan.json` | 2 commits since creation. The `gui` list names `libs/core/**` and `libs/storage/**` by component. | Rare. Becomes the policy file for groups and reuse (one pull request), then stable. Replace the named entries by `libs/**` while every library installs Qt. |
| `mkdocs.yml` nav | 3 commits since creation. One line per page. | Leave. Avoiding it needs a nav plugin or omitting pages from the nav; neither is worth it for one-line conflicts that resolve trivially. |
| CMake source lists | See the first two rows above. | Fix below. |
| `docs/plan/*` | stage files edited by 5 pull requests (#4, #7, #8, #9, #11) in under two hours, all recording decisions or breakdowns. | Fix below. |
| `docs/architecture.md`, `docs/testing.md` | 5 and 3 pull requests; #15 and #16 conflict. | Fix below. |

### 5.2 Layout

| Hotspot | Change | Effect |
|---|---|---|
| Library sources in `libs/*/CMakeLists.txt` | `file(GLOB ... CONFIGURE_DEPENDS src/*.cpp)` for the top-level `src/` of each library; `src/platform/<os>/` stays an explicit list because the platform is selected there | A new source file adds no line to a shared file. Cost: a stray `.cpp` in `src/` is compiled. CMake documents globbing as a trade-off; `CONFIGURE_DEPENDS` removes the stale-build half of it. |
| Test sources in `libs/*/tests/CMakeLists.txt` | `file(GLOB ... CONFIGURE_DEPENDS test_*.cpp)` plus `golden*.cpp` helpers by name | One new test file, no edit to the list |
| Coverage floors | Per-component file `coverage-floor.json` beside the component's `CMakeLists.txt` (`{"line": 90, "branch": 85}`); `coverage_gate.py` gets `--floors-glob 'libs/*/coverage-floor.json' --floors-glob 'apps/*/coverage-floor.json'` and keeps the root file for `default` only | A new library adds its own file; the `--write-floors` ratchet touches only components that moved |
| `docs/architecture.md` file lists | Keep layering rules and the component table in `architecture.md`; move each component's files and notes to `docs/components/<name>.md` | A pull request edits its component's page; `architecture.md` changes when a layer rule changes |
| `docs/testing.md` | Same: one page per test area under `docs/testing/` | |
| `docs/plan/stage-N.md` | After the owner approves a stage breakdown, decisions are one file each, `docs/plan/decisions/<stage>-<slug>.md`, linked from the stage file once at approval time | Decision records never collide |
| Fragment names | `changelog.d/<slug>.<type>.md` with `<slug>` equal to the branch slug (the part after `feature/`). In `icl-error-journaling` 4 of 6 fragments already match. Warn, do not fail, in `check_changelog_fragment.py` | Two pull requests cannot pick the same slug |

The three CMake and coverage changes need `check_platform_isolation` and the preprocessor check to
keep passing; neither reads the lists. The owner decided to adopt globbing
(section 9, decision 4), although it changes a habit the standard does not address either way.

## 6. Queue settings and capacity

### 6.1 Budget

GitHub Free allows 20 concurrent hosted jobs and 5 macOS, organisation-wide (standard 11.5 rule 10),
shared by all the repositories. Waiting for a runner costs time, not correctness: jobs queue. So the
budget decides latency, and the allotment below is a planning figure for `icl-error-journaling`,
not an enforced quota.

| Quantity | Value |
|---|---|
| Hosted Linux slots assumed for `icl-error-journaling` | 10 of 20 (the rest: `iclforge`, other consumers) |
| macOS slots assumed | 2 of 5 |
| Heavy jobs per ready pull request run | 3 (GCC release, ASan/UBSan, coverage) |
| Heavy jobs per queue entry, today | 5 Linux, 3 macOS (8) |
| Heavy jobs per queue entry, after, worst case (delta asks for all) | 5 Linux (`build-fast` 2, `coverage` 1, `build-linux-full` 2), 0 macOS; 2 macOS when promoted |
| Heavy jobs per queue entry, after, expected | 0 to 2 Linux on a hit (section 4.1) |
| Four entries building, today / after worst case | 20 Linux + 12 macOS / 20 Linux + 0 to 8 macOS |
| Post-merge run, after | 2 macOS (+1 iOS) at one run at a time, 0 on a documentation batch |

Demand arithmetic for the burst the `iclforge` notes record (20 merges in 10 minutes): at
`icl-error-journaling`'s 3-minute entry wall time the arrival rate times the wall time is 120/hour
x 0.05 hour = 6 entries in flight. Four builds in parallel therefore cost a wait of about one entry
at the burst. Entries that miss entirely would want 20 Linux jobs against the 10 allotted, so each
would take about twice as long (6 minutes rather than 3); the strict worst-case rule
(10 slots / 5 jobs = 2 builds) is not adopted because a miss on everything is rare once reuse works,
and section 8.2 adds the runner-wait metric that says when to lower the number. The macOS figure is
the real constraint: today four entries can ask for 12 macOS jobs against 5, and the measured start
delay stayed under 8 minutes only because merges rarely overlapped. Moving the
macOS groups to the push run (one run at a time) removes that fan-out.

For `iclforge`, 8 entries each asking for 6 heavy hosted jobs (Linux GCC, Windows MSVC, static
checks, two comparisons, ESP32 image) is 48 against 20. The measured queue wall time (median 18,
p90 36.8, max 68 minutes, against a longest job of 18 minutes at the median) is that backlog. Its
`max_entries_to_build` stays at 8 until the reuse rate is measured (section 8.2; decision 7 of
section 9), although the standard says "start at 4" (12.2); it is retuned from the measurement.

### 6.2 Settings

| Setting | `icl-error-journaling` now | After | `iclforge` now | After | Reason |
|---|---|---|---|---|---|
| `merge_method` | SQUASH | keep | MERGE | keep | Section 3.1 relies on the entry commit landing unchanged |
| `grouping_strategy` | ALLGREEN | keep | ALLGREEN | keep | A failing entry is named by its own `CI Status`; with reuse a rebuilt entry costs little |
| `max_entries_to_build` | 4 | 4 | 8 | 8, then retune from section 8.2 | Section 6.1 |
| `max_entries_to_merge` | 5 | 5 | 5 | 5 | Groups of 5 mean one push run per group of merges |
| `min_entries_to_merge` | 1 | 1 | 1 | 1 | |
| `min_entries_to_merge_wait_minutes` | 1 | 1 | 5 | 1 | A fixed 5 is a large share of an 18-minute latency (`branch-protection.md`) |
| `check_response_timeout_minutes` | 180 | 45 | 180 | 90 | Longest queue run measured: 10 minutes wall at `icl-error-journaling`, 68 at `iclforge` (p90 36.8). A stuck entry should free its place. |

Job timeouts: `build.yml` allows 90 minutes per leg and the measured median is 2
(`icl-error-journaling`) to 18 (`iclforge`); the consumer sets a per-leg `timeout_minutes` (a new
optional matrix key, default the existing input), 30 at `icl-error-journaling`. `reuse`,
`ci-status`, `mark-green` and `report-red` get 5.

Concurrency: unchanged. Pull request runs cancel superseded pushes; queue entries and pushes
never cancel; the push group keeps one running, one waiting, and the newest takes the waiting place.

The ruleset edits are applied by `admin/apply.sh` after the owner approves (standard 1.2 rule 2).

## 7. Changes needed

### 7.1 `icl-common-infra`

One pull request per step (standard 11.5 rule 13). Each adds its tests to `scripts/tests` and runs
`python scripts/precheck.py` and the existing `Script tests` job. The tests for steps 1 to 3 include
fixtures of recorded API responses and git trees from the pull requests measured above, and the
spoofing cases of section 3.7 (a run from another workflow file, from a fork, a skipped group, a
bad parent, a changed barrier, a missing artifact, an HTTP error, a stale proof).

| # | Change | Files |
|---|---|---|
| 1 | Planner groups: `plan_gate.py --groups` reads a `groups` table in `plan.json` (home, `skips`, `promote`, job names, leg list) and prints `groups=<json>` for a path list; unchanged output otherwise. Add the `reuse` section (barrier, max age) and its defaults. | `scripts/plan_gate.py`, `scripts/tests/test_plan_gate.py`, `docs/using.md` |
| 2 | Proof writer: `ci_proof.py` and the action `record-proof`. | `scripts/ci_proof.py`, `actions/record-proof/action.yml`, tests |
| 3 | Proof finder: `reuse_proof.py` and the action `find-proof` (inputs: `plan-config`, `mode`, `stage`; outputs `run`, `reused`, `mode`). It takes an optional `--planner` command so a consumer with its own planner (`iclforge`) can map paths to groups. Integration test of the artifact download first. | `scripts/reuse_proof.py`, `actions/find-proof/action.yml`, tests |
| 4 | `ci-status`: optional input `reused`, summary table and notices; `check_needs.py --reused`. | `actions/ci-status/action.yml`, `scripts/check_needs.py`, tests |
| 5 | Green refs and failure reports: `mark_green.py` and action `mark-green`; `report_red.py` and action `report-red` (pattern: `report-nightly-failure`). | `scripts/`, `actions/`, tests |
| 6 | Per-component coverage floors: `coverage_gate.py --floors-glob`. | `scripts/coverage_gate.py`, tests, `docs/using.md` |
| 7 | `build.yml`: optional per-leg `timeout_minutes`. | `.github/workflows/build.yml` |
| 8 | Metrics: `ci_metrics.py` and `templates/ci-metrics.yml` (the weekly job of standard 11.5 rule 11). | `scripts/ci_metrics.py`, `templates/`, tests |
| 9 | Administration and standard: `integration_id` on the required checks and the queue parameters of section 6.2 in `admin/rulesets/`; `docs/standard.md` 0.15 (section 7.3); `docs/using.md`. | `admin/rulesets/*.json`, `docs/` |
| 10 | Tag `v0.1.20` (owner decision, section 9), the next tag on the monotonic `v0.1.x` line. | tag (owner) |

Steps 2, 3 and 4 add no behaviour until a consumer calls them.

### 7.2 A consumer (`icl-error-journaling` first)

| # | Change | Effect |
|---|---|---|
| 1 | `.github/ci/plan.json`: `groups` and `reuse` sections. Inert. | |
| 2 | `ci.yml`: split `build-full` into `build-linux-full` and `build-macos`; add the `record-proof` step to `CI Status`; add `timeout_minutes` to legs. Same checks run as today. | Proofs start to exist |
| 3 | `ci.yml`: add `reuse` after `plan`, `CI_REUSE_MODE=shadow`, `expected` and `if:` conditions written as `asked && !reused`. Everything still runs; the job summary shows what would have been skipped. | Shadow measurements |
| 4 | `ci.yml`: `CI_REUSE_MODE=on`; home stages per section 4.1; `push` plans per group from `refs/ci/green/*`; `mark-green` and `report-red` jobs; `workflow_dispatch` inputs `groups` (default `all`); drop policy, zizmor and confidentiality from `push`. | Savings begin |
| 5 | `deep-ci.yml`: the label workflow of section 4.2. | |
| 6 | Move `ios-build.yml` into `ci.yml` as `ios-device`; remove the path-filtered pull request trigger. | iOS compile joins the scheme |
| 7 | Layout changes of section 5.2, one pull request each, in the order CMake lists, docs split, decisions folder, per-component floors. | Fewer conflicts |
| 8 | Update `docs/ci.md`, `AGENTS.md` (dispatch rule, fragment slug, where to record a decision). | |
| 9 | Owner: `admin/apply.sh` for the rulesets (`integration_id`, queue settings). | |

Other consumers repeat steps 1 to 5 (Dependabot moves the pin; `plan.json` and `ci.yml` are theirs).
`iclforge` has its own planner and an `_ci-*` workflow set, so it uses the `--planner` adapter and
`legs.jsonc`, which already holds `tier` per leg.

### 7.3 Edits to `standard.md` when this is merged and implemented

| Section | Edit |
|---|---|
| 11.2 | Table rows say which group runs where, by home stage, and that a stage runs a group only without a valid proof |
| 11.3 | Required checks are pinned to the GitHub Actions integration |
| 11.5 rule 1 | Attribution is per group against `refs/ci/green/<group>` |
| 11.5 rule 7 | The post-merge run plans per group from the delta since the group's green ref |
| 11.5 rule 9 | `deep` and dispatch feed reuse; they are cheaper because they reuse |
| 11.5 rule 12 | Dispatch only for a final branch |
| 11.5 rule 13 | Add the layout rules of section 5.2 and the fragment-slug convention |
| 12.2 | Queue timeout and entry settings of section 6.2 |

## 8. Rollout and measurement

### 8.1 Order

| Phase | What | Exit |
|---|---|---|
| 0 | Record the baseline (below) from the runs of the previous 7 days for `icl-error-journaling` and `iclforge`, with `ci_metrics.py`. | Numbers in the tracking issue |
| 1 | `icl-error-journaling`, infra steps 1 to 4 and consumer steps 1 to 3: proofs recorded, `reuse` in shadow mode. | 50 queue entries or 7 days, whichever is later; shadow disagreements all explained; zero false reuse (a group the job would have skipped that failed when it ran) |
| 2 | Consumer step 4: `CI_REUSE_MODE=on` for `merge_group` and `push`; `mark-green` and `report-red`. | 2 weeks at the targets below |
| 3 | `virtual-serial-studio` first (the most active: 100 `ci.yml` runs between 2026-11-06 and 2026-11-07), then `arinc-data-loader`, `cubeulator`, `snapandspell`, `countdownsolver`, each shadow first. A code search finds the infra `ci-status` action in all five `ci.yml` files; whether each also uses the infra planner was not checked. A Dependabot bump of the pin brings the actions. | Each repeats phase 1 and 2 on a shorter clock (20 entries) |
| 4 | `iclforge`, with the `--planner` adapter and its own groups, after its queue timeout and wait are changed (section 6.2). It has the largest saving and the largest chance of a wrong skip. | Phase 1 and 2 clocks as for the first repository |
| 5 | Layout changes (section 5.2) and standard 0.15 land with phase 2. | |

`aqualink-automate` has no `merge_group` run in `ci.yml` and is out of scope until it has a queue.

### 8.2 What to measure

`ci_metrics.py` runs weekly from the template and prints these per repository (standard 11.5 rule
11 asked for the first four). Sources: `gh api repos/{r}/actions/runs` and `.../jobs`, the
`refs/ci/green/*` refs, and the shadow-mode summaries.

| Metric | Definition | Baseline `icl-error-journaling` | Baseline `iclforge` | Target |
|---|---|---|---|---|
| Queue time per merge | First `merge_group` run of the pull request to the `push` run on the commit that landed it (match on SHA) | median 2.4, p90 3.1 min | median 19.4, p90 29.2 min | no worse at `icl-error-journaling`; `iclforge` median 12, p90 20 |
| Runner-minutes per merged change, code | Sum of job durations of all `ci.yml` runs (all events) tied to the change by branch, queue branch and squash title, split Linux / macOS | 52.8 and 54.6 (#10, #12; #13 is at 40.4 before its push) | about 5.7 runner-hours per merge (281 h in the sampled workflows over 49 merges; not split by change type) | at most 40% of baseline at `icl-error-journaling` (about 20); at most 60% at `iclforge` |
| Runner-minutes per merged change, documentation-only | same | 11.6 to 16.0 | | at most 2 |
| macOS minutes per merged change | same, macOS jobs only | 31.3 queue + 54.6 push + 49.6 dispatch over 14 merges | | at most 40% of baseline |
| Reuse rate | Groups reused / groups required in queue and push runs, by `equal-tree` and `delta` | not available | not available | at least 50% of required groups in the queue at `icl-error-journaling` |
| False reuse | A reused group that failed when it next ran (post-merge, nightly, or a later non-reused run of the same tree) | not available | | 0; any occurrence is investigated before the next merge |
| PR gate duration | Median and p95 wall time of ready `pull_request` runs (standard 11.5 rule 11) | median 2.7 min (6 runs) | median 10.5, p90 13.8 min | median at most 10, p95 at most 20 |
| Wasted share | Runner-minutes in cancelled and failed runs / total | not computed | 24% of hours in runs that passed (section 2.3); 10 of 68 queue runs failed | track |
| Post-merge time to name the cause | Failure to the issue that lists the suspects | no process | `main-health.yml` comments on suspects; not measured | under 10 minutes |
| Runner wait | p90 of a job's `started_at` minus its run's `created_at`, queue entries and push runs, split Linux / macOS | Linux median 0.0, max 1.6; macOS median 0.2 to 0.3, max 7.2 min | not computed | p90 under 2 minutes; above that, lower `max_entries_to_build` |
| API calls per queue entry and `reuse` job duration | From the job log | | | under 40 calls, under 60 seconds |

Rule of the standard, kept: when a target is missed for two weeks, fixing it comes before new CI
features.

## 9. Decisions

Recorded from the owner's acceptance of the recommendations in the first version of this section.

1. **Where macOS and iOS are gated.** macOS and iOS are gated in the post-merge run, unless the
   entry touches Apple-specific paths or carries `deep`. A change that breaks only macOS can
   therefore land, and is found minutes later with the pull request named. Keeping the macOS groups
   in the queue would cost 5.4 macOS minutes per code change and, at four entries, up to 12 macOS
   jobs against a limit of 5. (owner, 2026-11-07)
2. **Reuse of pull request runs.** Pull request runs may be reused, with the checks of section 3.3
   (a `pull_request` run tests GitHub's merge commit, and only the run's own artifact says which
   commit that was). There is no reuse for fork pull requests. Setting `integration_id: 15368` on
   every required check in every repository is an owner action (section 3.7) that is applied
   regardless of the other decisions. (owner, 2026-11-07)
3. **What a red `develop` does.** A red `develop` reports and names suspects; it does not block the
   queue or revert. Revisit if the false-reuse or time-to-fix metrics (section 8.2) are poor.
   (owner, 2026-11-07)
4. **Globbing.** Adopt `file(GLOB ... CONFIGURE_DEPENDS)` for library and test sources
   (section 5.2). (owner, 2026-11-07)
5. **Version.** The reuse work is tagged `v0.1.20`, the next tag on the monotonic `v0.1.x` line
   (owner, 2026-11-07; this replaces an earlier `v0.2.0-beta.1`).
6. **The `xcode-27` experimental leg.** It runs nightly only. (owner, 2026-11-07)
7. **`max_entries_to_build` for `iclforge`.** It stays at 8 until reuse is measured (section 8.2).
   (owner, 2026-11-07)

## 10. Not proposed, and risks

- Test-level impact selection (running only the tests a diff can affect) is the next step and needs
  a coverage map first; `iclforge` lists it as not built. Reuse here is per group, not per test.
- `linux-gcc-release` and `coverage` both build with GCC and run every test, once without and once
  with coverage instrumentation, so each pull request pays for two similar jobs. Merging them is a
  separate change with its own measurement.
- HEADGREEN grouping would let one green head merge the whole group, but it removes the per-entry
  check that names the failing pull request; not proposed.
- The skip tables and the barrier are the risk: a missing skip only costs minutes, a wrong skip is a
  silent miss. The controls are the default of "run", shadow mode, the replay test, the nightly
  run of every group, and the false-reuse metric.
- Reuse cannot see changes outside the tree: the runner image, a vcpkg registry change that is not in
  the baseline, a secret. The age cap and the nightly run bound them.
- The measurements for `icl-error-journaling` are one day on a nearly empty application, and the
  `iclforge` window is 2.5 days during which its post-merge run was almost always red. Both should
  be re-taken for phase 0.

This document changes no workflow and no setting; merging it records the design and the owner's decisions of section 9.
