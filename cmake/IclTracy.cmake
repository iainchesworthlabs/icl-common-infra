# SPDX-License-Identifier: GPL-3.0-or-later
# ---------------------------------------------------------------------------
# IclTracy.cmake
#
# Defines the INTERFACE target icl::tracy. With ICL_ENABLE_TRACY on it links
# Tracy's client (from vcpkg) and defines TRACY_ENABLE, TRACY_ON_DEMAND and
# TRACY_ONLY_LOCALHOST, so nothing is sent until a profiler connects and nothing
# leaves the machine. With it off the target is empty and Tracy need not be
# installed.
#
# Presets turn ICL_ENABLE_TRACY on for Debug and off for sanitizer, coverage and
# fuzz builds (those configures fail if both are on; see IclSanitizers.cmake).
# A Release build can opt in with -DICL_ENABLE_TRACY=ON.
#
# Platforms without a socket-based Tracy client (WebAssembly, iOS) use the
# in-process recorder instead: set ICL_TRACY_IN_PROCESS=ON and provide the
# recorder through the project's own ProfileRecorder module.
# ---------------------------------------------------------------------------

include_guard(GLOBAL)

option(ICL_ENABLE_TRACY "Enable Tracy profiler instrumentation" OFF)
option(ICL_TRACY_IN_PROCESS "Use the in-process recorder instead of the Tracy client" OFF)

add_library(icl_tracy INTERFACE)
add_library(icl::tracy ALIAS icl_tracy)

if(ICL_ENABLE_TRACY AND NOT ICL_TRACY_IN_PROCESS)
    find_package(Tracy CONFIG REQUIRED)
    target_link_libraries(icl_tracy INTERFACE Tracy::TracyClient)
    target_compile_definitions(icl_tracy INTERFACE
        TRACY_ENABLE TRACY_ON_DEMAND TRACY_ONLY_LOCALHOST)
endif()
