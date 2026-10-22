# SPDX-License-Identifier: GPL-3.0-or-later
# ---------------------------------------------------------------------------
# IclSanitizers.cmake
#
# ICL_SANITIZERS is a comma-separated -fsanitize= value applied to every target
# through global compile and link options. Empty (the default) changes nothing.
#
#   address,undefined   ASan + UBSan (Clang, GCC). MSVC supports address only.
#   thread              TSan (Clang, GCC). Cannot be combined with address.
#
# Sanitizer builds are optimised at -O1 (/O1 on MSVC) so stack traces stay
# readable and the run time stays practical. -fno-sanitize-recover=all makes
# the first violation fail the run.
#
# Conflicts that stop the configure:
#   ICL_SANITIZERS with ICL_ENABLE_TRACY     (Tracy is incompatible with sanitizer runtimes)
#   ICL_SANITIZERS with ICL_ENABLE_COVERAGE  (instrumentation overhead and noise)
#   ICL_SANITIZERS with ICL_ENABLE_FUZZING   (libFuzzer already enables ASan on fuzz targets)
# ---------------------------------------------------------------------------

include_guard(GLOBAL)

set(ICL_SANITIZERS "" CACHE STRING "Comma-separated -fsanitize= value, for example address,undefined or thread")

if(NOT ICL_SANITIZERS)
    return()
endif()

foreach(_icl_other IN ITEMS TRACY COVERAGE FUZZING)
    if(ICL_ENABLE_${_icl_other})
        message(FATAL_ERROR
            "ICL_SANITIZERS='${ICL_SANITIZERS}' and ICL_ENABLE_${_icl_other} cannot both be on. "
            "Use separate presets.")
    endif()
endforeach()

string(REPLACE "," ";" _icl_san_list "${ICL_SANITIZERS}")

if("thread" IN_LIST _icl_san_list AND "address" IN_LIST _icl_san_list)
    message(FATAL_ERROR "ICL_SANITIZERS cannot combine 'thread' and 'address'. Use separate presets.")
endif()

if(MSVC AND NOT CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    foreach(_icl_san IN LISTS _icl_san_list)
        if(NOT _icl_san STREQUAL "address")
            message(FATAL_ERROR
                "MSVC supports only the 'address' sanitizer; ICL_SANITIZERS contains '${_icl_san}'. "
                "Run undefined and thread on the Linux presets.")
        endif()
    endforeach()
    add_compile_options(/fsanitize=address /O1 /Zi)
    # /fsanitize=address enables STL container annotations in our objects. Libraries built
    # without ASan (vcpkg packages such as Catch2) do not carry them, and the linker rejects
    # the mix with LNK2038. Disable the annotations so both sides agree.
    add_compile_definitions(
        _DISABLE_STRING_ANNOTATION
        _DISABLE_VECTOR_ANNOTATION
        _DISABLE_OPTIONAL_ANNOTATION)
    # /fsanitize=address is incompatible with /RTC and incremental linking.
    add_link_options(/INCREMENTAL:NO)
    string(REGEX REPLACE "/RTC[1csu]+" "" CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG}")
elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang|AppleClang")
    set(_icl_san_flags
        "-fsanitize=${ICL_SANITIZERS}"
        -fno-sanitize-recover=all
        -fno-omit-frame-pointer
        -O1)
    add_compile_options(${_icl_san_flags})
    add_link_options("-fsanitize=${ICL_SANITIZERS}")
    unset(_icl_san_flags)
else()
    message(FATAL_ERROR
        "ICL_SANITIZERS='${ICL_SANITIZERS}' is not supported by ${CMAKE_CXX_COMPILER_ID}.")
endif()

message(STATUS "Sanitizers enabled: ${ICL_SANITIZERS}")
unset(_icl_san_list)
