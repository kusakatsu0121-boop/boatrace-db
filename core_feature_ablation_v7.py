#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# Reuse the leakage-safe historical data construction only.  The experiment
# below never uses archived series_* fields as predictors.
import run_market_blend_v4_leak_safe as leak

aug = leak.aug
m = aug.m
v1 = m.v1
v2 = m.v2
be = m.be

TRAIN_END = pd.Timestamp('2026-05-01')
CAL_START = pd.Timestamp('2026-05-01')
CAL_END = pd.Timestamp('2026-06-30')
JULY_START = pd.Timestamp('2026-07-01')
JULY_END = pd.Timestamp('2026-07-31')
AUG_START = pd.Timestamp('2026-08-01')
AUG_END = pd.Timestamp('2026-08-28')
TEMP_GRID = [0.80, 1.00, 1.20, 1.40, 1.60]
GAMMA_GRID = [0.00, 0.25, 0.50, 0.75, 1.00]
LAMBDA_GRID = np.round(np.arange(0.0, 1.0001, 0.05), 2)


def _num(s):
    return pd.to_numeric(s, errors='coerce')


def _add_interactions(e: pd.DataFrame) -> pd.DataFrame:
    e = e.copy()
    venue = _num(e.get('venue')).fillna(-1).astype(int).astype(str)
    course = _num(e.get('expo_course')).fillna(-1).astype(int).astype(str)
    e['venue_course'] = venue + '_' + course
    ws = _num(e.get('wind_speed'))
    wb = pd.cut(ws, [-np.inf, 1.5, 3.5, 5.5, np.inf], labels=['0-1','2-3','4-5','6+']).astype(str)
    wave = _num(e.get('wave'))
    wavb = pd.cut(wave, [-np.inf, 2, 5, 10, np.inf], labels=['0-2','3-5','6-10','11+']).astype(str)
    wd = e.get('wind_dir', pd.Series('nan', index=e.index)).astype(str)
    e['venue_course_wind'] = e['venue_course'] + '_' + wd + '_' + wb
    e['venue_course_wave'] = e['venue_course'] + '_' + wavb
    return e


CORE_NUM = [
    'adjusted_rating_z',
    'p1', 'p2', 'p3', 'top2', 'top3',
]
CORE_CAT = ['expo_course']

FAMILIES = {
    'PUBLISHED_ABILITY': {
        'num': [
            'national_win_rate','national_2rate','national_3rate',
            'local_win_rate','local_2rate','local_3rate',
            'national_win_rate_rel','national_win_rate_rank',
            'national_2rate_rel','national_2rate_rank',
            'national_3rate_rel','national_3rate_rank',
            'local_win_rate_rel','local_win_rate_rank',
            'local_2rate_rel','local_2rate_rank',
            'local_3rate_rel','local_3rate_rank','class_num',
        ],
        'cat': ['class_grade'],
    },
    'VENUE': {
        'num': [],
        'cat': ['venue_course'],
    },
    'ST': {
        'num': [
            'pub_avg_st','pub_avg_st_rel','pub_avg_st_rank','avg_st','st_edge',
            'expo_st','expo_st_rel','expo_st_rank','st_correction','st_delta_sd',
            'pred_st','pred_st_rel','pred_st_rank','st_edge_inner','st_edge_outer',
            'inside_st_pressure','pred_fastest_flag',
        ],
        'cat': [],
    },
    'MOTOR_BOAT': {
        'num': [
            'motor_2rate','motor_3rate','boat_2rate','boat_3rate',
            'motor_2rate_rel','motor_2rate_rank','motor_3rate_rel','motor_3rate_rank',
            'boat_2rate_rel','boat_2rate_rank','boat_3rate_rel','boat_3rate_rank',
        ],
        'cat': [],
    },
    'EXHIBITION': {
        'num': [
            'ex_time','ex_time_rel','ex_time_rank','weight','weight_rel','weight_rank',
            'weight_adjust','tilt','tilt_rel','tilt_rank',
        ],
        'cat': [],
    },
    'WEATHER_VENUE': {
        'num': ['wind_speed','wave','air_temp','water_temp'],
        'cat': ['weather','wind_dir','venue_course_wind','venue_course_wave'],
    },
    'ATTACK_ESCAPE': {
        'num': [
            'allow_escape','attack_proxy_rate','attack_start_edge','attack_conversion',
            'inner_damage_rate','outer_supply_rate','resist_rate','resist_top3',
            'true_escape_adj','c1_true_escape_adj','escape_influence_score','race_escape_pressure',
        ],
        'cat': [],
    },
    'F_STAGE': {
        'num': ['f_count','l_count','days_since_f','f_recent30','f_recent60','day_no','late_series','race_grade_num'],
        'cat': ['race_stage'],
    },
}


def columns_for(e: pd.DataFrame, families: list[str]):
    nums = [c for c in CORE_NUM if c in e.columns]
    cats = [c for c in CORE_CAT if c in e.columns]
    for fam in families:
        for c in FAMILIES[fam]['num']:
            if c in e.columns and c not in nums and not c.startswith('series_'):
                nums.append(c)
        for c in FAMILIES[fam]['cat']:
            if c in e.columns and c not in cats:
                cats.append(c)
    return nums, cats


def fit_model(e: pd.DataFrame, nums: list[str], cats: list[str]):
    tr = e[(e.race_date < TRAIN_END) & e.finish.notna()].copy()
    tr['y'] = np.where(tr.finish.eq(1), 0, np.where(tr.finish.eq(2), 1, np.where(tr.finish.eq(3), 2, 3)))
    pre = ColumnTransformer([
        ('num', Pipeline([('imp', SimpleImputer(strategy='median')), ('sc', StandardScaler())]), nums),
        ('cat', Pipeline([('imp', SimpleImputer(strategy='most_frequent')), ('oh', OneHotEncoder(handle_unknown='ignore', min_frequency=10))]), cats),
    ])
    clf = LogisticRegression(max_iter=350, C=.55, solver='lbfgs')
    pipe = Pipeline([('pre', pre), ('clf', clf)])
    pipe.fit(tr[nums + cats], tr['y'])
    return pipe, len(tr)


def entry_probs(model, e, nums, cats):
    pp = model.predict_proba(e[nums + cats])
    cls = list(model.named_steps['clf'].classes_)
    out = np.zeros((len(e), 3), dtype=float)
    for pos in (0,1,2):
        if pos in cls:
            out[:, pos] = pp[:, cls.index(pos)]
    return np.clip(out, 1e-8, 1.0)


def path_prob(g, pp, temp: float, gamma: float):
    gg = g.sort_values('expo_course')
    courses = _num(gg['expo_course']).dropna().astype(int).tolist()
    if courses != list(range(1,7)):
        return None
    idx = gg.index.to_numpy(dtype=int)
    w = pp[idx].copy()
    w /= np.maximum(w.sum(axis=0, keepdims=True), 1e-12)
    r2 = np.power(np.clip(v2.RATIO2, 1e-9, None), gamma)
    r3 = np.power(np.clip(v2.RATIO3, 1e-9, None), gamma)
    p = np.zeros(len(m.PATHS), dtype=float)
    for pi, (a1,b1,c1) in enumerate(m.PATHS):
        a,b,c = a1-1,b1-1,c1-1
        sw = w[:,1] * r2[a]
        d2 = max(float(sw.sum() - sw[a]), 1e-12)
        tw = w[:,2] * r3[a,b]
        d3 = max(float(tw.sum() - tw[a] - tw[b]), 1e-12)
        p[pi] = w[a,0] * (w[b,1] * r2[a,b] / d2) * (w[c,2] * r3[a,b,c] / d3)
    p /= max(float(p.sum()), 1e-12)
    if temp != 1.0:
        p = np.power(np.clip(p, 1e-12, 1.0), 1.0 / temp)
        p /= p.sum()
    return p


def winner_idx(g):
    z = g.dropna(subset=['finish']).sort_values('finish')
    if len(z) < 3:
        return None
    t = tuple(int(x) for x in z.head(3)['expo_course'])
    return m.PATH_TO_IDX.get(t)


def make_predictions(e, pp, start, end, temp, gamma):
    probs, winners = {}, {}
    z = e[(e.race_date >= start) & (e.race_date <= end)]
    for code, g in z.groupby('レースコード', sort=False):
        p = path_prob(g, pp, temp, gamma)
        wi = winner_idx(g)
        if p is not None and wi is not None:
            probs[str(code)] = p
            winners[str(code)] = int(wi)
    return probs, winners


def nll_for(probs, winners):
    vals = [-math.log(max(float(probs[c][w]), 1e-12)) for c,w in winners.items() if c in probs]
    return float(np.mean(vals)) if vals else np.nan


def tune_path(e, pp):
    rows=[]; best=None
    for gamma in GAMMA_GRID:
        for temp in TEMP_GRID:
            probs, wins = make_predictions(e, pp, CAL_START, CAL_END, temp, gamma)
            loss = nll_for(probs, wins)
            row={'gamma':gamma,'temperature':temp,'cal_nll':loss,'races':len(wins)}
            rows.append(row)
            if best is None or loss < best['cal_nll']:
                best=row.copy()
    return best, pd.DataFrame(rows)


def period_market(base, start, end):
    races = base[(base.race_date >= start) & (base.race_date <= end)].reset_index(drop=True)
    odds, q, winner_path, _ = be.odds_in_exhibition_course_order(races)
    return races, odds, q, winner_path


def blend(p, q, lam):
    pp = m._norm(p); qq = m._norm(q)
    return m._blend(pp, qq, float(lam))


def tune_market_weight(probs, base, venue=None):
    races, _, q, wi = period_market(base, JULY_START, JULY_END)
    if venue is not None:
        races = races.copy()
    rows=[]; best=None
    for lam in LAMBDA_GRID:
        losses=[]
        for i,r in races.iterrows():
            if venue is not None and int(pd.to_numeric(r.get('レース場コード', r.get('レース場', -1)), errors='coerce')) != int(venue):
                continue
            code=str(r['レースコード']); w=int(wi[i])
            if code not in probs or w < 0 or not np.isfinite(q[i]).any():
                continue
            b=blend(probs[code], q[i], lam)
            losses.append(-math.log(max(float(b[w]),1e-12)))
        if not losses:
            continue
        row={'model_weight':float(lam),'market_weight':1.0-float(lam),'nll':float(np.mean(losses)),'races':len(losses)}
        rows.append(row)
        if best is None or row['nll'] < best['nll']:
            best=row.copy()
    return best, pd.DataFrame(rows)


def eval_aug(probs, base, lam, venue_weights=None):
    races, _, q, wi = period_market(base, AUG_START, AUG_END)
    rows=[]
    for i,r in races.iterrows():
        code=str(r['レースコード']); w=int(wi[i])
        if code not in probs or w < 0 or not np.isfinite(q[i]).any():
            continue
        venue=int(pd.to_numeric(r.get('レース場コード', r.get('レース場', -1)), errors='coerce'))
        use_lam=float(venue_weights.get(venue,lam)) if venue_weights else float(lam)
        pp=m._norm(probs[code]); qq=m._norm(q[i]); bb=blend(pp,qq,use_lam)
        rows.append({
            'race_date':r.race_date,'venue':venue,
            'standalone_nll':-math.log(max(float(pp[w]),1e-12)),
            'blend_nll':-math.log(max(float(bb[w]),1e-12)),
            'market_nll':-math.log(max(float(qq[w]),1e-12)),
            'standalone_top':int(np.argmax(pp)==w),'blend_top':int(np.argmax(bb)==w),'market_top':int(np.argmax(qq)==w),
        })
    d=pd.DataFrame(rows)
    if d.empty:
        return {}, d
    s={
        'aug_races':len(d),
        'aug_standalone_nll':d.standalone_nll.mean(),
        'aug_blend_nll':d.blend_nll.mean(),
        'aug_market_nll':d.market_nll.mean(),
        'aug_delta_vs_market':d.blend_nll.mean()-d.market_nll.mean(),
        'aug_standalone_top':d.standalone_top.mean(),
        'aug_blend_top':d.blend_top.mean(),
        'aug_market_top':d.market_top.mean(),
    }
    return s,d


def coefficient_mass(model, nums, cats, family_membership):
    try:
        names=model.named_steps['pre'].get_feature_names_out()
        coef=np.abs(model.named_steps['clf'].coef_).mean(axis=0)
    except Exception:
        return pd.DataFrame()
    rows=[]
    for name,val in zip(names,coef):
        raw=str(name).split('__',1)[-1]
        fam='UNKNOWN'
        for f,cols in family_membership.items():
            if any(raw==c or raw.startswith(c+'_') for c in cols):
                fam=f; break
        rows.append({'transformed_feature':name,'family':fam,'abs_coef':float(val)})
    z=pd.DataFrame(rows)
    if z.empty:return z
    g=z.groupby('family').agg(features=('abs_coef','size'),coef_mass=('abs_coef','sum'),mean_abs_coef=('abs_coef','mean')).reset_index()
    g['coef_mass_share']=g.coef_mass/g.coef_mass.sum()
    return g.sort_values('coef_mass_share',ascending=False)


def main():
    out=Path('artifacts/core_feature_ablation_v7'); out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=v1.build_entries(Path('source/data'))
    e=v2._add_context_features(e,panel,roles).reset_index(drop=True)
    v2._build_conditional_ratios(e)
    e=_add_interactions(e)

    fams=list(FAMILIES)
    specs={'CORE':[]}
    for f in fams: specs[f'CORE+{f}']=[f]
    specs['FULL']=fams.copy()
    for f in fams: specs[f'FULL-{f}']=[x for x in fams if x!=f]

    results=[]; models={}; predictions={}; path_tunes={}; july_weights={}; aug_details={}
    full_mass=pd.DataFrame()

    for name,fs in specs.items():
        nums,cats=columns_for(e,fs)
        model,ntrain=fit_model(e,nums,cats)
        pp=entry_probs(model,e,nums,cats)
        best,grid=tune_path(e,pp)
        july_pred,_=make_predictions(e,pp,JULY_START,JULY_END,best['temperature'],best['gamma'])
        wbest,wgrid=tune_market_weight(july_pred,base)
        aug_pred,_=make_predictions(e,pp,AUG_START,AUG_END,best['temperature'],best['gamma'])
        sm,detail=eval_aug(aug_pred,base,wbest['model_weight'])
        row={'model':name,'families':'|'.join(fs) if fs else 'CORE_ONLY','numeric_features':len(nums),'categorical_features':len(cats),'train_rows':ntrain,
             'cal_nll':best['cal_nll'],'gamma':best['gamma'],'temperature':best['temperature'],
             'july_model_weight':wbest['model_weight'],'july_blend_nll':wbest['nll'],**sm}
        results.append(row)
        models[name]=(model,nums,cats); predictions[name]=aug_pred; path_tunes[name]=grid; july_weights[name]=wgrid; aug_details[name]=detail
        if name=='FULL':
            membership={'CORE':CORE_NUM+CORE_CAT}
            for f in fams: membership[f]=FAMILIES[f]['num']+FAMILIES[f]['cat']
            full_mass=coefficient_mass(model,nums,cats,membership)
        print(name,row)

    res=pd.DataFrame(results)
    core_cal=float(res.loc[res.model.eq('CORE'),'cal_nll'].iloc[0])
    full_cal=float(res.loc[res.model.eq('FULL'),'cal_nll'].iloc[0])
    diag=[]
    for f in fams:
        add=res[res.model.eq(f'CORE+{f}')].iloc[0]
        rem=res[res.model.eq(f'FULL-{f}')].iloc[0]
        diag.append({
            'family':f,
            'cal_delta_add_to_core':float(add.cal_nll-core_cal),
            'cal_delta_remove_from_full':float(rem.cal_nll-full_cal),
            'aug_delta_vs_market_core_plus':float(add.aug_delta_vs_market),
            'aug_delta_vs_market_full_minus':float(rem.aug_delta_vs_market),
            'keep_by_calibration':bool((add.cal_nll < core_cal) or (rem.cal_nll > full_cal)),
        })
    diag=pd.DataFrame(diag)
    selected=diag.loc[diag.keep_by_calibration,'family'].tolist()

    # One-pass compact model selected only from May/June calibration diagnostics.
    nums,cats=columns_for(e,selected)
    model,ntrain=fit_model(e,nums,cats); pp=entry_probs(model,e,nums,cats)
    best,grid=tune_path(e,pp)
    july_pred,_=make_predictions(e,pp,JULY_START,JULY_END,best['temperature'],best['gamma'])
    wbest,wgrid=tune_market_weight(july_pred,base)
    aug_pred,_=make_predictions(e,pp,AUG_START,AUG_END,best['temperature'],best['gamma'])
    compact_sm,compact_detail=eval_aug(aug_pred,base,wbest['model_weight'])
    compact_row={'model':'COMPACT_SELECTED','families':'|'.join(selected) if selected else 'CORE_ONLY','numeric_features':len(nums),'categorical_features':len(cats),'train_rows':ntrain,
                 'cal_nll':best['cal_nll'],'gamma':best['gamma'],'temperature':best['temperature'],'july_model_weight':wbest['model_weight'],'july_blend_nll':wbest['nll'],**compact_sm}
    res=pd.concat([res,pd.DataFrame([compact_row])],ignore_index=True)

    # Venue-specific market/model trust for the compact model. July only, shrunk to global.
    venue_rows=[]; venue_weights={}
    global_lam=float(wbest['model_weight'])
    july_races,_,_,_=period_market(base,JULY_START,JULY_END)
    venue_col='レース場コード' if 'レース場コード' in july_races.columns else 'レース場'
    for venue,n in pd.to_numeric(july_races[venue_col],errors='coerce').dropna().astype(int).value_counts().items():
        vb,_=tune_market_weight(july_pred,base,int(venue))
        if vb is None: continue
        shrink=float(n)/(float(n)+80.0)
        shrunk=global_lam+shrink*(float(vb['model_weight'])-global_lam)
        venue_weights[int(venue)]=shrunk
        venue_rows.append({'venue':int(venue),'july_races':int(n),'raw_best_model_weight':vb['model_weight'],'global_model_weight':global_lam,'shrink':shrink,'shrunk_model_weight':shrunk,'july_nll':vb['nll']})
    venue_weights_df=pd.DataFrame(venue_rows)
    venue_sm,venue_detail=eval_aug(aug_pred,base,global_lam,venue_weights)

    # Venue family effects are exploratory August diagnostics for CORE/FULL/COMPACT only.
    venue_diag=[]
    for label,detail in [('CORE',aug_details['CORE']),('FULL',aug_details['FULL']),('COMPACT_SELECTED',compact_detail),('COMPACT_VENUE_WEIGHT',venue_detail)]:
        if detail.empty: continue
        for venue,g in detail.groupby('venue'):
            venue_diag.append({'model':label,'venue':int(venue),'races':len(g),'standalone_nll':g.standalone_nll.mean(),'blend_nll':g.blend_nll.mean(),'market_nll':g.market_nll.mean(),'delta_vs_market':g.blend_nll.mean()-g.market_nll.mean()})
    venue_diag=pd.DataFrame(venue_diag)

    compact_compare=pd.DataFrame([
        {'model':'COMPACT_GLOBAL_WEIGHT',**compact_sm,'model_weight':global_lam},
        {'model':'COMPACT_VENUE_WEIGHT',**venue_sm,'model_weight':np.nan},
    ])

    res.to_csv(out/'model_comparison.csv',index=False)
    diag.sort_values('cal_delta_add_to_core').to_csv(out/'family_diagnostics.csv',index=False)
    full_mass.to_csv(out/'full_coefficient_mass.csv',index=False)
    venue_weights_df.to_csv(out/'venue_model_weights.csv',index=False)
    venue_diag.to_csv(out/'venue_diagnostics.csv',index=False)
    compact_compare.to_csv(out/'compact_venue_compare.csv',index=False)
    pd.DataFrame([{'selected_families':'|'.join(selected),'selection_rule':'keep if add-to-core improves May-Jun NLL OR removing from full worsens May-Jun NLL','market_weight_tuned_on':'July only','final_test':'August 1-28','series_features_removed':True}]).to_csv(out/'meta.csv',index=False)

    print('\nFAMILY DIAGNOSTICS (negative add delta = helps CORE; positive remove delta = useful in FULL)')
    print(diag.sort_values('cal_delta_add_to_core').to_string(index=False))
    print('\nMODEL COMPARISON')
    print(res.sort_values('aug_blend_nll').to_string(index=False))
    print('\nFULL COEFFICIENT MASS')
    print(full_mass.to_string(index=False))
    print('\nVENUE WEIGHTS')
    print(venue_weights_df.to_string(index=False))
    print('\nCOMPACT GLOBAL VS VENUE-SPECIFIC')
    print(compact_compare.to_string(index=False))


if __name__=='__main__':
    main()
