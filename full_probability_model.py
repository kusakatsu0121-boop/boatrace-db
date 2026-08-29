#!/usr/bin/env python3
from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import backtest_ev as be
from racer_directory import load_many, cards_to_long, results_to_long, build_panel, latest_profile
from strategy_features import build_roles
from adjusted_winrate import build_adjusted_tables

# Strict chronology. No July/August result is used in training/calibration.
BASE_TRAIN_START = pd.Timestamp('2025-01-01')
ROLE_TRAIN_END = pd.Timestamp('2026-05-01')
CAL_START = pd.Timestamp('2026-05-01')
CAL_END = pd.Timestamp('2026-06-30')
TEST_START = pd.Timestamp('2026-07-01')
TEST_END = pd.Timestamp('2026-08-28')
PRIMARY_EV = 1.15
MAX_BETS = 4
EV_GRID = [1.05, 1.10, 1.15, 1.20, 1.30, 1.50]
PATHS = be.PATHS
PAIRS = [(1,2),(1,3),(1,4),(2,3),(2,4),(3,4)]
LABELS = ['style','finish_role']


def num(s):
    return pd.to_numeric(s, errors='coerce')


def tkz_to_long(tkz: pd.DataFrame) -> pd.DataFrame:
    parts=[]
    if tkz.empty:
        return pd.DataFrame()
    for boat in range(1,7):
        cols=['レースコード']
        mp={}
        for jp,en in [('体重(kg)','weight'),('体重調整(kg)','weight_adjust'),('展示タイム','ex_time'),('チルト','tilt')]:
            c=f'艇{boat}_{jp}'
            if c in tkz.columns:
                cols.append(c); mp[c]=en
        q=tkz[cols].copy().rename(columns=mp); q['boat_no']=boat
        for c in mp.values():
            q[c]=num(q[c])
        parts.append(q)
    return pd.concat(parts,ignore_index=True)


def series_form_to_long(cards: pd.DataFrame) -> pd.DataFrame:
    parts=[]
    for boat in range(1,7):
        stcols=[]; fcols=[]
        for d in range(1,8):
            for run in (1,2):
                sc=f'艇{boat}_節D{d}走{run}_ST'; fc=f'艇{boat}_節D{d}走{run}_着順'
                if sc in cards.columns: stcols.append(sc)
                if fc in cards.columns: fcols.append(fc)
        q=cards[['レースコード']].copy(); q['boat_no']=boat
        if fcols:
            f=cards[fcols].apply(pd.to_numeric,errors='coerce')
            q['series_n']=f.notna().sum(axis=1)
            q['series_avg_finish']=f.mean(axis=1)
            q['series_top3']=(f.le(3).sum(axis=1)/q['series_n'].replace(0,np.nan))
            q['series_win']=(f.eq(1).sum(axis=1)/q['series_n'].replace(0,np.nan))
        else:
            q['series_n']=0; q['series_avg_finish']=np.nan; q['series_top3']=np.nan; q['series_win']=np.nan
        if stcols:
            s=cards[stcols].apply(pd.to_numeric,errors='coerce')
            q['series_avg_st']=s.mean(axis=1)
        else:
            q['series_avg_st']=np.nan
        parts.append(q)
    return pd.concat(parts,ignore_index=True)


def grade_num(v):
    s=str(v or '').upper().replace(' ','')
    if 'SG' in s: return 6
    if 'PG1' in s: return 5
    if 'G1' in s: return 4
    if 'G2' in s: return 3
    if 'G3' in s: return 2
    return 1


def class_num(v):
    return {'A1':4,'A2':3,'B1':2,'B2':1}.get(str(v).upper(),0)


def build_entries(src: Path):
    cards=load_many(str(src/'programs/race_cards/*/*/*.csv'))
    results=load_many(str(src/'results/realtime/*/*/*.csv'))
    title=load_many(str(src/'programs/title/*/*/*.csv'))
    stt=load_many(str(src/'previews/stt/*/*/*.csv'))
    tkz=load_many(str(src/'previews/tkz/*/*/*.csv'))
    sui=load_many(str(src/'previews/sui/*/*/*.csv'))
    odds=load_many(str(src/'previews/od3/*/*/*.csv'))
    payouts=load_many(str(src/'results/payouts/*/*/*.csv'))

    cl=cards_to_long(cards)
    rl=results_to_long(results)
    panel=build_panel(cl,rl,title)
    panel=panel.dropna(subset=['race_date','regno','actual_course','finish']).copy()

    expo=be.stt_to_long(stt)
    form=series_form_to_long(cards)
    ex=tkz_to_long(tkz)
    out=rl[['レースコード','boat_no','finish']].drop_duplicates(['レースコード','boat_no'],keep='last')

    e=expo.merge(cl,on=['レースコード','boat_no'],how='inner')
    e=e.merge(form,on=['レースコード','boat_no'],how='left')
    if not ex.empty: e=e.merge(ex,on=['レースコード','boat_no'],how='left')
    e=e.merge(out,on=['レースコード','boat_no'],how='left')
    e['race_date']=pd.to_datetime(e['レース日'],errors='coerce')

    if not sui.empty:
        scols=[c for c in ['レースコード','風速(m)','風向','波の高さ(cm)','天候','気温(℃)','水温(℃)'] if c in sui.columns]
        s=sui[scols].drop_duplicates('レースコード',keep='last').copy()
        ren={'風速(m)':'wind_speed','風向':'wind_dir','波の高さ(cm)':'wave','天候':'weather','気温(℃)':'air_temp','水温(℃)':'water_temp'}
        s=s.rename(columns=ren)
        for c in ['wind_speed','wind_dir','wave','weather','air_temp','water_temp']:
            if c in s: s[c]=num(s[c])
        e=e.merge(s,on='レースコード',how='left')

    if not title.empty:
        tcols=[c for c in ['レースコード','グレード','レース名','日次'] if c in title.columns]
        e=e.merge(title[tcols].drop_duplicates('レースコード',keep='last'),on='レースコード',how='left')
    e['race_grade_num']=e.get('グレード',pd.Series('',index=e.index)).map(grade_num)
    e['class_num']=e.get('class_grade',pd.Series('',index=e.index)).map(class_num)
    e['venue']=num(e.get('レース場コード'))

    # Only complete six-entry exhibition lineups are modelled.
    good=e.groupby('レースコード').agg(n=('boat_no','size'),courses=('expo_course',lambda s:set(pd.to_numeric(s,errors='coerce').dropna().astype(int))))
    good=good[(good.n==6)&good.courses.map(lambda x:x==set(range(1,7)))].index
    e=e[e['レースコード'].isin(good)].copy()

    # Leakage-safe pre-race relative information.
    rel_cols=['pub_avg_st','national_win_rate','national_2rate','national_3rate','local_win_rate','local_2rate','local_3rate',
              'motor_2rate','motor_3rate','boat_2rate','boat_3rate','expo_st','ex_time','weight','tilt',
              'series_avg_finish','series_top3','series_win','series_avg_st']
    for c in rel_cols:
        if c not in e: e[c]=np.nan
        e[c]=num(e[c])
        mean=e.groupby('レースコード')[c].transform('mean')
        e[f'{c}_rel']=e[c]-mean
        e[f'{c}_rank']=e.groupby('レースコード')[c].rank(method='average',ascending=(c in ['pub_avg_st','expo_st','ex_time','series_avg_finish','series_avg_st']))

    # Build frozen historical course/type and opponent-adjusted ratings only from data before May.
    hist=panel[panel.race_date<ROLE_TRAIN_END].copy()
    roles=build_roles(hist)
    rolecols=['regno','course','p1','p2','p3','top2','top3','allow_escape','avg_st','st_edge','style','finish_role','outer_special']
    e=e.merge(roles[rolecols],left_on=['regno','expo_course'],right_on=['regno','course'],how='left').drop(columns=['course'])
    roles_base=roles.groupby('course')[['p1','p2','p3']].mean().rename(columns={'p1':'base_p1','p2':'base_p2','p3':'base_p3'}).reset_index()
    e=e.merge(roles_base,left_on='expo_course',right_on='course',how='left').drop(columns=['course'])
    for p in (1,2,3):
        e[f'role_ratio{p}']=(e[f'p{p}']/e[f'base_p{p}']).clip(.25,4.0).fillna(1.0)

    prof=latest_profile(cl[pd.to_datetime(cl['レース日'],errors='coerce')<ROLE_TRAIN_END].copy())
    adj=build_adjusted_tables(hist,prof)['racer_adjusted']
    keep=[c for c in ['regno','base_winrate','current_winrate','rating_quality','form_adjustment'] if c in adj.columns]
    e=e.merge(adj[keep],on='regno',how='left')
    mu=e['current_winrate'].mean(); sd=e['current_winrate'].std(ddof=0)
    e['adjusted_rating_z']=((e['current_winrate']-mu)/(sd if sd and np.isfinite(sd) else 1.0)).fillna(0.0)

    # Existing base-race machinery is only for odds/payout mapping at the final EV layer.
    base,_=be.build_base_races(expo,cl,odds,payouts)
    return e,panel,roles,base


def feature_columns(e: pd.DataFrame):
    raw=['age','f_count','l_count','pub_avg_st','national_win_rate','national_2rate','national_3rate','local_win_rate','local_2rate','local_3rate',
         'motor_2rate','motor_3rate','boat_2rate','boat_3rate','expo_st','ex_time','weight','weight_adjust','tilt','series_n','series_avg_finish','series_top3','series_win','series_avg_st',
         'wind_speed','wave','air_temp','water_temp','race_grade_num','class_num']
    rel=[]
    for c in ['pub_avg_st','national_win_rate','national_2rate','national_3rate','local_win_rate','local_2rate','local_3rate','motor_2rate','motor_3rate','boat_2rate','boat_3rate','expo_st','ex_time','weight','tilt','series_avg_finish','series_top3','series_win','series_avg_st']:
        rel += [f'{c}_rel',f'{c}_rank']
    nums=[c for c in raw+rel if c in e.columns]
    cats=[c for c in ['expo_course','boat_no','venue','class_grade','weather','wind_dir'] if c in e.columns]
    return nums,cats


def fit_base_model(e: pd.DataFrame):
    train=e[(e.race_date>=BASE_TRAIN_START)&(e.race_date<ROLE_TRAIN_END)&e.finish.notna()].copy()
    train['y']=np.where(train.finish.eq(1),0,np.where(train.finish.eq(2),1,np.where(train.finish.eq(3),2,3)))
    nums,cats=feature_columns(e)
    pre=ColumnTransformer([
        ('num',Pipeline([('imp',SimpleImputer(strategy='median')),('sc',StandardScaler())]),nums),
        ('cat',Pipeline([('imp',SimpleImputer(strategy='most_frequent')),('oh',OneHotEncoder(handle_unknown='ignore',min_frequency=10))]),cats),
    ])
    clf=LogisticRegression(max_iter=350,C=.55,solver='lbfgs')
    pipe=Pipeline([('pre',pre),('clf',clf)])
    pipe.fit(train[nums+cats],train['y'])
    return pipe,nums,cats,len(train)


def base_entry_probs(model,e,nums,cats):
    pp=model.predict_proba(e[nums+cats])
    cls=list(model.named_steps['clf'].classes_)
    out=np.zeros((len(e),3),dtype=float)
    for pos in (0,1,2):
        if pos in cls: out[:,pos]=pp[:,cls.index(pos)]
    return np.clip(out,1e-7,1.0)


def winner_path_for_group(g):
    z=g.dropna(subset=['finish']).sort_values('finish')
    if len(z)<3:return None
    t=tuple(int(x) for x in z.head(3)['expo_course'])
    return be.PATH_TO_IDX.get(t)


def path_from_entries(g, entry_pp, alpha=.0,beta=.0,temp=1.0,signal_lookup=None):
    g=g.sort_values('expo_course')
    if list(g.expo_course.astype(int))!=list(range(1,7)): return None
    idx=g.index.to_numpy()
    w=entry_pp[idx].copy()
    rr=g[['role_ratio1','role_ratio2','role_ratio3']].to_numpy(float)
    rr=np.where(np.isfinite(rr),rr,1.0)
    rz=g['adjusted_rating_z'].fillna(0).to_numpy(float)[:,None]
    w=w*np.power(rr,alpha)*np.exp(beta*rz)
    w=w/np.maximum(w.sum(axis=0,keepdims=True),1e-12)
    p=np.zeros(len(PATHS),float)
    for i,(a,b,c) in enumerate(PATHS): p[i]=w[a-1,0]*w[b-1,1]*w[c-1,2]
    p=p/np.maximum(p.sum(),1e-12)
    if temp!=1.0:
        p=np.power(np.clip(p,1e-12,1),1.0/temp); p/=p.sum()

    if signal_lookup:
        best={}
        for label in LABELS:
            for a,b in PAIRS:
                ta=str(g.iloc[a-1][label]); tb=str(g.iloc[b-1][label])
                if ta in ('nan','SAMPLE_LOW') or tb in ('nan','SAMPLE_LOW'): continue
                for tc,pos,lift,strength in signal_lookup.get((label,a,ta,b,tb),[]):
                    key=(tc,pos)
                    if key not in best or strength>best[key][1]: best[key]=(lift,strength)
        if best:
            marg=np.zeros((3,6),float)
            for i,(a,b,c) in enumerate(PATHS): marg[0,a-1]+=p[i]; marg[1,b-1]+=p[i]; marg[2,c-1]+=p[i]
            ratios=np.ones((3,6),float)
            for (tc,pos),(lift,_) in best.items():
                base=marg[pos-1,tc-1]
                if base>0:
                    ratios[pos-1,tc-1]=np.clip((base+lift)/base,.70,1.40)
            for i,(a,b,c) in enumerate(PATHS):
                p[i]*=(ratios[0,a-1]*ratios[1,b-1]*ratios[2,c-1])**0.5
            p/=p.sum()
    return p


def make_path_predictions(e,entry_pp,start,end,alpha,beta,temp,signal_lookup=None):
    out={}; winners={}
    z=e[(e.race_date>=pd.Timestamp(start))&(e.race_date<=pd.Timestamp(end))].copy()
    for code,g in z.groupby('レースコード'):
        p=path_from_entries(g,entry_pp,alpha,beta,temp,signal_lookup)
        if p is None: continue
        out[str(code)]=p
        winners[str(code)]=winner_path_for_group(g)
    return out,winners


def nll_for(pred,winners):
    vals=[]
    for code,p in pred.items():
        wi=winners.get(code)
        if wi is not None and wi>=0: vals.append(-math.log(max(float(p[wi]),1e-12)))
    return float(np.mean(vals)) if vals else np.inf


def tune_calibration(e,entry_pp):
    rows=[]; best=None
    for alpha in [0.0,.25,.50,.75,1.0]:
        for beta in [0.0,.08,.16,.24]:
            for temp in [.80,1.00,1.20,1.40,1.60]:
                pr,win=make_path_predictions(e,entry_pp,CAL_START,CAL_END,alpha,beta,temp)
                loss=nll_for(pr,win)
                rows.append({'alpha_role':alpha,'beta_adjusted':beta,'temperature':temp,'cal_nll':loss,'races':len(pr)})
                if best is None or loss<best[0]: best=(loss,alpha,beta,temp)
    return best,pd.DataFrame(rows).sort_values('cal_nll')


def race_frame_for_signals(e,pred,winners):
    rows=[]
    z=e[(e.race_date>=CAL_START)&(e.race_date<=CAL_END)].copy()
    for code,g in z.groupby('レースコード'):
        code=str(code)
        if code not in pred or winners.get(code) is None: continue
        gg=g.sort_values('expo_course')
        if len(gg)!=6: continue
        p=pred[code]
        marg=np.zeros((3,6),float)
        for i,(a,b,c) in enumerate(PATHS): marg[0,a-1]+=p[i]; marg[1,b-1]+=p[i]; marg[2,c-1]+=p[i]
        wi=winners[code]; wp=PATHS[wi]
        r={'レースコード':code,'race_date':gg.race_date.iloc[0]}
        for c in range(1,7):
            rr=gg.iloc[c-1]
            r[f'style_c{c}']=rr.get('style'); r[f'finish_role_c{c}']=rr.get('finish_role')
            for pos in (1,2,3):
                r[f'exp_{pos}_{c}']=marg[pos-1,c-1]
                r[f'obs_{pos}_{c}']=float(wp[pos-1]==c)
                r[f'resid_{pos}_{c}']=r[f'obs_{pos}_{c}']-r[f'exp_{pos}_{c}']
        rows.append(r)
    return pd.DataFrame(rows)


def discover_pair_signals(rf: pd.DataFrame):
    rows=[]
    if rf.empty:return pd.DataFrame()
    rf=rf.copy(); rf['half']=np.where(rf.race_date<pd.Timestamp('2026-06-01'),'MAY','JUN')
    for label in LABELS:
        for a,b in PAIRS:
            ca=f'{label}_c{a}'; cb=f'{label}_c{b}'
            d=rf[rf[ca].notna()&rf[cb].notna()&rf[ca].ne('SAMPLE_LOW')&rf[cb].ne('SAMPLE_LOW')]
            if d.empty: continue
            for tc in range(1,7):
                for pos in (1,2,3):
                    col=f'resid_{pos}_{tc}'
                    overall=float(d[col].mean()); ma=d.groupby(ca)[col].mean(); mb=d.groupby(cb)[col].mean()
                    pg=d.groupby([ca,cb])[col].agg(['mean','size','std']).reset_index()
                    for rr in pg.itertuples(index=False):
                        n=int(rr.size)
                        if n<60:continue
                        A=getattr(rr,ca); B=getattr(rr,cb)
                        lift=float(rr.mean-ma.get(A,0)-mb.get(B,0)+overall)
                        se=float(rr.std/math.sqrt(n)) if pd.notna(rr.std) and rr.std>0 else np.nan
                        t=lift/se if np.isfinite(se) and se>0 else np.nan
                        hs=[]; ok=True
                        for h in ('MAY','JUN'):
                            dh=d[d.half.eq(h)]; gh=dh[(dh[ca]==A)&(dh[cb]==B)]
                            if len(gh)<20:ok=False;break
                            hl=float(gh[col].mean()-dh.groupby(ca)[col].mean().get(A,0)-dh.groupby(cb)[col].mean().get(B,0)+dh[col].mean())
                            hs.append(hl)
                        if not ok or np.sign(lift)!=np.sign(hs[0]) or np.sign(lift)!=np.sign(hs[1]):continue
                        if abs(lift)<.018 or not np.isfinite(t) or abs(t)<1.25:continue
                        rows.append({'label_kind':label,'course_a':a,'type_a':A,'course_b':b,'type_b':B,'target_course':tc,'position':pos,'n':n,'lift':lift,'t_approx':t,'may_lift':hs[0],'jun_lift':hs[1]})
    s=pd.DataFrame(rows)
    return s.sort_values('t_approx',key=lambda x:x.abs(),ascending=False) if len(s) else s


def signal_lookup(s):
    out={}
    if s.empty:return out
    for r in s.itertuples(index=False):
        k=(r.label_kind,int(r.course_a),str(r.type_a),int(r.course_b),str(r.type_b))
        out.setdefault(k,[]).append((int(r.target_course),int(r.position),float(r.lift),abs(float(r.t_approx))))
    return out


def evaluate_model(base,model_probs):
    races=base[(base.race_date>=TEST_START)&(base.race_date<=TEST_END)].reset_index(drop=True)
    odds_course,q,winner_path,_=be.odds_in_exhibition_course_order(races)
    rows=[]; metric=[]
    for i,r in races.iterrows():
        code=str(r['レースコード']); p=model_probs.get(code)
        wi=int(winner_path[i])
        if p is None or wi<0: continue
        metric.append({'race_date':r.race_date,'model_nll':-math.log(max(p[wi],1e-12)),'market_nll':-math.log(max(q[i,wi],1e-12)) if np.isfinite(q[i,wi]) else np.nan,'model_top_hit':int(np.argmax(p)==wi),'market_top_hit':int(np.nanargmax(q[i])==wi) if np.isfinite(q[i]).any() else 0,'winner_model_p':p[wi]})
        ev=p*odds_course[i]
        eligible=np.flatnonzero(np.isfinite(ev)&(ev>=PRIMARY_EV))
        order=eligible[np.argsort(ev[eligible])[::-1]][:MAX_BETS]
        for rank,pidx in enumerate(order,start=1):
            hit=int(pidx==wi)
            rows.append({'レースコード':code,'race_date':r.race_date,'rank_in_race':rank,'course_trifecta':'-'.join(map(str,PATHS[pidx])),'snapshot_odds':float(odds_course[i,pidx]),'model_prob':float(p[pidx]),'model_ev':float(ev[pidx]),'hit':hit,'return_per_100':float(r.payout) if hit else 0.0})
    return pd.DataFrame(rows),pd.DataFrame(metric),races,odds_course,winner_path


def summarize(name,b):
    s=be.summarize_bets(b)
    return {'period':name,**s,'races_bet':int(b['レースコード'].nunique()) if len(b) else 0}


def sensitivity(base,model_probs):
    races=base[(base.race_date>=TEST_START)&(base.race_date<=TEST_END)].reset_index(drop=True)
    odds_course,_,winner_path,_=be.odds_in_exhibition_course_order(races)
    rows=[]
    for th in EV_GRID:
        bets=[]
        for i,r in races.iterrows():
            p=model_probs.get(str(r['レースコード'])); wi=int(winner_path[i])
            if p is None or wi<0:continue
            ev=p*odds_course[i]; el=np.flatnonzero(np.isfinite(ev)&(ev>=th)); order=el[np.argsort(ev[el])[::-1]][:MAX_BETS]
            for pidx in order:
                bets.append({'レースコード':r['レースコード'],'hit':int(pidx==wi),'return_per_100':float(r.payout) if pidx==wi else 0.0})
        b=pd.DataFrame(bets); st=be.summarize_bets(b)
        rows.append({'ev_threshold':th,'max_bets':MAX_BETS,'races_bet':int(b['レースコード'].nunique()) if len(b) else 0,**st})
    return pd.DataFrame(rows)


def main():
    out=Path('artifacts/full_probability'); out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=build_entries(Path('source/data'))
    model,nums,cats,train_rows=fit_base_model(e)
    entry_pp=base_entry_probs(model,e,nums,cats)

    best,tuning=tune_calibration(e,entry_pp)
    _,alpha,beta,temp=best
    cal_pred,cal_win=make_path_predictions(e,entry_pp,CAL_START,CAL_END,alpha,beta,temp)
    rf=race_frame_for_signals(e,cal_pred,cal_win)
    signals=discover_pair_signals(rf); lk=signal_lookup(signals)
    test_pred,test_win=make_path_predictions(e,entry_pp,TEST_START,TEST_END,alpha,beta,temp,lk)

    bets,metrics,_,_,_=evaluate_model(base,test_pred)
    july=bets[(bets.race_date>=pd.Timestamp('2026-07-01'))&(bets.race_date<=pd.Timestamp('2026-07-31'))] if len(bets) else bets
    aug=bets[(bets.race_date>=pd.Timestamp('2026-08-01'))&(bets.race_date<=pd.Timestamp('2026-08-28'))] if len(bets) else bets
    summary=pd.DataFrame([summarize('JULY',july),summarize('AUGUST',aug),summarize('POOLED',bets)])
    sens=sensitivity(base,test_pred)
    mm=pd.DataFrame([{
        'test_races_scored':len(metrics),
        'model_path_nll':metrics.model_nll.mean() if len(metrics) else np.nan,
        'market_path_nll':metrics.market_nll.mean() if len(metrics) else np.nan,
        'model_top_path_hit_rate':metrics.model_top_hit.mean() if len(metrics) else np.nan,
        'market_top_path_hit_rate':metrics.market_top_hit.mean() if len(metrics) else np.nan,
        'avg_model_prob_on_winner':metrics.winner_model_p.mean() if len(metrics) else np.nan,
    }])
    meta=pd.DataFrame([{'base_train_start':str(BASE_TRAIN_START.date()),'role_train_end':str(ROLE_TRAIN_END.date()),'cal_start':str(CAL_START.date()),'cal_end':str(CAL_END.date()),'test_start':str(TEST_START.date()),'test_end':str(TEST_END.date()),'train_entry_rows':train_rows,'all_entry_rows':len(e),'numeric_features':len(nums),'categorical_features':len(cats),'alpha_role':alpha,'beta_adjusted':beta,'temperature':temp,'pair_signals':len(signals),'primary_ev':PRIMARY_EV,'max_bets':MAX_BETS}])

    summary.to_csv(out/'summary.csv',index=False); sens.to_csv(out/'sensitivity.csv',index=False); mm.to_csv(out/'model_metrics.csv',index=False); meta.to_csv(out/'meta.csv',index=False)
    tuning.to_csv(out/'calibration_grid.csv',index=False); signals.to_csv(out/'pair_signals.csv',index=False); bets.to_csv(out/'bets.csv',index=False); metrics.to_csv(out/'race_metrics.csv',index=False)
    print('INDEPENDENT FULL PROBABILITY MODEL -- ODDS NOT USED TO CREATE PROBABILITIES')
    print('\nMETA'); print(meta.to_string(index=False))
    print('\nMODEL QUALITY'); print(mm.to_string(index=False))
    print('\nPRIMARY EV>=1.15 MAX4'); print(summary.to_string(index=False))
    print('\nEV SENSITIVITY'); print(sens.to_string(index=False))
    print('\nTOP PAIR SIGNALS'); print(signals.head(20).to_string(index=False) if len(signals) else 'none')

if __name__=='__main__':
    main()
