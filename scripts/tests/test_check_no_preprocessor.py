# SPDX-License-Identifier: GPL-3.0-or-later
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_no_preprocessor.py"
sys.path.insert(0, str(SCRIPT.parent))
import check_no_preprocessor as c  # noqa: E402


class ScanText(unittest.TestCase):
    def test_platform_conditional_is_hard(self):
        hard, soft = c.scan_text("#ifdef _WIN32\nint x;\n#endif\n")
        self.assertEqual([h[1] for h in hard], ["ifdef"])
        self.assertEqual(len(soft), 1)  # the #endif

    def test_defined_form_and_has_include(self):
        hard, _ = c.scan_text("#if defined(__linux__) && __has_include(<x>)\n#endif\n")
        self.assertEqual(len(hard), 1)

    def test_cpp_version_test(self):
        hard, _ = c.scan_text("#if __cplusplus >= 202302L\n#endif\n")
        self.assertEqual(len(hard), 1)

    def test_plain_define_is_soft(self):
        hard, soft = c.scan_text("#define FOO 1\n#ifdef FOO\n#endif\n")
        self.assertEqual(hard, [])
        self.assertEqual(len(soft), 3)

    def test_include_pragma_error_ignored(self):
        hard, soft = c.scan_text('#include <a>\n#pragma once\n#error "x"\n')
        self.assertEqual((hard, soft), ([], []))

    def test_comments_and_strings_ignored(self):
        text = '// #ifdef _WIN32\n/* #if __linux__\n#endif */\nconst char* s = "#define X";\n'
        self.assertEqual(c.scan_text(text), ([], []))

    def test_continuation_joined(self):
        hard, _ = c.scan_text("#if FOO || \\\n    _MSC_VER\n#endif\n")
        self.assertEqual(len(hard), 1)


class Cli(unittest.TestCase):
    def run_cli(self, files, baseline=None, allow=None, *extra):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            if baseline is not None:
                (root / "tools").mkdir(exist_ok=True)
                (root / "tools/preprocessor-baseline.json").write_text(json.dumps({"files": baseline}))
            if allow is not None:
                (root / "tools").mkdir(exist_ok=True)
                (root / "tools/preprocessor-allowlist.txt").write_text(allow)
            files_arg = list(files)
            res = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *extra, *files_arg],
                                 capture_output=True, text=True)
            baseline_after = None
            bp = root / "tools/preprocessor-baseline.json"
            if bp.exists():
                baseline_after = json.loads(bp.read_text())
            return res, baseline_after

    def test_clean_tree_passes(self):
        res, _ = self.run_cli({"src/a.cpp": "int f();\n"}, baseline={})
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_new_directive_fails(self):
        res, _ = self.run_cli({"src/a.cpp": "#define X 1\n"}, baseline={})
        self.assertEqual(res.returncode, 1)
        self.assertIn("baseline 0", res.stderr)

    def test_within_baseline_passes_and_lower_noted(self):
        res, _ = self.run_cli({"src/a.cpp": "#define X 1\n"}, baseline={"src/a.cpp": 3})
        self.assertEqual(res.returncode, 0)
        self.assertIn("below their baseline", res.stdout)

    def test_hard_violation_fails_even_when_allowlisted(self):
        res, _ = self.run_cli({"src/a.cpp": "#ifdef _WIN32\n#endif\n"}, baseline={"src/a.cpp": 9},
                              allow="src/*.cpp  # reason\n")
        self.assertEqual(res.returncode, 1)
        self.assertIn("src/platform", res.stderr)

    def test_allowlist_needs_reason(self):
        res, _ = self.run_cli({"src/a.cpp": "int x;\n"}, baseline={}, allow="src/*.cpp\n")
        self.assertEqual(res.returncode, 2)

    def test_allowlisted_soft_directives_not_counted(self):
        res, _ = self.run_cli({"src/a.cpp": "#define X 1\n"}, baseline={}, allow="src/*.cpp  # highway\n")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_update_baseline_lowers_but_never_raises(self):
        res, after = self.run_cli({"src/a.cpp": "#define X 1\n"}, {"src/a.cpp": 3}, None, "--update-baseline")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(after, {"files": {"src/a.cpp": 1}})
        res, _ = self.run_cli({"src/a.cpp": "#define X 1\n#define Y 2\n"}, {"src/a.cpp": 1}, None, "--update-baseline")
        self.assertEqual(res.returncode, 1)

    def test_missing_baseline_fails(self):
        res, _ = self.run_cli({"src/a.cpp": "int x;\n"})
        self.assertEqual(res.returncode, 1)


if __name__ == "__main__":
    unittest.main()
