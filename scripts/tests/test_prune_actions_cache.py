# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os
import shutil
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "prune_actions_cache.sh"
def find_bash():
    """bash, and on Windows Git's: the bash.exe on PATH there may be the WSL launcher."""
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
            candidate = Path(base) / "Git" / "bin" / "bash.exe"
            if base and candidate.is_file():
                return str(candidate)
        return None
    return shutil.which("bash")


BASH = find_bash()
HEX16 = "0123456789abcdef"
HEX64 = "0123456789abcdef" * 4


def cache(cache_id, key, ref, created, accessed=None, size=1048576, version="v1"):
    return {
        "id": cache_id,
        "key": key,
        "ref": ref,
        "version": version,
        "sizeInBytes": size,
        "createdAt": created,
        "lastAccessedAt": accessed or created,
    }


@unittest.skipUnless(BASH and shutil.which("jq"), "needs bash and jq")
class Plan(unittest.TestCase):
    def run_plan(self, caches, refs, *extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        caches_file = Path(tmp.name) / "caches.json"
        refs_file = Path(tmp.name) / "refs.txt"
        caches_file.write_text(json.dumps(caches), encoding="utf-8")
        refs_file.write_text("\n".join(refs) + "\n", encoding="utf-8")
        done = subprocess.run(
            [
                BASH,
                SCRIPT.as_posix(),
                "--dry-run",
                "--repo",
                "o/r",
                "--caches-file",
                caches_file.as_posix(),
                "--refs-file",
                refs_file.as_posix(),
                *extra,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return done

    @staticmethod
    def dropped(output):
        """The (reason, id-bearing key prefix) rows of the plan table."""
        rows = []
        for line in output.splitlines():
            if line.startswith("| ") and line.split("|")[1].strip() in ("ref gone", "superseded", "purged"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                rows.append((cells[0], cells[2].strip("`"), cells[3].strip("`")))
        return rows

    def test_entry_of_a_deleted_branch_goes_and_a_live_one_stays(self):
        key = f"vcpkg-binary-cache-x64-linux-{HEX16}"
        done = self.run_plan(
            [
                cache(1, key, "refs/heads/gone", "2026-10-01T00:00:00Z"),
                cache(2, key, "refs/heads/develop", "2026-10-01T00:00:00Z"),
            ],
            ["refs/heads/develop"],
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([(r[0], r[1]) for r in self.dropped(done.stdout)], [("ref gone", "refs/heads/gone")])
        self.assertIn("dry run: nothing deleted.", done.stdout)

    def test_older_generation_of_a_family_is_superseded(self):
        done = self.run_plan(
            [
                cache(1, f"vcpkg-binary-cache-x64-linux-{HEX16}", "refs/heads/develop", "2026-10-01T00:00:00Z"),
                cache(2, "vcpkg-binary-cache-x64-linux-fedcba9876543210", "refs/heads/develop", "2026-10-02T00:00:00Z"),
                cache(3, f"vcpkg-binary-cache-x64-windows-{HEX16}", "refs/heads/develop", "2026-10-01T00:00:00Z"),
            ],
            ["refs/heads/develop"],
            "--grace-minutes",
            "0",
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = self.dropped(done.stdout)
        self.assertEqual([(r[0], r[2]) for r in rows], [("superseded", f"vcpkg-binary-cache-x64-linux-{HEX16}")])

    def test_purge_prefix_goes_on_every_ref(self):
        done = self.run_plan(
            [
                cache(1, f"vcpkg-binary-cache-x64-windows-{HEX16}", "refs/heads/develop", "2026-10-01T00:00:00Z"),
                cache(2, f"vcpkg-binary-cache-x64-linux-{HEX16}", "refs/heads/develop", "2026-10-01T00:00:00Z"),
            ],
            ["refs/heads/develop"],
            "--purge",
            "vcpkg-binary-cache-x64-windows-",
        )
        self.assertEqual([r[0] for r in self.dropped(done.stdout)], ["purged"])

    def test_refuses_to_prune_on_a_list_with_no_branches(self):
        done = self.run_plan([cache(1, "setup-uv-x", "refs/heads/x", "2026-10-01T00:00:00Z")], ["refs/tags/v1"])
        self.assertEqual(done.returncode, 1)
        self.assertIn("refusing to prune", done.stderr)


if __name__ == "__main__":
    unittest.main()
