from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


PSI_WARNING_THRESHOLD = 0.10
PSI_ALERT_THRESHOLD = 0.25
_EPSILON = 1e-6


class ModelGateError(ValueError):
    """Raised when a trained model fails a publication threshold."""


def _numeric_array(values: Iterable[float], label: str) -> np.ndarray:
    raw = pd.Series(values, copy=False)
    numeric = pd.to_numeric(raw, errors="coerce")
    introduced_missing = numeric.isna() & raw.notna()
    if introduced_missing.any():
        raise ValueError(f"{label} contains non-numeric values")
    if numeric.notna().sum() == 0:
        raise ValueError(f"{label} contains no numeric observations")
    return numeric.to_numpy(dtype=float)


def _reference_edges(reference: np.ndarray, bins: int) -> np.ndarray:
    observed = reference[~np.isnan(reference)]
    unique = np.unique(observed)
    if len(unique) == 1:
        center = float(unique[0])
        tolerance = max(abs(center) * 1e-6, 1e-9)
        return np.array([-np.inf, center - tolerance, center + tolerance, np.inf])
    quantiles = np.quantile(observed, np.linspace(0.0, 1.0, bins + 1))
    interior = np.unique(quantiles[1:-1])
    return np.concatenate(([-np.inf], interior, [np.inf]))


def _distribution(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    observed = values[~np.isnan(values)]
    counts, _ = np.histogram(observed, bins=edges)
    missing_count = int(np.isnan(values).sum())
    distribution = np.append(counts.astype(float), missing_count) / len(values)
    return np.clip(distribution, _EPSILON, None)


def calculate_psi(
    reference_values: Iterable[float],
    current_values: Iterable[float],
    *,
    bins: int = 10,
) -> dict:
    """Calculate PSI using reference quantile bins and a missing-value bucket."""
    if bins < 2:
        raise ValueError("bins must be at least 2")
    reference = _numeric_array(reference_values, "reference")
    current = _numeric_array(current_values, "current")
    edges = _reference_edges(reference, bins)
    reference_distribution = _distribution(reference, edges)
    current_distribution = _distribution(current, edges)
    psi = float(
        np.sum(
            (current_distribution - reference_distribution)
            * np.log(current_distribution / reference_distribution)
        )
    )
    if psi >= PSI_ALERT_THRESHOLD:
        status = "alert"
    elif psi >= PSI_WARNING_THRESHOLD:
        status = "warning"
    else:
        status = "stable"
    return {
        "psi": psi,
        "status": status,
        "reference_rows": int(len(reference)),
        "current_rows": int(len(current)),
        "reference_mean": float(np.nanmean(reference)),
        "current_mean": float(np.nanmean(current)),
        "reference_missing_rate": float(np.isnan(reference).mean()),
        "current_missing_rate": float(np.isnan(current).mean()),
        "bin_count": int(len(edges) - 1),
    }


def build_drift_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    features: list[str],
    *,
    reference_date_range: dict | None = None,
    current_date_range: dict | None = None,
    expected_shift_features: list[str] | None = None,
) -> dict:
    missing = sorted(
        set(features) - set(reference.columns) | set(features) - set(current.columns)
    )
    if missing:
        raise ValueError(f"Drift features missing: {missing}")
    expected_shifts = set(expected_shift_features or [])
    unknown_expected = sorted(expected_shifts - set(features))
    if unknown_expected:
        raise ValueError(f"Expected-shift features missing: {unknown_expected}")
    feature_results = {
        feature: calculate_psi(reference[feature], current[feature])
        for feature in features
    }
    for feature, result in feature_results.items():
        result["expected_shift"] = feature in expected_shifts
    raw_status_counts = {
        status: sum(result["status"] == status for result in feature_results.values())
        for status in ("stable", "warning", "alert")
    }
    actionable_status_counts = {
        status: sum(
            result["status"] == status and not result["expected_shift"]
            for result in feature_results.values()
        )
        for status in ("stable", "warning", "alert")
    }
    status_counts = actionable_status_counts
    status = "alert" if status_counts["alert"] else (
        "warning" if status_counts["warning"] else "stable"
    )
    return {
        "status": status,
        "method": "population_stability_index",
        "thresholds": {
            "warning": PSI_WARNING_THRESHOLD,
            "alert": PSI_ALERT_THRESHOLD,
        },
        "threshold_note": (
            "Engineering warning thresholds; they are not statistical significance tests. "
            "Expected calendar shifts remain visible but do not set the actionable status."
        ),
        "feature_count": len(features),
        "reference_rows": int(len(reference)),
        "current_rows": int(len(current)),
        "reference_date_range": reference_date_range,
        "current_date_range": current_date_range,
        "expected_shift_features": sorted(expected_shifts),
        "raw_status_counts": raw_status_counts,
        "actionable_status_counts": actionable_status_counts,
        "status_counts": status_counts,
        "features": feature_results,
    }


def evaluate_model_gate(
    test_metrics: dict,
    mae_improvement_vs_median_pct: float,
    baseline: dict,
    *,
    target: str,
) -> dict:
    if baseline.get("target") != target:
        raise ValueError(
            f"Model gate target mismatch: expected {baseline.get('target')!r}, got {target!r}"
        )
    thresholds = baseline.get("thresholds", {})
    required = {
        "min_test_r2",
        "max_test_mae",
        "min_mae_improvement_vs_median_pct",
    }
    missing = required - set(thresholds)
    if missing:
        raise ValueError(f"Model gate thresholds missing: {sorted(missing)}")
    rules = [
        {
            "name": "test_r2",
            "operator": ">=",
            "actual": float(test_metrics["r2"]),
            "threshold": float(thresholds["min_test_r2"]),
            "passed": float(test_metrics["r2"]) >= float(thresholds["min_test_r2"]),
        },
        {
            "name": "test_mae",
            "operator": "<=",
            "actual": float(test_metrics["mae"]),
            "threshold": float(thresholds["max_test_mae"]),
            "passed": float(test_metrics["mae"]) <= float(thresholds["max_test_mae"]),
        },
        {
            "name": "mae_improvement_vs_median_pct",
            "operator": ">=",
            "actual": float(mae_improvement_vs_median_pct),
            "threshold": float(thresholds["min_mae_improvement_vs_median_pct"]),
            "passed": float(mae_improvement_vs_median_pct)
            >= float(thresholds["min_mae_improvement_vs_median_pct"]),
        },
    ]
    return {
        "status": "passed" if all(rule["passed"] for rule in rules) else "failed",
        "target": target,
        "rules": rules,
    }


def enforce_model_gate(report: dict) -> None:
    if report.get("status") == "passed":
        return
    failed = [rule["name"] for rule in report.get("rules", []) if not rule["passed"]]
    raise ModelGateError(f"Model regression gate failed: {', '.join(failed)}")
