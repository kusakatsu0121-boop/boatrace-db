#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd
import advisor_extension_patterns as m
from racer_directory import load_many, cards_to_long, results_to_long, build_panel

TRAIN_END=pd.Timestamp('2026-06-30')
JUL0,JUL1=pd.Timestamp('2026-07-01'),pd.Timestamp('2026-07-31')
AUG0,AUGMID,AUG1=pd.Timestamp('2026-08-01'),pd.Timestamp('2026-08-14'),pd.Timestamp('2026-08-28')
MIN_JUL=35
MIN_AUG=25
OUT=Path('artifacts/targeted_value_rules'); OUT.mkdir(parents=True,exist_ok=True)


def q80(df, course, col):
    s=pd.to_numeric(df.loc[df.course.eq(course),col],errors='coerce').dropna()
    return float(s.quantile(.8)) if len(s) else np.nan

def safe_odds(r,path):
    try:
        v=float(r[f'3連単_{path}'])
        return v if np.isfinite(v) and v>0 else np.nan
    except Exception:
        return np.nan

def stats(df,path):
    if df.empty: return dict(n=0,hits=0,hit_rate=np.nan,avg_odds=np.nan,mean_implied=np.nan,roi=np.nan,roi_no_max=np.nan)
    odds=df.apply(lambda r:safe_odds(r,path),axis=1)
    z=df.loc[odds.notna()].copy(); odds=odds[odds.notna()]
    if z.empty: return dict(n=0,hits=0,hit_rate=np.nan,avg_odds=np.nan,mean_implied=np.nan,roi=np.nan,roi_no_max=np.nan)
    tup=tuple(map(int,path.split('-')))
    hit=z.winner_path.map(lambda x: tuple(x)==tup)
    ret=np.where(hit, pd.to_numeric(z.payout,errors='coerce').fillna(0), 0.0)
    n=len(z); total=float(np.nansum(ret)); roi=total/(100*n)*100
    if n>1:
        imax=int(np.nanargmax(ret)) if np.nanmax(ret)>0 else -1
        if imax>=0:
            rr=np.delete(ret,imax); roi2=float(np.nansum(rr))/(100*len(rr))*100
        else: roi2=roi
    else: roi2=np.nan
    return dict(n=n,hits=int(hit.sum()),hit_rate=float(hit.mean()),avg_odds=float(odds.mean()),mean_implied=float((1/odds).mean()),roi=roi,roi_no_max=roi2)

cards=load_many('source/data/programs/race_cards/*/*/*.csv')
results=load_many('source/data/results/realtime/*/*/*.csv')
odds=load_many('source/data/previews/od3/*/*/*.csv')
payouts=load_many('source/data/results/payouts/*/*/*.csv')
cl=cards_to_long(cards); rl=results_to_long(results)
if '決まり手' in rl.columns: rl['決まり手']=m.normalize_method(rl['決まり手'])
panel=build_panel(cl,rl,pd.DataFrame()).dropna(subset=['race_date','regno','actual_course','finish']).copy()
train=panel[panel.race_date<=TRAIN_END].copy()
roles=m.build_role_metrics(train)
f2,f3,chain=m.build_follow_metrics(train)
races=m.attach_roles(m.build_base(cl,odds,payouts),roles)
races=races[(races.race_date>=JUL0)&(races.race_date<=AUG1)].copy()

# Attach trained 1-course follower tendencies for 1->2 and 1->3.
F2={(int(r.regno),int(r.winner_course),int(r.target_course)):r for r in f2.itertuples(index=False)}
def fmap(reg,target,field):
    try: r=F2.get((int(reg),1,int(target))); return getattr(r,field) if r else np.nan
    except: return np.nan
for target in (2,3):
    races[f'c1_follow2_to{target}']=races.reg_c1.map(lambda x:fmap(x,target,'follow2_lift_pt'))
    races[f'c1_follow2prob_to{target}']=races.reg_c1.map(lambda x:fmap(x,target,'follow2_prob'))

thr={
'c1_beaten_sashi':q80(roles,1,'beaten_sashi_rate'),
'c2_sashi':q80(roles,2,'sashi_win_rate'),
'c1_beaten_makuri':q80(roles,1,'beaten_makuri_rate'),
'c3_makuri':q80(roles,3,'makuri_win_rate'),
'c1_beaten_ms':q80(roles,1,'beaten_makuri_sashi_rate'),
'c3_ms':q80(roles,3,'makuri_sashi_win_rate'),
'c1_escape':q80(roles,1,'escape_rate'),
}
# follower lift thresholds are across trained 1-course winners only
for t in (2,3):
    s=f2[(f2.winner_course==1)&(f2.target_course==t)].follow2_lift_pt.dropna()
    thr[f'follow_to{t}']=float(s.quantile(.8))

rules={
'diff2_weak1_strong2': (races.c1_beaten_sashi_rate>=thr['c1_beaten_sashi']) & (races.c2_sashi_win_rate>=thr['c2_sashi']),
'makuri3_weak1_strong3': (races.c1_beaten_makuri_rate>=thr['c1_beaten_makuri']) & (races.c3_makuri_win_rate>=thr['c3_makuri']),
'makurisashi3_weak1_strong3': (races.c1_beaten_makuri_sashi_rate>=thr['c1_beaten_ms']) & (races.c3_makuri_sashi_win_rate>=thr['c3_ms']),
'strong1_follows2': (races.c1_escape_rate>=thr['c1_escape']) & (races.c1_follow2_to2>=thr['follow_to2']),
'strong1_follows3': (races.c1_escape_rate>=thr['c1_escape']) & (races.c1_follow2_to3>=thr['follow_to3']),
}

paths_by_rule={
'diff2_weak1_strong2':[f'2-{b}-{c}' for b in [1,3,4,5,6] for c in [1,3,4,5,6] if c!=b],
'makuri3_weak1_strong3':[f'3-{b}-{c}' for b in [1,2,4,5,6] for c in [1,2,4,5,6] if c!=b],
'makurisashi3_weak1_strong3':[f'3-{b}-{c}' for b in [1,2,4,5,6] for c in [1,2,4,5,6] if c!=b],
'strong1_follows2':[f'1-2-{c}' for c in [3,4,5,6]],
'strong1_follows3':[f'1-3-{c}' for c in [2,4,5,6]],
}
rows=[]
for name,mask in rules.items():
    z=races[mask].copy()
    splits={'July':z[(z.race_date>=JUL0)&(z.race_date<=JUL1)],
            'Aug_all':z[(z.race_date>=AUG0)&(z.race_date<=AUG1)],
            'Aug_1_14':z[(z.race_date>=AUG0)&(z.race_date<=AUGMID)],
            'Aug_15_28':z[(z.race_date>AUGMID)&(z.race_date<=AUG1)]}
    for path in paths_by_rule[name]:
        rec={'rule':name,'path':path,'rule_races_july':len(splits['July']),'rule_races_aug':len(splits['Aug_all'])}
        for label,d in splits.items():
            st=stats(d,path)
            for k,v in st.items(): rec[f'{label}_{k}']=v
        rows.append(rec)
D=pd.DataFrame(rows)
D['july_edge_vs_implied']=D.July_hit_rate-D.July_mean_implied
D['aug_edge_vs_implied']=D.Aug_all_hit_rate-D.Aug_all_mean_implied
D['candidate']=(D.July_n>=MIN_JUL)&(D.Aug_all_n>=MIN_AUG)&(D.July_roi>100)&(D.Aug_all_roi>100)&(D.July_roi_no_max>80)&(D.Aug_all_roi_no_max>80)
D=D.sort_values(['candidate','Aug_all_roi','July_roi','Aug_all_n'],ascending=[False,False,False,False])
D.to_csv(OUT/'all_rules.csv',index=False)
D[D.candidate].to_csv(OUT/'candidates.csv',index=False)
pd.DataFrame([{'threshold':k,'value':v} for k,v in thr.items()]).to_csv(OUT/'thresholds.csv',index=False)
print('races',len(races),'train',len(train),'roles',len(roles))
print('thresholds',thr)
cols=['rule','path','July_n','July_hits','July_roi','July_roi_no_max','Aug_all_n','Aug_all_hits','Aug_all_roi','Aug_all_roi_no_max','Aug_1_14_roi','Aug_15_28_roi','candidate']
print(D[cols].head(40).to_string(index=False))
