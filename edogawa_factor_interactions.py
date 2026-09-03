#!/usr/bin/env python3
from pathlib import Path
import itertools, math
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long

from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.inspection import permutation_importance

SRC=Path("source/data")
OUT=Path("artifacts/edogawa_factor_interactions")
OUT.mkdir(parents=True,exist_ok=True)
VENUE="03"

def venue_code_from_race(s):
    x=s.astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    return x.str[-4:-2]

def prep():
    cards=load_many(str(SRC/"programs/race_cards/*/*/*.csv"))
    pay=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    sui=load_many(str(SRC/"previews/sui/*/*/*.csv"))
    if cards.empty or pay.empty:
        raise SystemExit("cards/payout missing")
    cl=cards_to_long(cards)
    cl["_venue"]=venue_code_from_race(cl["レースコード"])
    cl=cl[cl["_venue"].eq(VENUE)].copy()
    cl["race_date"]=pd.to_datetime(cl["レース日"],errors="coerce")

    # One row per race with boat-specific pre-race values.
    fields=["pub_avg_st","national_win_rate","local_win_rate","motor_2rate","motor_3rate","boat_2rate","f_count"]
    rows=[]
    for rc,g in cl.groupby("レースコード"):
        if g.boat_no.nunique()!=6: continue
        r={"レースコード":rc,"race_date":g.race_date.iloc[0]}
        for b in range(1,7):
            z=g[g.boat_no.eq(b)]
            if z.empty: continue
            z=z.iloc[0]
            for f in fields:
                r[f"b{b}_{f}"]=pd.to_numeric(z.get(f),errors="coerce")
        # relative / structural features
        for b in range(1,7):
            for f in ["pub_avg_st","national_win_rate","local_win_rate","motor_2rate"]:
                vals=[r.get(f"b{k}_{f}",np.nan) for k in range(1,7)]
                x=r.get(f"b{b}_{f}",np.nan)
                oth=np.nanmean([v for k,v in enumerate(vals,1) if k!=b])
                if f=="pub_avg_st":
                    r[f"b{b}_{f}_edge"]=oth-x
                else:
                    r[f"b{b}_{f}_edge"]=x-oth
        # wall / attack context around 2-4
        r["st_gap_3_vs_2"]=r.get("b2_pub_avg_st",np.nan)-r.get("b3_pub_avg_st",np.nan)
        r["st_gap_3_vs_4"]=r.get("b4_pub_avg_st",np.nan)-r.get("b3_pub_avg_st",np.nan)
        r["st_gap_4_vs_3"]=r.get("b3_pub_avg_st",np.nan)-r.get("b4_pub_avg_st",np.nan)
        r["local_gap_3_vs_2"]=r.get("b3_local_win_rate",np.nan)-r.get("b2_local_win_rate",np.nan)
        r["motor_gap_3_vs_2"]=r.get("b3_motor_2rate",np.nan)-r.get("b2_motor_2rate",np.nan)
        r["local_gap_4_vs_3"]=r.get("b4_local_win_rate",np.nan)-r.get("b3_local_win_rate",np.nan)
        r["motor_gap_4_vs_3"]=r.get("b4_motor_2rate",np.nan)-r.get("b3_motor_2rate",np.nan)
        rows.append(r)
    base=pd.DataFrame(rows)

    p=pay.copy()
    p["_venue"]=venue_code_from_race(p["レースコード"])
    p=p[p["_venue"].eq(VENUE)].drop_duplicates("レースコード",keep="last")
    def p3(v):
        try:
            xs=[int(x) for x in str(v).replace("=","-").split("-")]
            return xs if len(xs)==3 else None
        except: return None
    p["_tri"]=p["3連単_組番"].map(p3)
    p=p[p["_tri"].notna()].copy()
    p["y_1lose"]=p["_tri"].map(lambda x:int(x[0]!=1))
    p["y_3win"]=p["_tri"].map(lambda x:int(x[0]==3))
    p["y_4win"]=p["_tri"].map(lambda x:int(x[0]==4))
    p["y_centerwin"]=p["_tri"].map(lambda x:int(x[0] in (3,4)))
    p["y_4top2"]=p["_tri"].map(lambda x:int(4 in x[:2]))
    p["y_3top2"]=p["_tri"].map(lambda x:int(3 in x[:2]))
    keep=["レースコード","y_1lose","y_3win","y_4win","y_centerwin","y_4top2","y_3top2"]
    z=base.merge(p[keep],on="レースコード",how="inner")

    if not sui.empty:
        s=sui.copy()
        s["_venue"]=venue_code_from_race(s["レースコード"])
        s=s[s["_venue"].eq(VENUE)].drop_duplicates("レースコード")
        s["wind"]=pd.to_numeric(s["風速(m)"],errors="coerce")
        s["wave"]=pd.to_numeric(s["波の高さ(cm)"],errors="coerce")
        s["wind_dir"]=s["風向"].astype(str)
        z=z.merge(s[["レースコード","wind","wave","wind_dir"]],on="レースコード",how="left")
    return z.sort_values(["race_date","レースコード"]).reset_index(drop=True)

def chrono(df):
    a=int(len(df)*.60); b=int(len(df)*.80)
    return df.iloc[:a].copy(),df.iloc[a:b].copy(),df.iloc[b:].copy()

def feature_cols(df):
    num=[c for c in df.columns if c.startswith("b") or c.startswith("st_gap_") or c.startswith("local_gap_") or c.startswith("motor_gap_")]
    num += [c for c in ["wind","wave"] if c in df.columns]
    cat=[c for c in ["wind_dir"] if c in df.columns]
    return num,cat

def make_lr(num,cat):
    pre=ColumnTransformer([
      ("num",Pipeline([("imp",SimpleImputer(strategy="median")),("sc",StandardScaler())]),num),
      ("cat",Pipeline([("imp",SimpleImputer(strategy="most_frequent")),("oh",OneHotEncoder(handle_unknown="ignore"))]),cat),
    ])
    return Pipeline([("pre",pre),("lr",LogisticRegression(max_iter=3000,C=0.5))])

def perm_importance_pct(train,val,target,num,cat):
    # HistGradient on numeric-only for stable feature-level permutation importance.
    Xtr=train[num].copy(); Xv=val[num].copy()
    med=Xtr.median(numeric_only=True)
    Xtr=Xtr.fillna(med); Xv=Xv.fillna(med)
    ytr=train[target].astype(int); yv=val[target].astype(int)
    m=HistGradientBoostingClassifier(max_depth=3,learning_rate=.05,max_iter=250,l2_regularization=1.0,random_state=7)
    m.fit(Xtr,ytr)
    base=roc_auc_score(yv,m.predict_proba(Xv)[:,1]) if yv.nunique()>1 else np.nan
    pi=permutation_importance(m,Xv,yv,n_repeats=8,random_state=7,scoring="roc_auc")
    imp=np.maximum(pi.importances_mean,0)
    s=imp.sum()
    rows=[]
    for f,v in zip(num,imp):
        rows.append({"target":target,"feature":f,"importance_pct":(v/s*100 if s>0 else 0.0),"auc_drop":float(v),"val_auc":base})
    return pd.DataFrame(rows).sort_values("importance_pct",ascending=False)

def interaction_scan(train,val,oos,target,num):
    # Search a compact set of meaningful interaction candidates.
    cand=[c for c in num if any(k in c for k in ["edge","gap_","wind","wave"])]
    # prefer attack-related and boat1 fragility variables
    pref=[c for c in cand if any(k in c for k in ["b1_","b2_","b3_","b4_","st_gap_","local_gap_","motor_gap_","wind","wave"])]
    cand=pref[:28]
    rows=[]
    for a,b in itertools.combinations(cand,2):
        def design(d):
            x=d[[a,b]].copy()
            x[a]=pd.to_numeric(x[a],errors="coerce")
            x[b]=pd.to_numeric(x[b],errors="coerce")
            x["interaction"]=x[a]*x[b]
            return x
        Xtr=design(train); Xv=design(val); Xo=design(oos)
        med=Xtr.median()
        Xtr=Xtr.fillna(med); Xv=Xv.fillna(med); Xo=Xo.fillna(med)
        ytr=train[target].astype(int); yv=val[target].astype(int); yo=oos[target].astype(int)
        if ytr.nunique()<2 or yv.nunique()<2 or yo.nunique()<2: continue
        base=LogisticRegression(max_iter=2000).fit(Xtr[[a,b]],ytr)
        inter=LogisticRegression(max_iter=2000).fit(Xtr[[a,b,"interaction"]],ytr)
        vb=log_loss(yv,base.predict_proba(Xv[[a,b]])[:,1])
        vi=log_loss(yv,inter.predict_proba(Xv[[a,b,"interaction"]])[:,1])
        ob=log_loss(yo,base.predict_proba(Xo[[a,b]])[:,1])
        oi=log_loss(yo,inter.predict_proba(Xo[[a,b,"interaction"]])[:,1])
        rows.append({"target":target,"a":a,"b":b,"val_logloss_gain":vb-vi,"oos_logloss_gain":ob-oi,
                     "stable_interaction":bool((vb-vi)>0 and (ob-oi)>0)})
    return pd.DataFrame(rows).sort_values(["stable_interaction","oos_logloss_gain","val_logloss_gain"],ascending=[False,False,False])

def bucket_effects(df,target,features):
    rows=[]
    for f in features:
        x=pd.to_numeric(df[f],errors="coerce")
        if x.notna().sum()<100: continue
        try:
            q=pd.qcut(x,4,duplicates="drop")
        except: continue
        for bucket,g in df.assign(_q=q).dropna(subset=["_q"]).groupby("_q",observed=True):
            rows.append({"target":target,"feature":f,"bucket":str(bucket),"n":len(g),
                         "event_rate_pct":g[target].mean()*100})
    return pd.DataFrame(rows)

def adjusted_binary_effect(df,target,exposure,confounders):
    # Observational adjusted association using propensity weighting.
    d=df[[target,exposure]+confounders].copy()
    d=d.dropna(subset=[target,exposure])
    if len(d)<200: return None
    x=pd.to_numeric(d[exposure],errors="coerce")
    thr=x.quantile(.75)
    d["_t"]=(x>=thr).astype(int)
    if d["_t"].mean()<.1 or d["_t"].mean()>.9: return None
    X=d[confounders].copy()
    for c in confounders: X[c]=pd.to_numeric(X[c],errors="coerce")
    med=X.median(); X=X.fillna(med)
    prop=LogisticRegression(max_iter=2000).fit(X,d["_t"]).predict_proba(X)[:,1]
    prop=np.clip(prop,.05,.95)
    t=d["_t"].to_numpy(); y=d[target].astype(float).to_numpy()
    wt=t/prop + (1-t)/(1-prop)
    mu1=np.sum(wt*t*y)/np.sum(wt*t)
    mu0=np.sum(wt*(1-t)*y)/np.sum(wt*(1-t))
    return {"target":target,"exposure":exposure,"threshold":float(thr),"n":len(d),
            "treated_rate_pct":float(t.mean()*100),"adjusted_event_treated_pct":float(mu1*100),
            "adjusted_event_control_pct":float(mu0*100),"adjusted_diff_pt":float((mu1-mu0)*100)}

def main():
    z=prep()
    if len(z)<1000: raise SystemExit(f"too few rows {len(z)}")
    disc,val,oos=chrono(z)
    num,cat=feature_cols(z)
    targets=["y_1lose","y_3win","y_4win","y_centerwin","y_3top2","y_4top2"]

    all_imp=[]; all_int=[]; all_buck=[]; all_causal=[]
    for target in targets:
        imp=perm_importance_pct(disc,val,target,num,cat)
        all_imp.append(imp)
        top=imp.head(12)["feature"].tolist()
        all_buck.append(bucket_effects(oos,target,top))
        ints=interaction_scan(disc,val,oos,target,num)
        all_int.append(ints.head(120))
        conf=[c for c in ["wind","wave","b1_national_win_rate_edge","b1_local_win_rate_edge","b1_motor_2rate_edge",
                           "b2_national_win_rate_edge","b2_local_win_rate_edge","b2_motor_2rate_edge"] if c in num]
        exposures=[c for c in ["st_gap_3_vs_2","local_gap_3_vs_2","motor_gap_3_vs_2","st_gap_4_vs_3","local_gap_4_vs_3","motor_gap_4_vs_3",
                               "b3_pub_avg_st_edge","b3_local_win_rate_edge","b3_motor_2rate_edge",
                               "b4_pub_avg_st_edge","b4_local_win_rate_edge","b4_motor_2rate_edge"] if c in num]
        for e in exposures:
            cf=[c for c in conf if c!=e]
            r=adjusted_binary_effect(z,target,e,cf)
            if r: all_causal.append(r)

    imp=pd.concat(all_imp,ignore_index=True)
    inter=pd.concat(all_int,ignore_index=True)
    buck=pd.concat(all_buck,ignore_index=True) if all_buck else pd.DataFrame()
    causal=pd.DataFrame(all_causal)
    imp.to_csv(OUT/"importance_pct.csv",index=False)
    inter.to_csv(OUT/"interaction_gains.csv",index=False)
    buck.to_csv(OUT/"oos_bucket_event_rates.csv",index=False)
    causal.to_csv(OUT/"adjusted_effect_candidates.csv",index=False)

    # concise ranked summary
    stable=inter[inter["stable_interaction"]].copy()
    summary=pd.DataFrame([{
      "races":len(z),"date_min":str(z.race_date.min().date()),"date_max":str(z.race_date.max().date()),
      "disc":len(disc),"val":len(val),"oos":len(oos),
      "stable_interactions":len(stable),
      "adjusted_effect_candidates":len(causal)
    }])
    summary.to_csv(OUT/"summary.csv",index=False)
    print(summary.to_string(index=False))
    print("\nIMPORTANCE TOP")
    print(imp.sort_values(["target","importance_pct"],ascending=[True,False]).groupby("target").head(8).to_string(index=False))
    print("\nSTABLE INTERACTIONS TOP")
    print(stable.head(30).to_string(index=False))
    print("\nADJUSTED EFFECTS TOP")
    if len(causal):
        cc=causal.assign(absdiff=causal.adjusted_diff_pt.abs()).sort_values("absdiff",ascending=False).head(30)
        print(cc.to_string(index=False))

if __name__=="__main__":
    main()
