# SPDX-License-Identifier: GPL-3.0-or-later
#
#   icl_install_qt_app(<target>
#       BUNDLE_IDENTIFIER <reverse.domain.name>
#       [DISPLAY_NAME <name>]
#       [NOTICE_EXCLUDE <vcpkg package>...]
#       [NOTICE_PACKAGES <vcpkg package>...])
#
# Everything a Qt application needs to be packaged, in one call from the application's directory,
# after qt_add_executable and qt_add_qml_module:
#
#   - macOS bundle properties (the identifier, the name, and the version taken from PROJECT_VERSION,
#     so the property list says 0.1.0 and not 0.1), and the install rules for the bundle or the program;
#   - the Qt deploy step, which copies the Qt libraries, plugins and QML modules next to the program so
#     the installed tree runs on a machine without Qt; the QML debugging plugins (qmltooling) are
#     removed from it, because a shipped program should not accept a debugger connection;
#   - the licence files: LICENSE, the LICENSES directory when there is one, THIRD-PARTY-NOTICES.txt
#     (see IclNotices.cmake) and SOURCE.txt naming the commit. They go to share/doc/<name> and, on
#     macOS, to <name>.app/Contents/Resources/doc, so the bundle carries them.
#
# The target's OUTPUT_NAME is used as <name> when it is set. Call project() with VERSION and
# HOMEPAGE_URL first. There are no placeholders: BUNDLE_IDENTIFIER is required.

include_guard(GLOBAL)
include("${CMAKE_CURRENT_LIST_DIR}/IclNotices.cmake")

function(icl_install_qt_app target)
    cmake_parse_arguments(ARG "" "BUNDLE_IDENTIFIER;DISPLAY_NAME" "NOTICE_EXCLUDE;NOTICE_PACKAGES" ${ARGN})
    if(NOT TARGET ${target})
        message(FATAL_ERROR "icl_install_qt_app: '${target}' is not a target")
    endif()
    if(NOT ARG_BUNDLE_IDENTIFIER)
        message(FATAL_ERROR "icl_install_qt_app: BUNDLE_IDENTIFIER is required (for example io.github.owner.name)")
    endif()
    if(NOT PROJECT_VERSION)
        message(FATAL_ERROR "icl_install_qt_app: call project() with VERSION first")
    endif()

    get_target_property(name ${target} OUTPUT_NAME)
    if(NOT name)
        set(name ${target})
    endif()
    if(NOT ARG_DISPLAY_NAME)
        set(ARG_DISPLAY_NAME "${name}")
    endif()

    # The bundle properties are read when Info.plist is generated and mean nothing elsewhere.
    set_target_properties(${target} PROPERTIES
        MACOSX_BUNDLE ON
        MACOSX_BUNDLE_GUI_IDENTIFIER "${ARG_BUNDLE_IDENTIFIER}"
        MACOSX_BUNDLE_BUNDLE_NAME "${ARG_DISPLAY_NAME}"
        MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
        MACOSX_BUNDLE_BUNDLE_VERSION "${PROJECT_VERSION}")

    install(TARGETS ${target}
        BUNDLE DESTINATION .
        RUNTIME DESTINATION bin)

    qt_generate_deploy_qml_app_script(
        TARGET ${target}
        OUTPUT_SCRIPT deploy_script
        NO_UNSUPPORTED_PLATFORM_ERROR
        NO_TRANSLATIONS)
    install(SCRIPT "${deploy_script}")

    if(APPLE)
        set(doc_dir "${name}.app/Contents/Resources/doc")
        set(plugin_dirs "${name}.app/Contents/PlugIns/qmltooling")
    else()
        set(doc_dir "share/doc/${name}")
        set(plugin_dirs "plugins/qmltooling" "bin/plugins/qmltooling")
    endif()

    # Runs after the deploy script, which installs the plugin directory.
    install(CODE "
        foreach(dir IN ITEMS ${plugin_dirs})
            file(REMOVE_RECURSE \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/\${dir}\")
        endforeach()")

    set(notices "${CMAKE_CURRENT_BINARY_DIR}/${name}-THIRD-PARTY-NOTICES.txt")
    icl_generate_notices(
        OUTPUT "${notices}"
        NAME "${ARG_DISPLAY_NAME}"
        QT_VERSION "${Qt6_VERSION}"
        PACKAGES ${ARG_NOTICE_PACKAGES}
        EXCLUDE ${ARG_NOTICE_EXCLUDE})
    install(FILES "${notices}" DESTINATION "${doc_dir}" RENAME THIRD-PARTY-NOTICES.txt)
    install(FILES "${PROJECT_SOURCE_DIR}/LICENSE" DESTINATION "${doc_dir}")
    if(IS_DIRECTORY "${PROJECT_SOURCE_DIR}/LICENSES")
        install(DIRECTORY "${PROJECT_SOURCE_DIR}/LICENSES" DESTINATION "${doc_dir}")
    endif()

    install(CODE "
        include([[${CMAKE_CURRENT_FUNCTION_LIST_DIR}/IclNotices.cmake]])
        icl_write_source_info(
            OUTPUT \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${doc_dir}/SOURCE.txt\"
            NAME [[${ARG_DISPLAY_NAME}]]
            VERSION [[${PROJECT_VERSION}]]
            SOURCE_DIR [[${PROJECT_SOURCE_DIR}]]
            URL [[${PROJECT_HOMEPAGE_URL}]]
            QT_VERSION [[${Qt6_VERSION}]])")
endfunction()
