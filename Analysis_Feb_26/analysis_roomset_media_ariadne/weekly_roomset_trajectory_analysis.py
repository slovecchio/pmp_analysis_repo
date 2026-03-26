from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from analysis_common import (
    BASE_DIR,
    SHOWROOM_GEOJSON,
    TRAJECTORY_DIR,
    assign_points_to_roomsets,
    infer_location_groups,
    load_roomsets,
    load_trajectories,
)

OUTPUT_DIR = BASE_DIR / "outputs/weekly_trajectory_analysis"
TARGET_FLOOR = 2


def build_daily_summary(trajectories: pd.DataFrame, joined: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    sample_daily = trajectories.groupby("date", as_index=False).agg(sample_hash_ids=("hash_id", "nunique"))
    roomset_daily = joined.groupby("date", as_index=False).agg(roomset_hash_ids=("hash_id", "nunique"))

    roomsets_per_user = (
        joined.groupby(["date", "hash_id"], as_index=False)
        .agg(roomsets_visited=("roomset_name_std", "nunique"))
    )
    avg_roomsets_per_roomset_visitor = (
        roomsets_per_user.groupby("date", as_index=False)
        .agg(avg_roomsets_per_roomset_visitor=("roomsets_visited", "mean"))
    )

    all_users = trajectories[["date", "hash_id"]].drop_duplicates()
    all_users = all_users.merge(roomsets_per_user, on=["date", "hash_id"], how="left")
    all_users["roomsets_visited"] = all_users["roomsets_visited"].fillna(0)
    avg_roomsets_per_sample_hash_id = (
        all_users.groupby("date", as_index=False)
        .agg(avg_roomsets_per_sample_hash_id=("roomsets_visited", "mean"))
    )

    daily = sample_daily.merge(roomset_daily, on="date", how="left")
    daily = daily.merge(avg_roomsets_per_roomset_visitor, on="date", how="left")
    daily = daily.merge(avg_roomsets_per_sample_hash_id, on="date", how="left")
    daily["roomset_hash_ids"] = daily["roomset_hash_ids"].fillna(0)
    daily["avg_roomsets_per_roomset_visitor"] = daily["avg_roomsets_per_roomset_visitor"].fillna(0)
    daily["avg_roomsets_per_sample_hash_id"] = daily["avg_roomsets_per_sample_hash_id"].fillna(0)
    daily["pct_roomset_hash_ids_vs_sample"] = 100 * daily["roomset_hash_ids"] / daily["sample_hash_ids"].replace(0, pd.NA)
    daily = daily.sort_values("date")

    user_summary = (
        all_users.groupby("hash_id", as_index=False)
        .agg(
            active_days=("date", "nunique"),
            avg_roomsets_visited=("roomsets_visited", "mean"),
            max_roomsets_visited=("roomsets_visited", "max"),
        )
    )
    user_summary["touched_roomset"] = user_summary["max_roomsets_visited"] > 0
    return daily, user_summary.sort_values(["touched_roomset", "avg_roomsets_visited"], ascending=[False, False])


def build_overview(trajectories: pd.DataFrame, joined: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    total_sample_hash_ids = trajectories["hash_id"].nunique()
    total_roomset_hash_ids = joined["hash_id"].nunique() if not joined.empty else 0

    overview = pd.DataFrame(
        [
            {
                "start_date": pd.to_datetime(trajectories["date"]).min().date().isoformat(),
                "end_date": pd.to_datetime(trajectories["date"]).max().date().isoformat(),
                "total_sample_hash_ids": total_sample_hash_ids,
                "total_hash_ids_touching_roomset": total_roomset_hash_ids,
                "pct_hash_ids_touching_roomset": 100 * total_roomset_hash_ids / total_sample_hash_ids if total_sample_hash_ids else 0,
                "avg_daily_sample_hash_ids": daily["sample_hash_ids"].mean(),
                "avg_daily_roomset_hash_ids": daily["roomset_hash_ids"].mean(),
                "avg_daily_pct_hash_ids_touching_roomset": daily["pct_roomset_hash_ids_vs_sample"].mean(),
                "avg_roomsets_per_roomset_visitor": daily["avg_roomsets_per_roomset_visitor"].mean(),
                "avg_roomsets_per_sample_hash_id": daily["avg_roomsets_per_sample_hash_id"].mean(),
            }
        ]
    )
    return overview


def plot_daily_summary(daily: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    axes[0].bar(daily["date"], daily["sample_hash_ids"], color="#CBD5E1", label="Sample hash ids")
    axes[0].bar(daily["date"], daily["roomset_hash_ids"], color="#4C78A8", label="Hash ids touching at least 1 roomset")
    axes[0].set_ylabel("Unique hash ids")
    axes[0].set_title("Trajectory sample size and roomset touch")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].plot(
        daily["date"],
        daily["pct_roomset_hash_ids_vs_sample"],
        color="#F58518",
        marker="o",
        linewidth=2,
        label="Touched at least 1 roomset / sample (%)",
    )
    axes[1].plot(
        daily["date"],
        daily["avg_roomsets_per_roomset_visitor"],
        color="#54A24B",
        marker="o",
        linewidth=2,
        label="Avg roomsets visited per roomset visitor",
    )
    axes[1].plot(
        daily["date"],
        daily["avg_roomsets_per_sample_hash_id"],
        color="#E45756",
        marker="o",
        linewidth=2,
        label="Avg roomsets visited per sample hash id",
    )
    axes[1].set_ylabel("Value")
    axes[1].set_xlabel("Date")
    axes[1].grid(alpha=0.25)
    axes[1].legend()

    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def run(trajectory_path: Path, geojson_path: Path, output_dir: Path, target_floor: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    trajectories = load_trajectories(trajectory_path)
    roomsets = infer_location_groups(load_roomsets(geojson_path), n_groups=4)
    _, joined = assign_points_to_roomsets(trajectories, roomsets, target_floor=target_floor)

    daily, user_summary = build_daily_summary(trajectories, joined)
    overview = build_overview(trajectories, joined, daily)

    daily.to_csv(output_dir / "trajectory_sample_daily_summary.csv", index=False)
    user_summary.to_csv(output_dir / "trajectory_user_summary.csv", index=False)
    overview.to_csv(output_dir / "trajectory_sample_overview.csv", index=False)
    plot_daily_summary(daily, output_dir / "trajectory_sample_size_analysis.png")

    print("=== Trajectory sample analysis ===")
    print(overview.to_string(index=False))
    print("\n=== Daily summary ===")
    print(daily.to_string(index=False))
    print(f"\nSaved: {output_dir / 'trajectory_sample_daily_summary.csv'}")
    print(f"Saved: {output_dir / 'trajectory_user_summary.csv'}")
    print(f"Saved: {output_dir / 'trajectory_sample_overview.csv'}")
    print(f"Saved: {output_dir / 'trajectory_sample_size_analysis.png'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyse the trajectory sample size and roomset touch rate on the showroom floor.")
    parser.add_argument("--trajectories", type=Path, default=TRAJECTORY_DIR, help="Trajectory JSON file or folder.")
    parser.add_argument("--geojson", type=Path, default=SHOWROOM_GEOJSON, help="Showroom GeoJSON file.")
    parser.add_argument("--floor", type=int, default=TARGET_FLOOR, help="Showroom floor number.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Folder where outputs are saved.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        trajectory_path=args.trajectories,
        geojson_path=args.geojson,
        output_dir=args.output_dir,
        target_floor=args.floor,
    )
