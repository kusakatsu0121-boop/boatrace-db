#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import pandas as pd

import run_market_blend_v3_august as aug

# The archived race-card CSV can contain full-series results, including the
# current race and later races on the same day. Therefore every feature whose
# name begins with series_ is excluded from model inputs. The columns may stay
# in the dataframe for diagnostics, but they are never passed to the model.
safe = aug.m.safe
_original_base_feature_columns = safe._orig_feature_columns


def leakage_safe_base_feature_columns(e):
    nums, cats = _original_base_feature_columns(e)
    nums = [c for c in nums if not str(c).startswith('series_')]
    return nums, cats


safe._orig_feature_columns = leakage_safe_base_feature_columns


if __name__ == '__main__':
    aug.main()
    p = Path('artifacts/market_blend_v3/meta.csv')
    if p.exists():
        meta = pd.read_csv(p)
        meta['leakage_safe_series_features_removed'] = True
        meta['excluded_feature_family'] = 'series_* (archived race-card full-series fields)'
        meta.to_csv(p, index=False)
