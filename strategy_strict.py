#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel
from strategy_features import build_roles, baseline_map, attach_roles

HOLDOUT_DAYS = 120
PAIR_MIN_N = 80
HALF_MIN_N = 25
PAIRS = [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (3, 5), (4, 5)]
EVENTS = ["1", "2", "3", "top2", "top3"]


def normalize_method(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.replace(r"[\s　]+", "", regex=True)


def observed(g: pd.DataFrame, ev: str) -> pd.Series:
    if ev in ("1", "2", "3"):
        return (g["finish"] == int(ev)).astype(float)
    return (g["finish"] <= (2 if ev == "top2" else 3)).astype(float)


def expected_all_six(panel: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    """Build race-specific baselines from all six racers' prior same-course strengths."""
    base = baseline_map(roles)
    x = panel.copy()
    for ev in EVENTS:
        raw = pd.Series(
            [base.get((int(r), int(c)), {}).get(ev, np.nan) for r, c in zip(x["regno"], x["actual_course"])],
            index=x.index,
            dtype=float,
        )
        # For unseen racer/course cells, use the holdout course mean only as a fallback.
        fallback = raw.groupby(x["actual_course"]).transform("mean")
        raw = raw.fillna(fallback).fillna(raw.mean())

        # Within each race, exact places must sum to 1 and top2/top3 to 2/3.
        target_sum = 1.0 if ev in ("1", "2", "3") else (2.0 if ev == "top2" else 3.0)
        den = raw.groupby(x["レースコード"]).transform("sum").replace(0, np.nan)
        x[f"exp_{ev}"] = (raw * target_sum / den).clip(0.001, 0.999)
        x[f"obs_{ev}"] = observed(x, ev)
        x[f"resid_{ev}"] = x[f"obs_{ev}"] - x[f"exp_{ev}"]
    return x


def pair_interactions(x: pd.DataFrame, label_col: str, half_cut: pd.Timestamp) -> pd.DataFrame:
    z0 = x.copy()
    z0["half"] = np.where(z0["race_date"] < half_cut, "H1", "H2")
    pieces = []

    for a, b in PAIRS:
        qa = z0[z0["actual_course"].eq(a)][["レースコード", label_col, "outer_special"]].rename(
            columns={label_col: "A", "outer_special": "sa"}
        )
        qb = z0[z0["actual_course"].eq(b)][["レースコード", label_col, "outer_special"]].rename(
            columns={label_col: "B", "outer_special": "sb"}
        )
        pair = qa.merge(qb, on="レースコード")
        pair = pair[
            pair["A"].notna()
            & pair["B"].notna()
            & pair["A"].ne("SAMPLE_LOW")
            & pair["B"].ne("SAMPLE_LOW")
        ]
        if a >= 5:
            pair = pair[pair["sa"].eq(1)]
        if b >= 5:
            pair = pair[pair["sb"].eq(1)]
        if pair.empty:
            continue

        z = z0.merge(pair[["レースコード", "A", "B"]], on="レースコード")
        for tc in range(1, 7):
            zz = z[z["actual_course"].eq(tc)].copy()
            if zz.empty:
                continue
            for ev in EVENTS:
                col = f"resid_{ev}"
                overall = float(zz[col].mean())
                ma = zz.groupby("A", as_index=False)[col].mean().rename(columns={col: "ma"})
                mb = zz.groupby("B", as_index=False)[col].mean().rename(columns={col: "mb"})
                pg = (
                    zz.groupby(["A", "B"], as_index=False)
                    .agg(pair_mean=(col, "mean"), n=(col, "size"), sd=(col, "std"))
                    .merge(ma, on="A")
                    .merge(mb, on="B")
                )
                # Interaction-specific residual: remove both single-type marginal effects.
                pg["interaction_lift_pt"] = pg["pair_mean"] - pg["ma"] - pg["mb"] + overall
                denom = pg["sd"] / np.sqrt(pg["n"])
                pg["t_approx"] = pg["interaction_lift_pt"] / denom.replace(0, np.nan)

                for h in ("H1", "H2"):
                    zh = zz[zz["half"].eq(h)]
                    if zh.empty:
                        pg[f"{h}_lift"] = np.nan
                        pg[f"{h}_n"] = 0
                        continue
                    oh = float(zh[col].mean())
                    mah = zh.groupby("A", as_index=False)[col].mean().rename(columns={col: "mah"})
                    mbh = zh.groupby("B", as_index=False)[col].mean().rename(columns={col: "mbh"})
                    ph = (
                        zh.groupby(["A", "B"], as_index=False)
                        .agg(hmean=(col, "mean"), hn=(col, "size"))
                        .merge(mah, on="A")
                        .merge(mbh, on="B")
                    )
                    ph[f"{h}_lift"] = ph["hmean"] - ph["mah"] - ph["mbh"] + oh
                    ph = ph[["A", "B", f"{h}_lift", "hn"]].rename(columns={"hn": f"{h}_n"})
                    pg = pg.merge(ph, on=["A", "B"], how="left")

                pg["same_sign_halves"] = (
                    pg["H1_lift"].notna()
                    & pg["H2_lift"].notna()
                    & pg["H1_n"].ge(HALF_MIN_N)
                    & pg["H2_n"].ge(HALF_MIN_N)
                    & np.sign(pg["H1_lift"]).eq(np.sign(pg["H2_lift"]))
                    & np.sign(pg["H1_lift"]).eq(np.sign(pg["interaction_lift_pt"]))
                ).astype(int)
                pg = pg[pg["n"].ge(PAIR_MIN_N)]
                if pg.empty:
                    continue
                pg["label_kind"] = label_col
                pg["course_a"] = a
                pg["course_b"] = b
                pg["target_course"] = tc
                pg["event"] = ev
                pg = pg.rename(columns={"A": "type_a", "B": "type_b"})
                pieces.append(
                    pg[
                        [
                            "label_kind", "course_a", "type_a", "course_b", "type_b",
                            "target_course", "event", "n", "interaction_lift_pt", "t_approx",
                            "H1_lift", "H1_n", "H2_lift", "H2_n", "same_sign_halves",
                        ]
                    ]
                )
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def race_paths(x: pd.DataFrame) -> pd.DataFrame:
    fin = x.pivot_table(index="レースコード", columns="actual_course", values="finish", aggfunc="first").reindex(columns=range(1, 7))
    arr = fin.to_numpy(float)
    order = np.argsort(np.where(np.isnan(arr), 99, arr), axis=1)[:, :3] + 1
    out = pd.DataFrame(
        {
            "レースコード": fin.index,
            "course_trifecta": [f"{a}-{b}-{c}" for a, b, c in order],
        }
    )
    date = x.groupby("レースコード")["race_date"].first().rename("race_date")
    out = out.merge(date, on="レースコード", how="left")
    for c in range(1, 6):
        q = x[x["actual_course"].eq(c)][["レースコード", "style"]].rename(columns={"style": f"style{c}"})
        out = out.merge(q, on="レースコード", how="left")
    return out


def path_interactions(x: pd.DataFrame, half_cut: pd.Timestamp) -> pd.DataFrame:
    r = race_paths(x)
    r["half"] = np.where(r["race_date"] < half_cut, "H1", "H2")
    common = r["course_trifecta"].value_counts()
    paths = common[common.ge(120)].index.tolist()
    rows = []

    for a, b in [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4)]:
        z = r[["half", f"style{a}", f"style{b}", "course_trifecta"]].rename(
            columns={f"style{a}": "A", f"style{b}": "B"}
        )
        z = z[z["A"].notna() & z["B"].notna() & z["A"].ne("SAMPLE_LOW") & z["B"].ne("SAMPLE_LOW")].copy()
        for path in paths:
            z["y"] = z["course_trifecta"].eq(path).astype(float)
            overall = float(z["y"].mean())
            ma = z.groupby("A")["y"].mean()
            mb = z.groupby("B")["y"].mean()
            pg = z.groupby(["A", "B"])["y"].agg(["mean", "size", "std"]).reset_index()
            for rr in pg.itertuples(index=False):
                if rr.size < 100:
                    continue
                inter = float(rr.mean - ma.get(rr.A, 0) - mb.get(rr.B, 0) + overall)
                halfs = {}
                for h in ("H1", "H2"):
                    zh = z[z["half"].eq(h)]
                    gh = zh[(zh["A"].eq(rr.A)) & (zh["B"].eq(rr.B))]
                    if len(gh) < HALF_MIN_N:
                        halfs[h] = (np.nan, len(gh))
                        continue
                    ih = float(
                        gh["y"].mean()
                        - zh.groupby("A")["y"].mean().get(rr.A, 0)
                        - zh.groupby("B")["y"].mean().get(rr.B, 0)
                        + zh["y"].mean()
                    )
                    halfs[h] = (ih, len(gh))
                se = float(rr.std / math.sqrt(rr.size)) if pd.notna(rr.std) and rr.std > 0 else np.nan
                same = int(
                    pd.notna(halfs["H1"][0])
                    and pd.notna(halfs["H2"][0])
                    and np.sign(inter) == np.sign(halfs["H1"][0]) == np.sign(halfs["H2"][0])
                )
                rows.append(
                    {
                        "course_a": a, "type_a": rr.A, "course_b": b, "type_b": rr.B,
                        "course_trifecta": path, "n": int(rr.size), "interaction_lift_pt": inter,
                        "t_approx": inter / se if pd.notna(se) and se else np.nan,
                        "H1_lift": halfs["H1"][0], "H1_n": halfs["H1"][1],
                        "H2_lift": halfs["H2"][0], "H2_n": halfs["H2"][1],
                        "same_sign_halves": same,
                    }
                )
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="source/data")
    ap.add_argument("--out", default="artifacts/strategy_strict")
    ap.add_argument("--holdout-days", type=int, default=HOLDOUT_DAYS)
    args = ap.parse_args()
    src = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cards = load_many(str(src / "programs/race_cards/*/*/*.csv"))
    results = load_many(str(src / "results/realtime/*/*/*.csv"))
    title = load_many(str(src / "programs/title/*/*/*.csv"))
    if cards.empty or results.empty:
        raise SystemExit("race_cards/results not found")

    res_long = results_to_long(results)
    if "決まり手" in res_long.columns:
        res_long["決まり手"] = normalize_method(res_long["決まり手"])
    panel = build_panel(cards_to_long(cards), res_long, title)
    panel = panel.dropna(subset=["race_date", "regno", "actual_course", "finish"]).copy()

    end = panel["race_date"].max()
    cutoff = end - pd.Timedelta(days=args.holdout_days)
    half = cutoff + pd.Timedelta(days=args.holdout_days / 2)
    train = panel[panel["race_date"] < cutoff].copy()
    test = panel[panel["race_date"] >= cutoff].copy()
    if train.empty or test.empty:
        raise SystemExit("train/holdout split produced empty data")

    roles = build_roles(train)
    x = attach_roles(test, roles)
    x = expected_all_six(x, roles)

    style = pair_interactions(x, "style", half)
    finish = pair_interactions(x, "finish_role", half)
    paths = path_interactions(x, half)

    top = pd.concat(
        [style.assign(signal="STYLE_PAIR"), finish.assign(signal="FINISH_PAIR")],
        ignore_index=True,
        sort=False,
    )
    if not top.empty:
        top = top[
            top["same_sign_halves"].eq(1)
            & top["n"].ge(100)
            & top["interaction_lift_pt"].abs().ge(0.025)
            & top["t_approx"].abs().ge(1.8)
        ].copy()
        top["score"] = top["t_approx"].abs() * np.sqrt(top["n"])
        top = top.sort_values("score", ascending=False)

    if not paths.empty:
        path_top = paths[
            paths["same_sign_halves"].eq(1)
            & paths["n"].ge(140)
            & paths["interaction_lift_pt"].abs().ge(0.018)
            & paths["t_approx"].abs().ge(1.8)
        ].copy()
        path_top["score"] = path_top["t_approx"].abs() * np.sqrt(path_top["n"])
        path_top = path_top.sort_values("score", ascending=False)
    else:
        path_top = paths

    outputs = {
        "racer_course_roles_train.csv": roles,
        "style_pair_interactions.csv": style,
        "finish_pair_interactions.csv": finish,
        "path_interactions.csv": paths,
        "top_strategy_signals.csv": top,
        "top_path_signals.csv": path_top,
    }
    for name, df in outputs.items():
        df.to_csv(out / name, index=False)

    meta = pd.DataFrame(
        [
            {
                "data_end": str(end.date()),
                "cutoff": str(cutoff.date()),
                "train_races": train["レースコード"].nunique(),
                "holdout_races": test["レースコード"].nunique(),
                "role_rows": len(roles),
                "style_rows": len(style),
                "finish_rows": len(finish),
                "stable_top_signals": len(top),
                "stable_path_signals": len(path_top),
            }
        ]
    )
    meta.to_csv(out / "run_meta.csv", index=False)
    print(meta.to_string(index=False))
    print("\nTOP")
    print(top.head(25).to_string(index=False) if len(top) else "none")
    print("\nPATHS")
    print(path_top.head(25).to_string(index=False) if len(path_top) else "none")


if __name__ == "__main__":
    main()
