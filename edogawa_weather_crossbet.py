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

def norm_pair(v):
    try:
        a,b=[int(x) for x in str(v).replace("=","-").split("-")]
        return f"{min(a,b)}={max(a,b)}"
    except Exception:
        return None

def norm_trio(v):
    try:
        xs=sorted(int(x) for x in str(v).replace("=","-").split("-"))
        return "=".join(map(str,xs)) if len(xs)==3 else None
    except Exception:
        return None

def norm_exact(v, n):
    try:
        xs=[int(x) for x in str(v).replace("=","-").split("-")]
        return "-".join(map(str,xs)) if len(xs)==n else None
    except Exception:
        return None

def split3(df):
    df=df.sort_values(["レース日","レースコード"]).reset_index(drop=True)
    a=int(len(df)*0.60); b=int(len(df)*0.80)
    return {"DISC":df.iloc[:a].copy(),"VAL":df.iloc[a:b].copy(),"OOS":df.iloc[b:].copy()}

def result_map(pay, typ):
    if typ=="2連単":
        return pay["2連単_組番"].map(lambda x:norm_exact(x,2)), pd.to_numeric(pay["2連単_払戻金"],errors="coerce")
    if typ=="2連複":
        return pay["2連複_組番"].map(norm_pair), pd.to_numeric(pay["2連複_払戻金"],errors="coerce")
    if typ=="3連複":
        return pay["3連複_組番"].map(norm_trio), pd.to_numeric(pay["3連複_払戻金"],errors="coerce")
    if typ=="3連単":
        return pay["3連単_組番"].map(lambda x:norm_exact(x,3)), pd.to_numeric(pay["3連単_払戻金"],errors="coerce")
    raise KeyError(typ)

def odds_columns(df, typ):
    return [c for c in df.columns if c.startswith(typ+"_")]

def ticket_key(col, typ):
    return col.split("_",1)[1]

def metric(g, outcome_col, payout_col, key):
    if len(g)==0: return dict(n=0,hits=0,roi=np.nan,roi_dropmax=np.nan)
    hit=g[outcome_col].eq(key)
    rets=np.where(hit,pd.to_numeric(g[payout_col],errors="coerce").fillna(0),0.0)
    n=len(g); ret=float(np.sum(rets))
    mx=float(np.max(rets)) if len(rets) else 0.0
    return dict(n=n,hits=int(hit.sum()),roi=ret/(100*n)*100,roi_dropmax=(ret-mx)/(100*n)*100)

def main():
    sui=load_many(str(SRC/"previews/sui/*/*/*.csv"))
    od1=load_many(str(SRC/"previews/od1/*/*/*.csv"))
    od2=load_many(str(SRC/"previews/od2/*/*/*.csv"))
    od3=load_many(str(SRC/"previews/od3/*/*/*.csv"))
    pay=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    if any(x.empty for x in [sui,od1,od2,od3,pay]):
        raise SystemExit("required source tables missing")

    weather=sui[venue_mask(sui)].copy()
    weather["レース日"]=pd.to_datetime(weather["レース日"],errors="coerce")
    weather["wind"]=pd.to_numeric(weather["風速(m)"],errors="coerce")
    weather["wave"]=pd.to_numeric(weather["波の高さ(cm)"],errors="coerce")
    weather["wind_bin"]=pd.cut(weather["wind"],[-.1,1.9,3.9,5.9,99],labels=["0-1","2-3","4-5","6+"])
    weather["wave_bin"]=pd.cut(weather["wave"],[-.1,2.9,5.9,99],labels=["0-2","3-5","6+"])
    weather["wind_dir"]=weather["風向"].astype(str)
    weather=weather[["レースコード","レース日","wind","wave","wind_bin","wave_bin","wind_dir"]].drop_duplicates("レースコード")

    pay=pay[venue_mask(pay)].copy()
    base=weather.merge(pay,on=["レースコード","レース日"],how="inner")
    if len(base)<250:
        raise SystemExit(f"too few Edogawa weather+payout rows: {len(base)}")

    odds_by={"2連単":od2,"2連複":od2,"3連複":od1,"3連単":od3}
    rows=[]
    for typ,od in odds_by.items():
        od=od[venue_mask(od)].copy()
        use=["レースコード"]+odds_columns(od,typ)
        z=base.merge(od[use].drop_duplicates("レースコード"),on="レースコード",how="inner")
        outcome,payout=result_map(z,typ)
        z["_outcome"]=outcome; z["_payout"]=payout
        splits=split3(z)
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

        for col in odds_columns(z,typ):
            key=ticket_key(col,typ)
            for cname,fn in conds:
                rec={"bet_type":typ,"ticket":key,"condition":cname}
                ok=True
                for sname,d in splits.items():
                    g=d[fn(d) & pd.to_numeric(d[col],errors="coerce").gt(1)].copy()
                    m=metric(g,"_outcome","_payout",key)
                    rec.update({f"{sname}_{k}":v for k,v in m.items()})
                    if sname in ("VAL","OOS") and m["n"]<40: ok=False
                rec["stable"]=bool(ok and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and rec["OOS_roi_dropmax"]>=90)
                vals=[rec["VAL_roi"],rec["OOS_roi"],rec["OOS_roi_dropmax"]]
                rec["robust_score"]=float(np.nanmin(vals)) if all(np.isfinite(vals)) else np.nan
                rows.append(rec)

    out=pd.DataFrame(rows)
    out=out.sort_values(["stable","robust_score","OOS_n"],ascending=[False,False,False])
    out.to_csv(OUT/"all_candidates.csv",index=False)
    out[out["stable"]].head(300).to_csv(OUT/"stable_top300.csv",index=False)
    summary=pd.DataFrame([{
        "edogawa_races":len(base),
        "date_min":str(base["レース日"].min().date()),
        "date_max":str(base["レース日"].max().date()),
        "candidates":len(out),
        "stable_candidates":int(out["stable"].sum())
    }])
    summary.to_csv(OUT/"summary.csv",index=False)
    print(summary.to_string(index=False))
    print(out.head(40).to_string(index=False))

if __name__=="__main__":
    main()
