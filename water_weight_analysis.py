#!/usr/bin/env python3
from pathlib import Path
import glob, os
import numpy as np
import pandas as pd

SRC=Path('source/data')
OUT=Path('artifacts/water_weight_analysis'); OUT.mkdir(parents=True, exist_ok=True)
WATER={
'01':'fresh','02':'fresh','03':'brackish','04':'sea','05':'fresh','06':'brackish','07':'brackish','08':'sea','09':'sea','10':'fresh','11':'fresh','12':'fresh','13':'fresh','14':'sea','15':'sea','16':'sea','17':'sea','18':'sea','19':'sea','20':'sea','21':'fresh','22':'brackish','23':'fresh','24':'sea'}

def load(pattern):
    fs=sorted(glob.glob(str(SRC/pattern)))
    xs=[]
    for f in fs:
        try: xs.append(pd.read_csv(f, low_memory=False))
        except: pass
    return pd.concat(xs, ignore_index=True) if xs else pd.DataFrame()

def long_cards(df):
    rows=[]
    for b in range(1,7):
        cols={'レースコード':'race','レース日':'date','レース場コード':'venue',f'艇{b}_登録番号':'reg',f'艇{b}_級別':'class',f'艇{b}_全国勝率':'nat_win',f'艇{b}_全国平均ST':'nat_st',f'艇{b}_モーター2連対率':'motor'}
        use=[c for c in cols if c in df.columns]
        q=df[use].rename(columns={c:cols[c] for c in use}).copy(); q['boat']=b; rows.append(q)
    return pd.concat(rows,ignore_index=True)

def long_tkz(df):
    rows=[]
    for b in range(1,7):
        cols={'レースコード':'race','レース日':'date','レース場':'venue',f'艇{b}_体重(kg)':'weight',f'艇{b}_体重調整(kg)':'adjust',f'艇{b}_展示タイム':'ex_time'}
        use=[c for c in cols if c in df.columns]
        q=df[use].rename(columns={c:cols[c] for c in use}).copy(); q['boat']=b; rows.append(q)
    return pd.concat(rows,ignore_index=True)

def long_results(df):
    rows=[]
    # finish by boat
    finish={}
    for k in range(1,7):
        c=f'{k}着_艇番'
        if c in df.columns:
            tmp=df[['レースコード',c]].copy(); tmp['finish']=k; tmp=tmp.rename(columns={'レースコード':'race',c:'boat'}); finish[k]=tmp
    f=pd.concat(finish.values(),ignore_index=True) if finish else pd.DataFrame(columns=['race','boat','finish'])
    # actual course by boat
    cs=[]
    for cno in range(1,7):
        c=f'{cno}コース_艇番'
        if c in df.columns:
            q=df[['レースコード',c]].copy().rename(columns={'レースコード':'race',c:'boat'}); q['course']=cno; cs.append(q)
    cr=pd.concat(cs,ignore_index=True) if cs else pd.DataFrame(columns=['race','boat','course'])
    z=f.merge(cr,on=['race','boat'],how='inner')
    return z

def slope(g,ycol):
    x=g['excess'].to_numpy(float); y=g[ycol].to_numpy(float)
    if len(g)<100 or np.nanstd(x)<0.15:return np.nan
    return float(np.cov(x,y,bias=True)[0,1]/np.var(x))

cards=load('programs/race_cards/*/*/*.csv')
tkz=load('previews/tkz/*/*/*.csv')
res=load('results/realtime/*/*/*.csv')
print('loaded',len(cards),len(tkz),len(res))
C=long_cards(cards); T=long_tkz(tkz); R=long_results(res)
for d in (C,T,R):
    d['race']=d['race'].astype(str)
    d['boat']=pd.to_numeric(d['boat'],errors='coerce')
X=C.merge(T,on=['race','boat'],how='inner',suffixes=('','_t')).merge(R,on=['race','boat'],how='inner')
X['date']=pd.to_datetime(X['date'],errors='coerce')
X=X[X['date']>=pd.Timestamp('2025-11-01')].copy()
X['venue']=X['venue'].astype(str).str.extract(r'(\d+)')[0].str.zfill(2)
X['water']=X['venue'].map(WATER)
for c in ['reg','weight','adjust','course','finish','nat_win','nat_st','motor']:
    X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','weight','adjust','course','finish','water'])
X['carried']=X['weight']+X['adjust']
# infer minimum-weight regime by racer median carried weight; robustly separates 47kg female regime from 52kg male regime
regmed=X.groupby('reg')['carried'].median()
sexmap=(regmed<49.5).map({True:'female',False:'male'})
X['sex']=X['reg'].map(sexmap)
X['minimum']=np.where(X.sex.eq('female'),47.0,52.0)
X['excess']=(X['carried']-X['minimum']).clip(lower=0)
X['win']=(X.finish==1).astype(float); X['top3']=(X.finish<=3).astype(float)
# baseline residuals by racer x course to reduce ability confounding
for y in ['win','top3']:
    X[y+'_base']=X.groupby(['reg','course'])[y].transform('mean')
    X[y+'_resid']=X[y]-X[y+'_base']
# summarize raw bins and residual slope by sex/water/course
X['bin']=pd.cut(X.excess,[-.01,.99,1.99,2.99,99],labels=['0-0.9','1-1.9','2-2.9','3+'])
raw=X.groupby(['sex','water','course','bin'],observed=True).agg(n=('win','size'),win=('win','mean'),top3=('top3','mean'),avg_excess=('excess','mean')).reset_index()
raw.to_csv(OUT/'bins.csv',index=False)
rows=[]
for (sex,water,course),g in X.groupby(['sex','water','course']):
    rows.append({'sex':sex,'water':water,'course':int(course),'n':len(g),'avg_excess':g.excess.mean(),'win_slope_pt_per_kg':slope(g,'win_resid')*100 if len(g) else np.nan,'top3_slope_pt_per_kg':slope(g,'top3_resid')*100 if len(g) else np.nan})
S=pd.DataFrame(rows); S.to_csv(OUT/'slopes_by_course.csv',index=False)
# weighted overall across courses
summary=[]
for sex in ['male','female']:
  for water in ['fresh','sea','brackish']:
    q=S[(S.sex==sex)&(S.water==water)&S.win_slope_pt_per_kg.notna()]
    if len(q):
      summary.append({'sex':sex,'water':water,'n':int(q.n.sum()),'win_slope_pt_per_kg':np.average(q.win_slope_pt_per_kg,weights=q.n),'top3_slope_pt_per_kg':np.average(q.top3_slope_pt_per_kg,weights=q.n)})
SUM=pd.DataFrame(summary); SUM.to_csv(OUT/'summary.csv',index=False)
# holdout: Jan-Jun vs Jul-Aug, same method
hold=[]
for label,mask in [('early',X.date<=pd.Timestamp('2026-06-30')),('late',X.date>=pd.Timestamp('2026-07-01'))]:
  Z=X[mask].copy()
  for y in ['win','top3']:
    Z[y+'_base2']=Z.groupby(['reg','course'])[y].transform('mean'); Z[y+'_resid2']=Z[y]-Z[y+'_base2']
  for sex in ['male','female']:
    for water in ['fresh','sea']:
      g=Z[(Z.sex==sex)&(Z.water==water)]
      hold.append({'period':label,'sex':sex,'water':water,'n':len(g),'win_pt_per_kg':slope(g.rename(columns={'win_resid2':'win_resid'}),'win_resid')*100 if len(g) else np.nan,'top3_pt_per_kg':slope(g.rename(columns={'top3_resid2':'top3_resid'}),'top3_resid')*100 if len(g) else np.nan})
H=pd.DataFrame(hold); H.to_csv(OUT/'holdout.csv',index=False)
print('\nSUMMARY\n',SUM.to_string(index=False))
print('\nHOLDOUT\n',H.to_string(index=False))
print('\nCOURSE\n',S.to_string(index=False))
