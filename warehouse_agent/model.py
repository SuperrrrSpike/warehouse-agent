from __future__ import annotations

import json
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import TransformedTargetRegressor
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .monitoring import build_drift_report, enforce_model_gate, evaluate_model_gate


FEATURES = [
    "pick_lines",
    "total_units",
    "unique_skus",
    "unique_locations",
    "mapped_pick_count",
    "mapping_rate",
    "aisle_count",
    "floor_count",
    "x_mean",
    "y_mean",
    "x_std",
    "y_std",
    "x_range",
    "y_range",
    "abc_a_share",
    "product_mapping_rate",
    "order_count",
    "customer_count",
    "ordered_units",
    "weekday",
    "month",
]
TARGET = "route_distance_proxy"
RANDOM_STATE = 42
MODEL_VERSION = "1.2.0"


def _load_regression_baseline(root_dir: Path) -> dict:
    path = root_dir / "models" / "route_distance" / "regression_baseline.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少模型回归基线：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_saved_model(root_dir: Path) -> dict:
    metadata_path = root_dir / "models" / "route_distance" / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"缺少模型元数据：{metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    report = evaluate_model_gate(
        metadata["test_metrics"],
        metadata["mae_improvement_vs_median_pct"],
        _load_regression_baseline(root_dir),
        target=metadata["target"],
    )
    enforce_model_gate(report)
    return report


def _candidate_estimators() -> dict:
    return {
        "ridge": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", Ridge(alpha=10.0)),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=260,
                        min_samples_leaf=3,
                        max_features=0.8,
                        n_jobs=-1,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        learning_rate=0.06,
                        max_iter=300,
                        max_leaf_nodes=24,
                        l2_regularization=1.0,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
    }


def train_route_model(root_dir: Path) -> tuple[Path, Path]:
    feature_path = root_dir / "data" / "processed" / "wave_features.csv"
    if not feature_path.exists():
        raise FileNotFoundError("缺少 wave_features.csv，请先运行 prepare-real-data")
    data = pd.read_csv(feature_path, parse_dates=["created_at"])
    data = data.loc[data["eligible_for_training"].astype(str).str.lower().isin(["true", "1"])].copy()
    data = data.dropna(subset=[TARGET, "created_at"]).sort_values(["created_at", "wave_number"])
    if len(data) < 500:
        raise ValueError(f"可训练波次不足：{len(data)}，至少需要 500 条")

    train_end = int(len(data) * 0.70)
    validation_end = int(len(data) * 0.85)
    train = data.iloc[:train_end]
    validation = data.iloc[train_end:validation_end]
    test = data.iloc[validation_end:]

    candidates = _candidate_estimators()

    validation_results = {}
    validation_error_p90 = {}
    for name, estimator in candidates.items():
        wrapped = TransformedTargetRegressor(
            regressor=estimator,
            func=np.log1p,
            inverse_func=np.expm1,
            check_inverse=False,
        )
        wrapped.fit(train[FEATURES], train[TARGET])
        prediction = np.maximum(wrapped.predict(validation[FEATURES]), 0)
        validation_results[name] = _metrics(validation[TARGET], prediction)
        validation_error_p90[name] = float(
            np.quantile(np.abs(validation[TARGET].to_numpy() - prediction), 0.90)
        )

    selected_name = min(validation_results, key=lambda name: validation_results[name]["mae"])
    selected = TransformedTargetRegressor(
        regressor=candidates[selected_name],
        func=np.log1p,
        inverse_func=np.expm1,
        check_inverse=False,
    )
    train_validation = data.iloc[:validation_end]
    selected.fit(train_validation[FEATURES], train_validation[TARGET])
    test_prediction = np.maximum(selected.predict(test[FEATURES]), 0)
    test_metrics = _metrics(test[TARGET], test_prediction)

    baseline = DummyRegressor(strategy="median")
    baseline.fit(train_validation[FEATURES], train_validation[TARGET])
    baseline_prediction = baseline.predict(test[FEATURES])
    baseline_metrics = _metrics(test[TARGET], baseline_prediction)
    improvement = (
        (baseline_metrics["mae"] - test_metrics["mae"]) / baseline_metrics["mae"] * 100
        if baseline_metrics["mae"]
        else 0.0
    )
    drift_report = build_drift_report(
        train,
        test,
        FEATURES,
        reference_date_range=_date_range(train),
        current_date_range=_date_range(test),
        expected_shift_features=["month"],
    )
    gate_report = evaluate_model_gate(
        test_metrics,
        improvement,
        _load_regression_baseline(root_dir),
        target=TARGET,
    )
    enforce_model_gate(gate_report)

    importance = permutation_importance(
        selected,
        test[FEATURES],
        test[TARGET],
        scoring="neg_mean_absolute_error",
        n_repeats=5,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    importance_frame = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance_mean": importance.importances_mean,
            "importance_std": importance.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)

    model_dir = root_dir / "models" / "route_distance"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.joblib"
    metadata_path = model_dir / "metadata.json"
    importance_path = model_dir / "feature_importance.csv"
    drift_path = model_dir / "drift_report.json"
    gate_path = model_dir / "model_gate.json"
    bundle = {
        "model": selected,
        "features": FEATURES,
        "target": TARGET,
        "model_version": MODEL_VERSION,
        "selected_model": selected_name,
        "uncertainty_abs_error_p90": validation_error_p90[selected_name],
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(bundle, model_path)
    importance_frame.to_csv(importance_path, index=False)

    quality_path = root_dir / "data" / "processed" / "data_quality_report.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
    metadata = {
        "model_name": "wave_route_distance_estimator",
        "model_version": MODEL_VERSION,
        "selected_algorithm": selected_name,
        "business_use": "Estimate picking-wave travel workload before execution for capacity planning.",
        "target": TARGET,
        "target_limitations": (
            "Target is a deterministic Manhattan route proxy derived from the source pick sequence, "
            "not an observed travel-time measurement."
        ),
        "features": FEATURES,
        "dataset": {
            "name": "Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company",
            "doi": "10.17632/pf2w725pw3.1",
            "license": "CC BY 4.0",
        },
        "split_strategy": "chronological 70% train / 15% validation / 15% test by wave creation time",
        "feature_sha256": quality.get("feature_sha256"),
        "rows": {
            "eligible": int(len(data)),
            "train": int(len(train)),
            "validation": int(len(validation)),
            "test": int(len(test)),
        },
        "date_ranges": {
            "train": _date_range(train),
            "validation": _date_range(validation),
            "test": _date_range(test),
        },
        "validation_candidates": validation_results,
        "test_metrics": test_metrics,
        "test_error_slices": _error_slices(test, test_prediction),
        "baseline_metrics": baseline_metrics,
        "mae_improvement_vs_median_pct": float(improvement),
        "drift": {
            "status": drift_report["status"],
            "status_counts": drift_report["status_counts"],
            "raw_status_counts": drift_report["raw_status_counts"],
            "expected_shift_features": drift_report["expected_shift_features"],
            "report_path": "drift_report.json",
        },
        "model_gate": gate_report,
        "uncertainty": {
            "method": "90th percentile of absolute validation residuals before final refit",
            "absolute_error_p90": validation_error_p90[selected_name],
            "coverage_note": "Operational planning interval; not a formal probabilistic guarantee.",
        },
        "top_features": importance_frame.head(10).to_dict(orient="records"),
        "runtime": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "trained_at": bundle["trained_at"],
    }
    drift_path.write_text(
        json.dumps(drift_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    gate_path.write_text(
        json.dumps(gate_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_model_card(model_dir / "MODEL_CARD.md", metadata)
    return model_path, metadata_path


def score_waves(root_dir: Path) -> Path:
    feature_path = root_dir / "data" / "processed" / "wave_features.csv"
    model_path = root_dir / "models" / "route_distance" / "model.joblib"
    if not feature_path.exists() or not model_path.exists():
        raise FileNotFoundError("缺少特征或模型，请先运行完整 ML pipeline")
    data = pd.read_csv(feature_path, parse_dates=["created_at"])
    bundle = joblib.load(model_path)
    eligible = data["eligible_for_training"].astype(str).str.lower().isin(["true", "1"])
    scored = data.loc[eligible, ["wave_number", "created_at", "operator", TARGET] + FEATURES].copy()
    scored["predicted_route_distance"] = np.maximum(
        bundle["model"].predict(scored[bundle["features"]]), 0
    )
    interval = float(bundle.get("uncertainty_abs_error_p90", 0.0))
    scored["prediction_lower_p90"] = np.maximum(scored["predicted_route_distance"] - interval, 0)
    scored["prediction_upper_p90"] = scored["predicted_route_distance"] + interval
    scored["absolute_error"] = np.abs(scored[TARGET] - scored["predicted_route_distance"])
    p50, p75, p90 = scored["predicted_route_distance"].quantile([0.50, 0.75, 0.90])
    scored["workload_band"] = pd.cut(
        scored["predicted_route_distance"],
        bins=[-np.inf, p50, p75, p90, np.inf],
        labels=["normal", "elevated", "high", "critical"],
        include_lowest=True,
    ).astype(str)
    critical_location_threshold = float(scored["unique_locations"].quantile(0.90))
    long_axis_threshold = float(scored["y_range"].quantile(0.75))
    scored["recommended_action"] = scored.apply(
        lambda row: _recommended_action(row, critical_location_threshold, long_axis_threshold),
        axis=1,
    )
    scored["model_version"] = bundle.get("model_version", MODEL_VERSION)
    scored["scored_at"] = datetime.now(timezone.utc).isoformat()

    output = root_dir / "data" / "processed" / "wave_scores.csv"
    scored.to_csv(output, index=False)
    action_queue = (
        scored.loc[
            scored["workload_band"].isin(["high", "critical"]),
            [
                "wave_number",
                "created_at",
                "workload_band",
                "predicted_route_distance",
                "prediction_lower_p90",
                "prediction_upper_p90",
                "pick_lines",
                "unique_skus",
                "unique_locations",
                "mapping_rate",
                "recommended_action",
            ],
        ]
        .sort_values(["predicted_route_distance", "wave_number"], ascending=[False, True])
        .reset_index(drop=True)
    )
    action_queue.insert(0, "priority_rank", np.arange(1, len(action_queue) + 1))
    action_queue_path = root_dir / "reports" / "wave_action_queue.csv"
    action_queue_path.parent.mkdir(parents=True, exist_ok=True)
    action_queue.to_csv(action_queue_path, index=False)
    with sqlite3.connect(root_dir / "data" / "warehouse_real.db") as conn:
        scored.to_sql("wave_predictions", conn, if_exists="replace", index=False)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wave_predictions_band ON wave_predictions(workload_band)"
        )
    return output


def _metrics(actual, prediction) -> dict:
    actual_array = np.asarray(actual, dtype=float)
    prediction_array = np.asarray(prediction, dtype=float)
    return {
        "mae": float(mean_absolute_error(actual_array, prediction_array)),
        "rmse": float(np.sqrt(mean_squared_error(actual_array, prediction_array))),
        "r2": float(r2_score(actual_array, prediction_array)),
        "median_absolute_error": float(np.median(np.abs(actual_array - prediction_array))),
    }


def _date_range(frame: pd.DataFrame) -> dict:
    return {
        "start": frame["created_at"].min().isoformat(),
        "end": frame["created_at"].max().isoformat(),
    }


def _error_slices(frame: pd.DataFrame, prediction: np.ndarray) -> dict:
    evaluated = frame[[TARGET, "mapping_rate"]].copy()
    evaluated["prediction"] = prediction
    evaluated["workload_quartile"] = pd.qcut(
        evaluated[TARGET], q=4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop"
    )
    evaluated["mapping_band"] = pd.cut(
        evaluated["mapping_rate"],
        bins=[0.79, 0.90, 0.99, 1.01],
        labels=["80%-90%", "90%-99%", "100%"],
        include_lowest=True,
    )

    def summarize(column: str) -> dict:
        result = {}
        for name, group in evaluated.groupby(column, observed=True):
            result[str(name)] = {
                "rows": int(len(group)),
                **_metrics(group[TARGET], group["prediction"]),
            }
        return result

    return {
        "by_actual_workload_quartile": summarize("workload_quartile"),
        "by_location_mapping_rate": summarize("mapping_band"),
    }


def _recommended_action(
    row: pd.Series, critical_location_threshold: float, long_axis_threshold: float
) -> str:
    if row["workload_band"] == "critical" and row["unique_locations"] >= critical_location_threshold:
        return "按库区或巷道拆分波次，并复核各子波次截止时间"
    if row["workload_band"] == "critical":
        return "优先分配拣选资源并错峰释放，执行前复核站点容量"
    if row["workload_band"] == "high" and row["y_range"] >= long_axis_threshold:
        return "按纵向库区重排拣选顺序，减少跨区移动"
    if row["workload_band"] == "high":
        return "纳入班前重点波次清单，复核人员与设备资源"
    return "按常规计划执行并监控实际偏差"


def _write_model_card(path: Path, metadata: dict) -> None:
    test = metadata["test_metrics"]
    baseline = metadata["baseline_metrics"]
    top_features = "\n".join(
        f"- `{item['feature']}`：{item['importance_mean']:.3f}"
        for item in metadata["top_features"][:8]
    )
    expected_shifts = "、".join(metadata["drift"]["expected_shift_features"]) or "无"
    content = f"""# 波次路径负荷预测模型卡

## 用途

在波次执行前，根据订单规模、库位空间分布和商品结构估计拣选路线负荷，用于波次拆分、人员排班和拥堵预警。模型不用于评价单个员工。

## 数据与切分

- 数据：Mendeley Data `10.17632/pf2w725pw3.1`，CC BY 4.0。
- 有效波次：{metadata['rows']['eligible']:,}。
- 切分：按创建时间顺序 70% 训练、15% 验证、15% 测试，避免随机切分引起未来信息泄漏。
- 目标：从固定出发点沿原始拣选序列计算的曼哈顿往返距离代理值。

## 最终模型

- 算法：`{metadata['selected_algorithm']}`。
- 测试集 MAE：{test['mae']:.2f} 坐标单位。
- 测试集 RMSE：{test['rmse']:.2f} 坐标单位。
- 测试集 R²：{test['r2']:.3f}。
- 中位数基线 MAE：{baseline['mae']:.2f}。
- 相对基线 MAE 改善：{metadata['mae_improvement_vs_median_pct']:.1f}%。
- 规划区间：预测值 ± {metadata['uncertainty']['absolute_error_p90']:.2f} 坐标单位（基于验证集绝对误差 90 分位，不构成统计覆盖保证）。
- 模型回归门禁：`{metadata['model_gate']['status']}`。
- 输入特征漂移：`{metadata['drift']['status']}`（稳定 {metadata['drift']['status_counts']['stable']}、警告 {metadata['drift']['status_counts']['warning']}、告警 {metadata['drift']['status_counts']['alert']}）。
- 预期日历偏移：`{expected_shifts}`；原始 PSI 仍保留在 `drift_report.json`，但不计入可行动状态。

## 主要特征

{top_features}

## 限制与上线门槛

- 目标是依据布局坐标构造的路线代理值，不是真实行走时间；上线前必须用扫描时间、设备轨迹或实际工时重新标定。
- 约 11% 的拣选明细无法映射到库位坐标，训练只保留映射率不低于 80% 的波次。
- 当前没有班次、拥堵、设备状态和员工经验字段，不能用于承诺实际 SLA。
- `wave_action_queue.csv` 仅用于班前容量复核；模型输出必须由现场负责人确认，不能自动评价员工或直接触发生产指令。
- 上线应增加数据漂移、误差分层、模型版本、人工回退和定期再训练机制。
"""
    path.write_text(content, encoding="utf-8")
