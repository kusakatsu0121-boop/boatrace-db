#!/usr/bin/env python3
import math
import numpy as np
import pandas as pd
import core_feature_ablation_v7 as a

a.m.PATH_TO_IDX = a.be.PATH_TO_IDX


def _arrays(e, pp, start, end):
    bases=[]; wins=[]
    z=e[(e.race_date>=start)&(e.race_date<=end)]
    for _,g in z.groupby('レースコード', sort=False):
        gg=g.sort_values('expo_course')
        courses=pd.to_numeric(gg['expo_course'],errors='coerce').dropna().astype(int).tolist()
        if courses!=list(range(1,7)):
            continue
        wi=a.winner_idx(gg)
        if wi is None:
            continue
        idx=gg.index.to_numpy(dtype=int)
        w=pp[idx].copy()
        w/=np.maximum(w.sum(axis=0,keepdims=True),1e-12)
        bases.append(w); wins.append(int(wi))
    if not bases:
        return None
    return np.stack(bases), np.asarray(wins,dtype=int)


def _path_matrix(w, gamma):
    n=w.shape[0]
    out=np.zeros((n,len(a.m.PATHS)),dtype=float)
    r2=np.power(np.clip(a.v2.RATIO2,1e-9,None),gamma)
    r3=np.power(np.clip(a.v2.RATIO3,1e-9,None),gamma)
    sec_den={}; third_den={}
    for aa in range(6):
        sw=w[:,:,1]*r2[aa][None,:]
        sec_den[aa]=sw.sum(axis=1)-sw[:,aa]
        for bb in range(6):
            if bb==aa: continue
            tw=w[:,:,2]*r3[aa,bb][None,:]
            third_den[(aa,bb)]=tw.sum(axis=1)-tw[:,aa]-tw[:,bb]
    for pi,(a1,b1,c1) in enumerate(a.m.PATHS):
        aa,bb,cc=a1-1,b1-1,c1-1
        d2=np.maximum(sec_den[aa],1e-12)
        d3=np.maximum(third_den[(aa,bb)],1e-12)
        out[:,pi]=w[:,aa,0]*(w[:,bb,1]*r2[aa,bb]/d2)*(w[:,cc,2]*r3[aa,bb,cc]/d3)
    out/=np.maximum(out.sum(axis=1,keepdims=True),1e-12)
    return out


def _nll(p,winners,temp):
    x=p
    if temp!=1.0:
        x=np.power(np.clip(x,1e-12,1.0),1.0/temp)
        x/=np.maximum(x.sum(axis=1,keepdims=True),1e-12)
    chosen=np.maximum(x[np.arange(len(winners)),winners],1e-12)
    return float(np.mean(-np.log(chosen)))


def fast_tune_path(e, pp):
    arr=_arrays(e,pp,a.CAL_START,a.CAL_END)
    if arr is None:
        return {'gamma':0.0,'temperature':1.0,'cal_nll':np.inf,'races':0},pd.DataFrame()
    w,winners=arr
    rows=[]; best=None
    for gamma in a.GAMMA_GRID:
        p=_path_matrix(w,float(gamma))
        for temp in a.TEMP_GRID:
            loss=_nll(p,winners,float(temp))
            row={'gamma':float(gamma),'temperature':float(temp),'cal_nll':loss,'races':len(winners)}
            rows.append(row)
            if best is None or loss<best['cal_nll']:
                best=row.copy()
    return best,pd.DataFrame(rows)


a.tune_path=fast_tune_path

if __name__=='__main__':
    a.main()
