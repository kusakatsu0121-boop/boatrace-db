#!/usr/bin/env python3
"""Quick exploratory scan.

Purpose: choose provisional feature weights/conditions fast, then rerun only the
few survivors on the full sample. Historical profile construction still uses
all training data; only July/Aug evaluation races are sampled.
"""
from __future__ import annotations

import pandas as pd
import advisor_extension_patterns as m

CAL_RACES = 1500
OOS_RACES = 1000
SEED = 20260831


def _stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if len(df) <= n:
        return df.copy()

    # Keep venue composition roughly intact. Deterministic for reproducibility.
    venue_col = 'レース場コード' if 'レース場コード' in df.columns else None
    if venue_col is None:
        return df.sample(n=n, random_state=seed).copy()

    parts = []
    total = len(df)
    for i, (_, g) in enumerate(df.groupby(venue_col, dropna=False)):
        take = max(1, int(round(n * len(g) / total)))
        take = min(take, len(g))
        parts.append(g.sample(n=take, random_state=seed + i))
    out = pd.concat(parts, ignore_index=False)
    if len(out) > n:
        out = out.sample(n=n, random_state=seed + 999)
    elif len(out) < n:
        remain = df.loc[~df.index.isin(out.index)]
        if not remain.empty:
            out = pd.concat([out, remain.sample(n=min(n-len(out), len(remain)), random_state=seed + 1000)])
    return out.sort_values(['race_date', 'レースコード']).copy()


_full_ticket_frame = m.ticket_frame


def quick_ticket_frame(races, f2lk, f3lk, chainlk):
    cal = races[(races.race_date >= m.CAL_START) & (races.race_date <= m.CAL_END)]
    oos = races[(races.race_date >= m.OOS_START) & (races.race_date <= m.OOS_END)]
    cal_s = _stratified_sample(cal, CAL_RACES, SEED)
    oos_s = _stratified_sample(oos, OOS_RACES, SEED + 1)
    sampled = pd.concat([cal_s, oos_s], ignore_index=False)
    print(f'QUICK SAMPLE races: cal={len(cal_s):,}, oos={len(oos_s):,}, total={len(sampled):,}')
    return _full_ticket_frame(sampled, f2lk, f3lk, chainlk)


# Small-sample thresholds for exploration only.
m.MIN_CAL_BETS = 25
m.MIN_OOS_BETS = 15
m.TOP_SINGLE_PER_PATH = 8
m.TOP_GLOBAL_SINGLE = 120
m.TOP_PAIR_SIGNALS = 40
m.ticket_frame = quick_ticket_frame

if __name__ == '__main__':
    m.main()
