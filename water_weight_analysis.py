#!/usr/bin/env python3
from pathlib import Path
import glob
import numpy as np
import pandas as pd

SRC=Path('source/data'); OUT=Path('artifacts/water_weight_analysis'); OUT.mkdir(parents=True,exist_ok=True)
WATER={'01':'fresh','02':'fresh','03':'brackish','04':'sea','05':'fresh','06':'brackish','07':'brackish','08':'sea','09':'sea','10':'fresh','11':'fresh','12':'fresh','13':'fresh','14':'sea','15':'sea','16':'sea','17':'sea','18':'sea','19':'sea','20':'sea','21':'fresh','22':'brackish','23':'fresh','24':'sea'}

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
        q=df[list(mp)].rename(columns=mp).copy(); q['boat']=b; out.append(q)
    return pd.concat(out,ignore_index=True)

def tkz_long(df):
    out=[]
    for b in range(1,7):
        mp={'レースコード':'race',f'艇{b}_体重(kg)':'weight',f'艇{b}_体重調整(kg)':'adjust'}
        q=df[list(mp)].rename(columns=mp).copy(); q['boat']=b; out.append(q)
    return pd.concat(out,ignore_index=True)

def result_long(df):
    fs=[]; cs=[]
    for k in range(1,7):
        c=f'{k}着_艇番'; q=df[['レースコード',c]].rename(columns={'レースコード':'race',c:'boat'}).copy(); q['finish']=k; fs.append(q)
        c=f'{k}コース_艇番'; q=df[['レースコード',c]].rename(columns={'レースコード':'race',c:'boat'}).copy(); q['course']=k; cs.append(q)
    return pd.concat(fs).merge(pd.concat(cs),on=['race','boat'])

def slope(g,col):
    z=g[['excess',col]].dropna()
    if len(z)<100 or z.excess.std()<0.15:return np.nan
    x=z.excess.to_numpy(float); y=z[col].to_numpy(float)
    return np.cov(x,y,bias=True)[0,1]/np.var(x)*100

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
X['win']=(X.finish==1).astype(float); X['top3']=(X.finish<=3).astype(float)
for y in ['win','top3']:
    X[y+'_resid']=X[y]-X.groupby(['reg','course'])[y].transform('mean')

# raw bins
X['bin']=pd.cut(X.excess,[-.01,.99,1.99,2.99,99],labels=['0-0.9','1-1.9','2-2.9','3+'])
B=X.groupby(['sex','water','course','bin'],observed=True).agg(n=('win','size'),win=('win','mean'),top3=('top3','mean'),avg_excess=('excess','mean')).reset_index(); B.to_csv(OUT/'bins.csv',index=False)

rows=[]
for (sex,water,course),g in X.groupby(['sex','water','course']):
    rows.append({'sex':sex,'water':water,'course':int(course),'n':len(g),'win_pt_per_kg':slope(g,'win_resid'),'top3_pt_per_kg':slope(g,'top3_resid')})
S=pd.DataFrame(rows); S.to_csv(OUT/'slopes_by_course.csv',index=False)
summary=[]
for sex in ['male','female']:
    for water in ['fresh','sea','brackish']:
        q=S[(S.sex==sex)&(S.water==water)&S.win_pt_per_kg.notna()]
        if len(q): summary.append({'sex':sex,'water':water,'n':int(q.n.sum()),'win_pt_per_kg':np.average(q.win_pt_per_kg,weights=q.n),'top3_pt_per_kg':np.average(q.top3_pt_per_kg,weights=q.n)})
SUM=pd.DataFrame(summary); SUM.to_csv(OUT/'summary.csv',index=False)

hold=[]
for label,mask in [('early',X.date<=pd.Timestamp('2026-06-30')),('late',X.date>=pd.Timestamp('2026-07-01'))]:
    Z=X[mask].copy()
    for y in ['win','top3']: Z[y+'_r2']=Z[y]-Z.groupby(['reg','course'])[y].transform('mean')
    for sex in ['male','female']:
        for water in ['fresh','sea']:
            g=Z[(Z.sex==sex)&(Z.water==water)]
            hold.append({'period':label,'sex':sex,'water':water,'n':len(g),'win_pt_per_kg':slope(g,'win_r2'),'top3_pt_per_kg':slope(g,'top3_r2')})
H=pd.DataFrame(hold); H.to_csv(OUT/'holdout.csv',index=False)

print('RUNS',len(X),'RACERS',X.reg.nunique())
print('\nSUMMARY\n'+SUM.to_string(index=False))
print('\nHOLDOUT\n'+H.to_string(index=False))
print('\nCOURSE\n'+S.to_string(index=False))
