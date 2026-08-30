#!/usr/bin/env python3
import pandas as pd
import advisor_extension_patterns as m


def fast_scan_pairs(cal, oos, singles):
    if singles.empty:
        return pd.DataFrame()
    cand = singles[(singles.cal_bets >= m.MIN_CAL_BETS) & (singles.cal_uplift_pt >= 5.0)].copy()
    cand = cand.sort_values(['cal_uplift_pt', 'cal_bets'], ascending=[False, False]).head(m.TOP_GLOBAL_SINGLE)
    rows = []
    for path, sp in cand.groupby('path'):
        cp = cal[cal.path == path]
        op = oos[oos.path == path]
        sigs = sp.head(m.TOP_SINGLE_PER_PATH).to_dict('records')
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                a, b = sigs[i], sigs[j]
                if a['feature'] == b['feature']:
                    continue
                ca, cb = f"{a['feature']}__bin", f"{b['feature']}__bin"
                gc = cp[(cp[ca] == a['bin']) & (cp[cb] == b['bin'])]
                if len(gc) < m.MIN_CAL_BETS:
                    continue
                go = op[(op[ca] == a['bin']) & (op[cb] == b['bin'])]
                rows.append({'path': path, 'feature1': a['feature'], 'bin1': a['bin'],
                             'feature2': b['feature'], 'bin2': b['bin'],
                             **{f'cal_{k}': v for k, v in m.stat(gc).items()},
                             **{f'oos_{k}': v for k, v in m.stat(go).items()}})
    d = pd.DataFrame(rows)
    if d.empty:
        return d
    # Discovery ranking is calibration-only. August is shown only as OOS validation.
    d = d.sort_values(['cal_roi_pct', 'cal_bets'], ascending=[False, False]).head(m.TOP_PAIR_SIGNALS)
    d['oos_positive'] = (d.oos_bets >= m.MIN_OOS_BETS) & (d.oos_roi_pct > 0)
    return d


m.scan_pairs = fast_scan_pairs
m.main()
