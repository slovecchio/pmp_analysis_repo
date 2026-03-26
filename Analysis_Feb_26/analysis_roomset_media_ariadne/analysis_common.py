from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = BASE_DIR.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
MAIN_VISUALS_DIR = OUTPUTS_DIR / "main_visuals"
SHOWROOM_GEOJSON = WORKSPACE_DIR / "files_Geojson/274_final_floor2_october.geojson"
TRAJECTORY_DIR = WORKSPACE_DIR / "traject_file"

TOKEN = os.getenv(
    "ARIADNE_TOKEN",
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VybmFtZSI6ImlrZWFfaG9sYW5kIiwiZXhwIjoxNzkyMDY4MDI3fQ.w7iQydNm-cjCO8WsCgV1tT6fAckzr1YM5idvAEX-ggM",
)
LOCATION_ID = os.getenv("ARIADNE_LOCATION_ID", "48")
STORE_NO = os.getenv("FIXA_STORE_NO", "274")
BIGQUERY_PROJECT = os.getenv("BIGQUERY_PROJECT", "ingka-sot-cfm-dev")

PREFIX_ORDER = ["L", "WS", "KD", "B", "C"]
PREFIX_PLOT_ORDER = ["B", "C", "KD", "L", "OTHER", "WS"]
PREFIX_COLORS = {
    "L": "#4C78A8",
    "WS": "#F58518",
    "KD": "#54A24B",
    "B": "#E45756",
    "C": "#B279A2",
    "OTHER": "#7F7F7F",
}
PREFIX_2DIG = {"L", "B", "SE", "BA", "WS", "K", "KD", "D"}
LABEL_CANDIDATES = ["labels", "label", "type", "category"]
NAME_CANDIDATES = ["name", "roomset", "room_set", "id", "title"]
SHOWROOM_HFB_SEQUENCE = ["HFB 01", "HFB 02", "HFB 03", "HFB 07", "HFB 08", "HFB 05", "HFB 04", "HFB 09"]
METRIC_CRS = "EPSG:3035"


def standardize_location(value: object) -> object:
    if pd.isna(value):
        return value

    text = " ".join(str(value).upper().strip().split())
    if pd.Series([text]).str.fullmatch(r"\d{3,5}\s*-\s*\d{3,5}").iloc[0]:
        return text.replace(" ", "")

    match = pd.Series([text]).str.extract(r"\b([A-Z]{1,3})\s*0*([0-9]{1,2})\b").iloc[0]
    if match.notna().all():
        prefix, number = match[0], match[1]
        if prefix in PREFIX_2DIG:
            number = number.zfill(2)
        return f"{prefix}{number}"

    return text


def classify_prefix(name: object) -> str:
    text = str(name).upper().strip()
    for prefix in PREFIX_ORDER:
        if text.startswith(prefix):
            return prefix
    return "OTHER"


def detect_column(columns: Iterable[str], candidates: list[str], label: str) -> str:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    raise KeyError(f"No {label} column found. Expected one of: {candidates}")


def load_floor_polygons(geojson_path: Path = SHOWROOM_GEOJSON) -> gpd.GeoDataFrame:
    floor = gpd.read_file(geojson_path)
    floor = floor.set_crs(4326) if floor.crs is None else floor.to_crs(4326)
    return floor.to_crs(METRIC_CRS)


def load_roomsets(geojson_path: Path = SHOWROOM_GEOJSON) -> gpd.GeoDataFrame:
    polygons = gpd.read_file(geojson_path)
    polygons = polygons.set_crs(4326) if polygons.crs is None else polygons.to_crs(4326)

    labels_col = detect_column(polygons.columns, LABEL_CANDIDATES, "labels")
    name_col = detect_column(polygons.columns, NAME_CANDIDATES, "name")

    roomsets = polygons.loc[
        polygons[labels_col].astype(str).str.upper().str.contains("ROOMSET", na=False)
    ].copy()
    if roomsets.empty:
        raise ValueError(f"No roomsets found in {geojson_path}")

    roomsets["roomset_name"] = roomsets[name_col].astype(str).str.strip()
    roomsets["roomset_name_std"] = roomsets["roomset_name"].apply(standardize_location)
    roomsets["hfb_zone"] = roomsets.get("parent_1", "").fillna("").astype(str).str.strip().str.upper()

    roomsets = roomsets.to_crs(METRIC_CRS)
    roomsets["area_m2"] = roomsets.geometry.area
    roomsets["centroid_x"] = roomsets.geometry.centroid.x
    roomsets["centroid_y"] = roomsets.geometry.centroid.y
    roomsets["prefix_group"] = roomsets["roomset_name_std"].apply(classify_prefix)

    grouped = (
        roomsets.groupby("roomset_name_std", as_index=False)
        .agg(
            roomset_name=("roomset_name", "first"),
            hfb_zone=("hfb_zone", "first"),
            prefix_group=("prefix_group", "first"),
            area_m2=("area_m2", "sum"),
            centroid_x=("centroid_x", "mean"),
            centroid_y=("centroid_y", "mean"),
            geometry=("geometry", lambda s: s.union_all()),
        )
        .sort_values("roomset_name_std")
        .reset_index(drop=True)
    )
    return gpd.GeoDataFrame(grouped, geometry="geometry", crs=METRIC_CRS)


def infer_location_groups(roomsets: gpd.GeoDataFrame, n_groups: int = 4) -> gpd.GeoDataFrame:
    if roomsets.empty:
        return roomsets.copy()

    result = roomsets.copy()
    sequence_map = {label.upper(): index for index, label in enumerate(SHOWROOM_HFB_SEQUENCE, start=1)}
    result["hfb_sequence_order"] = result["hfb_zone"].map(sequence_map)

    missing_order = result["hfb_sequence_order"].isna()
    if missing_order.any():
        fallback_zones = sorted(result.loc[missing_order, "hfb_zone"].dropna().unique())
        fallback_map = {zone: len(sequence_map) + offset for offset, zone in enumerate(fallback_zones, start=1)}
        result.loc[missing_order, "hfb_sequence_order"] = result.loc[missing_order, "hfb_zone"].map(fallback_map)

    result["hfb_sequence_order"] = result["hfb_sequence_order"].fillna(len(sequence_map) + 99).astype(int)

    unique_steps = min(result["hfb_sequence_order"].nunique(), len(result))
    n_groups = max(1, min(n_groups, unique_steps))
    dense_rank = result["hfb_sequence_order"].rank(method="dense")
    if n_groups == 1:
        result["location_group"] = "G1"
    else:
        result["location_group"] = pd.qcut(
            dense_rank,
            q=n_groups,
            labels=[f"G{i}" for i in range(1, n_groups + 1)],
            duplicates="drop",
        ).astype(str)

    min_order = result["hfb_sequence_order"].min()
    max_order = result["hfb_sequence_order"].max()
    if min_order == max_order:
        result["path_progress"] = 0.0
    else:
        result["path_progress"] = (
            (result["hfb_sequence_order"] - min_order) / (max_order - min_order)
        ).round(4)

    return result.sort_values(["hfb_sequence_order", "roomset_name_std"]).reset_index(drop=True)


def fetch_area_metric(metric: str, value_key: str, start_date: str, end_date: str) -> pd.DataFrame:
    base_url = f"https://api.ariadne.inc/api/v2/locations/{LOCATION_ID}/areas/{metric}"
    params = {
        "token": TOKEN,
        "start": start_date,
        "end": end_date,
        "step": "day",
        "format": "json",
    }

    first_response = requests.get(base_url, params=params, timeout=60)
    first_response.raise_for_status()
    pages = int(first_response.json().get("pages", 1))

    rows: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        response = requests.get(base_url, params={**params, "page": page}, timeout=60)
        response.raise_for_status()
        payload = response.json()

        for area in payload.get("areas", []):
            area_name = area.get("name")
            area_name_std = standardize_location(area_name)
            for entry in area.get("data", []):
                rows.append(
                    {
                        "date": entry.get("date"),
                        "name": area_name,
                        "roomset_name_std": area_name_std,
                        value_key: entry.get(value_key),
                    }
                )

    data = pd.DataFrame(rows)
    if data.empty:
        raise ValueError(f"Ariadne metric '{metric}' returned no data.")

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data[value_key] = pd.to_numeric(data[value_key], errors="coerce")
    return data.dropna(subset=["date", "roomset_name_std", value_key]).copy()


def fetch_area_visitors(start_date: str, end_date: str) -> pd.DataFrame:
    return fetch_area_metric("visitors", "visitors", start_date=start_date, end_date=end_date)


def fetch_area_durations(start_date: str, end_date: str) -> pd.DataFrame:
    return fetch_area_metric("durations", "avg_time", start_date=start_date, end_date=end_date)


def fetch_store_visitors(start_date: str, end_date: str) -> pd.DataFrame:
    base_url = f"https://api.ariadne.inc/api/v2/locations/{LOCATION_ID}/visitors"
    params = {
        "token": TOKEN,
        "start": start_date,
        "end": end_date,
        "step": "day",
        "format": "json",
    }
    response = requests.get(base_url, params=params, timeout=60)
    response.raise_for_status()

    store = pd.DataFrame(response.json().get("data", []))
    if store.empty:
        raise ValueError("Ariadne store visitors returned no data.")

    store["date"] = pd.to_datetime(store["date"], errors="coerce")
    store["store_visitors"] = pd.to_numeric(store["visitors"], errors="coerce")
    return store[["date", "store_visitors"]].dropna(subset=["date", "store_visitors"]).copy()


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return payload["rows"]
    raise ValueError(f"Unsupported JSON structure in {path}")


def load_trajectories(path: Path = TRAJECTORY_DIR) -> pd.DataFrame:
    files = sorted(path.glob("output_trajectories_all_*.json")) if path.is_dir() else [path]
    if not files:
        raise FileNotFoundError(f"No trajectory files found in {path}")

    rows: list[dict[str, Any]] = []
    for file_path in files:
        file_date = file_path.stem.replace("output_trajectories_all_", "")
        for record in _read_json_records(file_path):
            row = dict(record)
            row["source_file"] = file_path.name
            row["file_date"] = file_date
            rows.append(row)

    trajectories = pd.DataFrame(rows)
    if trajectories.empty:
        raise ValueError("Trajectory input is empty.")

    trajectories = trajectories.rename(columns={"latitude": "lat", "longitude": "lon"})
    required_columns = {"hash_id", "floor", "lat", "lon"}
    missing_columns = required_columns - set(trajectories.columns)
    if missing_columns:
        raise KeyError(f"Missing trajectory columns: {missing_columns}")

    trajectories["lat"] = pd.to_numeric(trajectories["lat"], errors="coerce")
    trajectories["lon"] = pd.to_numeric(trajectories["lon"], errors="coerce")
    trajectories["floor"] = pd.to_numeric(trajectories["floor"], errors="coerce")
    trajectories["timestamp"] = pd.to_numeric(trajectories.get("timestamp"), errors="coerce")
    trajectories["ts"] = pd.to_datetime(trajectories["timestamp"], unit="s", errors="coerce")
    trajectories["date"] = pd.to_datetime(trajectories["file_date"], errors="coerce")

    return trajectories.dropna(subset=["hash_id", "floor", "lat", "lon", "date"]).copy()


def assign_points_to_roomsets(
    trajectories: pd.DataFrame,
    roomsets: gpd.GeoDataFrame,
    target_floor: int = 2,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    floor_points = trajectories.loc[trajectories["floor"] == target_floor].copy()
    if floor_points.empty:
        raise ValueError(f"No trajectory points found on floor {target_floor}.")

    floor_points_gdf = gpd.GeoDataFrame(
        floor_points,
        geometry=gpd.points_from_xy(floor_points["lon"], floor_points["lat"]),
        crs=4326,
    ).to_crs(METRIC_CRS)

    joined = gpd.sjoin(
        floor_points_gdf,
        roomsets[["roomset_name", "roomset_name_std", "prefix_group", "location_group", "area_m2", "geometry"]],
        how="inner",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")

    return floor_points, joined


def month_start(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.to_period("M").dt.to_timestamp()


def safe_pct_change(before: float, after: float) -> float:
    if pd.isna(before) or before == 0 or pd.isna(after):
        return float("nan")
    return 100 * (after - before) / before


def permutation_p_value(pre: np.ndarray, post: np.ndarray, n_permutations: int = 4000, seed: int = 42) -> float:
    pre = np.asarray(pre, dtype=float)
    post = np.asarray(post, dtype=float)
    pre = pre[np.isfinite(pre)]
    post = post[np.isfinite(post)]

    if len(pre) == 0 or len(post) == 0:
        return float("nan")

    observed = abs(post.mean() - pre.mean())
    combined = np.concatenate([pre, post])
    n_pre = len(pre)
    rng = np.random.default_rng(seed)

    extreme = 0
    for _ in range(n_permutations):
        shuffled = rng.permutation(combined)
        diff = abs(shuffled[n_pre:].mean() - shuffled[:n_pre].mean())
        if diff >= observed:
            extreme += 1

    return (extreme + 1) / (n_permutations + 1)
