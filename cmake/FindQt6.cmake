# SPDX-License-Identifier: GPL-3.0-or-later
# ---------------------------------------------------------------------------
# FindQt6.cmake - wrapper picked up automatically by find_package(Qt6 ...)
# because this directory is on CMAKE_MODULE_PATH (CMake tries Module mode, a
# Find<Pkg>.cmake, before Config mode).
#
# It never replaces Qt6Config.cmake. It widens CMAKE_PREFIX_PATH with the
# standard prebuilt-Qt install layouts when Qt6 is not already discoverable,
# then defers to Qt's own config package.
#
# Set ICL_PROJECT_PREFIX (for example MYPROJECT) before find_package so the
# project-specific variable <P>_QT_ROOT is honoured.
#
# Precedence, highest first:
#   1. -DCMAKE_PREFIX_PATH=... / -DQt6_DIR=... / -DQt6_ROOT=..., which the plain
#      find_package below honours, so this module never gets a say;
#   2. <P>_QT_ROOT (CMake variable or environment), then ICL_QT_ROOT (the shared
#      per-machine setting, for example C:/repos/common). A value that holds no
#      kit is an error;
#   3. QT_ROOT_DIR or QTDIR in the environment (QT_ROOT_DIR is what aqtinstall
#      and install-qt-action export). A miss here falls through;
#   4. the per-platform default install roots, newest version first.
#
# Qt is never a vcpkg dependency. A machine with no Qt kit builds everything
# else with the project's GUI option off; the error at the bottom says so.
# ---------------------------------------------------------------------------

set(ICL_QT_ROOT "" CACHE PATH
    "Prebuilt Qt6 kit (for example C:/repos/common/6.12.0/msvc2022_64) or Qt install root")
if(ICL_PROJECT_PREFIX)
    set(${ICL_PROJECT_PREFIX}_QT_ROOT "" CACHE PATH "Prebuilt Qt6 kit or Qt install root for this project")
    set(_qt6_pfx_root "${${ICL_PROJECT_PREFIX}_QT_ROOT}")
    set(_qt6_pfx_env "$ENV{${ICL_PROJECT_PREFIX}_QT_ROOT}")
else()
    set(_qt6_pfx_root "")
    set(_qt6_pfx_env "")
endif()
set(_qt6_pfx_name "${ICL_PROJECT_PREFIX}_QT_ROOT")

# Respect anything the caller already pointed CMake at.
find_package(Qt6 ${Qt6_FIND_VERSION} CONFIG QUIET COMPONENTS ${Qt6_FIND_COMPONENTS})

if(NOT Qt6_FOUND)
    # Search roots, highest priority first. Each entry is paired with a label
    # so a failure can say where the path came from rather than just listing
    # directories the reader has to recognise.
    set(_qt6_roots "")
    set(_qt6_root_labels "")

    # <P>_QT_ROOT and ICL_QT_ROOT are deliberate settings, so a value that
    # yields no kit is an error rather than a cue to look elsewhere.
    # QT_ROOT_DIR and QTDIR are shared with the rest of the Qt world and are
    # routinely left stale in a shell profile, so a miss on those falls through.
    if(_qt6_pfx_root)
        list(APPEND _qt6_roots "${_qt6_pfx_root}")
        list(APPEND _qt6_root_labels "from -D${_qt6_pfx_name}")
    endif()
    if(NOT "${_qt6_pfx_env}" STREQUAL "")
        list(APPEND _qt6_roots "${_qt6_pfx_env}")
        list(APPEND _qt6_root_labels "from the ${_qt6_pfx_name} environment variable")
    endif()
    if(ICL_QT_ROOT)
        list(APPEND _qt6_roots "${ICL_QT_ROOT}")
        list(APPEND _qt6_root_labels "from -DICL_QT_ROOT")
    endif()
    if(NOT "$ENV{ICL_QT_ROOT}" STREQUAL "")
        list(APPEND _qt6_roots "$ENV{ICL_QT_ROOT}")
        list(APPEND _qt6_root_labels "from the ICL_QT_ROOT environment variable")
    endif()
    list(LENGTH _qt6_roots _qt6_strict_count)

    foreach(_qt6_env IN ITEMS QT_ROOT_DIR QTDIR)
        if(NOT "$ENV{${_qt6_env}}" STREQUAL "")
            list(APPEND _qt6_roots "$ENV{${_qt6_env}}")
            list(APPEND _qt6_root_labels "from the ${_qt6_env} environment variable")
        endif()
    endforeach()
    list(LENGTH _qt6_roots _qt6_hint_count)

    # Kit directory names are an allow-list, never a glob: an official Qt
    # install also holds android_*, ios and wasm_* kits that a glob would
    # happily pick and that would then fail at link time. Only 64-bit desktop
    # kits belong here, newest toolchain first.
    if(WIN32)
        set(_qt6_default_roots "C:/Qt" "$ENV{USERPROFILE}/Qt" "D:/Qt")
        set(_qt6_arch_dirs "msvc2022_64" "msvc2019_64" "mingw_64" "llvm-mingw_64")
        set(_qt6_arm_arch_dirs "msvc2022_arm64")
        set(_qt6_example "C:/Qt/6.12.0/msvc2022_64")
    elseif(APPLE)
        # The "macos" kit is a universal binary, so one name serves both Intel
        # and Apple silicon; "clang_64" is the Qt 6.1-and-earlier spelling.
        # The Homebrew and MacPorts prefixes below are Qt prefixes in their own
        # right and are caught by the root-is-a-prefix test in the loop.
        set(_qt6_default_roots
            "$ENV{HOME}/Qt" "/opt/Qt" "/usr/local/Qt"
            "/opt/homebrew/opt/qt" "/opt/homebrew/opt/qt6"
            "/usr/local/opt/qt" "/usr/local/opt/qt6"
            "/opt/local/libexec/qt6")
        set(_qt6_arch_dirs "macos" "clang_64")
        set(_qt6_arm_arch_dirs "")
        set(_qt6_example "$ENV{HOME}/Qt/6.12.0/macos")
    else()
        # Distro packages (apt's qt6-base-dev, Fedora's qt6-qtbase-devel) land
        # on CMake's own default prefixes, so the plain find_package above
        # already finds them. These roots are for relocated or hand-installed
        # kits, which is what the official installer and aqtinstall produce.
        set(_qt6_default_roots
            "$ENV{HOME}/Qt" "/opt/Qt" "/usr/local/Qt"
            "/usr/lib/qt6" "/usr/lib64/qt6" "/usr/lib/x86_64-linux-gnu/qt6")
        set(_qt6_arch_dirs "gcc_64" "linux_gcc_64")
        set(_qt6_arm_arch_dirs "linux_gcc_arm64" "gcc_arm64")
        set(_qt6_example "$ENV{HOME}/Qt/6.12.0/gcc_64")
    endif()

    if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64|ARM64)$" AND _qt6_arm_arch_dirs)
        list(PREPEND _qt6_arch_dirs ${_qt6_arm_arch_dirs})
    endif()

    foreach(_qt6_root IN LISTS _qt6_default_roots)
        list(APPEND _qt6_roots "${_qt6_root}")
        list(APPEND _qt6_root_labels "default location")
    endforeach()

    # Roots are consulted in order and the first that yields a kit wins, so an
    # explicit hint always beats a newer kit found in a default location.
    set(_qt6_candidates "")
    set(_qt6_report "")
    set(_qt6_index 0)
    foreach(_qt6_root IN LISTS _qt6_roots)
        list(GET _qt6_root_labels ${_qt6_index} _qt6_label)
        math(EXPR _qt6_index "${_qt6_index} + 1")

        if(NOT _qt6_root)
            continue()
        endif()
        if(NOT IS_DIRECTORY "${_qt6_root}")
            string(APPEND _qt6_report "    ${_qt6_root}  [${_qt6_label}] - no such directory\n")
            continue()
        endif()
        string(APPEND _qt6_report "    ${_qt6_root}  [${_qt6_label}]\n")

        # The root may be a Qt prefix itself: a relocated install, a Homebrew
        # or MacPorts prefix, or a hint aimed straight at one kit. lib64 is
        # where Fedora and openSUSE put the 64-bit package files.
        foreach(_qt6_libdir IN ITEMS lib lib64)
            if(EXISTS "${_qt6_root}/${_qt6_libdir}/cmake/Qt6/Qt6Config.cmake")
                list(APPEND _qt6_candidates "${_qt6_root}")
            endif()
        endforeach()
        # ... or a hint copied out of Qt6_DIR, which names the config dir.
        if(EXISTS "${_qt6_root}/Qt6Config.cmake")
            list(APPEND _qt6_candidates "${_qt6_root}")
        endif()

        # Official installer / aqtinstall layout: <root>/<version>/<kit>/.
        file(GLOB _qt6_version_dirs LIST_DIRECTORIES true "${_qt6_root}/6.*")
        list(SORT _qt6_version_dirs COMPARE NATURAL ORDER DESCENDING)
        foreach(_qt6_version_dir IN LISTS _qt6_version_dirs)
            if(NOT IS_DIRECTORY "${_qt6_version_dir}")
                continue()
            endif()
            foreach(_qt6_arch IN LISTS _qt6_arch_dirs)
                if(EXISTS "${_qt6_version_dir}/${_qt6_arch}/lib/cmake/Qt6/Qt6Config.cmake")
                    list(APPEND _qt6_candidates "${_qt6_version_dir}/${_qt6_arch}")
                endif()
            endforeach()
        endforeach()

        if(_qt6_candidates)
            break()
        endif()
    endforeach()

    # _qt6_index is one past the root that matched, and the strict roots are
    # the first _qt6_strict_count entries.
    if(_qt6_strict_count GREATER 0 AND _qt6_index GREATER _qt6_strict_count)
        list(SUBLIST _qt6_roots 0 ${_qt6_strict_count} _qt6_strict_roots)
        string(REPLACE ";" "\n    " _qt6_strict_text "${_qt6_strict_roots}")
        message(FATAL_ERROR
            "A Qt root setting (${_qt6_pfx_name} or ICL_QT_ROOT) holds no Qt6 kit:\n"
            "    ${_qt6_strict_text}\n"
            "Expected lib/cmake/Qt6/Qt6Config.cmake under it, or a 6.x/<kit>/ "
            "subdirectory containing one. Point it at a kit such as "
            "${_qt6_example}, at the install root above the version "
            "directories, or unset it to search the default locations.\n")
    endif()

    if(_qt6_candidates)
        list(GET _qt6_candidates 0 _qt6_chosen)

        message(STATUS "FindQt6: auto-detected prebuilt Qt6 at ${_qt6_chosen} (pass -DICL_QT_ROOT to override)")
        list(APPEND CMAKE_PREFIX_PATH "${_qt6_chosen}")

        set(_qt6_args CONFIG)
        if(Qt6_FIND_QUIETLY)
            list(APPEND _qt6_args QUIET)
        endif()
        if(Qt6_FIND_REQUIRED)
            list(APPEND _qt6_args REQUIRED)
        endif()
        if(Qt6_FIND_COMPONENTS)
            list(APPEND _qt6_args COMPONENTS ${Qt6_FIND_COMPONENTS})
        endif()

        find_package(Qt6 ${Qt6_FIND_VERSION} ${_qt6_args})

        unset(_qt6_args)
        unset(_qt6_chosen)
    elseif(Qt6_FIND_REQUIRED)
        string(REPLACE ";" " " _qt6_arch_text "${_qt6_arch_dirs}")
        if(_qt6_hint_count GREATER 0)
            set(_qt6_hint_note "")
        else()
            set(_qt6_hint_note "  No Qt hint variable was set.\n")
        endif()

        message(FATAL_ERROR
            "Qt6 was not found, so the GUI cannot be configured.\n"
            "Qt is a prebuilt dependency, never a vcpkg port. Searched, in order:\n"
            "${_qt6_report}"
            "  In each of those: lib/cmake/Qt6/Qt6Config.cmake, lib64/cmake/Qt6/Qt6Config.cmake, "
            "and <root>/6.x/<kit>/lib/cmake/Qt6/Qt6Config.cmake for kit in: ${_qt6_arch_text}\n"
            "${_qt6_hint_note}"
            "Point at a Qt kit with any one of:\n"
            "  cmake --preset <preset> -DICL_QT_ROOT=${_qt6_example}\n"
            "  ICL_QT_ROOT, QT_ROOT_DIR or QTDIR in the environment\n"
            "  cmake --preset <preset> -DCMAKE_PREFIX_PATH=${_qt6_example}\n"
            "Or configure with the project's GUI option off.\n")
    elseif(NOT Qt6_FIND_QUIETLY)
        message(STATUS "FindQt6: no prebuilt Qt6 kit found; configure with -DICL_QT_ROOT=<kit> to use one")
    endif()

    unset(_qt6_pfx_root)
    unset(_qt6_pfx_env)
    unset(_qt6_pfx_name)
    unset(_qt6_arch_dirs)
    unset(_qt6_arch_text)
    unset(_qt6_arm_arch_dirs)
    unset(_qt6_candidates)
    unset(_qt6_default_roots)
    unset(_qt6_env)
    unset(_qt6_example)
    unset(_qt6_hint_count)
    unset(_qt6_hint_note)
    unset(_qt6_index)
    unset(_qt6_label)
    unset(_qt6_libdir)
    unset(_qt6_report)
    unset(_qt6_root)
    unset(_qt6_root_labels)
    unset(_qt6_roots)
    unset(_qt6_strict_count)
    unset(_qt6_strict_roots)
    unset(_qt6_strict_text)
    unset(_qt6_version_dir)
    unset(_qt6_version_dirs)
endif()
