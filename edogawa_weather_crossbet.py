#!/usr/bin/env python3
from pathlib import Path
import itertools
import numpy as np
import pandas as pd
from racer_directory import load_many

SRC=Path("source/data")
OUT=Path("artifacts/edogawa_weather_crossbet")
OUT.mkdir(parents=True,exist_ok=True)
VENUE="03"

def venue_mask(df):
    if "レース場" in df.columns:
        s=df["レース場"].astype(str)
        n=s.str.extract(r"(\d+)")[0].str.zfill(2)
        return n.eq(VENUE) | s.str.contains("江戸川",na=False)
    code=df["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    return code.str[-4:-2].eq(VENUE)

def norm_exact(v,n):
    try:
        xs=[int(x) for x in str(v).replace("=","-").split("-")]
        return "-".join(map(str,xs)) if len(xs)==n else None
    except Exception:
        return None

def norm_pair(v):
    try:
        xs=sorted(int(x) for x in str(v).replace("=","-").split("-"))
        return "=".join(map(str,xs)) if len(xs)==2 else None
    except Exception:
        return None

def norm_trio(v):
    try:
        xs=sorted(int(x) for x in str(v).replace("=","-").split("-"))
        return "=".join(map(str,xs)) if len(xs)==3 else None
    except Exception:
        return None

def split3(df):
    df=df.sort_values(["レース日","レースコード"]).reset_index(drop=True)
    a=int(len(df)*.60); b=int(len(df)*.80)
    return {"DISC":df.iloc[:a].copy(),"VAL":df.iloc[a:b].copy(),"OOS":df.iloc[b:].copy()}

def calc(g, outcome_col, payout_col, ticket):
    n=len(g)
    if n==0: return {"n":0,"hits":0,"roi":np.nan,"roi_dropmax":np.nan,"max_payout":np.nan}
    hit=g[outcome_col].eq(ticket).to_numpy()
    vals=np.where(hit,pd.to_numeric(g[payout_col],errors="coerce").fillna(0),0.0)
    ret=float(vals.sum()); mx=float(vals.max()) if len(vals) else 0.0
    return {"n":n,"hits":int(hit.sum()),"roi":ret/(100*n)*100,"roi_dropmax":(ret-mx)/(100*n)*100,"max_payout":mx}

def main():
    sui=load_many(str(SRC/"previews/sui/*/*/*.csv"))
    pay=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    if sui.empty or pay.empty: raise SystemExit("sui/payout missing")

    w=sui[venue_mask(sui)].copy()
    w["レース日"]=pd.to_datetime(w["レース日"],errors="coerce")
    w["wind"]=pd.to_numeric(w["風速(m)"],errors="coerce")
    w["wave"]=pd.to_numeric(w["波の高さ(cm)"],errors="coerce")
    w["wind_bin"]=pd.cut(w["wind"],[-.1,1.9,3.9,5.9,99],labels=["0-1","2-3","4-5","6+"])
    w["wave_bin"]=pd.cut(w["wave"],[-.1,2.9,5.9,99],labels=["0-2","3-5","6+"])
    w["wind_dir"]=w["風向"].astype(str)
    w=w[["レースコード","レース日","wind","wave","wind_bin","wave_bin","wind_dir"]].drop_duplicates("レースコード")

    p=pay[venue_mask(pay)].copy()
    p["レース日"]=pd.to_datetime(p["レース日"],errors="coerce")
    z=w.merge(p,on=["レースコード","レース日"],how="inner").drop_duplicates("レースコード",keep="last")
    if len(z)<500: raise SystemExit(f"too few Edogawa weather+payout rows: {len(z)}")

    defs={
      "2連単":("2連単_組番","2連単_払戻金",lambda x:norm_exact(x,2),[f"{a}-{b}" for a in range(1,7) for b in range(1,7) if a!=b]),
      "2連複":("2連複_組番","2連複_払戻金",norm_pair,[f"{a}={b}" for a in range(1,7) for b in range(a+1,7)]),
      "3連複":("3連複_組番","3連複_払戻金",norm_trio,["=".join(map(str,c)) for c in itertools.combinations(range(1,7),3)]),
      "3連単":("3連単_組番","3連単_払戻金",lambda x:norm_exact(x,3),["-".join(map(str,c)) for c in itertools.permutations(range(1,7),3)]),
    }

    conds=[("ALL",lambda d:pd.Series(True,index=d.index))]
    for wb in ["0-1","2-3","4-5","6+"]:
        conds.append((f"WIND_{wb}",lambda d,wb=wb:d["wind_bin"].astype(str).eq(wb)))
    for vb in sorted(z["wind_dir"].dropna().astype(str).unique()):
        conds.append((f"DIR_{vb}",lambda d,vb=vb:d["wind_dir"].eq(vb)))
    for wave in ["0-2","3-5","6+"]:
        conds.append((f"WAVE_{wave}",lambda d,wave=wave:d["wave_bin"].astype(str).eq(wave)))
    for wb in ["0-1","2-3","4-5","6+"]:
        for vb in sorted(z["wind_dir"].dropna().astype(str).unique()):
            conds.append((f"WIND_{wb}_DIR_{vb}",lambda d,wb=wb,vb=vb:(d["wind_bin"].astype(str).eq(wb)&d["wind_dir"].eq(vb))))
    for wave in ["0-2","3-5","6+"]:
        for wb in ["0-1","2-3","4-5","6+"]:
            conds.append((f"WIND_{wb}_WAVE_{wave}",lambda d,wb=wb,wave=wave:(d["wind_bin"].astype(str).eq(wb)&d["wave_bin"].astype(str).eq(wave))))

    rows=[]
    for typ,(oc,pc,parser,tickets) in defs.items():
        d=z.dropna(subset=[oc,pc]).copy()
        d["_out"]=d[oc].map(parser)
        splits=split3(d)
        for cname,fn in conds:
            for ticket in tickets:
                rec={"bet_type":typ,"ticket":ticket,"condition":cname}
                for sname,sd in splits.items():
                    g=sd[fn(sd)]
                    m=calc(g,"_out",pc,ticket)
                    rec.update({f"{sname}_{k}":v for k,v in m.items()})
                rec["stable"]=bool(
                    rec["DISC_n"]>=150 and rec["VAL_n"]>=50 and rec["OOS_n"]>=50 and
                    rec["DISC_roi"]>100 and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and
                    rec["DISC_roi_dropmax"]>=90 and rec["VAL_roi_dropmax"]>=90 and rec["OOS_roi_dropmax"]>=90
                )
                vals=[rec["DISC_roi"],rec["VAL_roi"],rec["OOS_roi"],rec["DISC_roi_dropmax"],rec["VAL_roi_dropmax"],rec["OOS_roi_dropmax"]]
                rec["robust_score"]=float(np.nanmin(vals)) if all(np.isfinite(vals)) else np.nan
                rows.append(rec)

    out=pd.DataFrame(rows).sort_values(["stable","robust_score","OOS_n"],ascending=[False,False,False])
    out.to_csv(OUT/"all_candidates.csv",index=False)
    out[out["stable"]].head(500).to_csv(OUT/"stable_top500.csv",index=False)
    pd.DataFrame([{
      "races":len(z),"date_min":str(z["レース日"].min().date()),"date_max":str(z["レース日"].max().date()),
      "candidates":len(out),"stable_candidates":int(out["stable"].sum())
    }]).to_csv(OUT/"summary.csv",index=False)
    print(pd.read_csv(OUT/"summary.csv").to_string(index=False))
    print("\nTOP")
    print(out.head(50).to_string(index=False))

if __name__=="__main__":
    main()
