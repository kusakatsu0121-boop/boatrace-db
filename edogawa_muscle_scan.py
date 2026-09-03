#!/usr/bin/env python3
from pathlib import Path
import itertools
import numpy as np
import pandas as pd
from racer_directory import load_many

SRC=Path("source/data")
OUT=Path("artifacts/edogawa_muscle_scan")
OUT.mkdir(parents=True,exist_ok=True)
VENUE="03"
PATHS=list(itertools.permutations(range(1,7),3))

def venue_mask(df):
    if "レース場" in df.columns:
        s=df["レース場"].astype(str)
        n=s.str.extract(r"(\d+)")[0].str.zfill(2)
        return n.eq(VENUE) | s.str.contains("江戸川",na=False)
    code=df["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    return code.str[-4:-2].eq(VENUE)

def parse3(v):
    try:
        xs=[int(x) for x in str(v).replace("=","-").split("-")]
        return tuple(xs) if len(xs)==3 and len(set(xs))==3 else None
    except Exception:
        return None

def split3(df):
    df=df.sort_values(["レース日","レースコード"]).reset_index(drop=True)
    a=int(len(df)*.60); b=int(len(df)*.80)
    return {"DISC":df.iloc[:a].copy(),"VAL":df.iloc[a:b].copy(),"OOS":df.iloc[b:].copy()}

def calc_fixed(g, hitmask, stake_per_race):
    n=len(g)
    if n==0: return {"n":0,"hits":0,"roi":np.nan,"roi_dropmax":np.nan,"max_payout":np.nan}
    rets=np.where(hitmask,pd.to_numeric(g["payout"],errors="coerce").fillna(0),0.0)
    ret=float(np.sum(rets)); mx=float(np.max(rets)) if len(rets) else 0.0
    stake=stake_per_race*n
    return {"n":n,"hits":int(np.sum(hitmask)),"roi":ret/stake*100,"roi_dropmax":(ret-mx)/stake*100,"max_payout":mx}

def main():
    pay=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    if pay.empty: raise SystemExit("payouts missing")
    pay=pay[venue_mask(pay)].copy()
    pay["レース日"]=pd.to_datetime(pay["レース日"],errors="coerce")
    pay["winner"]=pay["3連単_組番"].map(parse3)
    pay["payout"]=pd.to_numeric(pay["3連単_払戻金"],errors="coerce")
    pay=pay.dropna(subset=["レース日","winner","payout"]).drop_duplicates("レースコード",keep="last")
    pay=pay.sort_values(["レース日","レースコード"]).reset_index(drop=True)
    if len(pay)<500: raise SystemExit(f"too few Edogawa payout races: {len(pay)}")
    splits=split3(pay)

    rows=[]
    for path in PATHS:
        rec={"kind":"EXACT","ticket":"-".join(map(str,path)),"stake_per_race":100}
        for s,d in splits.items():
            m=calc_fixed(d,d["winner"].map(lambda x:x==path).to_numpy(),100)
            rec.update({f"{s}_{k}":v for k,v in m.items()})
        rec["stable"]=bool(rec["DISC_n"]>=500 and rec["VAL_n"]>=100 and rec["OOS_n"]>=100 and rec["DISC_roi"]>100 and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and rec["DISC_roi_dropmax"]>=90 and rec["VAL_roi_dropmax"]>=90 and rec["OOS_roi_dropmax"]>=90)
        rec["robust_score"]=min(rec["VAL_roi"],rec["OOS_roi"],rec["OOS_roi_dropmax"])
        rows.append(rec)

    # winner-second muscle: a-b-* = four 100-yen tickets per race
    for a in range(1,7):
        for b in range(1,7):
            if a==b: continue
            rec={"kind":"AB_STAR","ticket":f"{a}-{b}-*","stake_per_race":400}
            for s,d in splits.items():
                hit=d["winner"].map(lambda x:x[0]==a and x[1]==b).to_numpy()
                m=calc_fixed(d,hit,400)
                rec.update({f"{s}_{k}":v for k,v in m.items()})
            rec["stable"]=bool(rec["DISC_n"]>=500 and rec["VAL_n"]>=100 and rec["OOS_n"]>=100 and rec["DISC_roi"]>100 and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and rec["DISC_roi_dropmax"]>=90 and rec["VAL_roi_dropmax"]>=90 and rec["OOS_roi_dropmax"]>=90)
            rec["robust_score"]=min(rec["VAL_roi"],rec["OOS_roi"],rec["OOS_roi_dropmax"])
            rows.append(rec)

    # winner-third muscle: a-*-c = four second-place tickets
    for a in range(1,7):
        for c in range(1,7):
            if a==c: continue
            rec={"kind":"A_STAR_C","ticket":f"{a}-*-{c}","stake_per_race":400}
            for s,d in splits.items():
                hit=d["winner"].map(lambda x:x[0]==a and x[2]==c).to_numpy()
                m=calc_fixed(d,hit,400)
                rec.update({f"{s}_{k}":v for k,v in m.items()})
            rec["stable"]=bool(rec["DISC_n"]>=500 and rec["VAL_n"]>=100 and rec["OOS_n"]>=100 and rec["DISC_roi"]>100 and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and rec["DISC_roi_dropmax"]>=90 and rec["VAL_roi_dropmax"]>=90 and rec["OOS_roi_dropmax"]>=90)
            rec["robust_score"]=min(rec["VAL_roi"],rec["OOS_roi"],rec["OOS_roi_dropmax"])
            rows.append(rec)

    out=pd.DataFrame(rows).sort_values(["stable","robust_score","OOS_n"],ascending=[False,False,False])
    out.to_csv(OUT/"all_muscle_candidates.csv",index=False)
    out[out["stable"]].to_csv(OUT/"stable_candidates.csv",index=False)

    # monthly diagnostic for top discovery candidates only; not used for selection
    top=out.sort_values("DISC_roi",ascending=False).head(30)
    mons=[]
    for r in top.itertuples(index=False):
        for month,g in pay.groupby(pay["レース日"].dt.to_period("M").astype(str)):
            if r.kind=="EXACT":
                p=parse3(r.ticket); hit=g["winner"].map(lambda x:x==p).to_numpy()
            elif r.kind=="AB_STAR":
                a,b=map(int,r.ticket.replace("-*","").split("-")[:2]); hit=g["winner"].map(lambda x:x[0]==a and x[1]==b).to_numpy()
            else:
                a=int(r.ticket.split("-")[0]); c=int(r.ticket.split("-")[2]); hit=g["winner"].map(lambda x:x[0]==a and x[2]==c).to_numpy()
            m=calc_fixed(g,hit,int(r.stake_per_race))
            mons.append({"kind":r.kind,"ticket":r.ticket,"month":month,**m})
    pd.DataFrame(mons).to_csv(OUT/"monthly_top30.csv",index=False)

    summary=pd.DataFrame([{
        "races":len(pay),"date_min":str(pay["レース日"].min().date()),"date_max":str(pay["レース日"].max().date()),
        "disc":len(splits["DISC"]),"val":len(splits["VAL"]),"oos":len(splits["OOS"]),
        "candidates":len(out),"stable_candidates":int(out["stable"].sum())
    }])
    summary.to_csv(OUT/"summary.csv",index=False)
    print(summary.to_string(index=False))
    print("\nTOP")
    print(out.head(30).to_string(index=False))

if __name__=="__main__":
    main()
