#!/usr/bin/env python3
from pathlib import Path
import glob
import pandas as pd
import numpy as np

SRC=Path('source/data'); OUT=Path('artifacts/ongaeshi_analysis'); OUT.mkdir(parents=True,exist_ok=True)

def load(pattern):
    xs=[]
    for f in sorted(glob.glob(str(SRC/pattern))):
        try: xs.append(pd.read_csv(f,low_memory=False))
        except Exception: pass
    return pd.concat(xs,ignore_index=True) if xs else pd.DataFrame()

def cards_long(df):
    out=[]
    for b in range(1,7):
        cols={'レースコード':'race','レース日':'date','レース場コード':'venue',f'艇{b}_登録番号':'reg'}
        if all(c in df.columns for c in cols):
            q=df[list(cols)].rename(columns=cols).copy(); q['boat']=b; out.append(q)
    return pd.concat(out,ignore_index=True)

def results_long(df):
    fs=[]; cs=[]
    for k in range(1,7):
        c=f'{k}着_艇番'
        if c in df.columns:
            q=df[['レースコード',c]].rename(columns={'レースコード':'race',c:'boat'}).copy(); q['finish']=k; fs.append(q)
        c=f'{k}コース_艇番'
        if c in df.columns:
            q=df[['レースコード',c]].rename(columns={'レースコード':'race',c:'boat'}).copy(); q['course']=k; cs.append(q)
    return pd.concat(fs,ignore_index=True).merge(pd.concat(cs,ignore_index=True),on=['race','boat'])

C=cards_long(load('programs/race_cards/*/*/*.csv'))
R=results_long(load('results/realtime/*/*/*.csv'))
for d in (C,R):
    d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat'])
X['date']=pd.to_datetime(X.date,errors='coerce')
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['date','reg','course','finish']).copy()
X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
X['reg']=X.reg.astype(int); X['course']=X.course.astype(int); X['finish']=X.finish.astype(int)

# race dictionaries by course
rows=[]
for race,g in X.groupby('race'):
    if len(g)<5: continue
    m={int(r.course):r for _,r in g.iterrows()}
    # strict observable proxy for an "恩恵" event:
    # donor wins from 2-5 course, immediately outside racer reaches top3.
    winner=g[g.finish.eq(1)]
    if len(winner)!=1: continue
    a=winner.iloc[0]
    ac=int(a.course)
    if ac<2 or ac>5 or ac+1 not in m: continue
    b=m[ac+1]
    if int(b.finish)<=3:
        rows.append({'benefit_race':race,'benefit_date':a.date,'donor':int(a.reg),'beneficiary':int(b.reg),
                     'donor_course0':ac,'beneficiary_course0':ac+1,'beneficiary_finish0':int(b.finish)})
E=pd.DataFrame(rows).drop_duplicates(['benefit_race','donor','beneficiary'])

# all ordered adjacent pair meetings: inner=A, outer=B
meet=[]
for race,g in X.groupby('race'):
    m={int(r.course):r for _,r in g.iterrows()}
    for c in range(1,6):
        if c not in m or c+1 not in m: continue
        a,b=m[c],m[c+1]
        meet.append({'race':race,'date':a.date,'donor':int(a.reg),'beneficiary':int(b.reg),
                     'inner_course':c,'outer_course':c+1,'inner_finish':int(a.finish),'outer_finish':int(b.finish),
                     'outer_beats_inner':int(b.finish<a.finish),'inner_top3':int(a.finish<=3)})
M=pd.DataFrame(meet)

# tag whether this ordered pair had a prior benefit event within 180d
E2=E[['donor','beneficiary','benefit_date']].sort_values('benefit_date')
M=M.sort_values('date').copy(); M['after_benefit']=0; M['days_since_benefit']=np.nan
last={}
# merge-like streaming per pair
for idx,r in M.iterrows():
    key=(r.donor,r.beneficiary)
    if key in last:
        dd=(r.date-last[key]).days
        if 1<=dd<=180:
            M.at[idx,'after_benefit']=1; M.at[idx,'days_since_benefit']=dd
    # update last benefit only if benefit happened on this race/date, handled below by date map
    # prebuild through date loop not necessary; use pair event lists later

# exact prior-event lookup using pair lists
pair_dates={k:list(v.benefit_date.sort_values()) for k,v in E2.groupby(['donor','beneficiary'])}
for idx,r in M.iterrows():
    ds=pair_dates.get((r.donor,r.beneficiary),[])
    prev=[d for d in ds if d<r.date]
    if prev:
        dd=(r.date-prev[-1]).days
        if dd<=180:
            M.at[idx,'after_benefit']=1; M.at[idx,'days_since_benefit']=dd

# residualize outcomes by the exact two courses to avoid comparing 1-2 with 4-5 etc.
base=M.groupby(['inner_course','outer_course'])[['outer_beats_inner','inner_top3']].mean().rename(columns=lambda c:c+'_base')
M=M.join(base,on=['inner_course','outer_course'])
M['beat_resid']=M.outer_beats_inner-M.outer_beats_inner_base
M['inner_top3_resid']=M.inner_top3-M.inner_top3_base

# stronger control: beneficiary and donor own course tendencies
bbase=M.groupby(['beneficiary','outer_course']).outer_beats_inner.mean().rename('b_beat_base')
abase=M.groupby(['donor','inner_course']).inner_top3.mean().rename('a_top3_base')
M=M.join(bbase,on=['beneficiary','outer_course']).join(abase,on=['donor','inner_course'])
M['beat_person_resid']=M.outer_beats_inner-M.b_beat_base
M['inner_top3_person_resid']=M.inner_top3-M.a_top3_base

def summarize(z,label):
    if len(z)==0:return None
    return {'group':label,'n':len(z),'outer_beats_inner_rate':z.outer_beats_inner.mean(),
            'inner_top3_rate':z.inner_top3.mean(),'beat_course_adjusted':z.beat_resid.mean(),
            'inner_top3_course_adjusted':z.inner_top3_resid.mean(),
            'beat_person_adjusted':z.beat_person_resid.mean(),
            'inner_top3_person_adjusted':z.inner_top3_person_resid.mean()}
S=pd.DataFrame([summarize(M[M.after_benefit.eq(1)],'after_benefit'),summarize(M[M.after_benefit.eq(0)],'no_recent_benefit')]).dropna(how='all')

# time split to test replication
hold=[]
for label,mask in [('early',M.date<=pd.Timestamp('2026-06-30')),('late',M.date>=pd.Timestamp('2026-07-01'))]:
    Z=M[mask & M.after_benefit.eq(1)]
    hold.append({'period':label,'n':len(Z),'outer_beats_inner_rate':Z.outer_beats_inner.mean() if len(Z) else np.nan,
                 'inner_top3_rate':Z.inner_top3.mean() if len(Z) else np.nan,
                 'beat_person_adjusted':Z.beat_person_resid.mean() if len(Z) else np.nan,
                 'inner_top3_person_adjusted':Z.inner_top3_person_resid.mean() if len(Z) else np.nan})
H=pd.DataFrame(hold)

# pair-level candidates, only enough repeat meetings
P=M[M.after_benefit.eq(1)].groupby(['donor','beneficiary']).agg(
    n=('race','size'), outer_beats_inner_rate=('outer_beats_inner','mean'), inner_top3_rate=('inner_top3','mean'),
    beat_person_adjusted=('beat_person_resid','mean'), inner_top3_person_adjusted=('inner_top3_person_resid','mean')).reset_index()
P=P[P.n>=3].sort_values(['n','beat_person_adjusted'],ascending=[False,True])

E.to_csv(OUT/'benefit_events.csv',index=False)
M.to_csv(OUT/'remeetings.csv',index=False)
S.to_csv(OUT/'summary.csv',index=False)
H.to_csv(OUT/'holdout.csv',index=False)
P.to_csv(OUT/'pair_candidates.csv',index=False)
print('STARTS',len(X),'RACES',X.race.nunique(),'BENEFIT_EVENTS',len(E),'REMEETINGS_AFTER',int(M.after_benefit.sum()))
print('\nSUMMARY\n',S.to_string(index=False))
print('\nHOLDOUT\n',H.to_string(index=False))
print('\nPAIR CANDIDATES\n',P.head(30).to_string(index=False))
print('\nCAUTION: this tests an observable after-benefit behavioral pattern. It does NOT prove gratitude, intent, collusion, or deliberate yielding.')
