#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a
import run_core_feature_ablation_v7_fast as fast
import backtest_ev as be
from compact_path_worker_v7 import CANDIDATES

a.m.PATH_TO_IDX = a.be.PATH_TO_IDX
a.tune_path = fast.fast_tune_path

TARGET_RATES = [0.01, 0.03, 0.05, 0.10]
EV_FLOORS = [1.00, 1.05, 1.10, 1.15]
MAX_BETS = 4


def scored_table(probs: dict[str, np.ndarray], races: pd.DataFrame, odds: np.ndarray, winner: np.ndarray):
    rows=[]
    for i,r in races.iterrows():
        code=str(r['レースコード'])
        p=probs.get(code)
        if p is None or int(winner[i]) < 0:
            continue
        ev=p*odds[i]
        good=np.flatnonzero(np.isfinite(ev))
        if len(good)==0:
            continue
        order=good[np.argsort(ev[good])[::-1]]
        rows.append({'row_idx':int(i),'レースコード':code,'race_date':r.race_date,'max_structural_ev':float(ev[order[0]])})
    return pd.DataFrame(rows)


def cutoff(scores: pd.DataFrame, rate: float):
    if scores.empty: return np.inf
    return float(scores.max_structural_ev.quantile(1-rate, interpolation='higher'))


def make_bets(probs, races, odds, winner, scores, score_cut, ev_floor):
    rows=[]
    selected=scores[scores.max_structural_ev>=score_cut]
    for s in selected.itertuples(index=False):
        i=int(s.row_idx); r=races.iloc[i]; code=str(r['レースコード'])
        p=probs.get(code)
        if p is None: continue
        ev=p*odds[i]
        eligible=np.flatnonzero(np.isfinite(ev)&(ev>=ev_floor))
        if len(eligible)==0: continue
        order=eligible[np.argsort(ev[eligible])[::-1]][:MAX_BETS]
        for rank,pidx in enumerate(order,start=1):
            pidx=int(pidx); hit=int(pidx==winner[i])
            rows.append({
                'レースコード':code,'race_date':r.race_date,'rank_in_race':rank,
                'course_trifecta':'-'.join(map(str,be.PATHS[pidx])),
                'snapshot_odds':float(odds[i,pidx]),'model_prob':float(p[pidx]),
                'model_ev':float(ev[pidx]),'hit':hit,
                'return_per_100':float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def main():
    name=os.environ['CANDIDATE']
    fams=CANDIDATES[name]
    out=Path('artifacts/structural_ev_v7'); out.mkdir(parents=True,exist_ok=True)

    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e)
    nums,cats=a.columns_for(e,fams)
    model,_=a.fit_model(e,nums,cats)
    pp=a.entry_probs(model,e,nums,cats)
    best,_=a.tune_path(e,pp)

    jul_probs,_=a.make_predictions(e,pp,a.JULY_START,a.JULY_END,best['temperature'],best['gamma'])
    aug_probs,_=a.make_predictions(e,pp,a.AUG_START,a.AUG_END,best['temperature'],best['gamma'])
    jr,jo,jq,jw=a.period_market(base,a.JULY_START,a.JULY_END)
    ar,ao,aq,aw=a.period_market(base,a.AUG_START,a.AUG_END)
    js=scored_table(jul_probs,jr,jo,jw)
    ass=scored_table(aug_probs,ar,ao,aw)

    rows=[]; rankrows=[]; allbets=[]
    for rate in TARGET_RATES:
        sc=cutoff(js,rate)
        for ef in EV_FLOORS:
            bets=make_bets(aug_probs,ar,ao,aw,ass,sc,ef)
            st=be.summarize_bets(bets)
            row={
                'candidate':name,'target_rate_pct':rate*100,'july_score_cutoff':sc,
                'ticket_ev_floor':ef,'max_bets_per_race':MAX_BETS,
                'aug_total_races':len(ar),'aug_scored_races':len(ass),
                'aug_races_bet':int(bets['レースコード'].nunique()) if len(bets) else 0,
                'achieved_bet_rate_pct':(bets['レースコード'].nunique()/len(ar)*100) if len(bets) and len(ar) else 0.0,
                **st,
            }
            rows.append(row)
            if len(bets):
                b=bets.copy(); b['candidate']=name; b['target_rate_pct']=rate*100; b['ticket_ev_floor']=ef; allbets.append(b)
                for rk in range(1,MAX_BETS+1):
                    rs=be.summarize_bets(bets[bets.rank_in_race.eq(rk)])
                    rankrows.append({'candidate':name,'target_rate_pct':rate*100,'ticket_ev_floor':ef,'rank':rk,**rs})
    pd.DataFrame(rows).to_csv(out/f'{name}_summary.csv',index=False)
    pd.DataFrame(rankrows).to_csv(out/f'{name}_rank.csv',index=False)
    if allbets: pd.concat(allbets,ignore_index=True).to_csv(out/f'{name}_bets.csv',index=False)
    meta=pd.DataFrame([{'candidate':name,'families':'|'.join(fams),'cal_nll':best['cal_nll'],'gamma':best['gamma'],'temperature':best['temperature'],'july_scored':len(js),'aug_scored':len(ass)}])
    meta.to_csv(out/f'{name}_meta.csv',index=False)
    print(meta.to_string(index=False))
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':
    main()
