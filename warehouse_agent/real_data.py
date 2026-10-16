from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


DEPOT_X = 66.0
DEPOT_Y = -29.0


def prepare_wave_features(root_dir: Path) -> tuple[Path, Path]:
    source_dir = root_dir / "data" / "external" / "order_picking_mendeley" / "raw"
    output_dir = root_dir / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    required = [
        "Picking_Wave.csv",
        "Customer_Order.csv",
        "Storage_Location.csv",
        "Product.csv",
    ]
    missing = [name for name in required if not (source_dir / name).exists()]
    if missing:
        raise FileNotFoundError(
            "缺少真实数据文件：" + ", ".join(missing) + "；请先运行 scripts/download_real_dataset.py"
        )

    picking = pd.read_csv(source_dir / "Picking_Wave.csv", sep=";")
    orders = pd.read_csv(source_dir / "Customer_Order.csv", sep=";")
    locations = pd.read_csv(source_dir / "Storage_Location.csv")
    products = pd.read_csv(source_dir / "Product.csv", sep=";")

    picking.columns = [column.strip() for column in picking.columns]
    orders.columns = [column.strip() for column in orders.columns]
    for frame, columns in [
        (picking, ["reference", "locations", "operator"]),
        (orders, ["codCustomer", "Reference", "operator"]),
        (locations, ["originalLocation"]),
        (products, ["Reference", "ABCCOD", "Sector"]),
    ]:
        for column in columns:
            frame[column] = frame[column].astype("string").str.strip()

    orders["created_at"] = pd.to_datetime(
        orders["creationDate"], format="%d/%m/%Y %H:%M", errors="coerce"
    )
    location_lookup = locations[["originalLocation", "x", "y", "z"]].drop_duplicates(
        "originalLocation"
    )
    product_lookup = products[["Reference", "ABCCOD", "Sector"]].drop_duplicates("Reference")
    enriched = picking.merge(
        location_lookup,
        how="left",
        left_on="locations",
        right_on="originalLocation",
        validate="many_to_one",
    ).merge(
        product_lookup,
        how="left",
        left_on="reference",
        right_on="Reference",
        validate="many_to_one",
    )

    records = []
    for wave_number, group in enriched.groupby("waveNumber", sort=True):
        mapped = group.dropna(subset=["x", "y"])
        x = mapped["x"].astype(float)
        y = mapped["y"].astype(float)
        coordinates = mapped[["x", "y"]].astype(float).to_numpy()
        records.append(
            {
                "wave_number": int(wave_number),
                "operator": _single_value(group["operator"]),
                "pick_lines": int(len(group)),
                "total_units": float(group["quantityToPick (units)"].sum()),
                "unique_skus": int(group["reference"].nunique()),
                "unique_locations": int(group["locations"].nunique()),
                "mapped_pick_count": int(len(mapped)),
                "mapping_rate": float(len(mapped) / len(group)),
                "aisle_count": int(mapped["locations"].str[0].nunique()),
                "floor_count": int(mapped["z"].nunique()),
                "x_mean": _safe_mean(x),
                "y_mean": _safe_mean(y),
                "x_std": _safe_std(x),
                "y_std": _safe_std(y),
                "x_range": _safe_range(x),
                "y_range": _safe_range(y),
                "abc_a_share": float((group["ABCCOD"] == "A").mean()),
                "product_mapping_rate": float(group["ABCCOD"].notna().mean()),
                "route_distance_proxy": _route_distance(coordinates),
            }
        )
    waves = pd.DataFrame.from_records(records)

    order_summary = (
        orders.groupby("waveNumber", as_index=False)
        .agg(
            created_at=("created_at", "min"),
            order_count=("orderNumber", "nunique"),
            customer_count=("codCustomer", "nunique"),
            ordered_units=("quantity (units)", "sum"),
        )
        .rename(columns={"waveNumber": "wave_number"})
    )
    waves = waves.merge(order_summary, on="wave_number", how="left", validate="one_to_one")
    waves["weekday"] = waves["created_at"].dt.weekday
    waves["month"] = waves["created_at"].dt.month
    waves["eligible_for_training"] = (
        waves["created_at"].notna()
        & (waves["mapping_rate"] >= 0.80)
        & (waves["mapped_pick_count"] >= 3)
        & (waves["route_distance_proxy"] > 0)
    )
    waves = waves.sort_values(["created_at", "wave_number"], na_position="last").reset_index(drop=True)

    feature_path = output_dir / "wave_features.csv"
    waves.to_csv(feature_path, index=False)
    db_path = root_dir / "data" / "warehouse_real.db"
    with sqlite3.connect(db_path) as conn:
        waves.to_sql("wave_features", conn, if_exists="replace", index=False)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wave_features_date ON wave_features(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wave_features_eligible ON wave_features(eligible_for_training)")

    quality = {
        "source_rows": {
            "picking_wave": int(len(picking)),
            "customer_order": int(len(orders)),
            "storage_location": int(len(locations)),
            "product": int(len(products)),
        },
        "wave_count": int(len(waves)),
        "eligible_wave_count": int(waves["eligible_for_training"].sum()),
        "location_mapping_rate": float(enriched["x"].notna().mean()),
        "product_mapping_rate": float(enriched["ABCCOD"].notna().mean()),
        "missing_order_date_waves": int(waves["created_at"].isna().sum()),
        "duplicate_picking_rows": int(picking.duplicated().sum()),
        "feature_sha256": _sha256(feature_path),
        "target_definition": (
            "Manhattan round-trip distance from depot (66,-29) through the recorded pick sequence; "
            "units follow the source layout coordinate system."
        ),
    }
    quality_path = output_dir / "data_quality_report.json"
    quality_path.write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    return feature_path, quality_path


def _route_distance(coordinates: np.ndarray) -> float:
    if len(coordinates) == 0:
        return 0.0
    depot = np.array([DEPOT_X, DEPOT_Y], dtype=float)
    route = np.vstack([depot, coordinates, depot])
    return float(np.abs(np.diff(route, axis=0)).sum())


def _single_value(series: pd.Series) -> str:
    values = series.dropna().astype(str)
    return values.mode().iloc[0] if not values.empty else "UNKNOWN"


def _safe_mean(series: pd.Series) -> float:
    return float(series.mean()) if len(series) else 0.0


def _safe_std(series: pd.Series) -> float:
    value = series.std(ddof=0) if len(series) else 0.0
    return float(value) if not pd.isna(value) else 0.0


def _safe_range(series: pd.Series) -> float:
    return float(series.max() - series.min()) if len(series) else 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
