#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a
a.m.PATH_TO_IDX = a.be.PATH_TO_IDX
import v8_interpretable_model as v8


def main():
    out=Path('artifacts/v8_weights_only'); out.mkdir(parents=True,exist_ok=True)
    e,panel,roles,base=a.v1.build_entries(Path('source/data'))
    e=a.v2._add_context_features(e,panel,roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e=a._add_interactions(e).reset_index(drop=True)

    core_nums,core_cats=a.columns_for(e,[])
    core_model,_=a.fit_model(e,core_nums,core_cats)
    core_pp=a.entry_probs(core_model,e,core_nums,core_cats)

    fam_pp={}
    for fam in v8.FAMILIES:
        nums,cats=a.columns_for(e,[fam])
        model,_=a.fit_model(e,nums,cats)
        fam_pp[fam]=a.entry_probs(model,e,nums,cats)

    fam_w,fam_table=v8._family_weights(e,core_pp,fam_pp)
    share_best,share_grid,final_pp=v8._tune_core_share(e,core_pp,fam_pp,fam_w)
    contrib=v8._contribution_table(core_pp,fam_pp,fam_w,share_best['core_share'])
    fam_table['total_model_share_pct']=fam_table['addon_weight_within_addons']*(1-share_best['core_share'])*100
    shift=np.abs(final_pp-core_pp)
    sanity=pd.DataFrame([{
        'core_share_pct':share_best['core_share']*100,
        'addon_share_pct':share_best['addon_share']*100,
        'mean_abs_entry_shift_pt':100*float(np.mean(shift)),
        'p95_abs_entry_shift_pt':100*float(np.quantile(shift,0.95)),
        'max_abs_entry_shift_pt':100*float(np.max(shift)),
        'entry_shift_cap_pt':v8.MAX_ENTRY_SHIFT_PT,
        'odds_used_in_structural_prediction':False,
    }])
    fam_table.to_csv(out/'family_selection.csv',index=False)
    share_grid.to_csv(out/'core_share_grid.csv',index=False)
    contrib.to_csv(out/'final_weight_table.csv',index=False)
    sanity.to_csv(out/'sanity.csv',index=False)
    print(contrib.to_string(index=False))
    print(sanity.to_string(index=False))

if __name__=='__main__':
    main()
