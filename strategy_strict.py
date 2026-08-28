#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from strategy_features import (
    load_many, cards_long, results_long, build_course_roles, race_matrix,
    make_baseline_map, event_prob,
)

HOLDOUT_DAYS = 120
PAIR_MIN_N = 80
HALF_MIN_N = 25
PAIRS = [(1,2),(1,3),(2,3),(2,4),(3,4),(3,5),(4,5)]
EVENTS = ['1','2','3','top2','top3']


def normalize_method(s: pd.Series) -> pd.Series:
    return s.fillna('').astype(str).str.replace(r'[\s　]+', '', regex=True)


def observed(g: pd.DataFrame, ev: str) -> pd.Series:
    if ev in ('1','2','3'):
        return (g.finish == int(ev)).astype(float)
    return (g.finish <= (2 if ev == 'top2' else 3)).astype(float)


def expected_all_six(panel: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    """Race-specific baseline using every boat's historical same-course probability.

    Exact-place probabilities are normalized to sum to 1 per race.
    top2/top3 probabilities are normalized to sum to 2/3 per race.
    This removes much of the 'weak opponents happened to be there' effect before
    measuring type interactions.
    """
    base = make_baseline_map(roles)
    x = panel.copy()
    for ev in EVENTS:
        raw = pd.Series([
            event_prob(base, r, c, int(ev) if ev in ('1','2','3') else ev)
            for r,c in zip(x.regno, x.actual_course)
        ], index=x.index, dtype=float)
        fallback = raw.groupby(x.actual_course).transform('mean')
        raw = raw.fillna(fallback).fillna(raw.mean())
        target_sum = 1.0 if ev in ('1','2','3') else (2.0 if ev == 'top2' else 3.0)
        den = raw.groupby(x['レースコード']).transform('sum').replace(0, np.nan)
        x[f'exp_{ev}'] = (raw * target_sum / den).clip(0.001, 0.999)
        x[f'obs_{ev}'] = observed(x, ev)
        x[f'resid_{ev}'] = x[f'obs_{ev}'] - x[f'exp_{ev}']
    return x


def pair_interactions(x: pd.DataFrame, label_col: str, half_cut: pd.Timestamp) -> pd.DataFrame:
    z0=x.copy()
    z0['half']=np.where(z0.race_date < half_cut, 'H1', 'H2')
    pieces=[]
    for a,b in PAIRS:
        qa=z0[z0.actual_course.eq(a)][['レースコード',label_col,'outer_special']].rename(columns={label_col:'A','outer_special':'sa'})
        qb=z0[z0.actual_course.eq(b)][['レースコード',label_col,'outer_special']].rename(columns={label_col:'B','outer_special':'sb'})
        pair=qa.merge(qb,on='レースコード')
        pair=pair[(pair.A.notna())&(pair.B.notna())&(pair.A!='SAMPLE_LOW')&(pair.B!='SAMPLE_LOW')]
        if a>=5: pair=pair[pair.sa.eq(1)]
        if b>=5: pair=pair[pair.sb.eq(1)]
        if pair.empty: continue
        z=z0.merge(pair[['レースコード','A','B']],on='レースコード')
        for tc in range(1,7):
            zz=z[z.actual_course.eq(tc)].copy()
            if zz.empty: continue
            for ev in EVENTS:
                col=f'resid_{ev}'
                overall=zz[col].mean()
                ma=zz.groupby('A',as_index=False)[col].mean().rename(columns={col:'ma'})
                mb=zz.groupby('B',as_index=False)[col].mean().rename(columns={col:'mb'})
                pg=zz.groupby(['A','B'],as_index=False).agg(pair_mean=(col,'mean'),n=(col,'size'),sd=(col,'std')).merge(ma,on='A').merge(mb,on='B')
                pg['interaction_lift_pt']=pg.pair_mean-pg.ma-pg.mb+overall
                pg['t_approx']=pg.interaction_lift_pt/(pg.sd/np.sqrt(pg.n))
                for h in ('H1','H2'):
                    zh=zz[zz.half.eq(h)]
                    if zh.empty:
                        pg[f'{h}_lift']=np.nan; pg[f'{h}_n']=0; continue
                    oh=zh[col].mean()
                    mah=zh.groupby('A',as_index=False)[col].mean().rename(columns={col:'mah'})
                    mbh=zh.groupby('B',as_index=False)[col].mean().rename(columns={col:'mbh'})
                    ph=zh.groupby(['A','B'],as_index=False).agg(hmean=(col,'mean'),hn=(col,'size')).merge(mah,on='A').merge(mbh,on='B')
                    ph[f'{h}_lift']=ph.hmean-ph.mah-ph.mbh+oh
                    ph=ph[['A','B',f'{h}_lift','hn']].rename(columns={'hn':f'{h}_n'})
                    pg=pg.merge(ph,on=['A','B'],how='left')
                pg['same_sign_halves']=(
                    pg.H1_lift.notna() & pg.H2_lift.notna() &
                    (pg.H1_n>=HALF_MIN_N) & (pg.H2_n>=HALF_MIN_N) &
                    (np.sign(pg.H1_lift)==np.sign(pg.H2_lift)) &
                    (np.sign(pg.H1_lift)==np.sign(pg.interaction_lift_pt))
                ).astype(int)
                pg=pg[pg.n>=PAIR_MIN_N]
                if len(pg):
                    pg['label_kind']=label_col; pg['course_a']=a; pg['course_b']=b; pg['target_course']=tc; pg['event']=ev
                    pg=pg.rename(columns={'A':'type_a','B':'type_b'})
                    pieces.append(pg[['label_kind','course_a','type_a','course_b','type_b','target_course','event','n','interaction_lift_pt','t_approx','H1_lift','H1_n','H2_lift','H2_n','same_sign_halves']])
    return pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame()


def race_paths(x: pd.DataFrame) -> pd.DataFrame:
    fin=x.pivot_table(index='レースコード',columns='actual_course',values='finish',aggfunc='first').reindex(columns=range(1,7))
    arr=fin.to_numpy(float)
    order=np.argsort(np.where(np.isnan(arr),99,arr),axis=1)[:,:3]+1
    out=pd.DataFrame({'レースコード':fin.index,'course_trifecta':[f'{a}-{b}-{c}' for a,b,c in order]})
    date=x.groupby('レースコード').race_date.first().rename('race_date')
    out=out.merge(date,on='レースコード',how='left')
    for c in range(1,6):
        q=x[x.actual_course.eq(c)][['レースコード','style_label']].rename(columns={'style_label':f'style{c}'})
        out=out.merge(q,on='レースコード',how='left')
    return out


def path_interactions(x: pd.DataFrame, half_cut: pd.Timestamp) -> pd.DataFrame:
    r=race_paths(x); r['half']=np.where(r.race_date<half_cut,'H1','H2')
    common=r.course_trifecta.value_counts(); paths=common[common>=120].index.tolist(); rows=[]
    for a,b in [(1,2),(1,3),(2,3),(2,4),(3,4)]:
        z=r[['half',f'style{a}',f'style{b}','course_trifecta']].rename(columns={f'style{a}':'A',f'style{b}':'B'}).copy()
        z=z[(z.A.notna())&(z.B.notna())&(z.A!='SAMPLE_LOW')&(z.B!='SAMPLE_LOW')]
        for path in paths:
            z['y']=(z.course_trifecta==path).astype(float)
            overall=z.y.mean(); ma=z.groupby('A').y.mean(); mb=z.groupby('B').y.mean()
            pg=z.groupby(['A','B']).y.agg(['mean','size','std']).reset_index()
            for rr in pg.itertuples(index=False):
                if rr.size<100: continue
                inter=float(rr.mean-ma.get(rr.A,0)-mb.get(rr.B,0)+overall); halfs={}
                for h in ('H1','H2'):
                    zh=z[z.half.eq(h)]; gh=zh[(zh.A==rr.A)&(zh.B==rr.B)]
                    if len(gh)<HALF_MIN_N: halfs[h]=(np.nan,len(gh)); continue
                    ih=float(gh.y.mean()-zh.groupby('A').y.mean().get(rr.A,0)-zh.groupby('B').y.mean().get(rr.B,0)+zh.y.mean())
                    halfs[h]=(ih,len(gh))
                se=float(rr.std/math.sqrt(rr.size)) if pd.notna(rr.std) and rr.std>0 else np.nan
                same=int(pd.notna(halfs['H1'][0]) and pd.notna(halfs['H2'][0]) and np.sign(inter)==np.sign(halfs['H1'][0])==np.sign(halfs['H2'][0]))
                rows.append({'course_a':a,'type_a':rr.A,'course_b':b,'type_b':rr.B,'course_trifecta':path,'n':int(rr.size),'interaction_lift_pt':inter,
                             't_approx':inter/se if se else np.nan,'H1_lift':halfs['H1'][0],'H1_n':halfs['H1'][1],'H2_lift':halfs['H2'][0],'H2_n':halfs['H2'][1],'same_sign_halves':same})
    return pd.DataFrame(rows)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',default='source/data')
    ap.add_argument('--out',default='artifacts/strategy_strict')
    ap.add_argument('--holdout-days',type=int,default=HOLDOUT_DAYS)
    args=ap.parse_args()
    src=Path(args.source); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    cards=load_many(str(src/'programs/race_cards/*/*/*.csv'))
    results=load_many(str(src/'results/realtime/*/*/*.csv'))
    if cards.empty or results.empty: raise SystemExit('race_cards/results not found')
    cl=cards_long(cards); rl=results_long(results)
    rl['決まり手']=normalize_method(rl['決まり手'])
    panel=rl.merge(cl[['レースコード','boat','regno']].drop_duplicates(['レースコード','boat']),on=['レースコード','boat'],how='left').dropna(subset=['regno']).copy()
    panel['regno']=panel.regno.astype('Int64'); panel['finish']=pd.to_numeric(panel.finish,errors='coerce'); panel['race_date']=pd.to_datetime(panel['レース日'],errors='coerce')
    panel=panel.dropna(subset=['race_date','finish','actual_course','regno'])
    end=panel.race_date.max(); cutoff=end-pd.Timedelta(days=args.holdout_days); half=cutoff+pd.Timedelta(days=args.holdout_days/2)
    train=panel[panel.race_date<cutoff].copy(); test=panel[panel.race_date>=cutoff].copy()
    roles=build_course_roles(train); x=race_matrix(test,roles); x['race_date']=pd.to_datetime(x['レース日'],errors='coerce'); x=expected_all_six(x,roles)
    style=pair_interactions(x,'style_label',half); finish=pair_interactions(x,'finish_role_label',half); paths=path_interactions(x,half)
    top=pd.concat([style.assign(signal='STYLE_PAIR'),finish.assign(signal='FINISH_PAIR')],ignore_index=True,sort=False)
    if not top.empty:
        top=top[(top.same_sign_halves==1)&(top.n>=100)&(top.interaction_lift_pt.abs()>=.025)&(top.t_approx.abs()>=1.8)].copy()
        top['score']=top.t_approx.abs()*np.sqrt(top.n); top=top.sort_values('score',ascending=False)
    path_top=paths[(paths.same_sign_halves==1)&(paths.n>=140)&(paths.interaction_lift_pt.abs()>=.018)&(paths.t_approx.abs()>=1.8)].copy() if not paths.empty else paths
    roles.to_csv(out/'racer_course_roles_train.csv',index=False); style.to_csv(out/'style_pair_interactions.csv',index=False); finish.to_csv(out/'finish_pair_interactions.csv',index=False); paths.to_csv(out/'path_interactions.csv',index=False); top.to_csv(out/'top_strategy_signals.csv',index=False); path_top.to_csv(out/'top_path_signals.csv',index=False)
    meta=pd.DataFrame([{'data_end':str(end.date()),'cutoff':str(cutoff.date()),'train_races':train['レースコード'].nunique(),'holdout_races':test['レースコード'].nunique(),'role_rows':len(roles),'style_rows':len(style),'finish_rows':len(finish),'stable_top_signals':len(top),'stable_path_signals':len(path_top)}]); meta.to_csv(out/'run_meta.csv',index=False)
    print(meta.to_string(index=False)); print('\nTOP'); print(top.head(25).to_string(index=False) if len(top) else 'none'); print('\nPATHS'); print(path_top.head(25).to_string(index=False) if len(path_top) else 'none')


if __name__=='__main__': main()
