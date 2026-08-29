#!/usr/bin/env python3
import math
import numpy as np
import pandas as pd
import backtest_ev as be

# Avoid duplicate race-date columns when exhibition data are joined to the card.
_orig_stt_to_long = be.stt_to_long

def _fixed_stt_to_long(stt):
    x = _orig_stt_to_long(stt)
    return x.drop(columns=['レース日'], errors='ignore')

be.stt_to_long = _fixed_stt_to_long

import full_probability_model as model

# Ensure entry-probability array positions match DataFrame indices after lineup filtering.
_orig_build_entries = model.build_entries

def _fixed_build_entries(src):
    e, panel, roles, base = _orig_build_entries(src)
    return e.reset_index(drop=True), panel, roles, base

model.build_entries = _fixed_build_entries

# Same 5 x 4 x 5 calibration grid as the original implementation, but vectorized.
# This changes computation speed only; chronology and candidate parameters are unchanged.
def _fast_tune_calibration(e, entry_pp):
    z = e[(e.race_date >= model.CAL_START) & (e.race_date <= model.CAL_END)].copy()
    base_rows = []
    role_rows = []
    rating_rows = []
    winners = []

    for _, g in z.groupby('レースコード', sort=False):
        gg = g.sort_values('expo_course')
        courses = pd.to_numeric(gg['expo_course'], errors='coerce').dropna().astype(int).tolist()
        if courses != list(range(1, 7)):
            continue
        wi = model.winner_path_for_group(gg)
        if wi is None or wi < 0:
            continue
        idx = gg.index.to_numpy(dtype=int)
        base_rows.append(entry_pp[idx])
        rr = gg[['role_ratio1', 'role_ratio2', 'role_ratio3']].to_numpy(float)
        role_rows.append(np.where(np.isfinite(rr), rr, 1.0))
        rz = pd.to_numeric(gg['adjusted_rating_z'], errors='coerce').fillna(0).to_numpy(float)[:, None]
        rating_rows.append(rz)
        winners.append(int(wi))

    if not base_rows:
        return (np.inf, 0.0, 0.0, 1.0), pd.DataFrame()

    base = np.stack(base_rows)          # races x 6 x 3
    role = np.stack(role_rows)          # races x 6 x 3
    rating = np.stack(rating_rows)      # races x 6 x 1
    winners = np.asarray(winners, dtype=int)
    ridx = np.arange(len(winners))

    aidx = np.asarray([p[0] - 1 for p in model.PATHS], dtype=int)
    bidx = np.asarray([p[1] - 1 for p in model.PATHS], dtype=int)
    cidx = np.asarray([p[2] - 1 for p in model.PATHS], dtype=int)

    rows = []
    best = None
    for alpha in [0.0, .25, .50, .75, 1.0]:
        role_factor = np.power(np.clip(role, 1e-9, None), alpha)
        for beta in [0.0, .08, .16, .24]:
            w = base * role_factor * np.exp(beta * rating)
            w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-12)
            p = w[:, aidx, 0] * w[:, bidx, 1] * w[:, cidx, 2]
            p /= np.maximum(p.sum(axis=1, keepdims=True), 1e-12)
            for temp in [.80, 1.00, 1.20, 1.40, 1.60]:
                if temp == 1.0:
                    pt = p
                else:
                    pt = np.power(np.clip(p, 1e-12, 1.0), 1.0 / temp)
                    pt /= np.maximum(pt.sum(axis=1, keepdims=True), 1e-12)
                chosen = np.maximum(pt[ridx, winners], 1e-12)
                loss = float(np.mean(-np.log(chosen)))
                rows.append({'alpha_role': alpha, 'beta_adjusted': beta, 'temperature': temp,
                             'cal_nll': loss, 'races': len(winners)})
                if best is None or loss < best[0]:
                    best = (loss, alpha, beta, temp)

    return best, pd.DataFrame(rows).sort_values('cal_nll')

model.tune_calibration = _fast_tune_calibration

if __name__ == '__main__':
    model.main()
