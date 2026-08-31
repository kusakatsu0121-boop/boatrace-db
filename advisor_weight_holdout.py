#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

import advisor_extension_patterns as m
import advisor_weight_quick as q
from racer_directory import load_many, cards_to_long, results_to_long, build_panel

CANDIDATES = {
    'A_70_30_0_0': np.array([0.7,0.3,0.0,0.0]),
    'B_80_20_0_0': np.array([0.8,0.2,0.0,0.0]),
    'C_60_30_0_10': np.array([0.6,0.3,0.0,0.1]),
    'D_70_20_0_10': np.array([0.7,0.2,0.0,0.1]),
    'E_60_40_0_0': np.array([0.6,0.4,0.0,0.0]),
    'CTRL_ability_only': np.array([1.0,0.0,0.0,0.0]),
}
EPS=1e-12


def base_follow_dict(df: pd.DataFrame, kind: str) -> dict:
    base_col=f'{kind}_base'
    z=df.groupby(['winner_course','target_course'])[base_col].median().reset_index()
    return {(int(r.winner_course),int(r.target_course)):float(getattr(r,base_col)) for r in z.itertuples(index=False)}


def make_arrays(df, f2lk, f3lk, b2, b3, chainlk):
    path_to_idx={p:i for i,p in enumerate(q.PATHS)}
    probs=[]; y=[]; codes=[]; v1=[]
    for _,row in df.iterrows():
        wp=tuple(row['winner_path'])
        if wp not in path_to_idx: continue
        probs.append(q.family_probs(row,f2lk,f3lk,b2,b3,chainlk))
        y.append(path_to_idx[wp]); codes.append(row['レースコード'])
        scores=np.array([q.safe(row.get(f'{b}枠_強さpt'),50.0) for b in range(1,7)])
        v1.append(q.pl_path_probs(scores))
    return np.log(np.clip(np.stack(probs),EPS,1.0)), np.array(y,dtype=int), codes, np.log(np.clip(np.stack(v1),EPS,1.0))


def per_race_loss(logp,y,w=None):
    if w is None:
        lp=logp
    else:
        z=np.tensordot(logp,w,axes=([2],[0]))
        mx=z.max(axis=1,keepdims=True)
        lp=z-(mx+np.log(np.exp(z-mx).sum(axis=1,keepdims=True)))
    return -lp[np.arange(len(y)),y], lp


def summarize(name, logp, y, w=None):
    loss,lp=per_race_loss(logp,y,w)
    top1=(lp.argmax(axis=1)==y).mean()
    top5idx=np.argpartition(lp,-5,axis=1)[:,-5:]
    top5=np.mean([yy in top5idx[i] for i,yy in enumerate(y)])
    return {'candidate':name,'n':len(y),'logloss':float(loss.mean()),'top1':float(top1),'top5':float(top5)}, loss


def ci_diff(diff):
    n=len(diff); mu=float(np.mean(diff)); se=float(np.std(diff,ddof=1)/np.sqrt(n)) if n>1 else np.nan
    return mu, mu-1.96*se, mu+1.96*se


def main():
    src=Path('source/data'); out=Path('artifacts/advisor_weight_holdout'); out.mkdir(parents=True,exist_ok=True)
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
    idx=q.load_index(src)
    keep=['レースコード']+[c for c in idx.columns if '枠_' in c]
    base=base.merge(idx[keep],on='レースコード',how='inner')
    base=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.OOS_END)].copy()
    jul=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.CAL_END)].copy()
    aug=base[(base.race_date>=m.OOS_START)&(base.race_date<=m.OOS_END)].copy()

    used_j=q.stratified_sample(jul,q.CAL_N,q.SEED)
    used_a=q.stratified_sample(aug,q.OOS_N,q.SEED+1)
    rem_j=jul[~jul['レースコード'].isin(set(used_j['レースコード']))].copy()
    rem_a=aug[~aug['レースコード'].isin(set(used_a['レースコード']))].copy()
    print(f'UNTOUCHED REMAINDER: July={len(rem_j):,} August={len(rem_a):,} total={len(rem_j)+len(rem_a):,}')

    rows=[]; diffs=[]
    for label,df in [('July_remainder',rem_j),('August_remainder',rem_a),('Combined_remainder',pd.concat([rem_j,rem_a]))]:
        logp,y,_,v1log=make_arrays(df,f2lk,f3lk,b2,b3,chainlk)
        losses={}
        for name,w in CANDIDATES.items():
            s,l=summarize(name,logp,y,w); s['split']=label; rows.append(s); losses[name]=l
        s,l=summarize('CTRL_v1_strength',v1log,y,None); s['split']=label; rows.append(s); losses['CTRL_v1_strength']=l
        ref=losses['A_70_30_0_0']
        for name,l in losses.items():
            if name=='A_70_30_0_0': continue
            # positive value means candidate has higher (worse) loss than A
            mu,lo,hi=ci_diff(l-ref)
            diffs.append({'split':label,'candidate_vs_A':name,'mean_logloss_diff':mu,'ci95_low':lo,'ci95_high':hi})

    res=pd.DataFrame(rows)
    res.to_csv(out/'candidate_holdout_metrics.csv',index=False)
    pd.DataFrame(diffs).to_csv(out/'paired_logloss_diff_vs_A.csv',index=False)
    print('\nCANDIDATE METRICS')
    print(res.to_string(index=False))
    print('\nPAIRED LOGLOSS DIFFERENCE vs A (positive = worse than A)')
    print(pd.DataFrame(diffs).to_string(index=False))

if __name__=='__main__':
    main()
