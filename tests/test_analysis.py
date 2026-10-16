import sqlite3
import unittest

from warehouse_agent.analysis import build_daily_snapshot, build_period_snapshot
from warehouse_agent.db import ensure_schema
from warehouse_agent.sample_data import seed_demo_data


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        ensure_schema(self.conn)
        seed_demo_data(
            self.conn,
            start_date="2026-07-24",
            days=7,
            seed=42,
        )

    def tearDown(self):
        self.conn.close()

    def test_week_snapshot_has_consistent_metrics(self):
        snapshot = build_period_snapshot(self.conn, "2026-07-30", days=7)
        self.assertEqual(snapshot["task_count"], 1512)
        self.assertEqual(
            snapshot["task_count"],
            snapshot["completed_task_count"] + snapshot["backlog_count"],
        )
        self.assertEqual(len(snapshot["daily_trends"]), 7)
        self.assertEqual(snapshot["active_robot_count"], 12)
        self.assertEqual(snapshot["active_station_count"], 6)
        self.assertAlmostEqual(
            snapshot["completion_rate_pct"],
            snapshot["completed_task_count"] * 100 / snapshot["task_count"],
        )
        self.assertGreater(len(snapshot["recommendations"]), 0)

    def test_daily_snapshot_is_deterministic(self):
        first = build_daily_snapshot(self.conn, "2026-07-29")
        second = build_daily_snapshot(self.conn, "2026-07-29")
        self.assertEqual(first, second)
        self.assertEqual(first["period_days"], 1)
        self.assertEqual(first["task_count"], 240)

    def test_no_data_returns_actionable_empty_state(self):
        snapshot = build_daily_snapshot(self.conn, "2030-01-01")
        self.assertEqual(snapshot["task_count"], 0)
        self.assertEqual(snapshot["completion_rate_pct"], 0)
        self.assertIn("没有任务数据", snapshot["risk_flags"][0])

    def test_rejects_invalid_date_and_period(self):
        with self.assertRaises(ValueError):
            build_daily_snapshot(self.conn, "2026/07/29")
        with self.assertRaises(ValueError):
            build_period_snapshot(self.conn, "2026-07-30", days=0)

    def test_seed_requires_explicit_reset(self):
        with self.assertRaises(ValueError):
            seed_demo_data(self.conn)
        seed_demo_data(self.conn, seed=42, reset=True)
        count = self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        self.assertEqual(count, 1512)


if __name__ == "__main__":
    unittest.main()
