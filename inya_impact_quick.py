#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
from racer_directory import load_many, cards_to_long, results_to_long, build_panel

SRC=Path('source/data')
OUT=Path('artifacts/inya_impact_quick'); OUT.mkdir(parents=True, exist_ok=True)
CUT=pd.Timestamp('2026-07-01')

cards=load_many(str(SRC/'programs/race_cards/*/*/*.csv'))
results=load_many(str(SRC/'results/realtime/*/*/*.csv'))
title=load_many(str(SRC/'programs/title/*/*/*.csv'))
panel=build_panel(cards_to_long(cards), results_to_long(results), title)
panel=panel.dropna(subset=['race_date','regno','boat_no','actual_course','finish']).copy()
panel['boat_no']=pd.to_numeric(panel['boat_no'],errors='coerce').astype(int)
panel['actual_course']=pd.to_numeric(panel['actual_course'],errors='coerce').astype(int)
panel['move_in']=(panel['boat_no']-panel['actual_course']).clip(lower=0)
panel['fronted']=(panel['move_in']>0).astype(int)

train=panel[panel.race_date<CUT].copy()
evalp=panel[panel.race_date>=CUT].copy()

# Historical front-push profile, only when drawn 3-6 where there is room to move inward.
opps=train[train.boat_no>=3].copy()
prof=(opps.groupby(['regno','name'],dropna=False)
      .agg(opps=('レースコード','size'),fronts=('fronted','sum'),avg_move=('move_in','mean'),max_move=('move_in','max'))
      .reset_index())
prof['front_rate']=prof.fronts/prof.opps
prof['inya30']=(prof.opps>=15)&(prof.front_rate>=0.30)
prof['inya50']=(prof.opps>=15)&(prof.front_rate>=0.50)
# Top-decile among racers with 15+ opportunities
eligible=prof[prof.opps>=15]
q90=float(eligible.front_rate.quantile(.90)) if len(eligible) else np.nan
prof['inya_top10']=(prof.opps>=15)&(prof.front_rate>=q90)
prof.sort_values(['front_rate','opps'],ascending=[False,False]).to_csv(OUT/'inya_profiles.csv',index=False)

flags=prof[['regno','inya30','inya50','inya_top10','front_rate','opps']]
evalp=evalp.merge(flags,on='regno',how='left')
for c in ['inya30','inya50','inya_top10']:
    evalp[c]=evalp[c].fillna(False)

# Race-level event features
race_rows=[]
for rc,g in evalp.groupby('レースコード'):
    b1=g[g.boat_no.eq(1)]
    if b1.empty: continue
    b1=b1.iloc[0]
    front=g[g.fronted.eq(1)]
    f30=g[g.fronted.eq(1)&g.inya30]
    f50=g[g.fronted.eq(1)&g.inya50]
    f10=g[g.fronted.eq(1)&g.inya_top10]
    winner=g[g.finish.eq(1)]
    win_boat=int(winner.boat_no.iloc[0]) if len(winner) else -1
    method=str(winner['決まり手'].iloc[0]) if len(winner) and '決まり手' in winner else ''
    race_rows.append({
        'race_code':rc,'race_date':b1.race_date,'venue':str(b1.get('レース場','')),
        'b1_regno':int(b1.regno),'b1_name':b1.get('name',''),
        'b1_nat_win':pd.to_numeric(pd.Series([b1.get('national_win_rate',np.nan)]),errors='coerce').iloc[0],
        'b1_actual_course':int(b1.actual_course),
        'b1_win':int(win_boat==1),
        'b1_escape':int(win_boat==1 and method=='逃げ'),
        'b1_top2':int(b1.finish<=2),'b1_top3':int(b1.finish<=3),
        'any_front':int(len(front)>0),
        'inya30_front':int(len(f30)>0),'inya50_front':int(len(f50)>0),'inya_top10_front':int(len(f10)>0),
        'front_count':int(len(front)),
        'max_move':int(front.move_in.max()) if len(front) else 0,
        'deepest_front_course':int(front.actual_course.min()) if len(front) else 9,
        'inya30_deepest_course':int(f30.actual_course.min()) if len(f30) else 9,
    })
r=pd.DataFrame(race_rows)
# Strength bins for adjusted expectation.
r['b1_strength_bin']=pd.qcut(r['b1_nat_win'],5,labels=False,duplicates='drop')

# Baseline expected rates by venue x b1 strength bin x whether b1 retained course1, using races with no actual front-push.
base=r[r.any_front.eq(0)].copy()
keys=['venue','b1_strength_bin','b1_actual_course']
base_rates=(base.groupby(keys,dropna=False)
            .agg(base_n=('race_code','size'),exp_win=('b1_win','mean'),exp_escape=('b1_escape','mean'),exp_top2=('b1_top2','mean'))
            .reset_index())
# fallback strength-bin-only baselines
fb=(base.groupby(['b1_strength_bin','b1_actual_course'],dropna=False)
    .agg(fb_win=('b1_win','mean'),fb_escape=('b1_escape','mean'),fb_top2=('b1_top2','mean')).reset_index())

def summarize(label, mask):
    z=r[mask].copy()
    if z.empty:
        return {'group':label,'n':0}
    z=z.merge(base_rates,on=keys,how='left').merge(fb,on=['b1_strength_bin','b1_actual_course'],how='left')
    z['ew']=z.exp_win.fillna(z.fb_win); z['ee']=z.exp_escape.fillna(z.fb_escape); z['et2']=z.exp_top2.fillna(z.fb_top2)
    return {
        'group':label,'n':len(z),
        'b1_win_rate':z.b1_win.mean(),'b1_escape_rate':z.b1_escape.mean(),'b1_top2_rate':z.b1_top2.mean(),
        'expected_win_matched':z.ew.mean(),'win_lift_pt_adj':(z.b1_win-z.ew).mean(),
        'expected_escape_matched':z.ee.mean(),'escape_lift_pt_adj':(z.b1_escape-z.ee).mean(),
        'expected_top2_matched':z.et2.mean(),'top2_lift_pt_adj':(z.b1_top2-z.et2).mean(),
        'b1_retains_c1_rate':(z.b1_actual_course==1).mean(),
        'avg_b1_nat_win':z.b1_nat_win.mean(),
    }

rows=[]
rows.append(summarize('NO_FRONT_BASE',r.any_front.eq(0)))
rows.append(summarize('ANY_FRONT',r.any_front.eq(1)))
rows.append(summarize('INYA30_FRONT',r.inya30_front.eq(1)))
rows.append(summarize('INYA50_FRONT',r.inya50_front.eq(1)))
rows.append(summarize('INYA_TOP10_FRONT',r.inya_top10_front.eq(1)))
rows.append(summarize('INYA30_FRONT_B1_RETAINS_C1',r.inya30_front.eq(1)&r.b1_actual_course.eq(1)))
rows.append(summarize('INYA30_FRONT_B1_LOSES_C1',r.inya30_front.eq(1)&r.b1_actual_course.ne(1)))
rows.append(summarize('INYA30_TO_C2',r.inya30_front.eq(1)&r.inya30_deepest_course.eq(2)&r.b1_actual_course.eq(1)))
rows.append(summarize('INYA30_TO_C3',r.inya30_front.eq(1)&r.inya30_deepest_course.eq(3)&r.b1_actual_course.eq(1)))
rows.append(summarize('INYA30_MOVE2PLUS',r.inya30_front.eq(1)&r.max_move.ge(2)))
summary=pd.DataFrame(rows)
for c in [x for x in summary.columns if x.endswith('_rate') or x.endswith('_matched') or x.endswith('_adj')]:
    summary[c]=pd.to_numeric(summary[c],errors='coerce')
summary.to_csv(OUT/'inya_impact_summary.csv',index=False)

# Venue breakdown for the main definition, only reasonable n.
venue=[]
for v,g in r.groupby('venue'):
    m=g.inya30_front.eq(1)&g.b1_actual_course.eq(1)
    if m.sum()<20: continue
    s=summarize(f'VENUE_{v}', (r.venue.eq(v)&m))
    venue.append(s)
pd.DataFrame(venue).sort_values('win_lift_pt_adj').to_csv(OUT/'inya_impact_by_venue.csv',index=False)

# Deepness bands for actual front-push, descriptive.
bands=[]
for c in [2,3,4,5]:
    m=r.inya30_front.eq(1)&r.b1_actual_course.eq(1)&r.inya30_deepest_course.eq(c)
    if m.sum(): bands.append(summarize(f'INYA30_DEEPEST_C{c}',m))
pd.DataFrame(bands).to_csv(OUT/'inya_impact_by_depth.csv',index=False)

print(f'TRAIN through {train.race_date.max().date()} / EVAL {r.race_date.min().date()}..{r.race_date.max().date()} races={len(r):,}')
print(f'INYA thresholds: fixed30%, fixed50%, top10 threshold={q90:.3f}; eligible racers={len(eligible)}')
show=summary.copy()
for c in ['b1_win_rate','b1_escape_rate','b1_top2_rate','expected_win_matched','win_lift_pt_adj','expected_escape_matched','escape_lift_pt_adj','b1_retains_c1_rate']:
    if c in show: show[c]=show[c]*100
print(show[['group','n','b1_win_rate','expected_win_matched','win_lift_pt_adj','b1_escape_rate','expected_escape_matched','escape_lift_pt_adj','b1_retains_c1_rate']].to_string(index=False))
print('WROTE',OUT)
