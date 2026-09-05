#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
import advisor_extension_patterns as m
from racer_directory import load_many,cards_to_long,results_to_long,build_panel

TRAIN_END=pd.Timestamp('2026-06-30'); JUL0=pd.Timestamp('2026-07-01');JUL1=pd.Timestamp('2026-07-31');AUG0=pd.Timestamp('2026-08-01');MID=pd.Timestamp('2026-08-14');AUG1=pd.Timestamp('2026-08-28')
OUT=Path('artifacts/anti_hype_head_scan');OUT.mkdir(parents=True,exist_ok=True)
KS=[5,10,20]

def q80(df,c,col):
 s=pd.to_numeric(df.loc[df.course.eq(c),col],errors='coerce').dropna();return float(s.quantile(.8))

def basket(r,head,k):
 arr=[]
 for b in range(1,7):
  if b==head:continue
  for c in range(1,7):
   if c in (head,b):continue
   p=f'{head}-{b}-{c}'
   try:o=float(r[f'3連単_{p}'])
   except:continue
   if np.isfinite(o) and o>0:arr.append((p,o))
 arr.sort(key=lambda x:x[1]);arr=arr[:k]
 if not arr:return None
 inv=np.array([1/o for _,o in arr]);s=inv.sum();stakes=100*inv/s;win='-'.join(map(str,tuple(r.winner_path)));ret=0
 for (p,o),st in zip(arr,stakes):
  if p==win:ret=st*float(r.payout)/100;break
 return ret,int(win in {p for p,_ in arr}),s

def stat(d):
 if d.empty:return (0,0,np.nan,np.nan,np.nan,np.nan)
 roi=d.ret.sum()/len(d);i=d.ret.idxmax();z=d.drop(index=i) if len(d)>1 else d.iloc[0:0];roi2=z.ret.sum()/len(z) if len(z) else np.nan
 return len(d),int(d.hit.sum()),float(d.hit.mean()),float(roi),float(d.imp.mean()),float(roi2)

cards=load_many('source/data/programs/race_cards/*/*/*.csv');results=load_many('source/data/results/realtime/*/*/*.csv');odds=load_many('source/data/previews/od3/*/*/*.csv');pay=load_many('source/data/results/payouts/*/*/*.csv')
cl=cards_to_long(cards);rl=results_to_long(results)
if '決まり手' in rl.columns:rl['決まり手']=m.normalize_method(rl['決まり手'])
panel=build_panel(cl,rl,pd.DataFrame()).dropna(subset=['race_date','regno','actual_course','finish']);roles=m.build_role_metrics(panel[panel.race_date<=TRAIN_END])
r=m.attach_roles(m.build_base(cl,odds,pay),roles);r=r[(r.race_date>=JUL0)&(r.race_date<=AUG1)].copy()
th={'b1s':q80(roles,1,'beaten_sashi_rate'),'c2s':q80(roles,2,'sashi_win_rate'),'b1m':q80(roles,1,'beaten_makuri_rate'),'c3m':q80(roles,3,'makuri_win_rate'),'b1ms':q80(roles,1,'beaten_makuri_sashi_rate'),'c3ms':q80(roles,3,'makuri_sashi_win_rate')}
conds={
'2差し注目条件':(r.c1_beaten_sashi_rate>=th['b1s'])&(r.c2_sashi_win_rate>=th['c2s']),
'3まくり注目条件':(r.c1_beaten_makuri_rate>=th['b1m'])&(r.c3_makuri_win_rate>=th['c3m']),
'3まくり差し注目条件':(r.c1_beaten_makuri_sashi_rate>=th['b1ms'])&(r.c3_makuri_sashi_win_rate>=th['c3ms'])}
rows=[]
for cn,mask in conds.items():
 z=r[mask]
 for head in range(1,7):
  for k in KS:
   rec=[]
   for idx,x in z.iterrows():
    b=basket(x,head,k)
    if b:rec.append({'date':x.race_date,'ret':b[0],'hit':b[1],'imp':b[2]})
   d=pd.DataFrame(rec)
   if d.empty:continue
   splits={'July':d[(d.date>=JUL0)&(d.date<=JUL1)],'Aug':d[(d.date>=AUG0)&(d.date<=AUG1)],'Aug1':d[(d.date>=AUG0)&(d.date<=MID)],'Aug2':d[(d.date>MID)&(d.date<=AUG1)]}
   row={'condition':cn,'head':head,'k':k}
   for lab,x in splits.items():
    n,h,hr,roi,imp,roi2=stat(x);row.update({f'{lab}_n':n,f'{lab}_hits':h,f'{lab}_hit_rate':hr,f'{lab}_roi':roi,f'{lab}_avg_implied':imp,f'{lab}_roi_no_best':roi2})
   row['stable']=(row['July_n']>=40 and row['Aug_n']>=50 and row['July_roi']>100 and row['Aug_roi']>100 and row['July_roi_no_best']>85 and row['Aug_roi_no_best']>85)
   row['both_aug_halves']=(row['Aug1_roi']>90 and row['Aug2_roi']>90)
   rows.append(row)
D=pd.DataFrame(rows);D=D.sort_values(['stable','both_aug_halves','Aug_roi','July_roi'],ascending=[False,False,False,False]);D.to_csv(OUT/'summary.csv',index=False)
print(D.head(50).to_string(index=False))
