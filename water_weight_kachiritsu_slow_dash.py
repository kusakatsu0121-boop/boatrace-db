#!/usr/bin/env python3
from pathlib import Path
import glob
import numpy as np
import pandas as pd

SRC=Path('source/data'); OUT=Path('artifacts/water_weight_kachiritsu_slow_dash'); OUT.mkdir(parents=True,exist_ok=True)
WATER={'01':'fresh','02':'fresh','03':'brackish','04':'sea','05':'fresh','06':'brackish','07':'brackish','08':'sea','09':'sea','10':'fresh','11':'fresh','12':'fresh','13':'fresh','14':'sea','15':'sea','16':'sea','17':'sea','18':'sea','19':'sea','20':'sea','21':'fresh','22':'brackish','23':'fresh','24':'sea'}
PTS={1:10.,2:8.,3:6.,4:4.,5:2.,6:1.}

def load(p):
    xs=[]
    for f in sorted(glob.glob(str(SRC/p))):
        try: xs.append(pd.read_csv(f,low_memory=False))
        except: pass
    return pd.concat(xs,ignore_index=True) if xs else pd.DataFrame()

def cards_long(df):
    out=[]
    for b in range(1,7):
        mp={'レースコード':'race','レース日':'date','レース場コード':'venue',f'艇{b}_登録番号':'reg'}
        if not all(c in df.columns for c in mp): continue
        q=df[list(mp)].rename(columns=mp).copy(); q['boat']=b; out.append(q)
    return pd.concat(out,ignore_index=True)

def tkz_long(df):
    out=[]
    for b in range(1,7):
        mp={'レースコード':'race',f'艇{b}_体重(kg)':'weight',f'艇{b}_体重調整(kg)':'adjust'}
        if not all(c in df.columns for c in mp): continue
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

def slope(g,col='score_resid'):
    z=g[['excess',col]].dropna()
    if len(z)<100 or z.excess.std()<0.15:return np.nan
    x=z.excess.to_numpy(float); y=z[col].to_numpy(float)
    return float(np.cov(x,y,bias=True)[0,1]/np.var(x))

C=cards_long(load('programs/race_cards/*/*/*.csv'))
T=tkz_long(load('previews/tkz/*/*/*.csv'))
R=result_long(load('results/realtime/*/*/*.csv'))
for d in (C,T,R):
    d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(T,on=['race','boat']).merge(R,on=['race','boat'])
X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
X['venue']=X.venue.astype(str).str.extract(r'(\d+)')[0].str.zfill(2); X['water']=X.venue.map(WATER)
for c in ['reg','weight','adjust','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','weight','adjust','course','finish','water'])
X['carried']=X.weight+X.adjust
med=X.groupby('reg').carried.median(); X['sex']=X.reg.map((med<49.5).map({True:'female',False:'male'}))
X['minimum']=np.where(X.sex.eq('female'),47.,52.); X['excess']=(X.carried-X.minimum).clip(lower=0)
X['score']=X.finish.map(PTS)
X['start_group']=np.where(X.course<=3,'slow','dash')
X['score_resid']=X.score-X.groupby(['reg','course']).score.transform('mean')
rows=[]
for (sex,water,grp),g in X[X.water.isin(['fresh','sea'])].groupby(['sex','water','start_group']):
    sl=slope(g)
    rows.append({'sex':sex,'water':water,'start_group':grp,'n':len(g),'avg_score':g.score.mean(),'score_change_per_kg':sl,'score_change_3kg':sl*3 if pd.notna(sl) else np.nan})
S=pd.DataFrame(rows); S.to_csv(OUT/'summary.csv',index=False)
# course detail
rows=[]
for (sex,water,course),g in X[X.water.isin(['fresh','sea'])].groupby(['sex','water','course']):
    sl=slope(g)
    rows.append({'sex':sex,'water':water,'course':int(course),'n':len(g),'avg_score':g.score.mean(),'score_change_per_kg':sl,'score_change_3kg':sl*3 if pd.notna(sl) else np.nan})
CDET=pd.DataFrame(rows); CDET.to_csv(OUT/'course_detail.csv',index=False)
# holdout early/late
hold=[]
for label,mask in [('early',X.date<=pd.Timestamp('2026-06-30')),('late',X.date>=pd.Timestamp('2026-07-01'))]:
    Z=X[mask].copy(); Z['score_r2']=Z.score-Z.groupby(['reg','course']).score.transform('mean')
    for (sex,water,grp),g in Z[Z.water.isin(['fresh','sea'])].groupby(['sex','water','start_group']):
        sl=slope(g,'score_r2')
        hold.append({'period':label,'sex':sex,'water':water,'start_group':grp,'n':len(g),'score_change_per_kg':sl,'score_change_3kg':sl*3 if pd.notna(sl) else np.nan})
H=pd.DataFrame(hold); H.to_csv(OUT/'holdout.csv',index=False)
print('RUNS',len(X),'RACERS',X.reg.nunique())
print('\nSUMMARY\n'+S.to_string(index=False))
print('\nHOLDOUT\n'+H.to_string(index=False))
print('\nCOURSE\n'+CDET.to_string(index=False))
print('\nNOTE general-race points only: 10,8,6,4,2,1. Grade/final bonuses not in source rows, so this is comparable-rate proxy, not exact official aggregate for graded races.')
