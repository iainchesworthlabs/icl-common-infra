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
| `release-publish.yml` | Tag checks, release notes check, SHA-512 sums, GPG signatures checked against the committed public key, SBOM, attestations, optional project verification, GitHub Release, fast-forward of `main`. | `artifact-pattern`, `generate-sbom`, `public-key`, `verify-script`, `draft`, `title` |
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

## Release notes

A release always has notes from the changelog; there is no placeholder. `release-publish.yml` runs
`actions/release-notes` in `verify` (before the approval wait) and again when it creates the release.

- A final release (`v1.2.0`) needs a `## [1.2.0]` section in `CHANGELOG.md`. Make it with a pull request that runs
  `changelog_tool.py assemble --version 1.2.0 --date YYYY-MM-DD`, then tag the merge commit. The run fails without it.
- A pre-release (`v1.2.0-rc.1`) uses that section when it exists. Otherwise its notes are the fragments still in
  `changelog.d/`, left in place, so the final release lists every change since the previous final release.
- `changelog_tool.py notes --version 1.2.0 --allow-pending` prints the same text locally.

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

## Repository administration

```bash
admin/apply.sh --repo iainchesworthlabs/<name>                 # dry run: prints the calls
RELEASE_BOT_APP_ID=<id> OWNER_USER=iainchesworth admin/apply.sh --repo iainchesworthlabs/<name> --apply
```

The script reads `.github/repo-settings.json`, `.github/labels.json` and `.github/rulesets/`
of the current directory when present, otherwise the defaults in `admin/`. It needs an
admin-scoped token that the owner supplies when running it.
