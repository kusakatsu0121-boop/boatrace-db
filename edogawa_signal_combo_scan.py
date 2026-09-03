#!/usr/bin/env python3
from pathlib import Path
import itertools, numpy as np, pandas as pd
from racer_directory import load_many, cards_to_long

SRC=Path("source/data")
OUT=Path("artifacts/edogawa_signal_combo")
OUT.mkdir(parents=True,exist_ok=True)
VENUE="03"

def venue_mask(df):
    if "レース場コード" in df.columns:
        s=df["レース場コード"].astype(str).str.extract(r"(\d+)")[0].str.zfill(2)
        return s.eq(VENUE)
    if "レース場" in df.columns:
        s=df["レース場"].astype(str); n=s.str.extract(r"(\d+)")[0].str.zfill(2)
        return n.eq(VENUE)|s.str.contains("江戸川",na=False)
    code=df["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    return code.str[-4:-2].eq(VENUE)

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

def rank_boats(g, col, asc=False):
    x=g[["boat_no",col]].dropna().copy()
    x=x.sort_values([col,"boat_no"],ascending=[asc,True])
    return [int(v) for v in x.boat_no.tolist()]

def build_races():
    cards=load_many(str(SRC/"programs/race_cards/*/*/*.csv"))
    pay=load_many(str(SRC/"results/payouts/*/*/*.csv"))
    sui=load_many(str(SRC/"previews/sui/*/*/*.csv"))
    if cards.empty or pay.empty: raise SystemExit("cards/payout missing")
    cl=cards_to_long(cards)
    # cards_to_long may not preserve レース場; derive from race code if needed
    cl["race_date"]=pd.to_datetime(cl["レース日"],errors="coerce")
    code=cl["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    cl["_venue"]=code.str[-4:-2]
    cl=cl[cl["_venue"].eq(VENUE)].copy()
    rows=[]
    for rc,g in cl.groupby("レースコード"):
        if g.boat_no.nunique()!=6: continue
        loc=rank_boats(g,"local_win_rate",False)
        st=rank_boats(g,"pub_avg_st",True)
        mot=rank_boats(g,"motor_2rate",False)
        nat=rank_boats(g,"national_win_rate",False)
        if min(len(loc),len(st),len(mot),len(nat))<3: continue
        r={"レースコード":rc,"race_date":g["race_date"].iloc[0]}
        for name,arr in [("loc",loc),("st",st),("mot",mot),("nat",nat)]:
            for i,b in enumerate(arr[:3],1): r[f"{name}{i}"]=b
        # best attacking boat among 2-5 by normalized local + start + motor ranks
        gg=g[g.boat_no.between(2,5)].copy()
        for col,asc in [("local_win_rate",False),("pub_avg_st",True),("motor_2rate",False)]:
            gg[f"r_{col}"]=gg[col].rank(ascending=asc,method="average")
        gg["attack_score"]=gg["r_local_win_rate"]+gg["r_pub_avg_st"]+gg["r_motor_2rate"]
        r["attack"]=int(gg.sort_values(["attack_score","boat_no"]).iloc[0].boat_no)
        rows.append(r)
    base=pd.DataFrame(rows)

    p=pay.copy(); p["race_date"]=pd.to_datetime(p["レース日"],errors="coerce")
    pcode=p["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
    p=p[pcode.str[-4:-2].eq(VENUE)].drop_duplicates("レースコード",keep="last")
    keep=["レースコード","2連単_組番","2連単_払戻金","2連複_組番","2連複_払戻金","3連複_組番","3連複_払戻金","3連単_組番","3連単_払戻金"]
    z=base.merge(p[[c for c in keep if c in p.columns]],on="レースコード",how="inner")

    if not sui.empty:
        s=sui.copy(); scode=s["レースコード"].astype(str).str.replace(r"\D","",regex=True).str.zfill(12)
        s=s[scode.str[-4:-2].eq(VENUE)].drop_duplicates("レースコード")
        s["wind"]=pd.to_numeric(s["風速(m)"],errors="coerce")
        s["wave"]=pd.to_numeric(s["波の高さ(cm)"],errors="coerce")
        z=z.merge(s[["レースコード","wind","wave","風向"]],on="レースコード",how="left")
    return z

def strategies(r):
    # dynamic tickets: every strategy outputs one ticket per race
    out={}
    loc1,st1,mot1,nat1,atk=int(r.loc1),int(r.st1),int(r.mot1),int(r.nat1),int(r.attack)
    def distinct(seq):
        a=[]
        for x in seq:
            if x not in a: a.append(x)
        return a
    d=distinct([loc1,st1,mot1,nat1,atk,1,2,3,4,5,6])
    out["EX_loc-st"]=("2連単",(loc1,next(x for x in d if x!=loc1)))
    out["EX_st-loc"]=("2連単",(st1,next(x for x in d if x!=st1)))
    out["EX_attack-1"]=("2連単",(atk,1)) if atk!=1 else ("2連単",(atk,2))
    out["EX_1-attack"]=("2連単",(1,atk)) if atk!=1 else ("2連単",(1,2))
    pair=tuple(sorted(distinct([loc1,st1])[:2]))
    if len(pair)==2: out["QN_loc+st"]=("2連複",pair)
    trio=tuple(sorted(distinct([loc1,st1,mot1,nat1])[:3]))
    if len(trio)==3: out["TRIO_loc+st+mot"]=("3連複",trio)
    tri=distinct([atk,loc1,st1,mot1,nat1,1,2,3,4,5,6])[:3]
    if len(tri)==3:
        out["TF_attack_loc_st"]=("3連単",tuple(tri))
        out["TRIO_attack_loc_st"]=("3連複",tuple(sorted(tri)))
    tri2=distinct([1,atk,loc1,st1,mot1,2,3,4,5,6])[:3]
    if len(tri2)==3: out["TF_1_attack_loc"]=("3連単",tuple(tri2))
    return out

def outcome(row, typ):
    if typ=="2連単": return norm_exact(row["2連単_組番"],2), float(row["2連単_払戻金"])
    if typ=="2連複": return norm_set(row["2連複_組番"],2), float(row["2連複_払戻金"])
    if typ=="3連複": return norm_set(row["3連複_組番"],3), float(row["3連複_払戻金"])
    if typ=="3連単": return norm_exact(row["3連単_組番"],3), float(row["3連単_払戻金"])
    raise KeyError

def eval_strategy(df,name,condition):
    vals=[]
    for _,rr in df.iterrows():
        if condition=="WIND6+" and not (pd.notna(rr.get("wind")) and rr["wind"]>=6): continue
        if condition=="WIND4+" and not (pd.notna(rr.get("wind")) and rr["wind"]>=4): continue
        if condition=="WAVE6+" and not (pd.notna(rr.get("wave")) and rr["wave"]>=6): continue
        st=strategies(rr)
        if name not in st: continue
        typ,ticket=st[name]
        o,p=outcome(rr,typ)
        hit=(o==ticket)
        vals.append(p if hit else 0.0)
    n=len(vals)
    if not n:return {"n":0,"hits":0,"roi":np.nan,"roi_dropmax":np.nan}
    arr=np.array(vals,float); ret=arr.sum(); mx=arr.max() if n else 0
    return {"n":n,"hits":int((arr>0).sum()),"roi":ret/(100*n)*100,"roi_dropmax":(ret-mx)/(100*n)*100}

def main():
    z=build_races()
    if len(z)<500: raise SystemExit(f"too few races {len(z)}")
    splits=split3(z)
    sample=strategies(z.iloc[0])
    names=list(sample.keys())
    conditions=["ALL","WIND4+","WIND6+","WAVE6+"]
    rows=[]
    for name in names:
        typ=sample[name][0]
        for cond in conditions:
            rec={"strategy":name,"bet_type":typ,"condition":cond}
            for s,d in splits.items():
                m=eval_strategy(d,name,cond)
                rec.update({f"{s}_{k}":v for k,v in m.items()})
            rec["stable"]=bool(rec["DISC_n"]>=150 and rec["VAL_n"]>=50 and rec["OOS_n"]>=50 and rec["DISC_roi"]>100 and rec["VAL_roi"]>100 and rec["OOS_roi"]>100 and rec["DISC_roi_dropmax"]>=90 and rec["VAL_roi_dropmax"]>=90 and rec["OOS_roi_dropmax"]>=90)
            rec["robust_score"]=min([x for x in [rec["DISC_roi"],rec["VAL_roi"],rec["OOS_roi"],rec["DISC_roi_dropmax"],rec["VAL_roi_dropmax"],rec["OOS_roi_dropmax"]] if pd.notna(x)])
            rows.append(rec)
    out=pd.DataFrame(rows).sort_values(["stable","robust_score","OOS_n"],ascending=[False,False,False])
    out.to_csv(OUT/"signal_combo_results.csv",index=False)
    pd.DataFrame([{"races":len(z),"date_min":str(z.race_date.min().date()),"date_max":str(z.race_date.max().date()),"stable":int(out.stable.sum())}]).to_csv(OUT/"summary.csv",index=False)
    print(pd.read_csv(OUT/"summary.csv").to_string(index=False))
    print(out.to_string(index=False))

if __name__=="__main__":
    main()
