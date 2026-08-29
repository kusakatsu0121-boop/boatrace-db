#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a
import backtest_ev as be
import model_v7_config as cfg

a.m.PATH_TO_IDX = a.be.PATH_TO_IDX

TARGET_RATES = [0.01, 0.03, 0.05, 0.10, 0.20]
EV_FLOORS = [1.00, 1.02, 1.05, 1.10, 1.15]
MAX_BETS = cfg.MAX_TRIFECTA_TICKETS_PER_RACE


def final_prob(p_struct, q_market):
    return a.blend(p_struct, q_market, cfg.MODEL_BLEND_WEIGHT)


def score_period(probs, races, odds, q, winner):
    rows=[]
    final={}
    for i,r in races.iterrows():
        code=str(r['レースコード'])
        ps=probs.get(code)
        if ps is None or int(winner[i])<0 or not np.isfinite(q[i]).any():
            continue
        pf=final_prob(ps,q[i])
        final[code]=pf
        ev=pf*odds[i]
        good=np.flatnonzero(np.isfinite(ev))
        if not len(good): continue
        top=int(good[np.argmax(ev[good])])
        rows.append({'row_idx':int(i),'レースコード':code,'race_date':r.race_date,'max_ev':float(ev[top]),'top_path_idx':top})
    return pd.DataFrame(rows), final


def qcut(scores, rate):
    if scores.empty:return np.inf
    return float(scores.max_ev.quantile(1-rate,interpolation='higher'))


def bets_for(scores, final, races, odds, winner, cut, floor):
    rows=[]
    for s in scores[scores.max_ev>=cut].itertuples(index=False):
        i=int(s.row_idx); r=races.iloc[i]; code=str(r['レースコード']); p=final.get(code)
        if p is None:continue
        ev=p*odds[i]
        good=np.flatnonzero(np.isfinite(ev)&(ev>=floor))
        if not len(good):continue
        order=good[np.argsort(ev[good])[::-1]][:MAX_BETS]
        for rank,pidx in enumerate(order,start=1):
            pidx=int(pidx); hit=int(pidx==winner[i])
            rows.append({
                'レースコード':code,'race_date':r.race_date,'rank_in_race':rank,'path_idx':pidx,
                'course_trifecta':'-'.join(map(str,be.PATHS[pidx])),
                'snapshot_odds':float(odds[i,pidx]),'final_prob':float(p[pidx]),'model_ev':float(ev[pidx]),
                'hit':hit,'return_per_100':float(r.payout) if hit else 0.0,
            })
    return pd.DataFrame(rows)


def main():
    out=Path('artifacts/blended_ev_v7'); out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e)
    nums,cats=a.columns_for(e,cfg.SELECTED_FAMILIES)
    model,_=a.fit_model(e,nums,cats)
    pp=a.entry_probs(model,e,nums,cats)

    jp,_=a.make_predictions(e,pp,a.JULY_START,a.JULY_END,cfg.PATH_TEMPERATURE,cfg.PATH_GAMMA)
    ap,_=a.make_predictions(e,pp,a.AUG_START,a.AUG_END,cfg.PATH_TEMPERATURE,cfg.PATH_GAMMA)
    jr,jo,jq,jw=a.period_market(base,a.JULY_START,a.JULY_END)
    ar,ao,aq,aw=a.period_market(base,a.AUG_START,a.AUG_END)
    js,jfinal=score_period(jp,jr,jo,jq,jw)
    ass,afinal=score_period(ap,ar,ao,aq,aw)

    rows=[]; rankrows=[]; allbets=[]
    for rate in TARGET_RATES:
        cut=qcut(js,rate)
        for floor in EV_FLOORS:
            b=bets_for(ass,afinal,ar,ao,aw,cut,floor)
            st=be.summarize_bets(b)
            rb=int(b['レースコード'].nunique()) if len(b) else 0
            rows.append({
                'target_rate_pct':rate*100,'july_score_cutoff':cut,'ticket_ev_floor':floor,'max_bets_per_race':MAX_BETS,
                'aug_total_races':len(ar),'aug_scored_races':len(ass),'aug_races_bet':rb,
                'achieved_bet_rate_pct':rb/len(ar)*100 if len(ar) else np.nan,**st,
            })
            if len(b):
                bb=b.copy(); bb['target_rate_pct']=rate*100;bb['ticket_ev_floor']=floor;allbets.append(bb)
                for rk in range(1,MAX_BETS+1):
                    rankrows.append({'target_rate_pct':rate*100,'ticket_ev_floor':floor,'rank':rk,**be.summarize_bets(b[b.rank_in_race.eq(rk)])})
    pd.DataFrame(rows).to_csv(out/'summary.csv',index=False)
    pd.DataFrame(rankrows).to_csv(out/'rank_summary.csv',index=False)
    js.to_csv(out/'july_scores.csv',index=False);ass.to_csv(out/'aug_scores.csv',index=False)
    if allbets: pd.concat(allbets,ignore_index=True).to_csv(out/'bets.csv',index=False)
    pd.DataFrame([{
        'model':cfg.MODEL_NAME,'families':'|'.join(cfg.SELECTED_FAMILIES),'model_weight':cfg.MODEL_BLEND_WEIGHT,
        'market_weight':cfg.MARKET_BLEND_WEIGHT,'july_scored':len(js),'aug_scored':len(ass),
    }]).to_csv(out/'meta.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':
    main()
