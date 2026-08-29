#!/usr/bin/env python3
import backtest_ev as be
import full_probability_model as v1

_orig_stt_to_long = be.stt_to_long
_orig_feature_columns = v1.feature_columns

def _fixed_stt_to_long(stt):
    x = _orig_stt_to_long(stt)
    return x.drop(columns=['レース日'], errors='ignore')

be.stt_to_long = _fixed_stt_to_long

import full_probability_model_v2 as model

_orig_v2_feature_columns = model.feature_columns_v2
_orig_add_context_features = model._add_context_features

def _safe_feature_columns(e):
    current = v1.feature_columns
    v1.feature_columns = _orig_feature_columns
    try:
        return _orig_v2_feature_columns(e)
    finally:
        v1.feature_columns = current

def _safe_add_context_features(e, panel, roles):
    # Keep ndarray prediction rows aligned with DataFrame row indices after all merges/sorts.
    return _orig_add_context_features(e, panel, roles).reset_index(drop=True)

model.feature_columns_v2 = _safe_feature_columns
model._add_context_features = _safe_add_context_features

if __name__ == '__main__':
    model.main()
