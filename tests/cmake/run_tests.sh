#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke tests for the CMake modules. Needs cmake and a C++ compiler.
set -euo pipefail

# The modules read these; a developer machine that sets them would change the result.
unset ICL_VCPKG_STORE ICL_VCPKG_MIRROR ICL_QT_ROOT QT_ROOT_DIR QTDIR VCPKG_ROOT

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
modules="$(cd "$here/../../cmake" && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "pass  $*"; }

# --- IclVcpkgRoot -----------------------------------------------------------
mkdir -p "$work/fake/scripts/buildsystems" && touch "$work/fake/scripts/buildsystems/vcpkg.cmake"
mkdir -p "$work/vcpkg-proj"
cat > "$work/vcpkg-proj/CMakeLists.txt" <<CM
cmake_minimum_required(VERSION 3.25)
list(APPEND CMAKE_MODULE_PATH "$modules")
include(IclVcpkgRoot)
icl_resolve_vcpkg("\${CMAKE_SOURCE_DIR}" DEMO)
project(demo NONE)
message(STATUS "TOOLCHAIN=\${CMAKE_TOOLCHAIN_FILE}")
CM
out="$(DEMO_VCPKG_ROOT="$work/fake" cmake -S "$work/vcpkg-proj" -B "$work/b1" 2>&1)"
echo "$out" | grep -q "TOOLCHAIN=$work/fake/scripts/buildsystems/vcpkg.cmake" || fail "project vcpkg root"
pass "vcpkg: <P>_VCPKG_ROOT"
out="$(VCPKG_ROOT="$work/fake" cmake -S "$work/vcpkg-proj" -B "$work/b2" 2>&1)"
echo "$out" | grep -q "TOOLCHAIN=$work/fake" || fail "VCPKG_ROOT"
pass "vcpkg: VCPKG_ROOT"
if cmake -S "$work/vcpkg-proj" -B "$work/b3" -DVCPKG_TARGET_TRIPLET=x64-linux >/dev/null 2>&1; then fail "missing vcpkg should stop the configure"; fi
pass "vcpkg: stops when none is set and a triplet asks for it"

# --- FindQt6 ----------------------------------------------------------------
mkdir -p "$work/qt/6.12.0/gcc_64/lib/cmake/Qt6" "$work/qt2/6.12.0/gcc_64/lib/cmake/Qt6"
echo 'set(Qt6_FOUND TRUE)' | tee "$work/qt/6.12.0/gcc_64/lib/cmake/Qt6/Qt6Config.cmake" > "$work/qt2/6.12.0/gcc_64/lib/cmake/Qt6/Qt6Config.cmake"
mkdir -p "$work/qt-proj"
cat > "$work/qt-proj/CMakeLists.txt" <<CM
cmake_minimum_required(VERSION 3.25)
project(t NONE)
list(APPEND CMAKE_MODULE_PATH "$modules")
set(ICL_PROJECT_PREFIX DEMO)
find_package(Qt6 REQUIRED)
CM
out="$(ICL_QT_ROOT="$work/qt" cmake -S "$work/qt-proj" -B "$work/q1" 2>&1)"
echo "$out" | grep -q "auto-detected prebuilt Qt6 at $work/qt/" || fail "ICL_QT_ROOT"
pass "qt: ICL_QT_ROOT"
out="$(DEMO_QT_ROOT="$work/qt2" ICL_QT_ROOT="$work/qt" cmake -S "$work/qt-proj" -B "$work/q2" 2>&1)"
echo "$out" | grep -q "auto-detected prebuilt Qt6 at $work/qt2/" || fail "project root should win"
pass "qt: <P>_QT_ROOT beats ICL_QT_ROOT"
if DEMO_QT_ROOT=/nonexistent cmake -S "$work/qt-proj" -B "$work/q3" >/dev/null 2>&1; then fail "bad root should fail"; fi
pass "qt: a root with no kit is an error"

# --- build options ----------------------------------------------------------
mkdir -p "$work/opt/src/platform/linux"
echo 'int platform_value() { return 1; }' > "$work/opt/src/platform/linux/p.cpp"
echo 'int platform_value(); int main() { return platform_value() - 1; }' > "$work/opt/main.cpp"
cat > "$work/opt/CMakeLists.txt" <<CM
cmake_minimum_required(VERSION 3.25)
project(t CXX)
list(APPEND CMAKE_MODULE_PATH "$modules")
include(IclSanitizers)
include(IclWarnings)
include(IclHardening)
include(IclTracy)
include(IclCoverage)
include(IclPlatform)
add_executable(t main.cpp)
icl_platform_sources(t)
target_link_libraries(t PRIVATE icl::warnings icl::hardening icl::tracy icl::coverage)
CM
for opt in "-DICL_SANITIZERS=address,undefined" "-DICL_SANITIZERS=thread" "-DICL_ENABLE_COVERAGE=ON" ""; do
  d="$work/o-$(echo "$opt" | tr -c 'A-Za-z' _)"
  cmake -S "$work/opt" -B "$d" -DCMAKE_BUILD_TYPE=Release $opt >/dev/null
  cmake --build "$d" >/dev/null
  "$d/t" || fail "run with '$opt'"
  pass "build and run: ${opt:-defaults}"
done
if cmake -S "$work/opt" -B "$work/c1" -DICL_SANITIZERS=thread -DICL_ENABLE_TRACY=ON >/dev/null 2>&1; then fail "sanitizer + tracy"; fi
pass "sanitizers and Tracy cannot be combined"
if cmake -S "$work/opt" -B "$work/c2" -DICL_SANITIZERS=thread,address >/dev/null 2>&1; then fail "thread + address"; fi
pass "thread and address cannot be combined"
# --- generated sources ------------------------------------------------------
mkdir -p "$work/gen"
echo 'int gen(); int main() { return gen(); }' > "$work/gen/main.cpp"
for relax in ON OFF; do
  cat > "$work/gen/CMakeLists.txt" <<CM
cmake_minimum_required(VERSION 3.25)
project(t CXX)
list(APPEND CMAKE_MODULE_PATH "$modules")
include(IclWarnings)
file(WRITE "\${CMAKE_CURRENT_BINARY_DIR}/gen.cpp" "int gen() { int unused_value = 1; return 0; }\n")
add_executable(t main.cpp "\${CMAKE_CURRENT_BINARY_DIR}/gen.cpp")
target_link_libraries(t PRIVATE icl::warnings)
if("$relax")
  icl_relax_generated_warnings(t)
endif()
CM
  d="$work/gen-$relax"
  cmake -S "$work/gen" -B "$d" >/dev/null
  if [ "$relax" = ON ]; then
    cmake --build "$d" >/dev/null 2>&1 || fail "generated source should build once relaxed"
    pass "warnings: generated sources compile when relaxed"
  else
    if cmake --build "$d" >/dev/null 2>&1; then fail "generated source should fail the strict set"; fi
    pass "warnings: generated sources fail the strict set otherwise"
  fi
done
# --- notices, source information and the Qt application install -----------------
# A stand-in for Qt's deploy command: the real one needs a Qt kit. It puts a plugin and the debugging
# plugin directory where Qt would, so the removal of qmltooling can be checked.
mkdir -p "$work/qtapp/vcpkg/share/zlib" "$work/qtapp/vcpkg/share/catch2" "$work/qtapp/LICENSES"
echo "zlib licence text" > "$work/qtapp/vcpkg/share/zlib/copyright"
echo "catch2 licence text" > "$work/qtapp/vcpkg/share/catch2/copyright"
echo "GPL text" > "$work/qtapp/LICENSE"
echo "GPL text" > "$work/qtapp/LICENSES/GPL-3.0-or-later.txt"
echo 'int main() { return 0; }' > "$work/qtapp/main.cpp"
cat > "$work/qtapp/vcpkg.json" <<JSON
{ "name": "demo", "version": "1.2.3",
  "dependencies": [ "zlib", "catch2", { "name": "vcpkg-cmake", "host": true }, { "name": "fmt", "platform": "!windows" } ] }
JSON
mkdir -p "$work/qtapp/vcpkg/share/fmt" && echo "fmt licence text" > "$work/qtapp/vcpkg/share/fmt/copyright"
cat > "$work/qtapp/CMakeLists.txt" <<CM
cmake_minimum_required(VERSION 3.25)
project(demo VERSION 1.2.3 HOMEPAGE_URL "https://example.org/demo" LANGUAGES CXX)
list(APPEND CMAKE_MODULE_PATH "$modules")
set(Qt6_VERSION 6.12.0)
function(qt_generate_deploy_qml_app_script)
    cmake_parse_arguments(A "NO_UNSUPPORTED_PLATFORM_ERROR;NO_TRANSLATIONS" "TARGET;OUTPUT_SCRIPT" "" \${ARGN})
    set(\${A_OUTPUT_SCRIPT} "\${CMAKE_CURRENT_BINARY_DIR}/fake_deploy.cmake" PARENT_SCOPE)
    file(WRITE "\${CMAKE_CURRENT_BINARY_DIR}/fake_deploy.cmake" "
        file(MAKE_DIRECTORY \"\\\$ENV{DESTDIR}\\\${CMAKE_INSTALL_PREFIX}/plugins/platforms\"
                            \"\\\$ENV{DESTDIR}\\\${CMAKE_INSTALL_PREFIX}/plugins/qmltooling\")
        file(WRITE \"\\\$ENV{DESTDIR}\\\${CMAKE_INSTALL_PREFIX}/plugins/platforms/libq.so\" x)
        file(WRITE \"\\\$ENV{DESTDIR}\\\${CMAKE_INSTALL_PREFIX}/plugins/qmltooling/libdbg.so\" x)")
endfunction()
include(IclQtApp)
add_executable(app main.cpp)
set_target_properties(app PROPERTIES OUTPUT_NAME demo)
icl_install_qt_app(app BUNDLE_IDENTIFIER org.example.demo DISPLAY_NAME Demo
    NOTICE_EXCLUDE catch2)
CM
git -C "$work/qtapp" init -q && git -C "$work/qtapp" -c user.name=t -c user.email=t@example.org add -A \
  && git -C "$work/qtapp" -c user.name=t -c user.email=t@example.org commit -q -m init
commit="$(git -C "$work/qtapp" rev-parse HEAD)"
cmake -S "$work/qtapp" -B "$work/qtapp-b" -DVCPKG_INSTALLED_DIR="$work/qtapp" -DVCPKG_TARGET_TRIPLET=vcpkg >/dev/null \
  || fail "qt app: configure"
cmake --build "$work/qtapp-b" >/dev/null || fail "qt app: build"
cmake --install "$work/qtapp-b" --prefix "$work/qtapp-i" >/dev/null || fail "qt app: install"
doc="$work/qtapp-i/share/doc/demo"
for f in LICENSE LICENSES/GPL-3.0-or-later.txt THIRD-PARTY-NOTICES.txt SOURCE.txt; do
  test -f "$doc/$f" || fail "qt app: $f is not installed"
done
test -x "$work/qtapp-i/bin/demo" || fail "qt app: program is not installed"
test -f "$work/qtapp-i/plugins/platforms/libq.so" || fail "qt app: deployed plugins must stay"
test ! -e "$work/qtapp-i/plugins/qmltooling" || fail "qt app: qmltooling must be removed"
pass "qt app: install layout, licence files, qmltooling removed"
grep -q "zlib licence text" "$doc/THIRD-PARTY-NOTICES.txt" || fail "notices: zlib"
grep -q "fmt licence text" "$doc/THIRD-PARTY-NOTICES.txt" || fail "notices: fmt"
if grep -q "catch2 licence text" "$doc/THIRD-PARTY-NOTICES.txt"; then fail "notices: excluded package present"; fi
if grep -q "vcpkg-cmake" "$doc/THIRD-PARTY-NOTICES.txt"; then fail "notices: host package present"; fi
grep -q "Qt 6.12.0" "$doc/THIRD-PARTY-NOTICES.txt" || fail "notices: Qt entry"
grep -q "qt-everywhere-src-6.12.0.tar.xz" "$doc/THIRD-PARTY-NOTICES.txt" || fail "notices: Qt source link"
pass "notices: runtime dependencies, Qt; no test or host packages"
grep -q "^Commit: $commit\$" "$doc/SOURCE.txt" || fail "source info: commit"
grep -q "^Demo 1.2.3\$" "$doc/SOURCE.txt" || fail "source info: name and version"
grep -q "https://download.qt.io/official_releases/qt/6.12/6.12.0/single/" "$doc/SOURCE.txt" || fail "source info: Qt source"
pass "source info: commit, version and Qt source"
cmake -S "$work/qtapp" -B "$work/qtapp-b" -DVCPKG_INSTALLED_DIR="$work/qtapp" -DVCPKG_TARGET_TRIPLET=vcpkg >/dev/null
cmake --install "$work/qtapp-b" --prefix "$work/qtapp-i2" >/dev/null
rm -rf "$work/qtapp/.git"
GITHUB_SHA=abc123 cmake --install "$work/qtapp-b" --prefix "$work/qtapp-i3" >/dev/null
grep -q "^Commit: abc123\$" "$work/qtapp-i3/share/doc/demo/SOURCE.txt" || fail "source info: GITHUB_SHA fallback"
(unset GITHUB_SHA; cmake --install "$work/qtapp-b" --prefix "$work/qtapp-i4" >/dev/null)
grep -q "^Commit: unknown\$" "$work/qtapp-i4/share/doc/demo/SOURCE.txt" || fail "source info: unknown"
pass "source info: GITHUB_SHA, then unknown"
rm "$work/qtapp/vcpkg/share/zlib/copyright"
if cmake -S "$work/qtapp" -B "$work/qtapp-b2" -DVCPKG_INSTALLED_DIR="$work/qtapp" -DVCPKG_TARGET_TRIPLET=vcpkg >"$work/missing.log" 2>&1; then
  fail "notices: a package with no licence file must stop the configure"
fi
tr '\n' ' ' < "$work/missing.log" | grep -q "no licence file.*zlib" || fail "notices: the error names the package"
pass "notices: a dependency with no licence file stops the configure"
mkdir -p "$work/noid" && cat > "$work/noid/CMakeLists.txt" <<CM
cmake_minimum_required(VERSION 3.25)
project(d VERSION 1.0 LANGUAGES CXX)
list(APPEND CMAKE_MODULE_PATH "$modules")
include(IclQtApp)
add_executable(app main.cpp)
icl_install_qt_app(app)
CM
echo 'int main() { return 0; }' > "$work/noid/main.cpp"
if cmake -S "$work/noid" -B "$work/noid-b" >/dev/null 2>&1; then fail "qt app: BUNDLE_IDENTIFIER is required"; fi
pass "qt app: BUNDLE_IDENTIFIER is required"
echo "all CMake module tests passed"
