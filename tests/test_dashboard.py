import unittest

from warehouse_agent.dashboard import render_dashboard


class DashboardTest(unittest.TestCase):
    def test_dashboard_escapes_dynamic_content(self):
        snapshot = {
            "task_count": 0,
            "completed_task_count": 0,
            "backlog_count": 0,
            "completion_rate_pct": 0.0,
            "throughput_per_day": 0.0,
            "avg_utilization_pct": 0.0,
            "avg_queue_wait_minutes": 0.0,
            "congested_station_count": 0,
            "empty_run_pct": 0.0,
            "total_travel_distance_km": 0.0,
            "active_robot_count": 0,
            "biz_date": "2026-07-30",
            "period_days": 1,
            "risk_flags": ["<script>alert(1)</script>"],
            "recommendations": ["安全检查"],
            "top_congested_stations": [],
            "top_robot_exceptions": [],
            "daily_trends": [],
        }
        html = render_dashboard(snapshot, "测试看板")
        self.assertIn("测试看板", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
