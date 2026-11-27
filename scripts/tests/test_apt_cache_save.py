# SPDX-License-Identifier: GPL-3.0-or-later
"""The save step of the package cache of setup-gcc, setup-llvm and setup-qt.

The install scripts keep the .deb files they download in a directory under $HOME and leave a `.new` marker there. The
save step must run when the marker is there. A `hashFiles()` test of the marker cannot do that: the function reads only
files under GITHUB_WORKSPACE, so it was always empty and the cache was never saved. These tests check that the action
tests an output instead, that no `hashFiles` is left in the three, and that the step that sets the output does it."""
import datetime
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTIONS = ("setup-gcc", "setup-llvm", "setup-qt")
NOTE = "Note whether packages were downloaded"
SAVE = "Save the package cache"


def find_bash():
    """bash, and on Windows Git's: the bash.exe on PATH there may be the WSL launcher."""
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            candidate = Path(base) / "Git" / "bin" / "bash.exe"
            if base and candidate.is_file():
                return str(candidate)
        return None
    import shutil
    return shutil.which("bash")


BASH = find_bash()


def steps(action: str) -> dict[str, str]:
    """The text of each step of a composite action, by name."""
    text = (ROOT / "actions" / action / "action.yml").read_text(encoding="utf-8")
    parts = re.split(r"(?m)^    - name: ", text)
    return {part.split("\n", 1)[0].strip(): part for part in parts[1:]}


def script_of(step: str) -> str:
    match = re.search(r"(?m)^      run: \|\n((?:        .*\n|\n)+)", step)
    assert match, "the step has no run block"
    return textwrap.dedent(match.group(1))


def expression(step: str, key: str) -> str:
    """The `${{ ... }}` that a step gives as `key:` (an `env` entry or a `with` input)."""
    match = re.search(rf"(?m)^\s+{key}: (\$\{{\{{.*?\}}\}})\s*$", step)
    assert match, f"no {key} in the step"
    return match.group(1)


class SaveStep(unittest.TestCase):
    def test_no_hashfiles_of_the_package_directory_is_left(self):
        for action in ACTIONS:
            text = (ROOT / "actions" / action / "action.yml").read_text(encoding="utf-8")
            code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            self.assertNotIn("hashFiles(", code, action)

    def test_the_save_step_tests_the_output_of_the_note_step(self):
        for action in ACTIONS:
            by_name = steps(action)
            self.assertIn(NOTE, by_name, action)
            self.assertIn("id: fresh", by_name[NOTE], action)
            self.assertIn("steps.fresh.outputs.new == 'true'", by_name[SAVE], action)
            # The note step must be before the save step, or its output is empty when the save step asks.
            names = list(by_name)
            self.assertLess(names.index(NOTE), names.index(SAVE), action)

    def test_the_note_step_looks_in_the_directory_that_the_save_step_saves(self):
        for action in ACTIONS:
            by_name = steps(action)
            self.assertEqual(expression(by_name[NOTE], "DEB_DIR"), expression(by_name[SAVE], "path"), action)

    @unittest.skipUnless(BASH, "needs bash")
    def test_the_note_step_sets_the_output_when_the_marker_is_there_and_not_otherwise(self):
        for action in ACTIONS:
            script = script_of(steps(action)[NOTE])
            for marker, wanted in ((True, ["new=true"]), (False, [])):
                with tempfile.TemporaryDirectory() as tmp:
                    deb_dir = Path(tmp) / "debs"
                    deb_dir.mkdir()
                    (deb_dir / "a.deb").write_text("x")
                    if marker:
                        (deb_dir / ".new").write_text("")
                    output = Path(tmp) / "github_output"
                    output.write_text("")
                    script_file = Path(tmp) / "note.sh"
                    script_file.write_text(script)
                    done = subprocess.run(
                        [BASH, script_file.as_posix()],
                        env=dict(os.environ, DEB_DIR=deb_dir.as_posix(), GITHUB_OUTPUT=output.as_posix()),
                        capture_output=True, text=True,
                    )
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(output.read_text().split(), wanted, f"{action}, marker={marker}")


if __name__ == "__main__":
    unittest.main()


NAME_STEP = "Name the package cache"
RESTORE = "Restore the package cache"
INSTALL_SCRIPTS = {"setup-gcc": "install-gcc.sh", "setup-llvm": "install-llvm.sh", "setup-qt": "install-deps.sh"}


def value(step: str, key: str) -> str:
    """The text after `key:` on its line in a step."""
    match = re.search(rf"(?m)^\s+{key}: (.*)$", step)
    assert match, f"no {key} in the step"
    return match.group(1).strip()


def iso_week() -> str:
    year, week, _ = datetime.datetime.now(datetime.timezone.utc).isocalendar()
    return f"week-{year}-{week:02d}"


class KeyStep(unittest.TestCase):
    """The key of the package cache names the runner image. `${{ env.ImageVersion }}` is empty in an expression (the env
    context holds only what a workflow sets, and a probe on a hosted ubuntu-24.04 runner printed [] for it and
    20261122.23.1 for the shell variable), so the key never named one, and on a runner image with no version at all an
    entry kept its key for ever. A step reads the shell variable and, when there is none, takes the ISO week."""

    def test_no_key_reads_the_image_from_the_env_context(self):
        for action in ACTIONS:
            text = (ROOT / "actions" / action / "action.yml").read_text(encoding="utf-8")
            code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            self.assertNotIn("env.ImageVersion", code, action)

    def test_restore_and_save_use_the_name_that_the_step_before_made(self):
        for action in ACTIONS:
            by_name = steps(action)
            names = list(by_name)
            self.assertIn(NAME_STEP, by_name, action)
            self.assertIn("id: aptkey", by_name[NAME_STEP], action)
            self.assertLess(names.index(NAME_STEP), names.index(RESTORE), action)
            restore_key, save_key = value(by_name[RESTORE], "key"), value(by_name[SAVE], "key")
            self.assertEqual(restore_key, save_key, action)
            self.assertIn("steps.aptkey.outputs.image", restore_key, action)

    @unittest.skipUnless(BASH, "needs bash")
    def test_the_name_is_the_image_version_or_else_the_iso_week(self):
        for action in ACTIONS:
            script = script_of(steps(action)[NAME_STEP])
            for image in ("20261122.23.1", None):
                with tempfile.TemporaryDirectory() as tmp:
                    output = Path(tmp) / "github_output"
                    output.write_text("")
                    script_file = Path(tmp) / "name.sh"
                    script_file.write_text(script)
                    env = {k: v for k, v in os.environ.items() if k != "ImageVersion"}
                    env["GITHUB_OUTPUT"] = output.as_posix()
                    if image:
                        env["ImageVersion"] = image
                    before = iso_week()
                    done = subprocess.run([BASH, script_file.as_posix()], env=env, capture_output=True, text=True)
                    after = iso_week()
                    self.assertEqual(done.returncode, 0, done.stderr)
                    lines = output.read_text().split()
                    if image:
                        self.assertEqual(lines, [f"image={image}"], action)
                    else:
                        self.assertIn(lines, ([f"image={before}"], [f"image={after}"]), action)


def install_from_cache_function(action: str) -> str:
    text = (ROOT / "actions" / action / INSTALL_SCRIPTS[action]).read_text(encoding="utf-8")
    match = re.search(r"(?ms)^install_from_cache\(\) \{.*?^\}$", text)
    assert match, f"{action} has no install_from_cache"
    return match.group(0)


@unittest.skipUnless(BASH, "needs bash")
class InstallFromCache(unittest.TestCase):
    """What the install scripts do with a restored cache, with a stand-in for apt-get. A set that apt will not install
    (for one thing a restored cache that holds older packages than the image has, which apt refuses to downgrade with -y)
    must end in a warning and the network path, and never in a failed job."""

    def run_function(self, action, debs, apt_exit):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deb_dir = root / "debs"
            deb_dir.mkdir()
            for name in debs:
                (deb_dir / name).write_text("not a package")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            calls = root / "calls"
            stub = bin_dir / "apt-get"
            stub.write_text("#!/usr/bin/env bash\necho \"$*\" >> \"$STUB_CALLS\"\nexit \"$STUB_EXIT\"\n")
            stub.chmod(0o755)
            script = root / "run.sh"
            script.write_text(f'DEB_DIR="$1"\n{install_from_cache_function(action)}\ninstall_from_cache\necho "rc=$?"\n')
            env = dict(os.environ, STUB_CALLS=calls.as_posix(), STUB_EXIT=str(apt_exit),
                       PATH=bin_dir.as_posix() + os.pathsep + os.environ["PATH"])
            done = subprocess.run([BASH, script.as_posix(), deb_dir.as_posix()], env=env, capture_output=True, text=True)
            return done.stdout, (calls.read_text() if calls.exists() else "")

    def test_a_set_that_apt_will_not_install_falls_back_to_the_network_with_a_warning(self):
        for action in INSTALL_SCRIPTS:
            out, calls = self.run_function(action, ["a_1.0_all.deb", "b_1.0_all.deb"], apt_exit=100)
            self.assertIn("rc=1", out, action)
            self.assertIn("::warning title=apt-get::the cached packages did not install; using the network", out, action)
            self.assertIn("a_1.0_all.deb", calls, action)

    def test_a_set_that_installs_is_used(self):
        for action in INSTALL_SCRIPTS:
            out, calls = self.run_function(action, ["a_1.0_all.deb"], apt_exit=0)
            self.assertIn("rc=0", out, action)
            self.assertNotIn("::warning", out, action)
            self.assertIn("a_1.0_all.deb", calls, action)

    def test_no_cached_packages_means_the_network_without_calling_apt(self):
        for action in INSTALL_SCRIPTS:
            out, calls = self.run_function(action, [], apt_exit=0)
            self.assertIn("rc=1", out, action)
            self.assertEqual(calls, "", action)
