#!/usr/bin/env python3
import math
import numpy as np
import pandas as pd
import backtest_ev as be
import full_probability_model as v1

_orig_stt_to_long = be.stt_to_long
_orig_feature_columns = v1.feature_columns

def _fixed_stt_to_long(stt):
    x = _orig_stt_to_long(stt)
    return x.drop(columns=['レース日'], errors='ignore')

be.stt_to_long = _fixed_stt_to_long

import full_probability_model_v2 as model

_orig_v2_feature_columns = model.feature_columns_v2
_orig_add_context_features = model._add_context_features

def _safe_feature_columns(e):
    current = v1.feature_columns
    v1.feature_columns = _orig_feature_columns
    try:
        return _orig_v2_feature_columns(e)
    finally:
        v1.feature_columns = current

def _safe_add_context_features(e, panel, roles):
    return _orig_add_context_features(e, panel, roles).reset_index(drop=True)

model.feature_columns_v2 = _safe_feature_columns
model._add_context_features = _safe_add_context_features


def _cal_arrays(e, entry_pp):
    z = e[(e.race_date >= model.CAL_START) & (e.race_date <= model.CAL_END)].copy()
    base_rows, role_rows, rating_rows, winners = [], [], [], []
    for _, g in z.groupby('レースコード', sort=False):
        gg = g.sort_values('expo_course')
        courses = pd.to_numeric(gg['expo_course'], errors='coerce').dropna().astype(int).tolist()
        if courses != list(range(1, 7)):
            continue
        wi = v1.winner_path_for_group(gg)
        if wi is None or wi < 0:
            continue
        idx = gg.index.to_numpy(dtype=int)
        base_rows.append(entry_pp[idx])
        rr = gg[['role_ratio1','role_ratio2','role_ratio3']].to_numpy(float)
        role_rows.append(np.where(np.isfinite(rr), rr, 1.0))
        rz = pd.to_numeric(gg['adjusted_rating_z'], errors='coerce').fillna(0).to_numpy(float)[:, None]
        rating_rows.append(rz)
        winners.append(int(wi))
    if not base_rows:
        return None
    return np.stack(base_rows), np.stack(role_rows), np.stack(rating_rows), np.asarray(winners, dtype=int)


def _path_matrix(w, gamma):
    n = w.shape[0]
    out = np.zeros((n, len(model.PATHS)), dtype=float)
    r2 = np.power(np.clip(model.RATIO2, 1e-9, None), gamma)
    r3 = np.power(np.clip(model.RATIO3, 1e-9, None), gamma)
    sec_den = {}
    third_den = {}
    for a in range(6):
        sw = w[:,:,1] * r2[a][None,:]
        sec_den[a] = sw.sum(axis=1) - sw[:,a]
        for b in range(6):
            if b == a:
                continue
            tw = w[:,:,2] * r3[a,b][None,:]
            third_den[(a,b)] = tw.sum(axis=1) - tw[:,a] - tw[:,b]
    for pi, (a1,b1,c1) in enumerate(model.PATHS):
        a,b,c = a1-1,b1-1,c1-1
        d2 = np.maximum(sec_den[a], 1e-12)
        d3 = np.maximum(third_den[(a,b)], 1e-12)
        out[:,pi] = w[:,a,0] * (w[:,b,1] * r2[a,b] / d2) * (w[:,c,2] * r3[a,b,c] / d3)
    out /= np.maximum(out.sum(axis=1, keepdims=True), 1e-12)
    return out


def _nll(p, winners, temp):
    if temp != 1.0:
        p = np.power(np.clip(p, 1e-12, 1.0), 1.0/temp)
        p /= np.maximum(p.sum(axis=1, keepdims=True), 1e-12)
    chosen = np.maximum(p[np.arange(len(winners)), winners], 1e-12)
    return float(np.mean(-np.log(chosen)))


def _fast_tune_calibration(e, entry_pp):
    arr = _cal_arrays(e, entry_pp)
    if arr is None:
        return (np.inf,0.0,0.0,1.0), pd.DataFrame()
    base, role, rating, winners = arr
    rows=[]; best=None
    gamma=float(model.COND_GAMMA)
    for alpha in [0.0,.25,.50,.75,1.0]:
        rf=np.power(np.clip(role,1e-9,None),alpha)
        for beta in [0.0,.08,.16,.24]:
            w=base*rf*np.exp(beta*rating)
            w/=np.maximum(w.sum(axis=1,keepdims=True),1e-12)
            p=_path_matrix(w,gamma)
            for temp in [.80,1.00,1.20,1.40,1.60]:
                loss=_nll(p,winners,temp)
                rows.append({'alpha_role':alpha,'beta_adjusted':beta,'temperature':temp,'cal_nll':loss,'races':len(winners)})
                if best is None or loss<best[0]:
                    best=(loss,alpha,beta,temp)
    return best,pd.DataFrame(rows).sort_values('cal_nll')


def _fast_tune_gamma(e, entry_pp, alpha, beta, temp):
    arr=_cal_arrays(e,entry_pp)
    if arr is None:
        return (np.inf,0.0),pd.DataFrame()
    base,role,rating,winners=arr
    w=base*np.power(np.clip(role,1e-9,None),alpha)*np.exp(beta*rating)
    w/=np.maximum(w.sum(axis=1,keepdims=True),1e-12)
    rows=[]; best=None
    for gamma in [0.0,.25,.50,.75,1.00]:
        p=_path_matrix(w,gamma)
        loss=_nll(p,winners,temp)
        rows.append({'conditional_gamma':gamma,'cal_nll':loss,'races':len(winners)})
        if best is None or loss<best[0]:
            best=(loss,gamma)
    model.COND_GAMMA=best[1]
    return best,pd.DataFrame(rows).sort_values('cal_nll')

v1.tune_calibration = _fast_tune_calibration
model._tune_gamma = _fast_tune_gamma

if __name__ == '__main__':
    model.main()
