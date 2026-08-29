#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

# Importing the safe V2 runner applies the duplicate-date fix, index reset,
# recursion-safe feature patch, and vectorized chronology-preserving tuning.
import run_full_probability_model_v2 as safe

be = safe.be
v1 = safe.v1
v2 = safe.model

PATHS = v2.PATHS
CAL_START = v2.CAL_START
CAL_END = v2.CAL_END
TEST_START = v2.TEST_START
TEST_END = v2.TEST_END

LAMBDA_GRID = np.round(np.arange(0.0, 1.0001, 0.05), 2)
EV_GRID = [1.01, 1.02, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50]
BET_GRID = [1, 2, 3, 4]
PRIMARY_EV = 1.05
PRIMARY_MAX_BETS = 3


def _norm(p):
    x = np.asarray(p, dtype=float)
    x = np.where(np.isfinite(x) & (x > 0), x, 1e-12)
    s = x.sum()
    return x / s if s > 0 else np.full_like(x, 1.0 / len(x))


def _blend(model_p, market_p, lam):
    p = _norm(model_p)
    q = _norm(market_p)
    z = lam * np.log(np.clip(p, 1e-12, 1.0)) + (1.0 - lam) * np.log(np.clip(q, 1e-12, 1.0))
    z -= np.max(z)
    out = np.exp(z)
    return out / out.sum()


def _period_market(base, start, end):
    races = base[(base.race_date >= start) & (base.race_date <= end)].reset_index(drop=True)
    odds, q, winner_path, _ = be.odds_in_exhibition_course_order(races)
    return races, odds, q, winner_path


def _tune_market_blend(cal_pred, base):
    races, _, q, winner_path = _period_market(base, CAL_START, CAL_END)
    rows = []
    best = None
    for lam in LAMBDA_GRID:
        losses = []
        tops = []
        market_losses = []
        model_losses = []
        used = 0
        for i, r in races.iterrows():
            p = cal_pred.get(str(r['レースコード']))
            wi = int(winner_path[i])
            if p is None or wi < 0 or not np.isfinite(q[i]).any():
                continue
            qq = _norm(q[i])
            pp = _norm(p)
            b = _blend(pp, qq, lam)
            losses.append(-math.log(max(float(b[wi]), 1e-12)))
            model_losses.append(-math.log(max(float(pp[wi]), 1e-12)))
            market_losses.append(-math.log(max(float(qq[wi]), 1e-12)))
            tops.append(int(np.argmax(b) == wi))
            used += 1
        if not losses:
            continue
        row = {
            'market_weight': 1.0 - float(lam),
            'model_weight': float(lam),
            'cal_nll': float(np.mean(losses)),
            'cal_top_hit_rate': float(np.mean(tops)),
            'cal_model_nll': float(np.mean(model_losses)),
            'cal_market_nll': float(np.mean(market_losses)),
            'races': used,
        }
        rows.append(row)
        if best is None or row['cal_nll'] < best['cal_nll']:
            best = row.copy()
    return best, pd.DataFrame(rows).sort_values('cal_nll')


def _blend_predictions(model_pred, base, start, end, lam):
    races, odds, q, winner_path = _period_market(base, start, end)
    out = {}
    for i, r in races.iterrows():
        p = model_pred.get(str(r['レースコード']))
        if p is None or not np.isfinite(q[i]).any():
            continue
        out[str(r['レースコード'])] = _blend(p, q[i], lam)
    return out, races, odds, q, winner_path


def _quality(model_pred, blend_pred, base):
    races, _, q, winner_path = _period_market(base, TEST_START, TEST_END)
    rows = []
    for i, r in races.iterrows():
        code = str(r['レースコード'])
        p = model_pred.get(code)
        b = blend_pred.get(code)
        wi = int(winner_path[i])
        if p is None or b is None or wi < 0 or not np.isfinite(q[i]).any():
            continue
        pp = _norm(p); qq = _norm(q[i]); bb = _norm(b)
        rows.append({
            'race_date': r.race_date,
            'model_nll': -math.log(max(float(pp[wi]), 1e-12)),
            'blend_nll': -math.log(max(float(bb[wi]), 1e-12)),
            'market_nll': -math.log(max(float(qq[wi]), 1e-12)),
            'model_top_hit': int(np.argmax(pp) == wi),
            'blend_top_hit': int(np.argmax(bb) == wi),
            'market_top_hit': int(np.argmax(qq) == wi),
            'winner_model_p': float(pp[wi]),
            'winner_blend_p': float(bb[wi]),
            'winner_market_p': float(qq[wi]),
        })
    d = pd.DataFrame(rows)
    m = pd.DataFrame([{
        'test_races_scored': len(d),
        'standalone_model_nll': d.model_nll.mean(),
        'market_blend_nll': d.blend_nll.mean(),
        'market_nll': d.market_nll.mean(),
        'standalone_top_hit_rate': d.model_top_hit.mean(),
        'market_blend_top_hit_rate': d.blend_top_hit.mean(),
        'market_top_hit_rate': d.market_top_hit.mean(),
        'avg_standalone_prob_on_winner': d.winner_model_p.mean(),
        'avg_blend_prob_on_winner': d.winner_blend_p.mean(),
        'avg_market_prob_on_winner': d.winner_market_p.mean(),
    }]) if len(d) else pd.DataFrame()
    return m, d


def _evaluate(base, probs, ev_threshold, max_bets):
    races, odds, _, winner_path = _period_market(base, TEST_START, TEST_END)
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
                'course_trifecta': '-'.join(map(str, PATHS[pidx])),
                'snapshot_odds': float(odds[i, pidx]),
                'blend_prob': float(p[pidx]),
                'blend_ev': float(ev[pidx]),
                'hit': hit,
                'return_per_100': float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def _summary(b):
    if b is None or len(b) == 0:
        return {'bets': 0, 'hits': 0, 'hit_rate': 0.0, 'stake': 0.0, 'return': 0.0, 'roi_pct': np.nan}
    return be.summarize_bets(b)


def _edge_distribution(probs, base):
    races, odds, _, _ = _period_market(base, TEST_START, TEST_END)
    maxev = []
    count105 = []
    count110 = []
    count120 = []
    for i, r in races.iterrows():
        p = probs.get(str(r['レースコード']))
        if p is None:
            continue
        ev = p * odds[i]
        good = ev[np.isfinite(ev)]
        if len(good) == 0:
            continue
        maxev.append(float(np.max(good)))
        count105.append(int((good >= 1.05).sum()))
        count110.append(int((good >= 1.10).sum()))
        count120.append(int((good >= 1.20).sum()))
    if not maxev:
        return pd.DataFrame()
    qv = np.quantile(maxev, [0, .1, .25, .5, .75, .9, .95, .99, 1.0])
    return pd.DataFrame([{
        'races': len(maxev),
        'max_ev_min': qv[0], 'max_ev_p10': qv[1], 'max_ev_p25': qv[2], 'max_ev_median': qv[3],
        'max_ev_p75': qv[4], 'max_ev_p90': qv[5], 'max_ev_p95': qv[6], 'max_ev_p99': qv[7], 'max_ev_max': qv[8],
        'avg_tickets_ev105': float(np.mean(count105)), 'avg_tickets_ev110': float(np.mean(count110)), 'avg_tickets_ev120': float(np.mean(count120)),
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

    v2.COND_GAMMA = 0.50
    best, calibration_grid = v1.tune_calibration(e, entry_pp)
    _, alpha, beta, temp = best
    _, gamma_grid = v2._tune_gamma(e, entry_pp, alpha, beta, temp)

    # May/June only: ordinary model calibration and interaction discovery.
    cal_pred, cal_win = v1.make_path_predictions(e, entry_pp, CAL_START, CAL_END, alpha, beta, temp)
    rf = v1.race_frame_for_signals(e, cal_pred, cal_win)
    signals = v1.discover_pair_signals(rf)
    lk = v1.signal_lookup(signals)

    # July/August remains the untouched test period.
    test_model_pred, _ = v1.make_path_predictions(e, entry_pp, TEST_START, TEST_END, alpha, beta, temp, lk)

    # Tune only the global shrinkage toward market on May/June NLL.
    blend_best, blend_grid = _tune_market_blend(cal_pred, base)
    lam = float(blend_best['model_weight'])
    test_blend_pred, _, _, _, _ = _blend_predictions(test_model_pred, base, TEST_START, TEST_END, lam)

    model_metrics, race_metrics = _quality(test_model_pred, test_blend_pred, base)

    sensitivity_rows = []
    monthly_rows = []
    primary = None
    for ev in EV_GRID:
        for k in BET_GRID:
            b = _evaluate(base, test_blend_pred, ev, k)
            st = _summary(b)
            sensitivity_rows.append({
                'ev_threshold': ev,
                'max_bets': k,
                'races_bet': int(b['レースコード'].nunique()) if len(b) else 0,
                **st,
            })
            for month, lo, hi in [('JULY','2026-07-01','2026-07-31'), ('AUGUST','2026-08-01','2026-08-28')]:
                bm = b[(b.race_date >= pd.Timestamp(lo)) & (b.race_date <= pd.Timestamp(hi))] if len(b) else b
                monthly_rows.append({
                    'month': month, 'ev_threshold': ev, 'max_bets': k,
                    'races_bet': int(bm['レースコード'].nunique()) if len(bm) else 0,
                    **_summary(bm),
                })
            if abs(ev - PRIMARY_EV) < 1e-12 and k == PRIMARY_MAX_BETS:
                primary = b.copy()

    sensitivity = pd.DataFrame(sensitivity_rows)
    monthly = pd.DataFrame(monthly_rows)
    primary = primary if primary is not None else pd.DataFrame()

    meta = pd.DataFrame([{
        'train_entry_rows': train_rows,
        'all_entry_rows': len(e),
        'numeric_features': len(nums),
        'categorical_features': len(cats),
        'alpha_role': alpha,
        'beta_adjusted': beta,
        'temperature': temp,
        'conditional_gamma': v2.COND_GAMMA,
        'pair_signals': len(signals),
        'market_weight': 1.0 - lam,
        'model_weight': lam,
        'blend_cal_nll': blend_best['cal_nll'],
        'primary_ev': PRIMARY_EV,
        'primary_max_bets': PRIMARY_MAX_BETS,
    }])

    edge = _edge_distribution(test_blend_pred, base)

    meta.to_csv(out/'meta.csv', index=False)
    model_metrics.to_csv(out/'model_metrics.csv', index=False)
    race_metrics.to_csv(out/'race_metrics.csv', index=False)
    calibration_grid.to_csv(out/'calibration_grid.csv', index=False)
    gamma_grid.to_csv(out/'conditional_gamma_grid.csv', index=False)
    blend_grid.to_csv(out/'market_blend_grid.csv', index=False)
    signals.to_csv(out/'pair_signals.csv', index=False)
    sensitivity.to_csv(out/'sensitivity.csv', index=False)
    monthly.to_csv(out/'monthly_sensitivity.csv', index=False)
    primary.to_csv(out/'primary_bets.csv', index=False)
    edge.to_csv(out/'edge_distribution.csv', index=False)

    print('MARKET PRIOR / MODEL RESIDUAL V3')
    print('\nMETA'); print(meta.to_string(index=False))
    print('\nMODEL QUALITY'); print(model_metrics.to_string(index=False))
    print('\nBLEND GRID TOP10'); print(blend_grid.head(10).to_string(index=False))
    print('\nSENSITIVITY'); print(sensitivity.to_string(index=False))
    print('\nMONTHLY'); print(monthly.to_string(index=False))
    print('\nEDGE DISTRIBUTION'); print(edge.to_string(index=False))


if __name__ == '__main__':
    main()
