#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel, latest_profile

SRC = Path('source/data')
OUT = Path('docs/racers.json')


def safe_num(v, digits=1):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    try:
        return round(float(v), digits)
    except Exception:
        return None


def perf(g: pd.DataFrame) -> dict:
    if g.empty:
        return {'n': 0, 'win1': None, 'top2': None, 'top3': None, 'avg_st': None, 'avg_finish': None}
    normal = g[g.get('f_start', 0).fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {'n': int(len(g)), 'win1': safe_num(g['finish'].eq(1).mean()*100,1), 'top2': safe_num(g['finish'].le(2).mean()*100,1), 'top3': safe_num(g['finish'].le(3).mean()*100,1), 'avg_st': safe_num(normal['actual_st'].mean(),3) if 'actual_st' in normal.columns else None, 'avg_finish': safe_num(g['finish'].mean(),2)}


def method_mix(g: pd.DataFrame) -> dict:
    if g.empty or '決まり手' not in g.columns: return {}
    wins = g[g['finish'].eq(1) & g['決まり手'].notna()]
    if wins.empty: return {}
    c = wins['決まり手'].astype(str).str.replace(r'[\s　]+','',regex=True).value_counts(); total=c.sum()
    return {k: round(v/total*100,1) for k,v in c.items() if k}


def course_rows(g: pd.DataFrame) -> list[dict]:
    rows=[]
    if 'actual_course' not in g.columns: return rows
    for course in range(1,7):
        h=g[g['actual_course'].eq(course)]; p=perf(h); p['course']=course; p['methods']=method_mix(h); rows.append(p)
    return rows


def strongest_course(rows: list[dict]):
    valid=[r for r in rows if r['n']>=12 and r['win1'] is not None]
    return None if not valid else max(valid,key=lambda r:r['win1'])['course']


def public_features(g6,g1):
    out=[]; p6,p1=perf(g6),perf(g1)
    if p6['n']>=30 and p1['n']>=50 and p6['top3'] is not None and p1['top3'] is not None:
        d=p6['top3']-p1['top3']
        if d>=6: out.append({'label':'最近6か月で成績上向き','confidence':'中','note':f'3連対率 半年 {p6["top3"]}% / 1年 {p1["top3"]}%'})
        elif d<=-6: out.append({'label':'最近6か月で成績下向き','confidence':'中','note':f'3連対率 半年 {p6["top3"]}% / 1年 {p1["top3"]}%'})
    return out


def phase_stats(g):
    if g.empty: return {'n':0,'course_adj':None,'top3':None,'avg_finish':None,'avg_st':None,'opp':None}
    normal=g[g['f_start'].fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {'n':int(len(g)),'course_adj':safe_num(g['course_adjusted_perf'].mean(),3),'top3':safe_num(g['finish'].le(3).mean()*100,1),'avg_finish':safe_num(g['finish'].mean(),2),'avg_st':safe_num(normal['actual_st'].mean(),3) if 'actual_st' in normal.columns else None,'opp':safe_num(g['opponent_strength'].mean(),2) if 'opponent_strength' in g.columns else None}


def late_meet_memo(g,label):
    if g.empty or 'day_no' not in g.columns: return {'window':label,'status':'不足','reason':'節日次データなし'}
    x=g.dropna(subset=['day_no']).copy(); early=x[x['day_no'].between(1,2)]; middle=x[x['day_no'].between(3,4)]; late=x[x['day_no']>=5]
    e,m,l=phase_stats(early),phase_stats(middle),phase_stats(late); result={'window':label,'early':e,'middle':m,'late':l}
    if e['n']<10 or l['n']<10 or e['course_adj'] is None or l['course_adj'] is None:
        result.update({'status':'不足','confidence':'低','note':'初盤または終盤の標本不足'}); return result
    delta=l['course_adj']-e['course_adj']; top3=None if e['top3'] is None or l['top3'] is None else l['top3']-e['top3']; finish=None if e['avg_finish'] is None or l['avg_finish'] is None else e['avg_finish']-l['avg_finish']
    result.update({'late_minus_early_course_adj':safe_num(delta,3),'late_minus_early_top3_pt':safe_num(top3,1) if top3 is not None else None,'early_minus_late_avg_finish':safe_num(finish,2) if finish is not None else None})
    up=(top3 is not None and top3>=4) or (finish is not None and finish>=.15); down=(top3 is not None and top3<=-4) or (finish is not None and finish<=-.15)
    status='後半上昇候補' if delta>=.18 and up else ('後半低下候補' if delta<=-.18 and down else '明確な後半差なし')
    nmin=min(e['n'],l['n']); conf='高' if nmin>=30 and abs(delta)>=.25 else ('中' if nmin>=15 else '低'); result.update({'status':status,'confidence':conf}); return result


def opponent_resilience_memo(g,label):
    if g.empty or 'opponent_strength' not in g.columns or 'course_adjusted_perf' not in g.columns: return {'window':label,'status':'不足','reason':'相手強度データなし'}
    x=g.dropna(subset=['opponent_strength','course_adjusted_perf','finish']).copy()
    if len(x)<40: return {'window':label,'status':'不足','reason':'全体標本不足','n':int(len(x))}
    q25,q75=x['opponent_strength'].quantile(.25),x['opponent_strength'].quantile(.75); w,s=phase_stats(x[x['opponent_strength']<=q25]),phase_stats(x[x['opponent_strength']>=q75]); result={'window':label,'weak_field':w,'strong_field':s,'weak_cut':safe_num(q25,3),'strong_cut':safe_num(q75,3)}
    if w['n']<10 or s['n']<10 or w['course_adj'] is None or s['course_adj'] is None: result.update({'status':'不足','confidence':'低','note':'強弱グループの標本不足'}); return result
    cad=s['course_adj']-w['course_adj']; top3=None if s['top3'] is None or w['top3'] is None else s['top3']-w['top3']; finish=None if s['avg_finish'] is None or w['avg_finish'] is None else w['avg_finish']-s['avg_finish']
    result.update({'strong_minus_weak_course_adj':safe_num(cad,3),'strong_minus_weak_top3_pt':safe_num(top3,1) if top3 is not None else None,'weak_minus_strong_avg_finish':safe_num(finish,2) if finish is not None else None})
    status='強豪相手でも崩れにくい候補' if cad>=.10 and ((top3 is not None and top3>=-2) or (finish is not None and finish>=-.10)) else ('強豪相手で低下候補' if cad<=-.20 and ((top3 is not None and top3<=-5) or (finish is not None and finish<=-.20)) else '明確な相手強度差なし')
    nmin=min(w['n'],s['n']); conf='高' if nmin>=30 and abs(cad)>=.18 else ('中' if nmin>=15 else '低'); result.update({'status':status,'confidence':conf}); return result


def venue_memo(g,label):
    if g.empty or 'レース場' not in g.columns or 'course_adjusted_perf' not in g.columns: return {'window':label,'status':'不足','reason':'場別データなし','venues':[]}
    x=g.dropna(subset=['レース場','course_adjusted_perf','finish']).copy()
    if len(x)<40: return {'window':label,'status':'不足','reason':'全体標本不足','n':int(len(x)),'venues':[]}
    overall=phase_stats(x); rows=[]
    for venue,h in x.groupby('レース場'):
        s=phase_stats(h)
        if s['n']<6 or s['course_adj'] is None or overall['course_adj'] is None: continue
        cad=s['course_adj']-overall['course_adj']; t=None if s['top3'] is None or overall['top3'] is None else s['top3']-overall['top3']; f=None if s['avg_finish'] is None or overall['avg_finish'] is None else overall['avg_finish']-s['avg_finish']
        rows.append({'venue':str(venue),'n':s['n'],'stats':s,'course_adj_vs_overall':safe_num(cad,3),'top3_vs_overall_pt':safe_num(t,1) if t is not None else None,'overall_minus_venue_avg_finish':safe_num(f,2) if f is not None else None})
    rows.sort(key=lambda r:abs(r['course_adj_vs_overall'] or 0),reverse=True)
    return {'window':label,'status':'集計済','overall':overall,'venues':rows[:8]}


def reproduced_venue_traits(vm6,vm1):
    a={r['venue']:r for r in vm6.get('venues',[]) if r.get('n',0)>=6}; b={r['venue']:r for r in vm1.get('venues',[]) if r.get('n',0)>=10}; out=[]
    for venue in sorted(set(a)&set(b)):
        r6,r1=a[venue],b[venue]; d6,d1=r6.get('course_adj_vs_overall'),r1.get('course_adj_vs_overall')
        if d6 is None or d1 is None: continue
        t6,t1=r6.get('top3_vs_overall_pt'),r1.get('top3_vs_overall_pt'); f6,f1=r6.get('overall_minus_venue_avg_finish'),r1.get('overall_minus_venue_avg_finish')
        good=((t6 is not None and t6>=4) or (f6 is not None and f6>=.15)) and ((t1 is not None and t1>=3) or (f1 is not None and f1>=.10)); bad=((t6 is not None and t6<=-4) or (f6 is not None and f6<=-.15)) and ((t1 is not None and t1<=-3) or (f1 is not None and f1<=-.10))
        if d6>=.18 and d1>=.14 and good: status='得意場候補'
        elif d6<=-.18 and d1<=-.14 and bad: status='苦手場候補'
        else: continue
        conf='高' if min(r6['n'],r1['n'])>=15 and min(abs(d6),abs(d1))>=.20 else '中'; out.append({'venue':venue,'status':status,'confidence':conf,'six_month':r6,'one_year':r1})
    out.sort(key=lambda r:min(abs(r['six_month']['course_adj_vs_overall']),abs(r['one_year']['course_adj_vs_overall'])),reverse=True); return out[:4]


def build_player_memo(g6,g1):
    lm6,lm1=late_meet_memo(g6,'6か月'),late_meet_memo(g1,'1年'); or6,or1=opponent_resilience_memo(g6,'6か月'),opponent_resilience_memo(g1,'1年'); vm6,vm1=venue_memo(g6,'6か月'),venue_memo(g1,'1年'); vt=reproduced_venue_traits(vm6,vm1); tags=[]
    if lm6.get('status')=='後半上昇候補' and lm1.get('status')=='後半上昇候補': tags.append('節後半に上げる')
    if or6.get('status')=='強豪相手でも崩れにくい候補' and or1.get('status')=='強豪相手でも崩れにくい候補': tags.append('強豪相手でも崩れにくい')
    tags += [f"{v['venue']}・{v['status']}" for v in vt]
    return {'late_meet_6m':lm6,'late_meet_1y':lm1,'late_meet_reproduced':'節後半に上げる' in tags,'opponent_resilience_6m':or6,'opponent_resilience_1y':or1,'opponent_resilience_reproduced':'強豪相手でも崩れにくい' in tags,'venue_6m':vm6,'venue_1y':vm1,'venue_reproduced_traits':vt,'memo_tags':tags,'visibility':'internal_memo'}


def main():
    cards=load_many(str(SRC/'programs/race_cards/*/*/*.csv')); results=load_many(str(SRC/'results/realtime/*/*/*.csv')); title=load_many(str(SRC/'programs/title/*/*/*.csv'))
    if cards.empty or results.empty: raise SystemExit('race cards/results not found')
    cl=cards_to_long(cards); panel=build_panel(cl,results_to_long(results),title).dropna(subset=['race_date','regno','finish']).copy(); panel['race_date']=pd.to_datetime(panel['race_date']); asof=panel['race_date'].max().normalize(); start_1y=asof-pd.Timedelta(days=365); start_6m=asof-pd.Timedelta(days=183); p1=panel[panel['race_date'].ge(start_1y)].copy(); p6=panel[panel['race_date'].ge(start_6m)].copy(); prof=latest_profile(cl).set_index('regno'); racers=[]
    for reg,g1 in p1.groupby('regno'):
        if reg not in prof.index: continue
        g6=p6[p6['regno'].eq(reg)]; row=prof.loc[reg]; c1,c6=course_rows(g1),course_rows(g6); name=str(row.get('name','') or '').strip()
        if not name or name.lower()=='nan': continue
        racers.append({'regno':int(reg),'name':name,'class':None if pd.isna(row.get('class_grade')) else str(row.get('class_grade')),'branch':None if pd.isna(row.get('branch')) else str(row.get('branch')),'birthplace':None if pd.isna(row.get('birthplace')) else str(row.get('birthplace')),'age':None if pd.isna(row.get('age')) else int(float(row.get('age'))),'term':None if pd.isna(row.get('term')) else str(row.get('term')),'six_month':perf(g6),'one_year':perf(g1),'courses_6m':c6,'courses_1y':c1,'strongest_course_6m':strongest_course(c6),'features':public_features(g6,g1),'player_memo':build_player_memo(g6,g1)})
    racers.sort(key=lambda x:(x['class'] or '',x['one_year']['win1'] or 0,x['regno']),reverse=True); payload={'updated':asof.strftime('%Y-%m-%d'),'window_6m_start':start_6m.strftime('%Y-%m-%d'),'window_1y_start':start_1y.strftime('%Y-%m-%d'),'count':len(racers),'racers':racers,'notes':['半年・1年は実レース結果から再集計','何コース何型という分類は公開しない','節後半上昇・相手強度耐性・場依存など分析途中の情報は選手メモに蓄積','心理・相手依存などは半年/1年で再現し裏が取れたものだけ公開候補に昇格']}; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); print(f'wrote {OUT} racers={len(racers)} asof={asof.date()}')


if __name__=='__main__': main()
