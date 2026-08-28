#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_ev as be

# Fixed before reading July/August returns for this hierarchical model.
ROLE_TRAIN_END = pd.Timestamp('2026-05-01')
DISC_START = pd.Timestamp('2026-05-01')
DISC_END = pd.Timestamp('2026-06-30')
TEST_START = pd.Timestamp('2026-07-01')
TEST_END = pd.Timestamp('2026-08-28')
PAIRS = [(1,2),(1,3),(1,4),(2,3),(2,4),(3,4)]
LABELS = ['style','finish_role']
POSITIONS = [1,2,3]
MIN_N = 80
HALF_MIN_N = 25
MIN_ABS_LIFT = 0.020
MIN_ABS_T = 1.50
RATIO_MIN = 0.55
RATIO_MAX = 1.80
DAMP_POWER = 0.50
PRIMARY_EV = 1.15
PRIMARY_MAX_BETS = 4


def role_baseline_map(roles):
    out = {}
    for r in roles.itertuples(index=False):
        out[(int(r.regno), int(r.course))] = {1: float(r.p1), 2: float(r.p2), 3: float(r.p3)}
    return out


def attach_actual_roles(panel, roles):
    cols = ['regno','course','style','finish_role']
    return panel.merge(roles[cols], left_on=['regno','actual_course'], right_on=['regno','course'], how='left').drop(columns=['course'])


def discovery_expected(panel, roles):
    bm = role_baseline_map(roles)
    x = panel.copy()
    for pos in POSITIONS:
        raw = pd.Series([bm.get((int(r), int(c)), {}).get(pos, np.nan) for r,c in zip(x.regno, x.actual_course)], index=x.index, dtype=float)
        fallback = raw.groupby(x.actual_course).transform('mean')
        raw = raw.fillna(fallback).fillna(raw.mean())
        den = raw.groupby(x['レースコード']).transform('sum').replace(0, np.nan)
        exp = (raw / den).clip(0.001, 0.999)
        x[f'exp{pos}'] = exp
        x[f'obs{pos}'] = (x.finish == pos).astype(float)
        x[f'resid{pos}'] = x[f'obs{pos}'] - x[f'exp{pos}']
    return x


def discover_pair_signals(disc, roles):
    x = attach_actual_roles(discovery_expected(disc, roles), roles)
    x['half'] = np.where(x.race_date < pd.Timestamp('2026-06-01'), 'MAY', 'JUN')
    rows = []
    for label in LABELS:
        for a,b in PAIRS:
            qa = x[x.actual_course.eq(a)][['レースコード', label]].rename(columns={label:'A'})
            qb = x[x.actual_course.eq(b)][['レースコード', label]].rename(columns={label:'B'})
            pair = qa.merge(qb, on='レースコード')
            pair = pair[pair.A.notna() & pair.B.notna() & pair.A.ne('SAMPLE_LOW') & pair.B.ne('SAMPLE_LOW')]
            if pair.empty:
                continue
            z = x.merge(pair, on='レースコード')
            for tc in range(1,7):
                zz = z[z.actual_course.eq(tc)].copy()
                if zz.empty:
                    continue
                for pos in POSITIONS:
                    col = f'resid{pos}'
                    overall = float(zz[col].mean())
                    ma = zz.groupby('A')[col].mean()
                    mb = zz.groupby('B')[col].mean()
                    pg = zz.groupby(['A','B'])[col].agg(['mean','size','std']).reset_index()
                    for r in pg.itertuples(index=False):
                        n = int(r.size)
                        if n < MIN_N:
                            continue
                        lift = float(r.mean - ma.get(r.A,0.0) - mb.get(r.B,0.0) + overall)
                        se = float(r.std / math.sqrt(n)) if pd.notna(r.std) and r.std > 0 else np.nan
                        t = lift / se if np.isfinite(se) and se > 0 else np.nan
                        halves = {}
                        good_halves = True
                        for h in ('MAY','JUN'):
                            zh = zz[zz.half.eq(h)]
                            gh = zh[(zh.A == r.A) & (zh.B == r.B)]
                            if len(gh) < HALF_MIN_N:
                                good_halves = False
                                halves[h] = (np.nan, len(gh))
                                continue
                            oh = float(zh[col].mean())
                            mah = zh.groupby('A')[col].mean().get(r.A,0.0)
                            mbh = zh.groupby('B')[col].mean().get(r.B,0.0)
                            hl = float(gh[col].mean() - mah - mbh + oh)
                            halves[h] = (hl, len(gh))
                        if not good_halves:
                            continue
                        same = np.sign(lift) == np.sign(halves['MAY'][0]) == np.sign(halves['JUN'][0])
                        if not same or abs(lift) < MIN_ABS_LIFT or not np.isfinite(t) or abs(t) < MIN_ABS_T:
                            continue
                        rows.append({
                            'label_kind': label, 'course_a':a, 'type_a':r.A, 'course_b':b, 'type_b':r.B,
                            'target_course':tc, 'position':pos, 'n':n, 'lift':lift, 't_approx':float(t),
                            'may_lift':halves['MAY'][0], 'may_n':halves['MAY'][1],
                            'jun_lift':halves['JUN'][0], 'jun_n':halves['JUN'][1],
                        })
    s = pd.DataFrame(rows)
    return s.sort_values(['t_approx','n'], key=lambda col: col.abs() if col.name=='t_approx' else col, ascending=False) if len(s) else s


def lookup_signals(signals):
    out = {}
    for r in signals.itertuples(index=False):
        key = (r.label_kind, int(r.course_a), str(r.type_a), int(r.course_b), str(r.type_b))
        out.setdefault(key, []).append((int(r.target_course), int(r.position), float(r.lift), abs(float(r.t_approx))))
    return out


def market_marginals(qrow):
    m = np.zeros((4,7), dtype=float)
    for i,(a,b,c) in enumerate(be.PATHS):
        q = qrow[i]
        if not np.isfinite(q):
            continue
        m[1,a] += q; m[2,b] += q; m[3,c] += q
    return m


def adjusted_probs(row, qrow, signal_lookup):
    marg = market_marginals(qrow)
    # strongest evidence only per target course/position, avoiding correlated signal multiplication
    best = {}
    for label in LABELS:
        for a,b in PAIRS:
            ta = getattr(row, f'{label}_c{a}')
            tb = getattr(row, f'{label}_c{b}')
            if pd.isna(ta) or pd.isna(tb) or ta == 'SAMPLE_LOW' or tb == 'SAMPLE_LOW':
                continue
            for tc,pos,lift,strength in signal_lookup.get((label,a,str(ta),b,str(tb)), []):
                key = (pos,tc)
                if key not in best or strength > best[key][1]:
                    best[key] = (lift,strength)
    if not best:
        return None

    ratio = np.ones((4,7), dtype=float)
    for (pos,tc),(lift,_) in best.items():
        base = marg[pos,tc]
        if base <= 0 or not np.isfinite(base):
            continue
        adj = float(np.clip(base + lift, 0.001, 0.999))
        ratio[pos,tc] = float(np.clip(adj/base, RATIO_MIN, RATIO_MAX))

    p = np.array(qrow, dtype=float)
    for i,(a,b,c) in enumerate(be.PATHS):
        if not np.isfinite(p[i]):
            continue
        mod = (ratio[1,a] * ratio[2,b] * ratio[3,c]) ** DAMP_POWER
        p[i] *= mod
    den = np.nansum(p)
    if den <= 0:
        return None
    p /= den
    return p, len(best)


def make_test_bets(races, odds_course, q, winner_path, signals, start, end, ev_threshold=PRIMARY_EV, max_bets=PRIMARY_MAX_BETS):
    lk = lookup_signals(signals)
    mask = (races.race_date >= pd.Timestamp(start)) & (races.race_date <= pd.Timestamp(end)) & (winner_path >= 0)
    rows = []
    for i in np.flatnonzero(mask.to_numpy()):
        r = races.iloc[i]
        pack = adjusted_probs(r, q[i], lk)
        if pack is None:
            continue
        p, used = pack
        ev = p * odds_course[i]
        eligible = np.flatnonzero(np.isfinite(ev) & (ev >= ev_threshold))
        if len(eligible) == 0:
            continue
        order = eligible[np.argsort(ev[eligible])[::-1]][:max_bets]
        for rank, pidx in enumerate(order, start=1):
            pidx = int(pidx)
            hit = int(pidx == winner_path[i])
            rows.append({
                'レースコード':r['レースコード'], 'race_date':r.race_date, 'rank_in_race':rank,
                'course_trifecta':'-'.join(map(str,be.PATHS[pidx])), 'path_idx':pidx,
                'snapshot_odds':float(odds_course[i,pidx]), 'model_prob':float(p[pidx]),
                'model_ev':float(ev[pidx]), 'signals_used':used, 'hit':hit,
                'return_per_100':float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def summarize(name,bets):
    s = be.summarize_bets(bets)
    return {'period':name, **s}


def main():
    out = Path('artifacts/backtest_hierarchical'); out.mkdir(parents=True,exist_ok=True)
    panel, base, expo = be.prepare_inputs(Path('source/data'))
    roles = be.build_roles(panel[panel.race_date < ROLE_TRAIN_END].copy())
    disc = panel[(panel.race_date >= DISC_START) & (panel.race_date <= DISC_END)].copy()
    signals = discover_pair_signals(disc, roles)
    signals.to_csv(out/'signals_may_june.csv', index=False)

    races = be.attach_fold_roles(base, expo, roles)
    races = races[(races.race_date >= TEST_START) & (races.race_date <= TEST_END)].reset_index(drop=True)
    odds_course, q, winner_path, _ = be.odds_in_exhibition_course_order(races)

    all_bets = make_test_bets(races, odds_course, q, winner_path, signals, TEST_START, TEST_END, PRIMARY_EV, PRIMARY_MAX_BETS)
    july = all_bets[(all_bets.race_date >= pd.Timestamp('2026-07-01')) & (all_bets.race_date <= pd.Timestamp('2026-07-31'))].copy() if len(all_bets) else all_bets
    aug = all_bets[(all_bets.race_date >= pd.Timestamp('2026-08-01')) & (all_bets.race_date <= pd.Timestamp('2026-08-28'))].copy() if len(all_bets) else all_bets

    rows = [summarize('JULY',july), summarize('AUGUST',aug), summarize('POOLED',all_bets)]
    summary = pd.DataFrame(rows)
    summary['signals'] = len(signals)
    summary['max_bets_per_race'] = PRIMARY_MAX_BETS
    summary.to_csv(out/'summary.csv', index=False)
    all_bets.to_csv(out/'primary_bets.csv', index=False)
    pd.DataFrame([{
        'role_train_end':str(ROLE_TRAIN_END.date()), 'discovery_start':str(DISC_START.date()),
        'discovery_end':str(DISC_END.date()), 'test_start':str(TEST_START.date()), 'test_end':str(TEST_END.date()),
        'role_rows':len(roles),'discovery_races':disc['レースコード'].nunique(),'test_races':len(races),
        'signals':len(signals), 'primary_ev':PRIMARY_EV, 'primary_max_bets':PRIMARY_MAX_BETS,
    }]).to_csv(out/'meta.csv',index=False)

    print('HIERARCHICAL OOS SUMMARY')
    print(summary.to_string(index=False))
    print('\nMETA')
    print(pd.read_csv(out/'meta.csv').to_string(index=False))
    print('\nTOP DISCOVERY SIGNALS')
    print(signals.head(25).to_string(index=False) if len(signals) else 'none')


if __name__ == '__main__':
    main()
