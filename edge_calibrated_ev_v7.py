#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a
import backtest_ev as be
import model_v7_config as cfg

a.m.PATH_TO_IDX = a.be.PATH_TO_IDX

ALPHAS = np.round(np.arange(0.05, 0.5001, 0.05), 2)
CAPS = [0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 3.00, 99.0]
TARGET_RATES = [0.01, 0.03, 0.05, 0.10, 0.20]
EV_FLOORS = [1.00, 1.02, 1.05, 1.10, 1.15, 1.20]
MAX_BETS = cfg.MAX_TRIFECTA_TICKETS_PER_RACE


def norm(x):
    y=np.asarray(x,float)
    y=np.where(np.isfinite(y)&(y>0),y,1e-12)
    return y/y.sum()


def edge_calibrate(p, q, alpha, cap):
    pp=norm(p); qq=norm(q)
    d=np.log(np.clip(pp/qq,1e-12,1e12))
    if cap < 90:
        d=np.clip(d,-cap,cap)
    z=np.log(qq)+float(alpha)*d
    z-=z.max(); out=np.exp(z); return out/out.sum()


def tune(jp, jr, jq, jw):
    rows=[];best=None
    for cap in CAPS:
        for alpha in ALPHAS:
            losses=[]
            for i,r in jr.iterrows():
                p=jp.get(str(r['レースコード'])); wi=int(jw[i])
                if p is None or wi<0 or not np.isfinite(jq[i]).any():continue
                f=edge_calibrate(p,jq[i],alpha,cap)
                losses.append(-math.log(max(float(f[wi]),1e-12)))
            if not losses:continue
            row={'alpha':float(alpha),'log_ratio_cap':float(cap),'july_nll':float(np.mean(losses)),'races':len(losses)}
            rows.append(row)
            if best is None or row['july_nll']<best['july_nll']:
                best=row.copy()
    return best,pd.DataFrame(rows).sort_values('july_nll')


def make_final(probs,races,q,winner,alpha,cap):
    out={}; rows=[]
    for i,r in races.iterrows():
        code=str(r['レースコード']); p=probs.get(code); wi=int(winner[i])
        if p is None or wi<0 or not np.isfinite(q[i]).any():continue
        f=edge_calibrate(p,q[i],alpha,cap);out[code]=f
        rows.append({'レースコード':code,'race_date':r.race_date,'winner_nll':-math.log(max(float(f[wi]),1e-12)),'top_hit':int(np.argmax(f)==wi)})
    return out,pd.DataFrame(rows)


def score(final,races,odds,winner):
    rows=[]
    for i,r in races.iterrows():
        code=str(r['レースコード']); p=final.get(code)
        if p is None or int(winner[i])<0:continue
        ev=p*odds[i];good=np.flatnonzero(np.isfinite(ev))
        if not len(good):continue
        top=int(good[np.argmax(ev[good])])
        rows.append({'row_idx':int(i),'レースコード':code,'race_date':r.race_date,'max_ev':float(ev[top])})
    return pd.DataFrame(rows)


def cutoff(scores,rate):
    return float(scores.max_ev.quantile(1-rate,interpolation='higher')) if len(scores) else np.inf


def bet(final,scores,races,odds,winner,cut,floor):
    rows=[]
    for s in scores[scores.max_ev>=cut].itertuples(index=False):
        i=int(s.row_idx);r=races.iloc[i];code=str(r['レースコード']);p=final.get(code)
        if p is None:continue
        ev=p*odds[i];good=np.flatnonzero(np.isfinite(ev)&(ev>=floor))
        if not len(good):continue
        order=good[np.argsort(ev[good])[::-1]][:MAX_BETS]
        for rank,pidx in enumerate(order,start=1):
            pidx=int(pidx);hit=int(pidx==winner[i])
            rows.append({'レースコード':code,'race_date':r.race_date,'rank_in_race':rank,'path_idx':pidx,
                         'course_trifecta':'-'.join(map(str,be.PATHS[pidx])),'snapshot_odds':float(odds[i,pidx]),
                         'final_prob':float(p[pidx]),'model_ev':float(ev[pidx]),'hit':hit,
                         'return_per_100':float(r.payout) if hit else 0.0})
    return pd.DataFrame(rows)


def main():
    out=Path('artifacts/edge_calibrated_ev_v7');out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True);a.v2._build_conditional_ratios(e);e=a._add_interactions(e)
    nums,cats=a.columns_for(e,cfg.SELECTED_FAMILIES);model,_=a.fit_model(e,nums,cats);pp=a.entry_probs(model,e,nums,cats)
    jp,_=a.make_predictions(e,pp,a.JULY_START,a.JULY_END,cfg.PATH_TEMPERATURE,cfg.PATH_GAMMA)
    ap,_=a.make_predictions(e,pp,a.AUG_START,a.AUG_END,cfg.PATH_TEMPERATURE,cfg.PATH_GAMMA)
    jr,jo,jq,jw=a.period_market(base,a.JULY_START,a.JULY_END);ar,ao,aq,aw=a.period_market(base,a.AUG_START,a.AUG_END)
    best,grid=tune(jp,jr,jq,jw);grid.to_csv(out/'july_edge_calibration_grid.csv',index=False)
    jf,jqual=make_final(jp,jr,jq,jw,best['alpha'],best['log_ratio_cap']);af,aqual=make_final(ap,ar,aq,aw,best['alpha'],best['log_ratio_cap'])
    js=score(jf,jr,jo,jw);ass=score(af,ar,ao,aw)
    rows=[];rank=[];allbets=[]
    for rate in TARGET_RATES:
        cut=cutoff(js,rate)
        for floor in EV_FLOORS:
            b=bet(af,ass,ar,ao,aw,cut,floor);st=be.summarize_bets(b);rb=int(b['レースコード'].nunique()) if len(b) else 0
            rows.append({'target_rate_pct':rate*100,'july_score_cutoff':cut,'ticket_ev_floor':floor,'aug_total_races':len(ar),'aug_scored_races':len(ass),'aug_races_bet':rb,'achieved_bet_rate_pct':rb/len(ar)*100 if len(ar) else np.nan,**st})
            if len(b):
                bb=b.copy();bb['target_rate_pct']=rate*100;bb['ticket_ev_floor']=floor;allbets.append(bb)
                for rk in range(1,MAX_BETS+1):rank.append({'target_rate_pct':rate*100,'ticket_ev_floor':floor,'rank':rk,**be.summarize_bets(b[b.rank_in_race.eq(rk)])})
    pd.DataFrame(rows).to_csv(out/'summary.csv',index=False);pd.DataFrame(rank).to_csv(out/'rank_summary.csv',index=False)
    js.to_csv(out/'july_scores.csv',index=False);ass.to_csv(out/'aug_scores.csv',index=False)
    if allbets:pd.concat(allbets,ignore_index=True).to_csv(out/'bets.csv',index=False)
    meta={'model':cfg.MODEL_NAME,**best,'aug_nll':float(aqual.winner_nll.mean()),'aug_top':float(aqual.top_hit.mean()),'july_scored':len(js),'aug_scored':len(ass)}
    pd.DataFrame([meta]).to_csv(out/'meta.csv',index=False)
    print(pd.DataFrame([meta]).to_string(index=False));print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':main()
