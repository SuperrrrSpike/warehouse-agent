import unittest
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor

from warehouse_agent.monitoring import (
    ModelGateError,
    build_drift_report,
    calculate_psi,
    enforce_model_gate,
    evaluate_model_gate,
)
from warehouse_agent.model import FEATURES, TARGET, train_route_model, validate_saved_model


class PopulationStabilityTests(unittest.TestCase):
    def test_identical_distribution_is_stable(self):
        values = np.arange(1, 101, dtype=float)

        result = calculate_psi(values, values.copy())

        self.assertAlmostEqual(result["psi"], 0.0, places=9)
        self.assertEqual(result["status"], "stable")

    def test_shifted_distribution_is_alert(self):
        reference = np.arange(1, 101, dtype=float)
        current = np.arange(101, 201, dtype=float)

        result = calculate_psi(reference, current)

        self.assertGreaterEqual(result["psi"], 0.25)
        self.assertEqual(result["status"], "alert")

    def test_constant_feature_detects_value_change(self):
        stable = calculate_psi(np.ones(100), np.ones(100))
        shifted = calculate_psi(np.ones(100), np.full(100, 2.0))

        self.assertEqual(stable["status"], "stable")
        self.assertEqual(shifted["status"], "alert")

    def test_missing_values_are_reported(self):
        result = calculate_psi(
            np.array([1.0, 2.0, np.nan, 4.0]),
            np.array([1.0, np.nan, np.nan, 4.0]),
        )

        self.assertEqual(result["reference_rows"], 4)
        self.assertEqual(result["current_rows"], 4)
        self.assertAlmostEqual(result["reference_missing_rate"], 0.25)
        self.assertAlmostEqual(result["current_missing_rate"], 0.50)


class DriftReportTests(unittest.TestCase):
    def test_report_summarizes_feature_statuses(self):
        reference = pd.DataFrame(
            {"stable": np.arange(100), "shifted": np.arange(100)}
        )
        current = pd.DataFrame(
            {"stable": np.arange(100), "shifted": np.arange(100) + 500}
        )

        report = build_drift_report(reference, current, ["stable", "shifted"])

        self.assertEqual(report["status"], "alert")
        self.assertEqual(report["feature_count"], 2)
        self.assertEqual(report["status_counts"]["alert"], 1)
        self.assertEqual(report["features"]["stable"]["status"], "stable")
        self.assertEqual(report["features"]["shifted"]["status"], "alert")

    def test_report_rejects_missing_feature(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            build_drift_report(
                pd.DataFrame({"x": [1, 2]}),
                pd.DataFrame({"x": [1, 2]}),
                ["x", "missing"],
            )

    def test_expected_calendar_shift_is_reported_but_not_actionable(self):
        reference = pd.DataFrame(
            {"stable": np.arange(100), "month": np.ones(100)}
        )
        current = pd.DataFrame(
            {"stable": np.arange(100), "month": np.full(100, 9.0)}
        )

        report = build_drift_report(
            reference,
            current,
            ["stable", "month"],
            expected_shift_features=["month"],
        )

        self.assertEqual(report["features"]["month"]["status"], "alert")
        self.assertTrue(report["features"]["month"]["expected_shift"])
        self.assertEqual(report["raw_status_counts"]["alert"], 1)
        self.assertEqual(report["actionable_status_counts"]["alert"], 0)
        self.assertEqual(report["status"], "stable")


class ModelGateTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "target": "route_distance_proxy",
            "thresholds": {
                "min_test_r2": 0.80,
                "max_test_mae": 430.0,
                "min_mae_improvement_vs_median_pct": 50.0,
            },
        }

    def test_gate_passes_acceptable_model(self):
        report = evaluate_model_gate(
            {"r2": 0.84, "mae": 368.0},
            65.0,
            self.baseline,
            target="route_distance_proxy",
        )

        self.assertEqual(report["status"], "passed")
        self.assertTrue(all(rule["passed"] for rule in report["rules"]))

    def test_gate_fails_regressed_model(self):
        report = evaluate_model_gate(
            {"r2": 0.20, "mae": 900.0},
            5.0,
            self.baseline,
            target="route_distance_proxy",
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(sum(not rule["passed"] for rule in report["rules"]), 3)
        with self.assertRaises(ModelGateError):
            enforce_model_gate(report)

    def test_gate_rejects_wrong_target(self):
        with self.assertRaisesRegex(ValueError, "target"):
            evaluate_model_gate(
                {"r2": 0.84, "mae": 368.0},
                65.0,
                self.baseline,
                target="actual_minutes",
            )

    def test_checked_in_model_metadata_passes_versioned_gate(self):
        root_dir = Path(__file__).resolve().parents[1]

        report = validate_saved_model(root_dir)

        self.assertEqual(report["status"], "passed")

    def test_validate_model_cli_passes_checked_in_metadata(self):
        root_dir = Path(__file__).resolve().parents[1]

        completed = subprocess.run(
            [sys.executable, "main.py", "validate-model"],
            cwd=root_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("模型回归门禁：PASS", completed.stdout)

    def test_failed_gate_does_not_overwrite_existing_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            processed = root / "data" / "processed"
            model_dir = root / "models" / "route_distance"
            processed.mkdir(parents=True)
            model_dir.mkdir(parents=True)

            rows = 500
            frame = pd.DataFrame(
                {
                    "wave_number": np.arange(rows),
                    "created_at": pd.date_range("2023-01-01", periods=rows, freq="h"),
                    "eligible_for_training": True,
                    TARGET: np.linspace(100.0, 1000.0, rows),
                    **{
                        feature: np.linspace(index + 1.0, index + 10.0, rows)
                        for index, feature in enumerate(FEATURES)
                    },
                }
            )
            frame.to_csv(processed / "wave_features.csv", index=False)
            (processed / "data_quality_report.json").write_text(
                json.dumps({"feature_sha256": "test"}), encoding="utf-8"
            )
            (model_dir / "regression_baseline.json").write_text(
                json.dumps(
                    {
                        "target": TARGET,
                        "thresholds": {
                            "min_test_r2": 2.0,
                            "max_test_mae": 0.0,
                            "min_mae_improvement_vs_median_pct": 100.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            existing_model = model_dir / "model.joblib"
            existing_model.write_bytes(b"existing-model")

            with mock.patch(
                "warehouse_agent.model._candidate_estimators",
                return_value={"dummy": DummyRegressor(strategy="mean")},
            ):
                with self.assertRaises(ModelGateError):
                    train_route_model(root)

            self.assertEqual(existing_model.read_bytes(), b"existing-model")


if __name__ == "__main__":
    unittest.main()
