#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
import advisor_extension_patterns as m
from racer_directory import load_many, cards_to_long, results_to_long, build_panel

TRAIN_END=pd.Timestamp('2026-06-30')
JUL0,JUL1=pd.Timestamp('2026-07-01'),pd.Timestamp('2026-07-31')
AUG0,MID,AUG1=pd.Timestamp('2026-08-01'),pd.Timestamp('2026-08-14'),pd.Timestamp('2026-08-28')
OUT=Path('artifacts/head_edge_basket');OUT.mkdir(parents=True,exist_ok=True)
KS=[5,10,20]

def q80(df,c,col):
    s=pd.to_numeric(df.loc[df.course.eq(c),col],errors='coerce').dropna();return float(s.quantile(.8))

def race_basket(r,head,k):
    items=[]
    for b in range(1,7):
        if b==head: continue
        for c in range(1,7):
            if c in (head,b): continue
            path=f'{head}-{b}-{c}'; col=f'3連単_{path}'
            try: od=float(r[col])
            except: continue
            if np.isfinite(od) and od>0: items.append((path,od))
    items=sorted(items,key=lambda x:x[1])[:k]
    if not items:return None
    inv=np.array([1/x[1] for x in items],float); s=inv.sum()
    stakes=100*inv/s
    win='-'.join(map(str,tuple(r.winner_path)))
    ret=0.0
    for (path,od),stake in zip(items,stakes):
        if path==win:
            # actual payout is yen returned for 100 yen; fractional stake is fine for normalized backtest
            ret=stake*float(r.payout)/100.0
            break
    return {'return':ret,'hit':int(win in {p for p,_ in items}),'implied_basket':s,
            'min_odds':items[0][1],'max_odds':items[-1][1],'paths':'|'.join(p for p,_ in items)}

def summarize(z):
    if z.empty:return dict(n=0,hits=0,hit_rate=np.nan,roi=np.nan,avg_implied=np.nan,roi_no_best=np.nan)
    roi=z['return'].sum()/len(z)
    if len(z)>1:
        i=z['return'].idxmax(); zz=z.drop(index=i); roi2=zz['return'].sum()/len(zz) if len(zz) else np.nan
    else:roi2=np.nan
    return dict(n=len(z),hits=int(z.hit.sum()),hit_rate=float(z.hit.mean()),roi=float(roi),avg_implied=float(z.implied_basket.mean()),roi_no_best=float(roi2))

cards=load_many('source/data/programs/race_cards/*/*/*.csv');results=load_many('source/data/results/realtime/*/*/*.csv')
odds=load_many('source/data/previews/od3/*/*/*.csv');payouts=load_many('source/data/results/payouts/*/*/*.csv')
cl=cards_to_long(cards);rl=results_to_long(results)
if '決まり手' in rl.columns:rl['決まり手']=m.normalize_method(rl['決まり手'])
panel=build_panel(cl,rl,pd.DataFrame()).dropna(subset=['race_date','regno','actual_course','finish'])
roles=m.build_role_metrics(panel[panel.race_date<=TRAIN_END])
races=m.attach_roles(m.build_base(cl,odds,payouts),roles)
races=races[(races.race_date>=JUL0)&(races.race_date<=AUG1)].copy()
th={
'b1s':q80(roles,1,'beaten_sashi_rate'),'c2s':q80(roles,2,'sashi_win_rate'),
'b1m':q80(roles,1,'beaten_makuri_rate'),'c3m':q80(roles,3,'makuri_win_rate'),
'b1ms':q80(roles,1,'beaten_makuri_sashi_rate'),'c3ms':q80(roles,3,'makuri_sashi_win_rate'),
'esc1':q80(roles,1,'escape_rate')}
rules={
'2差し弱点狩り':(2,(races.c1_beaten_sashi_rate>=th['b1s'])&(races.c2_sashi_win_rate>=th['c2s'])),
'3まくり弱点狩り':(3,(races.c1_beaten_makuri_rate>=th['b1m'])&(races.c3_makuri_win_rate>=th['c3m'])),
'3まくり差し弱点狩り':(3,(races.c1_beaten_makuri_sashi_rate>=th['b1ms'])&(races.c3_makuri_sashi_win_rate>=th['c3ms'])),
'1逃げ強者':(1,(races.c1_escape_rate>=th['esc1']))}
rows=[];detail=[]
for name,(head,mask) in rules.items():
    base=races[mask].copy()
    for k in KS:
        rr=[]
        for idx,r in base.iterrows():
            b=race_basket(r,head,k)
            if b is not None: b.update({'idx':idx,'race_date':r.race_date});rr.append(b)
        d=pd.DataFrame(rr)
        if d.empty:continue
        splits={'July':d[(d.race_date>=JUL0)&(d.race_date<=JUL1)],'Aug':d[(d.race_date>=AUG0)&(d.race_date<=AUG1)],'Aug1':d[(d.race_date>=AUG0)&(d.race_date<=MID)],'Aug2':d[(d.race_date>MID)&(d.race_date<=AUG1)]}
        rec={'rule':name,'head':head,'k':k}
        for lab,z in splits.items():
            s=summarize(z)
            for key,val in s.items():rec[f'{lab}_{key}']=val
        rec['stable']=(rec['July_n']>=40 and rec['Aug_n']>=50 and rec['July_roi']>100 and rec['Aug_roi']>100 and rec['July_roi_no_best']>85 and rec['Aug_roi_no_best']>85)
        rows.append(rec)
        d['rule']=name;d['head']=head;d['k']=k;detail.append(d)
D=pd.DataFrame(rows).sort_values(['stable','Aug_roi','July_roi'],ascending=[False,False,False])
D.to_csv(OUT/'summary.csv',index=False)
if detail:pd.concat(detail,ignore_index=True).to_csv(OUT/'detail.csv',index=False)
pd.DataFrame([{'threshold':a,'value':b} for a,b in th.items()]).to_csv(OUT/'thresholds.csv',index=False)
print(D.to_string(index=False))
