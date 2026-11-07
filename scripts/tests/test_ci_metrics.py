# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_metrics as m  # noqa: E402

T0 = datetime(2026, 11, 7, 10, 0, tzinfo=timezone.utc)


def ts(minutes_from_start):
    return (T0 + timedelta(minutes=minutes_from_start)).isoformat()


def job(label, start, end):
    return {"labels": [label], "started_at": ts(start), "completed_at": ts(end)}


def run(id_, event, created, conclusion="success", **kw):
    d = {"id": id_, "event": event, "created_at": ts(created), "updated_at": ts(created + 3),
         "conclusion": conclusion, "head_sha": f"sha{id_}", "head_branch": "x"}
    d.update(kw)
    return d


class Metrics(unittest.TestCase):
    def test_runner_minutes_split_by_os(self):
        runs = [run(1, "push", 0)]
        jobs = {1: [job("ubuntu-24.04", 0, 2), job("macos-15", 1, 4), job("windows-2025", 0, 1)]}
        out = m.compute(runs, jobs, now=T0)
        self.assertEqual(out["runner_minutes"]["push"], {"linux": 2.0, "macos": 3.0, "windows": 1.0, "total": 6.0})

    def test_ready_pull_request_wall_time(self):
        runs = [run(1, "pull_request", 0), run(2, "pull_request", 10), run(3, "pull_request", 20, draft=True),
                run(4, "pull_request", 30, conclusion="failure")]
        jobs = {1: [job("ubuntu", 0, 2)], 2: [job("ubuntu", 10, 14)], 3: [job("ubuntu", 20, 21)], 4: [job("ubuntu", 30, 31)]}
        out = m.compute(runs, jobs, now=T0)
        self.assertEqual((out["pr_wall"]["n"], out["pr_wall"]["median"], out["pr_wall"]["p95"]), (2, 3.0, 4.0))

    def test_queue_time_matches_the_push_on_the_sha(self):
        runs = [run(1, "merge_group", 0, head_branch="gh-readonly-queue/develop/pr-7-abc", head_sha="landed"),
                run(2, "merge_group", 5, head_branch="gh-readonly-queue/develop/pr-7-abc", head_sha="retry"),
                run(3, "push", 1, head_sha="landed", updated_at=ts(6))]
        out = m.compute(runs, {}, now=T0)
        self.assertEqual((out["queue_time"]["n"], out["queue_time"]["median"], out["merged_changes"]), (1, 6.0, 1))

    def test_per_change_figures(self):
        runs = [run(1, "merge_group", 0, head_branch="q/pr-1-a"), run(2, "merge_group", 1, head_branch="q/pr-2-a")]
        jobs = {1: [job("macos-15", 0, 2)], 2: [job("ubuntu", 0, 4)]}
        out = m.compute(runs, jobs, now=T0)
        self.assertEqual((out["minutes_per_merged_change"], out["macos_minutes_per_merged_change"]), (3.0, 1.0))

    def test_wasted_share_and_runner_wait(self):
        runs = [run(1, "merge_group", 0), run(2, "merge_group", 0, conclusion="failure")]
        jobs = {1: [job("ubuntu", 1, 3)], 2: [job("ubuntu", 0, 2)]}
        out = m.compute(runs, jobs, now=T0)
        self.assertEqual(out["wasted_share"], 0.5)
        self.assertEqual(out["runner_wait_p90"], {"linux": 1.0})

    def test_green_ref_age(self):
        out = m.compute([], {}, {"coverage": ("a" * 40, T0 - timedelta(hours=5))}, now=T0)
        self.assertEqual(out["green_refs"]["coverage"]["age_hours"], 5.0)

    def test_empty_input_renders(self):
        text = m.render("o/r", 7, m.compute([], {}, now=T0))
        self.assertIn("CI metrics for o/r", text)
        self.assertIn("n/a", text)

    def test_percentile(self):
        self.assertIsNone(m.percentile([], 0.9))
        self.assertEqual(m.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9), 9)

    def test_api_failure_is_a_warning(self):
        from unittest import mock
        with mock.patch.object(m, "fetch", side_effect=RuntimeError("boom")):
            self.assertEqual(m.main(["--repo", "o/r"]), 0)


if __name__ == "__main__":
    unittest.main()
