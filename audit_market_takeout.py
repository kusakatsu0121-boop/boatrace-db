#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
import backtest_ev as be

PERIODS = [
    ('JULY','2026-07-01','2026-07-31'),
    ('AUG','2026-08-01','2026-08-28'),
    ('POOLED','2026-07-01','2026-08-28'),
]


def main():
    out=Path('artifacts/market_takeout_audit'); out.mkdir(parents=True,exist_ok=True)
    _, base, _ = be.prepare_inputs(Path('source/data'))
    rows=[]; race_rows=[]
    for name,lo,hi in PERIODS:
        races=base[(base.race_date>=pd.Timestamp(lo))&(base.race_date<=pd.Timestamp(hi))].reset_index(drop=True)
        odds,q,winner,_=be.odds_in_exhibition_course_order(races)
        inv=np.where(np.isfinite(odds)&(odds>1),1.0/odds,np.nan)
        den=np.nansum(inv,axis=1)
        market_baseline=np.where(den>0,1.0/den,np.nan)
        # With q normalized from inverse odds, q_i*odds_i should equal baseline for every valid outcome.
        ev_market=q*odds
        ev_err=[]
        for i in range(len(races)):
            good=ev_market[i][np.isfinite(ev_market[i])]
            if len(good): ev_err.append(float(np.max(np.abs(good-market_baseline[i]))) if np.isfinite(market_baseline[i]) else np.nan)
            race_rows.append({'period':name,'race_date':races.iloc[i].race_date,'レースコード':races.iloc[i]['レースコード'],'sum_inverse_odds':den[i],'market_baseline_return':market_baseline[i]})
        x=market_baseline[np.isfinite(market_baseline)]
        rows.append({
            'period':name,'races':len(races),'valid_races':len(x),
            'baseline_mean_pct':float(np.mean(x)*100) if len(x) else np.nan,
            'baseline_median_pct':float(np.median(x)*100) if len(x) else np.nan,
            'baseline_p05_pct':float(np.quantile(x,.05)*100) if len(x) else np.nan,
            'baseline_p95_pct':float(np.quantile(x,.95)*100) if len(x) else np.nan,
            'sum_inverse_mean':float(np.mean(den[np.isfinite(den)])) if len(x) else np.nan,
            'max_identity_error':float(np.nanmax(ev_err)) if ev_err else np.nan,
        })
    pd.DataFrame(rows).to_csv(out/'summary.csv',index=False)
    pd.DataFrame(race_rows).to_csv(out/'race_level.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__': main()
