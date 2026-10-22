# SPDX-License-Identifier: GPL-3.0-or-later
# ---------------------------------------------------------------------------
# IclCoverage.cmake
#
# Defines the INTERFACE target icl::coverage. With ICL_ENABLE_COVERAGE on it adds
# gcov-style instrumentation (GCC, Clang) or LLVM source-based coverage
# (clang-cl). Link it PRIVATE into every first-party target whose coverage is
# measured. Compile options are target-scoped, so a consumer's own sources need
# the link too, otherwise gcovr finds no .gcno files for them.
#
# Vendored third-party code is left uninstrumented on purpose.
# Reports come from gcovr (see scripts/coverage_report.sh); the gate is 90%
# statement and 80% branch coverage.
# ---------------------------------------------------------------------------

include_guard(GLOBAL)

option(ICL_ENABLE_COVERAGE "Enable source coverage instrumentation" OFF)

add_library(icl_coverage INTERFACE)
add_library(icl::coverage ALIAS icl_coverage)

if(NOT ICL_ENABLE_COVERAGE)
    return()
endif()

if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_COMPILER_FRONTEND_VARIANT STREQUAL "MSVC")
    target_compile_options(icl_coverage INTERFACE -fprofile-instr-generate -fcoverage-mapping /Od /Ob0)
    execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" -print-resource-dir
        OUTPUT_VARIABLE _icl_clang_resource_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET)
    file(TO_CMAKE_PATH "${_icl_clang_resource_dir}" _icl_clang_resource_dir)
    find_library(ICL_CLANG_PROFILE_RUNTIME
        NAMES clang_rt.profile-x86_64 clang_rt.profile-aarch64
        PATHS "${_icl_clang_resource_dir}/lib/windows"
        NO_DEFAULT_PATH)
    if(NOT ICL_CLANG_PROFILE_RUNTIME)
        message(FATAL_ERROR
            "ICL_ENABLE_COVERAGE with clang-cl needs clang_rt.profile-*.lib under "
            "${_icl_clang_resource_dir}/lib/windows; it was not found.")
    endif()
    target_link_libraries(icl_coverage INTERFACE "${ICL_CLANG_PROFILE_RUNTIME}")
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    target_compile_options(icl_coverage INTERFACE --coverage -fno-inline)
    target_link_options(icl_coverage INTERFACE --coverage)
else()
    message(FATAL_ERROR
        "ICL_ENABLE_COVERAGE is on but ${CMAKE_CXX_COMPILER_ID} has no supported coverage instrumentation.")
endif()
