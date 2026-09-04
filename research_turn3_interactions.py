#!/usr/bin/env python3
from pathlib import Path
import glob,re,requests
import numpy as np
import pandas as pd
SRC=Path('source/data'); OUT=Path('artifacts/research_turn3'); OUT.mkdir(parents=True,exist_ok=True)

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
  a=f'{k}着_艇番'; b=f'{k}コース_艇番'
  if a in df.columns:
   q=df[['レースコード',a]].rename(columns={'レースコード':'race',a:'boat'}); q['finish']=k; fs.append(q)
  if b in df.columns:
   q=df[['レースコード',b]].rename(columns={'レースコード':'race',b:'boat'}); q['course']=k; cs.append(q)
 return pd.concat(fs,ignore_index=True).merge(pd.concat(cs,ignore_index=True),on=['race','boat'])

def female_regs():
 s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})
 u='https://www.boatrace.jp/owpc/pc/data/racersearch/result?prevpgid=TDAT320&sexval=2'
 t=s.get(u,timeout=30).text
 m=re.search(r'検索結果[^0-9]*([0-9]+)人',t); total=int(m.group(1)) if m else None
 regs=set()
 def add(h): regs.update(int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',h))
 add(t)
 for row in range(41,401,40):
  if total and row>total: break
  add(s.get(f'https://www.boatrace.jp/owpc/pc/data/racersearch/result?orteusPageSelectBeginRow={row}',timeout=30).text)
 if total and len(regs)<int(total*.9): raise RuntimeError(f'female list incomplete {len(regs)}/{total}')
 return regs,total

C=cards_long(load('programs/race_cards/*/*/*.csv')); RR=load('results/realtime/*/*/*.csv'); R=result_long(RR)
for d in (C,R): d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat']); X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int)
X['win']=(X.finish==1).astype(int); X['top3']=(X.finish<=3).astype(int)
fregs,total=female_regs(); X['sex']=np.where(X.reg.isin(fregs),'female','male')

# leakage-safe baselines: learn only through June, test July+August
learn=X[X.date<=pd.Timestamp('2026-06-30')].copy(); test=X[X.date>=pd.Timestamp('2026-07-01')].copy()
# racer-course expected top3/win learned in early period
rt=learn.groupby(['reg','course']).agg(win_rate=('win','mean'),top3_rate=('top3','mean'),n=('reg','size')).reset_index()
winmap={(int(r.reg),int(r.course)):r.win_rate for _,r in rt.iterrows()}; t3map={(int(r.reg),int(r.course)):r.top3_rate for _,r in rt.iterrows()}

# adjacent rows
inner=test[['race','date','course','reg','sex','finish','top3']].copy(); inner['course']=inner.course+1
inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish','top3':'inner_top3'})
Y=test.merge(inner,on=['race','date','course']); Y=Y[(Y.sex=='male')&(Y.course>=2)].copy(); Y['inner_course']=Y.course-1
Y['actor_exp']=[t3map.get((r,int(c)),np.nan) for r,c in zip(Y.reg,Y.course)]; Y['inner_exp']=[t3map.get((r,int(c)),np.nan) for r,c in zip(Y.inner_reg,Y.inner_course)]
Y['actor_adj']=Y.top3-Y.actor_exp; Y['inner_adj']=Y.inner_top3-Y.inner_exp; Y['beats_inner']=(Y.finish<Y.inner_finish).astype(int)

rows=[]
for s,g in Y.groupby('inner_sex'):
 rows.append({'theme':'female_adjacent','group':s,'n':len(g),'actor_top3':g.top3.mean(),'actor_adj':g.actor_adj.mean(),'inner_top3':g.inner_top3.mean(),'inner_adj':g.inner_adj.mean(),'beats_inner':g.beats_inner.mean()})

# reproducibility July vs Aug
hold=[]
for label,start,end in [('jul','2026-07-01','2026-07-31'),('aug','2026-08-01','2026-08-31')]:
 z=Y[(Y.date>=start)&(Y.date<=end)]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
 if len(a) and len(b): hold.append({'theme':'female_adjacent','period':label,'n_case':len(a),'n_base':len(b),'actor_adj_diff':a.actor_adj.mean()-b.actor_adj.mean(),'inner_adj_diff':a.inner_adj.mean()-b.inner_adj.mean()})

# theme2 third boat directly outside: female -> male -> third. effect on third top3 and top3 composition
third=test[['race','date','course','reg','top3','finish']].copy(); third['course']=third.course-1
third=third.rename(columns={'reg':'third_reg','top3':'third_top3','finish':'third_finish'})
T=Y.merge(third,on=['race','date','course']); T=T[T.course<=5].copy()
T['third_course']=T.course+1; T['third_exp']=[t3map.get((r,int(c)),np.nan) for r,c in zip(T.third_reg,T.third_course)]; T['third_adj']=T.third_top3-T.third_exp
T['outer2_top3']=((T.top3==1)&(T.third_top3==1)).astype(int); T['inner_out_outer2_in']=((T.inner_top3==0)&(T.top3==1)&(T.third_top3==1)).astype(int)
for s,g in T.groupby('inner_sex'):
 rows.append({'theme':'third_boat_supply','group':s,'n':len(g),'actor_top3':g.top3.mean(),'third_top3':g.third_top3.mean(),'third_adj':g.third_adj.mean(),'outer2_top3':g.outer2_top3.mean(),'inner_out_outer2_in':g.inner_out_outer2_in.mean()})
for label,start,end in [('jul','2026-07-01','2026-07-31'),('aug','2026-08-01','2026-08-31')]:
 z=T[(T.date>=start)&(T.date<=end)]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
 if len(a) and len(b): hold.append({'theme':'third_boat_supply','period':label,'n_case':len(a),'n_base':len(b),'third_adj_diff':a.third_adj.mean()-b.third_adj.mean(),'outer2_top3_diff':a.outer2_top3.mean()-b.outer2_top3.mean(),'inner_out_outer2_in_diff':a.inner_out_outer2_in.mean()-b.inner_out_outer2_in.mean()})

# theme3 successful makuri, using winning method
kcols=[c for c in RR.columns if '決まり手' in str(c)]
if kcols:
 M=RR[['レースコード',kcols[0]]].rename(columns={'レースコード':'race',kcols[0]:'kimarite'}); M.race=M.race.astype(str)
 Z=Y[['race','date','course','reg','inner_sex']].drop_duplicates().merge(test[test.finish==1][['race','reg']],on=['race','reg'],how='left',indicator='won').merge(M,on='race',how='left')
 ks=Z.kimarite.astype(str); Z['makuri']=((Z.won=='both')&ks.str.contains('まくり',na=False)&~ks.str.contains('差し',na=False)).astype(int)
 for (c,s),g in Z.groupby(['course','inner_sex']): rows.append({'theme':'successful_makuri','group':f'c{int(c)}_{s}','n':len(g),'makuri_rate':g.makuri.mean()})
 for label,start,end in [('jul','2026-07-01','2026-07-31'),('aug','2026-08-01','2026-08-31')]:
  q=Z[(Z.date>=start)&(Z.date<=end)]
  for c in [2,3,4,5,6]:
   a=q[(q.course==c)&(q.inner_sex=='female')]; b=q[(q.course==c)&(q.inner_sex=='male')]
   if len(a) and len(b): hold.append({'theme':'successful_makuri','period':label,'course':c,'n_case':len(a),'n_base':len(b),'makuri_diff':a.makuri.mean()-b.makuri.mean()})

# themes4/5 weakness hunting: learned racer-course quintiles through June, tested Jul+Aug
# C1 vulnerability = low win rate in C1 among racers with >=12 starts; attackers c2/c3 high win rate with >=12 starts
r1=rt[(rt.course==1)&(rt.n>=12)]; q1=r1.win_rate.quantile(.2); vulnerable=set(r1[r1.win_rate<=q1].reg.astype(int))
for ac in [2,3]:
 ra=rt[(rt.course==ac)&(rt.n>=12)]; qa=ra.win_rate.quantile(.8); attackers=set(ra[ra.win_rate>=qa].reg.astype(int))
 # create race course table
 c1=test[test.course==1][['race','date','reg','finish']].rename(columns={'reg':'r1','finish':'f1'})
 aa=test[test.course==ac][['race','date','reg','finish','win']].rename(columns={'reg':'ra','finish':'fa','win':'awin'})
 P=c1.merge(aa,on=['race','date']); P['case']=P.r1.isin(vulnerable)&P.ra.isin(attackers); P['attacker_beats_1']=(P.fa<P.f1).astype(int)
 # comparison: same attacker type vs non-vulnerable C1, preserves strong attacker
 B=P[P.ra.isin(attackers)].copy(); a=B[B.case]; b=B[~B.r1.isin(vulnerable)]
 rows.append({'theme':f'weakness_hunt_c{ac}','group':'case','n':len(a),'attacker_win':a.awin.mean(),'beats1':a.attacker_beats_1.mean()})
 rows.append({'theme':f'weakness_hunt_c{ac}','group':'base','n':len(b),'attacker_win':b.awin.mean(),'beats1':b.attacker_beats_1.mean()})
 for label,start,end in [('jul','2026-07-01','2026-07-31'),('aug','2026-08-01','2026-08-31')]:
  z=B[(B.date>=start)&(B.date<=end)]; a=z[z.r1.isin(vulnerable)]; b=z[~z.r1.isin(vulnerable)]
  if len(a) and len(b): hold.append({'theme':f'weakness_hunt_c{ac}','period':label,'n_case':len(a),'n_base':len(b),'attacker_win_diff':a.awin.mean()-b.awin.mean(),'beats1_diff':a.attacker_beats_1.mean()-b.attacker_beats_1.mean()})

pd.DataFrame(rows).to_csv(OUT/'themes.csv',index=False); pd.DataFrame(hold).to_csv(OUT/'holdout.csv',index=False)
print('official female total',total,'scraped',len(fregs),'starts',len(X),'test starts',len(test))
print(pd.DataFrame(rows).to_string(index=False)); print('\nHOLDOUT\n',pd.DataFrame(hold).to_string(index=False))
print('\nNOTE: successful_makuri counts only winning makuri, not failed attempts. Baselines learned only through June; July/Aug are later-period checks.')