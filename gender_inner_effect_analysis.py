#!/usr/bin/env python3
from pathlib import Path
import glob
import numpy as np
import pandas as pd

SRC=Path('source/data'); OUT=Path('artifacts/gender_inner_effect'); OUT.mkdir(parents=True,exist_ok=True)

def load(p):
    xs=[]
    for f in sorted(glob.glob(str(SRC/p))):
        try: xs.append(pd.read_csv(f,low_memory=False))
        except: pass
    return pd.concat(xs,ignore_index=True) if xs else pd.DataFrame()

def cards_long(df):
    out=[]
    for b in range(1,7):
        mp={'レースコード':'race','レース日':'date',f'艇{b}_登録番号':'reg'}
        if all(c in df.columns for c in mp):
            q=df[list(mp)].rename(columns=mp).copy(); q['boat']=b; out.append(q)
    return pd.concat(out,ignore_index=True)

def tkz_long(df):
    out=[]
    for b in range(1,7):
        mp={'レースコード':'race',f'艇{b}_体重(kg)':'weight',f'艇{b}_体重調整(kg)':'adjust'}
        if all(c in df.columns for c in mp):
            q=df[list(mp)].rename(columns=mp).copy(); q['boat']=b; out.append(q)
    return pd.concat(out,ignore_index=True)

def result_long(df):
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
T=tkz_long(load('previews/tkz/*/*/*.csv'))
R=result_long(load('results/realtime/*/*/*.csv'))
for d in (C,T,R):
    d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(T,on=['race','boat']).merge(R,on=['race','boat'])
X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','weight','adjust','course','finish']:
    X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','weight','adjust','course','finish'])
X['carried']=X.weight+X.adjust
med=X.groupby('reg').carried.median(); X['sex_est']=X.reg.map((med<49.5).map({True:'female_est',False:'male_est'}))
inner=X[['race','course','reg','sex_est','finish']].copy(); inner['course']=inner.course+1
inner=inner.rename(columns={'reg':'inner_reg','sex_est':'inner_sex','finish':'inner_finish'})
Y=X.merge(inner,on=['race','course'],how='inner')
Y=Y[(Y.sex_est=='male_est') & (Y.course>=2)].copy()
Y['beats_inner']=(Y.finish<Y.inner_finish).astype(float)
Y['male_win']=(Y.finish==1).astype(float)
Y['male_top3']=(Y.finish<=3).astype(float)
Y['inner_top3']=(Y.inner_finish<=3).astype(float)

# two-sided adjustment: outer male's normal ability AND inner opponent's normal ability, by course.
# resid = y - actor(course) mean - inner_opponent(inner-course) mean + course mean
for col in ['beats_inner','male_win','male_top3','inner_top3']:
    actor=Y.groupby(['reg','course'])[col].transform('mean')
    opp=Y.groupby(['inner_reg','course'])[col].transform('mean')
    course_mean=Y.groupby('course')[col].transform('mean')
    Y[col+'_adj']=Y[col]-actor-opp+course_mean

rows=[]
for innersex,g in Y.groupby('inner_sex'):
    row={'inner_sex':innersex,'n':len(g)}
    for col in ['beats_inner','male_win','male_top3','inner_top3']:
        row[col]=g[col].mean(); row[col+'_adj']=g[col+'_adj'].mean()
    rows.append(row)
S=pd.DataFrame(rows)

cr=[]
for course,g in Y.groupby('course'):
    a=g[g.inner_sex=='female_est']; b=g[g.inner_sex=='male_est']
    if len(a) and len(b):
        cr.append({'course':int(course),'n_female_inner':len(a),'n_male_inner':len(b),**{c+'_diff':a[c+'_adj'].mean()-b[c+'_adj'].mean() for c in ['beats_inner','male_win','male_top3','inner_top3']}})
CD=pd.DataFrame(cr)

hr=[]
for label,mask in [('early',Y.date<=pd.Timestamp('2026-06-30')),('late',Y.date>=pd.Timestamp('2026-07-01'))]:
    Z=Y[mask].copy()
    for col in ['beats_inner','male_win','male_top3','inner_top3']:
        actor=Z.groupby(['reg','course'])[col].transform('mean')
        opp=Z.groupby(['inner_reg','course'])[col].transform('mean')
        cm=Z.groupby('course')[col].transform('mean')
        Z[col+'_adj2']=Z[col]-actor-opp+cm
    a=Z[Z.inner_sex=='female_est']; b=Z[Z.inner_sex=='male_est']
    if len(a) and len(b):
        hr.append({'period':label,'n_female_inner':len(a),'n_male_inner':len(b),**{c+'_diff':a[c+'_adj2'].mean()-b[c+'_adj2'].mean() for c in ['beats_inner','male_win','male_top3','inner_top3']}})
H=pd.DataFrame(hr)

pr=[]
for reg,g in Y.groupby('reg'):
    a=g[g.inner_sex=='female_est']; b=g[g.inner_sex=='male_est']
    if len(a)>=20 and len(b)>=80:
        pr.append({'reg':int(reg),'n_female_inner':len(a),'n_male_inner':len(b),**{c+'_diff':a[c+'_adj'].mean()-b[c+'_adj'].mean() for c in ['beats_inner','male_win','male_top3','inner_top3']}})
P=pd.DataFrame(pr)
if len(P): P=P.sort_values('beats_inner_diff')
S.to_csv(OUT/'summary.csv',index=False); CD.to_csv(OUT/'course_detail.csv',index=False); H.to_csv(OUT/'holdout.csv',index=False); P.to_csv(OUT/'player_candidates.csv',index=False)
print('STARTS',len(X),'MALE_OUTER_ADJ',len(Y),'RACERS',Y.reg.nunique())
print('\nSUMMARY\n'+S.to_string(index=False))
print('\nCOURSE\n'+CD.to_string(index=False))
print('\nHOLDOUT\n'+H.to_string(index=False))
print('\nPLAYER LOW beats-inner (possible restraint)\n'+(P.head(20).to_string(index=False) if len(P) else 'none'))
print('\nNOTE: sex is inferred from median carried weight (<49.5 female-like), so this is preliminary. Losing-racer intent is not observed. Two-sided adjustment removes both outer male and inner opponent historical course ability.')
