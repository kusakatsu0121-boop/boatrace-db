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
 return pd.concat(fs,ignore_index=True).merge(pd.concat(cs,ignore_index=True),on=['race','boat'])

def female_regs_official():
 s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})
 first='https://www.boatrace.jp/owpc/pc/data/racersearch/result?prevpgid=TDAT320&sexval=2'
 t=s.get(first,timeout=30).text
 totalm=re.search(r'検索結果[^0-9]*([0-9]+)人',t)
 total=int(totalm.group(1)) if totalm else None
 regs=set()
 def add(html):
  regs.update(int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',html))
 add(t)
 for row in range(41,401,40):
  if total and row>total: break
  u=f'https://www.boatrace.jp/owpc/pc/data/racersearch/result?orteusPageSelectBeginRow={row}'
  add(s.get(u,timeout=30).text)
 if total and len(regs)<int(total*0.9):
  raise RuntimeError(f'female list incomplete: got {len(regs)} / official total {total}')
 return regs,total

C=cards_long(load('programs/race_cards/*/*/*.csv'))
RR=load('results/realtime/*/*/*.csv'); R=result_long(RR)
for d in (C,R): d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat']); X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int)
fregs,official_total=female_regs_official(); X['sex']=np.where(X.reg.isin(fregs),'female','male')
X['win']=(X.finish==1).astype(int); X['top2']=(X.finish<=2).astype(int); X['top3']=(X.finish<=3).astype(int)
X['score']=X.finish.map({1:10,2:8,3:6,4:4,5:2,6:1})
base=X.groupby(['sex','course']).agg(n=('reg','size'),win=('win','mean'),top2=('top2','mean'),top3=('top3','mean'),score=('score','mean')).reset_index(); base.to_csv(OUT/'gender_course_baseline.csv',index=False)
inner=X[['race','course','reg','sex','finish']].copy(); inner['course']=inner.course+1; inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish'})
Y=X.merge(inner,on=['race','course'],how='inner'); Y=Y[(Y.sex=='male')&(Y.course>=2)].copy()
Y['beats_inner']=(Y.finish<Y.inner_finish).astype(int); Y['male_win']=(Y.finish==1).astype(int); Y['male_top3']=(Y.finish<=3).astype(int); Y['inner_top3']=(Y.inner_finish<=3).astype(int)
top3_rate=X.groupby(['reg','course']).top3.mean(); Y['inner_course']=Y.course-1
Y['inner_exp_top3']=[top3_rate.get((r,c),np.nan) for r,c in zip(Y.inner_reg,Y.inner_course)]
Y['actor_exp_top3']=[top3_rate.get((r,c),np.nan) for r,c in zip(Y.reg,Y.course)]
Y['inner_top3_adj']=Y.inner_top3-Y.inner_exp_top3; Y['male_top3_adj']=Y.male_top3-Y.actor_exp_top3
sm=[]
for s,g in Y.groupby('inner_sex'):
 sm.append({'inner_sex':s,'n':len(g),'beats_inner':g.beats_inner.mean(),'male_win':g.male_win.mean(),'male_top3':g.male_top3.mean(),'male_top3_adj':g.male_top3_adj.mean(),'inner_top3':g.inner_top3.mean(),'inner_top3_adj':g.inner_top3_adj.mean()})
pd.DataFrame(sm).to_csv(OUT/'adjacent_summary.csv',index=False)
hs=[]
for label,mask in [('early',Y.date<=pd.Timestamp('2026-06-30')),('late',Y.date>=pd.Timestamp('2026-07-01'))]:
 z=Y[mask]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
 if len(a) and len(b): hs.append({'period':label,'n_female_inner':len(a),'n_male_inner':len(b),'male_top3_adj_diff':a.male_top3_adj.mean()-b.male_top3_adj.mean(),'inner_top3_adj_diff':a.inner_top3_adj.mean()-b.inner_top3_adj.mean()})
pd.DataFrame(hs).to_csv(OUT/'adjacent_holdout.csv',index=False)
kcols=[c for c in RR.columns if '決まり手' in str(c)]; mk=[]; mh=[]
if kcols:
 M=RR[['レースコード',kcols[0]]].rename(columns={'レースコード':'race',kcols[0]:'kimarite'}).copy(); M.race=M.race.astype(str)
 W=X[X.finish==1][['race','reg']].merge(M,on='race',how='left')
 WI=Y[['race','date','reg','course','inner_sex']].drop_duplicates().merge(W,on=['race','reg'],how='left')
 ks=WI.kimarite.astype(str); WI['makuri_win']=(ks.str.contains('まくり',na=False)&~ks.str.contains('差し',na=False)).astype(int); WI['makurisashi_win']=ks.str.contains('まくり差し',na=False).astype(int)
 for (c,s),g in WI.groupby(['course','inner_sex']): mk.append({'course':c,'inner_sex':s,'n':len(g),'makuri_win_rate':g.makuri_win.mean(),'makurisashi_win_rate':g.makurisashi_win.mean()})
 for label,mask in [('early',WI.date<=pd.Timestamp('2026-06-30')),('late',WI.date>=pd.Timestamp('2026-07-01'))]:
  z=WI[mask]
  for c in [2,3,4,5,6]:
   a=z[(z.course==c)&(z.inner_sex=='female')]; b=z[(z.course==c)&(z.inner_sex=='male')]
   if len(a) and len(b): mh.append({'period':label,'course':c,'n_female_inner':len(a),'n_male_inner':len(b),'makuri_diff':a.makuri_win.mean()-b.makuri_win.mean(),'makurisashi_diff':a.makurisashi_win.mean()-b.makurisashi_win.mean()})
pd.DataFrame(mk).to_csv(OUT/'makuri_win_by_inner_sex.csv',index=False); pd.DataFrame(mh).to_csv(OUT/'makuri_holdout.csv',index=False)
print('OFFICIAL_TOTAL',official_total,'SCRAPED_REGS',len(fregs),'MATCHED_FEMALE_STARTS',(X.sex=='female').sum(),'TOTAL_STARTS',len(X))
print('\nBASELINE\n',base.to_string(index=False)); print('\nADJ\n',pd.DataFrame(sm).to_string(index=False)); print('\nHOLDOUT\n',pd.DataFrame(hs).to_string(index=False)); print('\nMAKURI\n',pd.DataFrame(mk).to_string(index=False)); print('\nMAKURI_HOLDOUT\n',pd.DataFrame(mh).to_string(index=False))
print('NOTE winning method detects successful winning tactic only, not failed makuri attempts.')