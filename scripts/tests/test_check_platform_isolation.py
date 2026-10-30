# SPDX-License-Identifier: GPL-3.0-or-later
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_platform_isolation.py"
sys.path.insert(0, str(SCRIPT.parent))
import check_platform_isolation as c  # noqa: E402


class Tree:
    """A throwaway project: files are written relative to its root."""

    def __init__(self, test: unittest.TestCase):
        self.dir = tempfile.TemporaryDirectory()
        test.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        # A clean platform section: windows and linux, one unit each, wired.
        self.write("src/app/platform/windows/platform.cmake", "set(SOURCES platform/windows/camera.cpp)\n")
        self.write("src/app/platform/windows/camera.cpp", "#include <windows.h>\n")
        self.write("src/app/platform/linux/platform.cmake", "set(SOURCES platform/linux/camera.cpp)\n")
        self.write("src/app/platform/linux/camera.cpp", "#include <unistd.h>\n")
        self.write("src/app/platform/detail/helper.cpp", "#include <sys/types.h>\n")

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run(self, **config):
        cfg = dict(c.DEFAULTS)
        cfg.update(config)
        violations, _, _ = c.check(self.root, cfg)
        return violations


class Rules(unittest.TestCase):
    def test_clean_tree_passes(self):
        self.assertEqual(Tree(self).run(), [])

    def test_os_header_outside_the_section_is_flagged(self):
        tree = Tree(self)
        tree.write("src/app/shell.cpp", '#include <vector>\n#include <windows.h>\n')
        found = tree.run()
        self.assertEqual([(v.rule, v.path, v.line) for v in found], [("os-header", "src/app/shell.cpp", 2)])

    def test_sys_header_family_and_objective_c_are_flagged(self):
        tree = Tree(self)
        tree.write("src/lib/a.cpp", "#include <sys/stat.h>\n")
        tree.write("src/lib/b.mm", "#import <AVFoundation/AVFoundation.h>\n")
        tree.write("src/lib/c.cpp", '#include "android/log.h"\n')
        self.assertEqual({v.path for v in tree.run()}, {"src/lib/a.cpp", "src/lib/b.mm", "src/lib/c.cpp"})

    def test_standard_headers_are_not_flagged(self):
        tree = Tree(self)
        tree.write("src/lib/a.cpp", "#include <filesystem>\n#include <iosfwd>\n#include <system_error>\n")
        self.assertEqual(tree.run(), [])

    def test_os_header_in_the_test_platform_section_is_allowed(self):
        tree = Tree(self)
        tree.write("tests/platform/windows/paths_test.cpp", "#include <windows.h>\n")
        self.assertEqual(tree.run(), [])

    def test_os_query_is_flagged_in_code_and_in_qml(self):
        tree = Tree(self)
        tree.write("src/app/a.cpp", "bool mac = QSysInfo::productType() == QStringLiteral(\"macos\");\n")
        tree.write("src/app/b.cpp", "auto name = QGuiApplication::platformName();\n")
        tree.write("src/app/c.qml", "visible: Qt.platform.os === \"ios\"\n")
        tree.write("src/app/d.cpp", "#ifdef Q_OS_WIN\n")
        self.assertEqual({v.path for v in tree.run()}, {"src/app/a.cpp", "src/app/b.cpp", "src/app/c.qml", "src/app/d.cpp"})

    def test_a_comment_that_mentions_an_os_api_is_not_a_finding(self):
        tree = Tree(self)
        tree.write(
            "src/app/a.cpp",
            "// not QSysInfo, which would ask the OS\n"
            "/* nor <windows.h>:\n   #include <windows.h>\n   QOperatingSystemVersion */\n"
            "int ok = 1;  // Q_OS_WIN is for the platform section\n",
        )
        self.assertEqual(tree.run(), [])

    def test_cmake_os_test_is_flagged_outside_the_selector(self):
        tree = Tree(self)
        tree.write("src/lib/CMakeLists.txt", "if(WIN32)\n  add_definitions(-DX)\nendif()\n")
        tree.write("cmake/Other.cmake", "if(CMAKE_SYSTEM_NAME STREQUAL Linux)\nendif()\n")
        tree.write("cmake/Gen.cmake", 'set(x "$<PLATFORM_ID:Windows>")\n')
        self.assertEqual(
            {(v.rule, v.path) for v in tree.run()},
            {("cmake-os", "src/lib/CMakeLists.txt"), ("cmake-os", "cmake/Other.cmake"), ("cmake-os", "cmake/Gen.cmake")},
        )

    def test_cmake_selector_fragments_and_triplets_are_exempt(self):
        tree = Tree(self)
        tree.write("cmake/Platform.cmake", "if(WIN32)\nendif()\n")
        tree.write("src/app/platform/windows/platform.cmake", "if(WIN32)\nendif()\nset(SOURCES platform/windows/camera.cpp)\n")
        tree.write("cmake/triplets/x64-linux.cmake", "if(UNIX)\nendif()\n")
        self.assertEqual(tree.run(), [])

    def test_names_that_only_contain_an_os_word_are_not_flagged(self):
        tree = Tree(self)
        tree.write(
            "src/lib/CMakeLists.txt",
            "if(CMAKE_HOST_WIN32)\nendif()\n"
            "set_target_properties(x PROPERTIES WIN32_EXECUTABLE ON)\n"
            "set(QT_ANDROID_PACKAGE_SOURCE_DIR a)\n"
            "# if(WIN32) in a comment\n"
            "if(MSVC)\nendif()\n",
        )
        self.assertEqual(tree.run(), [])

    def test_unit_that_no_fragment_names_is_flagged(self):
        tree = Tree(self)
        tree.write("src/app/platform/linux/orphan.cpp", "int x;\n")
        found = tree.run()
        self.assertEqual([(v.rule, v.path) for v in found], [("unwired", "src/app/platform/linux/orphan.cpp")])

    def test_a_name_only_in_a_comment_is_not_wired(self):
        tree = Tree(self)
        tree.write("src/app/platform/linux/platform.cmake", "# platform/linux/camera.cpp\nset(SOURCES)\n")
        self.assertEqual([v.path for v in tree.run()], ["src/app/platform/linux/camera.cpp"])

    def test_platform_directory_without_a_fragment_is_flagged(self):
        tree = Tree(self)
        tree.write("src/app/platform/web/driver.cpp", "int x;\n")
        rules = {(v.rule, v.path) for v in tree.run()}
        self.assertIn(("unwired", "src/app/platform/web"), rules)

    def test_shared_directories_need_no_fragment(self):
        tree = Tree(self)
        tree.write("src/app/platform/posix/crash.cpp", "int x;\n")
        # posix is not a platform, but its units are still named by a fragment.
        tree.write("src/app/platform/linux/platform.cmake", "set(SOURCES platform/linux/camera.cpp platform/posix/crash.cpp)\n")
        self.assertEqual(tree.run(), [])

    def test_skipped_prefix_is_not_scanned(self):
        tree = Tree(self)
        tree.write("cmake/icl/IclPlatform.cmake", "if(WIN32)\nendif()\n")
        self.assertEqual(tree.run(), [])


class Config(unittest.TestCase):
    def test_defaults_when_there_is_no_file(self):
        tree = Tree(self)
        self.assertEqual(c.load_config(tree.root, None), c.DEFAULTS)

    def test_file_overrides_and_unknown_key_is_an_error(self):
        tree = Tree(self)
        tree.write("tools/platform-isolation.json", json.dumps({"not_platforms": ["detail"]}))
        self.assertEqual(c.load_config(tree.root, None)["not_platforms"], ["detail"])
        tree.write("tools/platform-isolation.json", json.dumps({"nope": 1}))
        with self.assertRaises(ValueError):
            c.load_config(tree.root, None)

    def test_main_exit_codes(self):
        tree = Tree(self)
        self.assertEqual(c.main(["--root", str(tree.root)]), 0)
        tree.write("src/app/bad.cpp", "#include <windows.h>\n")
        self.assertEqual(c.main(["--root", str(tree.root)]), 1)
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(c.main(["--root", empty]), 2)


if __name__ == "__main__":
    unittest.main()
