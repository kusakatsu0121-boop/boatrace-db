#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
import numpy as np

from backtest_ev import (
    prepare_inputs, run_fold, PRIMARY_EV, PRIMARY_MAX_BETS,
)


def main():
    src = Path('source/data')
    out = Path('artifacts/backtest_ev')
    out.mkdir(parents=True, exist_ok=True)
    panel, base, expo = prepare_inputs(src)

    folds = [
        ('F1', '2026-01-01', '2026-01-01', '2026-02-28', '2026-03-01', '2026-04-30'),
        ('F2', '2026-05-01', '2026-05-01', '2026-06-30', '2026-07-01', '2026-08-28'),
    ]
    summaries, primaries, metas = [], [], []
    for spec in folds:
        name, role_train_end, discovery_start, discovery_end, test_start, test_end = spec
        s, p, m = run_fold(
            name, panel, base, expo,
            role_train_end, discovery_start, discovery_end, test_start, test_end, out,
        )
        summaries.append(s)
        if len(p):
            primaries.append(p.assign(fold=name))
        metas.append(m)

    summary = pd.concat(summaries, ignore_index=True)
    pooled = []
    for (strategy, ev, k), g in summary.groupby(['strategy', 'ev_threshold', 'max_bets']):
        stake = float(g['stake'].sum())
        ret = float(g['return'].sum())
        bets = int(g['bets'].sum())
        hits = int(g['hits'].sum())
        pooled.append({
            'fold': 'POOLED', 'strategy': strategy, 'ev_threshold': ev, 'max_bets': int(k),
            'signals': int(g['signals'].sum()), 'bets': bets, 'races_bet': int(g['races_bet'].sum()),
            'hits': hits, 'hit_rate': hits / bets if bets else np.nan,
            'stake': stake, 'return': ret, 'roi_pct': ret / stake * 100.0 if stake else np.nan,
        })
    summary = pd.concat([summary, pd.DataFrame(pooled)], ignore_index=True)
    summary.to_csv(out / 'summary.csv', index=False)
    pd.DataFrame(metas).to_csv(out / 'fold_meta.csv', index=False)
    if primaries:
        pd.concat(primaries, ignore_index=True).to_csv(out / 'primary_bets_all.csv', index=False)

    primary_name = f'EV{PRIMARY_EV:.2f}_TOP{PRIMARY_MAX_BETS}'
    print('PRIMARY OOS')
    print(summary[summary['strategy'].eq(primary_name)].to_string(index=False))
    print('\nSENSITIVITY POOLED')
    print(summary[summary['fold'].eq('POOLED')].sort_values(['roi_pct', 'bets'], ascending=[False, False]).to_string(index=False))
    print('\nFOLD META')
    print(pd.DataFrame(metas).to_string(index=False))


if __name__ == '__main__':
    main()
