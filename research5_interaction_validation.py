#!/usr/bin/env python3
from pathlib import Path
import glob,re,requests
import numpy as np
import pandas as pd
SRC=Path('source/data'); OUT=Path('artifacts/research5'); OUT.mkdir(parents=True,exist_ok=True)

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
  namec=next((c for c in [f'艇{b}_選手名',f'艇{b}_名前',f'{b}号艇_選手名'] if c in df.columns),None)
  if all(c in df.columns for c in mp):
   use=list(mp)+( [namec] if namec else [] ); q=df[use].rename(columns=mp).copy(); q['boat']=b
   q['name']=q[namec] if namec else ''
   if namec: q=q.drop(columns=[namec])
   out.append(q)
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
 regs=set(int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',t))
 for row in range(41,401,40):
  if total and row>total: break
  h=s.get(f'https://www.boatrace.jp/owpc/pc/data/racersearch/result?orteusPageSelectBeginRow={row}',timeout=30).text
  regs.update(int(x) for x in re.findall(r'(?<!\d)(3\d{3}|4\d{3}|5\d{3})(?!\d)',h))
 if total and len(regs)<int(total*.9): raise RuntimeError(f'female list incomplete {len(regs)}/{total}')
 return regs,total

C=cards_long(load('programs/race_cards/*/*/*.csv')); RR=load('results/realtime/*/*/*.csv'); R=result_long(RR)
for d in (C,R): d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat']); X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int); X['top3']=(X.finish<=3).astype(int); X['win']=(X.finish==1).astype(int)
fregs,total=female_regs(); X['sex']=np.where(X.reg.isin(fregs),'female','male')
TRAIN=X[X.date<=pd.Timestamp('2026-06-30')].copy(); TEST=X[X.date>=pd.Timestamp('2026-07-01')].copy()
name_map=X.sort_values('date').groupby('reg').name.last().to_dict()
base=TRAIN.groupby(['reg','course']).agg(n=('top3','size'),t3=('top3','mean'),win=('win','mean')).reset_index(); base=base[base.n>=10]
t3={(int(r.reg),int(r.course)):r.t3 for _,r in base.iterrows()}; winmap={(int(r.reg),int(r.course)):r.win for _,r in base.iterrows()}
rows=[]; players=[]

# adjacent: male actor immediately outside; examine inner female by actor course 2/3/4 and all.
inner=TEST[['race','date','course','reg','sex','finish','top3']].copy(); inner['course']=inner.course+1
inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish','top3':'inner_top3'})
Y=TEST.merge(inner,on=['race','date','course']); Y=Y[(Y.sex=='male')&(Y.course>=2)].copy(); Y['inner_course']=Y.course-1
Y['actor_exp']=[t3.get((r,int(c)),np.nan) for r,c in zip(Y.reg,Y.course)]; Y['inner_exp']=[t3.get((r,int(c)),np.nan) for r,c in zip(Y.inner_reg,Y.inner_course)]
Y=Y.dropna(subset=['actor_exp','inner_exp']); Y['actor_resid']=Y.top3-Y.actor_exp; Y['inner_resid']=Y.inner_top3-Y.inner_exp
for label,sel in [('女子内→外男子残り_全体',Y.course>=2),('女子内→外男子残り_C2',Y.course==2),('女子内→外男子残り_C3',Y.course==3),('女子内→外男子残り_C4',Y.course==4)]:
 z=Y[sel]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
 if len(a) and len(b):
  rows.append({'theme':label,'period':'all','n_case':len(a),'n_base':len(b),'raw_case':a.top3.mean(),'raw_base':b.top3.mean(),'adjusted':a.actor_resid.mean()-b.actor_resid.mean(),'inner_adjusted':a.inner_resid.mean()-b.inner_resid.mean()})
  for per,mask in [('jul',z.date.dt.month==7),('aug',z.date.dt.month==8)]:
   q=z[mask]; aa=q[q.inner_sex=='female']; bb=q[q.inner_sex=='male']
   if len(aa) and len(bb): rows.append({'theme':label,'period':per,'n_case':len(aa),'n_base':len(bb),'raw_case':aa.top3.mean(),'raw_base':bb.top3.mean(),'adjusted':aa.actor_resid.mean()-bb.actor_resid.mean(),'inner_adjusted':aa.inner_resid.mean()-bb.inner_resid.mean()})

# three-boat composition, adjusted against each racer's own TRAIN top3 probability.
A=TEST[['race','date','course','reg','sex','top3']].copy(); B=A.rename(columns={'course':'c2','reg':'reg2','sex':'sex2','top3':'top32'}); C3=A.rename(columns={'course':'c3','reg':'reg3','sex':'sex3','top3':'top33'})
Z=A.merge(B,on=['race','date']); Z=Z[Z.c2==Z.course+1]; Z=Z.merge(C3,on=['race','date']); Z=Z[Z.c3==Z.course+2]; Z=Z[(Z.sex2=='male')&(Z.course<=4)].copy()
Z['pattern']=((Z.top3==0)&(Z.top32==1)&(Z.top33==1)).astype(int)
Z['p1']=[t3.get((r,int(c)),np.nan) for r,c in zip(Z.reg,Z.course)]; Z['p2']=[t3.get((r,int(c)),np.nan) for r,c in zip(Z.reg2,Z.c2)]; Z['p3']=[t3.get((r,int(c)),np.nan) for r,c in zip(Z.reg3,Z.c3)]
Z=Z.dropna(subset=['p1','p2','p3']); Z['pattern_exp']=(1-Z.p1)*Z.p2*Z.p3; Z['pattern_resid']=Z.pattern-Z.pattern_exp
for per,mask in [('all',np.ones(len(Z),dtype=bool)),('jul',Z.date.dt.month==7),('aug',Z.date.dt.month==8)]:
 q=Z[mask]; a=q[q.sex=='female']; b=q[q.sex=='male']
 if len(a) and len(b): rows.append({'theme':'内崩れ→外2艇残り_3者補正','period':per,'n_case':len(a),'n_base':len(b),'raw_case':a.pattern.mean(),'raw_base':b.pattern.mean(),'adjusted':a.pattern_resid.mean()-b.pattern_resid.mean(),'inner_adjusted':np.nan})

# player cards for female-inner adjacency, >=12 test cases and both Jul/Aug present.
for reg,g in Y[Y.inner_sex=='female'].groupby('reg'):
 if len(g)>=12 and (g.date.dt.month==7).any() and (g.date.dt.month==8).any():
  players.append({'theme':'女子内→外男子残り','reg':int(reg),'name':name_map.get(reg,''),'n':len(g),'raw':g.top3.mean(),'expected':g.actor_exp.mean(),'adjusted':g.actor_resid.mean(),'jul_n':int((g.date.dt.month==7).sum()),'jul_raw':g[g.date.dt.month==7].top3.mean(),'aug_n':int((g.date.dt.month==8).sum()),'aug_raw':g[g.date.dt.month==8].top3.mean()})

#恩返し observable: donor won from 2-5 and outside beneficiary top3, then remeet adjacent within 180d.
benef=[]
for race,g in X.groupby('race'):
 m={int(r.course):r for _,r in g.iterrows()}; w=g[g.finish.eq(1)]
 if len(w)!=1: continue
 a=w.iloc[0]; c=int(a.course)
 if 2<=c<=5 and c+1 in m and int(m[c+1].finish)<=3:
  benef.append({'date':a.date,'donor':int(a.reg),'beneficiary':int(m[c+1].reg)})
E=pd.DataFrame(benef)
meet=[]
for race,g in X.groupby('race'):
 m={int(r.course):r for _,r in g.iterrows()}
 for c in range(1,6):
  if c in m and c+1 in m:
   a,b=m[c],m[c+1]; meet.append({'date':a.date,'donor':int(a.reg),'beneficiary':int(b.reg),'ic':c,'oc':c+1,'outer_beats':int(b.finish<a.finish),'inner_top3':int(a.finish<=3)})
M=pd.DataFrame(meet).sort_values('date'); pair_dates={k:list(v.date.sort_values()) for k,v in E.groupby(['donor','beneficiary'])}; M['after']=0
for i,r in M.iterrows():
 ds=pair_dates.get((r.donor,r.beneficiary),[]); prev=[d for d in ds if d<r.date]
 if prev and 1<=(r.date-prev[-1]).days<=180: M.at[i,'after']=1
# use TRAIN-only person/course baselines, test Jul+ for clean check
mt=M[M.date<=pd.Timestamp('2026-06-30')]; mb=mt.groupby(['beneficiary','oc']).outer_beats.mean().to_dict(); ma=mt.groupby(['donor','ic']).inner_top3.mean().to_dict(); mv=M[M.date>=pd.Timestamp('2026-07-01')].copy(); mv['be']=[mb.get((r,int(c)),np.nan) for r,c in zip(mv.beneficiary,mv.oc)]; mv['ie']=[ma.get((r,int(c)),np.nan) for r,c in zip(mv.donor,mv.ic)]; mv=mv.dropna(subset=['be','ie']); mv['br']=mv.outer_beats-mv.be; mv['ir']=mv.inner_top3-mv.ie
for per,mask in [('all',np.ones(len(mv),dtype=bool)),('jul',mv.date.dt.month==7),('aug',mv.date.dt.month==8)]:
 q=mv[mask]; a=q[q.after==1]; b=q[q.after==0]
 if len(a) and len(b): rows.append({'theme':'恩返し行動候補','period':per,'n_case':len(a),'n_base':len(b),'raw_case':a.outer_beats.mean(),'raw_base':b.outer_beats.mean(),'adjusted':a.br.mean()-b.br.mean(),'inner_adjusted':a.ir.mean()-b.ir.mean()})

S=pd.DataFrame(rows); P=pd.DataFrame(players)
S.to_csv(OUT/'summary.csv',index=False); P.to_csv(OUT/'player_cards.csv',index=False)
print('STARTS',len(X),'TRAIN',len(TRAIN),'TEST',len(TEST),'FEMALE_TOTAL',total,'SCRAPED',len(fregs))
print('\nSUMMARY\n',S.to_string(index=False))
print('\nPLAYERS\n',P.sort_values('adjusted',ascending=False).head(40).to_string(index=False) if len(P) else 'none')
print('\nNOTE adjusted uses only training-period racer/course baselines. Three-boat expected pattern approximates three independent top3 probabilities; use only as a conservative diagnostic, not a final causal model.')