#!/usr/bin/env python3
from pathlib import Path
import glob,re,requests
import numpy as np
import pandas as pd
SRC=Path('source/data'); OUT=Path('artifacts/gender_true_makuri'); OUT.mkdir(parents=True,exist_ok=True)

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

def result_long(df):
 fs=[]; cs=[]
 for k in range(1,7):
  c=f'{k}着_艇番'
  if c in df.columns:
   q=df[['レースコード',c]].rename(columns={'レースコード':'race',c:'boat'}).copy(); q['finish']=k; fs.append(q)
  c=f'{k}コース_艇番'
  if c in df.columns:
   q=df[['レースコード',c]].rename(columns={'レースコード':'race',c:'boat'}).copy(); q['course']=k; cs.append(q)
 z=pd.concat(fs,ignore_index=True).merge(pd.concat(cs,ignore_index=True),on=['race','boat'])
 return z

def female_regs_official():
 regs=set()
 base='https://www.boatrace.jp/owpc/pc/data/racersearch/result?prevpgid=TDAT320&sexval=2'
 for page in range(1,8):
  url=base+(f'&page={page}' if page>1 else '')
  t=requests.get(url,timeout=30,headers={'User-Agent':'Mozilla/5.0'}).text
  found={int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',t)}
  before=len(regs); regs|=found
  if page>1 and len(regs)==before: break
 return regs

C=cards_long(load('programs/race_cards/*/*/*.csv'))
RR=load('results/realtime/*/*/*.csv'); R=result_long(RR)
for d in (C,R):
 d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat']); X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int)
fregs=female_regs_official(); X['sex']=np.where(X.reg.isin(fregs),'female','male')
# baseline by actual course
X['win']=(X.finish==1).astype(int); X['top2']=(X.finish<=2).astype(int); X['top3']=(X.finish<=3).astype(int)
score_map={1:10,2:8,3:6,4:4,5:2,6:1}; X['score']=X.finish.map(score_map)
base=X.groupby(['sex','course']).agg(n=('reg','size'),win=('win','mean'),top2=('top2','mean'),top3=('top3','mean'),score=('score','mean')).reset_index()
base.to_csv(OUT/'gender_course_baseline.csv',index=False)
# same-racer? sex effect isn't within racer; ability-matched via racer-course centered outcomes is impossible across sex. Produce grade-free descriptive + course only.
# Adjacent inner sex effect for male outer, ability adjusted both actors.
inner=X[['race','course','reg','sex','finish']].copy(); inner['course']=inner.course+1
inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish'})
Y=X.merge(inner,on=['race','course'],how='inner'); Y=Y[(Y.sex=='male')&(Y.course>=2)].copy()
Y['beats_inner']=(Y.finish<Y.inner_finish).astype(int); Y['male_win']=(Y.finish==1).astype(int); Y['male_top3']=(Y.finish<=3).astype(int); Y['inner_top3']=(Y.inner_finish<=3).astype(int)
for col in ['beats_inner','male_win','male_top3','inner_top3']:
 actor=Y.groupby(['reg','course'])[col].transform('mean')
 # inner baseline outcome from full X by inner reg and actual inner course = current course-1
 stat=X[['reg','course',col if col in X.columns else 'finish']].copy() if False else None
 Y[col+'_actor_resid']=Y[col]-actor
# expected inner top3 and expected actor beats proxy from each racers' historical finish distribution, course-specific
mean_finish=X.groupby(['reg','course']).finish.mean()
top3_rate=X.groupby(['reg','course']).top3.mean()
Y['inner_course']=Y.course-1
Y['inner_exp_top3']=[top3_rate.get((r,c),np.nan) for r,c in zip(Y.inner_reg,Y.inner_course)]
Y['actor_exp_top3']=[top3_rate.get((r,c),np.nan) for r,c in zip(Y.reg,Y.course)]
Y['inner_top3_adj']=Y.inner_top3-Y.inner_exp_top3
Y['male_top3_adj']=Y.male_top3-Y.actor_exp_top3
summary=[]
for s,g in Y.groupby('inner_sex'):
 summary.append({'inner_sex':s,'n':len(g),'beats_inner':g.beats_inner.mean(),'male_win':g.male_win.mean(),'male_top3':g.male_top3.mean(),'male_top3_adj':g.male_top3_adj.mean(),'inner_top3':g.inner_top3.mean(),'inner_top3_adj':g.inner_top3_adj.mean()})
pd.DataFrame(summary).to_csv(OUT/'adjacent_summary.csv',index=False)
# time split adjusted top3
hs=[]
for label,mask in [('early',Y.date<=pd.Timestamp('2026-06-30')),('late',Y.date>=pd.Timestamp('2026-07-01'))]:
 z=Y[mask]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
 if len(a)&len(b): hs.append({'period':label,'n_female_inner':len(a),'n_male_inner':len(b),'male_top3_adj_diff':a.male_top3_adj.mean()-b.male_top3_adj.mean(),'inner_top3_adj_diff':a.inner_top3_adj.mean()-b.inner_top3_adj.mean()})
pd.DataFrame(hs).to_csv(OUT/'adjacent_holdout.csv',index=False)
# Find winning method columns and race-level makuri. Usually winner method is race-level; identify any col containing 決まり手.
kcols=[c for c in RR.columns if '決まり手' in str(c)]
print('KIMARITE_COLS',kcols)
mk=[]
if kcols:
 kc=kcols[0]
 M=RR[['レースコード',kc]].rename(columns={'レースコード':'race',kc:'kimarite'}).copy(); M.race=M.race.astype(str)
 W=X[X.finish==1][['race','reg','sex','course']].merge(M,on='race',how='left')
 # winning makuri/makurisashi only tells when male outer actually wins that way.
 WI=Y[['race','reg','course','inner_sex']].drop_duplicates().merge(W[['race','reg','kimarite']],on=['race','reg'],how='left')
 WI['makuri_win']=WI.kimarite.astype(str).str.contains('まくり',na=False)&~WI.kimarite.astype(str).str.contains('差し',na=False)
 WI['makurisashi_win']=WI.kimarite.astype(str).str.contains('まくり差し',na=False)
 for c,g in WI.groupby(['course','inner_sex']):
  mk.append({'course':c[0],'inner_sex':c[1],'n':len(g),'makuri_win_rate':g.makuri_win.mean(),'makurisashi_win_rate':g.makurisashi_win.mean()})
pd.DataFrame(mk).to_csv(OUT/'makuri_win_by_inner_sex.csv',index=False)
print('OFFICIAL_FEMALE_REGS',len(fregs),'MATCHED_FEMALE_STARTS',(X.sex=='female').sum(),'TOTAL_STARTS',len(X))
print('\nBASELINE\n',base.to_string(index=False))
print('\nADJ\n',pd.DataFrame(summary).to_string(index=False))
print('\nHOLDOUT\n',pd.DataFrame(hs).to_string(index=False))
print('\nMAKURI_WIN\n',pd.DataFrame(mk).to_string(index=False) if mk else 'no kimarite cols')
print('NOTE: official female list is fetched from BOAT RACE racer search sex=2. Male is defined as active regs in our starts not in that official female list. Winning method only identifies successful winning tactic, not failed makuri attempts.')