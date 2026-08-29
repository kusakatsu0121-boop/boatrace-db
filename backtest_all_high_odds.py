#!/usr/bin/env python3
from pathlib import Path
import re
import pandas as pd
import numpy as np

from racer_directory import load_many

THRESHOLDS = [100,150,200,300,500,1000]
START = pd.Timestamp('2026-07-01')
END = pd.Timestamp('2026-08-28')


def norm_combo(x):
    if pd.isna(x):
        return None
    s = re.sub(r'[^0-9]+','-',str(x)).strip('-')
    p = s.split('-')
    if len(p) != 3:
        return None
    try:
        return '-'.join(str(int(z)) for z in p)
    except Exception:
        return None


def main():
    src = Path('source/data')
    odds = load_many(str(src/'previews/od3/*/*/*.csv'))
    pay = load_many(str(src/'results/payouts/*/*/*.csv'))
    if odds.empty or pay.empty:
        raise SystemExit('od3/payouts missing')

    for df in (odds,pay):
        if 'レース日' in df.columns:
            df['race_date'] = pd.to_datetime(df['レース日'], errors='coerce')
        else:
            df['race_date'] = pd.to_datetime(df['レースコード'].astype(str).str[:8], format='%Y%m%d', errors='coerce')

    odds = odds[(odds.race_date>=START)&(odds.race_date<=END)].copy()
    pay = pay[(pay.race_date>=START)&(pay.race_date<=END)].copy()
    odds = odds.drop_duplicates('レースコード',keep='last')
    pay = pay.drop_duplicates('レースコード',keep='last')

    odds_cols = [c for c in odds.columns if str(c).startswith('3連単_') and re.fullmatch(r'3連単_[1-6]-[1-6]-[1-6]', str(c))]
    if not odds_cols:
        raise SystemExit('trifecta odds columns missing')

    p = pay[['レースコード','race_date','3連単_組番','3連単_払戻金']].copy()
    p['winner'] = p['3連単_組番'].map(norm_combo)
    p['payout'] = pd.to_numeric(p['3連単_払戻金'], errors='coerce')
    x = odds.merge(p[['レースコード','winner','payout']], on='レースコード', how='inner')

    rows=[]
    for period, mask in [
        ('JULY', x.race_date.dt.month.eq(7)),
        ('AUG', x.race_date.dt.month.eq(8)),
        ('POOLED', pd.Series(True,index=x.index)),
    ]:
        d=x[mask].copy()
        for th in THRESHOLDS:
            tickets=0; hit_races=0; ret=0.0; bet_races=0
            for r in d.itertuples(index=False):
                selected=[]
                for c in odds_cols:
                    o = pd.to_numeric(getattr(r,c), errors='coerce')
                    if pd.notna(o) and float(o)>=th:
                        selected.append(c.replace('3連単_',''))
                if not selected:
                    continue
                bet_races += 1
                tickets += len(selected)
                if r.winner in selected:
                    hit_races += 1
                    if pd.notna(r.payout):
                        ret += float(r.payout)
            stake=tickets*100.0
            rows.append({
                'period':period,'threshold_odds':th,'races':len(d),'bet_races':bet_races,
                'tickets':tickets,'avg_tickets_per_bet_race':tickets/bet_races if bet_races else np.nan,
                'hit_races':hit_races,'stake':stake,'return':ret,
                'roi_pct':ret/stake*100 if stake else np.nan,
            })
    out=Path('artifacts/all_high_odds'); out.mkdir(parents=True,exist_ok=True)
    res=pd.DataFrame(rows)
    res.to_csv(out/'summary.csv',index=False)
    print(res.to_string(index=False))

if __name__=='__main__':
    main()
