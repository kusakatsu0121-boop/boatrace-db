#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import itertools
import numpy as np
import pandas as pd

import advisor_extension_patterns as m
import advisor_weight_quick as q
import advisor_hierarchical_quick as h
import advisor_ev_quick as ev
import advisor_market_calibration_quick as mc

RATIO_THRESHOLDS=[1.10,1.25,1.50,2.00]
ODDS_CAPS=[20.0,50.0,100.0,np.inf]
MIN_JULY_BETS=100


def make_ticket_cache(cache):
    rows=[]
    for x in cache:
        model=x['model']; market=x['market']; odds=x['odds']; y=x['y']
        ratio=model/np.clip(market,1e-12,None)
        for i,path in enumerate(m.PATHS):
            od=odds[i]
            if not np.isfinite(od) or od<=0: continue
            rows.append({'レースコード':x['code'],'race_date':x['race_date'],'path':'-'.join(map(str,path)),
                         'model_market_ratio':float(ratio[i]),'odds':float(od),'market_p':float(market[i]),
                         'model_p':float(model[i]),'hit':int(i==y),'return_yen':x['payout'] if i==y else 0.0})
    return pd.DataFrame(rows)


def select(tt,ratio_th,odds_cap):
    z=tt[(tt.model_market_ratio>=ratio_th)&(tt.odds<=odds_cap)].copy()
    if z.empty:return z
    # one bet per race: strongest disagreement, tie-break lower odds
    z=z.sort_values(['レースコード','model_market_ratio','odds'],ascending=[True,False,True])
    return z.groupby('レースコード',sort=False).head(1).copy()


def stat(b,total):
    n=len(b)
    if n==0:return {'bets':0,'races_bet':0,'coverage':0.0,'hits':0,'hit_rate':np.nan,'roi_pct':np.nan,'avg_odds':np.nan,'avg_ratio':np.nan}
    rb=b['レースコード'].nunique()
    return {'bets':int(n),'races_bet':int(rb),'coverage':rb/total if total else np.nan,'hits':int(b.hit.sum()),
            'hit_rate':float(b.hit.mean()),'roi_pct':float(b.return_yen.sum())/(100*n)*100,
            'avg_odds':float(b.odds.mean()),'avg_ratio':float(b.model_market_ratio.mean())}


def main():
    src=Path('source/data'); out=Path('artifacts/advisor_disagreement_quick'); out.mkdir(parents=True,exist_ok=True)
    base,f2lk,f3lk,b2,b3,chainlk=h.build_data(); base=ev.attach_market(base,src)
    jul=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.CAL_END)].copy()
    aug=base[(base.race_date>=m.OOS_START)&(base.race_date<=m.OOS_END)].copy()
    oos=q.stratified_sample(aug,q.OOS_N,q.SEED+1)
    rem=aug[~aug['レースコード'].isin(set(oos['レースコード']))].copy()
    cj=mc.build_cache(jul,f2lk,f3lk,b2,b3,chainlk)
    co=mc.build_cache(oos,f2lk,f3lk,b2,b3,chainlk)
    cr=mc.build_cache(rem,f2lk,f3lk,b2,b3,chainlk)
    tj,to,tr=map(make_ticket_cache,[cj,co,cr])
    rows=[]
    for rt,cap in itertools.product(RATIO_THRESHOLDS,ODDS_CAPS):
        b=select(tj,rt,cap)
        rows.append({'ratio_threshold':rt,'odds_cap':cap,**stat(b,len(cj))})
    grid=pd.DataFrame(rows).sort_values(['roi_pct','bets'],ascending=[False,False]).reset_index(drop=True)
    grid.to_csv(out/'disagreement_grid_july.csv',index=False)
    cand=grid[grid.bets>=MIN_JULY_BETS].head(5)
    if cand.empty:cand=grid.head(5)
    vals=[]
    for label,tt,n in [('August_OOS_1000',to,len(co)),('August_remainder',tr,len(cr))]:
        for c in cand.itertuples(index=False):
            b=select(tt,float(c.ratio_threshold),float(c.odds_cap))
            vals.append({'split':label,'ratio_threshold':float(c.ratio_threshold),'odds_cap':float(c.odds_cap),**stat(b,n)})
    vd=pd.DataFrame(vals)
    cand.to_csv(out/'top5_july.csv',index=False); vd.to_csv(out/'top5_aug_validation.csv',index=False)
    print(f'DISAGREEMENT QUICK July={len(cj):,} AugOOS={len(co):,} AugRem={len(cr):,}')
    print('\nJULY TOP RULES')
    print(cand.to_string(index=False))
    print('\nAUGUST FIXED VALIDATION')
    print(vd.to_string(index=False))
    print('\nRule meaning: bet at most one ticket per race where internal model probability exceeds normalized market probability by threshold, with an odds cap. No further search if this fails OOS.')

if __name__=='__main__':main()
