#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import itertools
import numpy as np
import pandas as pd

import advisor_extension_patterns as m
import advisor_weight_quick as q
import advisor_hierarchical_quick as h
from racer_directory import load_many

PARAMS=(0.25,0.0,0.25)
EV_THRESHOLDS=[1.00,1.10,1.20,1.30,1.50,2.00]
TOPKS=[1,2,3]
MIN_CAL_BETS=200
EPS=1e-12


def attach_market(base: pd.DataFrame, src: Path) -> pd.DataFrame:
    odds=load_many(str(src/'previews/od3/2026/{07,08}/*.csv'))
    if odds.empty:
        odds=pd.concat([
            load_many(str(src/'previews/od3/2026/07/*.csv')),
            load_many(str(src/'previews/od3/2026/08/*.csv'))
        ],ignore_index=True)
    odds=odds.drop_duplicates('レースコード',keep='last').copy()
    keep=['レースコード']+[c for c in m.ODDS_COLS if c in odds.columns]
    odds=odds[keep]
    for c in m.ODDS_COLS:
        if c not in odds: odds[c]=np.nan
        odds[c]=pd.to_numeric(odds[c],errors='coerce')

    pay=load_many(str(src/'results/payouts/2026/{07,08}/*.csv'))
    if pay.empty:
        pay=pd.concat([
            load_many(str(src/'results/payouts/2026/07/*.csv')),
            load_many(str(src/'results/payouts/2026/08/*.csv'))
        ],ignore_index=True)
    pay=pay.drop_duplicates('レースコード',keep='last').copy()
    pay['winner_path_pay']=pay['3連単_組番'].map(m.parse_combo)
    pay['actual_payout']=pd.to_numeric(pay['3連単_払戻金'],errors='coerce')
    pay=pay.dropna(subset=['winner_path_pay','actual_payout'])
    return base.merge(odds[['レースコード']+m.ODDS_COLS],on='レースコード',how='inner').merge(
        pay[['レースコード','winner_path_pay','actual_payout']],on='レースコード',how='inner')


def ticket_table(df,f2lk,f3lk,b2,b3,chainlk):
    rows=[]
    for _,r in df.iterrows():
        p=h.hier_probs(r,f2lk,f3lk,b2,b3,chainlk,*PARAMS)
        win=tuple(r['winner_path_pay'])
        for i,path in enumerate(m.PATHS):
            col=f'3連単_{path[0]}-{path[1]}-{path[2]}'
            od=q.safe(r.get(col),np.nan)
            if not np.isfinite(od) or od<=0: continue
            prob=float(p[i]); ev=prob*od
            hit=int(path==win)
            rows.append({'レースコード':r['レースコード'],'race_date':r['race_date'],'path':'-'.join(map(str,path)),
                         'prob':prob,'odds':od,'pred_ev':ev,'hit':hit,
                         'return_yen':float(r['actual_payout']) if hit else 0.0})
    return pd.DataFrame(rows)


def make_bets(tickets,threshold,topk):
    z=tickets[tickets.pred_ev>=threshold].copy()
    if z.empty: return z
    z=z.sort_values(['レースコード','pred_ev'],ascending=[True,False])
    return z.groupby('レースコード',sort=False).head(topk).copy()


def max_drawdown_yen(bets):
    if bets.empty: return np.nan
    z=bets.sort_values(['race_date','レースコード']).copy()
    pnl=z.return_yen-100.0
    cum=pnl.cumsum().to_numpy(dtype=float)
    peak=np.maximum.accumulate(np.r_[0.0,cum])
    dd=peak[1:]-cum
    return float(dd.max()) if len(dd) else 0.0


def stat(bets,total_races):
    n=len(bets)
    if n==0:
        return {'bets':0,'races_bet':0,'coverage':0.0,'bets_per_race':0.0,'hits':0,'hit_rate':np.nan,'roi_pct':np.nan,'avg_odds':np.nan,'avg_pred_ev':np.nan,'max_drawdown_yen':np.nan}
    rb=bets['レースコード'].nunique()
    return {'bets':int(n),'races_bet':int(rb),'coverage':rb/total_races if total_races else np.nan,
            'bets_per_race':n/rb if rb else np.nan,'hits':int(bets.hit.sum()),'hit_rate':float(bets.hit.mean()),
            'roi_pct':float(bets.return_yen.sum())/(100.0*n)*100.0,
            'avg_odds':float(bets.odds.mean()),'avg_pred_ev':float(bets.pred_ev.mean()),
            'max_drawdown_yen':max_drawdown_yen(bets)}


def scan(tickets,total_races):
    rows=[]
    for th,k in itertools.product(EV_THRESHOLDS,TOPKS):
        b=make_bets(tickets,th,k)
        rows.append({'ev_threshold':th,'topk':k,**stat(b,total_races)})
    return pd.DataFrame(rows)


def main():
    src=Path('source/data'); out=Path('artifacts/advisor_ev_quick'); out.mkdir(parents=True,exist_ok=True)
    base,f2lk,f3lk,b2,b3,chainlk=h.build_data()
    base=attach_market(base,src)
    jul=base[(base.race_date>=m.CAL_START)&(base.race_date<=m.CAL_END)].copy()
    aug=base[(base.race_date>=m.OOS_START)&(base.race_date<=m.OOS_END)].copy()
    cal=q.stratified_sample(jul,q.CAL_N,q.SEED)
    oos=q.stratified_sample(aug,q.OOS_N,q.SEED+1)
    rem_j=jul[~jul['レースコード'].isin(set(cal['レースコード']))].copy()
    rem_a=aug[~aug['レースコード'].isin(set(oos['レースコード']))].copy()

    print(f'EV QUICK base races cal={len(cal):,} oos={len(oos):,} remainder={len(rem_j)+len(rem_a):,}')
    tcal=ticket_table(cal,f2lk,f3lk,b2,b3,chainlk)
    calgrid=scan(tcal,len(cal))
    calgrid.to_csv(out/'ev_grid_july.csv',index=False)
    eligible=calgrid[calgrid.bets>=MIN_CAL_BETS].sort_values(['roi_pct','bets'],ascending=[False,False]).head(5)
    if eligible.empty:
        eligible=calgrid.sort_values(['roi_pct','bets'],ascending=[False,False]).head(5)

    def eval_candidates(label,df,cands):
        tt=ticket_table(df,f2lk,f3lk,b2,b3,chainlk)
        rows=[]
        for _,c in cands.iterrows():
            b=make_bets(tt,float(c.ev_threshold),int(c.topk))
            rows.append({'split':label,'ev_threshold':float(c.ev_threshold),'topk':int(c.topk),**stat(b,len(df))})
        return pd.DataFrame(rows)

    eo=eval_candidates('August_OOS_1000',oos,eligible)
    erj=eval_candidates('July_remainder',rem_j,eligible)
    era=eval_candidates('August_remainder',rem_a,eligible)
    erc=eval_candidates('Combined_remainder',pd.concat([rem_j,rem_a]),eligible)
    final=pd.concat([eligible.assign(split='July_CAL_1500'),eo,erj,era,erc],ignore_index=True,sort=False)
    final.to_csv(out/'ev_top5_validation.csv',index=False)

    print('\nJULY TOP EV RULES (min 200 bets)')
    print(eligible.to_string(index=False))
    print('\nVALIDATION')
    print(pd.concat([eo,erj,era,erc],ignore_index=True).to_string(index=False))
    print('\nNOTE: odds are pre-close snapshots; realized ROI uses actual 100-yen trifecta payout. This is provisional screening, not a claim of live profitability.')

if __name__=='__main__':
    main()
