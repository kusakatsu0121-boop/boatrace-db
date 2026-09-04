#!/usr/bin/env python3
from pathlib import Path
import glob,re,requests
import numpy as np
import pandas as pd
SRC=Path('source/data'); OUT=Path('artifacts/research4'); OUT.mkdir(parents=True,exist_ok=True)

def load(p):
 xs=[]
 for f in sorted(glob.glob(str(SRC/p))):
  try: xs.append(pd.read_csv(f,low_memory=False))
  except: pass
 return pd.concat(xs,ignore_index=True) if xs else pd.DataFrame()

def cards_long(df):
 out=[]
 for b in range(1,7):
  cols={'レースコード':'race','レース日':'date',f'艇{b}_登録番号':'reg'}
  namec=next((c for c in [f'艇{b}_選手名',f'艇{b}_名前',f'{b}号艇_選手名'] if c in df.columns),None)
  use=list(cols)
  if namec: use.append(namec)
  if all(c in df.columns for c in cols):
   q=df[use].rename(columns=cols).copy(); q['boat']=b
   if namec: q=q.rename(columns={namec:'name'})
   else: q['name']=''
   out.append(q)
 return pd.concat(out,ignore_index=True)

def results_long(df):
 fs=[]; cs=[]
 for k in range(1,7):
  fc=f'{k}着_艇番'; cc=f'{k}コース_艇番'
  if fc in df.columns:
   q=df[['レースコード',fc]].rename(columns={'レースコード':'race',fc:'boat'}); q['finish']=k; fs.append(q)
  if cc in df.columns:
   q=df[['レースコード',cc]].rename(columns={'レースコード':'race',cc:'boat'}); q['course']=k; cs.append(q)
 return pd.concat(fs,ignore_index=True).merge(pd.concat(cs,ignore_index=True),on=['race','boat'])

def female_regs_official():
 s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0'})
 u='https://www.boatrace.jp/owpc/pc/data/racersearch/result?prevpgid=TDAT320&sexval=2'
 t=s.get(u,timeout=30).text
 m=re.search(r'検索結果[^0-9]*([0-9]+)人',t); total=int(m.group(1)) if m else None
 regs=set(int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',t))
 for row in range(41,401,40):
  if total and row>total: break
  h=s.get(f'https://www.boatrace.jp/owpc/pc/data/racersearch/result?orteusPageSelectBeginRow={row}',timeout=30).text
  regs.update(int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',h))
 if total and len(regs)<int(total*.9): raise RuntimeError(f'female list incomplete {len(regs)}/{total}')
 return regs,total

C=cards_long(load('programs/race_cards/*/*/*.csv')); RR=load('results/realtime/*/*/*.csv'); R=results_long(RR)
for d in [C,R]: d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat']); X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int); X['win']=(X.finish==1).astype(int); X['top3']=(X.finish<=3).astype(int)
fregs,total=female_regs_official(); X['sex']=np.where(X.reg.isin(fregs),'female','male')
TRAIN=X[X.date<=pd.Timestamp('2026-06-30')].copy(); VAL=X[X.date>=pd.Timestamp('2026-07-01')].copy()
name_map=X.sort_values('date').groupby('reg').name.last().to_dict()

def race_course_table(df): return df.pivot_table(index='race',columns='course',values=['reg','finish','sex'],aggfunc='first')
T=race_course_table(TRAIN); V=race_course_table(VAL)
rows=[]
# Weakness hunters C2/C3: training actor strength + C1 vulnerability, validate July/Aug.
def weak_hunter(course):
 tr=TRAIN[TRAIN.course==course]; glob=tr.win.mean(); actor=tr.groupby('reg').agg(n=('win','size'),rate=('win','mean')); actor=actor[actor.n>=20]
 # c1 vulnerability to this course: join races
 rr=TRAIN[['race','course','reg','win']].copy(); c1=rr[rr.course==1][['race','reg']].rename(columns={'reg':'c1reg'}); atk=rr[rr.course==course][['race','reg','win']].rename(columns={'reg':'areg'})
 pair=c1.merge(atk,on='race'); vuln=pair.groupby('c1reg').agg(n=('win','size'),rate=('win','mean')); vuln=vuln[vuln.n>=20]
 aq=actor.rate.quantile(.8); vq=vuln.rate.quantile(.8); strong=set(actor[actor.rate>=aq].index); weak=set(vuln[vuln.rate>=vq].index)
 vv=VAL[['race','date','course','reg','win']]; c1v=vv[vv.course==1][['race','reg']].rename(columns={'reg':'c1reg'}); av=vv[vv.course==course][['race','date','reg','win']].rename(columns={'reg':'areg'}); z=c1v.merge(av,on='race')
 z['cond']=z.areg.isin(strong)&z.c1reg.isin(weak)
 ar=actor.rate.to_dict(); vr=vuln.rate.to_dict(); z['expected']=[np.clip(glob+(ar.get(a,glob)-glob)+(vr.get(i,glob)-glob),.01,.99) for a,i in zip(z.areg,z.c1reg)]; z['resid']=z.win-z.expected
 for per,mask in [('all',np.ones(len(z),dtype=bool)),('jul',z.date.dt.month==7),('aug',z.date.dt.month==8)]:
  g=z[mask & z.cond]; b=z[mask & ~z.cond]
  if len(g): rows.append({'theme':f'C{course}弱点狩り','period':per,'n':len(g),'raw':g.win.mean(),'baseline':b.win.mean(),'diff':g.win.mean()-b.win.mean(),'adjusted':g.resid.mean()})
 # player candidates among strong actors when facing weak c1
 pc=[]
 for reg,g in z[z.cond].groupby('areg'):
  if len(g)>=5: pc.append({'theme':f'C{course}弱点狩り','reg':int(reg),'name':name_map.get(reg,''),'n':len(g),'win':g.win.mean(),'expected':g.expected.mean(),'adjusted':g.resid.mean(),'jul_n':sum(g.date.dt.month==7),'jul_win':g[g.date.dt.month==7].win.mean() if sum(g.date.dt.month==7) else np.nan,'aug_n':sum(g.date.dt.month==8),'aug_win':g[g.date.dt.month==8].win.mean() if sum(g.date.dt.month==8) else np.nan})
 return pd.DataFrame(pc)
pcs=[weak_hunter(2),weak_hunter(3)]
# Gender adjacency using TRAIN baselines only
base_top3=TRAIN.groupby(['reg','course']).agg(n=('top3','size'),rate=('top3','mean')); base_top3=base_top3[base_top3.n>=10].rate.to_dict()
inner=VAL[['race','date','course','reg','sex','finish','top3']].copy(); inner['course']=inner.course+1; inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish','top3':'inner_top3'})
Y=VAL.merge(inner,on=['race','date','course'],suffixes=('','_x')); Y=Y[(Y.sex=='male')&(Y.course>=2)].copy(); Y['actor_exp']=[base_top3.get((r,c),np.nan) for r,c in zip(Y.reg,Y.course)]; Y['inner_exp']=[base_top3.get((r,c-1),np.nan) for r,c in zip(Y.inner_reg,Y.course)]; Y=Y.dropna(subset=['actor_exp','inner_exp']); Y['actor_resid']=Y.top3-Y.actor_exp; Y['inner_resid']=Y.inner_top3-Y.inner_exp
for per,mask in [('all',np.ones(len(Y),dtype=bool)),('jul',Y.date.dt.month==7),('aug',Y.date.dt.month==8)]:
 z=Y[mask]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
 if len(a):
  rows.append({'theme':'女子内→外男子残り','period':per,'n':len(a),'raw':a.top3.mean(),'baseline':b.top3.mean(),'diff':a.top3.mean()-b.top3.mean(),'adjusted':a.actor_resid.mean()-b.actor_resid.mean()})
  rows.append({'theme':'女子内の崩れ','period':per,'n':len(a),'raw':a.inner_top3.mean(),'baseline':b.inner_top3.mean(),'diff':a.inner_top3.mean()-b.inner_top3.mean(),'adjusted':a.inner_resid.mean()-b.inner_resid.mean()})
# Three-boat composition: inner female, male immediately outside, one more outside
A=VAL[['race','date','course','reg','sex','top3']].copy(); B=A.rename(columns={'course':'c2','reg':'reg2','sex':'sex2','top3':'top32'}); C3=A.rename(columns={'course':'c3','reg':'reg3','sex':'sex3','top3':'top33'})
Z=A.merge(B,on=['race','date']); Z=Z[Z.c2==Z.course+1]; Z=Z.merge(C3,on=['race','date']); Z=Z[Z.c3==Z.course+2]; Z=Z[(Z.sex2=='male') & (Z.course<=4)].copy(); Z['pattern']=((Z.top3==0)&(Z.top32==1)&(Z.top33==1)).astype(int)
# baseline pattern by inner sex raw + month
for per,mask in [('all',np.ones(len(Z),dtype=bool)),('jul',Z.date.dt.month==7),('aug',Z.date.dt.month==8)]:
 z=Z[mask]; a=z[z.sex=='female']; b=z[z.sex=='male']
 if len(a): rows.append({'theme':'内崩れ→外2艇残り','period':per,'n':len(a),'raw':a.pattern.mean(),'baseline':b.pattern.mean(),'diff':a.pattern.mean()-b.pattern.mean(),'adjusted':np.nan})
# player gender-adjacency candidates; require 8 val cases
pcg=[]
for reg,g in Y[Y.inner_sex=='female'].groupby('reg'):
 if len(g)>=8:
  pcg.append({'theme':'女子内→外男子残り','reg':int(reg),'name':name_map.get(reg,''),'n':len(g),'win':g.top3.mean(),'expected':g.actor_exp.mean(),'adjusted':g.actor_resid.mean(),'jul_n':sum(g.date.dt.month==7),'jul_win':g[g.date.dt.month==7].top3.mean() if sum(g.date.dt.month==7) else np.nan,'aug_n':sum(g.date.dt.month==8),'aug_win':g[g.date.dt.month==8].top3.mean() if sum(g.date.dt.month==8) else np.nan})
pcs.append(pd.DataFrame(pcg))
S=pd.DataFrame(rows); P=pd.concat([p for p in pcs if len(p)],ignore_index=True) if any(len(p) for p in pcs) else pd.DataFrame()
S.to_csv(OUT/'summary.csv',index=False); P.to_csv(OUT/'player_candidates.csv',index=False)
print('TOTAL_STARTS',len(X),'TRAIN',len(TRAIN),'VAL',len(VAL),'OFFICIAL_FEMALE_TOTAL',total,'SCRAPED_FEMALE',len(fregs))
print('\nSUMMARY\n',S.to_string(index=False))
print('\nPLAYERS\n',P.sort_values(['theme','adjusted'],ascending=[True,False]).head(60).to_string(index=False) if len(P) else 'none')
print('\nNOTE adjusted = validation outcome minus training-period racer/course expectations; gender adjacency compares residuals female-inner vs male-inner. Three-boat pattern is raw comparison only.')
