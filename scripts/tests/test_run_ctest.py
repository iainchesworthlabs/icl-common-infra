# SPDX-License-Identifier: GPL-3.0-or-later
"""run_ctest.py against a fake ctest that fails named tests a set number of times, and against the real ctest."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "run_ctest.py"

# The fake does what the real ctest does that matters here: it changes into the --test-dir before it reads anything
# else, so a relative --tests-from-file is looked for under the test directory; it cannot read a list it is given
# ("Problem reading test list file") without running a test or touching LastTestsFailed.log; and it writes
# LastTestsFailed.log only when a test failed, so that the file of an earlier run stays as it was.
FAKE = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys
    from pathlib import Path
    args = sys.argv[1:]
    build = Path(args[args.index("--test-dir") + 1]).resolve()
    os.chdir(build)
    state = build / "state.json"
    cfg = json.loads((build / "fake.json").read_text())
    st = json.loads(state.read_text()) if state.exists() else {}
    log = build / "Testing" / "Temporary" / "LastTestsFailed.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with (build / "args.log").open("a") as seen:
        seen.write(json.dumps(args) + "\\n")
    if "-N" in args:
        label = args[args.index("-L") + 1] if "-L" in args else None
        n = len(cfg.get(label, {}).get("tests", [])) if label else 0
        print(f"Total Tests: {n}")
        sys.exit(0)
    if "--tests-from-file" in args:
        listing = Path(args[args.index("--tests-from-file") + 1])
        if cfg.get("refuse_rerun") or not listing.is_file():
            print(f"Problem reading test list file: {listing} while generating list of tests to run.")
            print("Errors while running CTest")
            sys.exit(1)
        names = listing.read_text().split()
    else:
        label = args[args.index("-L") + 1] if "-L" in args else "all"
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
    if failed:
        log.write_text("".join(f"{i+1}:{n}\\n" for i, n in enumerate(failed)))
    sys.exit(1 if failed else 0)
''')


def install_fake(directory):
    """Write the fake as `ctest` in `directory` and return what to run. Windows runs no shebang, so a .cmd calls it."""
    fake = Path(directory) / "ctest"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    if os.name != "nt":
        return fake
    wrapper = Path(directory) / "ctest.cmd"
    wrapper.write_text(f'@"{sys.executable}" "{fake}" %*\r\n')
    return wrapper


class RunCtest(unittest.TestCase):
    def run_with(self, cfg, relative=False):
        """Run the script on the fake. `relative` gives --build-dir as the CI does, a path under the working directory."""
        with tempfile.TemporaryDirectory() as d:
            build = Path(d) / "build"
            build.mkdir()
            (build / "fake.json").write_text(json.dumps(cfg))
            fake = install_fake(d)
            summary = Path(d) / "summary.md"
            phases = Path(d) / "phases.json"
            phases.write_text(json.dumps([
                {"name": "parallel", "label": "unit", "jobs": 2},
                {"name": "ui", "label": "ui", "jobs": 1, "optional": True}]))
            res = subprocess.run([sys.executable, str(SCRIPT), "--build-dir", "build" if relative else str(build),
                                  "--ctest", str(fake), "--phases", str(phases), "--summary", str(summary)],
                                 capture_output=True, text=True, cwd=d)
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

    def test_flaky_passes_when_the_build_dir_is_relative(self):
        # The workflows give `build/<preset>`. ctest changes into --test-dir before it opens the list of tests to
        # re-run, so a list named by a path relative to the working directory is not found there.
        res, summary = self.run_with({"unit": {"tests": ["a", "b"]}, "fail_times": {"b": 1}}, relative=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("Flaky: b", summary)
        self.assertNotIn("Problem reading", res.stdout)

    def test_consistent_failure_fails_when_the_build_dir_is_relative(self):
        res, summary = self.run_with({"unit": {"tests": ["a", "b"]}, "fail_times": {"b": 2}}, relative=True)
        self.assertEqual(res.returncode, 1)
        self.assertIn("FAILED twice: b", summary)
        self.assertNotIn("Problem reading", res.stdout)

    def test_a_rerun_that_cannot_run_is_not_reported_as_failed_twice(self):
        # ctest that cannot read the list runs no test and leaves LastTestsFailed.log as the first run wrote it.
        # Reading that file again must not turn the first failure into a second one.
        res, summary = self.run_with({"unit": {"tests": ["a", "b"]}, "fail_times": {"b": 1}, "refuse_rerun": True})
        self.assertEqual(res.returncode, 1)
        self.assertIn("re-run failed without a failure list", summary)
        self.assertNotIn("FAILED twice", summary)

    @unittest.skipIf(os.name == "nt", "the .cmd that stands for ctest on Windows reads the | of a label expression as a pipe")
    def test_exclude_and_args_reach_ctest(self):
        with tempfile.TemporaryDirectory() as d:
            build = Path(d) / "build"
            build.mkdir()
            (build / "fake.json").write_text(json.dumps({"all": {"tests": ["a"]}}))
            fake = install_fake(d)
            phases = Path(d) / "phases.json"
            phases.write_text(json.dumps([
                {"name": "everything but system", "label": "", "exclude": "system|slow", "jobs": 2,
                 "args": ["-E", "flaky_name"]}]))
            res = subprocess.run([sys.executable, str(SCRIPT), "--build-dir", str(build), "--ctest", str(fake),
                                  "--phases", str(phases)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            seen = [json.loads(line) for line in (build / "args.log").read_text().splitlines()]
            first = seen[0]
            self.assertNotIn("-L", first)
            self.assertEqual(first[first.index("-LE") + 1], "system|slow")
            self.assertEqual(first[first.index("-E") + 1], "flaky_name")

    def test_required_phase_with_no_tests_fails(self):
        res, _ = self.run_with({"ui": {"tests": ["x"]}})
        self.assertEqual(res.returncode, 1)


FLAKY = textwrap.dedent('''\
    import sys
    from pathlib import Path
    marker = Path(sys.argv[1])
    if marker.exists():
        sys.exit(0)
    marker.write_text("x")
    sys.exit(1)
''')


@unittest.skipUnless(shutil.which("ctest"), "ctest is not installed")
class RunCtestWithRealCtest(unittest.TestCase):
    """The script against the real ctest, started from the working directory of a workflow with `build` as its build dir."""

    def run_real(self, tests, phases=None):
        """`tests` maps a name to what the test does: pass, fail, timeout (killed after a second) or flaky (fails once)."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            build = root / "build"
            build.mkdir()
            (root / "flaky.py").write_text(FLAKY)
            python = Path(sys.executable).as_posix()
            lines = []
            for name, kind in tests.items():
                command = {"pass": ["-c", "pass"],
                           "fail": ["-c", "raise SystemExit(1)"],
                           "timeout": ["-c", "__import__('time').sleep(60)"],
                           "flaky": [(root / "flaky.py").as_posix(), (root / f"{name}.marker").as_posix()]}[kind]
                lines.append(f"add_test({name} " + " ".join(f'"{a}"' for a in [python] + command) + ")")
            lines.append("set_tests_properties(" + " ".join(tests) + ' PROPERTIES LABELS "unit")')
            timeouts = [n for n, kind in tests.items() if kind == "timeout"]
            if timeouts:
                lines.append("set_tests_properties(" + " ".join(timeouts) + " PROPERTIES TIMEOUT 1)")
            (build / "CTestTestfile.cmake").write_text("\n".join(lines) + "\n")
            phases_file = root / "phases.json"
            phases_file.write_text(json.dumps(phases or [{"name": "unit", "label": "unit", "jobs": 2}]))
            summary = root / "summary.md"
            res = subprocess.run([sys.executable, str(SCRIPT), "--build-dir", "build", "--phases", str(phases_file),
                                  "--summary", str(summary)], capture_output=True, text=True, cwd=d)
            return res, summary.read_text()

    def test_a_flaky_test_passes_on_the_rerun(self):
        res, summary = self.run_real({"t_pass": "pass", "t_flaky": "flaky"})
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("Problem reading", res.stdout)
        self.assertIn("::warning::unit: 1 failed; re-running by name: t_flaky", res.stdout)
        self.assertIn("passed after re-run. Flaky: t_flaky", summary)

    def test_a_test_that_fails_or_times_out_twice_still_fails(self):
        res, summary = self.run_real({"t_pass": "pass", "t_flaky": "flaky", "t_fail": "fail", "t_timeout": "timeout"})
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertNotIn("Problem reading", res.stdout)
        self.assertIn("FAILED twice: t_fail, t_timeout", summary)
        self.assertIn("flaky (failed then passed): t_flaky", summary)


if __name__ == "__main__":
    unittest.main()
