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

EPS=1e-12
ALPHAS=[0.0,0.05,0.10,0.15,0.20,0.30,0.40,0.50,0.75,1.0]
EV_THRESHOLDS=[0.90,1.00,1.05,1.10,1.20,1.30]
TOPKS=[1,2,3]
MIN_CAL_BETS=150


def norm(v):
    v=np.asarray(v,dtype=float)
    v=np.clip(v,EPS,None)
    return v/v.sum()


def race_probs(row,f2lk,f3lk,b2,b3,chainlk):
    model=h.hier_probs(row,f2lk,f3lk,b2,b3,chainlk,*ev.PARAMS)
    odds=[]
    for a,b,c in m.PATHS:
        od=q.safe(row.get(f'3連単_{a}-{b}-{c}'),np.nan)
        odds.append(od)
    odds=np.asarray(odds,dtype=float)
    ok=np.isfinite(odds)&(odds>0)
    if ok.sum()<100:
        return None
    # unavailable/zero odds get tiny mass; normal races should have all 120.
    inv=np.where(ok,1.0/odds,EPS)
    market=norm(inv)
    return norm(model),market,odds


def blend(model,market,alpha):
    z=(1.0-alpha)*np.log(np.clip(market,EPS,1.0))+alpha*np.log(np.clip(model,EPS,1.0))
    z-=z.max()
    return norm(np.exp(z))


def build_cache(df,f2lk,f3lk,b2,b3,chainlk):
    pidx={p:i for i,p in enumerate(m.PATHS)}
    rows=[]
    for _,r in df.iterrows():
        rp=race_probs(r,f2lk,f3lk,b2,b3,chainlk)
        wp=tuple(r['winner_path_pay'])
        if rp is None or wp not in pidx: continue
        model,market,odds=rp
        rows.append({'code':r['レースコード'],'race_date':r['race_date'],'y':pidx[wp],
                     'payout':float(r['actual_payout']),'model':model,'market':market,'odds':odds})
    return rows


def metrics(cache,alpha):
    if not cache: return {'n':0,'logloss':np.nan,'top1':np.nan,'top5':np.nan}
    losses=[]; t1=0; t5=0
    for x in cache:
        p=blend(x['model'],x['market'],alpha); y=x['y']
        losses.append(-np.log(max(EPS,p[y])))
        t1+=int(int(np.argmax(p))==y)
        ids=np.argpartition(p,-5)[-5:]
        t5+=int(y in ids)
    n=len(cache)
    return {'n':n,'logloss':float(np.mean(losses)),'top1':t1/n,'top5':t5/n}


def tickets(cache,alpha):
    out=[]
    for x in cache:
        p=blend(x['model'],x['market'],alpha)
        for i,path in enumerate(m.PATHS):
            od=x['odds'][i]
            if not np.isfinite(od) or od<=0: continue
            hit=int(i==x['y'])
            out.append({'レースコード':x['code'],'race_date':x['race_date'],'path':'-'.join(map(str,path)),
                        'prob':float(p[i]),'odds':float(od),'pred_ev':float(p[i]*od),'hit':hit,
                        'return_yen':x['payout'] if hit else 0.0})
    return pd.DataFrame(out)


def scan_ev(tt,total):
    rows=[]
    for th,k in itertools.product(EV_THRESHOLDS,TOPKS):
        b=ev.make_bets(tt,th,k)
        rows.append({'ev_threshold':th,'topk':k,**ev.stat(b,total)})
    return pd.DataFrame(rows)


def main():
    src=Path('source/data'); out=Path('artifacts/advisor_market_calibration_quick'); out.mkdir(parents=True,exist_ok=True)
    base,f2lk,f3lk,b2,b3,chainlk=h.build_data()
    base=ev.attach_market(base,src)
    jul=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.CAL_END)].copy()
    aug=base[(base.race_date>=m.OOS_START)&(base.race_date<=m.OOS_END)].copy()
    # July market data is only ~1.4k standard-entry races; use all for alpha discovery.
    oos=q.stratified_sample(aug,q.OOS_N,q.SEED+1)
    rem=aug[~aug['レースコード'].isin(set(oos['レースコード']))].copy()

    cj=build_cache(jul,f2lk,f3lk,b2,b3,chainlk)
    co=build_cache(oos,f2lk,f3lk,b2,b3,chainlk)
    cr=build_cache(rem,f2lk,f3lk,b2,b3,chainlk)
    print(f'MARKET CALIBRATION races July={len(cj):,} AugOOS={len(co):,} AugRemainder={len(cr):,}')

    grid=[]
    for a in ALPHAS:
        sj=metrics(cj,a); so=metrics(co,a); sr=metrics(cr,a)
        grid.append({'alpha_model':a,**{f'jul_{k}':v for k,v in sj.items()},
                     **{f'aug_oos_{k}':v for k,v in so.items()},**{f'aug_rem_{k}':v for k,v in sr.items()}})
    gd=pd.DataFrame(grid).sort_values('jul_logloss').reset_index(drop=True)
    gd.to_csv(out/'alpha_grid.csv',index=False)
    best=float(gd.iloc[0].alpha_model)
    print('\nALPHA GRID sorted by July logloss (alpha=0 market only, 1 model only)')
    print(gd.to_string(index=False))
    print(f'\nJULY SELECTED alpha_model={best:.2f}')

    tj=tickets(cj,best); to=tickets(co,best); tr=tickets(cr,best)
    ej=scan_ev(tj,len(cj))
    ej.to_csv(out/'ev_grid_july_calibrated.csv',index=False)
    candidates=ej[ej.bets>=MIN_CAL_BETS].sort_values(['roi_pct','bets'],ascending=[False,False]).head(5)
    if candidates.empty: candidates=ej.sort_values(['roi_pct','bets'],ascending=[False,False]).head(5)

    vals=[]
    for label,tt,n in [('August_OOS_1000',to,len(co)),('August_remainder',tr,len(cr))]:
        for c in candidates.itertuples(index=False):
            b=ev.make_bets(tt,float(c.ev_threshold),int(c.topk))
            vals.append({'split':label,'ev_threshold':float(c.ev_threshold),'topk':int(c.topk),**ev.stat(b,n)})
    vd=pd.DataFrame(vals)
    candidates.to_csv(out/'ev_top5_july.csv',index=False)
    vd.to_csv(out/'ev_top5_aug_validation.csv',index=False)
    print('\nJULY CALIBRATED EV CANDIDATES')
    print(candidates.to_string(index=False))
    print('\nAUGUST VALIDATION')
    print(vd.to_string(index=False))
    print('\nNOTE: market probability is normalized reciprocal pre-close odds. Internal 70/30 model remains unchanged; alpha is only the final market-relative calibration layer.')

if __name__=='__main__':
    main()
