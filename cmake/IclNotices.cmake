# SPDX-License-Identifier: GPL-3.0-or-later
#
# Licence notices and source information for a shipped application (standard section 7.5).
#
#   icl_generate_notices(OUTPUT <file> NAME <name>
#       [QT_VERSION <version>]
#       [PACKAGES <vcpkg package>...]
#       [EXCLUDE <vcpkg package>...]
#       [MANIFEST <vcpkg.json>]
#       [INSTALLED_DIR <dir>])
#     Writes <file> at configure time: one entry per runtime dependency with the licence text vcpkg
#     installed for it, and an entry for Qt when QT_VERSION is given. The runtime dependencies are the
#     "dependencies" of the manifest (default: vcpkg.json next to the top-level CMakeLists.txt) except
#     host tools and the packages in EXCLUDE (test-only packages, for example catch2), or exactly
#     PACKAGES when that is given. A package with no licence file stops the configure, which is the
#     check that the notices cover every dependency. INSTALLED_DIR defaults to
#     ${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}. The manifest is a configure dependency.
#
#   icl_write_source_info(OUTPUT <file> NAME <name> VERSION <version> SOURCE_DIR <dir>
#       [URL <url>] [QT_VERSION <version>])
#     Writes <file> naming the commit the program was built from. It runs when the package is
#     installed, because only then is the commit the one that was built. The commit comes from git
#     in SOURCE_DIR, then from $GITHUB_SHA, and is "unknown" when neither exists.

function(icl_generate_notices)
    cmake_parse_arguments(ARG "" "OUTPUT;NAME;QT_VERSION;MANIFEST;INSTALLED_DIR" "PACKAGES;EXCLUDE" ${ARGN})
    if(NOT ARG_OUTPUT OR NOT ARG_NAME)
        message(FATAL_ERROR "icl_generate_notices: OUTPUT and NAME are required")
    endif()
    if(NOT ARG_MANIFEST)
        set(ARG_MANIFEST "${CMAKE_SOURCE_DIR}/vcpkg.json")
    endif()
    if(NOT ARG_INSTALLED_DIR AND VCPKG_INSTALLED_DIR AND VCPKG_TARGET_TRIPLET)
        set(ARG_INSTALLED_DIR "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}")
    endif()

    set(packages ${ARG_PACKAGES})
    if(NOT ARG_PACKAGES AND EXISTS "${ARG_MANIFEST}")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${ARG_MANIFEST}")
        file(READ "${ARG_MANIFEST}" manifest)
        string(JSON dependency_count ERROR_VARIABLE no_dependencies LENGTH "${manifest}" "dependencies")
        if(NOT no_dependencies AND dependency_count GREATER 0)
            math(EXPR last "${dependency_count} - 1")
            foreach(index RANGE ${last})
                string(JSON kind TYPE "${manifest}" "dependencies" ${index})
                if(kind STREQUAL "STRING")
                    string(JSON package GET "${manifest}" "dependencies" ${index})
                else()
                    string(JSON host ERROR_VARIABLE no_host GET "${manifest}" "dependencies" ${index} "host")
                    if(NOT no_host AND host)
                        continue()
                    endif()
                    string(JSON package GET "${manifest}" "dependencies" ${index} "name")
                endif()
                list(APPEND packages "${package}")
            endforeach()
        endif()
    endif()
    if(ARG_EXCLUDE)
        list(REMOVE_ITEM packages ${ARG_EXCLUDE})
    endif()
    list(REMOVE_DUPLICATES packages)

    set(text "Third-party notices for ${ARG_NAME}\n")
    string(APPEND text "\n${ARG_NAME} itself is covered by the LICENSE file in this directory.\n")
    if(ARG_QT_VERSION)
        string(APPEND text "\n================================================================================\n")
        string(APPEND text "Qt ${ARG_QT_VERSION}\n")
        string(APPEND text "================================================================================\n")
        string(APPEND text "Copyright The Qt Company Ltd. and other contributors.\n")
        string(APPEND text "Qt is available under the GNU LGPL version 3, the GNU GPL version 2 and version 3, and a\n")
        string(APPEND text "commercial licence (https://www.qt.io/licensing/).\n")
        string(APPEND text "Source code: https://download.qt.io/official_releases/qt/")
        string(REGEX REPLACE "^([0-9]+\\.[0-9]+).*" "\\1" qt_series "${ARG_QT_VERSION}")
        string(APPEND text "${qt_series}/${ARG_QT_VERSION}/single/qt-everywhere-src-${ARG_QT_VERSION}.tar.xz\n")
        string(APPEND text "Qt includes third-party components, for example ICU, FreeType, HarfBuzz and libpng. Their\n")
        string(APPEND text "licences are listed at https://doc.qt.io/qt-6/licenses-used-in-qt.html\n")
    endif()

    set(missing "")
    foreach(package IN LISTS packages)
        set(copyright "${ARG_INSTALLED_DIR}/share/${package}/copyright")
        if(NOT ARG_INSTALLED_DIR OR NOT EXISTS "${copyright}")
            list(APPEND missing "${package}")
            continue()
        endif()
        file(READ "${copyright}" licence_text)
        string(APPEND text "\n================================================================================\n")
        string(APPEND text "${package}\n")
        string(APPEND text "================================================================================\n")
        string(APPEND text "${licence_text}")
        string(REGEX MATCH "\n$" ends_with_newline "${licence_text}")
        if(NOT ends_with_newline)
            string(APPEND text "\n")
        endif()
    endforeach()
    if(missing)
        list(JOIN missing ", " missing_list)
        message(FATAL_ERROR
            "icl_generate_notices: no licence file in '${ARG_INSTALLED_DIR}' for: ${missing_list}.\n"
            "Every runtime dependency needs one. List packages that are not shipped (tests, tools) in EXCLUDE.")
    endif()

    set(previous "")
    if(EXISTS "${ARG_OUTPUT}")
        file(READ "${ARG_OUTPUT}" previous)
    endif()
    if(NOT previous STREQUAL text)
        file(WRITE "${ARG_OUTPUT}" "${text}")
    endif()
endfunction()

function(icl_write_source_info)
    cmake_parse_arguments(ARG "" "OUTPUT;NAME;VERSION;SOURCE_DIR;URL;QT_VERSION" "" ${ARGN})
    if(NOT ARG_OUTPUT OR NOT ARG_NAME OR NOT ARG_VERSION OR NOT ARG_SOURCE_DIR)
        message(FATAL_ERROR "icl_write_source_info: OUTPUT, NAME, VERSION and SOURCE_DIR are required")
    endif()
    set(commit "")
    set(describe "")
    find_program(git_program git)
    if(git_program)
        execute_process(COMMAND "${git_program}" -C "${ARG_SOURCE_DIR}" rev-parse HEAD
            OUTPUT_VARIABLE commit OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET RESULT_VARIABLE status)
        if(NOT status EQUAL 0)
            set(commit "")
        else()
            execute_process(COMMAND "${git_program}" -C "${ARG_SOURCE_DIR}" describe --tags --always --dirty
                OUTPUT_VARIABLE describe OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        endif()
    endif()
    if(NOT commit AND DEFINED ENV{GITHUB_SHA})
        set(commit "$ENV{GITHUB_SHA}")
    endif()
    if(NOT commit)
        set(commit "unknown")
    endif()

    set(text "${ARG_NAME} ${ARG_VERSION}\n")
    if(ARG_URL)
        string(APPEND text "Source: ${ARG_URL}\n")
    endif()
    string(APPEND text "Commit: ${commit}\n")
    if(describe)
        string(APPEND text "Version from git: ${describe}\n")
    endif()
    string(APPEND text "To get this exact source, check out the commit above.\n")
    if(ARG_QT_VERSION)
        string(REGEX REPLACE "^([0-9]+\\.[0-9]+).*" "\\1" qt_series "${ARG_QT_VERSION}")
        string(APPEND text "\nThis build uses Qt ${ARG_QT_VERSION}. Its source is at\n")
        string(APPEND text "https://download.qt.io/official_releases/qt/${qt_series}/${ARG_QT_VERSION}/single/\n")
    endif()
    get_filename_component(directory "${ARG_OUTPUT}" DIRECTORY)
    file(MAKE_DIRECTORY "${directory}")
    file(WRITE "${ARG_OUTPUT}" "${text}")
endfunction()
