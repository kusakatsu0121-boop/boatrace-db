#!/usr/bin/env python3
from pathlib import Path
import glob,re,requests,time
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import pandas as pd

SRC=Path('source/data'); OUT=Path('artifacts/research_batch_2'); OUT.mkdir(parents=True,exist_ok=True)

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

def fetch_gender(reg):
    url=f'https://boatracer.teimon.jp/{reg}/'
    try:
        r=requests.get(url,timeout=15,headers={'User-Agent':'Mozilla/5.0'})
        txt=re.sub(r'\s+','',r.text)
        if re.search(r'性別(?:</?[^>]+>)*女',txt) or '性別女' in txt: return reg,'female'
        if re.search(r'性別(?:</?[^>]+>)*男',txt) or '性別男' in txt: return reg,'male'
    except Exception:
        pass
    return reg,None

C=cards_long(load('programs/race_cards/*/*/*.csv'))
RR=load('results/realtime/*/*/*.csv'); R=result_long(RR)
for d in (C,R):
    d['race']=d.race.astype(str); d['boat']=pd.to_numeric(d.boat,errors='coerce')
X=C.merge(R,on=['race','boat'])
X['date']=pd.to_datetime(X.date,errors='coerce'); X=X[X.date>=pd.Timestamp('2025-11-01')].copy()
for c in ['reg','course','finish']: X[c]=pd.to_numeric(X[c],errors='coerce')
X=X.dropna(subset=['reg','course','finish']); X['reg']=X.reg.astype(int); X['course']=X.course.astype(int); X['finish']=X.finish.astype(int)
regs=sorted(X.reg.unique())
sexmap={}
with ThreadPoolExecutor(max_workers=32) as ex:
    futs=[ex.submit(fetch_gender,int(r)) for r in regs]
    for fut in as_completed(futs):
        reg,sex=fut.result()
        if sex: sexmap[reg]=sex
found=pd.DataFrame([{'reg':r,'sex':s} for r,s in sexmap.items()])
found.to_csv(OUT/'sex_map.csv',index=False)
X['sex']=X.reg.map(sexmap)
matched=X[X.sex.notna()].copy()
female_regs=sum(1 for s in sexmap.values() if s=='female')
male_regs=sum(1 for s in sexmap.values() if s=='male')
if female_regs < 240 or male_regs < 1100:
    raise RuntimeError(f'gender crawl incomplete female={female_regs} male={male_regs} of regs={len(regs)}')
X=matched
X['win']=(X.finish==1).astype(int); X['top2']=(X.finish<=2).astype(int); X['top3']=(X.finish<=3).astype(int)
X['score']=X.finish.map({1:10,2:8,3:6,4:4,5:2,6:1})
# 1. baseline true gender difference by actual course
base=X.groupby(['sex','course']).agg(n=('reg','size'),win=('win','mean'),top2=('top2','mean'),top3=('top3','mean'),score=('score','mean')).reset_index()
base.to_csv(OUT/'01_gender_course_baseline.csv',index=False)
# racer-course expected rates to adjust actor and opponent ability
rc=X.groupby(['reg','course']).agg(exp_win=('win','mean'),exp_top3=('top3','mean'),exp_finish=('finish','mean')).reset_index()
winmap={(int(r.reg),int(r.course)):r.exp_win for _,r in rc.iterrows()}; top3map={(int(r.reg),int(r.course)):r.exp_top3 for _,r in rc.iterrows()}; finmap={(int(r.reg),int(r.course)):r.exp_finish for _,r in rc.iterrows()}
# adjacent inner opponent
inner=X[['race','course','reg','sex','finish','top3']].copy(); inner['course']=inner.course+1
inner=inner.rename(columns={'reg':'inner_reg','sex':'inner_sex','finish':'inner_finish','top3':'inner_top3'})
Y=X.merge(inner,on=['race','course'],how='inner'); Y=Y[(Y.sex=='male')&(Y.course>=2)].copy()
Y['beats_inner']=(Y.finish<Y.inner_finish).astype(int)
Y['actor_exp_top3']=[top3map.get((int(r),int(c)),np.nan) for r,c in zip(Y.reg,Y.course)]
Y['inner_course']=Y.course-1
Y['inner_exp_top3']=[top3map.get((int(r),int(c)),np.nan) for r,c in zip(Y.inner_reg,Y.inner_course)]
Y['actor_top3_adj']=Y.top3-Y.actor_exp_top3; Y['inner_top3_adj']=Y.inner_top3-Y.inner_exp_top3
# 2. actor result change
adj=[]
for s,g in Y.groupby('inner_sex'):
    adj.append({'inner_sex':s,'n':len(g),'beats_inner':g.beats_inner.mean(),'actor_win':g.win.mean(),'actor_top3':g.top3.mean(),'actor_top3_adj':g.actor_top3_adj.mean(),'inner_top3':g.inner_top3.mean(),'inner_top3_adj':g.inner_top3_adj.mean()})
adj=pd.DataFrame(adj); adj.to_csv(OUT/'02_male_outside_by_inner_sex.csv',index=False)
# time reproducibility for adjusted actor and inner survival
hold=[]
for label,mask in [('early',Y.date<=pd.Timestamp('2026-06-30')),('late',Y.date>=pd.Timestamp('2026-07-01'))]:
    z=Y[mask]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
    if len(a) and len(b):
        hold.append({'period':label,'n_female_inner':len(a),'n_male_inner':len(b),'actor_top3_adj_diff':a.actor_top3_adj.mean()-b.actor_top3_adj.mean(),'inner_top3_adj_diff':a.inner_top3_adj.mean()-b.inner_top3_adj.mean(),'beats_inner_diff':a.beats_inner.mean()-b.beats_inner.mean()})
hold=pd.DataFrame(hold); hold.to_csv(OUT/'03_adjacent_holdout.csv',index=False)
# winning-method labels
kcols=[c for c in RR.columns if '決まり手' in str(c)]
M=None
if kcols:
    M=RR[['レースコード',kcols[0]]].rename(columns={'レースコード':'race',kcols[0]:'kimarite'}).copy(); M.race=M.race.astype(str)
    WI=Y[['race','date','reg','course','inner_sex']].drop_duplicates().merge(X[X.finish==1][['race','reg']],on=['race','reg'],how='left',indicator='winner_match').merge(M,on='race',how='left')
    WI['is_win']=(WI.winner_match=='both').astype(int)
    ks=WI.kimarite.astype(str)
    WI['makuri_win']=((WI.is_win==1)&ks.str.contains('まくり',na=False)&~ks.str.contains('差し',na=False)).astype(int)
    WI['makurisashi_win']=((WI.is_win==1)&ks.str.contains('まくり差し',na=False)).astype(int)
    # 3 and 4: successful makuri and makuri-sashi by inner sex
    rows=[]
    for (c,s),g in WI.groupby(['course','inner_sex']):
        rows.append({'course':c,'inner_sex':s,'n':len(g),'win_rate':g.is_win.mean(),'makuri_win_rate':g.makuri_win.mean(),'makurisashi_win_rate':g.makurisashi_win.mean()})
    pd.DataFrame(rows).to_csv(OUT/'04_makuri_by_inner_sex.csv',index=False)
    mh=[]
    for label,mask in [('early',WI.date<=pd.Timestamp('2026-06-30')),('late',WI.date>=pd.Timestamp('2026-07-01'))]:
        z=WI[mask]
        for c in [2,3,4,5,6]:
            a=z[(z.course==c)&(z.inner_sex=='female')]; b=z[(z.course==c)&(z.inner_sex=='male')]
            if len(a) and len(b):
                mh.append({'period':label,'course':c,'n_female_inner':len(a),'n_male_inner':len(b),'makuri_diff':a.makuri_win.mean()-b.makuri_win.mean(),'makurisashi_diff':a.makurisashi_win.mean()-b.makurisashi_win.mean()})
    pd.DataFrame(mh).to_csv(OUT/'05_makuri_holdout.csv',index=False)
# 5. course-specific inner survival and actor effect after both abilities adjusted
cr=[]
for c,g in Y.groupby('course'):
    a=g[g.inner_sex=='female']; b=g[g.inner_sex=='male']
    if len(a) and len(b):
        cr.append({'course':c,'n_female_inner':len(a),'n_male_inner':len(b),'actor_top3_adj_diff':a.actor_top3_adj.mean()-b.actor_top3_adj.mean(),'inner_top3_adj_diff':a.inner_top3_adj.mean()-b.inner_top3_adj.mean(),'beats_inner_diff':a.beats_inner.mean()-b.beats_inner.mean()})
pd.DataFrame(cr).to_csv(OUT/'06_course_specific_adjacent.csv',index=False)
# 6. does a third boat just outside the male benefit when his inner opponent is female?
outer=X[['race','course','reg','sex','top3']].copy(); outer['course']=outer.course-1
outer=outer.rename(columns={'reg':'outer_reg','sex':'outer_sex','top3':'outer_top3'})
T=Y.merge(outer,on=['race','course'],how='inner'); T=T[T.course<=5].copy()
T['outer_course']=T.course+1
T['outer_exp_top3']=[top3map.get((int(r),int(c)),np.nan) for r,c in zip(T.outer_reg,T.outer_course)]
T['outer_top3_adj']=T.outer_top3-T.outer_exp_top3
tri=[]
for s,g in T.groupby('inner_sex'):
    tri.append({'inner_sex':s,'n':len(g),'outer_top3':g.outer_top3.mean(),'outer_top3_adj':g.outer_top3_adj.mean()})
pd.DataFrame(tri).to_csv(OUT/'07_outer_beneficiary.csv',index=False)
th=[]
for label,mask in [('early',T.date<=pd.Timestamp('2026-06-30')),('late',T.date>=pd.Timestamp('2026-07-01'))]:
    z=T[mask]; a=z[z.inner_sex=='female']; b=z[z.inner_sex=='male']
    if len(a) and len(b): th.append({'period':label,'n_female_inner':len(a),'n_male_inner':len(b),'outer_top3_adj_diff':a.outer_top3_adj.mean()-b.outer_top3_adj.mean()})
pd.DataFrame(th).to_csv(OUT/'08_outer_beneficiary_holdout.csv',index=False)
# 7. individual male candidates; require substantial female-inner sample and reproduction direction
cand=[]
for reg,g in Y.groupby('reg'):
    a=g[g.inner_sex=='female']; b=g[g.inner_sex=='male']
    if len(a)<18 or len(b)<80: continue
    d=a.actor_top3_adj.mean()-b.actor_top3_adj.mean()
    e=g[g.date<=pd.Timestamp('2026-06-30')]; l=g[g.date>=pd.Timestamp('2026-07-01')]
    ea=e[e.inner_sex=='female']; eb=e[e.inner_sex=='male']; la=l[l.inner_sex=='female']; lb=l[l.inner_sex=='male']
    de=(ea.actor_top3_adj.mean()-eb.actor_top3_adj.mean()) if len(ea)>=8 and len(eb)>=30 else np.nan
    dl=(la.actor_top3_adj.mean()-lb.actor_top3_adj.mean()) if len(la)>=5 and len(lb)>=20 else np.nan
    cand.append({'reg':int(reg),'n_female_inner':len(a),'n_male_inner':len(b),'actor_top3_adj_diff':d,'early_diff':de,'late_diff':dl,'same_direction':bool(pd.notna(de) and pd.notna(dl) and np.sign(de)==np.sign(dl))})
P=pd.DataFrame(cand)
if len(P): P=P.sort_values(['same_direction','actor_top3_adj_diff'],ascending=[False,True])
P.to_csv(OUT/'09_player_candidates.csv',index=False)

print('GENDER_MAP',female_regs,male_regs,'matched starts',len(X),'unique regs',len(sexmap))
print('\nBASELINE\n',base.to_string(index=False))
print('\nADJ\n',adj.to_string(index=False))
print('\nHOLDOUT\n',hold.to_string(index=False))
print('\nCOURSE\n',pd.DataFrame(cr).to_string(index=False))
print('\nTRIAD\n',pd.DataFrame(tri).to_string(index=False))
print('\nTRIAD_HOLDOUT\n',pd.DataFrame(th).to_string(index=False))
if M is not None:
    print('\nMAKURI\n',pd.read_csv(OUT/'04_makuri_by_inner_sex.csv').to_string(index=False))
    print('\nMAKURI_HOLDOUT\n',pd.read_csv(OUT/'05_makuri_holdout.csv').to_string(index=False))
print('\nCANDIDATES\n',P.head(20).to_string(index=False) if len(P) else 'none')
print('NOTE: sex sourced from Teimon profile pages for each active registration number and validated by count threshold. Official BOAT RACE search currently reports 287 female racers; winning method only shows successful winning tactic, not failed makuri attempts.')
