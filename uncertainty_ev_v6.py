#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

# Importing this module applies the leak-safe exclusion of archived series_* fields.
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

# Predicted-EV calibration bands are fixed before looking at August V6 results.
EV_BINS = [-np.inf, 0.90, 1.00, 1.05, 1.10, 1.20, 1.35, 1.50, np.inf]
EV_LABELS = ['<0.90', '0.90-1.00', '1.00-1.05', '1.05-1.10', '1.10-1.20', '1.20-1.35', '1.35-1.50', '>=1.50']
ADJ_EV_GRID = [1.00, 1.02, 1.05, 1.10]
BET_GRID = [1, 2, 3]
WILSON_Z = 1.2815515655446004  # one-sided 90% lower bound


def wilson_lower(hits: int, n: int, z: float = WILSON_Z) -> float:
    if n <= 0:
        return 0.0
    phat = hits / n
    z2 = z * z
    den = 1.0 + z2 / n
    center = phat + z2 / (2.0 * n)
    rad = z * math.sqrt(max(phat * (1.0 - phat) / n + z2 / (4.0 * n * n), 0.0))
    return max(0.0, (center - rad) / den)


def blend_period(model_pred, base, start, end, lam):
    races, _, q, _ = m._period_market(base, start, end)
    out = {}
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = model_pred.get(code)
        if p is None or not np.isfinite(q[i]).any():
            continue
        out[code] = m._blend(p, q[i], float(lam))
    return out


def build_reliability(july_probs, base):
    races, odds, _, winner_path = m._period_market(base, JULY_START, JULY_END)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = july_probs.get(code)
        wi = int(winner_path[i])
        if p is None or wi < 0:
            continue
        ev = np.asarray(p, float) * odds[i]
        good = np.isfinite(ev) & np.isfinite(p) & (odds[i] > 0)
        for idx in np.flatnonzero(good):
            rows.append((float(ev[idx]), float(p[idx]), int(idx == wi)))
    d = pd.DataFrame(rows, columns=['raw_ev', 'pred_p', 'hit'])
    d['ev_band'] = pd.cut(d.raw_ev, EV_BINS, labels=EV_LABELS, right=False)

    out = []
    for label in EV_LABELS:
        g = d[d.ev_band.astype(str) == label]
        n = len(g)
        h = int(g.hit.sum())
        pred_sum = float(g.pred_p.sum())
        avg_p = float(g.pred_p.mean()) if n else np.nan
        empirical = h / n if n else np.nan
        point_ratio = h / pred_sum if pred_sum > 0 else np.nan
        lo = wilson_lower(h, n) if n else 0.0
        lower_ratio = lo / avg_p if avg_p and np.isfinite(avg_p) and avg_p > 0 else 0.0
        out.append({
            'ev_band': label,
            'tickets': n,
            'hits': h,
            'predicted_hits': pred_sum,
            'avg_pred_p': avg_p,
            'empirical_hit_rate': empirical,
            'point_calibration_ratio': point_ratio,
            'wilson90_lower_hit_rate': lo,
            'lower_calibration_ratio_raw': lower_ratio,
        })
    rel = pd.DataFrame(out)
    rel['safety_factor_raw'] = rel['lower_calibration_ratio_raw'].clip(lower=0.0, upper=1.0)

    # For positive-EV bands, do not allow more extreme predicted edges to receive
    # a higher safety factor than milder edges. This is conservative and fixed.
    start = EV_LABELS.index('1.00-1.05')
    vals = rel.loc[start:, 'safety_factor_raw'].to_numpy(float)
    mono = np.minimum.accumulate(vals)
    rel['safety_factor'] = rel['safety_factor_raw']
    rel.loc[start:, 'safety_factor'] = mono
    return rel, d


def factor_for_ev(ev, rel):
    s = pd.Series(ev)
    bands = pd.cut(s, EV_BINS, labels=EV_LABELS, right=False).astype(str)
    mp = dict(zip(rel.ev_band, rel.safety_factor))
    return bands.map(mp).fillna(0.0).to_numpy(float)


def evaluate_aug(base, probs, rel, threshold, max_bets):
    races, odds, _, winner_path = m._period_market(base, AUG_START, AUG_END)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = probs.get(code)
        wi = int(winner_path[i])
        if p is None or wi < 0:
            continue
        raw_ev = np.asarray(p, float) * odds[i]
        fac = factor_for_ev(raw_ev, rel)
        adj_ev = raw_ev * fac
        eligible = np.flatnonzero(np.isfinite(adj_ev) & (adj_ev >= threshold))
        order = eligible[np.argsort(adj_ev[eligible])[::-1]][:max_bets]
        for rank, idx in enumerate(order, 1):
            hit = int(idx == wi)
            rows.append({
                'レースコード': code,
                'race_date': r.race_date,
                'rank_in_race': rank,
                'course_trifecta': '-'.join(map(str, m.PATHS[idx])),
                'snapshot_odds': float(odds[i, idx]),
                'blend_prob': float(p[idx]),
                'raw_ev': float(raw_ev[idx]),
                'safety_factor': float(fac[idx]),
                'adjusted_ev': float(adj_ev[idx]),
                'hit': hit,
                'return_per_100': float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def summarize(b):
    if b is None or b.empty:
        return {'bets': 0, 'hits': 0, 'hit_rate': 0.0, 'stake': 0.0, 'return': 0.0, 'roi_pct': np.nan}
    return m._summary(b)


def robustness(b):
    if b is None or b.empty:
        return {'roi_ex_best_day': np.nan, 'roi_ex_top1_hit': np.nan, 'roi_ex_top3_hits': np.nan, 'max_hit_return': 0.0}
    def roi(x):
        return 100.0 * x.return_per_100.sum() / (100.0 * len(x)) if len(x) else np.nan
    day_ret = b.groupby('race_date').return_per_100.sum().sort_values(ascending=False)
    ex_day = b[b.race_date != day_ret.index[0]] if len(day_ret) else b
    s = b.sort_values('return_per_100', ascending=False)
    return {
        'roi_ex_best_day': roi(ex_day),
        'roi_ex_top1_hit': roi(s.iloc[1:]),
        'roi_ex_top3_hits': roi(s.iloc[3:]),
        'max_hit_return': float(s.return_per_100.iloc[0]) if len(s) else 0.0,
    }


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
        })
    d = pd.DataFrame(rows)
    daily = d.groupby('race_date')[['blend_nll','market_nll']].mean()
    return pd.DataFrame([{
        'test_races_scored': len(d),
        'standalone_model_nll': d.standalone_nll.mean(),
        'blend_nll': d.blend_nll.mean(),
        'market_nll': d.market_nll.mean(),
        'days_blend_beats_market': int((daily.blend_nll < daily.market_nll).sum()),
    }]), d


def main():
    out = Path('artifacts/uncertainty_ev_v6')
    out.mkdir(parents=True, exist_ok=True)

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
    signals = v1.discover_pair_signals(rf)
    lk = v1.signal_lookup(signals)

    # July: calibrate the global market/model blend, then estimate reliability of
    # the resulting predicted EV bands. No August outcome is used here.
    july_model, _ = v1.make_path_predictions(e, entry_pp, JULY_START, JULY_END, alpha, beta, temp, lk)
    blend_best, blend_grid = aug.tune_on_july(july_model, base)
    lam = float(blend_best['model_weight'])
    july_blend = blend_period(july_model, base, JULY_START, JULY_END, lam)
    reliability, july_ticket_cal = build_reliability(july_blend, base)

    # August: diagnostic replay only. Parameters and safety factors are frozen from July.
    aug_model, _ = v1.make_path_predictions(e, entry_pp, AUG_START, AUG_END, alpha, beta, temp, lk)
    aug_blend = blend_period(aug_model, base, AUG_START, AUG_END, lam)
    quality, race_metrics = quality_aug(aug_model, aug_blend, base)

    sens = []
    robust = []
    primary = pd.DataFrame()
    for th in ADJ_EV_GRID:
        for k in BET_GRID:
            b = evaluate_aug(base, aug_blend, reliability, th, k)
            st = summarize(b)
            sens.append({'adjusted_ev_threshold': th, 'max_bets': k,
                         'races_bet': int(b['レースコード'].nunique()) if len(b) else 0, **st})
            robust.append({'adjusted_ev_threshold': th, 'max_bets': k, **robustness(b)})
            if abs(th - 1.00) < 1e-12 and k == 1:
                primary = b.copy()

    # Distribution of raw/adjusted edges before selection in August.
    edge_rows = []
    races, odds, _, _ = m._period_market(base, AUG_START, AUG_END)
    for i, r in races.iterrows():
        p = aug_blend.get(str(r['レースコード']))
        if p is None:
            continue
        raw = np.asarray(p, float) * odds[i]
        fac = factor_for_ev(raw, reliability)
        adj = raw * fac
        good = np.isfinite(adj)
        if not good.any():
            continue
        edge_rows.append({
            'race_date': r.race_date,
            'max_raw_ev': float(np.nanmax(raw[good])),
            'max_adjusted_ev': float(np.nanmax(adj[good])),
            'tickets_adj_ge_1': int((adj[good] >= 1.0).sum()),
            'tickets_adj_ge_1_02': int((adj[good] >= 1.02).sum()),
            'tickets_adj_ge_1_05': int((adj[good] >= 1.05).sum()),
        })
    edge = pd.DataFrame(edge_rows)
    edge_summary = pd.DataFrame([{
        'races': len(edge),
        'median_max_raw_ev': edge.max_raw_ev.median(),
        'median_max_adjusted_ev': edge.max_adjusted_ev.median(),
        'avg_tickets_adj_ge_1': edge.tickets_adj_ge_1.mean(),
        'avg_tickets_adj_ge_1_02': edge.tickets_adj_ge_1_02.mean(),
        'avg_tickets_adj_ge_1_05': edge.tickets_adj_ge_1_05.mean(),
    }]) if len(edge) else pd.DataFrame()

    meta = pd.DataFrame([{
        'model_training_cutoff': str(v2.ROLE_TRAIN_END),
        'model_calibration_period': f'{v2.CAL_START.date()}..{v2.CAL_END.date()}',
        'ev_reliability_calibration_period': '2026-07-01..2026-07-31',
        'diagnostic_replay_period': '2026-08-01..2026-08-28',
        'series_features_removed': True,
        'numeric_features': len(nums), 'categorical_features': len(cats),
        'market_weight': 1.0 - lam, 'model_weight': lam,
        'wilson_one_sided_confidence': 0.90,
        'pair_signals': len(signals), 'train_entry_rows': train_rows,
    }])

    meta.to_csv(out/'meta.csv', index=False)
    quality.to_csv(out/'model_quality.csv', index=False)
    reliability.to_csv(out/'july_ev_reliability.csv', index=False)
    july_ticket_cal.to_csv(out/'july_ticket_calibration_raw.csv', index=False)
    pd.DataFrame(sens).to_csv(out/'sensitivity.csv', index=False)
    pd.DataFrame(robust).to_csv(out/'robustness.csv', index=False)
    primary.to_csv(out/'primary_bets.csv', index=False)
    edge.to_csv(out/'edge_by_race.csv', index=False)
    edge_summary.to_csv(out/'edge_summary.csv', index=False)
    calibration_grid.to_csv(out/'calibration_grid.csv', index=False)
    gamma_grid.to_csv(out/'conditional_gamma_grid.csv', index=False)
    blend_grid.to_csv(out/'market_blend_grid.csv', index=False)
    signals.to_csv(out/'pair_signals.csv', index=False)
    race_metrics.to_csv(out/'race_metrics.csv', index=False)

    print('UNCERTAINTY-ADJUSTED EV V6')
    print('\nMETA'); print(meta.to_string(index=False))
    print('\nJULY EV RELIABILITY'); print(reliability.to_string(index=False))
    print('\nMODEL QUALITY'); print(quality.to_string(index=False))
    print('\nAUGUST DIAGNOSTIC SENSITIVITY'); print(pd.DataFrame(sens).to_string(index=False))
    print('\nROBUSTNESS'); print(pd.DataFrame(robust).to_string(index=False))
    print('\nEDGE SUMMARY'); print(edge_summary.to_string(index=False))


if __name__ == '__main__':
    main()
