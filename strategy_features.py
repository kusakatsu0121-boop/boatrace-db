#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import math
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel

PRIOR = 30.0
MIN_ROLE_N = 18
MIN_PAIR_N = 40
MIN_TRIPLE_N = 40
MIN_PATH_N = 10
HOLDOUT_DAYS = 120


def shr(k, n, p0, prior=PRIOR):
    if n <= 0 or pd.isna(p0):
        return np.nan
    return (float(k) + prior * float(p0)) / (float(n) + prior)


def zscore(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors='coerce')
    sd = s.std(ddof=0)
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def build_roles(train: pd.DataFrame) -> pd.DataFrame:
    p = train.dropna(subset=['regno', 'actual_course', 'finish']).copy()
    p['actual_course'] = p['actual_course'].astype(int)
    p['is1'] = (p['finish'] == 1).astype(int)
    p['is2'] = (p['finish'] == 2).astype(int)
    p['is3'] = (p['finish'] == 3).astype(int)
    p['top2'] = (p['finish'] <= 2).astype(int)
    p['top3'] = (p['finish'] <= 3).astype(int)
    p['escape_race'] = (p.get('決まり手', '').astype(str) == '逃げ').astype(int)

    course_base = {}
    for c, g in p.groupby('actual_course'):
        good = g[g.get('f_start', 0).fillna(0).eq(0)]
        course_base[int(c)] = {
            'p1': g.is1.mean(), 'p2': g.is2.mean(), 'p3': g.is3.mean(),
            'top2': g.top2.mean(), 'top3': g.top3.mean(),
            'escape_allowed': g.escape_race.mean(),
            'avg_st': good.actual_st.mean(),
        }

    rows = []
    for (reg, c), g in p.groupby(['regno', 'actual_course']):
        c = int(c); n = len(g); b = course_base[c]
        good = g[g.get('f_start', 0).fillna(0).eq(0)]
        row = {
            'regno': int(reg), 'course': c, 'n': int(n),
            'p1': shr(g.is1.sum(), n, b['p1']),
            'p2': shr(g.is2.sum(), n, b['p2']),
            'p3': shr(g.is3.sum(), n, b['p3']),
            'top2': shr(g.top2.sum(), n, b['top2']),
            'top3': shr(g.top3.sum(), n, b['top3']),
            'allow_escape': shr(g.escape_race.sum(), n, b['escape_allowed']),
            'avg_st': good.actual_st.mean(),
            'course_avg_st': b['avg_st'],
        }
        row['st_edge'] = (b['avg_st'] - row['avg_st']) if pd.notna(b['avg_st']) and pd.notna(row['avg_st']) else 0.0
        wins = g[g.is1.eq(1)]
        for m, key in [('逃げ','escape'), ('差し','sashi'), ('まくり','makuri'), ('まくり差し','makuri_sashi')]:
            row[f'{key}_wins'] = int((wins.get('決まり手', '').astype(str) == m).sum())
        denom = max(row['p1'] + row['p2'] + row['p3'], 1e-9)
        row['head_share'] = row['p1'] / denom
        row['second_share'] = row['p2'] / denom
        row['third_share'] = row['p3'] / denom
        rows.append(row)

    d = pd.DataFrame(rows)
    if d.empty:
        return d
    outs = []
    for c, g in d.groupby('course'):
        g = g.copy()
        for col in ['head_share','second_share','third_share','p1','top3','st_edge']:
            g[f'z_{col}'] = zscore(g[col].fillna(g[col].median()))
        g['survival_score'] = 0.55*zscore((g.p2+g.p3)) + 0.45*g['z_top3']
        g['wall_score'] = np.nan
        if c in (2,3):
            g['wall_score'] = 0.7*zscore(-g.allow_escape) + 0.3*g['z_st_edge']

        flabel=[]; slabel=[]; outer=[]
        for _, r in g.iterrows():
            if int(r.n) < MIN_ROLE_N:
                flabel.append('SAMPLE_LOW'); slabel.append('SAMPLE_LOW'); outer.append(0); continue
            fs = {
                'HEAD': float(r.z_head_share),
                'SECOND_HOLD': float(r.z_second_share),
                'THIRD_PICK': float(r.z_third_share),
                'SURVIVE': float(r.survival_score),
            }
            fk, fv = max(fs.items(), key=lambda kv: kv[1])
            flabel.append(fk if fv >= 0.45 else 'BALANCED')

            total_wins = int(r.escape_wins+r.sashi_wins+r.makuri_wins+r.makuri_sashi_wins)
            if c == 1:
                ss = {'ESCAPE': int(r.escape_wins), 'ST_ATTACK': max(0.0, float(r.st_edge)*500.0)}
            else:
                denomw = max(total_wins, 1)
                ss = {
                    'SASHI': int(r.sashi_wins)/denomw,
                    'MAKURI': int(r.makuri_wins)/denomw,
                    'MAKURI_SASHI': int(r.makuri_sashi_wins)/denomw,
                    'ST_ATTACK': max(0.0, float(r.st_edge)/0.03),
                }
                if c in (2,3) and pd.notna(r.wall_score):
                    ss['WALL'] = max(0.0, float(r.wall_score)/2.0)
            sk, sv = max(ss.items(), key=lambda kv: kv[1])
            slabel.append(sk if sv >= 0.34 else 'BALANCED')
            outer.append(int(c >= 5 and (float(r.z_p1) >= 0.8 or float(r.st_edge) >= 0.015 or sk in ('MAKURI','MAKURI_SASHI','ST_ATTACK'))))
        g['finish_role'] = flabel
        g['style'] = slabel
        g['outer_special'] = outer
        outs.append(g)
    return pd.concat(outs, ignore_index=True)


def baseline_map(roles):
    out={}
    for _,r in roles.iterrows():
        out[(int(r.regno),int(r.course))] = {
            '1':float(r.p1),'2':float(r.p2),'3':float(r.p3),
            'top2':float(r.top2),'top3':float(r.top3)
        }
    return out


def attach_roles(evalp, roles):
    cols=['regno','course','style','finish_role','outer_special']
    return evalp.merge(roles[cols], left_on=['regno','actual_course'], right_on=['regno','course'], how='left').drop(columns=['course'])


def event_obs(df, event):
    if event in ('1','2','3'):
        return (df.finish == int(event)).astype(float)
    if event == 'top2': return (df.finish <= 2).astype(float)
    return (df.finish <= 3).astype(float)


def pair_effects(x, roles):
    bm=baseline_map(roles); rows=[]
    pairs=[(1,2),(1,3),(2,3),(2,4),(3,4),(3,5),(4,5)]
    for a,b in pairs:
        pa=x[x.actual_course.eq(a)][['レースコード','style','outer_special']].rename(columns={'style':'style_a','outer_special':'special_a'})
        pb=x[x.actual_course.eq(b)][['レースコード','style','outer_special']].rename(columns={'style':'style_b','outer_special':'special_b'})
        q=pa.merge(pb,on='レースコード')
        q=q[q.style_a.notna() & q.style_b.notna() & ~q.style_a.eq('SAMPLE_LOW') & ~q.style_b.eq('SAMPLE_LOW')]
        if a>=5: q=q[q.special_a.eq(1)]
        if b>=5: q=q[q.special_b.eq(1)]
        if q.empty: continue
        z=x.merge(q[['レースコード','style_a','style_b']],on='レースコード')
        for (sa,sb,tc),g in z.groupby(['style_a','style_b','actual_course']):
            tc=int(tc)
            for ev in ['1','2','3','top2','top3']:
                obs=event_obs(g,ev)
                exp=pd.Series([bm.get((int(r),tc),{}).get(ev,np.nan) for r in g.regno],index=g.index)
                ok=exp.notna()
                n=int(ok.sum())
                if n<MIN_PAIR_N: continue
                o=float(obs[ok].mean()); e=float(exp[ok].mean()); se=math.sqrt(max(e*(1-e)/n,1e-12))
                rows.append({'course_a':a,'style_a':sa,'course_b':b,'style_b':sb,'target_course':tc,'event':ev,'n':n,
                             'observed':o,'expected_from_target_strength':e,'lift_pt':o-e,'lift_ratio':o/e if e>0 else np.nan,'z_approx':(o-e)/se})
    return pd.DataFrame(rows)


def triple_effects(x, roles):
    bm=baseline_map(roles); parts=[]
    for c in (1,2,3,4):
        q=x[x.actual_course.eq(c)][['レースコード','regno','style','finish']].rename(columns={'regno':f'reg{c}','style':f'style{c}','finish':f'finish{c}'})
        parts.append(q)
    m=parts[0]
    for q in parts[1:]: m=m.merge(q,on='レースコード')
    race_meta=x[['レースコード','決まり手']].drop_duplicates('レースコード') if '決まり手' in x else pd.DataFrame({'レースコード':m['レースコード'],'決まり手':''})
    m=m.merge(race_meta,on='レースコード',how='left')
    m=m[m.style1.notna() & m.style2.notna() & m.style3.notna()]
    rows=[]
    for (s1,s2,s3),g in m.groupby(['style1','style2','style3']):
        n=len(g)
        if n<MIN_TRIPLE_N: continue
        exp=np.array([bm.get((int(r),1),{}).get('1',np.nan) for r in g.reg1],dtype=float)
        ok=~np.isnan(exp)
        esc=(g['決まり手'].astype(str)=='逃げ').to_numpy(float)
        rows.append({'style1':s1,'style2':s2,'style3':s3,'n':n,
                     'escape_rate':float(np.mean(esc)),
                     'expected_c1_win_from_strength':float(np.mean(exp[ok])) if ok.any() else np.nan,
                     'escape_lift_pt':float(np.mean(esc[ok])-np.mean(exp[ok])) if ok.any() else np.nan,
                     'c1_win':float((g.finish1==1).mean()),'c2_win':float((g.finish2==1).mean()),'c3_win':float((g.finish3==1).mean()),
                     'c2_dead_4plus':float((g.finish2>=4).mean()),'c3_top3':float((g.finish3<=3).mean()),'c4_top3':float((g.finish4<=3).mean())})
    return pd.DataFrame(rows).sort_values('n',ascending=False) if rows else pd.DataFrame()


def path_effects(x):
    piv=x.pivot_table(index='レースコード',columns='actual_course',values=['style','finish'],aggfunc='first')
    meta=x[['レースコード','決まり手']].drop_duplicates('レースコード').set_index('レースコード') if '決まり手' in x else None
    rows=[]
    for race,r in piv.iterrows():
        try: styles=[r[('style',c)] for c in (1,2,3,4)]
        except Exception: continue
        if any(pd.isna(v) or v=='SAMPLE_LOW' for v in styles): continue
        fin=[]
        for c in range(1,7):
            try: v=r[('finish',c)]
            except Exception: continue
            if pd.notna(v): fin.append((int(v),c))
        if len(fin)<3: continue
        fin.sort(); combo='-'.join(str(c) for _,c in fin[:3])
        method=str(meta.loc[race,'決まり手']) if meta is not None and race in meta.index else ''
        rows.append({'style1':styles[0],'style2':styles[1],'style3':styles[2],'style4':styles[3],'winning_method':method,'course_trifecta':combo})
    d=pd.DataFrame(rows)
    if d.empty:return d
    g=d.groupby(['style1','style2','style3','style4','winning_method','course_trifecta']).size().reset_index(name='count')
    den=d.groupby(['style1','style2','style3','style4','winning_method']).size().reset_index(name='pattern_n')
    g=g.merge(den,on=['style1','style2','style3','style4','winning_method'])
    g=g[g['count']>=MIN_PATH_N].copy(); g['rate']=g['count']/g['pattern_n']
    return g.sort_values(['pattern_n','rate'],ascending=[False,False])


def summary_table(pe, triple):
    chunks=[]
    if not pe.empty:
        q=pe[(pe.n>=60) & (pe.z_approx.abs()>=2.0) & (pe.lift_pt.abs()>=0.03)].copy()
        q['signal']='PAIR'; q['score']=q.z_approx.abs()*np.sqrt(q.n)
        chunks.append(q.sort_values('score',ascending=False).head(120))
    if not triple.empty:
        q=triple[(triple.n>=60) & (triple.escape_lift_pt.abs()>=0.04)].copy()
        q['signal']='TRIPLE_123'; q['score']=q.escape_lift_pt.abs()*np.sqrt(q.n)
        chunks.append(q.sort_values('score',ascending=False).head(80))
    return pd.concat(chunks,ignore_index=True,sort=False) if chunks else pd.DataFrame()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',default='source/data')
    ap.add_argument('--out',default='artifacts/strategy_features')
    ap.add_argument('--holdout-days',type=int,default=HOLDOUT_DAYS)
    args=ap.parse_args()
    src=Path(args.source); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    cards=load_many(str(src/'programs/race_cards/*/*/*.csv'))
    results=load_many(str(src/'results/realtime/*/*/*.csv'))
    title=load_many(str(src/'programs/title/*/*/*.csv'))
    if cards.empty or results.empty: raise SystemExit('required race_cards/results not found')
    panel=build_panel(cards_to_long(cards),results_to_long(results),title)
    panel=panel.dropna(subset=['race_date','regno','actual_course','finish']).copy()
    end=panel.race_date.max(); cutoff=end-pd.Timedelta(days=args.holdout_days)
    train=panel[panel.race_date<cutoff].copy(); test=panel[panel.race_date>=cutoff].copy()
    if train.empty or test.empty: raise SystemExit('train/holdout split produced empty data')
    roles=build_roles(train); x=attach_roles(test,roles)
    pe=pair_effects(x,roles); tr=triple_effects(x,roles); paths=path_effects(x); sm=summary_table(pe,tr)
    outputs={'racer_course_roles_train.csv':roles,'pair_effects_holdout.csv':pe,'triple_123_holdout.csv':tr,'path_effects_holdout.csv':paths,'top_strategy_signals.csv':sm}
    for name,df in outputs.items(): df.to_csv(out/name,index=False)
    meta=pd.DataFrame([{'data_end':str(end.date()),'cutoff':str(cutoff.date()),'train_races':train['レースコード'].nunique(),'holdout_races':test['レースコード'].nunique(),
                        'train_entries':len(train),'holdout_entries':len(test),'known_style_holdout_entries':int(x.style.notna().sum()),
                        'role_rows':len(roles),'pair_rows':len(pe),'triple_rows':len(tr),'path_rows':len(paths),'top_signal_rows':len(sm)}])
    meta.to_csv(out/'run_meta.csv',index=False)
    print(meta.to_string(index=False))
    if not sm.empty:
        print('\nTOP SIGNALS')
        print(sm.head(25).to_string(index=False))

if __name__=='__main__':
    main()
