import csv
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from govmon.client import SyntheticClient  # noqa: E402
from govmon.models import Dataset  # noqa: E402
from govmon.notify import FileOutbox, Notifier  # noqa: E402
from govmon.outputs import write_status  # noqa: E402
from govmon.status import Config, build_status, classify  # noqa: E402

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)


def ds(hours_ago=None, scheduled=True, status="Completed", owner="o@example.com", i="1", name="D"):
    last = None if hours_ago is None else NOW - timedelta(hours=hours_ago)
    return Dataset(f"id-{i}", name, "WS", owner, scheduled, last, status)


class ClassifyTests(unittest.TestCase):
    cfg = Config()

    def state(self, d):
        return classify(d, NOW, self.cfg)[0]

    def test_fresh_dataset_is_healthy(self):
        self.assertEqual(self.state(ds(hours_ago=3)), "Healthy")

    def test_grace_period_absorbs_schedule_jitter(self):
        # 25 hours old: more than 1 day, but inside the 2 hour grace
        self.assertEqual(self.state(ds(hours_ago=25)), "Healthy")

    def test_just_past_grace_is_stale(self):
        self.assertEqual(self.state(ds(hours_ago=26.5)), "Stale")

    def test_unscheduled_dataset_is_never_stale(self):
        self.assertEqual(self.state(ds(hours_ago=24 * 90, scheduled=False)), "Not scheduled")

    def test_never_refreshed(self):
        self.assertEqual(self.state(ds(hours_ago=None)), "Never refreshed")

    def test_failed_beats_age(self):
        self.assertEqual(self.state(ds(hours_ago=1, status="Failed")), "Failed")

    def test_failed_status_is_case_insensitive(self):
        self.assertEqual(self.state(ds(hours_ago=1, status="failed")), "Failed")


class StatusTableTests(unittest.TestCase):
    def test_archive_candidate_threshold(self):
        rows = build_status([ds(hours_ago=24 * 182, i="a"), ds(hours_ago=24 * 184, i="b")], set(), NOW)
        flags = {r.dataset_id: r.archive_candidate for r in rows}
        self.assertEqual(flags, {"id-a": False, "id-b": True})

    def test_unscheduled_abandoned_dataset_is_still_an_archive_candidate(self):
        r = build_status([ds(hours_ago=24 * 300, scheduled=False)], set(), NOW)[0]
        self.assertTrue(r.archive_candidate)
        self.assertEqual(r.state, "Not scheduled")

    def test_missing_owner_goes_to_fallback(self):
        r = build_status([ds(owner=None)], set(), NOW)[0]
        self.assertEqual(r.owner_email, "governance@example.com")

    def test_owner_email_is_normalised(self):
        r = build_status([ds(owner="  Mixed@Example.COM ")], set(), NOW)[0]
        self.assertEqual(r.owner_email, "mixed@example.com")

    def test_monitored_flag_uses_dataset_id_not_name(self):
        a = ds(i="a", name="Same Name")
        b = ds(i="b", name="Same Name")     # duplicate name in another workspace
        rows = {r.dataset_id: r.monitored for r in build_status([a, b], {"id-a"}, NOW)}
        self.assertEqual(rows, {"id-a": True, "id-b": False})

    def test_output_is_sorted_and_complete(self):
        rows = build_status(SyntheticClient(NOW).list_datasets(), set(), NOW)
        self.assertEqual(len(rows), 40)
        self.assertEqual(rows, sorted(rows, key=lambda r: (r.workspace, r.name, r.dataset_id)))


class NotifyTests(unittest.TestCase):
    def rows(self):
        data = [
            ds(hours_ago=100, owner="a@example.com", i="1", name="Late"),                  # stale, monitored
            ds(hours_ago=1, status="Failed", owner="a@example.com", i="2", name="Broke"),  # failed, monitored
            ds(hours_ago=100, owner="b@example.com", i="3", name="Unwatched"),             # stale, NOT monitored
            ds(hours_ago=1, owner="c@example.com", i="4", name="Fine"),                    # healthy, monitored
            ds(hours_ago=500, scheduled=False, owner="d@example.com", i="5", name="Idle"), # unscheduled, monitored
        ]
        return build_status(data, {"id-1", "id-2", "id-4", "id-5"}, NOW)

    def test_only_monitored_problem_datasets_are_emailed(self):
        msgs = Notifier(mode="live").build(self.rows())
        self.assertEqual([m.to[0] for m in msgs], ["a@example.com"])

    def test_one_email_per_owner_listing_all_datasets(self):
        m = Notifier(mode="live").build(self.rows())[0]
        self.assertIn("Late", m.body)
        self.assertIn("Broke", m.body)
        self.assertIn("2 dataset(s)", m.subject)

    def test_test_mode_redirects_and_labels_intended_recipient(self):
        m = Notifier(mode="test", test_recipient="me@example.com").build(self.rows())[0]
        self.assertEqual(m.to, ("me@example.com",))
        self.assertTrue(m.subject.startswith("[TEST - intended for a@example.com]"))

    def test_live_mode_has_no_test_prefix_and_adds_extra_recipients(self):
        m = Notifier(mode="live", extra_recipients=("team@example.com",)).build(self.rows())[0]
        self.assertEqual(m.to, ("a@example.com", "team@example.com"))
        self.assertFalse(m.subject.startswith("[TEST"))

    def test_extra_recipient_equal_to_owner_is_not_duplicated(self):
        m = Notifier(mode="live", extra_recipients=("a@example.com",)).build(self.rows())[0]
        self.assertEqual(m.to, ("a@example.com",))

    def test_bad_mode_rejected(self):
        with self.assertRaises(ValueError):
            Notifier(mode="prod").build(self.rows())

    def test_no_problems_means_no_email(self):
        rows = build_status([ds(hours_ago=1)], {"id-1"}, NOW)
        self.assertEqual(Notifier(mode="live").build(rows), [])

    def test_file_outbox_writes_messages(self):
        with tempfile.TemporaryDirectory() as t:
            paths = FileOutbox(t).send(Notifier(mode="test").build(self.rows()))
            self.assertEqual(len(paths), 1)
            self.assertIn("Subject:", paths[0].read_text(encoding="utf-8"))


class OutputTests(unittest.TestCase):
    def test_fixed_name_and_dated_copy_are_written_and_identical(self):
        rows = build_status(SyntheticClient(NOW).list_datasets(), set(), NOW)
        with tempfile.TemporaryDirectory() as t:
            fixed, dated = write_status(rows, t, NOW)
            self.assertEqual(fixed.name, "DailyRefreshStatus.csv")
            self.assertEqual(dated.name, "DailyRefreshStatus_2026-10-30.csv")
            self.assertEqual(fixed.read_text(), dated.read_text())

    def test_timestamps_use_explicit_format(self):
        rows = build_status([ds(hours_ago=5)], set(), NOW)
        with tempfile.TemporaryDirectory() as t:
            fixed, _ = write_status(rows, t, NOW)
            with open(fixed, newline="") as fh:
                row = list(csv.DictReader(fh))[0]
            self.assertEqual(row["last_refresh_utc"], "2026-10-30 04:00:00")

    def test_never_refreshed_has_blank_age(self):
        rows = build_status([ds(hours_ago=None)], set(), NOW)
        with tempfile.TemporaryDirectory() as t:
            fixed, _ = write_status(rows, t, NOW)
            with open(fixed, newline="") as fh:
                row = list(csv.DictReader(fh))[0]
            self.assertEqual((row["last_refresh_utc"], row["days_since_refresh"]), ("", ""))


class SyntheticClientTests(unittest.TestCase):
    def test_is_deterministic(self):
        a = SyntheticClient(NOW).list_datasets()
        b = SyntheticClient(NOW).list_datasets()
        self.assertEqual(a, b)

    def test_covers_every_state(self):
        states = {r.state for r in build_status(SyntheticClient(NOW).list_datasets(), set(), NOW)}
        self.assertEqual(states, {"Healthy", "Stale", "Failed", "Never refreshed", "Not scheduled"})


if __name__ == "__main__":
    unittest.main()


class ExportTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime, timezone
        from govmon.client import SyntheticClient
        from govmon.export import build_tables
        from govmon.status import Config, build_status
        self.now = datetime(2026, 10, 30, 9, tzinfo=timezone.utc)
        c = SyntheticClient(self.now)
        self.ds = c.list_datasets()
        self.rows = build_status(self.ds, set(), self.now, Config())
        self.hist = {d.dataset_id: c.refresh_history(d) for d in self.ds}
        self.t = build_tables(self.ds, self.hist, self.rows, self.now, Config(), 30)

    def test_latest_snapshot_equals_live_status(self):
        live = {r.dataset_id: r.state for r in self.rows}
        last = max(r["date"] for r in self.t["fact_daily_status"])
        snap = {r["dataset_id"]: r["state"] for r in self.t["fact_daily_status"] if r["date"] == last}
        self.assertEqual(snap, live)

    def test_one_snapshot_row_per_dataset_per_day(self):
        self.assertEqual(len(self.t["fact_daily_status"]), 30 * len(self.ds))
        keys = {(r["date"], r["dataset_id"]) for r in self.t["fact_daily_status"]}
        self.assertEqual(len(keys), 30 * len(self.ds))

    def test_history_is_deterministic_and_matches_last_refresh(self):
        from govmon.client import SyntheticClient
        c2 = SyntheticClient(self.now)
        for d in c2.list_datasets():
            h = c2.refresh_history(d)
            self.assertEqual(h, self.hist[d.dataset_id])
            in_window = d.last_refresh_utc and d.last_refresh_utc >= self.now - timedelta(days=45)
            if in_window:
                self.assertEqual(h[-1].end_utc, d.last_refresh_utc)
            else:
                self.assertEqual(h, [])   # nothing recent: the dataset shows no attempts in the window

    def test_attempt_keys_exist_in_dim(self):
        ids = {r["dataset_id"] for r in self.t["dim_dataset"]}
        self.assertTrue(all(a["dataset_id"] in ids for a in self.t["fact_refresh_attempt"]))
