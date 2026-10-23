# Using icl-common-infra

## Workflows

All are `workflow_call`. Required status checks must be jobs defined in the caller, because
a check from a called workflow is named `<caller job> / <called job>`. The caller therefore
defines two jobs by name: `CI Status` (using the `ci-status` action) and
`Scan dependency diff` (using the `dependency-review` action).

| Workflow | Purpose | Main inputs |
|---|---|---|
| `policy.yml` | Branch name, commit and PR text, preprocessor policy, action pinning, changelog fragment, vcpkg baseline in fork, REUSE. Runs on drafts. | `base-ref`, `runner`, `skip-changelog` |
| `build.yml` | Build and test a list of legs with CMake presets. | `legs` (JSON, see the file header), `timeout-minutes` |
| `codeql.yml` | Nightly code scanning; opens a `nightly-analysis` issue on failure. | `languages` (JSON) |
| `docs.yml` | `mkdocs build --strict`; uploads the Pages artifact when `upload: true`. | `requirements`, `upload` |
| `docs-deploy.yml` | Publishes the Pages artifact from the same run. Needs `pages: write` and `id-token: write` on the calling job. | none |
| `release-publish.yml` | Tag checks, SHA-512 sums, GPG signatures, SBOM, attestations, GitHub Release, fast-forward of `main`. | `artifact-pattern` |
| `zizmor.yml` | Workflow static analysis. | `min-severity` |
| `dependabot-auto-merge.yml` | Enable auto-merge for non-major Actions and tooling updates. | secret `MERGE_QUEUE_TOKEN` |

## Planner and aggregator

`scripts/plan_gate.py` reads the changed paths and prints `build`, `gui`, `docs_only`,
`machinery`. The caller runs it in a `plan` job and uses the outputs as job conditions.
The `ci-status` action takes `toJSON(needs)` and a map of job id to "the plan asked for it"
and fails when a job failed, was cancelled, or was skipped although the plan asked for it.
Configure the planner with `.github/ci/plan.json` in the consumer.

Hosted runner images carry CMake 3.x, so every job that configures a project installs CMake with
`actions/setup-cmake` (version from the `cmake` key of `.github/toolchain-versions.json`, else any 4.x) after
the checkout and after `setup-msvc-env`. The reusable workflows do this themselves.

Scripts run by a caller job (the planner, the coverage gate) come from the same commit as the
workflow: call `actions/checkout-infra` after the caller's own checkout and use `.icl-infra/scripts/...`.
The commit is read from the `uses:` line, so Dependabot's bump of that line moves the scripts too.

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

## Local checks

```bash
python3 path/to/icl-common-infra/scripts/precheck.py            # against origin/develop
python3 path/to/icl-common-infra/scripts/precheck.py --base main
```

The template's `tools/ci/precheck.py` finds a sibling checkout in `../icl-common-infra` or
the directory named by `ICL_COMMON_INFRA`.

## Repository administration

```bash
admin/apply.sh --repo iainchesworthlabs/<name>                 # dry run: prints the calls
RELEASE_BOT_APP_ID=<id> OWNER_USER=iainchesworth admin/apply.sh --repo iainchesworthlabs/<name> --apply
```

The script reads `.github/repo-settings.json`, `.github/labels.json` and `.github/rulesets/`
of the current directory when present, otherwise the defaults in `admin/`. It needs an
admin-scoped token that the owner supplies when running it.
