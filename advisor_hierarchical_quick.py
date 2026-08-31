#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

import advisor_extension_patterns as m
import advisor_weight_quick as q
from racer_directory import load_many, cards_to_long, results_to_long, build_panel

EPS=1e-12
PATHS=q.PATHS
GRID=[
    (0.0,0.0,0.0),
    (0.5,0.0,0.0),
    (1.0,0.0,0.0),
    (0.0,0.5,0.0),
    (0.0,1.0,0.0),
    (0.0,0.0,0.5),
    (0.0,0.0,1.0),
    (0.5,0.5,0.5),
]


def base_follow_dict(df: pd.DataFrame, kind: str) -> dict:
    col=f'{kind}_base'
    z=df.groupby(['winner_course','target_course'])[col].median().reset_index()
    return {(int(r.winner_course),int(r.target_course)):float(getattr(r,col)) for r in z.itertuples(index=False)}


def normalize(v):
    v=np.clip(np.asarray(v,dtype=float),EPS,None)
    return v/v.sum()


def baseline_probs(row,f2lk,f3lk,b2,b3,chainlk):
    fam=q.family_probs(row,f2lk,f3lk,b2,b3,chainlk)
    z=0.7*np.log(np.clip(fam[:,0],EPS,1.0))+0.3*np.log(np.clip(fam[:,1],EPS,1.0))
    z-=z.max()
    return normalize(np.exp(z))


def hier_probs(row,f2lk,f3lk,b2,b3,chainlk,gamma,beta,alpha):
    base=baseline_probs(row,f2lk,f3lk,b2,b3,chainlk)
    out=np.zeros_like(base)
    try:
        regs={a:int(row[f'reg_c{a}']) for a in range(1,7)}
    except Exception:
        return base
    path_idx={p:i for i,p in enumerate(PATHS)}
    for a in range(1,7):
        first_pairs={}
        first_mass=0.0
        for b in range(1,7):
            if b==a: continue
            ids=[path_idx[(a,b,c)] for c in range(1,7) if c not in (a,b)]
            pm=float(base[ids].sum()); first_mass+=pm
            rec=f2lk.get((regs[a],a,b),{})
            r2=q.safe(rec.get('follow2_lift_ratio'),1.0)
            r2=float(np.clip(r2,0.5,2.0))
            first_pairs[b]=(ids,pm,r2)
        denom=sum(pm*(r2**gamma) for _,pm,r2 in first_pairs.values())
        if denom<=0: continue
        for b,(ids,pm,r2) in first_pairs.items():
            target_pair_mass=first_mass*(pm*(r2**gamma))/denom
            raw=[]
            for c in range(1,7):
                if c in (a,b): continue
                i=path_idx[(a,b,c)]
                rec3=f3lk.get((regs[a],a,c),{})
                r3=q.safe(rec3.get('follow3_lift_ratio'),1.0)
                r3=float(np.clip(r3,0.5,2.0))
                base3=b3.get((a,c),np.nan)
                cp=chainlk.get((a,b,c),np.nan)
                sr=(cp/base3) if np.isfinite(cp) and np.isfinite(base3) and base3>0 else 1.0
                sr=float(np.clip(sr,0.5,2.0))
                raw.append((i,base[i]*(r3**beta)*(sr**alpha)))
            s=sum(v for _,v in raw)
            if s<=0:
                for i in ids: out[i]=base[i]
            else:
                for i,v in raw: out[i]=target_pair_mass*v/s
    return normalize(out)


def metrics(probs,y):
    p=np.clip(probs,EPS,1.0)
    loss=-np.log(p[np.arange(len(y)),y])
    top1=(p.argmax(axis=1)==y).mean()
    t5=np.argpartition(p,-5,axis=1)[:,-5:]
    top5=np.mean([yy in t5[i] for i,yy in enumerate(y)])
    return {'logloss':float(loss.mean()),'top1':float(top1),'top5':float(top5)},loss


def build_data():
    src=Path('source/data')
    cards=load_many(str(src/'programs/race_cards/*/*/*.csv'))
    results=load_many(str(src/'results/realtime/*/*/*.csv'))
    cl=cards_to_long(cards); rl=results_to_long(results)
    panel=build_panel(cl,rl,pd.DataFrame()).dropna(subset=['race_date','regno','actual_course','finish']).copy()
    train=panel[panel.race_date<=m.TRAIN_END].copy()
    roles=m.build_role_metrics(train); f2,f3,chain=m.build_follow_metrics(train)
    f2lk,f3lk=m.follow_lookup(f2),m.follow_lookup(f3)
    b2,b3=base_follow_dict(f2,'follow2'),base_follow_dict(f3,'follow3')
    chainlk=m.path_chain_lookup(chain)
    base=q.build_wide(cl,rl); base=m.attach_roles(base,roles)
    idx=q.load_index(src); keep=['レースコード']+[c for c in idx.columns if '枠_' in c]
    base=base.merge(idx[keep],on='レースコード',how='inner')
    base=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.OOS_END)].copy()
    return base,f2lk,f3lk,b2,b3,chainlk


def evaluate(df,f2lk,f3lk,b2,b3,chainlk,params):
    pidx={p:i for i,p in enumerate(PATHS)}
    ys=[]; rows=[]
    for _,r in df.iterrows():
        wp=tuple(r['winner_path'])
        if wp not in pidx: continue
        ys.append(pidx[wp]); rows.append(r)
    y=np.array(ys,dtype=int)
    allp=[]
    for gamma,beta,alpha in params:
        probs=np.stack([hier_probs(r,f2lk,f3lk,b2,b3,chainlk,gamma,beta,alpha) for r in rows])
        s,l=metrics(probs,y)
        allp.append((gamma,beta,alpha,s,l))
    return allp


def main():
    out=Path('artifacts/advisor_hierarchical_quick'); out.mkdir(parents=True,exist_ok=True)
    base,f2lk,f3lk,b2,b3,chainlk=build_data()
    jul=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.CAL_END)].copy()
    aug=base[(base.race_date>=m.OOS_START)&(base.race_date<=m.OOS_END)].copy()
    cal=q.stratified_sample(jul,q.CAL_N,q.SEED)
    oos=q.stratified_sample(aug,q.OOS_N,q.SEED+1)
    rem_j=jul[~jul['レースコード'].isin(set(cal['レースコード']))]
    rem_a=aug[~aug['レースコード'].isin(set(oos['レースコード']))]
    calres=evaluate(cal,f2lk,f3lk,b2,b3,chainlk,GRID)
    rows=[]
    for g,b,a,s,_ in calres:
        rows.append({'follow2_gamma':g,'follow3_beta':b,'struct_chain_alpha':a,**{f'cal_{k}':v for k,v in s.items()}})
    d=pd.DataFrame(rows).sort_values(['cal_logloss','cal_top5'],ascending=[True,False]).reset_index(drop=True)
    d.to_csv(out/'hier_grid_cal.csv',index=False)
    top_params=[tuple(x) for x in d[['follow2_gamma','follow3_beta','struct_chain_alpha']].to_numpy()]
    oosres=evaluate(oos,f2lk,f3lk,b2,b3,chainlk,top_params)
    top=[]
    for (g,b,a,s,_),(_,r) in zip(oosres,d.iterrows()):
        top.append({**r.to_dict(),**{f'oos_{k}':v for k,v in s.items()}})
    topdf=pd.DataFrame(top); topdf.to_csv(out/'hier_candidates_oos.csv',index=False)
    best=tuple(d.iloc[0][['follow2_gamma','follow3_beta','struct_chain_alpha']].to_numpy(dtype=float))
    checks=[]
    for label,dfx in [('July_remainder',rem_j),('August_remainder',rem_a),('Combined_remainder',pd.concat([rem_j,rem_a]))]:
        rr=evaluate(dfx,f2lk,f3lk,b2,b3,chainlk,[best,(0.0,0.0,0.0)])
        for g,b,a,s,_ in rr:
            checks.append({'split':label,'follow2_gamma':g,'follow3_beta':b,'struct_chain_alpha':a,**s})
    ck=pd.DataFrame(checks); ck.to_csv(out/'hier_best_remainder.csv',index=False)
    print(f'HIER QUICK 8-CANDIDATE: cal={len(cal):,} oos={len(oos):,} untouched={len(rem_j)+len(rem_a):,}')
    print('\nJULY CANDIDATES')
    print(d.to_string(index=False))
    print('\nAUG OOS')
    print(topdf.to_string(index=False))
    print('\nUNTOUCHED REMAINDER: JULY-BEST vs BASELINE 70/30')
    print(ck.to_string(index=False))

if __name__=='__main__':
    main()
