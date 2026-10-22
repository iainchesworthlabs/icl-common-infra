# SPDX-License-Identifier: GPL-3.0-or-later
"""run_ctest.py against a fake ctest that fails named tests a set number of times."""
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_ctest.py"

FAKE = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, sys
    from pathlib import Path
    args = sys.argv[1:]
    build = Path(args[args.index("--test-dir") + 1])
    state = build / "state.json"
    cfg = json.loads((build / "fake.json").read_text())
    st = json.loads(state.read_text()) if state.exists() else {}
    log = build / "Testing" / "Temporary" / "LastTestsFailed.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if "-N" in args:
        label = args[args.index("-L") + 1] if "-L" in args else None
        n = len(cfg.get(label, {}).get("tests", [])) if label else 0
        print(f"Total Tests: {n}")
        sys.exit(0)
    if "--tests-from-file" in args:
        names = Path(args[args.index("--tests-from-file") + 1]).read_text().split()
    else:
        label = args[args.index("-L") + 1]
        names = cfg.get(label, {}).get("tests", [])
        if not names and "--no-tests=error" in args:
            sys.exit(8)
    failed = []
    for n in names:
        remaining = cfg.get("fail_times", {}).get(n, 0) - st.get(n, 0)
        st[n] = st.get(n, 0) + 1
        if remaining > 0:
            failed.append(n)
    state.write_text(json.dumps(st))
    log.write_text("".join(f"{i+1}:{n}\\n" for i, n in enumerate(failed)))
    sys.exit(1 if failed else 0)
''')


class RunCtest(unittest.TestCase):
    def run_with(self, cfg):
        with tempfile.TemporaryDirectory() as d:
            build = Path(d) / "build"
            build.mkdir()
            (build / "fake.json").write_text(json.dumps(cfg))
            fake = Path(d) / "ctest"
            fake.write_text(FAKE)
            fake.chmod(0o755)
            summary = Path(d) / "summary.md"
            phases = Path(d) / "phases.json"
            phases.write_text(json.dumps([
                {"name": "parallel", "label": "unit", "jobs": 2},
                {"name": "ui", "label": "ui", "jobs": 1, "optional": True}]))
            res = subprocess.run([sys.executable, str(SCRIPT), "--build-dir", str(build), "--ctest", str(fake),
                                  "--phases", str(phases), "--summary", str(summary)],
                                 capture_output=True, text=True)
            return res, summary.read_text()

    def test_all_pass(self):
        res, summary = self.run_with({"unit": {"tests": ["a", "b"]}})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("ui: no tests match", summary)

    def test_flaky_passes_with_warning(self):
        res, summary = self.run_with({"unit": {"tests": ["a", "b"]}, "fail_times": {"b": 1}})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("Flaky: b", summary)
        self.assertIn("::warning::", res.stdout)

    def test_consistent_failure_fails(self):
        res, summary = self.run_with({"unit": {"tests": ["a", "b"]}, "fail_times": {"b": 2}})
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAILED twice: b", summary)

    def test_required_phase_with_no_tests_fails(self):
        res, _ = self.run_with({"ui": {"tests": ["x"]}})
        self.assertEqual(res.returncode, 1)


if __name__ == "__main__":
    unittest.main()
