#!/usr/bin/env python3
from pathlib import Path
import numpy as np, pandas as pd
from racer_directory import load_many, cards_to_long

SRC=Path("source/data")
OUT=Path("artifacts/edogawa_head_metric")
OUT.mkdir(parents=True,exist_ok=True)
VENUE="03"

def norm_exact(v,n):
    try:
        xs=[int(x) for x in str(v).replace("=","-").split("-")]
        return tuple(xs) if len(xs)==n else None
    except: return None

def norm_set(v,n):
    try:
        xs=tuple(sorted(int(x) for x in str(v).replace("=","-").split("-")))
        return xs if len(xs)==n else None
    except: return None

def split3(df):
    df=df.sort_values(["race_date","レースコード"]).reset_index(drop=True)
    a=int(len(df)*.60); b=int(len(df)*.80)
    return {"DISC":df.iloc[:a],"VAL":df.iloc[a:b],"OOS":df.iloc[b:]}

def main():
    cards=load_many(str(SRC/"programs/race_cards/*/*/*.csv"))
    pay=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    cl=cards_to_long(cards)
    code=cl["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    cl=cl[code.str[-4:-2].eq(VENUE)].copy()
    cl["race_date"]=pd.to_datetime(cl["レース日"],errors="coerce")
    metrics=[
      ("local_win_rate",False),
      ("national_win_rate",False),
      ("pub_avg_st",True),
      ("motor_2rate",False),
    ]
    races=[]
    for rc,g in cl.groupby("レースコード"):
        if g.boat_no.nunique()!=6: continue
        r={"レースコード":rc,"race_date":g.race_date.iloc[0]}
        for m,asc in metrics:
            gg=g[["boat_no",m]].dropna().sort_values([m,"boat_no"],ascending=[asc,True])
            if len(gg)>=3:
                r[m+"_1"]=int(gg.iloc[0].boat_no)
                r[m+"_2"]=int(gg.iloc[1].boat_no)
                r[m+"_3"]=int(gg.iloc[2].boat_no)
        races.append(r)
    base=pd.DataFrame(races)
    p=pay.copy()
    pcode=p["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    p=p[pcode.str[-4:-2].eq(VENUE)].drop_duplicates("レースコード",keep="last")
    z=base.merge(p,on="レースコード",how="inner")
    splits=split3(z)
    rows=[]
    for m,_ in metrics:
        for typ in ["2連単","2連複","3連複","3連単"]:
            for variant in ["TOP12","TOP123"]:
                rec={"metric":m,"bet_type":typ,"variant":variant}
                for s,d in splits.items():
                    vals=[]
                    for _,r in d.iterrows():
                        if any(pd.isna(r.get(m+f"_{i}")) for i in [1,2,3]): continue
                        a,b,c=[int(r[m+f"_{i}"]) for i in [1,2,3]]
                        if typ=="2連単":
                            tickets=[(a,b)] if variant=="TOP12" else [(a,b),(a,c)]
                            out=norm_exact(r["2連単_組番"],2); payout=float(r["2連単_払戻金"])
                        elif typ=="2連複":
                            tickets=[tuple(sorted((a,b)))] if variant=="TOP12" else [tuple(sorted((a,b))),tuple(sorted((a,c)))]
                            out=norm_set(r["2連複_組番"],2); payout=float(r["2連複_払戻金"])
                        elif typ=="3連複":
                            tickets=[tuple(sorted((a,b,c)))]
                            out=norm_set(r["3連複_組番"],3); payout=float(r["3連複_払戻金"])
                        else:
                            tickets=[(a,b,c)] if variant=="TOP12" else [(a,b,c),(a,c,b)]
                            out=norm_exact(r["3連単_組番"],3); payout=float(r["3連単_払戻金"])
                        vals.append((len(tickets), payout if out in tickets else 0.0))
                    if vals:
                        stake=sum(n for n,_ in vals)*100
                        rets=[x for _,x in vals]; ret=sum(rets); mx=max(rets)
                        rec[f"{s}_races"]=len(vals); rec[f"{s}_roi"]=ret/stake*100; rec[f"{s}_roi_dropmax"]=(ret-mx)/stake*100
                    else:
                        rec[f"{s}_races"]=0; rec[f"{s}_roi"]=np.nan; rec[f"{s}_roi_dropmax"]=np.nan
                rec["stable"]=bool(rec["DISC_races"]>=150 and rec["VAL_races"]>=50 and rec["OOS_races"]>=50 and rec["DISC_roi"]>100 and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and rec["DISC_roi_dropmax"]>=90 and rec["VAL_roi_dropmax"]>=90 and rec["OOS_roi_dropmax"]>=90)
                vals=[rec["DISC_roi"],rec["VAL_roi"],rec["OOS_roi"],rec["DISC_roi_dropmax"],rec["VAL_roi_dropmax"],rec["OOS_roi_dropmax"]]
                rec["robust_score"]=float(np.nanmin(vals))
                rows.append(rec)
    out=pd.DataFrame(rows).sort_values(["stable","robust_score"],ascending=[False,False])
    out.to_csv(OUT/"results.csv",index=False)
    pd.DataFrame([{"races":len(z),"stable":int(out.stable.sum()),"date_min":str(z.race_date.min().date()),"date_max":str(z.race_date.max().date())}]).to_csv(OUT/"summary.csv",index=False)
    print(pd.read_csv(OUT/"summary.csv").to_string(index=False)); print(out.to_string(index=False))
if __name__=="__main__": main()
