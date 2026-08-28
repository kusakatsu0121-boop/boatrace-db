#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from adjusted_winrate import POINTS, build_adjusted_tables
from racer_directory import build_panel, cards_to_long, latest_profile, load_many, results_to_long


def _safe_num(s):
    return pd.to_numeric(s, errors="coerce")


def _center_within_race(values: pd.Series, race_code: pd.Series) -> pd.Series:
    return values - values.groupby(race_code).transform("mean")


def _pairwise_accuracy(df: pd.DataFrame, score_col: str) -> float:
    wins = 0.0
    total = 0.0
    for _, g in df.dropna(subset=[score_col, "finish"]).groupby("レースコード"):
        if len(g) < 2:
            continue
        rows = g[[score_col, "finish"]].to_numpy(float)
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                sdiff = rows[i, 0] - rows[j, 0]
                fdiff = rows[j, 1] - rows[i, 1]  # positive means i finished ahead
                if sdiff == 0 or fdiff == 0:
                    continue
                total += 1.0
                if sdiff * fdiff > 0:
                    wins += 1.0
    return wins / total if total else np.nan


def _top_rated_win_rate(df: pd.DataFrame, score_col: str) -> float:
    hit = 0
    n = 0
    for _, g in df.dropna(subset=[score_col, "finish"]).groupby("レースコード"):
        if len(g) < 6:
            continue
        top = g.loc[g[score_col].idxmax()]
        hit += int(float(top["finish"]) == 1.0)
        n += 1
    return hit / n if n else np.nan


def _top_rated_top3_rate(df: pd.DataFrame, score_col: str) -> float:
    hit = 0
    n = 0
    for _, g in df.dropna(subset=[score_col, "finish"]).groupby("レースコード"):
        if len(g) < 6:
            continue
        top = g.loc[g[score_col].idxmax()]
        hit += int(float(top["finish"]) <= 3.0)
        n += 1
    return hit / n if n else np.nan


def _score_model(df: pd.DataFrame, score_col: str, label: str) -> list[dict]:
    z = df.dropna(subset=[score_col, "points", "レースコード"]).copy()
    z = z[z.groupby("レースコード")[score_col].transform("count") >= 6].copy()
    if z.empty:
        return []
    z["pred_centered"] = _center_within_race(z[score_col], z["レースコード"])
    z["actual_centered"] = _center_within_race(z["points"], z["レースコード"])
    mae = float(np.mean(np.abs(z["actual_centered"] - z["pred_centered"])))
    corr = float(z[["pred_centered", "actual_centered"]].corr(method="spearman").iloc[0, 1])
    return [
        {"model": label, "metric": "centered_mae", "value": mae},
        {"model": label, "metric": "spearman_centered", "value": corr},
        {"model": label, "metric": "pairwise_accuracy", "value": _pairwise_accuracy(z, score_col)},
        {"model": label, "metric": "top_rated_win_rate", "value": _top_rated_win_rate(z, score_col)},
        {"model": label, "metric": "top_rated_top3_rate", "value": _top_rated_top3_rate(z, score_col)},
        {"model": label, "metric": "entries_scored", "value": float(len(z))},
        {"model": label, "metric": "races_scored", "value": float(z["レースコード"].nunique())},
    ]


def build_forward_validation(panel: pd.DataFrame, cards_long: pd.DataFrame, holdout_days: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = panel.copy()
    p["race_date"] = pd.to_datetime(p["race_date"], errors="coerce")
    p = p.dropna(subset=["race_date", "regno", "finish", "レースコード"]).copy()
    if p.empty:
        return pd.DataFrame(), pd.DataFrame()

    max_date = p["race_date"].max().normalize()
    cutoff = max_date - pd.Timedelta(days=holdout_days)
    train = p[p["race_date"] < cutoff].copy()
    test = p[p["race_date"] >= cutoff].copy()
    if train.empty or test.empty:
        raise SystemExit("not enough data for requested holdout")

    card_dates = pd.to_datetime(cards_long.get("レース日"), errors="coerce")
    profile_train = latest_profile(cards_long.loc[card_dates < cutoff].copy())
    tables = build_adjusted_tables(train, profile_train)
    ratings = tables["racer_adjusted"].copy()
    keep = [c for c in ["regno", "base_winrate", "current_winrate", "sample_n", "rating_quality", "national_win_rate"] if c in ratings.columns]
    ratings = ratings[keep].rename(columns={"national_win_rate": "official_at_cutoff"})

    test["regno"] = _safe_num(test["regno"]).astype("Int64")
    test = test.dropna(subset=["regno"]).copy()
    test["regno"] = test["regno"].astype(int)
    test["finish"] = _safe_num(test["finish"])
    test["points"] = test["finish"].map(POINTS)
    scored = test.merge(ratings, on="regno", how="left")

    rows = []
    rows += _score_model(scored, "official_at_cutoff", "official_winrate_at_cutoff")
    rows += _score_model(scored, "base_winrate", "normalized_base_winrate")
    rows += _score_model(scored, "current_winrate", "normalized_current_winrate")

    metrics = pd.DataFrame(rows)
    meta = pd.DataFrame([
        {"item": "train_start", "value": str(train["race_date"].min().date())},
        {"item": "train_end", "value": str(train["race_date"].max().date())},
        {"item": "test_start", "value": str(test["race_date"].min().date())},
        {"item": "test_end", "value": str(test["race_date"].max().date())},
        {"item": "holdout_days", "value": str(holdout_days)},
        {"item": "train_races", "value": str(train["レースコード"].nunique())},
        {"item": "test_races", "value": str(test["レースコード"].nunique())},
        {"item": "rated_racers", "value": str(ratings["regno"].nunique())},
    ])
    return metrics, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="source/data")
    ap.add_argument("--out", default="artifacts/racer_directory")
    ap.add_argument("--holdout-days", type=int, default=30)
    args = ap.parse_args()

    src = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cards = load_many(str(src / "programs/race_cards/*/*/*.csv"))
    results = load_many(str(src / "results/realtime/*/*/*.csv"))
    title = load_many(str(src / "programs/title/*/*/*.csv"))
    if cards.empty or results.empty:
        raise SystemExit("required race_cards/results not found")

    cards_long = cards_to_long(cards)
    panel = build_panel(cards_long, results_to_long(results), title)
    metrics, meta = build_forward_validation(panel, cards_long, args.holdout_days)
    metrics.to_csv(out / "model_forward_validation.csv", index=False)
    meta.to_csv(out / "model_forward_validation_meta.csv", index=False)
    print(metrics.to_string(index=False))
    print(meta.to_string(index=False))


if __name__ == "__main__":
    main()
