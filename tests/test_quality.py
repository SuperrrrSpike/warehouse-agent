import sqlite3
import unittest

from warehouse_agent.db import ensure_schema
from warehouse_agent.quality import run_quality_checks
from warehouse_agent.sample_data import seed_demo_data


class QualityTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        ensure_schema(self.conn)
        seed_demo_data(self.conn, seed=42)

    def tearDown(self):
        self.conn.close()

    def test_sample_data_passes_quality_checks(self):
        result = run_quality_checks(self.conn)
        self.assertTrue(result["passed"])
        self.assertEqual(result["violation_count"], 0)

    def test_detects_invalid_empty_run_distance(self):
        task_id = self.conn.execute("SELECT task_id FROM tasks LIMIT 1").fetchone()[0]
        self.conn.execute(
            "UPDATE tasks SET empty_run_distance_m = travel_distance_m + 1 WHERE task_id = ?",
            (task_id,),
        )
        result = run_quality_checks(self.conn)
        failed = {item["name"] for item in result["checks"] if not item["passed"]}
        self.assertIn("empty_run_exceeds_total", failed)


if __name__ == "__main__":
    unittest.main()
