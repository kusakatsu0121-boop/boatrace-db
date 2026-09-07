#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from racer_directory import load_many, cards_to_long, results_to_long, build_panel, latest_profile

SRC=Path('source/data'); OUT=Path('docs/racers.json')

def safe_num(v,digits=1):
    try:
        if v is None or not np.isfinite(float(v)): return None
        return round(float(v),digits)
    except Exception: return None

def perf(g):
    if g.empty: return {'n':0,'win1':None,'top2':None,'top3':None,'avg_st':None,'avg_finish':None}
    normal=g[g['f_start'].fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {'n':int(len(g)),'win1':safe_num(g['finish'].eq(1).mean()*100,1),'top2':safe_num(g['finish'].le(2).mean()*100,1),'top3':safe_num(g['finish'].le(3).mean()*100,1),'avg_st':safe_num(normal['actual_st'].mean(),3) if 'actual_st' in normal.columns else None,'avg_finish':safe_num(g['finish'].mean(),2)}

def phase_stats(g):
    if g.empty: return {'n':0,'course_adj':None,'top3':None,'avg_finish':None,'avg_st':None,'opp':None}
    normal=g[g['f_start'].fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {'n':int(len(g)),'course_adj':safe_num(g['course_adjusted_perf'].mean(),3),'top3':safe_num(g['finish'].le(3).mean()*100,1),'avg_finish':safe_num(g['finish'].mean(),2),'avg_st':safe_num(normal['actual_st'].mean(),3) if 'actual_st' in normal.columns else None,'opp':safe_num(g['opponent_strength'].mean(),2) if 'opponent_strength' in g.columns else None}

def method_mix(g):
    if g.empty or '決まり手' not in g.columns: return {}
    wins=g[g['finish'].eq(1)&g['決まり手'].notna()]
    if wins.empty:return {}
    c=wins['決まり手'].astype(str).str.replace(r'[\s　]+','',regex=True).value_counts(); total=c.sum()
    return {k:round(v/total*100,1) for k,v in c.items() if k}

def course_rows(g):
    if 'actual_course' not in g.columns:return []
    out=[]
    for c in range(1,7):
        h=g[g['actual_course'].eq(c)]; p=perf(h); p['course']=c; p['methods']=method_mix(h); out.append(p)
    return out

def strongest_course(rows):
    valid=[r for r in rows if r['n']>=12 and r['win1'] is not None]
    return None if not valid else max(valid,key=lambda r:r['win1'])['course']

def public_features(g6,g1):
    out=[]; a,b=perf(g6),perf(g1)
    if a['n']>=30 and b['n']>=50 and a['top3'] is not None and b['top3'] is not None:
        d=a['top3']-b['top3']
        if d>=6: out.append({'label':'最近6か月で成績上向き','confidence':'中','note':f'3連対率 半年 {a["top3"]}% / 1年 {b["top3"]}%'})
        elif d<=-6: out.append({'label':'最近6か月で成績下向き','confidence':'中','note':f'3連対率 半年 {a["top3"]}% / 1年 {b["top3"]}%'})
    return out

def late_meet_memo(g,label):
    if g.empty or 'day_no' not in g.columns:return {'window':label,'status':'不足','reason':'節日次データなし'}
    x=g.dropna(subset=['day_no']); e=phase_stats(x[x.day_no.between(1,2)]); m=phase_stats(x[x.day_no.between(3,4)]); l=phase_stats(x[x.day_no>=5]); r={'window':label,'early':e,'middle':m,'late':l}
    if e['n']<10 or l['n']<10 or e['course_adj'] is None or l['course_adj'] is None:r.update({'status':'不足','confidence':'低','note':'初盤または終盤の標本不足'});return r
    cad=l['course_adj']-e['course_adj']; t=l['top3']-e['top3']; f=e['avg_finish']-l['avg_finish']; r.update({'late_minus_early_course_adj':safe_num(cad,3),'late_minus_early_top3_pt':safe_num(t,1),'early_minus_late_avg_finish':safe_num(f,2)})
    up=t>=4 or f>=.15; down=t<=-4 or f<=-.15; status='後半上昇候補' if cad>=.18 and up else ('後半低下候補' if cad<=-.18 and down else '明確な後半差なし'); n=min(e['n'],l['n']); conf='高' if n>=30 and abs(cad)>=.25 else ('中' if n>=15 else '低');r.update({'status':status,'confidence':conf});return r

def opponent_resilience_memo(g,label):
    if g.empty or not {'opponent_strength','course_adjusted_perf'}.issubset(g.columns):return {'window':label,'status':'不足','reason':'相手強度データなし'}
    x=g.dropna(subset=['opponent_strength','course_adjusted_perf','finish'])
    if len(x)<40:return {'window':label,'status':'不足','reason':'全体標本不足','n':int(len(x))}
    q25,q75=x.opponent_strength.quantile(.25),x.opponent_strength.quantile(.75); w=phase_stats(x[x.opponent_strength<=q25]); s=phase_stats(x[x.opponent_strength>=q75]); r={'window':label,'weak_field':w,'strong_field':s,'weak_cut':safe_num(q25,3),'strong_cut':safe_num(q75,3)}
    if w['n']<10 or s['n']<10:r.update({'status':'不足','confidence':'低'});return r
    cad=s['course_adj']-w['course_adj']; t=s['top3']-w['top3']; f=w['avg_finish']-s['avg_finish']; r.update({'strong_minus_weak_course_adj':safe_num(cad,3),'strong_minus_weak_top3_pt':safe_num(t,1),'weak_minus_strong_avg_finish':safe_num(f,2)}); status='強豪相手でも崩れにくい候補' if cad>=.10 and (t>=-2 or f>=-.10) else ('強豪相手で低下候補' if cad<=-.20 and (t<=-5 or f<=-.20) else '明確な相手強度差なし'); n=min(w['n'],s['n']); r.update({'status':status,'confidence':'高' if n>=30 and abs(cad)>=.18 else ('中' if n>=15 else '低')});return r

def venue_memo(g,label):
    if g.empty or 'レース場' not in g.columns:return {'window':label,'status':'不足','venues':[]}
    x=g.dropna(subset=['レース場','course_adjusted_perf','finish'])
    if len(x)<40:return {'window':label,'status':'不足','venues':[]}
    overall=phase_stats(x); rows=[]
    for venue,h in x.groupby('レース場'):
        s=phase_stats(h)
        if s['n']<6:continue
        rows.append({'venue':str(venue),'n':s['n'],'stats':s,'course_adj_vs_overall':safe_num(s['course_adj']-overall['course_adj'],3),'top3_vs_overall_pt':safe_num(s['top3']-overall['top3'],1),'overall_minus_venue_avg_finish':safe_num(overall['avg_finish']-s['avg_finish'],2)})
    rows.sort(key=lambda r:abs(r['course_adj_vs_overall'] or 0),reverse=True);return {'window':label,'status':'集計済','overall':overall,'venues':rows[:8]}

def reproduced_venue_traits(a,b):
    x={r['venue']:r for r in a.get('venues',[]) if r['n']>=6}; y={r['venue']:r for r in b.get('venues',[]) if r['n']>=10}; out=[]
    for v in set(x)&set(y):
        p,q=x[v],y[v]; d6,d1=p['course_adj_vs_overall'],q['course_adj_vs_overall']; good=(p['top3_vs_overall_pt']>=4 or p['overall_minus_venue_avg_finish']>=.15) and (q['top3_vs_overall_pt']>=3 or q['overall_minus_venue_avg_finish']>=.10); bad=(p['top3_vs_overall_pt']<=-4 or p['overall_minus_venue_avg_finish']<=-.15) and (q['top3_vs_overall_pt']<=-3 or q['overall_minus_venue_avg_finish']<=-.10)
        status='得意場候補' if d6>=.18 and d1>=.14 and good else ('苦手場候補' if d6<=-.18 and d1<=-.14 and bad else None)
        if status:out.append({'venue':v,'status':status,'confidence':'高' if min(p['n'],q['n'])>=15 and min(abs(d6),abs(d1))>=.20 else '中','six_month':p,'one_year':q})
    return sorted(out,key=lambda r:min(abs(r['six_month']['course_adj_vs_overall']),abs(r['one_year']['course_adj_vs_overall'])),reverse=True)[:4]

def condition_resilience(g,label,col,target_values,min_n=10):
    if g.empty or col not in g.columns:return {'window':label,'status':'不足','reason':f'{col}データなし'}
    x=g.dropna(subset=[col,'course_adjusted_perf','finish']); target=x[x[col].astype(str).isin(target_values)]; base=x[~x.index.isin(target.index)]; ts,bs=phase_stats(target),phase_stats(base); r={'window':label,'condition':col,'target_values':sorted(target_values),'target':ts,'other':bs}
    if ts['n']<min_n or bs['n']<20 or ts['course_adj'] is None or bs['course_adj'] is None:r.update({'status':'不足','confidence':'低','note':'条件側または比較側の標本不足'});return r
    cad=ts['course_adj']-bs['course_adj']; t=ts['top3']-bs['top3']; f=bs['avg_finish']-ts['avg_finish']; r.update({'condition_minus_other_course_adj':safe_num(cad,3),'condition_minus_other_top3_pt':safe_num(t,1),'other_minus_condition_avg_finish':safe_num(f,2)})
    if cad>=.16 and (t>=3 or f>=.12):status='耐性候補'
    elif cad<=-.16 and (t<=-3 or f<=-.12):status='苦手候補'
    else:status='明確な差なし'
    n=min(ts['n'],bs['n']);r.update({'status':status,'confidence':'高' if n>=30 and abs(cad)>=.22 else ('中' if n>=15 else '低')});return r

def water_memo(g,label):
    return {'window':label,'strong_wind':condition_resilience(g,label,'wind_band',{'4-5m','6m+'},10),'high_wave':condition_resilience(g,label,'wave_band',{'6-10cm','11cm+'},10)}

def reproduced_water_traits(w6,w1):
    out=[]
    for key,label in [('strong_wind','強風'),('high_wave','高波')]:
        a,b=w6[key],w1[key]
        if a.get('status')==b.get('status') and a.get('status') in {'耐性候補','苦手候補'}:
            out.append({'condition':label,'status':a['status'],'confidence':'高' if a.get('confidence')=='高' and b.get('confidence')=='高' else '中','six_month':a,'one_year':b})
    return out

def rebound_memo(g,label):
    need={'race_date','レース場','finish','course_adjusted_perf'}
    if g.empty or not need.issubset(g.columns):return {'window':label,'status':'不足','reason':'直前出走判定データなし'}
    x=g.dropna(subset=['race_date','レース場','finish','course_adjusted_perf']).copy()
    x=x.sort_values(['race_date','race_no_num','レースコード'])
    x['prev_finish']=x['finish'].shift(1); x['prev_date']=x['race_date'].shift(1); x['prev_venue']=x['レース場'].shift(1)
    x['gap_days']=(x['race_date']-x['prev_date']).dt.days
    x=x[(x['prev_venue'].astype(str)==x['レース場'].astype(str)) & x['gap_days'].between(0,2) & x['prev_finish'].notna()]
    after_good=phase_stats(x[x['prev_finish']<=3]); after_bad=phase_stats(x[x['prev_finish']>=4])
    r={'window':label,'after_top3':after_good,'after_4plus':after_bad,'same_venue_gap_days_max':2}
    if after_good['n']<10 or after_bad['n']<10 or after_good['course_adj'] is None or after_bad['course_adj'] is None:
        r.update({'status':'不足','confidence':'低','note':'直前3着以内/4着以下のどちらかが10走未満'});return r
    cad=after_bad['course_adj']-after_good['course_adj']; t=after_bad['top3']-after_good['top3']; f=after_good['avg_finish']-after_bad['avg_finish']
    r.update({'after_bad_minus_good_course_adj':safe_num(cad,3),'after_bad_minus_good_top3_pt':safe_num(t,1),'after_good_minus_bad_avg_finish':safe_num(f,2)})
    if cad>=.16 and (t>=3 or f>=.12):status='前走不振後に立て直す候補'
    elif cad<=-.16 and (t<=-3 or f<=-.12):status='前走不振を引きずる候補'
    else:status='前走結果による明確な差なし'
    n=min(after_good['n'],after_bad['n']); r.update({'status':status,'confidence':'高' if n>=25 and abs(cad)>=.22 else ('中' if n>=15 else '低')});return r

def reproduced_rebound_trait(r6,r1):
    if r6.get('status')==r1.get('status') and r6.get('status') in {'前走不振後に立て直す候補','前走不振を引きずる候補'}:
        return {'status':r6['status'],'confidence':'高' if r6.get('confidence')=='高' and r1.get('confidence')=='高' else '中','six_month':r6,'one_year':r1}
    return None

def build_player_memo(g6,g1):
    lm6,lm1=late_meet_memo(g6,'6か月'),late_meet_memo(g1,'1年'); or6,or1=opponent_resilience_memo(g6,'6か月'),opponent_resilience_memo(g1,'1年'); vm6,vm1=venue_memo(g6,'6か月'),venue_memo(g1,'1年'); vt=reproduced_venue_traits(vm6,vm1); wm6,wm1=water_memo(g6,'6か月'),water_memo(g1,'1年'); wt=reproduced_water_traits(wm6,wm1); rb6,rb1=rebound_memo(g6,'6か月'),rebound_memo(g1,'1年'); rbt=reproduced_rebound_trait(rb6,rb1); tags=[]
    if lm6.get('status')=='後半上昇候補' and lm1.get('status')=='後半上昇候補':tags.append('節後半に上げる')
    if or6.get('status')=='強豪相手でも崩れにくい候補' and or1.get('status')=='強豪相手でも崩れにくい候補':tags.append('強豪相手でも崩れにくい')
    tags += [f"{v['venue']}・{v['status']}" for v in vt] + [f"{w['condition']}・{w['status']}" for w in wt]
    if rbt:tags.append(rbt['status'].replace('候補',''))
    return {'late_meet_6m':lm6,'late_meet_1y':lm1,'opponent_resilience_6m':or6,'opponent_resilience_1y':or1,'venue_6m':vm6,'venue_1y':vm1,'venue_reproduced_traits':vt,'water_6m':wm6,'water_1y':wm1,'water_reproduced_traits':wt,'rebound_6m':rb6,'rebound_1y':rb1,'rebound_reproduced_trait':rbt,'memo_tags':tags,'visibility':'internal_memo'}

def main():
    cards=load_many(str(SRC/'programs/race_cards/*/*/*.csv')); results=load_many(str(SRC/'results/realtime/*/*/*.csv')); title=load_many(str(SRC/'programs/title/*/*/*.csv'))
    if cards.empty or results.empty:raise SystemExit('race cards/results not found')
    cl=cards_to_long(cards); panel=build_panel(cl,results_to_long(results),title).dropna(subset=['race_date','regno','finish']).copy(); panel['race_date']=pd.to_datetime(panel['race_date']); asof=panel['race_date'].max().normalize(); start1=asof-pd.Timedelta(days=365); start6=asof-pd.Timedelta(days=183); p1=panel[panel.race_date.ge(start1)]; p6=panel[panel.race_date.ge(start6)]; prof=latest_profile(cl).set_index('regno'); racers=[]
    for reg,g1 in p1.groupby('regno'):
        if reg not in prof.index:continue
        g6=p6[p6.regno.eq(reg)]; row=prof.loc[reg]; c1,c6=course_rows(g1),course_rows(g6); name=str(row.get('name','') or '').strip()
        if not name or name.lower()=='nan':continue
        racers.append({'regno':int(reg),'name':name,'class':None if pd.isna(row.get('class_grade')) else str(row.get('class_grade')),'branch':None if pd.isna(row.get('branch')) else str(row.get('branch')),'birthplace':None if pd.isna(row.get('birthplace')) else str(row.get('birthplace')),'age':None if pd.isna(row.get('age')) else int(float(row.get('age'))),'term':None if pd.isna(row.get('term')) else str(row.get('term')),'six_month':perf(g6),'one_year':perf(g1),'courses_6m':c6,'courses_1y':c1,'strongest_course_6m':strongest_course(c6),'features':public_features(g6,g1),'player_memo':build_player_memo(g6,g1)})
    racers.sort(key=lambda x:(x['class'] or '',x['one_year']['win1'] or 0,x['regno']),reverse=True); payload={'updated':asof.strftime('%Y-%m-%d'),'window_6m_start':start6.strftime('%Y-%m-%d'),'window_1y_start':start1.strftime('%Y-%m-%d'),'count':len(racers),'racers':racers,'notes':['半年・1年は実レース結果から再集計','何コース何型という分類は公開しない','節後半・相手強度・場依存・強風/高波耐性・前走不振後の立て直しは選手メモに蓄積','半年/1年で再現し裏が取れたものだけ公開候補に昇格']}; OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8'); print(f'wrote {OUT} racers={len(racers)} asof={asof.date()}')
if __name__=='__main__':main()
