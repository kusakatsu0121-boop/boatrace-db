#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a

# V8 policy: the model is structurally independent of odds.
# Odds are used only for market comparison / EV after probabilities are frozen.
FAMILIES = [
    'PUBLISHED_ABILITY',
    'ST',
    'MOTOR_BOAT',
    'EXHIBITION',
    'VENUE',
    'ATTACK_ESCAPE',
]
CORE_SHARE_GRID = [0.80, 0.85, 0.90]
PATH_COND_SHARE_GRID = [0.00, 0.05, 0.10, 0.15, 0.20]
PATH_TEMP_GRID = [1.00, 1.10, 1.20]
MAX_ENTRY_SHIFT_PT = 5.0  # absolute probability-point cap per class vs CORE


def _labels(e: pd.DataFrame) -> np.ndarray:
    f = pd.to_numeric(e['finish'], errors='coerce')
    return np.where(f.eq(1), 0, np.where(f.eq(2), 1, np.where(f.eq(3), 2, 3)))


def _entry_nll(e: pd.DataFrame, pp: np.ndarray, start, end) -> float:
    mask = (e.race_date >= start) & (e.race_date <= end) & e.finish.notna()
    idx = np.flatnonzero(mask.to_numpy())
    if not len(idx):
        return np.nan
    y = _labels(e.iloc[idx])
    # pp only carries p1,p2,p3; p4plus is residual.
    p4 = np.clip(1.0 - pp[idx].sum(axis=1), 1e-9, 1.0)
    full = np.column_stack([pp[idx], p4])
    full = np.clip(full, 1e-9, 1.0)
    full /= full.sum(axis=1, keepdims=True)
    return float(np.mean(-np.log(full[np.arange(len(idx)), y])))


def _blend_entry(core: np.ndarray, fam_pp: dict[str, np.ndarray], fam_w: dict[str, float], core_share: float) -> np.ndarray:
    if not fam_w or sum(fam_w.values()) <= 0:
        return core.copy()
    addon = np.zeros_like(core, dtype=float)
    z = float(sum(fam_w.values()))
    for fam, w in fam_w.items():
        addon += (float(w) / z) * fam_pp[fam]
    raw = core_share * core + (1.0 - core_share) * addon

    # Explainability / safety guard: addons may move each class by at most ±5 points vs CORE.
    cap = MAX_ENTRY_SHIFT_PT / 100.0
    raw = np.minimum(np.maximum(raw, core - cap), core + cap)
    raw = np.clip(raw, 1e-8, 1.0)
    # Keep p1+p2+p3 below 1 so residual p4plus remains valid.
    s = raw.sum(axis=1)
    over = s >= 0.999999
    if np.any(over):
        raw[over] *= (0.999999 / s[over])[:, None]
    return raw


def _family_weights(e, core_pp, fam_pp):
    core_nll = _entry_nll(e, core_pp, a.CAL_START, a.CAL_END)
    rows = []
    positive = {}
    for fam in FAMILIES:
        nll = _entry_nll(e, fam_pp[fam], a.CAL_START, a.CAL_END)
        gain = core_nll - nll
        rows.append({'family': fam, 'core_nll': core_nll, 'core_plus_family_nll': nll, 'nll_gain_vs_core': gain})
        if np.isfinite(gain) and gain > 0:
            positive[fam] = float(gain)
    s = sum(positive.values())
    weights = {fam: (positive.get(fam, 0.0) / s if s > 0 else 0.0) for fam in FAMILIES}
    for r in rows:
        r['addon_weight_within_addons'] = weights[r['family']]
    return weights, pd.DataFrame(rows)


def _tune_core_share(e, core_pp, fam_pp, fam_w):
    rows=[]; best=None
    for cs in CORE_SHARE_GRID:
        pp = _blend_entry(core_pp, fam_pp, fam_w, cs)
        nll = _entry_nll(e, pp, a.CAL_START, a.CAL_END)
        row={'core_share': cs, 'addon_share':1.0-cs, 'cal_entry_nll':nll}
        rows.append(row)
        if best is None or nll < best['cal_entry_nll']:
            best=row.copy()
    return best, pd.DataFrame(rows), _blend_entry(core_pp, fam_pp, fam_w, best['core_share'])


def _path_probs(g: pd.DataFrame, entry_pp: np.ndarray, cond_share: float, temp: float):
    gg=g.sort_values('expo_course')
    courses=pd.to_numeric(gg['expo_course'], errors='coerce').dropna().astype(int).tolist()
    if courses != list(range(1,7)):
        return None
    idx=gg.index.to_numpy(dtype=int)
    w=entry_pp[idx].copy()
    w /= np.maximum(w.sum(axis=0, keepdims=True), 1e-12)

    p0=np.zeros(len(a.m.PATHS), dtype=float)
    pc=np.zeros(len(a.m.PATHS), dtype=float)
    r2=np.clip(a.v2.RATIO2,1e-9,None)
    r3=np.clip(a.v2.RATIO3,1e-9,None)
    for pi,(a1,b1,c1) in enumerate(a.m.PATHS):
        x,y,z=a1-1,b1-1,c1-1
        # CORE sequential path: only entry probabilities / course strength, no conditional ratio boost.
        d2=max(float(w[:,1].sum()-w[x,1]),1e-12)
        d3=max(float(w[:,2].sum()-w[x,2]-w[y,2]),1e-12)
        p0[pi]=w[x,0]*(w[y,1]/d2)*(w[z,2]/d3)

        # Course-order correction candidate.
        sw=w[:,1]*r2[x]
        cd2=max(float(sw.sum()-sw[x]),1e-12)
        tw=w[:,2]*r3[x,y]
        cd3=max(float(tw.sum()-tw[x]-tw[y]),1e-12)
        pc[pi]=w[x,0]*(w[y,1]*r2[x,y]/cd2)*(w[z,2]*r3[x,y,z]/cd3)

    p0/=max(float(p0.sum()),1e-12)
    pc/=max(float(pc.sum()),1e-12)
    p=(1.0-cond_share)*p0+cond_share*pc
    p/=max(float(p.sum()),1e-12)
    if temp != 1.0:
        p=np.power(np.clip(p,1e-12,1.0),1.0/temp)
        p/=p.sum()
    return p


def _make_paths(e, entry_pp, start, end, cond_share, temp):
    probs={}; winners={}
    z=e[(e.race_date>=start)&(e.race_date<=end)]
    for code,g in z.groupby('レースコード',sort=False):
        p=_path_probs(g,entry_pp,cond_share,temp)
        wi=a.winner_idx(g)
        if p is not None and wi is not None:
            probs[str(code)]=p; winners[str(code)]=int(wi)
    return probs,winners


def _nll(probs,winners):
    vals=[-math.log(max(float(probs[c][w]),1e-12)) for c,w in winners.items() if c in probs]
    return float(np.mean(vals)) if vals else np.nan


def _top_rate(probs,winners):
    vals=[int(np.argmax(probs[c])==w) for c,w in winners.items() if c in probs]
    return float(np.mean(vals)) if vals else np.nan


def _tune_path(e, entry_pp):
    rows=[]; best=None
    for cs in PATH_COND_SHARE_GRID:
        for temp in PATH_TEMP_GRID:
            p,w=_make_paths(e,entry_pp,a.CAL_START,a.CAL_END,cs,temp)
            nll=_nll(p,w)
            row={'conditional_course_share':cs,'path_temperature':temp,'cal_path_nll':nll,'races':len(w)}
            rows.append(row)
            if best is None or nll < best['cal_path_nll']:
                best=row.copy()
    return best,pd.DataFrame(rows)


def _period_metrics(e, core_pp, final_pp, start, end, path_cfg):
    cp,cw=_make_paths(e,core_pp,start,end,0.0,1.0)
    vp,vw=_make_paths(e,final_pp,start,end,path_cfg['conditional_course_share'],path_cfg['path_temperature'])
    return {
        'races':len(vw),
        'core_path_nll':_nll(cp,cw),
        'v8_path_nll':_nll(vp,vw),
        'core_top_rate':_top_rate(cp,cw),
        'v8_top_rate':_top_rate(vp,vw),
    }, vp


def _contribution_table(core_pp, fam_pp, fam_w, core_share):
    rows=[]
    addon_budget=1.0-core_share
    for fam in FAMILIES:
        w=fam_w.get(fam,0.0)
        delta=addon_budget*w*(fam_pp[fam]-core_pp)
        rows.append({
            'family':fam,
            'total_model_share_pct':100.0*addon_budget*w,
            'mean_abs_probability_shift_pt':100.0*float(np.mean(np.abs(delta))),
            'p95_abs_probability_shift_pt':100.0*float(np.quantile(np.abs(delta),0.95)),
            'max_abs_probability_shift_pt':100.0*float(np.max(np.abs(delta))),
        })
    rows.insert(0,{
        'family':'CORE_ABILITY_COURSE',
        'total_model_share_pct':100.0*core_share,
        'mean_abs_probability_shift_pt':np.nan,
        'p95_abs_probability_shift_pt':np.nan,
        'max_abs_probability_shift_pt':np.nan,
    })
    return pd.DataFrame(rows)


def main():
    out=Path('artifacts/v8_interpretable'); out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e).reset_index(drop=True)

    # Train CORE and CORE+one-family models on pre-May only.
    core_nums,core_cats=a.columns_for(e,[])
    core_model,_=a.fit_model(e,core_nums,core_cats)
    core_pp=a.entry_probs(core_model,e,core_nums,core_cats)

    fam_pp={}
    for fam in FAMILIES:
        nums,cats=a.columns_for(e,[fam])
        model,_=a.fit_model(e,nums,cats)
        fam_pp[fam]=a.entry_probs(model,e,nums,cats)

    fam_w,fam_table=_family_weights(e,core_pp,fam_pp)
    share_best,share_grid,final_pp=_tune_core_share(e,core_pp,fam_pp,fam_w)
    path_best,path_grid=_tune_path(e,final_pp)

    periods=[
        ('MAY_JUN',a.CAL_START,a.CAL_END),
        ('JULY',a.JULY_START,a.JULY_END),
        ('AUGUST',a.AUG_START,a.AUG_END),
    ]
    metrics=[]
    for name,s,t in periods:
        row,_=_period_metrics(e,core_pp,final_pp,s,t,path_best)
        row['period']=name; metrics.append(row)

    contrib=_contribution_table(core_pp,fam_pp,fam_w,share_best['core_share'])
    fam_table['total_model_share_pct']=fam_table['addon_weight_within_addons']*(1.0-share_best['core_share'])*100.0

    # Extra sanity diagnostics: how far final entry probs moved from CORE.
    shift=np.abs(final_pp-core_pp)
    sanity=pd.DataFrame([{
        'core_share_pct':share_best['core_share']*100.0,
        'addon_share_pct':share_best['addon_share']*100.0,
        'mean_abs_entry_shift_pt':100.0*float(np.mean(shift)),
        'p95_abs_entry_shift_pt':100.0*float(np.quantile(shift,0.95)),
        'max_abs_entry_shift_pt':100.0*float(np.max(shift)),
        'entry_shift_cap_pt':MAX_ENTRY_SHIFT_PT,
        'conditional_course_share_pct':path_best['conditional_course_share']*100.0,
        'path_temperature':path_best['path_temperature'],
        'odds_used_in_structural_prediction':False,
    }])

    fam_table.to_csv(out/'family_selection.csv',index=False)
    share_grid.to_csv(out/'core_share_grid.csv',index=False)
    path_grid.to_csv(out/'path_grid.csv',index=False)
    contrib.to_csv(out/'final_weight_table.csv',index=False)
    pd.DataFrame(metrics).to_csv(out/'period_metrics.csv',index=False)
    sanity.to_csv(out/'sanity.csv',index=False)

    print('\nFINAL WEIGHTS')
    print(contrib.to_string(index=False))
    print('\nSANITY')
    print(sanity.to_string(index=False))
    print('\nPERIOD METRICS')
    print(pd.DataFrame(metrics).to_string(index=False))


if __name__=='__main__':
    main()
