# icl-common-infra

Shared build and CI infrastructure for the Iain Chesworth Labs C++23 projects: reusable
workflows, composite actions, CMake modules, check scripts, and repository administration
as code. Projects start from [`icl-cpp-template`](https://github.com/iainchesworthlabs/icl-cpp-template)
and call this repository by commit SHA.

## Contents

| Path | What it holds |
|---|---|
| `.github/workflows/` | Reusable workflows (`workflow_call`): `policy`, `build`, `codeql`, `docs`, `release-publish`, `zizmor`, `dependabot-auto-merge`. This repository's own CI is `ci.yml`, and `self-dependabot-auto-merge.yml` calls the reusable auto-merge workflow for its Dependabot pull requests. |
| `actions/` | Composite actions: `setup-vcpkg`, `save-vcpkg-cache`, `setup-qt`, `setup-ccache`, `setup-msvc-env`, `setup-emscripten`, `decide-runner`, `policy-checks`, `run-ctest`, `ci-status`, `dependency-review`, `report-nightly-failure`, `sign-windows`, `import-ios-signing`, `export-ios-ipa`, `release-notes`. |
| `cmake/` | `IclVcpkgRoot`, `FindQt6`, `IclWarnings`, `IclSanitizers`, `IclHardening`, `IclTracy`, `IclCoverage`, `IclPlatform`, `IclQtApp`, `IclNotices`. |
| `scripts/` | Checks and tools run by the actions: preprocessor policy, commit and PR text policy, action pinning, changelog fragments, planner, pre-push check, ctest phases, coverage gate, changelog assembly. Unit tests are in `scripts/tests/`. |
| `admin/` | `apply.sh` and the default rulesets, labels and repository settings. |
| `tools/test-signing/` | Script that issues a Windows test-signing leaf certificate from a personal CA. |
| `templates/` | Files that belong in other repositories (the vcpkg fork's sync workflow). |
| `docs/` | How to consume this repository, the owner runbook, test signing, and `standard.md`, the C++23 project standard that projects are built to. |

## Using it

A consumer pins this repository by full commit SHA, and Dependabot (`github-actions`
ecosystem) keeps the SHA current:

```yaml
jobs:
  policy:
    uses: iainchesworthlabs/icl-common-infra/.github/workflows/policy.yml@<sha> # v1.0.0
```

Inside this repository, workflows call their sibling actions with the `$/` syntax, which
resolves to the same commit as the workflow that is running. One SHA therefore pins a
workflow, its actions, and the scripts they run. `$/` needs runner 2.336.0 or newer and is
available on github.com only.

See `docs/using.md` for the full list of inputs and the CMake modules, and
`docs/secrets.md` for the secrets and variables the workflows read.

## Versioning

Tags `vMAJOR.MINOR.PATCH`. A change to an input or a required check name is a major version.
Consumers reference a SHA, with the tag in a trailing comment.

## Licence

GPL-3.0-or-later. REUSE metadata is in `REUSE.toml`.
