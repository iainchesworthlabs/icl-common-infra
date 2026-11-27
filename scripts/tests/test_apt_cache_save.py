# SPDX-License-Identifier: GPL-3.0-or-later
"""The save step of the package cache of setup-gcc, setup-llvm and setup-qt.

The install scripts keep the .deb files they download in a directory under $HOME and leave a `.new` marker there. The
save step must run when the marker is there. A `hashFiles()` test of the marker cannot do that: the function reads only
files under GITHUB_WORKSPACE, so it was always empty and the cache was never saved. These tests check that the action
tests an output instead, that no `hashFiles` is left in the three, and that the step that sets the output does it."""
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
