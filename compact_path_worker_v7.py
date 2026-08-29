#!/usr/bin/env python3
from pathlib import Path
import os
import pandas as pd
import core_feature_ablation_v7 as a
import run_core_feature_ablation_v7_fast as f

a.m.PATH_TO_IDX = a.be.PATH_TO_IDX
a.tune_path = f.fast_tune_path

CANDIDATES = {
    'FULL': list(a.FAMILIES),
    'NO_WEATHER': [x for x in a.FAMILIES if x != 'WEATHER_VENUE'],
    'NO_WEATHER_NO_F': [x for x in a.FAMILIES if x not in {'WEATHER_VENUE','F_STAGE'}],
    'NO_WEATHER_NO_ATTACK': [x for x in a.FAMILIES if x not in {'WEATHER_VENUE','ATTACK_ESCAPE'}],
    'LEAN': [x for x in a.FAMILIES if x not in {'WEATHER_VENUE','F_STAGE','ATTACK_ESCAPE'}],
}

def main():
    name=os.environ['CANDIDATE']
    fams=CANDIDATES[name]
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e)
    nums,cats=a.columns_for(e,fams)
    model,ntrain=a.fit_model(e,nums,cats)
    pp=a.entry_probs(model,e,nums,cats)
    best,_=a.tune_path(e,pp)
    july,_=a.make_predictions(e,pp,a.JULY_START,a.JULY_END,best['temperature'],best['gamma'])
    wb,_=a.tune_market_weight(july,base)
    aug,_=a.make_predictions(e,pp,a.AUG_START,a.AUG_END,best['temperature'],best['gamma'])
    sm,_=a.eval_aug(aug,base,wb['model_weight'])
    row={
        'candidate':name,
        'families':'|'.join(fams),
        'numeric_features':len(nums),
        'categorical_features':len(cats),
        'train_rows':ntrain,
        'cal_nll':best['cal_nll'],
        'gamma':best['gamma'],
        'temperature':best['temperature'],
        'july_model_weight':wb['model_weight'],
        'july_blend_nll':wb['nll'],
        **sm,
    }
    out=Path('artifacts/compact_path_v7'); out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame([row]).to_csv(out/f'{name}.csv',index=False)
    print(pd.DataFrame([row]).to_string(index=False))

if __name__=='__main__':
    main()
