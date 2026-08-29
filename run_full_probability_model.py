#!/usr/bin/env python3
import backtest_ev as be

_orig_stt_to_long = be.stt_to_long

def _fixed_stt_to_long(stt):
    x = _orig_stt_to_long(stt)
    return x.drop(columns=['レース日'], errors='ignore')

be.stt_to_long = _fixed_stt_to_long

import full_probability_model as model

if __name__ == '__main__':
    model.main()
