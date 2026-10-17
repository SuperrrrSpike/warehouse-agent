import unittest

import numpy as np
import pandas as pd

from warehouse_agent.ml_dashboard import render_ml_dashboard
from warehouse_agent.model import _metrics, _recommended_action
from warehouse_agent.real_data import _route_distance


class RealDataFeatureTests(unittest.TestCase):
    def test_route_distance_includes_return_to_depot(self):
        coordinates = np.array([[66.0, -19.0], [76.0, -19.0]])
        self.assertEqual(_route_distance(coordinates), 40.0)

    def test_empty_route_has_zero_distance(self):
        self.assertEqual(_route_distance(np.empty((0, 2))), 0.0)


class ModelDecisionTests(unittest.TestCase):
    def test_metrics_are_zero_for_perfect_prediction(self):
        metrics = _metrics([10, 20, 30], [10, 20, 30])
        self.assertEqual(metrics["mae"], 0.0)
        self.assertEqual(metrics["rmse"], 0.0)
        self.assertEqual(metrics["r2"], 1.0)

    def test_critical_wave_with_many_locations_is_split(self):
        row = pd.Series(
            {"workload_band": "critical", "unique_locations": 40, "y_range": 100}
        )
        action = _recommended_action(row, critical_location_threshold=30, long_axis_threshold=80)
        self.assertIn("拆分波次", action)

    def test_high_wave_with_long_axis_is_reordered(self):
        row = pd.Series({"workload_band": "high", "unique_locations": 10, "y_range": 120})
        action = _recommended_action(row, critical_location_threshold=30, long_axis_threshold=80)
        self.assertIn("重排拣选顺序", action)


class ModelDashboardTests(unittest.TestCase):
    def test_action_text_is_html_escaped(self):
        metadata = {
            "model_version": "1.0.0",
            "rows": {"eligible": 1},
            "test_metrics": {"mae": 10.0, "r2": 0.8},
            "mae_improvement_vs_median_pct": 20.0,
            "top_features": [{"feature": "x_range", "importance_mean": 3.0}],
            "validation_candidates": {
                "ridge": {"mae": 11.0, "rmse": 12.0, "r2": 0.7}
            },
            "selected_algorithm": "ridge",
        }
        quality = {"location_mapping_rate": 0.9}
        scores = pd.DataFrame(
            [
                {
                    "wave_number": 1,
                    "created_at": "2023-01-01 08:00",
                    "pick_lines": 10,
                    "unique_locations": 5,
                    "predicted_route_distance": 100.0,
                    "prediction_lower_p90": 80.0,
                    "prediction_upper_p90": 120.0,
                    "workload_band": "critical",
                    "recommended_action": "<script>alert(1)</script>",
                }
            ]
        )
        html = render_ml_dashboard(metadata, quality, scores)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_dashboard_shows_model_gate_and_drift_summary(self):
        metadata = {
            "model_version": "1.2.0",
            "rows": {"eligible": 100},
            "test_metrics": {"mae": 10.0, "r2": 0.8},
            "mae_improvement_vs_median_pct": 20.0,
            "top_features": [],
            "validation_candidates": {
                "ridge": {"mae": 11.0, "rmse": 12.0, "r2": 0.7}
            },
            "selected_algorithm": "ridge",
            "model_gate": {"status": "passed", "rules": []},
            "drift": {
                "status": "warning",
                "status_counts": {"stable": 16, "warning": 4, "alert": 0},
                "raw_status_counts": {"stable": 16, "warning": 4, "alert": 1},
                "expected_shift_features": ["month"],
            },
        }
        quality = {"location_mapping_rate": 0.9}
        scores = pd.DataFrame(
            [
                {
                    "wave_number": 1,
                    "created_at": "2023-01-01 08:00",
                    "pick_lines": 10,
                    "unique_locations": 5,
                    "predicted_route_distance": 100.0,
                    "prediction_lower_p90": 80.0,
                    "prediction_upper_p90": 120.0,
                    "workload_band": "normal",
                    "recommended_action": "正常监控",
                }
            ]
        )

        html = render_ml_dashboard(metadata, quality, scores)

        self.assertIn("模型回归门禁", html)
        self.assertIn("可行动漂移", html)
        self.assertIn("month", html)


if __name__ == "__main__":
    unittest.main()
