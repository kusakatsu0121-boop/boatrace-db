#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

import core_feature_ablation_v7 as a


def model_specs():
    fams = list(a.FAMILIES)
    specs = {'CORE': []}
    for f in fams:
        specs[f'CORE+{f}'] = [f]
    specs['FULL'] = fams.copy()
    for f in fams:
        specs[f'FULL-{f}'] = [x for x in fams if x != f]
    return specs


def evaluate(model, e: pd.DataFrame, nums: list[str], cats: list[str], start: str, end: str):
    z = e[(e.race_date >= pd.Timestamp(start)) & (e.race_date <= pd.Timestamp(end)) & e.finish.notna()].copy()
    if z.empty:
        return {}

    raw = model.predict_proba(z[nums + cats])
    classes = list(model.named_steps['clf'].classes_)
    p1 = raw[:, classes.index(0)] if 0 in classes else np.full(len(z), 1 / 6)
    z['_p1'] = np.clip(p1, 1e-12, 1.0)

    race_losses, race_hits = [], []
    for _, g in z.groupby('レースコード', sort=False):
        if len(g) != 6 or g['finish'].eq(1).sum() != 1:
            continue
        gp = g['_p1'].to_numpy(float)
        gp = gp / max(gp.sum(), 1e-12)
        win_pos = int(np.flatnonzero(g['finish'].eq(1).to_numpy())[0])
        race_losses.append(-math.log(max(float(gp[win_pos]), 1e-12)))
        race_hits.append(int(np.argmax(gp) == win_pos))

    y = np.where(z.finish.eq(1), 0, np.where(z.finish.eq(2), 1, np.where(z.finish.eq(3), 2, 3)))
    class_losses = []
    for i, yy in enumerate(y):
        if int(yy) in classes:
            class_losses.append(-math.log(max(float(raw[i, classes.index(int(yy))]), 1e-12)))

    return {
        'races': len(race_losses),
        'winner_nll': float(np.mean(race_losses)) if race_losses else np.nan,
        'winner_top1': float(np.mean(race_hits)) if race_hits else np.nan,
        'entry_class_nll': float(np.mean(class_losses)) if class_losses else np.nan,
        'entries': len(class_losses),
    }


def main():
    name = os.environ.get('MODEL_NAME', 'CORE')
    specs = model_specs()
    if name not in specs:
        raise SystemExit(f'unknown MODEL_NAME={name}')

    out = Path('artifacts/entry_ablation_v7')
    out.mkdir(parents=True, exist_ok=True)

    e, panel, roles, base = a.v1.build_entries(Path('source/data'))
    e = a.v2._add_context_features(e, panel, roles).reset_index(drop=True)
    a.v2._build_conditional_ratios(e)
    e = a._add_interactions(e)

    families = specs[name]
    nums, cats = a.columns_for(e, families)
    model, ntrain = a.fit_model(e, nums, cats)

    may_jun = evaluate(model, e, nums, cats, '2026-05-01', '2026-06-30')
    july = evaluate(model, e, nums, cats, '2026-07-01', '2026-07-31')
    august = evaluate(model, e, nums, cats, '2026-08-01', '2026-08-28')

    row = {
        'model': name,
        'families': '|'.join(families) if families else 'CORE_ONLY',
        'n_features_num': len(nums),
        'n_features_cat': len(cats),
        'train_entries': ntrain,
    }
    for prefix, metrics in [('may_jun', may_jun), ('july', july), ('aug', august)]:
        for k, v in metrics.items():
            row[f'{prefix}_{k}'] = v

    pd.DataFrame([row]).to_csv(out / f"{name.replace('+','PLUS').replace('/','_')}.csv", index=False)
    print(pd.DataFrame([row]).to_string(index=False))


if __name__ == '__main__':
    main()
