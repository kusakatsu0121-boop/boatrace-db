#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import itertools, numpy as np, pandas as pd

from racer_directory import load_many, cards_to_long

SRC=Path("source/data")
OUT=Path("artifacts/edogawa_muscle_scan")
OUT.mkdir(parents=True,exist_ok=True)
VENUE_CODE="03"
PATHS=list(itertools.permutations(range(1,7),3))
ODDS_COLS=[f"3連単_{a}-{b}-{c}" for a,b,c in PATHS]

def parse_combo(v):
    try:
        t=tuple(int(x) for x in str(v).replace("=","-").split("-"))
        return t if len(t)==3 and len(set(t))==3 else None
    except Exception:
        return None

def venue_mask(df):
    if "レース場コード" in df.columns:
        s=df["レース場コード"].astype(str).str.extract(r"(\d+)")[0].str.zfill(2)
        return s.eq(VENUE_CODE)
    if "レース場" in df.columns:
        s=df["レース場"].astype(str)
        numeric=s.str.extract(r"(\d+)")[0].str.zfill(2)
        return numeric.eq(VENUE_CODE) | s.str.contains("江戸川",na=False)
    code=df["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    return code.str[-4:-2].eq(VENUE_CODE)

def main():
    cards=load_many(str(SRC/"programs/race_cards/*/*/*.csv"))
    odds=load_many(str(SRC/"previews/od3/*/*/*.csv"))
    payouts=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    if any(x.empty for x in [cards,odds,payouts]):
        raise SystemExit("required cards/od3/payouts missing")

    cl=cards_to_long(cards)
    meta_cols=["レースコード"]
    for c in ["レース日","レース場コード","レース場"]:
        if c in cl.columns: meta_cols.append(c)
    base=cl[meta_cols].drop_duplicates("レースコード")
    base=base[venue_mask(base)].copy()
    if "レース日" in base:
        base["race_date"]=pd.to_datetime(base["レース日"],errors="coerce")
    else:
        base["race_date"]=pd.NaT

    paycols=[c for c in ["レースコード","3連単_組番","3連単_払戻金"] if c in payouts.columns]
    pay=payouts[paycols].drop_duplicates("レースコード",keep="last").copy()
    pay["winner"]=pay.get("3連単_組番").map(parse_combo)
    pay["payout"]=pd.to_numeric(pay.get("3連単_払戻金"),errors="coerce")
    pay=pay.dropna(subset=["winner","payout"])

    odcols=["レースコード"]+[c for c in ODDS_COLS if c in odds.columns]
    od=odds[odcols].drop_duplicates("レースコード",keep="last").copy()
    for c in ODDS_COLS:
        if c not in od: od[c]=np.nan
        od[c]=pd.to_numeric(od[c],errors="coerce")

    r=base.merge(pay[["レースコード","winner","payout"]],on="レースコード").merge(od[["レースコード"]+ODDS_COLS],on="レースコード")
    r=r.dropna(subset=["race_date"]).sort_values("race_date").reset_index(drop=True)
    if len(r)<300:
        raise SystemExit(f"too few Edogawa races: {len(r)}")

    # chronological 60/20/20 split
    q1=int(len(r)*0.60); q2=int(len(r)*0.80)
    disc, val, oos=r.iloc[:q1],r.iloc[q1:q2],r.iloc[q2:]
    rows=[]
    for path in PATHS:
        col=f"3連単_{path[0]}-{path[1]}-{path[2]}"
        for name,g in [("DISC",disc),("VAL",val),("OOS",oos)]:
            hit=g["winner"].map(lambda x: tuple(x)==path)
            bets=g[col].notna() & g[col].gt(1)
            gg=g[bets].copy(); hh=hit[bets]
            n=len(gg)
            ret=float(gg.loc[hh,"payout"].sum()) if n else 0.0
            rows.append({"path":"-".join(map(str,path)),"split":name,"n":n,"hits":int(hh.sum()),"hit_rate":float(hh.mean()) if n else np.nan,"roi_pct":ret/(100*n)*100 if n else np.nan})
    d=pd.DataFrame(rows)
    wide=d.pivot(index="path",columns="split",values=["n","hits","hit_rate","roi_pct"])
    wide.columns=["_".join(x) for x in wide.columns]
    wide=wide.reset_index()
    # Require positive validation and OOS, with adequate exposure.
    wide["stable"]=(wide["n_VAL"]>=100)&(wide["n_OOS"]>=100)&(wide["roi_pct_VAL"]>100)&(wide["roi_pct_OOS"]>100)
    wide["min_val_oos_roi"]=wide[["roi_pct_VAL","roi_pct_OOS"]].min(axis=1)
    wide=wide.sort_values(["stable","min_val_oos_roi","n_OOS"],ascending=[False,False,False])
    wide.to_csv(OUT/"path_stability.csv",index=False)

    # Muscle families: same winner + second, varying third; same winner, varying followers.
    fam=[]
    for a in range(1,7):
        for b in range(1,7):
            if b==a: continue
            members=[f"{a}-{b}-{c}" for c in range(1,7) if c not in (a,b)]
            for split,g in [("DISC",disc),("VAL",val),("OOS",oos)]:
                hit=g["winner"].map(lambda x: tuple(x)[:2]==(a,b))
                # Equal 100-yen stake on all 4 third-place continuations.
                ret=0.0
                n=len(g)
                for idx,row in g.iterrows():
                    if hit.loc[idx]:
                        ret += float(row["payout"])
                stake=400*n
                fam.append({"family":f"{a}-{b}-*","split":split,"races":n,"tickets":4*n,"hits":int(hit.sum()),"roi_pct":ret/stake*100 if stake else np.nan})
    f=pd.DataFrame(fam)
    fw=f.pivot(index="family",columns="split",values=["races","tickets","hits","roi_pct"])
    fw.columns=["_".join(x) for x in fw.columns]
    fw=fw.reset_index()
    fw["stable"]=(fw["roi_pct_VAL"]>100)&(fw["roi_pct_OOS"]>100)
    fw["min_val_oos_roi"]=fw[["roi_pct_VAL","roi_pct_OOS"]].min(axis=1)
    fw=fw.sort_values(["stable","min_val_oos_roi"],ascending=[False,False])
    fw.to_csv(OUT/"muscle_family_stability.csv",index=False)

    pd.DataFrame([{
      "races":len(r),"date_min":str(r.race_date.min().date()),"date_max":str(r.race_date.max().date()),
      "disc":len(disc),"val":len(val),"oos":len(oos),
      "stable_paths":int(wide.stable.sum()),"stable_families":int(fw.stable.sum())
    }]).to_csv(OUT/"summary.csv",index=False)
    print(pd.read_csv(OUT/"summary.csv").to_string(index=False))
    print("\nTOP PATHS")
    print(wide.head(20).to_string(index=False))
    print("\nTOP FAMILIES")
    print(fw.head(20).to_string(index=False))

if __name__=="__main__":
    main()
