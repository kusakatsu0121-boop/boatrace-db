#!/usr/bin/env python3
from pathlib import Path
import pandas as pd

import backtest_ev as be

# Chosen only after observing that July has 1,939 usable discovery races and the
# original large-sample rule produced zero discovery signals. August returns
# were not inspected to set these values.
be.DISCOVERY_MIN_N = 40
be.DISCOVERY_MIN_EXPECTED = 1.5
be.DISCOVERY_MIN_HITS = 3
be.DISCOVERY_MIN_MULT = 1.20
be.DISCOVERY_MIN_Z = 1.00
be.DISCOVERY_HALF_MIN_N = 12
be.DISCOVERY_PRIOR_N = 30.0


def main():
    src = Path('source/data')
    out = Path('artifacts/backtest_ev_jul_aug_small')
    out.mkdir(parents=True, exist_ok=True)
    panel, base, expo = be.prepare_inputs(src)

    name = 'JUL_AUG_SMALL'
    summary, primary, meta = be.run_fold(
        name, panel, base, expo,
        '2026-07-01', '2026-07-01', '2026-07-31', '2026-08-01', '2026-08-28', out,
    )
    summary.to_csv(out / 'summary.csv', index=False)
    pd.DataFrame([meta]).to_csv(out / 'fold_meta.csv', index=False)
    if len(primary):
        primary.to_csv(out / 'primary_bets_all.csv', index=False)

    primary_name = f'EV{be.PRIMARY_EV:.2f}_TOP{be.PRIMARY_MAX_BETS}'
    print('PRIMARY AUGUST OOS - SMALL SAMPLE RULE')
    print(summary[summary['strategy'].eq(primary_name)].to_string(index=False))
    print('\nSENSITIVITY')
    print(summary.sort_values(['roi_pct','bets'], ascending=[False,False]).to_string(index=False))
    print('\nMETA')
    print(pd.DataFrame([meta]).to_string(index=False))


if __name__ == '__main__':
    main()
