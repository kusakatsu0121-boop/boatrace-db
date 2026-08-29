#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
import core_feature_ablation_v7 as a
import run_core_feature_ablation_v7_fast as f

a.m.PATH_TO_IDX=a.be.PATH_TO_IDX
a.tune_path=f.fast_tune_path


def run_one(e, base, name, families):
    nums,cats=a.columns_for(e,families)
    model,ntrain=a.fit_model(e,nums,cats)
    pp=a.entry_probs(model,e,nums,cats)
    best,_=a.tune_path(e,pp)
    july,_=a.make_predictions(e,pp,a.JULY_START,a.JULY_END,best['temperature'],best['gamma'])
    wb,_=a.tune_market_weight(july,base)
    aug,_=a.make_predictions(e,pp,a.AUG_START,a.AUG_END,best['temperature'],best['gamma'])
    sm,_=a.eval_aug(aug,base,wb['model_weight'])
    return {'model':name,'families':'|'.join(families) if families else 'CORE_ONLY','numeric_features':len(nums),'categorical_features':len(cats),'train_rows':ntrain,'cal_nll':best['cal_nll'],'gamma':best['gamma'],'temperature':best['temperature'],'july_model_weight':wb['model_weight'],'july_blend_nll':wb['nll'],**sm}


def main():
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e)
    rows=[run_one(e,base,'CORE',[]),run_one(e,base,'FULL',list(a.FAMILIES))]
    out=Path('artifacts/core_vs_full_quick_v7'); out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':
    main()
