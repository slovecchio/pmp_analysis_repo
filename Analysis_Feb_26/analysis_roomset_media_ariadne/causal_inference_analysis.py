"""Causal inference analysis of FIXA maintenance impact on roomset visitors.

Three complementary approaches to estimate the causal effect of maintenance
interventions (FIXA task bursts) on the share of store visitors entering
each roomset:

1. **Difference-in-Differences (DiD)** — panel regression exploiting rooms
   that were *not* treated as a control group to absorb common time shocks.

2. **Synthetic Control Method (SCM)** — for each treated room, build a
   data-driven counterfactual from a weighted combination of untreated rooms
   that best matches the pre-treatment trajectory.

3. **Interrupted Time Series (ITS)** — segmented regression on each treated
   room individually, testing for an immediate level shift and a change in
   trend at the burst date.

Inputs (pre-computed CSVs, no new API / BQ calls):
  - outputs/reformat_investigation/roomset_relative_visitors_daily.csv
  - outputs/reformat_investigation/reformat_candidates_with_significance.csv
  - outputs/reformat_investigation/fixa_tasks.csv

Outputs:
  - outputs/causal_inference/causal_summary.csv          — one row per treated room with results from all 3 methods
  - outputs/causal_inference/did_panel_results.csv        — full DiD regression table
  - outputs/causal_inference/synthetic_control_weights.csv
  - outputs/causal_inference/causal_method_comparison.png — visual comparison
  - outputs/causal_inference/synthetic_control_plots.png  — per-room SCM plots
  - outputs/main_visuals/04_causal_inference_summary.png  — main visual
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
import statsmodels.api as sm
import statsmodels.formula.api as smf

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent / "outputs"
REFORMAT_DIR = BASE_DIR / "reformat_investigation"
OUTPUT_DIR = BASE_DIR / "causal_inference"
MAIN_VISUALS_DIR = BASE_DIR / "main_visuals"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PREFERRED_WINDOW = 14          # days pre/post for DiD / SCM
MIN_OBS_PER_WINDOW = 7         # minimum data points in a window
# For controls in DiD, only use showroom-type rooms (prefix B, L, KD, SE, C, WS, HFB)
SHOWROOM_PREFIXES = ("B", "L", "KD", "SE", "C", "WS", "HFB")
# Maximum number of control rooms per treated room for SCM (speed)
MAX_SCM_CONTROLS = 30
# Number of bootstrap samples for confidence intervals
BOOTSTRAP_N = 1000
SEED = 42


# ===================================================================
# Data loading
# ===================================================================
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (relative_visitors, candidates, tasks)."""
    rv = pd.read_csv(
        REFORMAT_DIR / "roomset_relative_visitors_daily.csv",
        parse_dates=["date"],
    )
    cands = pd.read_csv(
        REFORMAT_DIR / "reformat_candidates_with_significance.csv",
        parse_dates=["change_date"],
    )
    tasks = pd.read_csv(
        REFORMAT_DIR / "fixa_tasks.csv",
    )
    return rv, cands, tasks


def _is_showroom(name: str) -> bool:
    return any(name.startswith(p) for p in SHOWROOM_PREFIXES)


def get_control_rooms(
    rv: pd.DataFrame, tasks: pd.DataFrame, cands: pd.DataFrame
) -> list[str]:
    """Rooms that are showroom-type and had NO burst detected at all."""
    rooms_with_burst = set(cands["roomset_name_std"].unique())
    all_rooms = set(rv["roomset_name_std"].unique())
    controls = sorted(
        r for r in (all_rooms - rooms_with_burst) if _is_showroom(r)
    )
    return controls


# ===================================================================
# 1. Difference-in-Differences (DiD)
# ===================================================================
def run_did_per_room(
    rv: pd.DataFrame,
    treated_room: str,
    change_date: pd.Timestamp,
    control_rooms: list[str],
    window_days: int = PREFERRED_WINDOW,
) -> dict | None:
    """Run DiD regression for one treated room.

    Model:
        y_it = α + γ_i (room FE) + λ_t (day-of-week FE)
             + β_post * Post_t + δ_DID * (Treated_i × Post_t) + ε_it

    δ_DID is the Average Treatment Effect on the Treated (ATT).
    """
    pre_start = change_date - pd.Timedelta(days=window_days)
    post_end = change_date + pd.Timedelta(days=window_days)

    # select rooms
    rooms = [treated_room] + control_rooms
    panel = rv.loc[
        (rv["roomset_name_std"].isin(rooms))
        & (rv["date"] >= pre_start)
        & (rv["date"] <= post_end)
        & (rv["date"] != change_date)  # exclude the burst day itself
    ].copy()

    panel["treated"] = (panel["roomset_name_std"] == treated_room).astype(int)
    panel["post"] = (panel["date"] > change_date).astype(int)
    panel["did"] = panel["treated"] * panel["post"]
    panel["dow"] = panel["date"].dt.dayofweek  # day-of-week control

    # check minimum observations
    n_treated_pre = ((panel["treated"] == 1) & (panel["post"] == 0)).sum()
    n_treated_post = ((panel["treated"] == 1) & (panel["post"] == 1)).sum()
    if n_treated_pre < MIN_OBS_PER_WINDOW or n_treated_post < MIN_OBS_PER_WINDOW:
        return None

    y = panel["relative_visitors_pct"].values
    # design matrix: intercept, post, treated, did, dow dummies, room FE
    try:
        model = smf.ols(
            "relative_visitors_pct ~ post + treated + did + C(dow) + C(roomset_name_std)",
            data=panel,
        ).fit(cov_type="HC1")  # robust SE
    except Exception:
        return None

    did_coef = model.params.get("did", np.nan)
    did_se = model.bse.get("did", np.nan)
    did_pval = model.pvalues.get("did", np.nan)
    ci_lo = model.conf_int().loc["did", 0] if "did" in model.conf_int().index else np.nan
    ci_hi = model.conf_int().loc["did", 1] if "did" in model.conf_int().index else np.nan

    # pre-treatment mean for the treated room
    pre_mean = panel.loc[
        (panel["treated"] == 1) & (panel["post"] == 0),
        "relative_visitors_pct",
    ].mean()

    return {
        "room": treated_room,
        "change_date": change_date,
        "did_att": did_coef,
        "did_se": did_se,
        "did_pvalue": did_pval,
        "did_ci_lo": ci_lo,
        "did_ci_hi": ci_hi,
        "did_pct_effect": 100 * did_coef / pre_mean if pre_mean != 0 else np.nan,
        "pre_mean_treated": pre_mean,
        "n_controls": len(control_rooms),
        "n_obs": len(panel),
        "r_squared": model.rsquared,
    }


# ===================================================================
# 2. Synthetic Control Method (SCM)
# ===================================================================
def run_scm_per_room(
    rv: pd.DataFrame,
    treated_room: str,
    change_date: pd.Timestamp,
    control_rooms: list[str],
    window_days: int = PREFERRED_WINDOW,
) -> dict | None:
    """Synthetic control: find weights on control rooms that minimise
    pre-treatment RMSE against the treated room.  Then the treatment
    effect is (actual - synthetic) in the post period.
    """
    pre_start = change_date - pd.Timedelta(days=window_days)
    post_end = change_date + pd.Timedelta(days=window_days)

    # daily series for treated
    treated_ts = (
        rv.loc[
            (rv["roomset_name_std"] == treated_room)
            & (rv["date"] >= pre_start)
            & (rv["date"] <= post_end)
        ]
        .set_index("date")["relative_visitors_pct"]
        .sort_index()
    )
    if len(treated_ts) < 2 * MIN_OBS_PER_WINDOW:
        return None

    # daily series for controls — pivot to (date × room) matrix
    controls_ts = (
        rv.loc[
            (rv["roomset_name_std"].isin(control_rooms))
            & (rv["date"] >= pre_start)
            & (rv["date"] <= post_end)
        ]
        .pivot_table(index="date", columns="roomset_name_std", values="relative_visitors_pct")
        .sort_index()
    )
    # align dates
    common_dates = treated_ts.index.intersection(controls_ts.index)
    if len(common_dates) < 2 * MIN_OBS_PER_WINDOW:
        return None
    treated_ts = treated_ts.loc[common_dates]
    controls_ts = controls_ts.loc[common_dates]

    # drop controls with too many missing values
    controls_ts = controls_ts.dropna(axis=1, thresh=int(0.8 * len(common_dates)))
    controls_ts = controls_ts.fillna(controls_ts.mean())
    if controls_ts.shape[1] < 2:
        return None

    # limit controls for speed
    if controls_ts.shape[1] > MAX_SCM_CONTROLS:
        # keep the ones with smallest pre-treatment RMSE to treated
        pre_mask = common_dates < change_date
        pre_rmse = ((controls_ts.loc[pre_mask].values - treated_ts.loc[pre_mask].values[:, None]) ** 2).mean(axis=0) ** 0.5
        keep = np.argsort(pre_rmse)[:MAX_SCM_CONTROLS]
        controls_ts = controls_ts.iloc[:, keep]

    # split
    pre_mask = common_dates < change_date
    post_mask = common_dates > change_date

    Y_pre = treated_ts.loc[pre_mask].values
    X_pre = controls_ts.loc[pre_mask].values
    Y_post = treated_ts.loc[post_mask].values
    X_post = controls_ts.loc[post_mask].values

    if len(Y_pre) < MIN_OBS_PER_WINDOW or len(Y_post) < MIN_OBS_PER_WINDOW:
        return None

    n_controls = X_pre.shape[1]

    # optimise weights: min ||Y_pre - X_pre @ w||^2  s.t. w >= 0, sum(w) = 1
    def objective(w: np.ndarray) -> float:
        return float(np.sum((Y_pre - X_pre @ w) ** 2))

    w0 = np.ones(n_controls) / n_controls
    bounds = [(0.0, 1.0)] * n_controls
    constraints = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}

    result = minimize(
        objective, w0, method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-10},
    )
    w_star = result.x

    # synthetic series
    synth_pre = X_pre @ w_star
    synth_post = X_post @ w_star
    pre_rmse = float(np.sqrt(np.mean((Y_pre - synth_pre) ** 2)))

    # treatment effect = actual - synthetic in post period
    gap_post = Y_post - synth_post
    att = float(np.mean(gap_post))
    pre_mean = float(np.mean(Y_pre))

    # placebo p-value: run SCM for each control room and count
    # how many have |gap| >= |treated gap|
    placebo_atts = []
    for c_idx in range(n_controls):
        if w_star[c_idx] < 0.001 and np.random.random() > 0.3:
            continue  # speed: skip zero-weight controls sometimes
        c_room = controls_ts.columns[c_idx]
        c_pre = controls_ts.loc[pre_mask, c_room].values
        # remaining controls (exclude current)
        other_cols = [j for j in range(n_controls) if j != c_idx]
        if len(other_cols) < 2:
            continue
        X_other_pre = X_pre[:, other_cols]
        X_other_post = X_post[:, other_cols]

        def obj_placebo(w: np.ndarray) -> float:
            return float(np.sum((c_pre - X_other_pre @ w) ** 2))

        w0_p = np.ones(len(other_cols)) / len(other_cols)
        bounds_p = [(0.0, 1.0)] * len(other_cols)
        constr_p = {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}
        try:
            res_p = minimize(
                obj_placebo, w0_p, method="SLSQP", bounds=bounds_p,
                constraints=constr_p, options={"maxiter": 500},
            )
            c_synth_post = X_other_post @ res_p.x
            c_actual_post = controls_ts.loc[post_mask, c_room].values
            c_gap = float(np.mean(c_actual_post - c_synth_post))
            placebo_atts.append(c_gap)
        except Exception:
            pass

    # p-value: proportion of placebo effects as extreme as the real one
    if placebo_atts:
        placebo_arr = np.array(placebo_atts)
        scm_pvalue = float(np.mean(np.abs(placebo_arr) >= np.abs(att)))
    else:
        scm_pvalue = np.nan

    return {
        "room": treated_room,
        "change_date": change_date,
        "scm_att": att,
        "scm_pct_effect": 100 * att / pre_mean if pre_mean != 0 else np.nan,
        "scm_pre_rmse": pre_rmse,
        "scm_pvalue_placebo": scm_pvalue,
        "scm_n_controls_used": int((w_star > 0.01).sum()),
        "scm_weights": w_star,
        "scm_control_names": list(controls_ts.columns),
        "scm_synth_pre": synth_pre,
        "scm_synth_post": synth_post,
        "scm_actual_pre": Y_pre,
        "scm_actual_post": Y_post,
        "scm_pre_dates": common_dates[pre_mask],
        "scm_post_dates": common_dates[post_mask],
    }


# ===================================================================
# 3. Interrupted Time Series (ITS)
# ===================================================================
def run_its_per_room(
    rv: pd.DataFrame,
    treated_room: str,
    change_date: pd.Timestamp,
    window_days: int = PREFERRED_WINDOW,
) -> dict | None:
    """Segmented regression on the treated room alone.

    y_t = β₀ + β₁*t + β₂*D_t + β₃*(t - T₀)*D_t + ε_t

    β₂ = immediate level change at intervention
    β₃ = change in slope after intervention
    """
    pre_start = change_date - pd.Timedelta(days=window_days)
    post_end = change_date + pd.Timedelta(days=window_days)

    ts = (
        rv.loc[
            (rv["roomset_name_std"] == treated_room)
            & (rv["date"] >= pre_start)
            & (rv["date"] <= post_end)
            & (rv["date"] != change_date)
        ]
        .sort_values("date")
        .copy()
    )
    if len(ts) < 2 * MIN_OBS_PER_WINDOW:
        return None

    # time index: days since pre_start
    ts["t"] = (ts["date"] - pre_start).dt.days
    t0 = (change_date - pre_start).days
    ts["post"] = (ts["date"] > change_date).astype(int)
    ts["t_since"] = ts["t"].apply(lambda x: max(0, x - t0))  # time since intervention
    ts["dow"] = ts["date"].dt.dayofweek

    try:
        model = smf.ols(
            "relative_visitors_pct ~ t + post + t_since + C(dow)",
            data=ts,
        ).fit(cov_type="HC1")  # Newey-West also good, but HC1 is fine for short series
    except Exception:
        return None

    level_change = model.params.get("post", np.nan)
    level_pval = model.pvalues.get("post", np.nan)
    slope_change = model.params.get("t_since", np.nan)
    slope_pval = model.pvalues.get("t_since", np.nan)

    pre_mean = ts.loc[ts["post"] == 0, "relative_visitors_pct"].mean()

    return {
        "room": treated_room,
        "change_date": change_date,
        "its_level_change": level_change,
        "its_level_pvalue": level_pval,
        "its_slope_change": slope_change,
        "its_slope_pvalue": slope_pval,
        "its_level_pct": 100 * level_change / pre_mean if pre_mean != 0 else np.nan,
        "its_r_squared": model.rsquared,
        "its_n_obs": len(ts),
    }


# ===================================================================
# Plotting
# ===================================================================
def plot_summary_comparison(summary: pd.DataFrame, out_path: Path) -> None:
    """Side-by-side comparison of the three causal estimates per room."""
    rooms = summary["room"].tolist()
    n = len(rooms)
    fig, ax = plt.subplots(figsize=(10, max(4, 0.7 * n)))

    y_pos = np.arange(n)
    bar_h = 0.22

    # DiD
    did_vals = summary["did_pct_effect"].values
    did_lo = summary["did_ci_lo_pct"].values if "did_ci_lo_pct" in summary else did_vals
    did_hi = summary["did_ci_hi_pct"].values if "did_ci_hi_pct" in summary else did_vals
    did_sig = summary["did_pvalue"].values < 0.05

    ax.barh(y_pos + bar_h, did_vals, height=bar_h, color="#2563EB", alpha=0.75, label="DiD (ATT)")
    for i in range(n):
        if did_sig[i]:
            ax.plot(did_vals[i], y_pos[i] + bar_h, "k*", markersize=8, zorder=5)

    # SCM
    scm_vals = summary["scm_pct_effect"].values
    scm_sig = summary["scm_pvalue_placebo"].values < 0.10  # SCM uses 10% threshold typically

    ax.barh(y_pos, scm_vals, height=bar_h, color="#DC2626", alpha=0.75, label="Synthetic Control")
    for i in range(n):
        if scm_sig[i]:
            ax.plot(scm_vals[i], y_pos[i], "k*", markersize=8, zorder=5)

    # ITS
    its_vals = summary["its_level_pct"].values
    its_sig = summary["its_level_pvalue"].values < 0.05

    ax.barh(y_pos - bar_h, its_vals, height=bar_h, color="#16A34A", alpha=0.75, label="ITS (level shift)")
    for i in range(n):
        if its_sig[i]:
            ax.plot(its_vals[i], y_pos[i] - bar_h, "k*", markersize=8, zorder=5)

    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_yticks(y_pos)
    ax.set_yticklabels([f"{r}\n{d.date()}" for r, d in zip(rooms, summary["change_date"])], fontsize=8)
    ax.set_xlabel("Estimated causal effect on relative visitors (%)")
    ax.set_title("Causal inference: three methods compared\n(★ = statistically significant)", fontsize=11)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def plot_scm_panels(scm_results: list[dict], out_path: Path) -> None:
    """One panel per treated room: actual vs synthetic counterfactual."""
    results = [r for r in scm_results if r is not None]
    if not results:
        return

    n = len(results)
    fig, axes = plt.subplots(n, 1, figsize=(11, 3.2 * n), sharex=False)
    if n == 1:
        axes = [axes]

    for ax, r in zip(axes, results):
        pre_dates = r["scm_pre_dates"]
        post_dates = r["scm_post_dates"]
        all_dates = np.concatenate([pre_dates, post_dates])
        actual = np.concatenate([r["scm_actual_pre"], r["scm_actual_post"]])
        synth = np.concatenate([r["scm_synth_pre"], r["scm_synth_post"]])

        ax.plot(all_dates, actual, color="#2563EB", linewidth=1.0, label="Actual")
        ax.plot(all_dates, synth, color="#DC2626", linewidth=1.0, linestyle="--", label="Synthetic control")
        ax.axvline(r["change_date"], color="#FF6B6B", linewidth=1.5, label="Intervention")

        # shade gap
        ax.fill_between(
            post_dates, r["scm_actual_post"], r["scm_synth_post"],
            alpha=0.15, color="#7C3AED", label="Treatment effect",
        )

        att = r["scm_att"]
        pval = r["scm_pvalue_placebo"]
        sig_mark = "★" if pval < 0.10 else ""
        ax.set_title(
            f"{r['room']}  |  burst {r['change_date'].date()}  |  "
            f"SCM effect: {att:+.2f} pp ({r['scm_pct_effect']:+.1f}%)  |  "
            f"p={pval:.3f} {sig_mark}",
            fontsize=9,
        )
        ax.set_ylabel("Visitors / store (%)", fontsize=8)
        ax.legend(fontsize=7, ncols=4, loc="upper left")
        ax.grid(alpha=0.2)

    axes[-1].set_xlabel("Date")
    fig.suptitle("Synthetic Control Method — actual vs counterfactual", fontsize=12, y=1.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


# ===================================================================
# Main
# ===================================================================
def run() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MAIN_VISUALS_DIR.mkdir(parents=True, exist_ok=True)

    rv, cands, tasks = load_data()
    control_rooms = get_control_rooms(rv, tasks, cands)
    print(f"Control rooms (showroom-type, no bursts): {len(control_rooms)}")

    # Only analyse the significant candidates (the ones already displayed)
    sig_cands = cands.loc[cands["is_significant"]].copy()
    if sig_cands.empty:
        print("No significant candidates to analyse.")
        return

    print(f"Treated rooms to analyse: {len(sig_cands)}")
    print()

    did_results: list[dict] = []
    scm_results: list[dict] = []
    its_results: list[dict] = []

    for _, row in sig_cands.iterrows():
        room = row["roomset_name_std"]
        cd = pd.Timestamp(row["change_date"])
        window = max(PREFERRED_WINDOW, int(row.get("burst_days", 1)))

        print(f"--- {room} (burst {cd.date()}, window={window}d) ---")

        # 1. DiD
        did = run_did_per_room(rv, room, cd, control_rooms, window_days=window)
        if did:
            did_results.append(did)
            print(f"  DiD ATT: {did['did_att']:+.3f} pp ({did['did_pct_effect']:+.1f}%), p={did['did_pvalue']:.4f}")
        else:
            print("  DiD: insufficient data")

        # 2. SCM
        scm = run_scm_per_room(rv, room, cd, control_rooms, window_days=window)
        if scm:
            scm_results.append(scm)
            print(f"  SCM ATT: {scm['scm_att']:+.3f} pp ({scm['scm_pct_effect']:+.1f}%), placebo p={scm['scm_pvalue_placebo']:.3f}")
        else:
            print("  SCM: insufficient data")

        # 3. ITS
        its = run_its_per_room(rv, room, cd, window_days=window)
        if its:
            its_results.append(its)
            print(f"  ITS level: {its['its_level_change']:+.3f} pp ({its['its_level_pct']:+.1f}%), p={its['its_level_pvalue']:.4f}")
        else:
            print("  ITS: insufficient data")
        print()

    # --- Merge into a single summary -----------------------------------------------------------
    summary_parts = []
    if did_results:
        df_did = pd.DataFrame(did_results)
        df_did = df_did.rename(columns={c: c for c in df_did.columns})
        summary_parts.append(df_did)
    if scm_results:
        df_scm = pd.DataFrame([{k: v for k, v in r.items() if not isinstance(v, (np.ndarray, list, pd.DatetimeIndex))} for r in scm_results])
        summary_parts.append(df_scm)
    if its_results:
        df_its = pd.DataFrame(its_results)
        summary_parts.append(df_its)

    if not summary_parts:
        print("No methods returned results.")
        return

    # merge all on room + change_date
    summary = summary_parts[0]
    for sp in summary_parts[1:]:
        summary = summary.merge(sp, on=["room", "change_date"], how="outer")

    # compute DiD CI as %
    if "did_ci_lo" in summary.columns and "pre_mean_treated" in summary.columns:
        summary["did_ci_lo_pct"] = 100 * summary["did_ci_lo"] / summary["pre_mean_treated"]
        summary["did_ci_hi_pct"] = 100 * summary["did_ci_hi"] / summary["pre_mean_treated"]

    summary = summary.sort_values("room").reset_index(drop=True)

    # --- Save outputs --------------------------------------------------------------------------
    summary.to_csv(OUTPUT_DIR / "causal_summary.csv", index=False)
    print(f"Saved: {OUTPUT_DIR / 'causal_summary.csv'}")

    if did_results:
        pd.DataFrame(did_results).to_csv(OUTPUT_DIR / "did_panel_results.csv", index=False)
        print(f"Saved: {OUTPUT_DIR / 'did_panel_results.csv'}")

    if scm_results:
        # save weights
        w_rows = []
        for r in scm_results:
            for name, w in zip(r["scm_control_names"], r["scm_weights"]):
                if w > 0.01:
                    w_rows.append({"treated_room": r["room"], "control_room": name, "weight": round(w, 4)})
        if w_rows:
            pd.DataFrame(w_rows).to_csv(OUTPUT_DIR / "synthetic_control_weights.csv", index=False)
            print(f"Saved: {OUTPUT_DIR / 'synthetic_control_weights.csv'}")

    # --- Plots ---------------------------------------------------------------------------------
    print("\nGenerating plots...")

    # Main comparison chart
    plot_cols = ["room", "change_date"]
    for c in ["did_pct_effect", "did_pvalue", "did_ci_lo_pct", "did_ci_hi_pct",
              "scm_pct_effect", "scm_pvalue_placebo",
              "its_level_pct", "its_level_pvalue"]:
        if c not in summary.columns:
            summary[c] = np.nan
        plot_cols.append(c)

    plot_summary_comparison(
        summary[plot_cols].copy(),
        OUTPUT_DIR / "causal_method_comparison.png",
    )
    print(f"Saved: {OUTPUT_DIR / 'causal_method_comparison.png'}")

    import shutil
    shutil.copy2(
        OUTPUT_DIR / "causal_method_comparison.png",
        MAIN_VISUALS_DIR / "04_causal_inference_summary.png",
    )
    print(f"Saved: {MAIN_VISUALS_DIR / '04_causal_inference_summary.png'}")

    # SCM per-room panels
    if scm_results:
        plot_scm_panels(scm_results, OUTPUT_DIR / "synthetic_control_plots.png")
        print(f"Saved: {OUTPUT_DIR / 'synthetic_control_plots.png'}")

    # --- Print summary table -------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("CAUSAL INFERENCE SUMMARY")
    print("=" * 80)
    display_cols = ["room", "change_date"]
    if "did_pct_effect" in summary: display_cols += ["did_pct_effect", "did_pvalue"]
    if "scm_pct_effect" in summary: display_cols += ["scm_pct_effect", "scm_pvalue_placebo"]
    if "its_level_pct" in summary: display_cols += ["its_level_pct", "its_level_pvalue"]
    print(summary[display_cols].to_string(index=False, float_format="%.3f"))
    print()
    print("Methods agreement:")
    for _, row in summary.iterrows():
        sigs = []
        if pd.notna(row.get("did_pvalue")) and row["did_pvalue"] < 0.05:
            sigs.append(f"DiD ({row['did_pct_effect']:+.1f}%)")
        if pd.notna(row.get("scm_pvalue_placebo")) and row["scm_pvalue_placebo"] < 0.10:
            sigs.append(f"SCM ({row['scm_pct_effect']:+.1f}%)")
        if pd.notna(row.get("its_level_pvalue")) and row["its_level_pvalue"] < 0.05:
            sigs.append(f"ITS ({row['its_level_pct']:+.1f}%)")
        n_sig = len(sigs)
        verdict = "STRONG" if n_sig >= 2 else ("MODERATE" if n_sig == 1 else "WEAK")
        print(f"  {row['room']:6s}: {verdict} causal evidence — {', '.join(sigs) if sigs else 'no method significant'}")


if __name__ == "__main__":
    run()
