#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
import numpy as np
import pandas as pd

# Import applies the leak-safe removal of every archived series_* feature.
import run_market_blend_v4_leak_safe as leak

aug = leak.aug
m = aug.m
be = m.be
v1 = m.v1
v2 = m.v2

JULY_START = aug.JULY_START
JULY_END = aug.JULY_END
AUG_START = aug.AUG_START
AUG_END = aug.AUG_END

# Conservative three-band residual model. Model influence may only stay flat
# or decrease as the market odds get longer.
ODDS_CUTS = (50.0, 200.0)
LAMBDA_GRID = np.round(np.arange(0.0, 0.5001, 0.05), 2)
PRIMARY_EV = 1.05
PRIMARY_MAX_BETS = 3


def norm_rows(x):
    x = np.asarray(x, dtype=float)
    x = np.where(np.isfinite(x) & (x > 0), x, 1e-12)
    s = x.sum(axis=1, keepdims=True)
    return x / np.maximum(s, 1e-12)


def lam_matrix(odds, lams):
    a, b, c = map(float, lams)
    return np.where(odds < ODDS_CUTS[0], a, np.where(odds < ODDS_CUTS[1], b, c))


def blend_row(model_p, market_p, odds, lams):
    pp = m._norm(model_p)
    qq = m._norm(market_p)
    ll = lam_matrix(np.asarray(odds, dtype=float), lams)
    z = np.log(np.clip(qq, 1e-12, 1.0)) + ll * (
        np.log(np.clip(pp, 1e-12, 1.0)) - np.log(np.clip(qq, 1e-12, 1.0))
    )
    z -= np.max(z)
    out = np.exp(z)
    return out / out.sum()


def period_arrays(pred, base, start, end):
    races, odds, q, winner_path = m._period_market(base, start, end)
    ps, qs, os_, wins, codes = [], [], [], [], []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = pred.get(code)
        wi = int(winner_path[i])
        if p is None or wi < 0 or not np.isfinite(q[i]).any():
            continue
        ps.append(m._norm(p))
        qs.append(m._norm(q[i]))
        os_.append(np.asarray(odds[i], dtype=float))
        wins.append(wi)
        codes.append(code)
    return races, np.stack(ps), np.stack(qs), np.stack(os_), np.asarray(wins, dtype=int), codes


def tune_banded_lambdas(july_pred, base):
    _, P, Q, O, W, _ = period_arrays(july_pred, base, JULY_START, JULY_END)
    logp = np.log(np.clip(P, 1e-12, 1.0))
    logq = np.log(np.clip(Q, 1e-12, 1.0))
    rows = []
    best = None
    n = len(W)
    ridx = np.arange(n)

    # Monotone: short-odds model weight >= medium >= long-odds.
    for a in LAMBDA_GRID:
        for b in LAMBDA_GRID[LAMBDA_GRID <= a]:
            for c in LAMBDA_GRID[LAMBDA_GRID <= b]:
                ll = lam_matrix(O, (a, b, c))
                z = logq + ll * (logp - logq)
                zmax = np.max(z, axis=1, keepdims=True)
                logden = zmax[:, 0] + np.log(np.exp(z - zmax).sum(axis=1))
                nll = float(np.mean(-(z[ridx, W] - logden)))
                row = {'lambda_lt50': float(a), 'lambda_50_200': float(b), 'lambda_ge200': float(c), 'july_nll': nll, 'races': n}
                rows.append(row)
                if best is None or nll < best['july_nll']:
                    best = row.copy()

    grid = pd.DataFrame(rows).sort_values('july_nll').reset_index(drop=True)
    lams = (best['lambda_lt50'], best['lambda_50_200'], best['lambda_ge200'])

    # Diagnostics at the chosen point.
    ll = lam_matrix(O, lams)
    z = logq + ll * (logp - logq)
    zmax = np.max(z, axis=1, keepdims=True)
    B = np.exp(z - zmax)
    B /= B.sum(axis=1, keepdims=True)
    best['july_market_nll'] = float(np.mean(-np.log(np.maximum(Q[ridx, W], 1e-12))))
    best['july_model_nll'] = float(np.mean(-np.log(np.maximum(P[ridx, W], 1e-12))))
    best['july_top_hit_rate'] = float(np.mean(np.argmax(B, axis=1) == W))
    return best, grid


def blend_period(pred, base, start, end, lams):
    races, odds, q, _, = m._period_market(base, start, end)
    out = {}
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = pred.get(code)
        if p is None or not np.isfinite(q[i]).any():
            continue
        out[code] = blend_row(p, q[i], odds[i], lams)
    return out


def quality_aug(model_pred, blend_pred, base):
    races, _, q, winner_path = m._period_market(base, AUG_START, AUG_END)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = model_pred.get(code); b = blend_pred.get(code); wi = int(winner_path[i])
        if p is None or b is None or wi < 0 or not np.isfinite(q[i]).any():
            continue
        pp = m._norm(p); qq = m._norm(q[i]); bb = m._norm(b)
        rows.append({
            'race_date': r.race_date,
            'standalone_nll': -math.log(max(float(pp[wi]), 1e-12)),
            'blend_nll': -math.log(max(float(bb[wi]), 1e-12)),
            'market_nll': -math.log(max(float(qq[wi]), 1e-12)),
            'standalone_top_hit': int(np.argmax(pp) == wi),
            'blend_top_hit': int(np.argmax(bb) == wi),
            'market_top_hit': int(np.argmax(qq) == wi),
        })
    d = pd.DataFrame(rows)
    mm = pd.DataFrame([{
        'test_period': '2026-08-01..2026-08-28', 'test_races_scored': len(d),
        'standalone_model_nll': d.standalone_nll.mean(), 'band_blend_nll': d.blend_nll.mean(),
        'market_nll': d.market_nll.mean(), 'standalone_top_hit_rate': d.standalone_top_hit.mean(),
        'band_blend_top_hit_rate': d.blend_top_hit.mean(), 'market_top_hit_rate': d.market_top_hit.mean(),
        'days_band_blend_beats_market': int((d.groupby('race_date').blend_nll.mean() < d.groupby('race_date').market_nll.mean()).sum()),
    }])
    return mm, d


def evaluate(base, probs, ev_threshold, max_bets, start=AUG_START, end=AUG_END):
    races, odds, _, winner_path = m._period_market(base, start, end)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード']); p = probs.get(code); wi = int(winner_path[i])
        if p is None or wi < 0:
            continue
        ev = p * odds[i]
        eligible = np.flatnonzero(np.isfinite(ev) & (ev >= ev_threshold))
        order = eligible[np.argsort(ev[eligible])[::-1]][:max_bets]
        for rank, pidx in enumerate(order, 1):
            hit = int(pidx == wi)
            rows.append({
                'レースコード': code, 'race_date': r.race_date, 'rank_in_race': rank,
                'course_trifecta': '-'.join(map(str, m.PATHS[pidx])), 'snapshot_odds': float(odds[i, pidx]),
                'blend_prob': float(p[pidx]), 'blend_ev': float(ev[pidx]), 'hit': hit,
                'return_per_100': float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def robust_stats(b):
    if b is None or b.empty:
        return {'roi_ex_best_day': np.nan, 'roi_ex_top1_hit': np.nan, 'roi_ex_top3_hits': np.nan, 'max_hit_return': 0.0}
    def roi(x):
        return 100.0 * x.return_per_100.sum() / (100.0 * len(x)) if len(x) else np.nan
    byday = b.groupby('race_date').return_per_100.sum().sort_values(ascending=False)
    exday = b[b.race_date != byday.index[0]] if len(byday) else b
    s = b.sort_values('return_per_100', ascending=False)
    return {
        'roi_ex_best_day': roi(exday),
        'roi_ex_top1_hit': roi(s.iloc[1:]),
        'roi_ex_top3_hits': roi(s.iloc[3:]),
        'max_hit_return': float(s.return_per_100.iloc[0]) if len(s) else 0.0,
    }


def primary_odds_bands(b):
    if b.empty:
        return pd.DataFrame()
    z = b.copy()
    z['odds_band'] = pd.cut(z.snapshot_odds, [-np.inf, 50, 200, np.inf], labels=['<50x','50-200x','>=200x'])
    rows=[]
    for band,g in z.groupby('odds_band', observed=True):
        st=m._summary(g)
        rows.append({'odds_band':str(band), **st})
    return pd.DataFrame(rows)


def main():
    out = Path('artifacts/market_tail_v5'); out.mkdir(parents=True, exist_ok=True)

    e, panel, roles, base = v1.build_entries(Path('source/data'))
    e = v2._add_context_features(e, panel, roles)
    v2._build_conditional_ratios(e)
    v1.feature_columns = v2.feature_columns_v2
    v1.path_from_entries = v2.path_from_entries_v2
    model, nums, cats, train_rows = v1.fit_base_model(e)
    entry_pp = v1.base_entry_probs(model, e, nums, cats)

    v2.COND_GAMMA = 0.50
    best, calibration_grid = v1.tune_calibration(e, entry_pp)
    _, alpha, beta, temp = best
    _, gamma_grid = v2._tune_gamma(e, entry_pp, alpha, beta, temp)
    cal_pred, cal_win = v1.make_path_predictions(e, entry_pp, v2.CAL_START, v2.CAL_END, alpha, beta, temp)
    rf = v1.race_frame_for_signals(e, cal_pred, cal_win)
    signals = v1.discover_pair_signals(rf); lk = v1.signal_lookup(signals)

    july_model_pred, _ = v1.make_path_predictions(e, entry_pp, JULY_START, JULY_END, alpha, beta, temp, lk)
    band_best, band_grid = tune_banded_lambdas(july_model_pred, base)
    lams = (band_best['lambda_lt50'], band_best['lambda_50_200'], band_best['lambda_ge200'])
    july_blend = blend_period(july_model_pred, base, JULY_START, JULY_END, lams)

    aug_model_pred, _ = v1.make_path_predictions(e, entry_pp, AUG_START, AUG_END, alpha, beta, temp, lk)
    aug_blend = blend_period(aug_model_pred, base, AUG_START, AUG_END, lams)
    model_metrics, race_metrics = quality_aug(aug_model_pred, aug_blend, base)

    sensitivity=[]; robustness=[]; primary=pd.DataFrame()
    for ev in m.EV_GRID:
        for k in m.BET_GRID:
            b=evaluate(base, aug_blend, ev, k)
            st=m._summary(b); rb=robust_stats(b)
            row={'test_period':'AUGUST_OOS','ev_threshold':ev,'max_bets':k,'races_bet':int(b['レースコード'].nunique()) if len(b) else 0,**st}
            sensitivity.append(row); robustness.append({'ev_threshold':ev,'max_bets':k,**rb})
            if abs(ev-PRIMARY_EV)<1e-12 and k==PRIMARY_MAX_BETS: primary=b.copy()

    july_diag=[]
    for ev in [1.05,1.10,1.15,1.20,1.30,1.50]:
        b=evaluate(base,july_blend,ev,1,JULY_START,JULY_END)
        july_diag.append({'ev_threshold':ev,'max_bets':1,**m._summary(b)})

    meta=pd.DataFrame([{
        'model_training_cutoff':str(v2.ROLE_TRAIN_END), 'model_calibration':'2026-05-01..2026-06-30',
        'tail_calibration':'2026-07-01..2026-07-31', 'final_oos':'2026-08-01..2026-08-28',
        'numeric_features':len(nums),'categorical_features':len(cats),'series_features_removed':True,
        'lambda_lt50':lams[0],'lambda_50_200':lams[1],'lambda_ge200':lams[2],
        'july_banded_nll':band_best['july_nll'],'july_market_nll':band_best['july_market_nll'],
        'july_model_nll':band_best['july_model_nll'],'pair_signals':len(signals),
    }])

    meta.to_csv(out/'meta.csv',index=False); model_metrics.to_csv(out/'model_metrics.csv',index=False)
    race_metrics.to_csv(out/'race_metrics.csv',index=False); band_grid.to_csv(out/'band_lambda_grid.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(out/'sensitivity.csv',index=False); pd.DataFrame(robustness).to_csv(out/'robustness.csv',index=False)
    primary.to_csv(out/'primary_bets.csv',index=False); primary_odds_bands(primary).to_csv(out/'primary_odds_bands.csv',index=False)
    pd.DataFrame(july_diag).to_csv(out/'july_strategy_diagnostics.csv',index=False)
    calibration_grid.to_csv(out/'calibration_grid.csv',index=False); gamma_grid.to_csv(out/'conditional_gamma_grid.csv',index=False)
    signals.to_csv(out/'pair_signals.csv',index=False)

    print('LEAK-SAFE MARKET TAIL CALIBRATION V5')
    print('\nMETA'); print(meta.to_string(index=False))
    print('\nMODEL QUALITY'); print(model_metrics.to_string(index=False))
    print('\nTOP BAND LAMBDAS'); print(band_grid.head(12).to_string(index=False))
    print('\nAUGUST OOS'); print(pd.DataFrame(sensitivity).to_string(index=False))
    print('\nROBUSTNESS'); print(pd.DataFrame(robustness).to_string(index=False))
    print('\nPRIMARY ODDS BANDS'); print(primary_odds_bands(primary).to_string(index=False))
    print('\nJULY CALIBRATION-ONLY ROI DIAGNOSTIC'); print(pd.DataFrame(july_diag).to_string(index=False))


if __name__ == '__main__':
    main()
