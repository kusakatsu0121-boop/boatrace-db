#!/usr/bin/env python3
from pathlib import Path
import glob,re,requests,itertools,math
import numpy as np
import pandas as pd
SRC=Path('source/data'); OUT=Path('artifacts/research_round6'); OUT.mkdir(parents=True,exist_ok=True)

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
 u='https://www.boatrace.jp/owpc/pc/data/racersearch/result?prevpgid=TDAT320&sexval=2'
 t=s.get(u,timeout=30).text; totalm=re.search(r'検索結果[^0-9]*([0-9]+)人',t); total=int(totalm.group(1)) if totalm else None
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
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int); X['top3']=(X.finish<=3).astype(int); X['win']=(X.finish==1).astype(int)
fregs,official=female_regs_official(); X['sex']=np.where(X.reg.isin(fregs),'F','M')
train=X[X.date<=pd.Timestamp('2026-06-30')].copy(); test=X[X.date>=pd.Timestamp('2026-07-01')].copy()
# smoothed historic course baselines
G=train.groupby(['reg','course']).agg(n=('top3','size'),top3=('top3','mean'),win=('win','mean'),mean_finish=('finish','mean')).reset_index()
course_top3=train.groupby('course').top3.mean(); course_win=train.groupby('course').win.mean(); course_finish=train.groupby('course').finish.mean()
G['top3_s']=(G.top3*G.n+G.course.map(course_top3)*20)/(G.n+20); G['win_s']=(G.win*G.n+G.course.map(course_win)*20)/(G.n+20); G['finish_s']=(G.mean_finish*G.n+G.course.map(course_finish)*20)/(G.n+20)
lookup=G.set_index(['reg','course'])
def hist(reg,c,col,default):
 try:return float(lookup.loc[(int(reg),int(c)),col])
 except:return float(default.get(c,np.nan))

def adjacent(df):
 inner=df[['race','course','reg','sex','finish','top3']].copy(); inner['course']=inner.course+1
 inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish','top3':'inner_top3'})
 y=df.merge(inner,on=['race','course'],how='inner'); y=y[(y.sex=='M')&(y.course>=2)].copy()
 y['actor_exp']=[hist(r,c,'top3_s',course_top3) for r,c in zip(y.reg,y.course)]
 y['inner_exp']=[hist(r,c-1,'top3_s',course_top3) for r,c in zip(y.inner_reg,y.course)]
 y['actor_adj']=y.top3-y.actor_exp; y['inner_adj']=y.inner_top3-y.inner_exp
 return y
Y=adjacent(test)
rows=[]
# themes 1-3 exact adjacent course placements
for outer_c in [2,3,4]:
 z=Y[Y.course==outer_c]
 for label,mask in [('all',pd.Series(True,index=z.index)),('jul',z.date.dt.month==7),('aug',z.date.dt.month==8)]:
  q=z[mask]; a=q[q.inner_sex=='F']; b=q[q.inner_sex=='M']
  if len(a) and len(b): rows.append({'theme':f'{outer_c-1}F->{outer_c}M','period':label,'nF':len(a),'nM':len(b),'actor_raw_diff':a.top3.mean()-b.top3.mean(),'actor_adj_diff':a.actor_adj.mean()-b.actor_adj.mean(),'inner_raw_diff':a.inner_top3.mean()-b.inner_top3.mean(),'inner_adj_diff':a.inner_adj.mean()-b.inner_adj.mean()})
AD=pd.DataFrame(rows); AD.to_csv(OUT/'adjacent_course.csv',index=False)
# theme 4 triple: inner->middle male->outer one course farther
A=test[['race','date','course','reg','sex','top3','finish']].copy()
mid=A.rename(columns={'reg':'mid_reg','sex':'mid_sex','top3':'mid_top3','finish':'mid_finish'}); mid['course']=mid.course-1
out=A.rename(columns={'reg':'out_reg','sex':'out_sex','top3':'out_top3','finish':'out_finish'}); out['course']=out.course-2
T=A.merge(mid[['race','course','mid_reg','mid_sex','mid_top3','mid_finish']],on=['race','course']).merge(out[['race','course','out_reg','out_sex','out_top3','out_finish']],on=['race','course'])
T=T[(T.mid_sex=='M')&(T.course<=4)].copy(); T['event']=((T.top3==0)&(T.mid_top3==1)&(T.out_top3==1)).astype(int)
# expected event from historic individual course rates, independence approximation
T['p_in']=[hist(r,c,'top3_s',course_top3) for r,c in zip(T.reg,T.course)]
T['p_mid']=[hist(r,c+1,'top3_s',course_top3) for r,c in zip(T.mid_reg,T.course)]
T['p_out']=[hist(r,c+2,'top3_s',course_top3) for r,c in zip(T.out_reg,T.course)]
T['exp_event']=(1-T.p_in)*T.p_mid*T.p_out; T['adj_event']=T.event-T.exp_event
tr=[]
for label,mask in [('all',pd.Series(True,index=T.index)),('jul',T.date.dt.month==7),('aug',T.date.dt.month==8)]:
 q=T[mask]; f=q[q.sex=='F']; m=q[q.sex=='M']
 tr.append({'period':label,'nF':len(f),'nM':len(m),'rawF':f.event.mean(),'rawM':m.event.mean(),'raw_diff':f.event.mean()-m.event.mean(),'adjF':f.adj_event.mean(),'adjM':m.adj_event.mean(),'adj_diff':f.adj_event.mean()-m.adj_event.mean()})
TR=pd.DataFrame(tr); TR.to_csv(OUT/'triple_event.csv',index=False)
# theme 5 successful makuri check in Jul/Aug
kcols=[c for c in RR.columns if '決まり手' in str(c)]; MK=[]
if kcols:
 M=RR[['レースコード',kcols[0]]].rename(columns={'レースコード':'race',kcols[0]:'kimarite'}); M.race=M.race.astype(str)
 W=test[test.finish==1][['race','reg']].merge(M,on='race',how='left')
 Z=Y[['race','date','reg','course','inner_sex']].drop_duplicates().merge(W,on=['race','reg'],how='left'); ks=Z.kimarite.astype(str)
 Z['makuri']=(ks.str.contains('まくり',na=False)&~ks.str.contains('差し',na=False)).astype(int)
 for c in [2,3,4]:
  for label,mask in [('all',pd.Series(True,index=Z.index)),('jul',Z.date.dt.month==7),('aug',Z.date.dt.month==8)]:
   q=Z[(Z.course==c)&mask]; f=q[q.inner_sex=='F']; m=q[q.inner_sex=='M']
   MK.append({'course':c,'period':label,'nF':len(f),'nM':len(m),'F':f.makuri.mean(),'M':m.makuri.mean(),'diff':f.makuri.mean()-m.makuri.mean()})
MK=pd.DataFrame(MK); MK.to_csv(OUT/'makuri.csv',index=False)
# theme 6 venue dependence of strongest 2F->3M (race code first two digits before date assumption)
Z=Y[(Y.course==3)&(Y.inner_sex=='F')].copy(); Z['venue']=Z.race.astype(str).str[-4:-2] if False else Z.race.astype(str).str[8:10]
V=Z.groupby('venue').agg(n=('race','size'),actor_adj=('actor_adj','mean'),inner_adj=('inner_adj','mean')).reset_index(); V=V[V.n>=15].sort_values('n',ascending=False); V.to_csv(OUT/'venue_2F3M.csv',index=False)
# exact trifecta prediction: historical racer/course mean-finish scores; compare baseline vs a trained configuration effect
# estimate train effects using adjacent/triple relations in train with same historic estimates derived from train itself (descriptive training only)
YT=adjacent(train)
eff={}
for c in [2,3,4]:
 a=YT[(YT.course==c)&(YT.inner_sex=='F')]; b=YT[(YT.course==c)&(YT.inner_sex=='M')]
 if len(a) and len(b): eff[c]={'outer':float(a.actor_adj.mean()-b.actor_adj.mean()),'inner':float(a.inner_adj.mean()-b.inner_adj.mean())}
# convert baseline finish strength to positive score. apply modest multiplier derived from top3 diff, capped to avoid overfit
races=[]
for race,g in test.groupby('race'):
 if len(g)!=6: continue
 g=g.sort_values('course'); boats=g.boat.astype(int).tolist(); regs=g.reg.tolist(); sexes=g.sex.tolist(); courses=g.course.astype(int).tolist(); finishes=dict(zip(g.boat.astype(int),g.finish.astype(int)))
 base=np.array([math.exp(-0.55*hist(r,c,'finish_s',course_finish)) for r,c in zip(regs,courses)],float); adj=base.copy()
 for j in range(1,6):
  if sexes[j]=='M' and sexes[j-1]=='F' and courses[j] in eff:
   e=eff[courses[j]]; adj[j]*=max(.65,min(1.35,1+e['outer'])); adj[j-1]*=max(.65,min(1.35,1+e['inner']))
 def perm_prob(scores,perm_idx):
  rem=list(range(6)); p=1.0
  for idx in perm_idx[:3]:
   den=sum(scores[k] for k in rem); p*=scores[idx]/den; rem.remove(idx)
  return p
 actual=sorted(boats,key=lambda b:finishes[b])[:3]; idxmap={b:i for i,b in enumerate(boats)}; ai=tuple(idxmap[b] for b in actual)
 pb=perm_prob(base,ai); pa=perm_prob(adj,ai)
 # top prediction hit
 perms=list(itertools.permutations(range(6),3)); bp=max(perms,key=lambda p:perm_prob(base,p)); ap=max(perms,key=lambda p:perm_prob(adj,p))
 races.append({'date':g.date.iloc[0],'race':race,'p_actual_base':pb,'p_actual_adj':pa,'neglog_base':-math.log(max(pb,1e-12)),'neglog_adj':-math.log(max(pa,1e-12)),'top_hit_base':int(bp==ai),'top_hit_adj':int(ap==ai),'affected':int(np.any(np.abs(base-adj)>1e-12))})
PF=pd.DataFrame(races); PF.to_csv(OUT/'trifecta_probability.csv',index=False)
SUM=[]
for label,mask in [('all',pd.Series(True,index=PF.index)),('jul',PF.date.dt.month==7),('aug',PF.date.dt.month==8)]:
 q=PF[mask]; SUM.append({'period':label,'races':len(q),'affected':q.affected.sum(),'actual_prob_base':q.p_actual_base.mean(),'actual_prob_adj':q.p_actual_adj.mean(),'prediction_error_base':q.neglog_base.mean(),'prediction_error_adj':q.neglog_adj.mean(),'top_hit_base':q.top_hit_base.mean(),'top_hit_adj':q.top_hit_adj.mean()})
SUM=pd.DataFrame(SUM); SUM.to_csv(OUT/'trifecta_summary.csv',index=False)
print('OFFICIAL_FEMALE',official,'SCRAPED',len(fregs),'TEST_STARTS',len(test))
print('\nADJACENT\n',AD.to_string(index=False)); print('\nTRIPLE\n',TR.to_string(index=False)); print('\nMAKURI\n',MK.to_string(index=False)); print('\nVENUE\n',V.head(20).to_string(index=False)); print('\nTRIFECTA\n',SUM.to_string(index=False)); print('\nTRAIN_EFFECT',eff)
