# SPDX-License-Identifier: GPL-3.0-or-later
# ---------------------------------------------------------------------------
# IclHardening.cmake
#
# Defines the INTERFACE target icl::hardening: compiler and linker options that
# make memory-safety bugs harder to exploit. Link it PRIVATE into every
# first-party target that ships. Options that a platform lacks are skipped.
#
#   GCC / Clang   stack protector, _FORTIFY_SOURCE=3 (optimised builds only),
#                 relro + now, position-independent code, control-flow protection
#                 on x86 where the compiler has it
#   MSVC          /GS, /guard:cf, /sdl, /DYNAMICBASE, /NXCOMPAT, /CETCOMPAT
# ---------------------------------------------------------------------------

include_guard(GLOBAL)

include(CheckCXXCompilerFlag)

add_library(icl_hardening INTERFACE)
add_library(icl::hardening ALIAS icl_hardening)

if(MSVC AND NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    target_compile_options(icl_hardening INTERFACE /GS /guard:cf /sdl)
    target_link_options(icl_hardening INTERFACE /GUARD:CF /DYNAMICBASE /NXCOMPAT /CETCOMPAT)
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    target_compile_options(icl_hardening INTERFACE
        -fstack-protector-strong
        "$<$<NOT:$<CONFIG:Debug>>:-U_FORTIFY_SOURCE>"
        "$<$<NOT:$<CONFIG:Debug>>:-D_FORTIFY_SOURCE=3>")
    check_cxx_compiler_flag(-fcf-protection=full ICL_HAS_CF_PROTECTION)
    if(ICL_HAS_CF_PROTECTION AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64|i[3-6]86")
        target_compile_options(icl_hardening INTERFACE -fcf-protection=full)
    endif()
    if(NOT APPLE AND NOT WIN32)
        target_link_options(icl_hardening INTERFACE -Wl,-z,relro,-z,now)
    endif()
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()
