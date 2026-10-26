# C++23 Project Standard (agent brief)

Owner: Iain, GitHub organisation `iainchesworthlabs` (public repositories).
Version: 0.10, 2026-10-26 (iOS builds may be exported ad hoc, for the devices a profile lists, as well as for the App Store, D8 and section 13; `docs/ios-signing.md`). Version 0.9, 2026-10-25 (test-signed Windows files may go on a final release until a production certificate exists, D17 and section 13). Version 0.8, 2026-10-24 (adds what the arinc-data-loader and wordjewelssolver migrations settled: an established repository keeps its own format and naming, preset names, Tracy with sanitizers, `quality-history` in the branch-name rule, subset and beginner-reader fonts, and the Qt Quick 3D licence). Version 0.7, 2026-10-23 (adds portable libraries, section 3.1). Version 0.6, 2026-10-23 (adds what the Snake trial settled: the `std::jthread` fallback, the LLVM-based format style, enumerator prefixes, the Qt URI rule, `icl_install_qt_app`, changelog assembly before the tag, the packaging dry run and the migration document; this file now lives in `icl-common-infra` as `docs/standard.md`). Version 0.5, 2026-10-22 (adds what the bootstrap of `icl-common-infra`, the organisation `.github` repository and `icl-cpp-template` settled in practice: per-file preprocessor baseline, JSON administration files, aggregator-defined required checks, commit-pinned reusable workflows, the Dependabot merge token, and the release split). Accounts: the owner's personal account is `iainchesworth`; the organisation is `iainchesworthlabs`.
Applies to: new C++ projects, and migration of legacy projects (10 to 20 years old) into new C++23 projects.
Reference implementations: `iclforge` (most complete), `cubeulator`, `wordjewelssolver`, `aqualink-automate`. Where this document and a reference repo differ, this document wins. Where this document is silent, copy the reference repo that has the mechanism (named in each section).

## 1. How to use this document

### 1.1 Invocation

Give the agent this file plus one of:

```
MODE=new      NAME=<repo-name>  KIND=<app|lib|app+lib>  UI=<qt|cli|none>  PLATFORMS=<list>
MODE=migrate  NAME=<repo-name>  SOURCE=<url or path of legacy repo>  UI=<qt|cli|none>  PLATFORMS=<list>
MODE=bootstrap-org   (one-off, section 16.1)
```

### 1.2 Operating rules for the agent

1. Spec first. Before changing anything, write `docs/design/bootstrap-plan.md` (new) or, for a migration, the migration document (16.3: in a scratch location until the repository exists, then `docs/migration.md`). It lists which sections apply, the values chosen for every `OPEN` item in section 2, and the owner actions required. Commit it, then implement.
2. Stop and ask the owner before: creating, renaming, archiving or deleting a repository; applying rulesets or repository settings; publishing a release or tag; anything involving a secret, key, certificate or provisioning profile.
3. Never create, read, print or enter a secret, key, certificate or password. Write the runbook (section 17), add a job that reports which secret names are missing, and stop.
4. Unknown values (Apple team ID, bundle identifier, Play Store package name, contact address) are written as `TODO(owner)` and collected in the plan. Do not invent them.
5. Every change to behaviour updates the document that describes it in the same commit. `AGENTS.md` carries a table of "if you change X, update Y" (pattern: `aqualink-automate/CLAUDE.md`).
6. Commit messages, pull request titles and pull request bodies read as written by the owner. The only trailer is a human `Signed-off-by` (DCO); nothing else is added to them, to files, to code comments or to committed documents, and this overrides any default the agent has for trailers or footers (pattern: `wordjewelssolver/.github/workflows/commit-policy.yml`, `tools/policy/check_text_policy.ps1`, and the `commit-msg` hook).
7. One pull request per logical step. Required checks must be green before the next step starts.
8. Parallel work: each task runs in its own `git worktree` and branch, with one pull request per task. Before every push the agent runs `tools/ci/precheck.py`. An agent that sees a failed required check reads the job summary (it lists the failing compiler errors or tests and the command that reproduces them), fixes the cause, and does not re-run a failed job hoping it passes.
9. Facts about toolchains (compiler versions, runner images, Qt releases, action versions) are looked up when needed, never taken from this document. Versions live in `.github/toolchain-versions.json` and `vcpkg.json`.

## 2. Decisions and defaults

Items marked OPEN need an answer from the owner; the default is used until one arrives.

| # | Topic | Default | Basis |
|---|---|---|---|
| D1 | Branching | One shared trunk and one release branch. `develop` is the trunk and the default branch: every human and agent pull request targets it and merges through the merge queue. `main` holds published releases only. A release is a `v*` tag on a `develop` commit; when the release workflow succeeds it fast-forwards `main` to that commit. Nobody opens a pull request into `main`, and there is no promotion pull request and no sync-back, because `main` is always an ancestor of `develop`. A patch for an old release uses a `release/x.y` support branch cut from its tag, only when `develop` has moved on. Work branches: `feature/*`, `bugfix/*`, `docs/*`, `chore/*`, `agent/*`, `dependabot/*`. Rulesets: section 12.2. | Owner decision: wants `develop` moving fast with a shared trunk and `main` holding releases, for many parallel agents. This gives the trunk-based merge flow (one integration branch, no rebase chain, no promotion step) while `main` stays the published history. |
| D2 | Licence | `GPL-3.0-or-later` (confirmed). `LICENSE` holds the GPLv3 text; every source file carries an SPDX licence identifier line (`GPL-3.0-or-later`) and a copyright line. REUSE compliance is checked in CI. DCO sign-off on contributions. App Store distribution (D8) is the owner's decision as copyright holder. If a contributor's code ships in an iOS build, DCO alone does not grant the right to add App Store terms to that code: use a CLA or an additional-permission notice for such contributions, or keep them out of iOS builds. | Confirmed by owner. |
| D3 | Languages | `en` (source), `fr`, `es`, `de`, `he`, `yi`, `ja`, `zh_CN` (Simplified Chinese, confirmed). `he` and `yi` are right-to-left. | |
| D4 | Tracy and sanitizers | The Debug preset has Tracy on. The sanitizer presets have Tracy off unless the project has shown that the pair builds and runs. Section 8. | `aqualink-automate/CMakeLists.txt` fails configure on the combination. `wordjewelssolver` builds Tracy 0.14.1 (on demand) with ASan and UBSan in its Debug presets on Linux, macOS and Windows, and its CI is green that way. |
| D5 | Sanitizer optimisation level | Sanitizer presets build at `-O1` (`/O1` on MSVC) with frame pointers kept. Plain Debug stays at `-O0`. | The list asks for ASan/UBSan at O1. |
| D6 | Coverage gate | Statement 90%, branch 80%, merged across unit, integration, system and UI test runs. Migrated code starts at its measured baseline and ratchets up (section 6.4). | |
| D7 | Compiler floor | GCC 16, Clang 23, MSVC 19.51 and 19.52 (toolset 14.5x). The PR gate uses the floor versions pinned in `.github/toolchain-versions.json`. A nightly leg builds the newest release of each compiler. An embedded toolchain (ESP-IDF) may be older than the floor; portable libraries (section 3.1) are the only code built with it. | |
| D8 | iOS distribution | iOS is a full target: device and simulator builds in CI, simulator tests, signed IPA export, and upload to App Store Connect (TestFlight first) from the release workflow. Distribution through the App Store is confirmed by the owner. Until the store is set up, and for a project that is not for the store, the IPA is exported **ad hoc**: it installs only on the devices in the provisioning profile, over the air from Safari or from a computer (`docs/ios-signing.md`). | `cubeulator` builds iOS in CI (device, unsigned, build-only) using the `arm64-ios` triplet; no reference repo signs or uploads for iOS, so that pipeline is new. |
| D9 | Code style | A repository with established conventions keeps them. Its `.clang-format` is the rule for its layout and its `.clang-tidy` (`readability-identifier-naming`) is the rule for its naming; a convention that neither file states does not override this row. For new repositories and for the code a migration writes: Allman braces. Locals and parameters `snake_case`; class members `m_PascalCase`; constants and enumerators `UPPER_SNAKE_CASE` (an enumerator or constant whose name is a macro in a platform or build header takes a short prefix, used for every enumerator of the enum; see section 5.2); types (classes, structs, enums, concepts) `PascalCase`; functions and namespaces `snake_case`; template parameters `PascalCase`. Exception: the properties, signals, slots and `Q_INVOKABLE` functions that QML sees are `camelCase` (the QML convention), confined to view-model classes under `apps/<app>/src/viewmodel/`. | Confirmed by the owner: PascalCase types against snake_case functions and locals keeps a type name visibly different from a variable, and `m_PascalCase` members are visibly different from locals (`m_FrameCount` against `frame_count`). A legacy repository that states no conventions gets one reformat commit to the template's style, listed in `.git-blame-ignore-revs` (section 5.2). Established conventions stay because renaming public identifiers and reformatting a whole tree cost more than they return: `arinc-data-loader` has 1254 findings against the naming rules above (177 enumerators and 62 constants of them in public headers of its installed package) and none against its own rules once they are written into `.clang-tidy`; `wordjewelssolver` keeps Google-based attached braces at 100 columns, `name_` members and lower-case enumerators. |
| D10 | Qt performance practices | Three practices, each with tests and budgets (section 7.6): (1) asynchronous loading, (2) QML compilation through `qt_add_qml_module`, (3) preloading and batching through signals. | Owner decision. `iclforge` publishes speed, memory and growth figures. |
| D11 | Coverage and quality badges | Generated into the repo's `quality-history` branch as shields.io endpoint JSON. SonarCloud is optional and never a required check. | Local-first, fewer vendors (`iclforge` pattern). |
| D12 | Documentation site | MkDocs (Material) built with `--strict`, deployed to GitHub Pages from a workflow. | Present in three of four repos. |
| D13 | Shared tool roots on a developer machine | Two shared locations, both found through environment variables with the `ICL_` prefix (the organisation-wide setting) and overridden per project by a `<PROJECT>_` prefix (for example `ICLFORGE_`). (1) vcpkg: the labs' vcpkg fork `iainchesworthlabs/vcpkg` (it carries ports that upstream does not have yet), cloned locally at `C:\repos\vcpkg` and used as the mirror (`ICL_VCPKG_MIRROR`); each manifest baseline gets its own worktree under `ICL_VCPKG_STORE`. (2) Qt: the prebuilt Qt kit in `C:\repos\common` (today it holds only Qt), found through `ICL_QT_ROOT`, with `QT_ROOT_DIR` and `QTDIR` as fallbacks. CI uses the same variables: aqtinstall for Qt, and the `setup-vcpkg` action, which clones the fork at the baseline and exports `VCPKG_ROOT`. Section 4.2. | Owner decision; mechanism taken from `iclforge/cmake/VcpkgRoot.cmake` and `FindQt6.cmake`. |
| D15 | Shared CI and templates | Organisation repositories: `.github` (community files and defaults), `icl-common-infra` (reusable workflows, composite actions, CMake modules including `VcpkgRoot.cmake` and `FindQt6.cmake`, check scripts, rulesets, labels, `apply.sh`) and `icl-cpp-template` (template repository). The shared repository is named `icl-common-infra` (owner decision); the template repository is `icl-cpp-template`. `.github` and `icl-common-infra` are public because every consumer is public and public repositories cannot call workflows in a private repository. `icl-cpp-template` may be private. Section 16.1. | Owner agreed to org-level shared repositories and asked for a better name than `icl-common-infra`. `iclforge` copied toolchain scripts verbatim from `aqualink-automate`. |
| D16 | Secrets scope | Organisation-level secrets, restricted to selected repositories, for anything shared across projects: GPG signing key, Apple distribution certificate and API keys, Android upload keystore (one upload key for all apps), signing-service credentials. Repository-level secrets only for per-app items: iOS provisioning profile and bundle identifier, per-app tokens. Each repository keeps a `release` environment with the owner as required reviewer, so a release job pauses for approval. Section 17. | Owner decision; the environment gate is retained because organisation secrets alone are readable by any workflow in a selected repository. |
| D17 | Signing status | No commercial Windows or macOS code-signing certificate exists yet, and no Windows signing service is chosen because the options cost money. The release workflow contains the signing steps behind repository variables. `SIGN_WINDOWS` takes `false` (default), `test` or `production`; `SIGN_MACOS` takes `false` (default) or `production`. With `false`, artefacts are unsigned and named `-unsigned`. With `test`, Windows artefacts are signed with a leaf certificate issued by the owner's personal CA, are named `-testsigned`, and are trusted only on machines that have installed that CA's root certificate (section 13.2). | Owner status and decision. |
| D14 | Layout of platform code | `libs/<lib>/src/platform/<os>/` and `apps/<app>/src/platform/<os>/`. A single-target repository uses `src/platform/<os>/`. | The list says `src/platform`; a monorepo has several `src` directories. |

## 3. Repository layout (monorepo)

One repository per product family. Several libraries and applications live together; shared CI and build infrastructure comes from `icl-common-infra` (D15) and shared tool roots (vcpkg fork, Qt) from the `ICL_*` environment variables (D13).

```
CMakeLists.txt  CMakePresets.json  vcpkg.json  vcpkg-configuration.json
.clang-format  .clang-tidy  .editorconfig  .gitattributes  .gitignore  .git-blame-ignore-revs
AGENTS.md  README.md  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  CODE_OF_CONDUCT.md
LICENSE  REUSE.toml  CODEOWNERS (in .github/)
changelog.d/                    one fragment per pull request
cmake/                          modules/  toolchains/  triplets/   (synced from icl-common-infra)
libs/<lib>/
    include/<lib>/              public headers
    src/                        implementation
    src/platform/<os>/          platform-specific files only
    tests/{unit,integration,system}/
    fuzz/   bench/
apps/<app>/
    src/  qml/  src/platform/<os>/
    tests/{unit,integration,system}/   ui-tests/
    translations/               <app>_<lang>.ts
    packaging/                  per-platform bundle definitions
tools/                          scripts used by CI and developers (Python or PowerShell, no shell-only logic)
docs/                           MkDocs source
notices/                        generated third-party and font licence texts
.github/                        workflows/  actions/  rulesets/  labels.yml  ISSUE_TEMPLATE/  dependabot.yml  toolchain-versions.json
```

Rules:
- A library never depends on an application. Applications depend on libraries.
- Public headers are under `include/<lib>/`; everything else is private to the target.
- Static libraries by default. Shared libraries are opt-in per target and use CMake's `generate_export_header` (generated files are exempt from section 4.4).

### 3.1 Portable libraries

Code that is not about a platform lives in portable libraries, so it builds and behaves the same on every target, including targets that cannot run Qt or the full standard library (an ESP32 firmware, WebAssembly). Game rules, parsers, codecs, state machines, input interpretation, ranking and persistence formats belong here. A project declares each portable library in its plan and in CMake, and the rules below are checked, not just written down.

1. **Dependencies.** A portable library depends only on the C++ standard library headers in its declared subset and on other portable libraries. It includes no Qt, platform, operating-system, toolkit or vcpkg-package headers, and has no `src/platform/` directory. Anything that differs by platform is passed in through an interface the application implements (storage, clock, random seed, sensor samples, log sink).
2. **Language profile.** Built with exceptions and RTTI off (`-fno-exceptions -fno-rtti`, `/EHs-c- /GR-`). No iostream, no `std::locale`, no `std::thread` or other threading, no global mutable state, no static initialisers with side effects. Errors are returned (`std::expected`, status enums), never thrown.
3. **Memory.** Allocation after construction is declared per library. A library that claims "no allocation" uses fixed-capacity containers and is tested to show it (a counting allocator, or a build that makes `operator new` fail the test).
4. **Determinism where claimed.** A library whose results must be identical on every platform uses integer arithmetic or documented floating-point, its own random generator (the standard distributions are not portable across standard libraries), and carries golden tests: recorded inputs with expected outputs or state hashes, run on every platform leg of the PR gate.
5. **Language level.** C++23, like the rest of the code. A portable library compiles with every toolchain a project ships, so where an embedded toolchain is older than the compiler floor in D7 (ESP-IDF's stock toolchain is GCC 14 where the floor is GCC 16), the library keeps to the part of C++23 and its library that all of them provide, and the documented header subset says which part. The aim is to close that gap, not to live with it: a project with an embedded target runs a spike on building that target with a floor-level compiler, and records the result. Where the spike succeeds the embedded toolchain is pinned at the floor, and the subset restriction is dropped. The embedded toolchain version is pinned in `.github/toolchain-versions.json` like the others, and a CI leg builds every portable library with it.
6. **Direction.** Portable libraries are linked by applications, platform code and tests, never the other way round. A portable target links only portable targets; the configure step fails otherwise.
7. **Checks.** (a) An include check lists the headers each portable library may use and fails on any other. (b) The reduced-profile build runs on every floor compiler in the PR gate. (c) The embedded-toolchain leg runs in the post-merge tier (11.2), and in the PR gate for a change to a portable library. (d) Golden tests run on every platform leg. (e) Coverage for portable libraries meets D6 without UI tests.
8. **Placement.** The library lives under `libs/<lib>/` like any other. Its name and its place in the dependency graph are recorded in the project's `docs/architecture.md`. When a project migrates or gains a platform, code that is not platform-specific is moved into a portable library instead of copied into the new front end.

The CMake helper that applies the profile (`icl_add_portable_library`), the include check and the embedded-toolchain workflow are shared infrastructure. Until they exist in `icl-common-infra`, a project applies the same rules by hand and notes where it does so.

## 4. Build system

### 4.1 CMake

- `cmake_minimum_required(VERSION 4.0)` and `cmakeMinimumRequired` 4.0 in the presets for new projects. Migrated and existing repositories keep their range until touched.
- `CMAKE_CXX_STANDARD 23`, `CMAKE_CXX_STANDARD_REQUIRED ON`, `CMAKE_CXX_EXTENSIONS OFF`. Targets declare `target_compile_features(<t> PUBLIC cxx_std_23)`. Raising the standard later is a change to one variable.
- Everything is driven by `CMakePresets.json`: configure, build, test and workflow presets. CI calls presets and nothing else. Preset names are `<os>[-<compiler>]-<variant>`: `linux-asan-ubsan`, or `linux-gcc-debug` and `linux-clang-debug` where a project builds one OS with more than one compiler. Build and test presets reuse the name of their configure preset; workflow presets start with `ci-`.
- Required presets: `windows-msvc`, `windows-msvc-arm64`, `windows-llvm` (only if clang-cl is a goal), `linux-gcc`, `linux-llvm`, `linux-gcc-arm64`, `macos-llvm`, `macos-llvm-x64` (or one universal build), `wasm-emscripten` (where sensible), `android-arm64`, `ios-arm64`, `ios-simulator`, plus the variants `debug`, `release`, `asan-ubsan`, `tsan`, `coverage`, `fuzz`.
- Warnings as errors: `-Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror` (MSVC `/W4 /WX`). Hardening flags (`-fstack-protector-strong`, `-fcf-protection`, `-D_GLIBCXX_ASSERTIONS` or libc++ hardening mode, `/GS /guard:cf`, PIE and RELRO) are set in a CMake module from `icl-common-infra`.

### 4.2 Dependencies

- vcpkg in manifest mode with `builtin-baseline`, using the labs' fork `iainchesworthlabs/vcpkg` (D13). Custom ports are added to the fork's `ports/` directory and moved upstream when they are ready. A baseline must name a commit that exists in the fork, so the fork is synced from `microsoft/vcpkg` before a baseline bump. There is no `deps/vcpkg` submodule in new projects; `iclforge` already works this way, and `cubeulator`, `wordjewelssolver` and `aqualink-automate` still carry a submodule that migrates to this scheme.
- `cmake/VcpkgRoot.cmake` (copied from `iclforge` into `icl-common-infra`, with the project prefix as a parameter) picks the vcpkg checkout for a configure, first match wins: (1) an explicit `CMAKE_TOOLCHAIN_FILE`; (2) `<PROJECT>_VCPKG_ROOT`; (3) `<PROJECT>_VCPKG_STORE`, else `ICL_VCPKG_STORE`, where the commit named by the baseline gets its own `git worktree` checkout from the shared mirror (`<PROJECT>_VCPKG_MIRROR`, else `ICL_VCPKG_MIRROR`, else `<store>/mirror`), so checkouts, worktrees and repositories that pin the same commit share one directory and nothing existing is ever moved; (4) `VCPKG_ROOT`, which is what CI sets. A configure that asks for vcpkg and finds none stops with a message listing these options. A plain `cmake -S . -B build` without vcpkg uses FetchContent fallbacks for the small dependencies.
- `cmake/FindQt6.cmake` (from `iclforge`) widens `CMAKE_PREFIX_PATH` for `find_package(Qt6)` and never replaces Qt's own config package. Order: explicit `CMAKE_PREFIX_PATH`, `Qt6_DIR` or `Qt6_ROOT`; then `<PROJECT>_QT_ROOT`, `ICL_QT_ROOT`, `QT_ROOT_DIR` (exported by aqtinstall and `install-qt-action`) and `QTDIR`; then the standard install locations, newest version first. `ICL_QT_ROOT` is new: `iclforge` reads only `ICLFORGE_QT_ROOT`, so adding the shared variable is part of moving the module into `icl-common-infra`. No absolute path appears in a `CMakeLists.txt` or preset.
- Qt comes from aqtinstall (desktop, WebAssembly, Android and iOS kits), never from vcpkg (building it from source costs hours). The version is the `qt` key of `.github/toolchain-versions.json`. `iclforge` documents an aqtinstall workaround for Qt 6.11 and later on Windows; reuse its `aqtsource` handling until a release carries the fix. If another dependency later joins Qt in `C:\repos\common`, it follows the same pattern: an `ICL_<NAME>_ROOT` variable, a `<PROJECT>_<NAME>_ROOT` override, and a pinned version in `toolchain-versions.json`.
- Shared pieces come from `icl-common-infra` (D15): the two CMake modules above, custom triplets (for example `x64-windows-llvm`) and the `setup-vcpkg` action. Baseline bumps (owner approved): Dependabot's `vcpkg` ecosystem is configured in every repository (monthly, reviewed by hand, as in `wordjewelssolver/.github/dependabot.yml`). `iclforge`'s `dependabot.yml` says Dependabot has no vcpkg ecosystem, so the agent confirms the ecosystem works with a test pull request in the first repository and records the result in the plan. Because the baseline must exist in the fork, Dependabot proposes upstream commits and a required check, `vcpkg-baseline-in-fork`, fails the pull request until the fork contains the commit. A scheduled workflow in the fork repository syncs it from `microsoft/vcpkg` weekly so the check normally passes. `iclforge`'s `dependabot.yml` also notes that vcpkg dependencies are not covered by its OSV scan; `icl-common-infra`'s OSV and dependency-review jobs must read `vcpkg.json`.
- Test dependencies (Catch2) are vcpkg features, not default dependencies, so a consumer build does not pull them.

### 4.3 Toolchain pins

One file, `.github/toolchain-versions.json`, holds compiler majors, MSVC toolset, Qt, Emscripten, NDK, Xcode and CMake/Ninja versions that have no other home. A reusable workflow reads it and exposes outputs; a check asserts that duplicated values agree (pattern: `iclforge/.github/workflows/_toolchain-versions.yml`). Updating a toolchain is a one-file change.

The Ubuntu archive may carry a floor compiler as a pre-release snapshot until the upstream release is packaged (Ubuntu 26.04 ships `gcc-16` 16.0.1). The pin is the major version, CI prints the exact version at the start of every leg, and a snapshot counts as meeting the floor. The leg moves to the release package when the distribution publishes it, with no change to the pin.

### 4.4 Preprocessor use in project code

The goal is no preprocessor conditionals or definitions in project code. It is an ideal with two levels.

- Hard rule (the check fails): no preprocessor conditional that tests a platform, operating system, architecture, compiler or standard-library version (`_WIN32`, `__linux__`, `__APPLE__`, `__ANDROID__`, `__EMSCRIPTEN__`, `TARGET_OS_*`, `_MSC_VER`, `__GNUC__`, `__clang__`, `__cplusplus`, `__has_include`, `__cpp_*` and similar). All platform-specific code is in `src/platform/<os>/`.
- Soft rule (the check counts and ratchets): every other `#if`, `#ifdef`, `#ifndef`, `#elif`, `#else`, `#endif`, `#define` and `#undef` is avoided where a language feature does the job. The count of such directives outside the allowlist may not increase, and each pull request that removes some lowers the recorded baseline in `tools/preprocessor-baseline.json`. A new directive needs an allowlist entry with a reason. The baseline is kept per file (`{"files": {"path": count}}`), so two pull requests that touch different files never conflict on it; a file with no entry has a baseline of zero, and `--update-baseline` refuses to raise any number. `tools/preprocessor-allowlist.txt` holds `glob  # reason` lines (a line without a reason is an error) and exempts a path from the soft rule only. `tools/preprocessor-exclude.txt` lists generated and third-party directories, exempt from both rules.

`#include` and `#pragma once` are always allowed.

CMake decides which files are compiled, and nothing else changes what the code means:
- Platform differences: one header declares the interface, one implementation file per platform in `src/platform/<os>/`. A CMake function `platform_sources(<target>)` (in `icl-common-infra`) adds the directory matching the target platform.
- Optional features (Tracy, profiling recorder, SIMD back ends): a directory per implementation, for example `src/profiling/tracy/` and `src/profiling/null/`; CMake picks one. Both expose the same header.
- Build-time values (version, feature switches, paths): `configure_file` writes a header of `inline constexpr` values. Code uses `if constexpr` on them.
- CMake may set compiler and library flags (warnings, hardening, sanitizers, `_GLIBCXX_ASSERTIONS`). It must not set project macros that change which project code compiles.
- Compiler workarounds are deleted. Three compilers at a C++23 floor need none.

Enforcement: `tools/check_no_preprocessor.py` (from `icl-common-infra`; `iclforge` already has a no-preprocessor-conditional rule in its static checks, copy it first) runs in the PR gate over tracked C and C++ files. Paths in `tools/preprocessor-allowlist.txt` are exempt from the soft rule only; the hard rule has no exemption except generated and third-party directories. Each allowlist line carries a reason. Expected entries:

| Path pattern | Reason |
|---|---|
| `src/simd/**.cpp` | Highway requires `HWY_TARGET_INCLUDE` and `foreach_target.h` (section 9) |
| `**/profiling/tracy/*.hpp` | Tracy zone macros capture source location |
| `**/*.h` with `extern "C"` | `#ifdef __cplusplus` in headers that must also compile as C |
| generated and third-party directories | not project code |

An entry outside this table needs an owner-approved reason in the same pull request.

## 5. Language and style

### 5.1 Idiomatic C++23

Prefer, in this order: `std::expected` for recoverable errors at module boundaries; `std::format` and `std::print` instead of iostream and printf; `std::span`, `std::string_view`, `std::mdspan` for non-owning views; `std::unique_ptr` and value types instead of owning raw pointers; ranges and views; `std::jthread` with `std::stop_token` where all three standard libraries provide them (see below); `std::byteswap`, `std::endian`, `<cstdint>` instead of hand-rolled width and byte-order code; `std::flat_map` where a sorted contiguous map fits; deducing `this`; `constexpr` and `consteval` instead of macros; `[[nodiscard]]` on every function whose result matters; `enum class`; `std::unreachable`; `std::source_location`.

Apple's libc++ keeps `std::jthread` and `std::stop_token` behind `-fexperimental-library`, which is not used. Where a target must build on macOS, use `std::thread` with an RAII join (a small class that joins in its destructor) and a `std::atomic<bool>` as the stop flag. Revisit when Apple's libc++ drops the experimental gate.

`import std;` is off by default and may be enabled per target behind a CMake option once all floor compilers pass the CI leg. Targets that include Qt headers keep `#include`.

Use UTF-8 for text internally and at file and network boundaries. Convert at the Windows API boundary only, inside `src/platform/windows/`.

### 5.2 Format and static analysis

- `.clang-format`: a repository with an established format keeps it, and its file is the rule for that repository, as its `.clang-tidy` is for naming (D9). A new repository copies `icl-cpp-template/.clang-format` unchanged (`BasedOnStyle: LLVM`, `ColumnLimit: 120`, `IndentWidth: 4`, `BreakBeforeBraces: Allman`, `PointerAlignment: Left`, `Standard: c++23`); the template file is the source of truth.
- `.clang-tidy` carries `readability-identifier-naming` for D9. A new repository uses these options; an established repository writes its own conventions in the same place:

```yaml
CheckOptions:
  - { key: readability-identifier-naming.LocalVariableCase,        value: lower_case }
  - { key: readability-identifier-naming.ParameterCase,            value: lower_case }
  - { key: readability-identifier-naming.PrivateMemberCase,        value: CamelCase }
  - { key: readability-identifier-naming.PrivateMemberPrefix,      value: m_ }
  - { key: readability-identifier-naming.ProtectedMemberCase,      value: CamelCase }
  - { key: readability-identifier-naming.ProtectedMemberPrefix,    value: m_ }
  - { key: readability-identifier-naming.ConstexprVariableCase,    value: UPPER_CASE }
  - { key: readability-identifier-naming.GlobalConstantCase,       value: UPPER_CASE }
  - { key: readability-identifier-naming.StaticConstantCase,       value: UPPER_CASE }
  - { key: readability-identifier-naming.EnumConstantCase,         value: UPPER_CASE }
  - { key: readability-identifier-naming.ClassCase,                value: CamelCase }
  - { key: readability-identifier-naming.StructCase,               value: CamelCase }
  - { key: readability-identifier-naming.EnumCase,                 value: CamelCase }
  - { key: readability-identifier-naming.ConceptCase,              value: CamelCase }
  - { key: readability-identifier-naming.TemplateParameterCase,    value: CamelCase }
  - { key: readability-identifier-naming.FunctionCase,             value: lower_case }
  - { key: readability-identifier-naming.MethodCase,               value: lower_case }
  - { key: readability-identifier-naming.NamespaceCase,            value: lower_case }
```

`apps/<app>/src/viewmodel/.clang-tidy` overrides `MethodCase` and `PublicMemberCase` to `camelBack` for the properties, signals, slots and invokable functions that QML sees (D9). `CamelCase` in clang-tidy means PascalCase. In an established repository, a directory whose classes a framework names may carry a `.clang-tidy` of its own that inherits the parent's.

- An enumerator or constant whose name is a macro in a platform or build header takes a short prefix: `ERROR`, `DEBUG`, `NEAR`, `FAR`, `IN`, `OUT`, `OPTIONAL`, `min` and `max` are the usual ones. Use the same prefix for every enumerator of the enum (`LEVEL_ERROR`, `LEVEL_DEBUG`, not one prefixed name among plain ones). Do not define `NOGDI` or `NOMINMAX` globally to avoid this, because Qt and other libraries rely on those headers.
- `.editorconfig` mirrors `.clang-format` (indent, final newline, UTF-8, LF) so non-C++ files follow the same rules.
- `clang-format` is a required check. `clang-tidy` runs nightly across the tree and on changed files in the PR gate. `include-what-you-use` runs nightly and reports. MSVC `/analyze` (PREfast) runs nightly.
- Python and PowerShell tooling: `ruff` for Python, `PSScriptAnalyzer` for PowerShell.
- `.git-blame-ignore-revs` lists every mass-reformat commit.

### 5.3 Pre-commit and local hooks

`tools/hooks/` holds `commit-msg` (text policy, rule 6), `pre-commit` (clang-format on staged files, no-preprocessor check, SPDX check). `tools/hooks/install` sets `core.hooksPath`. CI runs the same scripts, so a hook is never the only gate.

## 6. Tests, coverage, performance, fuzzing

### 6.1 Frameworks and taxonomy

Catch2 v3 for all C++ tests. Tests carry CTest labels and the test presets filter on them.

| Label | Scope | Location |
|---|---|---|
| `unit` | one class or function, no I/O, milliseconds | `tests/unit/` |
| `integration` | several components, real filesystem and loopback sockets | `tests/integration/` |
| `system` | the built executable end to end, golden outputs | `tests/system/` |
| `ui` | the real Qt Quick UI driven by test code | `apps/<app>/ui-tests/` |
| `perf` | benchmarks with stored results | `libs/<lib>/bench/` |
| `fuzz` | fuzz harness regression replay | `libs/<lib>/fuzz/` |

Every public function in a library has a unit test. Every file format and wire protocol has a system test with golden data.

### 6.2 Qt UI tests drive features

A feature is accepted when a UI test drives it through the QML interface and passes. The UI test is the acceptance test and its name carries the feature identifier used in `changelog.d` and in `docs/`. UI tests run headless (`QT_QPA_PLATFORM=offscreen`). Where a GPU is not available on the runner, Quick tests use software rendering (`QT_QUICK_BACKEND=software`), and a separate nightly job on a GPU-capable runner (or Mesa llvmpipe for OpenGL) exercises Quick 3D scenes. UI tests run against the coverage build, so UI code and the C++ it calls count toward coverage (6.4).

### 6.3 Sanitizers

- Preset `asan-ubsan`: Linux Clang and GCC, `-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -O1`. MSVC: `/fsanitize=address /O1` (UBSan is not available in MSVC; the `/RTC` flags and incremental linking are removed, and `_DISABLE_STL_ANNOTATION` is set because vcpkg dependencies are not instrumented). clang-cl does not run ASan with the debug CRT that the Qt and vcpkg builds use; `cubeulator/cmake/Sanitizers.cmake` records this and skips the leg.
- Preset `tsan` (required): Linux Clang, a separate job (TSan cannot be combined with ASan). Runs the unit, integration, system and `ui` labels. It runs on every merge-queue entry and in the nightly run, and in the PR gate when the change touches threading code (files that include `<thread>`, `<mutex>`, `<atomic>`, `<stop_token>`, `<future>`, Qt thread or concurrent headers, or paths listed in `tools/ci/tsan-paths.json`).
- A separate `asan-ubsan` preset is not required when every Debug preset already carries both sanitizers, as long as one leg builds with Clang and one with GCC. `tsan` is always its own preset.
- The test suite runs under ASan/UBSan on every PR for the Linux Clang leg, and under TSan as above. The MSVC ASan leg runs nightly.
- A suppressions file per sanitizer lives in `tools/sanitizers/` with a reason and a tracking issue per line.

### 6.4 Coverage

- Build: preset `coverage` (Linux GCC with `--coverage`, or Clang source-based coverage). Run all labels except `perf` and `fuzz`, including `ui`.
- Report: `gcovr` merges the runs. Gate: `--fail-under-line 90 --fail-under-branch 80 --exclude-throw-branches --exclude-unreachable-branches`. gcovr line coverage is used as the statement measure.
- Excluded: `tests/`, `ui-tests/`, third-party code, and generated code (moc, rcc, qmlcachegen).
- Ratchet for migrated code: `coverage-floor.json` records the current statement and branch values; CI fails if coverage drops below the floor and a pull request that raises coverage lowers the gap by raising the floor. Each release raises the floor by a fixed step until the D6 targets are met. New code (files added after migration) must meet D6 on its own, checked on the diff.
- Output: the `quality-history` branch receives badge JSON and trend data (D11).

### 6.5 Performance tests

- Catch2 `BENCHMARK` for micro-benchmarks, plus Google Benchmark where repeated-run statistics are needed (`aqualink-automate` uses it).
- Qt performance tests (D10, section 7.6): startup to first frame, p95 frame time while content loads asynchronously, signal count per bulk update, and peak memory. Each has a budget in `perf-budget.json`.
- CI compares results against `develop` and fails on a regression above the threshold in `perf-budget.json` (pattern: `iclforge/.github/workflows/_compare.yml`). Performance legs run in the merge queue and nightly, on a pinned runner class so numbers are comparable. The bench environment is recorded with each result (`iclforge/.github/scripts/capture-bench-environment.sh`).

### 6.6 Fuzzing

Fuzzing is part of the nightly security run.
- Every function that parses untrusted input (file formats, network messages, command lines, configuration) has a libFuzzer harness in `libs/<lib>/fuzz/` with a seed corpus and a `regressions/` directory of past crashes.
- `fuzz-regress` (replay seeds and regressions with `-runs=0`) is part of the PR gate and takes seconds.
- `fuzz-short` runs on push to `develop` (about 60 seconds per target).
- `fuzz-nightly` runs 10 minutes per target, with the corpus persisted between runs through the Actions cache.
- A crash opens an issue labelled `nightly-analysis` and the reproducer is added to `regressions/` in the fix.
- Pattern: `iclforge/.github/workflows/fuzz.yml`. Fuzz builds are separate from the sanitizer and Tracy builds (libFuzzer brings its own ASan).

## 7. Qt, localisation, right-to-left, fonts, licences in the application

### 7.1 Qt

- Qt 6.12 from the shared pin (section 4.2). Qt Quick 3D is allowed for UI together with QML, with one cost: Qt offers it under GPL-3.0-only or a commercial licence, so an application that links it is GPL-3.0-only as a binary, which sits badly with D2 (`GPL-3.0-or-later`) and D8 (App Store). A project that wants "or later" or a store build does not use it. Modules are listed per app in CMake; unused modules are not linked.
- Business logic lives in libraries without Qt dependencies where practical. QML binds to thin C++ view-model classes.
- No Qt Widgets in new code unless an existing application needs it. A migrated application with no widget toolkit to preserve (for example a game rendering into a GLFW window) uses Qt Quick; Qt Widgets stay for an existing application that already has a Widgets UI.
- A QML module URI differs from the executable name and from every target's output name by more than case, for example `<Project>App` or `<Project>.Ui`. On a case-insensitive file system the module's output directory and the executable are otherwise one path, and the macOS link fails.

### 7.2 Localisation

- Languages per D3. Source strings are English via `qsTr` and `tr`. `qt_add_translations` generates `.ts` and `.qm` files; a `<app>_lupdate` target refreshes them.
- Machine translation is accepted. Each `.ts` file header and `docs/i18n.md` record the translation origin and review status per language.
- A test (pattern: `iclforge/apps/crucible/ui/tests/test_translations.cpp`) asserts that every language contains every source string, none is marked unfinished, and placeholders (`%1`, plural forms) match the source.
- Locale-sensitive formatting (numbers, dates, plurals) goes through `QLocale` and `std::format` with locale, never string concatenation.

### 7.3 Right-to-left

- `he` and `yi` set `Qt::RightToLeft` layout direction. QML uses `LayoutMirroring.enabled` and anchors or `Layout` positions instead of fixed left/right.
- A UI test runs each main screen under a right-to-left locale and checks mirrored geometry and that no text is clipped.
- Icons that imply direction (back, forward, progress) have a mirrored variant.
- Yiddish uses Hebrew script; the bundled font must cover Hebrew letters and points. `iclforge/apps/crucible/CMakeLists.txt` shows the font selection and fallback.

### 7.4 Fonts

Fonts are bundled in releases (embedded through Qt resources on mobile and WebAssembly, installed alongside the application on desktop). Font choices cover Latin, Hebrew, and CJK (Japanese and Simplified Chinese). Only fonts under the SIL OFL or an equally permissive licence are used. Each font's licence text is copied into `notices/` by the build. CJK fonts are large; the plan states the size cost per platform and the WebAssembly build subsets fonts or loads them lazily. Where the source strings are fixed, the bundled fonts are subset to the glyphs of the project's catalogues (`pyftsubset`), which also makes a browser build work, because a browser has no system fonts. A desktop-only project may document a system fallback instead. For a pixel-style look, Fusion Pixel Font (OFL 1.1) is a CJK candidate once the licence file of the exact release has been read; Zpix is excluded because it is paid for commercial use and forbids modification.

Letters and numerals that a child must read are set in a face designed for beginning readers (Andika, OFL); a pixel or display face is for the chrome. Pixel faces fail the test: `O` and `0` match, `G` reads as `6`, and at 16 to 30 px the digits 2, 3 and 5 read as Z, 8 and S.

### 7.5 Licences in the application

- `notices/` is generated, not hand-edited: from the vcpkg manifest and installed package metadata for libraries, from a font manifest for fonts, and from Qt's own notice for the Qt modules used (pattern: `cubeulator/cmake/ThirdPartyNoticesGenerate.cmake`).
- The About dialog shows the application licence (GPL-3.0-or-later), the source location with the exact tag or commit, and a list of third-party components with licence text one click away.
- A test fails if a runtime dependency in the vcpkg manifest has no entry in the generated notices.
- Every bundle (installer, archive, app bundle, APK/AAB, IPA, WebAssembly package) contains `LICENSE`, the generated notices, and a `SOURCE.txt` naming the commit.
- For a Qt application, `icl_install_qt_app()` (icl-common-infra, `cmake/IclQtApp.cmake`) does this in one call: install rules, the Qt deploy step, macOS bundle properties (identifier required, version from the project version), `LICENSE`, `LICENSES/`, `THIRD-PARTY-NOTICES.txt` generated at configure time from the licence file of each runtime dependency (the configure fails when one is missing), and `SOURCE.txt` written at install time. Qt's own third-party components are linked to Qt's list, not copied. The About dialog and its test remain the application's job.

### 7.6 Qt performance practices

Three practices apply to every Qt application. Each has a rule, a lint or check where one exists, and a test with a budget in `perf-budget.json`.

1. Asynchronous loading. Nothing that blocks (file or network I/O, parsing, decoding, heavy computation) runs on the GUI thread. Use `Loader` with `asynchronous: true`, asynchronous `QQmlComponent` creation or `QQmlIncubator` for components, `asynchronous: true` on `Image`, and worker threads (`std::jthread` where available, otherwise `std::thread` with an RAII join, or Qt Concurrent) that hand results to the GUI thread through queued signals. The window shows its first frame before heavy content exists, with a lightweight placeholder where needed.
   Tests: a UI test asserts that the first frame is presented before a deliberately slow content source finishes, and that no frame during loading exceeds the frame budget (measured from `QQuickWindow::frameSwapped` timestamps, with Tracy zones on the loading path in the `debug` preset).
2. QML compilation. Every QML module is declared with `qt_add_qml_module` (URI, version, `QML_FILES`, `RESOURCES`, and `SOURCES` for its C++ types registered with `QML_ELEMENT`), so QML is compiled ahead of time by qmlcachegen and no QML file is parsed from source at run time. `NO_CACHEGEN` is not used. The `qmllint` target that `qt_add_qml_module` creates runs in the PR gate and must report no warnings. Optional: the Qt Quick type compiler (`ENABLE_TYPE_COMPILER` on `qt_add_qml_module`) for hot modules, enabled per module with a measured gain recorded in the plan. A CMake check fails if `NO_CACHEGEN` appears anywhere.
   Tests: the startup-to-first-frame budget, measured in the release preset on a pinned runner class, catches a regression to run-time compilation.
3. Preloading and batching through signals. After the first frame, the application preloads in the background what the next likely screen needs (components created asynchronously, models filled, images and fonts loaded) so navigation does not stall. C++ objects batch their notifications: a bulk change emits one `rowsInserted`, `dataChanged` over a range, or a single `batchChanged`, not one signal per item; high-frequency property changes are coalesced with a dirty flag and one queued call or a zero-interval single-shot timer; worker threads deliver results as one batch (a vector payload) per queued signal.
   Tests: unit tests count the signals emitted for a bulk update (at most one per batch, for example with `QSignalSpy`), and a UI test checks frame time while a bulk update runs.

Budgets in `perf-budget.json` for these three: startup to first frame, p95 frame time during asynchronous loading, p95 frame time during a bulk update, signals per bulk update, and peak memory. The merge-queue comparison (6.5) enforces them.

## 8. Profiling (Tracy)

- Tracy comes from vcpkg as a feature (`profiling`), a pinned version from the baseline.
- Default: ON in the `debug` preset, OFF in the sanitizer presets unless D4's condition is met, OFF in the coverage and fuzz presets, and OFF in release. Release builds can switch it on with `-D<PROJECT>_ENABLE_TRACY=ON`. The option is declared once in `cmake/Tracy.cmake` (from `icl-common-infra`).
- A Tracy client opens a network listener. Defaults: `TRACY_ON_DEMAND` (no data collection until a profiler connects) and `TRACY_ONLY_LOCALHOST`. Remote profiling requires an explicit option. A release with Tracy on is never distributed through app stores.
- GPU profiling is on by default where Tracy supports the active graphics API. Qt picks the graphics API at runtime through the RHI, so the GPU context is created per active backend from `QQuickWindow` render signals, and unsupported backends skip GPU zones silently. Check the backends supported by the pinned Tracy version before promising a backend.
- Source-level macros: `src/profiling/tracy/` and `src/profiling/null/` expose the same header (`ZONE_SCOPED`-style names prefixed per project); CMake picks the directory (section 4.4).
- WebAssembly and iOS cannot host a Tracy listener usefully. They use the in-process recorder (Chrome trace or CSV output) from `cubeulator/cmake/ProfileRecorder.cmake`, selected the same way.

## 9. SIMD

- Library: Google Highway (`highway` in vcpkg). Code is written once with Highway ops and compiled for all attainable targets in one binary; `HWY_DYNAMIC_DISPATCH` picks the best target at run time. Scalar (`HWY_SCALAR`/`EMU128`) is always compiled, so a CPU without any supported extension runs the scalar path.
- WebAssembly uses the compile-time WASM targets; there is no runtime dispatch there.
- Tests: every SIMD function has a scalar reference implementation and a unit test that compares them over generated inputs. A CI job runs the full unit suite once with dispatch forced to scalar (check the API in the pinned Highway version: `hwy::SetSupportedTargetsForTest`).
- Highway's `foreach_target.h` mechanism uses `#define` and `#include` in the dispatching source files, which is the allowlisted exception in section 4.4. Keep dispatching sources small and in `src/simd/`.
- `xsimd::dispatch` is an acceptable alternative where no preprocessor use is wanted; the choice is recorded in the plan.

## 10. Platforms

| Platform | Presets | Notes |
|---|---|---|
| Windows x64 and ARM64 | `windows-msvc`, `windows-msvc-arm64` | MSVC 19.51/19.52 floor; Authenticode signing pending (D17, section 13) |
| macOS arm64 and x64 | `macos-llvm`, `macos-llvm-x64` | Developer ID signing and notarisation pending (D17) |
| Linux x64 and ARM64 | `linux-gcc`, `linux-llvm`, ARM64 variants | GCC 16, Clang 23 |
| Android arm64 | `android-arm64` | NDK from the toolchain pins; signed AAB and APK |
| iOS arm64 and simulator | `ios-arm64`, `ios-simulator` | D8 |
| WebAssembly | `wasm-emscripten` | where sensible; section 14 |
| ESP32 family (ESP-IDF) | `esp32p4` and similar | Portable libraries (3.1) plus a project-specific front end and drivers; toolchain from ESP-IDF or a floor-level compiler used with it, pinned in `.github/toolchain-versions.json`; the stock ESP-IDF toolchain may be below the D7 floor (section 3.1, rule 5); built in CI from Espressif's container, no hardware in CI |

Platform code lives in `src/platform/<os>/` only (D14, section 4.4). The CI matrix is tiered (section 11.2) so the full matrix runs nightly and the PR gate stays short.

## 11. CI

### 11.1 Workflow rules (all repositories)

- Top-level `permissions: {}` in every workflow; each job grants only what it needs.
- SHA pinning is required. Every `uses:` (including reusable workflows from `icl-common-infra` and local composite actions' own `uses:`) is pinned to a full commit SHA with the tag in a trailing comment. Inside `icl-common-infra`, a reusable workflow calls its own sibling actions with the `$/` syntax, which resolves to the same repository at the commit the caller pinned, so one SHA in the consumer covers the workflow, its actions and its scripts (runner 2.336.0 or later, github.com only; `actionlint` needs an ignore pattern for it). A caller job that needs the shared scripts uses the `checkout-infra` action, which reads the commit from `github.action_ref`, so Dependabot's bump of the `uses:` line moves the scripts as well. The consumer's vendored `cmake/icl/` records its source commit in `cmake/icl/SOURCE`, and CI fails when the copy differs from the pinned commit. A `pinact` check fails the PR gate on any unpinned reference, and the organisation Actions policy requires SHA pinning where GitHub offers the setting. Dependabot updates the pins. The existing repositories are 67% to 85% pinned today; migrating them to 100% is part of adopting this standard.
- Untrusted text (PR titles, bodies, branch names) is passed through `env:`, never interpolated into `run:` scripts.
- `actions/checkout` runs with `persist-credentials: false` unless the job pushes.
- `zizmor` and `actionlint` run on every pull request that touches `.github/`, and `zizmor` nightly.
- Concurrency groups cancel superseded runs on pull requests.
- Third-party actions are limited to a short list kept in `icl-common-infra` and reviewed on addition.

### 11.2 Tiers

| Tier | When | Content |
|---|---|---|
| Before a push | by hand or hook | `tools/ci/precheck.py`: the static checks that need no build, and the gate's plan for the diff |
| PR gate | every pull request and merge-queue entry | the planner (11.5) decides the scope. Format, no-preprocessor check, SPDX/REUSE, pinning, changelog fragment, docs build, Linux GCC build and all non-perf tests, Linux Clang ASan/UBSan, `fuzz-regress`, dependency review; TSan when threading code changed |
| Merge queue | queue entry | the gate on the merged tree, plus Windows MSVC, TSan, Qt GUI build, and the performance comparison when `src/` changed. macOS and mobile legs run here only when the planner flags a change that can affect them |
| Post-merge | push to `develop`, one run at a time | the remaining platform legs (macOS, ARM64, Android, iOS, WebAssembly, embedded toolchains), `fuzz-short`, coverage and quality-history update |
| Nightly | schedule | everything: all compilers at floor and newest, TSan, MSVC ASan, mobile and WebAssembly builds, CodeQL, MSVC `/analyze`, clang-tidy, include-what-you-use, OSV-Scanner, Scorecard, fuzz-nightly, GPU UI tests, full coverage |

Pattern: `iclforge/.github/ci/legs.jsonc` and `pr-gate.yml`.

### 11.3 Required checks

Required checks are the names of aggregator jobs (`CI Status`, `Branch Name`, `Scan dependency diff`, and `vcpkg-baseline-in-fork` on pull requests that change `builtin-baseline`), not individual matrix legs. Each required job is defined in the caller's `ci.yml` under exactly that name, because a check from a called workflow is reported as `<caller job> / <called job>`. The `ci-status` action takes `toJSON(needs)` and a map of job to whether the plan asked for it. The aggregator fails when a job the plan asked for was skipped. Every required workflow also triggers on `merge_group`. Path filters are not used on required workflows, because a required check that never reports leaves a docs-only pull request blocked (the CodeQL case recorded in `iclforge/.github/branch-protection.md`).

### 11.4 Nightly findings become issues

Nightly analysis workflows (CodeQL, MSVC `/analyze`, clang-tidy, fuzzing, OSV, SonarCloud if enabled) call the composite action `report-nightly-failure` from `icl-common-infra`. It opens or comments on one issue per engine labelled `nightly-analysis`. The owner closes the issue when the findings are fixed or dismissed.

### 11.5 CI for many parallel agents

CI speed and cost is a design constraint, not a tuning step. `iclforge/docs/ci-agentic.md` and `ci-lanes.md` record the measurements this section is built on: about 26 merges a day from a few dozen branches; one full run asked for 6 to 10 runner-hours and was paid three times per change (on the pull request, in the queue and on the main branch); 51% of requested runner time went to cancelled runs and 19% to failed runs; GitHub Free allows 20 concurrent hosted jobs organisation-wide and 5 for macOS; and a Linux GCC build with every test would have caught 71% of the failures that pull requests and queue entries actually had. Requirements for every repository:

1. Staged verification. A change pays for the cheap, high-yield checks on the pull request and the expensive checks later, once, on the merged tree (table 11.2). Failures found only by a later stage are attributed to the merges that could have caused them.
2. A planner, `tools/ci/plan_gate.py` (pattern: `iclforge/tools/ci/plan_gate.py`), reads the changed files and a project table (`tools/checks/projects.json`: project, kind, lanes) and decides the scope: documentation-only changes run static checks and no build; changes nothing a Linux build reads run static checks only; anything else builds Linux GCC; Qt is installed and the GUI built only when the change touches the GUI, shared UI code, `cmake/` or the top-level CMake and manifest files; a path the planner does not recognise builds everything; changes to the gate's own files build everything.
3. One aggregator job (`CI Status`) fails if any job the plan asked for did not succeed, and counts a needed-but-skipped job as a failure.
4. Static checks are one job that runs every check even after one fails, so a single run lists all failures. They run on the pull request and the queue entry and are not repeated after the merge.
5. ccache on every compile job. CTest runs in phases: Catch2 cases in parallel; Qt Quick suites in a phase of their own at a limited parallelism; performance guards alone and last. A failing case is retried once and a pass-after-fail is reported as a warning. A parallel phase that still fails re-runs the failed tests by name (`ctest --tests-from-file`, never `--rerun-failed`) one at a time, and the leg fails unless the tests it re-ran are exactly the tests that failed.
6. Fail early, report fully. Static checks and the build come first; checks that only need built binaries run whenever the build succeeded, even if a test failed. Every failed job writes a summary with the compiler errors or failing tests and the command that reproduces them locally.
7. Concurrency. Superseded pushes to a pull request cancel their runs. Post-merge runs execute one at a time with at most one waiting, and the waiting place goes to the newest push, so a burst of merges is verified as one batch. Merge-queue entries build in parallel and merge in groups (`ALLGREEN`).
8. Draft pull requests run the planner and the static checks only; the full gate runs when the pull request is marked ready or is queued (confirmed by the owner). Agents open pull requests as drafts and mark them ready when the work is complete and `precheck.py` is clean.
9. On request: `gh workflow run ci.yml --ref <branch>` runs the whole matrix and `-f legs=<names>` runs named legs, for changes to how things are built. The `deep` label does the same on a pull request. These are used sparingly because a full run holds a dozen or more hosted runners and delays every other gate.
10. Capacity budget. The hosted-runner limits are shared by every repository in the organisation. Nightly schedules are staggered by repository, macOS and mobile legs stay out of the PR gate, and a self-hosted fleet with hosted fallback (11.6) is the planned relief when saturation recurs.
11. Measurement. A weekly job reports, per repository, runner-minutes per merged change, the share spent in cancelled and failed runs, and the median and p95 gate duration. Targets for the PR gate: median 10 minutes or less on a warm cache, p95 20 minutes or less. When a target is missed for two weeks, fixing it comes before new CI features.
12. Before queueing a change that touches threads, the standard library, platform code or CMake, run `gh workflow run ci.yml --ref <branch>` (or add the `deep` label), because the macOS and Windows legs otherwise run first in the merge queue.
13. Conflict avoidance between agents: one `changelog.d` fragment per pull request (never edit `CHANGELOG.md`), no committed generated files, no shared lock files except the manifest baseline (bumped monthly in one pull request), `CODEOWNERS` without required reviews, and small pull requests (one logical step each, rule 7).

### 11.6 Runners and caches

- GitHub-hosted runners by default. A self-hosted fleet is optional and used through a `decide-runner` action that falls back to hosted runners when the fleet is busy (`iclforge/.github/actions/decide-runner`).
- vcpkg binary cache, ccache, and Qt install cache are keyed on the toolchain pin file and the vcpkg baseline. A `cache-hygiene` workflow deletes branch caches when a pull request closes.
- Qt installs and vcpkg builds happen once per leg in a composite action from `icl-common-infra`.

## 12. Repository administration as code

Settings that live in the GitHub UI are applied by one idempotent script, `tools/repo-admin/apply.sh` (uses `gh api`), reading files in the repository:
- `.github/rulesets/*.json`
- `.github/labels.json`
- `.github/repo-settings.json` (description, homepage, topics, features, Actions policy, security settings, environments)

The files are JSON, not YAML, so the script needs no YAML parser. The script is `admin/apply.sh` in `icl-common-infra`, run from the target repository's checkout; it falls back to the defaults in `icl-common-infra/admin/` when a file is absent. It makes no change unless given `--apply` (the default is a dry run that prints each call), and it substitutes `__RELEASE_BOT_APP_ID__` and `__OWNER_USER__` from the environment variables `RELEASE_BOT_APP_ID` and `OWNER_USER`.

The agent writes and tests the script against a scratch repository and then asks the owner before running it against the real one (rule 2). The script needs an admin-scoped token that the owner supplies at run time.

### 12.1 Repository settings

- Description set; homepage is the GitHub Pages URL; topics include `cpp`, `cpp23`, `cmake`, `vcpkg`, `qt6` (when Qt) and one or two domain topics.
- Features: Issues on, Discussions optional, Wiki off, Projects off.
- Merge: squash merge only, `allow_auto_merge` on, `delete_branch_on_merge` on, linear history.
- Actions: default `GITHUB_TOKEN` permission read-only, workflows cannot approve pull requests, outside-collaborator runs need approval, SHA pinning required where the setting is available.
- Security: Dependabot alerts and security updates on; secret scanning and push protection on; private vulnerability reporting on; code scanning with the CodeQL workflow in `.github/workflows/` (nightly); Copilot Autofix on for code scanning alerts (if the API does not expose it, the plan lists it as a manual step).
- Pages: build type "GitHub Actions".
- Merge queue and branch protection come from rulesets, which are available on public repositories owned by an organisation. The repository must be organisation-owned.

### 12.2 Rulesets

Branching follows D1: `develop` is the default branch and the trunk, `main` is release-only.

- `develop-protection` (target `develop`): deletion blocked, non-fast-forward blocked, pull request required (0 approving reviews while the project has one maintainer, stale approvals dismissed, conversation resolution required, squash only), required status checks (section 11.3), linear history, no bypass actors. "Require branches to be up to date" is off; the merge queue makes each entry current.
- `merge-queue-develop` (target `develop`): `merge_queue` rule, `ALLGREEN`, squash, build concurrency sized to the runner budget (start at 4 and tune from the section 11.5 measurements) (pattern: `wordjewelssolver/.github/rulesets/merge-queue-develop.json`).
- `main-release-only` (target `main`): restrict updates, so only the bypass actor can move it; deletion blocked; non-fast-forward blocked. No pull requests are used. The bypass actor is a small organisation GitHub App (the release bot), created once; the release workflow obtains a short-lived token for it (`actions/create-github-app-token`) and fast-forwards `main` to the tagged commit only after the release job succeeds. `GITHUB_TOKEN` cannot bypass a ruleset, which is why an App is used. The App's creation is an owner action (section 17).
- `tags` (target `v*`): tags cannot be deleted, moved or re-created; creation is restricted to the owner and the release bot.
- `branch-names` (creation rule): allowed prefixes are `develop`, `main`, `feature/**`, `bugfix/**`, `docs/**`, `chore/**`, `agent/**`, `dependabot/**`, `gh-readonly-queue/**`, `quality-history` (D11), `gh-pages` where a project publishes from a branch, and `release/**` for support branches only.
- A repository that opts out of D1 and uses plain trunk-based `main` changes `develop-protection` and `merge-queue-develop` to target `main` and drops `main-release-only`; the plan records the reason.

### 12.3 Dependabot

`.github/dependabot.yml` covers: `github-actions` (weekly, minor and patch grouped, majors separate), `pip` for CI and docs tooling (weekly), `vcpkg` (monthly, reviewed by hand, subject to the fork rule in section 4.2) together with `gitsubmodule` only in a repository that still has a submodule, `npm` or `docker` when present. All use `cooldown: default-days: 7`, `rebase-strategy: disabled`, target `develop`.

Auto-merge (pattern: `dependabot-auto-merge.yml` in three reference repos): enabled for patch and minor updates in the `github-actions` and `ci-tooling` groups after required checks pass. The bit is set with a personal access token stored as the Dependabot secret `MERGE_QUEUE_TOKEN`; the Actions `GITHUB_TOKEN` can set the bit but GitHub does not queue the pull request on its strength (the `iclforge` finding), so there is no fallback to it. It is not enabled for vcpkg, submodule, or any major update.

### 12.4 Labels

`.github/labels.yml` defines the standard set, applied by the script:
`bug`, `feature`, `docs`, `chore`, `security`, `dependencies`, `github-actions`, `performance`, `i18n`, `ui`, `no-changelog`, `nightly-analysis`, `deep` (runs the full matrix on a pull request), `good first issue`, `help wanted`, and `platform:windows|macos|linux|ios|android|wasm`.

### 12.5 Community files

`CONTRIBUTING.md` (branching, commit text policy, DCO, how to run presets, how to add a test, how to add a translation), `SECURITY.md` (private vulnerability reporting, what counts, supported versions, how to verify release signatures), `CODE_OF_CONDUCT.md`, `.github/CODEOWNERS`, issue forms (bug, feature), pull request template with a changelog-fragment and test checklist. These live in the organisation `.github` repository as defaults and are overridden per repository only when needed.

## 13. Releases, signing, SBOM, changelog

### 13.1 Versioning and changelog

- Semantic versioning. A release is a `vMAJOR.MINOR.PATCH` tag on a `develop` commit; `main` is fast-forwarded to it when the release succeeds.
- `changelog.d/<slug>.<type>.md` is added by each pull request that changes what a user sees. Types: `added`, `changed`, `fixed`, `removed`, `security`. The `no-changelog` label skips the check. A pull request into `develop` assembles the fragments into `CHANGELOG.md` before the tag (`changelog_tool.py assemble`), because the release job cannot commit to a protected branch. The release job fails a final release whose version has no section in `CHANGELOG.md`. For a pre-release it builds the notes from the pending fragments without consuming them (`changelog_tool.py notes --allow-pending`, the `release-notes` action), so the final release's section still lists everything since the previous final release (pattern: `cubeulator/changelog.d/README.md`, `tools/release/check-fragment.sh`). The check workflow starts advisory and becomes required once the habit holds.

### 13.2 Release workflow

`release.yml` is triggered by a `v*` tag on a `develop` commit. The release is split in two. The project's own `release.yml` builds the packaging matrix and applies the platform signing, then uploads each package as an artifact named `release-*`. The shared `release-publish.yml` in `icl-common-infra` then verifies the tag (semantic version, on `develop`), signs, attests, generates the SBOM, publishes a GitHub Release (pattern: `iclforge/.github/workflows/release.yml`), and as its last step fast-forwards `main` to the tagged commit using the release bot (section 12.2). The signing jobs run in the `release` environment, with the owner as required reviewer, so each release pauses for approval. Shared signing secrets are organisation secrets (D16).

Per artefact:
- SHA-512 checksum in `SHA512SUMS` and a detached GPG signature (`.asc`) for every artefact and for `SHA512SUMS`.
- SBOM in SPDX JSON, generated with `anchore/sbom-action`, signed the same way.
- Sigstore build-provenance attestation (`actions/attest-build-provenance`).
- The public GPG key and its fingerprint are committed (`docs/signing-key.asc`) and quoted in `SECURITY.md` with verification commands.

Platform signing (secret names are given in section 17):
- Windows (D17): the signing step is written behind `SIGN_WINDOWS` with three modes.
  - `false` (default): unsigned, named `*-unsigned`.
  - `test`: Authenticode signing (`signtool`) with a leaf certificate issued by the owner's personal CA, for test builds. The leaf has the Code Signing extended key usage (1.3.6.1.5.5.7.3.3) and a validity of one year or less. Only the leaf certificate and its key (a PFX in the organisation secret `WIN_TESTSIGN_PFX_BASE64` with its password) go to CI; the CA's own key stays offline on the owner's machine and is never uploaded. Signatures carry an RFC 3161 timestamp from a public timestamp server, so they stay valid after the leaf expires. Artefacts are named `*-testsigned`. Until a production certificate exists they may be attached to any release, final or pre-release; the release notes and the project's verification page then say that the Windows signature is a test signature that only machines with the CA root trust. `docs/test-signing.md` explains how to install the CA root on a test machine. Windows SmartScreen and other machines will not trust these builds.
  - `production`: signing through a trusted service or certificate, selected later. Options for the owner to evaluate: SignPath Foundation (free for open-source projects, application required), Azure Artifact Signing (check eligibility for the owner's country and entity type), or a certificate from a public certificate authority with a cloud-held key (hardware-token-only certificates cannot be used on hosted runners). The personal CA migrates to a production CA by changing the secret and setting the variable to `production`; the workflow steps stay the same where the tool is `signtool`. OPEN: the production service is not chosen.
- macOS (not yet purchased, D17): the step is written behind `SIGN_MACOS`, default `false`. When enabled: Developer ID Application certificate, `codesign` with hardened runtime, `notarytool` submission, stapling. One Apple Developer Program membership also covers iOS distribution (D8).
- Android: release keystore, `apksigner` (APK) and `jarsigner` or Gradle signing (AAB). Play App Signing is used for the store, with the keystore as the upload key.
- iOS (D8): the `import-ios-signing` and `export-ios-ipa` actions do this: distribution certificate and provisioning profile imported into a temporary keychain on a macOS runner, `xcodebuild -exportArchive`, upload to App Store Connect (TestFlight first) with an App Store Connect API key. The job is written and tested up to the export step with a development profile; the upload step is enabled once the Apple membership and API key exist.
- When a signing variable is `false` the release still publishes, with the unsigned status stated in the release notes and in `docs/releasing.md`. The GPG signatures, SHA-512 sums, SBOM and attestations above do not depend on these certificates.
- Linux: tar.gz and AppImage as a baseline; further formats (deb, Flatpak) are added per project.

Dry run before the first pre-release tag: `gh workflow run release.yml --ref develop` builds every package without publishing. Unpack each package on its platform and run it (`--smoke-test` where the application has one).

## 14. Documentation

- MkDocs Material, `mkdocs build --strict` in the PR gate. Deployment is a workflow with the Pages "GitHub Actions" build type, triggered by pushes to `main`, so the published site always matches the latest release. The release bot's fast-forward of `main` starts it, because pushes made with a GitHub App token start workflows and pushes made with `GITHUB_TOKEN` do not.
- Required pages: quick start, building (every preset), architecture (libraries, dependency direction, platform layer), testing (taxonomy, coverage policy), CI (tiers and required checks), releasing and signing, security and threat model, i18n, profiling, contributing. API reference from Doxygen XML or `mkdoxy`.
- Documentation accuracy rule (rule 5): `AGENTS.md` carries the "change X, update Y" table.
- WebAssembly web version, where sensible (a UI application or a library with an interactive demo): built in the docs workflow and published under `/demo/`. GitHub Pages cannot send the cross-origin isolation headers that multithreaded Qt for WebAssembly needs, so the Pages build uses the single-thread Qt kit, or ships a service worker that sets the headers. The plan records which one. Demo size is budgeted (fonts and Qt runtime).
- A docs check workflow validates links and that every command in `docs/building.md` names an existing preset.

## 15. README

Top of `README.md`, in this order: name and one-line description; badge row; screenshot or demo link; quick start; link to docs.

Badge row: CI, CodeQL, MSVC analysis, static analysis, zizmor, OSV-Scanner, OpenSSF Scorecard, coverage (statement), coverage (branch), performance figures (from `quality-history`), latest release, docs, C++23, licence (`GPL-3.0-or-later`), platforms. Every badge links to the workflow run or page it reports on. A check fails the docs build when a badge URL names a workflow file that does not exist (this catches stale keys such as the SonarCloud project key in `iclforge`'s README, which still says `ac3forge`).

## 16. Procedures

### 16.1 MODE=bootstrap-org (one-off)

1. Create the organisation `.github` repository, public (community files, issue forms, PR template, default labels).
2. Create `icl-common-infra` (D15), public, containing: reusable workflows (`workflow_call`) for the PR gate, merge queue, post-merge, nightly, release, docs; composite actions (`setup-qt`, `setup-vcpkg`, `setup-msvc-env`, `setup-emscripten`, `decide-runner`, `report-nightly-failure`, `save-vcpkg-cache`); CMake modules (`VcpkgRoot`, `FindQt6`, `Sanitizers`, `Tracy`, `Coverage`, `Warnings`, `Hardening`, `Platform`, `Translations`, `Notices`) with the project prefix as a parameter; triplets and toolchain files; check scripts (`check_no_preprocessor.py`, text policy, SPDX, pinning, fragment check, badge check, `plan_gate.py`, `precheck.py`); ruleset and label JSON; `apply.sh`.
3. Create the template repository `icl-cpp-template` (private is acceptable) that applies the layout in section 3 and wires the reusable workflows by SHA reference. Mark it as a template repository so `gh repo create --template` works.
4. Ask the owner to create the release bot GitHub App and the organisation secrets (section 17). Nothing else in this procedure needs them.
5. Version `icl-common-infra` with tags; consumers reference a tag by SHA; Dependabot bumps them.
6. Source material: copy from `iclforge` first (its `.github/`, `tools/ci/`, `tools/checks/`, `docs/ci-*.md`), then `aqualink-automate` and `cubeulator`; strip project names (`ICLFORGE_`, `cube::`, `ac3`).

### 16.2 MODE=new

1. Write the plan (rule 1). Collect `TODO(owner)` values.
2. Owner approves; create the repository from `icl-cpp-template`.
3. Fill project metadata: name, description, topics, licence headers, `AGENTS.md`, README badges.
4. Implement the first library and application skeleton with one unit, one integration, one system, and (for Qt) one UI test, so every CI leg has something to run.
5. Run every preset locally or in CI; fix until the PR gate and a nightly run are green.
6. Apply repository settings, rulesets and labels (section 12) after approval.
7. Write the release runbook and the secrets checklist (section 17) and hand them to the owner.
8. Walk the checklist in section 18.

### 16.3 MODE=migrate

M0. Inventory. Write the inventory as the first section of one document with the plan (M1), in a scratch location such as the session's scratchpad, from the legacy repository:
- size by language; build systems; compilers and language standard used; the last toolchain known to build it, and whether the build still reproduces in a container;
- dependencies, split into vendored, system and package-managed, with versions;
- preprocessor census: counts of `#ifdef`/`#if` by condition (`_WIN32`, `__linux__`, `DEBUG`, compiler checks, feature toggles) and of function-like macros;
- platform-API usage (Win32, MFC, POSIX, Cocoa, GTK, Qt 4/5, wxWidgets);
- licence and copyright holders per directory, including vendored code and contributions; anything GPL-incompatible is flagged for the owner;
- file encodings and line endings; 32-bit and endianness assumptions (`long`, `time_t`, `sizeof(void*)`, byte-order code);
- existing tests, test data, golden files and persisted file formats that users may hold;
- does the legacy code build today, and does it do what its description says when run? Record the first three errors if it does not. M3 depends on the answer.

M1. Plan. The second section of that document lists the modules in port order (leaves first), the replacement for each legacy dependency, the UI plan (legacy toolkit to Qt Quick), and the risks. The owner approves it there. After the repository exists (M2) it is committed as the first documentation pull request at `docs/migration.md`, and it is kept up to date until M7. There is no `migration/` directory.

M2. Repository switch (approval gate). When the legacy repository is in the same owner as the new one, it is renamed to `<name>.old` (Settings, General, or `gh repo rename`) and a new `<name>` is created from `icl-cpp-template`. When the legacy repository is in a different owner (for example a personal account against the organisation) the names do not clash: keep the legacy name, create the new repository, and archive the legacy one after M7. In both cases the legacy repository gets a README banner pointing at the new one. GitHub's redirect from the old name no longer applies once the new repository takes the name, so the plan lists external links to update (docs, package registries, badges, issue links). The `.old` repository keeps all history, issues and stars, gets a README banner pointing at the new repository, and is archived after M7. History is not copied into the new repository unless the owner asks for chosen subtrees (`git filter-repo`). The new README states provenance and links to `<name>.old`.

M3. Characterisation tests first. Build the legacy code at a pinned tag with its last good toolchain (container image definition kept under `tools/legacy-build/`). Record behaviour as golden data: outputs for representative inputs, file-format round trips, command-line results. These become `system` tests in the new repository. Where the legacy build cannot be reproduced, say so in the plan and base the tests on documented behaviour and sample files.

M4. Port module by module. For each module: copy, modernise using the table below, add unit tests, make the golden tests pass, pass the PR gate on all floor compilers, meet the coverage floor. Keep each module in its own pull request. Optionally, a nightly differential job builds the legacy tag and compares outputs with the new build on the same inputs (pattern: differential fuzzing in `iclforge`).

M5. Platform extraction. Every `#ifdef <platform>` block becomes an interface header plus one file per platform in `src/platform/<os>/`.

M6. UI. A legacy toolkit UI is rebuilt in Qt Quick. The legacy feature list becomes the UI test list (section 6.2); a feature is complete when its UI test passes.

M7. Localisation and RTL pass (section 7), documentation, release candidate, then the owner approves archiving `<name>.old`.

Modernisation table:

| Legacy | Replacement |
|---|---|
| include guards | `#pragma once` |
| `#define N 5` | `inline constexpr int N = 5;` (UPPER_SNAKE_CASE) |
| function-like macro | `constexpr` or `consteval` function, template, or lambda |
| `__FILE__`, `__LINE__` | `std::source_location` |
| `#ifdef _WIN32` / `__linux__` / `__APPLE__` code | `src/platform/<os>/` file chosen by CMake |
| `#ifdef DEBUG` / `NDEBUG` logic | `if constexpr` on a generated constant, or a runtime option |
| feature toggle macros | CMake picks the implementation directory, or a runtime setting |
| compiler workarounds and `__cplusplus` checks | delete |
| `#error` | `static_assert` |
| X-macro tables | `constexpr` tables, `magic_enum`, or `std::array` of structs |
| `int`/`long`/`unsigned` for sizes and fixed widths | `std::size_t`, `<cstdint>` types |
| hand-written byte swapping | `std::byteswap`, `std::endian` |
| raw owning pointers, `new`/`delete` | `std::unique_ptr`, containers, value types |
| `char*` plus length | `std::span`, `std::string_view` |
| error codes and `errno` style | `std::expected` at boundaries, exceptions only where already idiomatic |
| `printf`, iostream formatting | `std::format`, `std::print` |
| `pthread_*`, Win32 threads, hand-rolled locks | `std::jthread` and `std::stop_token` where available, otherwise `std::thread` with an RAII join; `std::mutex`, `std::atomic` |
| ANSI code pages and wide strings in logic | UTF-8 `std::string`; convert only in `src/platform/windows/` |
| custom containers and algorithms | the standard library, ranges |

The table is a default. Where the repository's own convention covers a row (naming above all), the convention stays and the plan says so.

## 17. Owner runbook and secrets

The agent never handles these values (rule 3). It writes `docs/releasing.md` with the exact steps and adds a `release-preflight` job that lists which of the names below are missing, so a release fails early with a clear message. Secrets are organisation-level where shared across projects (D16); an organisation secret is limited to the selected repositories that need it, and each release job runs in the repository's `release` environment so the owner approves it.

| Purpose | Names | Scope |
|---|---|---|
| GPG release signing | `REPO_GPG_PRIVATE_KEY`, `REPO_GPG_PASSPHRASE` | organisation |
| Android upload key | `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | organisation (one upload key for all apps; if an app needs its own key, a repository secret of the same name overrides it) |
| Apple distribution (D8) | `IOS_DIST_CERT_P12_BASE64`, `IOS_DIST_CERT_PASSWORD`, `APPSTORE_API_KEY_ID`, `APPSTORE_API_ISSUER_ID`, `APPSTORE_API_PRIVATE_KEY` | organisation |
| iOS per-app | `IOS_PROVISIONING_PROFILE_BASE64` (a profile is tied to one bundle identifier) | repository |
| macOS signing (D17, not yet purchased) | `MACOS_DEVID_CERT_P12_BASE64`, `MACOS_DEVID_CERT_PASSWORD`, `NOTARY_API_KEY_ID`, `NOTARY_API_ISSUER_ID`, `NOTARY_API_PRIVATE_KEY` | organisation |
| Windows test signing (D17) | `WIN_TESTSIGN_PFX_BASE64`, `WIN_TESTSIGN_PFX_PASSWORD` (leaf certificate from the personal CA, never the CA key) | organisation |
| Windows production signing (D17, not yet chosen) | depends on the chosen service (SignPath API token, Azure identity configuration, or a certificate and key) | organisation |
| Release bot | GitHub App ID and private key (`RELEASE_BOT_APP_ID`, `RELEASE_BOT_PRIVATE_KEY`) | organisation |
| Optional services | `SONAR_TOKEN`; a token for the self-hosted runner fleet | organisation |

Variables (not secrets), set per repository by `apply.sh`: `SIGN_WINDOWS` (`false`, `test` or `production`), `SIGN_MACOS` (`false` or `production`), `SIGN_IOS_UPLOAD`. All start as `false`, except that the owner may set `SIGN_WINDOWS` to `test` once the test certificate exists.

Owner tasks that cannot be automated: enrol in the Apple Developer Program, create bundle identifiers and the Play Console application, generate and back up the Android keystore and GPG key (offline copy), buy or apply for the Windows and macOS signing credentials when ready, create the release bot GitHub App, create the organisation secrets with repository access limited to the projects that need them, create the `release` environment in each repository, and run `apply.sh` after reviewing it.

## 18. Definition of done

A project is done when all of these hold:

1. Presets for every platform in section 10 configure and build; the PR gate and a full nightly run are green.
2. The compiler floor in D7 builds with warnings as errors. Portable libraries (3.1) also build with exceptions and RTTI off, pass the include check, and build with every embedded toolchain the project ships.
3. The no-preprocessor check passes: no platform or compiler conditionals at all, and the remaining directive count is at or below its recorded baseline with every allowlist line carrying a reason.
4. Coverage meets D6 (or the ratchet floor for migrated code) with UI test coverage included.
5. ASan/UBSan, TSan and fuzz-regress run in CI; nightly fuzz runs with corpus caching.
6. Tracy is on in `debug`, off in the sanitizer presets unless D4's condition is met, and switchable in release.
7. SIMD code has scalar references, tests, and a scalar-forced CI run.
8. All languages in D3 are present, complete and tested; right-to-left UI tests pass.
9. The About dialog shows licences; every bundle contains licences and `SOURCE.txt`.
10. A tagged release on a scratch tag produces `SHA512SUMS`, GPG signatures, an SPDX SBOM and attestations, with Windows and macOS artefacts either signed (`production`, or `test` for Windows) or named `-unsigned` or `-testsigned` according to the signing variables (variables `false`), the iOS archive exported, and `main` fast-forwarded by the release bot only on success. The release notes are not placeholder text.
11. Every `uses:` reference is SHA-pinned, the commit-text policy check is a required check, and a test commit with a trailer is rejected by the hook and by CI.
12. Docs build with `--strict` and deploy; the WebAssembly demo is published or the plan records why not.
13. README badges all resolve; repository description and topics are set.
14. Rulesets, merge queue, Dependabot, auto-merge, private vulnerability reporting, secret scanning and code scanning are applied and verified by a script that reads the settings back.
15. `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md` and `docs/releasing.md` exist and match the code.
16. For a migration: golden tests pass against the legacy behaviour, `<name>.old` carries the banner and is archived, and external links are updated.
