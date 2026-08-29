#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a
import backtest_ev as be
import model_v7_config as cfg
import blended_ev_v7 as bv7

a.m.PATH_TO_IDX = a.be.PATH_TO_IDX
EV_THRESHOLDS=[1.20,1.30,1.40,1.50,1.75,2.00]


def make_all_bets(final, races, odds, winner, threshold):
    rows=[]
    for i,r in races.iterrows():
        code=str(r['レースコード']); p=final.get(code)
        if p is None or int(winner[i])<0: continue
        ev=p*odds[i]
        good=np.flatnonzero(np.isfinite(ev)&(ev>=threshold))
        for pidx in good:
            pidx=int(pidx); hit=int(pidx==winner[i])
            rows.append({
                'レースコード':code,'race_date':r.race_date,'path_idx':pidx,
                'course_trifecta':'-'.join(map(str,be.PATHS[pidx])),
                'snapshot_odds':float(odds[i,pidx]),'final_prob':float(p[pidx]),
                'model_ev':float(ev[pidx]),'hit':hit,
                'return_per_100':float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def main():
    out=Path('artifacts/all_ev150_v7'); out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e)
    nums,cats=a.columns_for(e,cfg.SELECTED_FAMILIES)
    model,_=a.fit_model(e,nums,cats)
    pp=a.entry_probs(model,e,nums,cats)
    ap,_=a.make_predictions(e,pp,a.AUG_START,a.AUG_END,cfg.PATH_TEMPERATURE,cfg.PATH_GAMMA)
    ar,ao,aq,aw=a.period_market(base,a.AUG_START,a.AUG_END)
    _,afinal=bv7.score_period(ap,ar,ao,aq,aw)
    rows=[]; allb=[]
    for th in EV_THRESHOLDS:
        b=make_all_bets(afinal,ar,ao,aw,th)
        st=be.summarize_bets(b)
        rb=int(b['レースコード'].nunique()) if len(b) else 0
        rows.append({'ev_threshold':th,'aug_total_races':len(ar),'races_bet':rb,
                     'bet_rate_pct':rb/len(ar)*100 if len(ar) else np.nan,
                     'avg_tickets_per_bet_race':len(b)/rb if rb else np.nan,**st})
        if len(b):
            bb=b.copy();bb['ev_threshold']=th;allb.append(bb)
    pd.DataFrame(rows).to_csv(out/'summary.csv',index=False)
    if allb: pd.concat(allb,ignore_index=True).to_csv(out/'bets.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':
    main()
