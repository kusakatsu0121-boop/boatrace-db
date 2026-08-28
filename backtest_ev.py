#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel
from strategy_features import build_roles

# Pre-registered before reading the OOS return results.
PAIRS = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
LABEL_KINDS = ["style", "finish_role"]
DISCOVERY_MIN_N = 80
DISCOVERY_MIN_EXPECTED = 3.0
DISCOVERY_MIN_HITS = 4
DISCOVERY_MIN_MULT = 1.25
DISCOVERY_MIN_Z = 1.30
DISCOVERY_HALF_MIN_N = 25
DISCOVERY_PRIOR_N = 50.0
PRIMARY_EV = 1.15
PRIMARY_MAX_BETS = 1
START_BANKROLL = 100000.0
KELLY_FRACTION = 0.25
KELLY_RACE_CAP = 0.01
SENSITIVITY_EVS = [1.05, 1.10, 1.15, 1.20, 1.30]
SENSITIVITY_MAX_BETS = [1, 2, 3]

PATHS = list(itertools.permutations(range(1, 7), 3))
PATH_TO_IDX = {p: i for i, p in enumerate(PATHS)}
BOAT_COMBOS = list(itertools.permutations(range(1, 7), 3))
BOAT_TO_IDX = {p: i for i, p in enumerate(BOAT_COMBOS)}
ODDS_COLS = [f"3連単_{a}-{b}-{c}" for a, b, c in BOAT_COMBOS]


def normalize_method(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.replace(r"[\s　]+", "", regex=True)


def stt_to_long(stt: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for boat in range(1, 7):
        cc = f"艇{boat}_コース"
        sc = f"艇{boat}_スタート展示"
        if cc not in stt.columns:
            continue
        cols = ["レースコード", "レース日", cc] + ([sc] if sc in stt.columns else [])
        q = stt[cols].copy().rename(columns={cc: "expo_course", sc: "expo_st"})
        q["boat_no"] = boat
        parts.append(q)
    x = pd.concat(parts, ignore_index=True)
    x["expo_course"] = pd.to_numeric(x["expo_course"], errors="coerce")
    x["expo_st"] = pd.to_numeric(x.get("expo_st"), errors="coerce")
    x["race_date"] = pd.to_datetime(x["レース日"], errors="coerce")
    return x.dropna(subset=["expo_course", "race_date"])


def parse_combo(v):
    try:
        t = tuple(int(z) for z in str(v).replace("=", "-").split("-"))
        return t if len(t) == 3 and len(set(t)) == 3 else None
    except Exception:
        return None


def build_base_races(stt_long: pd.DataFrame, cards_long: pd.DataFrame, odds: pd.DataFrame, payouts: pd.DataFrame):
    card = cards_long[["レースコード", "boat_no", "regno"]].drop_duplicates(["レースコード", "boat_no"], keep="last")
    x = stt_long.merge(card, on=["レースコード", "boat_no"], how="left").dropna(subset=["regno"]).copy()
    x["regno"] = x["regno"].astype(int)

    # Only keep exhibition lineups that are complete permutations of courses 1..6.
    good = x.groupby("レースコード")["expo_course"].agg(lambda s: set(s.astype(int)) == set(range(1, 7)))
    good_codes = good[good].index
    x = x[x["レースコード"].isin(good_codes)].copy()

    base = x[["レースコード", "race_date"]].drop_duplicates("レースコード")
    for c in range(1, 7):
        q = x[x["expo_course"].eq(c)][["レースコード", "boat_no", "regno", "expo_st"]].copy()
        q = q.rename(columns={"boat_no": f"boat_c{c}", "regno": f"reg_c{c}", "expo_st": f"expo_st_c{c}"})
        base = base.merge(q, on="レースコード", how="inner")

    paycols = ["レースコード", "3連単_組番", "3連単_払戻金"]
    pay = payouts[[c for c in paycols if c in payouts.columns]].drop_duplicates("レースコード", keep="last").copy()
    pay["payout"] = pd.to_numeric(pay.get("3連単_払戻金"), errors="coerce")
    pay["winner_boat_combo"] = pay.get("3連単_組番").map(parse_combo)
    pay = pay.dropna(subset=["winner_boat_combo", "payout"])

    odcols = ["レースコード"] + [c for c in ODDS_COLS if c in odds.columns]
    od = odds[odcols].drop_duplicates("レースコード", keep="last").copy()
    for c in ODDS_COLS:
        if c not in od.columns:
            od[c] = np.nan
        od[c] = pd.to_numeric(od[c], errors="coerce")

    base = base.merge(od[["レースコード"] + ODDS_COLS], on="レースコード", how="inner")
    base = base.merge(pay[["レースコード", "payout", "winner_boat_combo"]], on="レースコード", how="inner")
    base = base.sort_values(["race_date", "レースコード"]).reset_index(drop=True)
    return base, x


def attach_fold_roles(base: pd.DataFrame, expo_long: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    rolecols = ["regno", "course", "style", "finish_role", "outer_special"]
    z = expo_long.merge(
        roles[rolecols], left_on=["regno", "expo_course"], right_on=["regno", "course"], how="left"
    ).drop(columns=["course"])
    out = base.copy()
    for c in range(1, 7):
        q = z[z["expo_course"].eq(c)][["レースコード", "style", "finish_role", "outer_special"]].copy()
        q = q.rename(columns={
            "style": f"style_c{c}", "finish_role": f"finish_role_c{c}", "outer_special": f"outer_special_c{c}"
        })
        out = out.merge(q.drop_duplicates("レースコード"), on="レースコード", how="left")
    return out


def odds_in_exhibition_course_order(races: pd.DataFrame):
    boat_odds = races[ODDS_COLS].to_numpy(dtype=float)
    n = len(races)
    out = np.full((n, len(PATHS)), np.nan, dtype=float)
    path_boat_idx = np.full((n, len(PATHS)), -1, dtype=int)
    winner_path = np.full(n, -1, dtype=int)
    cache = {}

    for i, r in enumerate(races.itertuples(index=False)):
        perm = tuple(int(getattr(r, f"boat_c{c}")) for c in range(1, 7))
        if perm not in cache:
            idxs = []
            for a, b, c in PATHS:
                idxs.append(BOAT_TO_IDX[(perm[a - 1], perm[b - 1], perm[c - 1])])
            cache[perm] = np.asarray(idxs, dtype=int)
        idxs = cache[perm]
        path_boat_idx[i] = idxs
        out[i] = boat_odds[i, idxs]

        inv = {boat: course for course, boat in enumerate(perm, start=1)}
        wc = getattr(r, "winner_boat_combo")
        try:
            cp = tuple(inv[int(b)] for b in wc)
            winner_path[i] = PATH_TO_IDX.get(cp, -1)
        except Exception:
            winner_path[i] = -1

    valid_odds = np.where(np.isfinite(out) & (out > 1.0), out, np.nan)
    inv_odds = 1.0 / valid_odds
    den = np.nansum(inv_odds, axis=1, keepdims=True)
    q = np.divide(inv_odds, den, out=np.full_like(inv_odds, np.nan), where=den > 0)
    return valid_odds, q, winner_path, path_boat_idx


def smoothed_multiplier(hits, expected, n, prior_n=DISCOVERY_PRIOR_N):
    avg_q = expected / max(n, 1)
    if avg_q <= 0:
        return np.nan
    post = (hits + prior_n * avg_q) / (n + prior_n)
    return post / avg_q


def discover_signals(races: pd.DataFrame, q: np.ndarray, winner_path: np.ndarray, start, end):
    dates = races["race_date"]
    mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end)) & (winner_path >= 0)
    disc_idx = np.flatnonzero(mask.to_numpy())
    if len(disc_idx) == 0:
        return pd.DataFrame()
    midpoint = pd.Timestamp(start) + (pd.Timestamp(end) - pd.Timestamp(start)) / 2
    h1_global = dates < midpoint
    rows = []

    for label in LABEL_KINDS:
        for a, b in PAIRS:
            ca, cb = f"{label}_c{a}", f"{label}_c{b}"
            if ca not in races or cb not in races:
                continue
            d = races.iloc[disc_idx][[ca, cb]].copy()
            d["pos"] = disc_idx
            d = d[d[ca].notna() & d[cb].notna() & d[ca].ne("SAMPLE_LOW") & d[cb].ne("SAMPLE_LOW")]
            for (ta, tb), g in d.groupby([ca, cb]):
                idx = g["pos"].to_numpy(dtype=int)
                n = len(idx)
                if n < DISCOVERY_MIN_N:
                    continue
                qq = q[idx]
                expected = np.nansum(qq, axis=0)
                hits = np.bincount(winner_path[idx], minlength=len(PATHS)).astype(float)
                variance = np.nansum(qq * (1 - qq), axis=0)
                mult = np.array([smoothed_multiplier(h, e, n) for h, e in zip(hits, expected)])
                z = np.divide(hits - expected, np.sqrt(np.maximum(variance, 1e-12)))

                i1 = idx[h1_global.iloc[idx].to_numpy()]
                i2 = idx[~h1_global.iloc[idx].to_numpy()]
                if len(i1) < DISCOVERY_HALF_MIN_N or len(i2) < DISCOVERY_HALF_MIN_N:
                    continue
                e1 = np.nansum(q[i1], axis=0); e2 = np.nansum(q[i2], axis=0)
                h1 = np.bincount(winner_path[i1], minlength=len(PATHS)).astype(float)
                h2 = np.bincount(winner_path[i2], minlength=len(PATHS)).astype(float)
                m1 = np.array([smoothed_multiplier(h, e, len(i1), prior_n=20.0) for h, e in zip(h1, e1)])
                m2 = np.array([smoothed_multiplier(h, e, len(i2), prior_n=20.0) for h, e in zip(h2, e2)])

                keep = (
                    (expected >= DISCOVERY_MIN_EXPECTED)
                    & (hits >= DISCOVERY_MIN_HITS)
                    & (mult >= DISCOVERY_MIN_MULT)
                    & (z >= DISCOVERY_MIN_Z)
                    & (m1 > 1.0)
                    & (m2 > 1.0)
                )
                for pidx in np.flatnonzero(keep):
                    rows.append({
                        "label_kind": label, "course_a": a, "type_a": ta, "course_b": b, "type_b": tb,
                        "path_idx": int(pidx), "course_trifecta": "-".join(map(str, PATHS[pidx])),
                        "n": n, "hits": int(hits[pidx]), "market_expected_hits": float(expected[pidx]),
                        "multiplier": float(mult[pidx]), "z_market": float(z[pidx]),
                        "H1_multiplier": float(m1[pidx]), "H2_multiplier": float(m2[pidx]),
                    })
    sig = pd.DataFrame(rows)
    return sig.sort_values(["multiplier", "z_market"], ascending=False) if len(sig) else sig


def signal_lookup(signals: pd.DataFrame):
    out = {}
    if signals.empty:
        return out
    for r in signals.itertuples(index=False):
        key = (r.label_kind, int(r.course_a), str(r.type_a), int(r.course_b), str(r.type_b))
        out.setdefault(key, []).append((int(r.path_idx), float(r.multiplier)))
    return out


def candidates_for_race(row, qrow, orow, lookup):
    m = np.ones(len(PATHS), dtype=float)
    for label in LABEL_KINDS:
        for a, b in PAIRS:
            ta = getattr(row, f"{label}_c{a}")
            tb = getattr(row, f"{label}_c{b}")
            if pd.isna(ta) or pd.isna(tb) or ta == "SAMPLE_LOW" or tb == "SAMPLE_LOW":
                continue
            for pidx, mult in lookup.get((label, a, str(ta), b, str(tb)), []):
                # Do not multiply correlated signals; keep the strongest discovered adjustment.
                m[pidx] = max(m[pidx], min(mult, 2.0))
    if not np.any(m > 1.0) or not np.isfinite(qrow).any():
        return None
    p = qrow * m
    s = np.nansum(p)
    if not np.isfinite(s) or s <= 0:
        return None
    p = p / s
    ev = p * orow
    return m, p, ev


def make_bets(races, odds_course, q, winner_path, signals, test_start, test_end, ev_threshold, max_bets):
    lookup = signal_lookup(signals)
    dates = races["race_date"]
    mask = (dates >= pd.Timestamp(test_start)) & (dates <= pd.Timestamp(test_end)) & (winner_path >= 0)
    rows = []
    for i in np.flatnonzero(mask.to_numpy()):
        r = races.iloc[i]
        pack = candidates_for_race(r, q[i], odds_course[i], lookup)
        if pack is None:
            continue
        m, p, ev = pack
        eligible = np.flatnonzero((m > 1.0) & np.isfinite(ev) & (ev >= ev_threshold))
        if len(eligible) == 0:
            continue
        order = eligible[np.argsort(ev[eligible])[::-1]][:max_bets]
        for rank, pidx in enumerate(order, start=1):
            hit = int(pidx == winner_path[i])
            payout = float(r["payout"]) if hit else 0.0
            rows.append({
                "レースコード": r["レースコード"], "race_date": r["race_date"], "rank_in_race": rank,
                "course_trifecta": "-".join(map(str, PATHS[pidx])), "path_idx": int(pidx),
                "snapshot_odds": float(odds_course[i, pidx]), "model_prob": float(p[pidx]),
                "model_ev": float(ev[pidx]), "signal_multiplier": float(m[pidx]),
                "hit": hit, "return_per_100": payout,
            })
    return pd.DataFrame(rows)


def summarize_bets(bets: pd.DataFrame):
    if bets.empty:
        return {"bets": 0, "races_bet": 0, "hits": 0, "hit_rate": np.nan, "stake": 0.0, "return": 0.0, "roi_pct": np.nan}
    stake = 100.0 * len(bets)
    ret = float(bets["return_per_100"].sum())
    return {
        "bets": int(len(bets)), "races_bet": int(bets["レースコード"].nunique()), "hits": int(bets["hit"].sum()),
        "hit_rate": float(bets["hit"].mean()), "stake": stake, "return": ret, "roi_pct": ret / stake * 100.0,
    }


def kelly_simulation(primary_bets: pd.DataFrame):
    bank = START_BANKROLL
    peak = bank
    max_dd = 0.0
    rows = []
    if primary_bets.empty:
        return pd.DataFrame(), {"kelly_start": bank, "kelly_end": bank, "kelly_return_pct": 0.0, "kelly_max_dd_pct": 0.0, "kelly_bets": 0}
    b = primary_bets.sort_values(["race_date", "レースコード"]).copy()
    # Primary strategy has one bet per race by construction.
    for r in b.itertuples(index=False):
        o = float(r.snapshot_odds); p = float(r.model_prob)
        full = max(0.0, (p * o - 1.0) / max(o - 1.0, 1e-9))
        frac = min(KELLY_RACE_CAP, KELLY_FRACTION * full)
        stake = math.floor((bank * frac) / 100.0) * 100.0
        if stake < 100.0:
            continue
        before = bank
        if int(r.hit):
            bank += stake * (float(r.return_per_100) / 100.0 - 1.0)
        else:
            bank -= stake
        peak = max(peak, bank)
        max_dd = max(max_dd, (peak - bank) / peak if peak > 0 else 0.0)
        rows.append({"race_date": r.race_date, "レースコード": r.レースコード, "stake": stake, "before": before, "after": bank, "hit": int(r.hit)})
    return pd.DataFrame(rows), {
        "kelly_start": START_BANKROLL, "kelly_end": bank,
        "kelly_return_pct": (bank / START_BANKROLL - 1.0) * 100.0,
        "kelly_max_dd_pct": max_dd * 100.0, "kelly_bets": len(rows),
    }


def prepare_inputs(src: Path):
    cards = load_many(str(src / "programs/race_cards/*/*/*.csv"))
    results = load_many(str(src / "results/realtime/*/*/*.csv"))
    stt = load_many(str(src / "previews/stt/*/*/*.csv"))
    odds = load_many(str(src / "previews/od3/*/*/*.csv"))
    payouts = load_many(str(src / "results/payouts/*/*/*.csv"))
    if any(z.empty for z in [cards, results, stt, odds, payouts]):
        raise SystemExit("required cards/results/stt/od3/payouts data not found")

    cl = cards_to_long(cards)
    rl = results_to_long(results)
    if "決まり手" in rl.columns:
        rl["決まり手"] = normalize_method(rl["決まり手"])
    panel = build_panel(cl, rl, pd.DataFrame()).dropna(subset=["race_date", "regno", "actual_course", "finish"]).copy()
    sl = stt_to_long(stt)
    base, expo = build_base_races(sl, cl, odds, payouts)
    return panel, base, expo


def run_fold(name, panel, base, expo, role_train_end, discovery_start, discovery_end, test_start, test_end, out: Path):
    train = panel[panel["race_date"] < pd.Timestamp(role_train_end)].copy()
    roles = build_roles(train)
    races = attach_fold_roles(base, expo, roles)
    # Restrict to races relevant to this fold before building arrays.
    lo = pd.Timestamp(discovery_start); hi = pd.Timestamp(test_end)
    races = races[(races["race_date"] >= lo) & (races["race_date"] <= hi)].reset_index(drop=True)
    odds_course, q, winner_path, _ = odds_in_exhibition_course_order(races)
    signals = discover_signals(races, q, winner_path, discovery_start, discovery_end)
    signals["fold"] = name
    signals.to_csv(out / f"signals_{name}.csv", index=False)

    summary_rows = []
    primary = None
    for ev in SENSITIVITY_EVS:
        for k in SENSITIVITY_MAX_BETS:
            bets = make_bets(races, odds_course, q, winner_path, signals, test_start, test_end, ev, k)
            stats = summarize_bets(bets)
            strategy = f"EV{ev:.2f}_TOP{k}"
            summary_rows.append({"fold": name, "strategy": strategy, "ev_threshold": ev, "max_bets": k, "signals": len(signals), **stats})
            if abs(ev - PRIMARY_EV) < 1e-9 and k == PRIMARY_MAX_BETS:
                primary = bets
                bets.to_csv(out / f"primary_bets_{name}.csv", index=False)

    primary = primary if primary is not None else pd.DataFrame()
    kelly_curve, kstats = kelly_simulation(primary)
    kelly_curve.to_csv(out / f"kelly_curve_{name}.csv", index=False)
    for row in summary_rows:
        if row["strategy"] == f"EV{PRIMARY_EV:.2f}_TOP{PRIMARY_MAX_BETS}":
            row.update(kstats)
    meta = {
        "fold": name, "role_train_end": role_train_end, "discovery_start": discovery_start, "discovery_end": discovery_end,
        "test_start": test_start, "test_end": test_end, "role_rows": len(roles), "signals": len(signals),
        "discovery_races": int(((races.race_date >= pd.Timestamp(discovery_start)) & (races.race_date <= pd.Timestamp(discovery_end))).sum()),
        "test_races": int(((races.race_date >= pd.Timestamp(test_start)) & (races.race_date <= pd.Timestamp(test_end))).sum()),
    }
    return pd.DataFrame(summary_rows), primary, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="source/data")
    ap.add_argument("--out", default="artifacts/backtest_ev")
    args = ap.parse_args()
    src = Path(args.source); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    panel, base, expo = prepare_inputs(src)

    folds = [
        ("F1", "2026-01-01", "2026-01-01", "2026-02-28", "2026-03-01", "2026-04-30"),
        ("F2", "2026-05-01", "2026-05-01", "2026-06-30", "2026-07-01", "2026-08-28"),
    ]
    summaries = []; primaries = []; metas = []
    for spec in folds:
        s, p, m = run_fold(*spec, panel, base, expo, out)
        summaries.append(s); primaries.append(p.assign(fold=spec[0]) if len(p) else p); metas.append(m)

    summary = pd.concat(summaries, ignore_index=True)
    pooled_rows = []
    for (strategy, ev, k), g in summary.groupby(["strategy", "ev_threshold", "max_bets"]):
        stake = float(g.stake.sum()); ret = float(g["return"].sum()); bets = int(g.bets.sum()); hits = int(g.hits.sum())
        pooled_rows.append({
            "fold": "POOLED", "strategy": strategy, "ev_threshold": ev, "max_bets": int(k), "signals": int(g.signals.sum()),
            "bets": bets, "races_bet": int(g.races_bet.sum()), "hits": hits, "hit_rate": hits / bets if bets else np.nan,
            "stake": stake, "return": ret, "roi_pct": ret / stake * 100 if stake else np.nan,
        })
    summary = pd.concat([summary, pd.DataFrame(pooled_rows)], ignore_index=True)
    summary.to_csv(out / "summary.csv", index=False)
    pd.DataFrame(metas).to_csv(out / "fold_meta.csv", index=False)
    if primaries:
        pp = pd.concat([p for p in primaries if len(p)], ignore_index=True) if any(len(p) for p in primaries) else pd.DataFrame()
        pp.to_csv(out / "primary_bets_all.csv", index=False)

    primary_name = f"EV{PRIMARY_EV:.2f}_TOP{PRIMARY_MAX_BETS}"
    print("\nPRIMARY OOS")
    print(summary[summary.strategy.eq(primary_name)].to_string(index=False))
    print("\nSENSITIVITY POOLED")
    print(summary[summary.fold.eq("POOLED")].sort_values(["roi_pct", "bets"], ascending=[False, False]).to_string(index=False))
    print("\nFOLD META")
    print(pd.DataFrame(metas).to_string(index=False))


if __name__ == "__main__":
    main()
