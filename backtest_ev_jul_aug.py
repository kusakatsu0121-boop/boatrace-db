#!/usr/bin/env python3
from pathlib import Path
import pandas as pd

from backtest_ev import prepare_inputs, run_fold, PRIMARY_EV, PRIMARY_MAX_BETS


def main():
    src = Path('source/data')
    out = Path('artifacts/backtest_ev_jul_aug')
    out.mkdir(parents=True, exist_ok=True)
    panel, base, expo = prepare_inputs(src)

    name = 'JUL_AUG'
    role_train_end = '2026-07-01'
    discovery_start = '2026-07-01'
    discovery_end = '2026-07-31'
    test_start = '2026-08-01'
    test_end = '2026-08-28'

    summary, primary, meta = run_fold(
        name, panel, base, expo,
        role_train_end, discovery_start, discovery_end, test_start, test_end, out,
    )
    summary.to_csv(out / 'summary.csv', index=False)
    pd.DataFrame([meta]).to_csv(out / 'fold_meta.csv', index=False)
    if len(primary):
        primary.to_csv(out / 'primary_bets_all.csv', index=False)

    primary_name = f'EV{PRIMARY_EV:.2f}_TOP{PRIMARY_MAX_BETS}'
    print('PRIMARY AUGUST OOS')
    print(summary[summary['strategy'].eq(primary_name)].to_string(index=False))
    print('\nSENSITIVITY')
    print(summary.sort_values(['roi_pct','bets'], ascending=[False,False]).to_string(index=False))
    print('\nMETA')
    print(pd.DataFrame([meta]).to_string(index=False))


if __name__ == '__main__':
    main()
