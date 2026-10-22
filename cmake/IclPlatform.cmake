# SPDX-License-Identifier: GPL-3.0-or-later
# ---------------------------------------------------------------------------
# IclPlatform.cmake
#
# CMake chooses which files to compile for a platform. Source code contains no
# platform conditionals (the CI preprocessor check enforces this).
#
#   icl_platform_sources(<target> [DIR <dir>])
#
# adds the *.cpp files in <dir>/<os>/ to <target>, where <os> is one of
# windows, macos, linux, ios, android, wasm. DIR defaults to
# ${CMAKE_CURRENT_SOURCE_DIR}/src/platform. Every platform directory must
# implement the same declarations from the same header, so the target links on
# every platform or fails on the first one that is missing something.
#
#   ICL_PLATFORM            windows | macos | linux | ios | android | wasm
# ---------------------------------------------------------------------------

include_guard(GLOBAL)

if(EMSCRIPTEN)
    set(ICL_PLATFORM wasm)
elseif(ANDROID)
    set(ICL_PLATFORM android)
elseif(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    set(ICL_PLATFORM ios)
elseif(APPLE)
    set(ICL_PLATFORM macos)
elseif(WIN32)
    set(ICL_PLATFORM windows)
elseif(UNIX)
    set(ICL_PLATFORM linux)
else()
    message(FATAL_ERROR "IclPlatform: unsupported system ${CMAKE_SYSTEM_NAME}")
endif()

function(icl_platform_sources target)
    cmake_parse_arguments(ARG "" "DIR" "" ${ARGN})
    if(NOT ARG_DIR)
        set(ARG_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/platform")
    endif()
    set(platform_dir "${ARG_DIR}/${ICL_PLATFORM}")
    file(GLOB platform_files CONFIGURE_DEPENDS "${platform_dir}/*.cpp" "${platform_dir}/*.mm")
    if(NOT platform_files)
        message(FATAL_ERROR "icl_platform_sources(${target}): no sources in ${platform_dir}")
    endif()
    target_sources(${target} PRIVATE ${platform_files})
endfunction()
