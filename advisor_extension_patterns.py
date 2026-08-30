#!/usr/bin/env python3
from __future__ import annotations

import itertools
from pathlib import Path
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel

PRIOR = 30.0
FOLLOW_PRIOR = 20.0
TRAIN_END = pd.Timestamp('2026-06-30')
CAL_START = pd.Timestamp('2026-07-01')
CAL_END = pd.Timestamp('2026-07-31')
OOS_START = pd.Timestamp('2026-08-01')
OOS_END = pd.Timestamp('2026-08-28')
MIN_CAL_BETS = 80
MIN_OOS_BETS = 50
TOP_SINGLE_PER_PATH = 12
TOP_GLOBAL_SINGLE = 250
TOP_PAIR_SIGNALS = 80

PATHS = list(itertools.permutations(range(1, 7), 3))
ODDS_COLS = [f'3連単_{a}-{b}-{c}' for a, b, c in PATHS]


def shr(k, n, p0, prior=PRIOR):
    if n <= 0 or not np.isfinite(p0):
        return np.nan
    return (float(k) + prior * float(p0)) / (float(n) + prior)


def normalize_method(s):
    return s.fillna('').astype(str).str.replace(r'[\s　]+', '', regex=True)


def parse_combo(v):
    try:
        t = tuple(int(z) for z in str(v).replace('=', '-').split('-'))
        return t if len(t) == 3 and len(set(t)) == 3 else None
    except Exception:
        return None


def build_role_metrics(train: pd.DataFrame) -> pd.DataFrame:
    p = train.dropna(subset=['regno', 'actual_course', 'finish']).copy()
    p['actual_course'] = p['actual_course'].astype(int)
    p['method'] = normalize_method(p.get('決まり手', pd.Series('', index=p.index)))
    p['is1'] = (p.finish == 1).astype(int)
    p['is2'] = (p.finish == 2).astype(int)
    p['is3'] = (p.finish == 3).astype(int)
    methods = {'escape': '逃げ', 'sashi': '差し', 'makuri': 'まくり', 'makuri_sashi': 'まくり差し'}
    for key, jp in methods.items():
        p[f'win_{key}'] = ((p.finish == 1) & p.method.eq(jp)).astype(int)
        p[f'race_{key}'] = p.method.eq(jp).astype(int)

    raw_cols = ['is1', 'is2', 'is3']
    for key in methods:
        raw_cols.extend([f'win_{key}', f'race_{key}'])
    course_base = p.groupby('actual_course')[raw_cols].mean().to_dict('index')

    rows = []
    for (reg, course), g in p.groupby(['regno', 'actual_course']):
        course = int(course)
        n = len(g)
        b = course_base[course]
        r = {'regno': int(reg), 'course': course, 'n': int(n)}
        r['p1'] = shr(g.is1.sum(), n, b['is1'])
        r['p2'] = shr(g.is2.sum(), n, b['is2'])
        r['p3'] = shr(g.is3.sum(), n, b['is3'])
        for key in methods:
            r[f'{key}_win_rate'] = shr(g[f'win_{key}'].sum(), n, b[f'win_{key}'])
            r[f'{key}_race_rate'] = shr(g[f'race_{key}'].sum(), n, b[f'race_{key}'])
        r['escape_rate'] = r['escape_win_rate'] if course == 1 else np.nan
        r['allow_escape_rate'] = r['escape_race_rate'] if course != 1 else np.nan
        r['beaten_sashi_rate'] = r['sashi_race_rate'] if course == 1 else np.nan
        r['beaten_makuri_rate'] = r['makuri_race_rate'] if course == 1 else np.nan
        r['beaten_makuri_sashi_rate'] = r['makuri_sashi_race_rate'] if course == 1 else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def build_follow_metrics(train: pd.DataFrame):
    p = train.dropna(subset=['regno', 'actual_course', 'finish']).copy()
    p['actual_course'] = p.actual_course.astype(int)
    core = p[['レースコード', 'regno', 'actual_course', 'finish']].drop_duplicates(['レースコード', 'actual_course'])
    winners = core[core.finish.eq(1)][['レースコード', 'regno', 'actual_course']].rename(columns={'regno': 'winner_regno', 'actual_course': 'winner_course'})
    seconds = core[core.finish.eq(2)][['レースコード', 'actual_course']].rename(columns={'actual_course': 'second_course'})
    thirds = core[core.finish.eq(3)][['レースコード', 'actual_course']].rename(columns={'actual_course': 'third_course'})
    x = winners.merge(seconds, on='レースコード').merge(thirds, on='レースコード')

    den = x.groupby('winner_course').size().rename('n').reset_index()
    base2 = x.groupby(['winner_course', 'second_course']).size().rename('k').reset_index().merge(den, on='winner_course')
    base2['p'] = base2.k / base2.n
    b2 = {(int(r.winner_course), int(r.second_course)): float(r.p) for r in base2.itertuples(index=False)}
    base3 = x.groupby(['winner_course', 'third_course']).size().rename('k').reset_index().merge(den, on='winner_course')
    base3['p'] = base3.k / base3.n
    b3 = {(int(r.winner_course), int(r.third_course)): float(r.p) for r in base3.itertuples(index=False)}

    rows2, rows3 = [], []
    for (reg, wc), g in x.groupby(['winner_regno', 'winner_course']):
        n = len(g)
        for tc in range(1, 7):
            if tc == int(wc):
                continue
            p0 = b2.get((int(wc), tc), np.nan)
            ps = shr(int((g.second_course == tc).sum()), n, p0, FOLLOW_PRIOR)
            rows2.append({'regno': int(reg), 'winner_course': int(wc), 'target_course': tc, 'winner_n': int(n),
                          'follow2_prob': ps, 'follow2_base': p0,
                          'follow2_lift_pt': ps - p0 if np.isfinite(ps) and np.isfinite(p0) else np.nan,
                          'follow2_lift_ratio': ps / p0 if np.isfinite(ps) and np.isfinite(p0) and p0 > 0 else np.nan})
            p03 = b3.get((int(wc), tc), np.nan)
            ps3 = shr(int((g.third_course == tc).sum()), n, p03, FOLLOW_PRIOR)
            rows3.append({'regno': int(reg), 'winner_course': int(wc), 'target_course': tc, 'winner_n': int(n),
                          'follow3_prob': ps3, 'follow3_base': p03,
                          'follow3_lift_pt': ps3 - p03 if np.isfinite(ps3) and np.isfinite(p03) else np.nan,
                          'follow3_lift_ratio': ps3 / p03 if np.isfinite(ps3) and np.isfinite(p03) and p03 > 0 else np.nan})

    pair = x.groupby(['winner_course', 'second_course', 'third_course']).size().rename('k').reset_index()
    pden = x.groupby(['winner_course', 'second_course']).size().rename('n').reset_index()
    pair = pair.merge(pden, on=['winner_course', 'second_course'])
    pair['p3_given_12'] = pair.k / pair.n
    return pd.DataFrame(rows2), pd.DataFrame(rows3), pair


def build_base(cards_long, odds, payouts):
    c = cards_long.drop_duplicates(['レースコード', 'boat_no'], keep='last').copy()
    c['race_date'] = pd.to_datetime(c.get('レース日'), errors='coerce')
    keep_meta = ['レースコード', 'race_date'] + (['レース場コード'] if 'レース場コード' in c.columns else [])
    base = c[keep_meta].drop_duplicates('レースコード')
    for boat in range(1, 7):
        q = c[c.boat_no.eq(boat)][['レースコード', 'regno']].rename(columns={'regno': f'reg_c{boat}'})
        base = base.merge(q, on='レースコード', how='inner')

    pay = payouts[[x for x in ['レースコード', '3連単_組番', '3連単_払戻金'] if x in payouts.columns]].drop_duplicates('レースコード', keep='last').copy()
    pay['winner_path'] = pay.get('3連単_組番').map(parse_combo)
    pay['payout'] = pd.to_numeric(pay.get('3連単_払戻金'), errors='coerce')
    pay = pay.dropna(subset=['winner_path', 'payout'])

    odcols = ['レースコード'] + [x for x in ODDS_COLS if x in odds.columns]
    od = odds[odcols].drop_duplicates('レースコード', keep='last').copy()
    for col in ODDS_COLS:
        if col not in od:
            od[col] = np.nan
        od[col] = pd.to_numeric(od[col], errors='coerce')
    return base.merge(od[['レースコード'] + ODDS_COLS], on='レースコード', how='inner').merge(pay[['レースコード', 'winner_path', 'payout']], on='レースコード', how='inner')


def attach_roles(base, roles):
    out = base.copy()
    rolecols = [c for c in roles.columns if c != 'course']
    for course in range(1, 7):
        q = roles[roles.course.eq(course)][rolecols].copy()
        q = q.rename(columns={c: f'c{course}_{c}' for c in q.columns if c != 'regno'})
        out = out.merge(q, left_on=f'reg_c{course}', right_on='regno', how='left').drop(columns=['regno'])
    return out


def follow_lookup(df):
    return {(int(r.regno), int(r.winner_course), int(r.target_course)): r._asdict() for r in df.itertuples(index=False)} if not df.empty else {}


def path_chain_lookup(pair):
    return {(int(r.winner_course), int(r.second_course), int(r.third_course)): float(r.p3_given_12) for r in pair.itertuples(index=False)}


def rename_odds(races):
    return races.rename(columns={f'3連単_{a}-{b}-{c}': f'odds_{a}_{b}_{c}' for a, b, c in PATHS})


def ticket_frame(races, f2lk, f3lk, chainlk):
    rows = []
    race_features = [
        'c1_escape_rate', 'c1_beaten_sashi_rate', 'c1_beaten_makuri_rate', 'c1_beaten_makuri_sashi_rate',
        'c2_allow_escape_rate', 'c3_allow_escape_rate',
        'c2_sashi_win_rate', 'c2_makuri_win_rate', 'c2_makuri_sashi_win_rate',
        'c3_sashi_win_rate', 'c3_makuri_win_rate', 'c3_makuri_sashi_win_rate',
        'c4_sashi_win_rate', 'c4_makuri_win_rate', 'c4_makuri_sashi_win_rate']
    for r in races.itertuples(index=False):
        winner = tuple(r.winner_path)
        common = {'レースコード': r.レースコード, 'race_date': r.race_date}
        for name in race_features:
            common[name] = getattr(r, name, np.nan)
        for a, b, c in PATHS:
            try:
                rega = int(getattr(r, f'reg_c{a}'))
            except Exception:
                continue
            f2 = f2lk.get((rega, a, b), {})
            f3 = f3lk.get((rega, a, c), {})
            hit = int((a, b, c) == winner)
            row = dict(common)
            row.update({'path': f'{a}-{b}-{c}', 'a': a, 'b': b, 'c': c,
                        'odds': getattr(r, f'odds_{a}_{b}_{c}', np.nan), 'hit': hit,
                        'return_per_100': float(r.payout) if hit else 0.0,
                        'winner_follow2_prob': f2.get('follow2_prob', np.nan),
                        'winner_follow2_lift_pt': f2.get('follow2_lift_pt', np.nan),
                        'winner_follow2_lift_ratio': f2.get('follow2_lift_ratio', np.nan),
                        'winner_follow_n': f2.get('winner_n', np.nan),
                        'winner_follow3_prob': f3.get('follow3_prob', np.nan),
                        'winner_follow3_lift_pt': f3.get('follow3_lift_pt', np.nan),
                        'winner_follow3_lift_ratio': f3.get('follow3_lift_ratio', np.nan),
                        'course_chain_p3_given_12': chainlk.get((a, b, c), np.nan)})
            rows.append(row)
    return pd.DataFrame(rows)


def stat(g):
    n = len(g)
    if n == 0:
        return {'bets': 0, 'hits': 0, 'hit_rate': np.nan, 'roi_pct': np.nan, 'avg_odds': np.nan}
    return {'bets': int(n), 'hits': int(g.hit.sum()), 'hit_rate': float(g.hit.mean()),
            'roi_pct': float(g.return_per_100.sum()) / (100.0 * n) * 100.0,
            'avg_odds': float(pd.to_numeric(g.odds, errors='coerce').mean())}


def make_bins(cal, features):
    bins = {}
    for f in features:
        s = pd.to_numeric(cal[f], errors='coerce').dropna()
        if len(s) < 200 or s.nunique() < 4:
            continue
        qs = sorted(set(float(x) for x in s.quantile([0.2, 0.4, 0.6, 0.8]).dropna()))
        if len(qs) >= 2:
            bins[f] = [-np.inf] + qs + [np.inf]
    return bins


def label_bins(df, bins):
    out = df.copy()
    for f, edges in bins.items():
        x = pd.to_numeric(out[f], errors='coerce')
        out[f'{f}__bin'] = pd.cut(x, bins=edges, include_lowest=True, duplicates='drop').astype(str)
        out.loc[x.isna(), f'{f}__bin'] = 'NA'
    return out


def baseline_by_path(df):
    return pd.DataFrame([{'path': path, **stat(g)} for path, g in df.groupby('path')])


def scan_single(cal, oos, bins):
    cal_base = baseline_by_path(cal).set_index('path')['roi_pct'].to_dict()
    oos_base = baseline_by_path(oos).set_index('path')['roi_pct'].to_dict()
    rows = []
    for f in bins:
        bc = f'{f}__bin'
        for (path, b), g in cal[cal[bc].ne('NA')].groupby(['path', bc]):
            if len(g) < MIN_CAL_BETS:
                continue
            s1 = stat(g)
            go = oos[(oos.path == path) & (oos[bc] == b)]
            s2 = stat(go)
            rows.append({'path': path, 'feature': f, 'bin': str(b),
                         'cal_base_roi': cal_base.get(path, np.nan), 'cal_uplift_pt': s1['roi_pct'] - cal_base.get(path, np.nan),
                         **{f'cal_{k}': v for k, v in s1.items()},
                         'oos_base_roi': oos_base.get(path, np.nan),
                         'oos_uplift_pt': s2['roi_pct'] - oos_base.get(path, np.nan) if s2['bets'] else np.nan,
                         **{f'oos_{k}': v for k, v in s2.items()}})
    d = pd.DataFrame(rows)
    if d.empty:
        return d
    d['stable_positive'] = (d.cal_uplift_pt > 0) & (d.oos_uplift_pt > 0) & (d.oos_bets >= MIN_OOS_BETS)
    return d.sort_values(['stable_positive', 'oos_uplift_pt', 'cal_uplift_pt', 'oos_bets'], ascending=[False, False, False, False])


def scan_pairs(cal, oos, singles):
    if singles.empty:
        return pd.DataFrame()
    cand = singles[(singles.cal_bets >= MIN_CAL_BETS) & (singles.cal_uplift_pt >= 5.0)].copy()
    cand = cand.sort_values(['cal_uplift_pt', 'cal_bets'], ascending=[False, False]).head(TOP_GLOBAL_SINGLE)
    rows = []
    for path, sp in cand.groupby('path'):
        sigs = sp.head(TOP_SINGLE_PER_PATH).to_dict('records')
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                a, b = sigs[i], sigs[j]
                if a['feature'] == b['feature']:
                    continue
                ca, cb = f"{a['feature']}__bin", f"{b['feature']}__bin"
                gc = cal[(cal.path == path) & (cal[ca] == a['bin']) & (cal[cb] == b['bin'])]
                if len(gc) < MIN_CAL_BETS:
                    continue
                go = oos[(oos.path == path) & (oos[ca] == a['bin']) & (oos[cb] == b['bin'])]
                rows.append({'path': path, 'feature1': a['feature'], 'bin1': a['bin'], 'feature2': b['feature'], 'bin2': b['bin'],
                             **{f'cal_{k}': v for k, v in stat(gc).items()}, **{f'oos_{k}': v for k, v in stat(go).items()}})
    d = pd.DataFrame(rows)
    return d.sort_values(['oos_roi_pct', 'oos_bets', 'cal_roi_pct'], ascending=[False, False, False]).head(TOP_PAIR_SIGNALS) if not d.empty else d


def main():
    out = Path('artifacts/advisor_extension_patterns')
    out.mkdir(parents=True, exist_ok=True)
    src = Path('source/data')
    cards = load_many(str(src / 'programs/race_cards/*/*/*.csv'))
    results = load_many(str(src / 'results/realtime/*/*/*.csv'))
    odds = load_many(str(src / 'previews/od3/*/*/*.csv'))
    payouts = load_many(str(src / 'results/payouts/*/*/*.csv'))
    if any(x.empty for x in [cards, results, odds, payouts]):
        raise SystemExit('required cards/results/od3/payouts data not found')

    cl = cards_to_long(cards)
    rl = results_to_long(results)
    if '決まり手' in rl.columns:
        rl['決まり手'] = normalize_method(rl['決まり手'])
    panel = build_panel(cl, rl, pd.DataFrame()).dropna(subset=['race_date', 'regno', 'actual_course', 'finish']).copy()
    train = panel[panel.race_date <= TRAIN_END].copy()
    roles = build_role_metrics(train)
    f2, f3, chain = build_follow_metrics(train)
    roles.to_csv(out / 'role_metrics_train.csv', index=False)
    f2.to_csv(out / 'winner_to_second_course_train.csv', index=False)
    f3.to_csv(out / 'winner_to_third_course_train.csv', index=False)
    chain.to_csv(out / 'course_chain_train.csv', index=False)

    races = attach_roles(build_base(cl, odds, payouts), roles)
    races = races[(races.race_date >= CAL_START) & (races.race_date <= OOS_END)].copy()
    tickets = ticket_frame(rename_odds(races), follow_lookup(f2), follow_lookup(f3), path_chain_lookup(chain))

    cal = tickets[(tickets.race_date >= CAL_START) & (tickets.race_date <= CAL_END)].copy()
    oos = tickets[(tickets.race_date >= OOS_START) & (tickets.race_date <= OOS_END)].copy()
    features = ['c1_escape_rate', 'c1_beaten_sashi_rate', 'c1_beaten_makuri_rate', 'c1_beaten_makuri_sashi_rate',
                'c2_allow_escape_rate', 'c3_allow_escape_rate',
                'c2_sashi_win_rate', 'c2_makuri_win_rate', 'c2_makuri_sashi_win_rate',
                'c3_sashi_win_rate', 'c3_makuri_win_rate', 'c3_makuri_sashi_win_rate',
                'c4_sashi_win_rate', 'c4_makuri_win_rate', 'c4_makuri_sashi_win_rate',
                'winner_follow2_prob', 'winner_follow2_lift_pt', 'winner_follow2_lift_ratio',
                'winner_follow3_prob', 'winner_follow3_lift_pt', 'winner_follow3_lift_ratio', 'course_chain_p3_given_12']
    bins = make_bins(cal, features)
    calb, oosb = label_bins(cal, bins), label_bins(oos, bins)
    pd.DataFrame([{'feature': f, 'edges': repr(e)} for f, e in bins.items()]).to_csv(out / 'bin_edges_from_july.csv', index=False)
    baseline_by_path(calb).to_csv(out / 'baseline_by_path_july.csv', index=False)
    baseline_by_path(oosb).to_csv(out / 'baseline_by_path_aug.csv', index=False)
    singles = scan_single(calb, oosb, bins)
    singles.to_csv(out / 'single_condition_scan.csv', index=False)
    if not singles.empty:
        singles.head(300).to_csv(out / 'single_condition_top300.csv', index=False)
    pairs = scan_pairs(calb, oosb, singles)
    pairs.to_csv(out / 'two_condition_top.csv', index=False)

    print('ADVISOR EXTENSION PATTERN SCAN')
    print(f'train rows={len(train):,} roles={len(roles):,} cal tickets={len(calb):,} oos tickets={len(oosb):,}')
    print(f'features binned={len(bins)}')
    if not singles.empty:
        cols = ['path','feature','bin','cal_bets','cal_roi_pct','cal_uplift_pt','oos_bets','oos_roi_pct','oos_uplift_pt','stable_positive']
        print('\nTOP STABLE SINGLE CONDITIONS')
        print(singles[singles.stable_positive][cols].head(50).to_string(index=False))
    if not pairs.empty:
        print('\nTOP TWO-CONDITION PATTERNS')
        print(pairs.head(30).to_string(index=False))


if __name__ == '__main__':
    main()
