#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import backtest_ev as be
import backtest_hierarchical as h

# Keep the causal/type model fixed. July is used only to calibrate score cutoffs.
# August outcomes are untouched until final scoring.
CAL_START = pd.Timestamp('2026-07-01')
CAL_END = pd.Timestamp('2026-07-31')
OOS_START = pd.Timestamp('2026-08-01')
OOS_END = pd.Timestamp('2026-08-28')
TARGET_RATES = [0.01, 0.03, 0.05, 0.10]
MAX_BETS_PER_RACE = 4
TICKET_EV_FLOOR = 1.00


def score_races(races, odds_course, q, winner_path, signals):
    lk = h.lookup_signals(signals)
    rows = []
    for i, r in races.iterrows():
        if winner_path[i] < 0:
            continue
        pack = h.adjusted_probs(r, q[i], lk)
        if pack is None:
            continue
        p, used = pack
        ev = p * odds_course[i]
        finite = np.flatnonzero(np.isfinite(ev))
        if len(finite) == 0:
            continue
        order = finite[np.argsort(ev[finite])[::-1]]
        top = int(order[0])
        rows.append({
            'row_idx': int(i),
            'レースコード': r['レースコード'],
            'race_date': r.race_date,
            'max_model_ev': float(ev[top]),
            'signals_used': int(used),
        })
    return pd.DataFrame(rows)


def cutoff_from_calibration(cal_scores: pd.DataFrame, target_rate: float) -> float:
    if cal_scores.empty:
        return np.inf
    # Top target_rate of calibration races by pre-result model score.
    return float(cal_scores['max_model_ev'].quantile(1.0 - target_rate, interpolation='higher'))


def make_bets_for_cutoff(races, odds_course, q, winner_path, signals, scores, cutoff):
    lk = h.lookup_signals(signals)
    selected = scores[scores.max_model_ev >= cutoff].copy()
    rows = []
    for s in selected.itertuples(index=False):
        i = int(s.row_idx)
        r = races.iloc[i]
        pack = h.adjusted_probs(r, q[i], lk)
        if pack is None:
            continue
        p, used = pack
        ev = p * odds_course[i]
        eligible = np.flatnonzero(np.isfinite(ev) & (ev >= TICKET_EV_FLOOR))
        if len(eligible) == 0:
            continue
        order = eligible[np.argsort(ev[eligible])[::-1]][:MAX_BETS_PER_RACE]
        for rank, pidx in enumerate(order, start=1):
            pidx = int(pidx)
            hit = int(pidx == winner_path[i])
            rows.append({
                'レースコード': r['レースコード'],
                'race_date': r.race_date,
                'rank_in_race': rank,
                'course_trifecta': '-'.join(map(str, be.PATHS[pidx])),
                'snapshot_odds': float(odds_course[i, pidx]),
                'model_prob': float(p[pidx]),
                'model_ev': float(ev[pidx]),
                'signals_used': int(used),
                'hit': hit,
                'return_per_100': float(r.payout) if hit else 0.0,
            })
    return selected, pd.DataFrame(rows)


def stats(bets: pd.DataFrame):
    return be.summarize_bets(bets)


def main():
    out = Path('artifacts/purchase_rate_sweep')
    out.mkdir(parents=True, exist_ok=True)

    panel, base, expo = be.prepare_inputs(Path('source/data'))
    roles = be.build_roles(panel[panel.race_date < h.ROLE_TRAIN_END].copy())
    disc = panel[(panel.race_date >= h.DISC_START) & (panel.race_date <= h.DISC_END)].copy()
    signals = h.discover_pair_signals(disc, roles)

    races = be.attach_fold_roles(base, expo, roles)
    races = races[(races.race_date >= CAL_START) & (races.race_date <= OOS_END)].reset_index(drop=True)
    odds_course, q, winner_path, _ = be.odds_in_exhibition_course_order(races)

    scored = score_races(races, odds_course, q, winner_path, signals)
    cal_scores = scored[(scored.race_date >= CAL_START) & (scored.race_date <= CAL_END)].copy()
    oos_scores = scored[(scored.race_date >= OOS_START) & (scored.race_date <= OOS_END)].copy()

    total_oos_races = int(((races.race_date >= OOS_START) & (races.race_date <= OOS_END)).sum())
    rows = []
    rank_rows = []
    all_bets = []

    for target in TARGET_RATES:
        cutoff = cutoff_from_calibration(cal_scores, target)
        selected, bets = make_bets_for_cutoff(races, odds_course, q, winner_path, signals, oos_scores, cutoff)
        st = stats(bets)
        selected_with_bet = int(bets['レースコード'].nunique()) if len(bets) else 0
        row = {
            'target_rate_pct': target * 100.0,
            'july_score_cutoff': cutoff,
            'aug_total_races': total_oos_races,
            'aug_scored_races': len(oos_scores),
            'aug_selected_by_score': len(selected),
            'aug_races_with_bet': selected_with_bet,
            'achieved_bet_rate_pct': selected_with_bet / total_oos_races * 100.0 if total_oos_races else np.nan,
            'ticket_ev_floor': TICKET_EV_FLOOR,
            'max_bets_per_race': MAX_BETS_PER_RACE,
            **st,
        }
        rows.append(row)
        if len(bets):
            b = bets.copy()
            b['target_rate_pct'] = target * 100.0
            all_bets.append(b)
            for rank in range(1, MAX_BETS_PER_RACE + 1):
                br = b[b.rank_in_race.eq(rank)].copy()
                rs = stats(br)
                rank_rows.append({'target_rate_pct': target * 100.0, 'rank_in_race': rank, **rs})
        else:
            for rank in range(1, MAX_BETS_PER_RACE + 1):
                rank_rows.append({'target_rate_pct': target * 100.0, 'rank_in_race': rank, **stats(pd.DataFrame())})

    summary = pd.DataFrame(rows)
    rank_summary = pd.DataFrame(rank_rows)
    summary.to_csv(out/'summary.csv', index=False)
    rank_summary.to_csv(out/'rank_summary.csv', index=False)
    scored.to_csv(out/'race_scores.csv', index=False)
    signals.to_csv(out/'signals_may_june.csv', index=False)
    if all_bets:
        pd.concat(all_bets, ignore_index=True).to_csv(out/'bets.csv', index=False)
    else:
        pd.DataFrame().to_csv(out/'bets.csv', index=False)

    print('PURCHASE RATE SWEEP -- JULY CALIBRATION / AUGUST OOS')
    print(summary.to_string(index=False))
    print('\nRANK CONTRIBUTION')
    print(rank_summary.to_string(index=False))


if __name__ == '__main__':
    main()
