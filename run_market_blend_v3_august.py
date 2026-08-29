#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import market_blend_v3 as m

be = m.be
v1 = m.v1
v2 = m.v2

JULY_START = pd.Timestamp('2026-07-01')
JULY_END = pd.Timestamp('2026-07-31')
AUG_START = pd.Timestamp('2026-08-01')
AUG_END = pd.Timestamp('2026-08-28')


def tune_on_july(july_pred, base):
    races, _, q, winner_path = m._period_market(base, JULY_START, JULY_END)
    rows = []
    best = None
    for lam in m.LAMBDA_GRID:
        losses = []
        tops = []
        model_losses = []
        market_losses = []
        for i, r in races.iterrows():
            p = july_pred.get(str(r['レースコード']))
            wi = int(winner_path[i])
            if p is None or wi < 0 or not np.isfinite(q[i]).any():
                continue
            pp = m._norm(p)
            qq = m._norm(q[i])
            bb = m._blend(pp, qq, float(lam))
            losses.append(-math.log(max(float(bb[wi]), 1e-12)))
            model_losses.append(-math.log(max(float(pp[wi]), 1e-12)))
            market_losses.append(-math.log(max(float(qq[wi]), 1e-12)))
            tops.append(int(np.argmax(bb) == wi))
        if not losses:
            continue
        row = {
            'market_weight': 1.0 - float(lam),
            'model_weight': float(lam),
            'cal_nll': float(np.mean(losses)),
            'cal_top_hit_rate': float(np.mean(tops)),
            'cal_model_nll': float(np.mean(model_losses)),
            'cal_market_nll': float(np.mean(market_losses)),
            'races': len(losses),
        }
        rows.append(row)
        if best is None or row['cal_nll'] < best['cal_nll']:
            best = row.copy()
    grid = pd.DataFrame(rows)
    if grid.empty:
        raise RuntimeError('No July races have usable market odds for V3 calibration')
    return best, grid.sort_values('cal_nll')


def blend_period(model_pred, base, start, end, lam):
    races, _, q, _ = m._period_market(base, start, end)
    out = {}
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = model_pred.get(code)
        if p is None or not np.isfinite(q[i]).any():
            continue
        out[code] = m._blend(p, q[i], lam)
    return out


def quality_aug(model_pred, blend_pred, base):
    races, _, q, winner_path = m._period_market(base, AUG_START, AUG_END)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = model_pred.get(code)
        b = blend_pred.get(code)
        wi = int(winner_path[i])
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
            'winner_standalone_p': float(pp[wi]),
            'winner_blend_p': float(bb[wi]),
            'winner_market_p': float(qq[wi]),
        })
    d = pd.DataFrame(rows)
    if d.empty:
        return pd.DataFrame(), d
    mm = pd.DataFrame([{
        'test_period': '2026-08-01..2026-08-28',
        'test_races_scored': len(d),
        'standalone_model_nll': d.standalone_nll.mean(),
        'market_blend_nll': d.blend_nll.mean(),
        'market_nll': d.market_nll.mean(),
        'standalone_top_hit_rate': d.standalone_top_hit.mean(),
        'market_blend_top_hit_rate': d.blend_top_hit.mean(),
        'market_top_hit_rate': d.market_top_hit.mean(),
        'avg_standalone_prob_on_winner': d.winner_standalone_p.mean(),
        'avg_blend_prob_on_winner': d.winner_blend_p.mean(),
        'avg_market_prob_on_winner': d.winner_market_p.mean(),
    }])
    return mm, d


def evaluate_aug(base, probs, ev_threshold, max_bets):
    races, odds, _, winner_path = m._period_market(base, AUG_START, AUG_END)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = probs.get(code)
        wi = int(winner_path[i])
        if p is None or wi < 0:
            continue
        ev = p * odds[i]
        eligible = np.flatnonzero(np.isfinite(ev) & (ev >= ev_threshold))
        order = eligible[np.argsort(ev[eligible])[::-1]][:max_bets]
        for rank, pidx in enumerate(order, 1):
            hit = int(pidx == wi)
            rows.append({
                'レースコード': code,
                'race_date': r.race_date,
                'rank_in_race': rank,
                'course_trifecta': '-'.join(map(str, m.PATHS[pidx])),
                'snapshot_odds': float(odds[i, pidx]),
                'blend_prob': float(p[pidx]),
                'blend_ev': float(ev[pidx]),
                'hit': hit,
                'return_per_100': float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def edge_aug(probs, base):
    races, odds, _, _ = m._period_market(base, AUG_START, AUG_END)
    maxev, c105, c110, c120 = [], [], [], []
    for i, r in races.iterrows():
        p = probs.get(str(r['レースコード']))
        if p is None:
            continue
        ev = p * odds[i]
        good = ev[np.isfinite(ev)]
        if not len(good):
            continue
        maxev.append(float(np.max(good)))
        c105.append(int((good >= 1.05).sum()))
        c110.append(int((good >= 1.10).sum()))
        c120.append(int((good >= 1.20).sum()))
    if not maxev:
        return pd.DataFrame()
    q = np.quantile(maxev, [0, .1, .25, .5, .75, .9, .95, .99, 1])
    return pd.DataFrame([{
        'races': len(maxev), 'max_ev_min': q[0], 'max_ev_p10': q[1], 'max_ev_p25': q[2],
        'max_ev_median': q[3], 'max_ev_p75': q[4], 'max_ev_p90': q[5], 'max_ev_p95': q[6],
        'max_ev_p99': q[7], 'max_ev_max': q[8],
        'avg_tickets_ev105': float(np.mean(c105)), 'avg_tickets_ev110': float(np.mean(c110)),
        'avg_tickets_ev120': float(np.mean(c120)),
    }])


def main():
    out = Path('artifacts/market_blend_v3')
    out.mkdir(parents=True, exist_ok=True)

    e, panel, roles, base = v1.build_entries(Path('source/data'))
    e = v2._add_context_features(e, panel, roles)
    v2._build_conditional_ratios(e)

    v1.feature_columns = v2.feature_columns_v2
    v1.path_from_entries = v2.path_from_entries_v2
    model, nums, cats, train_rows = v1.fit_base_model(e)
    entry_pp = v1.base_entry_probs(model, e, nums, cats)

    # V2 model calibration remains May/June and interaction discovery remains May/June.
    v2.COND_GAMMA = 0.50
    best, calibration_grid = v1.tune_calibration(e, entry_pp)
    _, alpha, beta, temp = best
    _, gamma_grid = v2._tune_gamma(e, entry_pp, alpha, beta, temp)
    cal_pred, cal_win = v1.make_path_predictions(e, entry_pp, v2.CAL_START, v2.CAL_END, alpha, beta, temp)
    rf = v1.race_frame_for_signals(e, cal_pred, cal_win)
    signals = v1.discover_pair_signals(rf)
    lk = v1.signal_lookup(signals)

    # July is used ONLY to calibrate market/model blend weight.
    july_pred, _ = v1.make_path_predictions(e, entry_pp, JULY_START, JULY_END, alpha, beta, temp, lk)
    blend_best, blend_grid = tune_on_july(july_pred, base)
    lam = float(blend_best['model_weight'])

    # August is untouched by blend tuning and is the final OOS test.
    aug_model_pred, _ = v1.make_path_predictions(e, entry_pp, AUG_START, AUG_END, alpha, beta, temp, lk)
    aug_blend_pred = blend_period(aug_model_pred, base, AUG_START, AUG_END, lam)
    model_metrics, race_metrics = quality_aug(aug_model_pred, aug_blend_pred, base)

    sensitivity_rows = []
    primary = None
    for ev in m.EV_GRID:
        for k in m.BET_GRID:
            b = evaluate_aug(base, aug_blend_pred, ev, k)
            st = m._summary(b)
            sensitivity_rows.append({
                'test_period': 'AUGUST_OOS', 'ev_threshold': ev, 'max_bets': k,
                'races_bet': int(b['レースコード'].nunique()) if len(b) else 0, **st,
            })
            if abs(ev - m.PRIMARY_EV) < 1e-12 and k == m.PRIMARY_MAX_BETS:
                primary = b.copy()
    sensitivity = pd.DataFrame(sensitivity_rows)
    primary = primary if primary is not None else pd.DataFrame()
    edge = edge_aug(aug_blend_pred, base)

    meta = pd.DataFrame([{
        'model_training_cutoff': str(v2.ROLE_TRAIN_END),
        'v2_calibration_period': f'{v2.CAL_START.date()}..{v2.CAL_END.date()}',
        'market_blend_calibration_period': '2026-07-01..2026-07-31',
        'final_oos_period': '2026-08-01..2026-08-28',
        'train_entry_rows': train_rows, 'all_entry_rows': len(e),
        'numeric_features': len(nums), 'categorical_features': len(cats),
        'alpha_role': alpha, 'beta_adjusted': beta, 'temperature': temp,
        'conditional_gamma': v2.COND_GAMMA, 'pair_signals': len(signals),
        'market_weight': 1.0 - lam, 'model_weight': lam,
        'blend_cal_nll_july': blend_best['cal_nll'],
        'july_model_nll': blend_best['cal_model_nll'],
        'july_market_nll': blend_best['cal_market_nll'],
        'primary_ev': m.PRIMARY_EV, 'primary_max_bets': m.PRIMARY_MAX_BETS,
    }])

    meta.to_csv(out/'meta.csv', index=False)
    model_metrics.to_csv(out/'model_metrics.csv', index=False)
    race_metrics.to_csv(out/'race_metrics.csv', index=False)
    calibration_grid.to_csv(out/'calibration_grid.csv', index=False)
    gamma_grid.to_csv(out/'conditional_gamma_grid.csv', index=False)
    blend_grid.to_csv(out/'market_blend_grid.csv', index=False)
    signals.to_csv(out/'pair_signals.csv', index=False)
    sensitivity.to_csv(out/'sensitivity.csv', index=False)
    pd.DataFrame().to_csv(out/'monthly_sensitivity.csv', index=False)
    primary.to_csv(out/'primary_bets.csv', index=False)
    edge.to_csv(out/'edge_distribution.csv', index=False)

    print('MARKET PRIOR / MODEL RESIDUAL V3 -- JULY CALIBRATION, AUGUST OOS')
    print('\nMETA'); print(meta.to_string(index=False))
    print('\nAUGUST MODEL QUALITY'); print(model_metrics.to_string(index=False))
    print('\nJULY BLEND GRID TOP10'); print(blend_grid.head(10).to_string(index=False))
    print('\nAUGUST OOS SENSITIVITY'); print(sensitivity.to_string(index=False))
    print('\nAUGUST EDGE DISTRIBUTION'); print(edge.to_string(index=False))


if __name__ == '__main__':
    main()
