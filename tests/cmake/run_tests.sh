#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Smoke tests for the CMake modules. Needs cmake and a C++ compiler.
set -euo pipefail

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
echo "all CMake module tests passed"
