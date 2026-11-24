# Using icl-common-infra

## Workflows

All are `workflow_call`. Required status checks must be jobs defined in the caller, because
a check from a called workflow is named `<caller job> / <called job>`. The caller therefore
defines two jobs by name: `CI Status` (using the `ci-status` action) and
`Scan dependency diff` (using the `dependency-review` action).

| Workflow | Purpose | Main inputs |
|---|---|---|
| `policy.yml` | Branch name, commit and PR text, preprocessor policy, action pinning, changelog fragment, vcpkg baseline in fork, REUSE. Runs on drafts. | `base-ref`, `runner`, `skip-changelog` |
| `build.yml` | Build and test a list of legs with CMake presets. | `legs` (JSON, see the file header; a leg may set `timeout_minutes`, default the input), `timeout-minutes` |
| `codeql.yml` | Nightly code scanning; opens a `nightly-analysis` issue on failure. | `languages` (JSON; an entry may name a CodeQL `queries` suite, or set `skip_qt` for a build that does not use Qt), `runner` |
| `docs.yml` | `mkdocs build --strict`; uploads the Pages artifact when `upload: true`, and the plain site as an artifact when `site-artifact` is set. | `requirements`, `upload`, `site-artifact`, `runner` |
| `docs-deploy.yml` | Publishes the Pages artifact from the same run. Needs `pages: write` and `id-token: write` on the calling job. | `runner` |
| `docs-deploy-aws.yml` | Publishes the built site to S3 behind CloudFront by OIDC, or removes a pull request preview. Needs `contents: read`, `id-token: write` and `pull-requests: write` on the calling job. See "Docs on AWS". | `prefix`, `mode`, `artifact-name`, `preview`, `pr-number`, `region`, `site-url`, `production-ref`, `runner`; secrets `DOCS_ROLE_ARN`, `DOCS_PREVIEW_ROLE_ARN`, `DOCS_BUCKET`, `DOCS_DISTRIBUTION_ID` |
| `release-publish.yml` | Tag checks, release notes check, SHA-512 sums, GPG signatures checked against the committed public key, SBOM, attestations, optional project verification, GitHub Release, fast-forward of `main`. | `artifact-pattern`, `generate-sbom`, `public-key`, `verify-script`, `pre-release-script`, `spdx-sbom`, `cyclonedx-sbom`, `notes-script`, `draft`, `title` |
| `zizmor.yml` | Workflow static analysis, at the version the caller pins in `ci/requirements-zizmor.txt` (or this repository's, without the file). | `min-severity`, `requirements-file`, `runner` |
| `dependabot-auto-merge.yml` | Enable auto-merge when every dependency a Dependabot pull request updates is a minor or patch bump in an allowed ecosystem (a grouped pull request with one major waits for a person). | `ecosystems`, `merge-method` (empty for a branch with a merge queue), `runner`, secret `MERGE_QUEUE_TOKEN` |

## Runners

`policy.yml`, `codeql.yml`, `zizmor.yml`, `docs.yml`, `docs-deploy.yml`, `docs-deploy-aws.yml` and
`dependabot-auto-merge.yml` take an optional `runner` input: a JSON array of runner labels, default `["ubuntu-24.04"]`.
Every job of the workflow uses it as `runs-on: ${{ fromJSON(inputs.runner) }}`, including the preview removal of
`docs-deploy-aws.yml`. A caller that does not pass it gets the hosted `ubuntu-24.04` job it always had. `build.yml` takes
a `runner` per leg, and `release-publish.yml` has no such input: it runs on hosted `ubuntu-24.04`.

```yaml
jobs:
  zizmor:
    uses: iainchesworthlabs/icl-common-infra/.github/workflows/zizmor.yml@<sha>  # v0.1.N
    with:
      runner: ${{ (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository) && '["self-hosted","Linux","X64","shared"]' || '["ubuntu-24.04"]' }}
```

- **A pull request from a fork never runs on a self-hosted runner.** The fork's author chooses what the job runs (the
  docs requirements file, the scripts, the calling workflow itself) and a self-hosted runner outlives the job and sits
  inside the organisation's network. The expression above gives a fork the hosted default; a repository that has no hosted minutes
  skips the job for a fork instead (an `if:` on the calling job). Pull requests from the repository itself, Dependabot's
  included, and pushes, merge groups and schedules may use the fleet. The `decide-runner` action applies the same
  rule when it picks a runner.
- **A repository that must use its own runners passes `runner` in every call**, the closed-pull-request removal of a
  preview included. A job left on the default asks for a hosted runner, and when the hosted minutes are used up it does
  not start.
- **The label list is a conjunction**: the runner must carry every label in the array.
- **A self-hosted image needs the tools a workflow does not install itself.** Hosted images carry `git`, `bash`, `curl`
  and `jq`, the GitHub CLI (`gh`) and the AWS CLI, and the workflows use them without installing them: `gh` in
  `docs-deploy-aws.yml` (the preview comment) and `dependabot-auto-merge.yml`, `jq` in `dependabot-auto-merge.yml`, `aws` (version 2) in
  `docs-deploy-aws.yml`. What the workflows install themselves is Python 3.12 with `actions/setup-python` (`docs.yml`
  and `zizmor.yml`) and then the pip packages of the docs requirements or of zizmor. That needs an operating system and
  architecture for which `actions/setup-python` publishes builds, a writable tool cache and a route to the Python and pip
  indexes. The actions that run on Node need nothing beyond the runner application.
- **The secrets and the identity go to the runner too.** `docs-deploy-aws.yml` asks for an OIDC token to assume the
  deploy role and `dependabot-auto-merge.yml` reads `MERGE_QUEUE_TOKEN`; send them only to runners that may hold them.

## CodeQL permissions

The `analyze` job of `codeql.yml` asks for four permissions, and the workflow's own top-level block is empty:

| Permission | What needs it |
|---|---|
| `security-events: write` | `github/codeql-action/analyze` uploads the results to code scanning. |
| `contents: read` | The checkout; a private repository has no anonymous read. |
| `actions: read` | The CodeQL action asks the API for this workflow run (`GET /repos/{owner}/{repo}/actions/runs/{run_id}`) to name the analysis. A private repository refuses the call with "Resource not accessible by integration" when the token lacks it. |
| `issues: write` | The `report-nightly-failure` step opens or updates the `nightly-analysis` issue. |

A called workflow cannot have more than its caller grants: its token is the calling job's, narrowed by the `permissions:`
of the called job. **The calling job must therefore grant the same four.** A caller that grants fewer does not run the
analysis: GitHub rejects the run at startup and names the nested job and the permission. A caller that grants more gains
nothing, because the job's own block narrows it back, so grant exactly these. Write the block on the calling job, with
an empty `permissions: {}` at the top of the calling workflow, rather than depend on the repository's default token
permissions, which differ between repositories.

```yaml
name: CodeQL
on:
  schedule: [{ cron: "17 3 * * *" }]
  workflow_dispatch:
permissions: {}
jobs:
  codeql:
    permissions:
      security-events: write
      contents: read
      actions: read
      issues: write
    uses: iainchesworthlabs/icl-common-infra/.github/workflows/codeql.yml@<sha>  # v0.1.N
    with:
      languages: '[{"language":"cpp","build_mode":"manual","preset":"<preset>","vcpkg":true}]'
```

The same four go on the job whether the run comes from the schedule or from `workflow_dispatch`; a manual run uses the
same token as a scheduled one. A caller that routes the job to its own runners passes `runner` as well (see Runners).

## Docs on AWS

`docs-deploy-aws.yml` is the sibling of `docs-deploy.yml` for a site served from a private S3 bucket behind CloudFront
(for example `https://iainchesworthlabs.com/field-test/`). It holds no repository-specific logic and no stored AWS keys:
the job assumes an IAM role by OIDC with `aws-actions/configure-aws-credentials`, so the caller grants `id-token: write`.
One production role per app, limited to its own prefix, and one preview role limited to `_preview/<prefix>/*`, both
trusted for that repository only (the role's trust policy is the real barrier; the checks in the workflow are a second
one).

The role ARNs, the bucket name and the distribution ID are `secrets:` of the workflow (`DOCS_ROLE_ARN`,
`DOCS_PREVIEW_ROLE_ARN`, `DOCS_BUCKET`, `DOCS_DISTRIBUTION_ID`), set as secrets on the calling repository. They are not
credentials, but this repository is public and GitHub prints a step's `with:` and `env:` in the log before a
`::add-mask::` command could hide them, so only a secret keeps the account ID in an ARN, the bucket and the distribution
out of public logs. The `aws` commands run with `--no-cli-pager` and quiet output, and the preview comment holds only
the public URL. A pull request from a fork or from Dependabot gets no secrets: the job then skips with a notice or a
warning rather than failing, and so does a run where a secret is not set.

| Mode | When | What it does |
|---|---|---|
| `deploy` | push to `main` (`production-ref`) | `aws s3 sync --delete` to `s3://<bucket>/<prefix>/`, then invalidates `/<prefix>/*`. Any other ref fails. |
| `deploy` with `preview: true` and `pr-number` | pull request from this repository | Same, to `_preview/<prefix>/pr-<n>/`, then comments `<site-url>/_preview/<prefix>/pr-<n>/` on the pull request (one comment, updated on each push). Uses `DOCS_PREVIEW_ROLE_ARN`. A pull request from a fork is skipped. |
| `remove-preview` | pull request closed | Deletes `_preview/<prefix>/pr-<n>/`, invalidates it, and marks the comment removed. A fork is skipped. |

The artifact is the built site as it is (not the Pages tarball): build with `docs.yml` and `site-artifact: docs-site`.
Its top level must hold `index.html`. Inputs and secrets reach the shell only through environment variables, and
`prefix` must be a lower-case slug. `region` defaults to `ap-southeast-2` (Sydney), `site-url` to `https://iainchesworthlabs.com`. Previews are public to
anyone with the link; combine them with an S3 lifecycle rule and `noindex` on `_preview/` (see the site stack).

A caller, with the four secrets set on the repository (a preview and a removal use `DOCS_PREVIEW_ROLE_ARN`, a production
deploy uses `DOCS_ROLE_ARN`):

```yaml
on:
  push: { branches: [main] }
  pull_request: { types: [opened, synchronize, reopened, closed] }
permissions: {}
jobs:
  build:
    if: github.event.action != 'closed'
    permissions: { contents: read }
    uses: iainchesworthlabs/icl-common-infra/.github/workflows/docs.yml@<sha>  # v0.1.N
    with: { site-artifact: docs-site }
  deploy:
    needs: build
    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name == github.repository
    permissions: { contents: read, id-token: write, pull-requests: write }
    uses: iainchesworthlabs/icl-common-infra/.github/workflows/docs-deploy-aws.yml@<sha>  # v0.1.N
    with:
      prefix: field-test
      preview: ${{ github.event_name == 'pull_request' }}
      pr-number: ${{ github.event.pull_request.number }}
    secrets:
      DOCS_ROLE_ARN: ${{ secrets.DOCS_ROLE_ARN }}
      DOCS_PREVIEW_ROLE_ARN: ${{ secrets.DOCS_PREVIEW_ROLE_ARN }}
      DOCS_BUCKET: ${{ secrets.DOCS_BUCKET }}
      DOCS_DISTRIBUTION_ID: ${{ secrets.DOCS_DISTRIBUTION_ID }}
  remove-preview:
    if: github.event.action == 'closed'
    permissions: { contents: read, id-token: write, pull-requests: write }
    uses: iainchesworthlabs/icl-common-infra/.github/workflows/docs-deploy-aws.yml@<sha>  # v0.1.N
    with:
      mode: remove-preview
      prefix: field-test
      pr-number: ${{ github.event.pull_request.number }}
    secrets:
      DOCS_ROLE_ARN: ${{ secrets.DOCS_ROLE_ARN }}
      DOCS_PREVIEW_ROLE_ARN: ${{ secrets.DOCS_PREVIEW_ROLE_ARN }}
      DOCS_BUCKET: ${{ secrets.DOCS_BUCKET }}
      DOCS_DISTRIBUTION_ID: ${{ secrets.DOCS_DISTRIBUTION_ID }}
```

On a push to `main`, `github.event.pull_request.number` is empty and `preview` is false, so it is ignored.

## Planner and aggregator

Reuse of earlier results (`docs/ci-many-agents.md`) is made of these pieces, used in this order by a consumer:
`plan_gate.py --groups` and the `groups` and `reuse` sections of `plan.json`; `record-proof` in `CI Status`; a `reuse`
job with `find-proof` in `CI_REUSE_MODE=shadow`, then `on`; `ci-status` with `reused`; and on `push` `report-red` then
`mark-green`. Start in shadow mode and move to `on` only when the shadow summaries agree with what ran.

`scripts/plan_gate.py` reads the changed paths and prints `build`, `gui`, `docs_only`,
`machinery`. The caller runs it in a `plan` job and uses the outputs as job conditions.
The `ci-status` action takes `toJSON(needs)` and a map of job id to "the plan asked for it"
and fails when a job failed, was cancelled, or was skipped although the plan asked for it, or when a job the plan asked for is missing from `needs` (GitHub leaves out a job that never got a runner).
Configure the planner with `.github/ci/plan.json` in the consumer.

`plan_gate.py --groups` adds two lines, `groups` and `promoted` (JSON lists), computed from the `groups`
table of `plan.json`: each group has a `home` stage, `skips` (globs the group does not read, besides
documentation and `no_build`), `promote` (globs that pull a post-merge group into the queue) and `jobs`
(the job names that must all succeed for the group to count as proved). The default is to run: a group is
left out only when every path is documentation, a `no_build` path or one of its `skips`. The `reuse` section
sets `barrier` (paths that define how results are produced; the workflows, actions, `.github/ci` and the
toolchain pins are always in it) and `max_age_hours` (default 48). Both are inert until the proof steps of
`docs/ci-many-agents.md` use them.

`actions/record-proof` (in the `CI Status` job) uploads the `ci-proof` artifact of a run, and `actions/find-proof`
(a `reuse` job after `plan`, with `contents: read`, `actions: read`, `pull-requests: read`) decides which groups an
earlier run already proved. Set the repository variable `CI_REUSE_MODE` to `shadow` first: the job computes and
reports in the job summary what it would reuse, and `reused` stays empty so every group still runs. `on` makes
`reused` real; `off` skips the lookup. The job never fails: on an error the `mode` output is `fallback`. Reuse needs
the `groups` and `reuse` sections of `plan.json`, and is refused for fork pull requests, for runs of another
workflow file, for proofs older than `reuse.max_age_hours`, and whenever a barrier path differs.

After a merge, `actions/report-red` (job needs `issues: write`, `pull-requests: write`, `actions: read`) opens one
`main-red: <group>` issue per failed group that names the pull requests merged since the group's last green commit
and comments once on each; the issue closes when the group next passes. `actions/mark-green` (job needs
`contents: write`; make it `needs` the report job) then moves `refs/ci/green/<group>` forward for every group that
passed. Neither reverts or blocks anything, and neither fails its job.

`coverage_gate.py --floors-glob 'libs/*/coverage-floor.json' --floors-glob 'apps/*/coverage-floor.json'` reads one
floor file per component (`{"line": 90, "branch": 85}`, keys left out take the default) beside the component's
`CMakeLists.txt`, so a new library adds a file instead of a line to `tools/coverage-floors.json`, which keeps `default`.
A component named in both places fails the gate. `--write-floors` writes a component's ratchet to its own file.

`templates/ci-metrics.yml` is a weekly job that runs `scripts/ci_metrics.py` and writes the numbers of
`docs/ci-many-agents.md` section 8.2 to its job summary (`actions: read`, no other write). Copy it to
`.github/workflows/ci-metrics.yml` and replace the placeholder pin with the commit of the tag you use. Reuse rate and
false reuse are read from the `Reuse` summaries of the runs; the API does not expose them as data.

Hosted runner images carry CMake 3.x, so every job that configures a project installs CMake with
`actions/setup-cmake` (version from the `cmake` key of `.github/toolchain-versions.json`, else any 4.x) after
the checkout and after `setup-msvc-env`. The reusable workflows do this themselves.

Scripts run by a caller job (the planner, the coverage gate) come from the same commit as the
workflow: call `actions/checkout-infra` after the caller's own checkout and use `.icl-infra/scripts/...`.
The commit is read from the `uses:` line, so a bump of that line moves the scripts too.

Pin the newest tag (`gh api repos/iainchesworthlabs/icl-common-infra/tags --jq '.[0].name'`), and move to each new one when
it is cut. In a project, `tools/ci/repin.py` moves every `uses:` line and `cmake/icl` to a tag in one change, which is the
pull request to open; section 12.3 of the standard says why it is not a commit on Dependabot's branch.

## Compilers

The floor is GCC 16, Clang 23 and MSVC 14.51 (14.52 when the runners carry it), with the newest Apple Clang
the macOS runners offer. The versions are pins in `.github/toolchain-versions.json`:

| Key | Used by | Meaning |
|---|---|---|
| `gcc` | `actions/setup-gcc` | GCC major version, installed on Ubuntu (26.04 has it in `universe`) |
| `llvm` | `actions/setup-llvm` | LLVM major version, from the Ubuntu archive or apt.llvm.org |
| `msvc_toolset` | `actions/setup-msvc-env` | lowest acceptable toolset; a newer one passes |

A `build.yml` leg sets `"compiler": "gcc"` or `"compiler": "clang"` (which also installs GCC for its libstdc++);
the leg's runner is `ubuntu-26.04`. A leg with `"experimental": true` reports but cannot fail the run, for a
preview toolchain such as the `xcode-27` runner. Apple Clang comes with the runner image; choose the label.

**Package cache.** `setup-gcc` and `setup-llvm` keep the `.deb` files of a clean install in an Actions cache (`apt-debs-<os>-<arch>-<tool>-<version>-<image version>`) and install from it with no `apt-get update` and no mirror, so an outage of apt.llvm.org or an Ubuntu mirror stops failing runs once the cache exists. Only a push to the default branch, a manual run or a schedule saves it. When the cache is empty or does not install, the scripts use the network: four attempts with waits of 20, 60 and 120 seconds plus jitter, on the runner image's own mirror for the index. `setup-gcc` downloads the packages itself before apt installs them: four at a time with `curl`, resuming a part file, dropping a transfer that runs under 200 kB/s for 10 seconds and trying the mirrors in the image's own list, azure.archive.ubuntu.com, archive.ubuntu.com and us.archive.ubuntu.com in turn, because one mirror node stalled the 95 MB `gcc-16-x86-64-linux-gnu` on every apt attempt (10 and 11 November 2026). `setup-ccache` no longer fails when another apt source is down.

## Qt

`actions/setup-qt` installs the Qt kit named by the `qt` key of `.github/toolchain-versions.json` (and, on Windows,
the `aqtsource` key). It does nothing when the key is empty, so a hand-written job can carry the step in a
project without Qt. `build.yml` installs Qt for a leg with `"qt": true`.

## CMake modules

A target that Qt generates sources for (moc, rcc, qmlcachegen) calls `icl_relax_generated_warnings(<target>)`
from `IclWarnings` so the generated files are compiled without the strict warning set.

Add `cmake/` of this repository to `CMAKE_MODULE_PATH` (the template vendors a pinned copy under
`cmake/icl/` with a script that updates it) and include what you need:

```cmake
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/cmake/icl")
include(IclVcpkgRoot)
icl_resolve_vcpkg("${CMAKE_SOURCE_DIR}" MYPROJECT)   # before project()
project(myproject LANGUAGES CXX)
set(ICL_PROJECT_PREFIX MYPROJECT)
find_package(Qt6 REQUIRED COMPONENTS Quick)          # FindQt6.cmake honours MYPROJECT_QT_ROOT / ICL_QT_ROOT
include(IclWarnings)    # icl::warnings
include(IclHardening)   # icl::hardening
include(IclSanitizers)  # ICL_SANITIZERS=address,undefined | thread
include(IclTracy)       # icl::tracy, ICL_ENABLE_TRACY
include(IclCoverage)    # icl::coverage, ICL_ENABLE_COVERAGE
include(IclPlatform)    # icl_platform_sources(<target>) picks src/platform/<os>/
```

Sanitizers, Tracy, coverage and fuzzing are mutually exclusive; the configure stops with a
message when two are on.

### Packaging a Qt application

`icl_install_qt_app(<target> BUNDLE_IDENTIFIER <id> [DISPLAY_NAME <name>] [NOTICE_EXCLUDE <pkg>...])` from `IclQtApp`
is the whole install step for a Qt application. Call it from the application's directory after `qt_add_executable`
and `qt_add_qml_module`, with `project(... VERSION ... HOMEPAGE_URL ...)` set:

```cmake
set_target_properties(snake_app PROPERTIES OUTPUT_NAME snake)
icl_install_qt_app(snake_app
    BUNDLE_IDENTIFIER io.github.owner.snake
    DISPLAY_NAME Snake
    NOTICE_EXCLUDE catch2)          # in vcpkg.json, but not shipped
```

It sets the macOS bundle properties (the identifier, the name, and the version from `PROJECT_VERSION`), installs the
program, runs Qt's deploy step so the install tree runs without Qt, and removes the QML debugging plugins
(`qmltooling`) from it. It also installs, to `share/doc/<name>` and into `<name>.app/Contents/Resources/doc` on macOS:

- `LICENSE` and the `LICENSES/` directory when there is one;
- `THIRD-PARTY-NOTICES.txt`, made at configure time from the licence file vcpkg installed for each runtime
  dependency in `vcpkg.json` (host tools and `NOTICE_EXCLUDE` packages are left out), plus an entry for Qt. A
  dependency with no licence file stops the configure, which is the check that the notices cover every dependency;
- `SOURCE.txt`, written when the package is installed, with the commit from git (or `GITHUB_SHA`) and the link to
  Qt's source.

`IclNotices` has the two pieces on their own (`icl_generate_notices`, `icl_write_source_info`) for a project that is
not a Qt application. Qt's own third-party components are credited by a link to Qt's list, not copied in.

## Release options

The defaults suit a project that builds only packages. A project that makes more can set:

- `generate-sbom: false` when the packages already include the project's own SBOM files; the workflow then adds none.
- `public-key` (default `docs/signing-key.asc`): every signature must verify against this committed key, or the
  release stops before it is created.
- `verify-script`: a script in the repository, run as `script <directory> <public-key>` on the signed and attested
  files, for checks only the project can make (for example its attestation or package layout rules). It is tried up
  to four times, because a new attestation can take a moment to be readable.
- `draft: true` creates the release as a draft for the owner to read and publish; `title` replaces the tag as its title.

## Platform steps of a project's own `release.yml`

The project's `release.yml` builds each package and applies the platform's signing; these actions are the shared pieces.
Each is pinned by commit, like the others.

| Action | Runner | What it does |
|---|---|---|
| `sign-windows` | Windows | Authenticode signing behind `SIGN_WINDOWS` (`false`, `test`, `production`) |
| `check-glibc-floor` | Linux | Fails the package job when a program or library in the package needs a glibc newer than 2.39 (`allowed` changes it). Call it on the folder that becomes the package. |
| `import-ios-signing` | macOS | The Apple Distribution certificate and the provisioning profile into a temporary keychain, and the profile checked |
| `export-ios-ipa` | macOS | `xcodebuild archive` and export, ad hoc or App Store |
| `upload-testflight` | macOS | Apple's validation of the IPA and the upload to TestFlight |

`docs/ios-signing.md` is the guide to the three iOS actions: the Apple portal, the secrets, a worked job and the
lessons of the first project to use them. The standard's 7.7 lists what a phone version needs of the project itself.

## Release notes

A release always has notes from the changelog; there is no placeholder. `release-publish.yml` runs
`actions/release-notes` in `verify` (before the approval wait) and again when it creates the release.

- A final release (`v1.2.0`) needs a `## [1.2.0]` section in `CHANGELOG.md`. Make it with a pull request that runs
  `changelog_tool.py assemble --version 1.2.0 --date YYYY-MM-DD`, then tag the merge commit. The run fails without it.
- A pre-release (`v1.2.0-rc.1`) uses that section when it exists. Otherwise its notes are the fragments still in
  `changelog.d/`, left in place, so the final release lists every change since the previous final release.
- `changelog_tool.py notes --version 1.2.0 --allow-pending` prints the same text locally.

### A project with its own SBOMs or notes

Three optional inputs let a project that makes more than the shared workflow does keep that work in its own scripts:

- `pre-release-script` runs as `bash script <dist> <version> <tag>` after the packages are downloaded and before the
  checksums. It may add files to `<dist>`, such as the project's SBOMs and its public key; they are summed, signed and
  published with the packages.
- `spdx-sbom` and `cyclonedx-sbom` name SBOM files (in `<dist>`) that the script wrote. Each is attested as an SBOM for
  every package, and the workflow then reads every attestation back and fails unless the document the attestation
  holds is the file that is published. Without them the workflow only generates its own `sbom.spdx.json`.
- `notes-script` runs as `bash script <dist> <output-file> <version> <tag> true` after signing, attestation and
  verification, and writes the notes. It replaces `actions/release-notes` in `verify` and in `publish`, so the
  changelog check is the script's to make, and it must fail when it has nothing to write.

## Extra branch prefixes

The branch-name check and the `branch-names` ruleset allow `feature/`, `bugfix/`, `docs/`, `chore/` and `agent/`. A
project with a working practice of its own (cubeulator's `spike/` branches) lists the extra prefixes, one lower-case word
per line, in `.github/branch-prefixes.txt`. `scripts/check_branch_name.py` reads the file when it checks a name, and
`admin/apply.sh` reads the same file when it builds the `branch-names` ruleset, adding the three exclude patterns each
built-in prefix has. A prefix the standard already uses, or a line that is not a lower-case word, is an error.

## Commit and pull request text

The text check follows git: a final paragraph made only of `Word: value` lines is read as trailers, and only
`Signed-off-by` is allowed. The rule applies to pull request bodies as well, because the squash merge uses the body as
the commit message. A `Word: value` line anywhere else is fine. To end a body with such a line, put a sentence after it.

## Local checks

```bash
python3 path/to/icl-common-infra/scripts/precheck.py            # against origin/develop
python3 path/to/icl-common-infra/scripts/precheck.py --base main
```

The template's `tools/ci/precheck.py` finds a sibling checkout in `../icl-common-infra` or
the directory named by `ICL_COMMON_INFRA`.

## Platform isolation

A project that keeps the code for each operating system in a directory of its own (`src/app/platform/<name>/`, with a
`platform.cmake` per platform) can have the shared check hold that line: `scripts/check_platform_isolation.py` fails on an
OS header or an OS query (`QSysInfo`, `Q_OS_*`, `Qt.platform`) outside the platform section, on a platform source file that
no `platform.cmake` names, and on a test of the OS in CMake outside the selector and the fragments. The preprocessor rule
is `check_no_preprocessor.py`'s.

The check runs in `policy-checks` and in `precheck.py` when the project has `tools/platform-isolation.json`. The file may
be `{}`: every key is optional, and the defaults are the layout of `cubeulator` (`platform_dir`, `section_prefixes`,
`scan_roots`, `root_files`, `skip_prefixes`, `cmake_exempt`, `not_platforms`, `wired_relative_to`, `interfaces_hint`; the
docstring of the script lists them). It replaces `cubeulator`'s PowerShell script of the same rules.

## The nightly summary

`actions/nightly-report` is the summary of a nightly workflow that runs several things: a table in the job summary, and one
standing issue (label `nightly`) that is opened or commented on when a job that gates is red and closed once a night is
green again. It reads `needs` for the nightly's own jobs and, with `ci-run-id`, the jobs of a CI run the nightly dispatched,
including the "success" job that carries a failure annotation because a step in it is `continue-on-error` (listed as a hidden
failure). Which jobs gate is the caller's: `gating-jobs` and `informational-jobs` name the nightly's own, and
`informational-ci` is a regular expression for the CI jobs whose red is informational (a wall-time budget on a shared
runner, a job that is new and has never run). The calling job runs with `if: always()` after the jobs it reports on and
needs `issues: write`, `actions: read` and `checks: read`. `dry-run: "true"` writes the summary and touches no issue. For one
analysis engine's failure, use `report-nightly-failure`.

## Actions cache hygiene

A repository's Actions cache is 10 GB, and GitHub evicts the least recently used entries past that without regard for
which took an hour to build. The `actions/prune-actions-cache` composite action keeps the quota for entries something can
still restore: it deletes those of a ref that no longer exists (a deleted branch, a closed pull request, a deleted tag),
and the older generations of a cache that is saved under a new key whenever its content changes (vcpkg binaries, ccache,
the Qt kit), keeping the newest of each family per ref. `purge` deletes every entry whose key starts with a prefix, the
reset for a vcpkg cache that has carried stale archives too long. `dry-run: "true"` only lists.

The triggers are the caller's, in a workflow of its own with `permissions: actions: write` on the job: `pull_request`
with `types: [synchronize, closed]` (not for a fork's pull request, whose token cannot delete), a push to the default
branch, `workflow_run` after the CI workflow finished saving its caches, and `workflow_dispatch` for a dry run and a
purge. The rules and the key shapes are in the header of `scripts/prune_actions_cache.sh`, which can also be run by hand
(`gh` with `actions: write`, and `jq`).

### Who writes the caches

`setup-vcpkg` and `setup-ccache` take a `cache-write` input, `auto` by default. With `auto`, only a push, scheduled or
manual run of the default branch saves the vcpkg binaries, downloads and tool, and the ccache. A pull request,
merge-queue entry or tag run restores the default branch's entries and saves nothing. An entry is readable from its own
ref and the default branch, so a merge-queue ref's entry can never be read again, and a pull request's helps only that
pull request. In error-journaling, those two kinds were 7 of the 10.7 GB in use on 9 November 2026. `build.yml` saves
the ccache only when `CCACHE_SAVE` is `true`. A caller that saves the ccache itself checks the same variable.
`save-vcpkg-cache` reads `VCPKG_CACHE_WRITE`. Pass `cache-write: "true"` for a job that must write on another ref.

### The vcpkg tool and the bootstrap

`bootstrap-vcpkg` downloads the vcpkg tool binary from GitHub's release CDN. Its own curl retries are one to four
seconds apart, and that download was the step that failed with HTTP 504 across the merge queue on 9 November 2026.
`setup-vcpkg` now caches the binary under `vcpkg-tool-<OS>-<ARCH>-<release tag>-<hash of vcpkg-tool-metadata.txt>`, a
few megabytes per platform. It bootstraps only when the cache has no copy or the cached copy does not run. The bootstrap,
the clone of the fork and its fetch run through `scripts/retry.sh`: 5 attempts, waiting 20, 40, 80 and 160 seconds.

Port sources and the tools vcpkg fetches itself (CMake, Ninja, 7-Zip) land in `VCPKG_DOWNLOADS`, which is the
`vcpkg-downloads-…` cache. vcpkg looks there by file name and SHA-512 before it goes upstream, so that directory is the
asset cache and `X_VCPKG_ASSET_SOURCES` is not set. On a binary-cache hit vcpkg downloads no sources at all.

## Tests in phases

`actions/run-ctest` runs CTest in phases, re-runs the tests that failed once, by name, and reports a test that failed and
then passed as a flaky pass (a warning, not a failure). A test that fails twice fails the run. The default phases suit a
project whose labels are `unit`, `integration`, `system`, `ui` and `perf`. A project with other labels gives its own
`phases-file` (JSON): each phase has a `name`, a `label` (a regular expression for `ctest -L`, or empty), `jobs` (0 for
all cores) and optionally `optional` (a phase that matches nothing is not an error), `exclude` (a regular expression for
`ctest -LE`, for a project that names what to leave out because it does not control its labels, such as Catch2 tags
promoted to labels) and `args` (further ctest arguments). The Qt Quick suites belong in a phase of their own at `jobs: 2`.

## Repository administration

```bash
admin/apply.sh --repo iainchesworthlabs/<name>                 # dry run: prints the calls
RELEASE_BOT_APP_ID=<id> OWNER_USER=iainchesworth admin/apply.sh --repo iainchesworthlabs/<name> --apply
```

The script reads `.github/repo-settings.json`, `.github/labels.json` and `.github/rulesets/`
of the current directory when present, otherwise the defaults in `admin/`. It needs an
admin-scoped token that the owner supplies when running it.
