#!/usr/bin/env python3
from __future__ import annotations

import itertools
from pathlib import Path
import numpy as np
import pandas as pd

import advisor_extension_patterns as m
from racer_directory import load_many, cards_to_long, results_to_long, build_panel

CAL_N = 1500
OOS_N = 1000
SEED = 20260831
FAMILIES = ['ability_course', 'attack_st', 'course_chain', 'current_state']
PATHS = m.PATHS
EPS = 1e-12


def stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if len(df) <= n:
        return df.copy()
    venue = 'レース場コード'
    if venue not in df.columns:
        return df.sample(n=n, random_state=seed).copy()
    parts = []
    total = len(df)
    for i, (_, g) in enumerate(df.groupby(venue, dropna=False)):
        take = min(len(g), max(1, int(round(n * len(g) / total))))
        parts.append(g.sample(n=take, random_state=seed + i))
    out = pd.concat(parts)
    if len(out) > n:
        out = out.sample(n=n, random_state=seed + 999)
    elif len(out) < n:
        rest = df.loc[~df.index.isin(out.index)]
        if len(rest):
            out = pd.concat([out, rest.sample(n=min(n-len(out), len(rest)), random_state=seed+1000)])
    return out.copy()


def pl_path_probs(scores: np.ndarray) -> np.ndarray:
    x = np.asarray(scores, dtype=float)
    x = np.nan_to_num(x, nan=np.nanmedian(x) if np.isfinite(x).any() else 50.0)
    strength = np.exp(np.clip((x - np.nanmean(x)) / 10.0, -5, 5))
    out = np.empty(len(PATHS), dtype=float)
    total = strength.sum()
    for i, (a, b, c) in enumerate(PATHS):
        sa, sb, sc = strength[a-1], strength[b-1], strength[c-1]
        p1 = sa / total
        p2 = sb / (total - sa)
        p3 = sc / (total - sa - sb)
        out[i] = p1 * p2 * p3
    out = np.clip(out, EPS, None)
    return out / out.sum()


def safe(v, default):
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def build_wide(cards_long: pd.DataFrame, results_long: pd.DataFrame) -> pd.DataFrame:
    c = cards_long.drop_duplicates(['レースコード', 'boat_no'], keep='last').copy()
    meta = c[['レースコード', 'レース日', 'レース場コード']].drop_duplicates('レースコード')
    meta['race_date'] = pd.to_datetime(meta['レース日'], errors='coerce')
    out = meta[['レースコード', 'レース場コード', 'race_date']].copy()
    for b in range(1, 7):
        q = c[c.boat_no.eq(b)][['レースコード', 'regno', 'pub_avg_st']].copy()
        q = q.rename(columns={'regno': f'reg_c{b}', 'pub_avg_st': f'st_c{b}'})
        out = out.merge(q, on='レースコード', how='inner')

    r = results_long.dropna(subset=['boat_no', 'actual_course', 'finish']).copy()
    r['same'] = r.boat_no.astype(int).eq(r.actual_course.astype(int))
    std = r.groupby('レースコード').agg(n=('boat_no','size'), same=('same','all')).reset_index()
    std = std[(std.n >= 6) & std.same]
    out = out.merge(std[['レースコード']], on='レースコード', how='inner')

    top3 = r[r.finish.le(3)].sort_values(['レースコード', 'finish'])
    wp = top3.groupby('レースコード')['boat_no'].agg(lambda s: tuple(int(x) for x in s)).rename('winner_path').reset_index()
    wp = wp[wp.winner_path.map(len).eq(3)]
    return out.merge(wp, on='レースコード', how='inner')


def load_index(src: Path) -> pd.DataFrame:
    a = load_many(str(src / 'estimate/v1_basic/2026/07/*.csv'))
    b = load_many(str(src / 'estimate/v1_basic/2026/08/*.csv'))
    x = pd.concat([a, b], ignore_index=True)
    x = x[x['状態'].eq('realtime')].drop_duplicates('レースコード', keep='last').copy()
    for col in x.columns:
        if '枠_' in col and col not in ['レースコード']:
            x[col] = pd.to_numeric(x[col], errors='coerce')
    return x


def base_follow_dict(df: pd.DataFrame, kind: str) -> dict:
    base_col = f'{kind}_base'
    if df.empty or base_col not in df.columns:
        return {}
    q = df.groupby(['winner_course','target_course'])[base_col].median().reset_index()
    return {(int(r.winner_course), int(r.target_course)): float(getattr(r, base_col)) for r in q.itertuples(index=False)}


def family_probs(row, f2lk, f3lk, b2, b3, chainlk):
    ability = []
    current = []
    for b in range(1, 7):
        w = safe(row.get(f'{b}枠_枠番pt'), 50.0)
        r = safe(row.get(f'{b}枠_選手pt'), 50.0)
        ability.append((w + r) / 2.0)
        mo = safe(row.get(f'{b}枠_モーターpt'), 50.0)
        ex = safe(row.get(f'{b}枠_展示pt'), 50.0)
        we = safe(row.get(f'{b}枠_気象pt'), 50.0)
        current.append((mo + ex + we) / 3.0)
    p_ability = pl_path_probs(np.array(ability))
    p_current = pl_path_probs(np.array(current))

    v_s = safe(row.get('c1_beaten_sashi_rate'), 0.10)
    v_m = safe(row.get('c1_beaten_makuri_rate'), 0.10)
    v_ms = safe(row.get('c1_beaten_makuri_sashi_rate'), 0.10)
    first_strength = []
    for b in range(1, 7):
        st = safe(row.get(f'st_c{b}'), 0.16)
        st_factor = float(np.exp(np.clip((0.16 - st) / 0.08, -1.5, 1.5)))
        if b == 1:
            s = safe(row.get('c1_escape_rate'), safe(row.get('c1_p1'), 0.55))
        else:
            p1 = safe(row.get(f'c{b}_p1'), 0.08)
            sa = safe(row.get(f'c{b}_sashi_win_rate'), 0.0)
            ma = safe(row.get(f'c{b}_makuri_win_rate'), 0.0)
            ms = safe(row.get(f'c{b}_makuri_sashi_win_rate'), 0.0)
            s = p1 + 2.0 * (sa*v_s + ma*v_m + ms*v_ms)
        first_strength.append(max(EPS, s * st_factor))
    first_strength = np.array(first_strength, dtype=float)
    first_prob = first_strength / first_strength.sum()
    p_attack = np.array([first_prob[a-1] / 20.0 for a,b,c in PATHS], dtype=float)
    p_attack = np.clip(p_attack, EPS, None); p_attack /= p_attack.sum()

    chain_score = np.empty(len(PATHS), dtype=float)
    for i, (a, b, c) in enumerate(PATHS):
        reg = int(row[f'reg_c{a}'])
        q2 = f2lk.get((reg, a, b), {})
        q3 = f3lk.get((reg, a, c), {})
        p2 = safe(q2.get('follow2_prob'), b2.get((a,b), 0.20))
        p3 = safe(q3.get('follow3_prob'), b3.get((a,c), 0.20))
        pc = safe(chainlk.get((a,b,c)), 0.25)
        chain_score[i] = max(EPS, p2 * p3 * pc)
    p_chain = chain_score / chain_score.sum()
    return np.stack([p_ability, p_attack, p_chain, p_current], axis=1)


def metric(logp: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    z = np.tensordot(logp, w, axes=([2],[0]))
    mx = z.max(axis=1, keepdims=True)
    logden = mx + np.log(np.exp(z-mx).sum(axis=1, keepdims=True))
    lp = z - logden
    idx = np.arange(len(y))
    loss = float(-lp[idx, y].mean())
    top1 = float((lp.argmax(axis=1) == y).mean())
    top5_idx = np.argpartition(lp, -5, axis=1)[:, -5:]
    top5 = float(np.mean([yy in top5_idx[i] for i, yy in enumerate(y)]))
    return {'logloss': loss, 'top1': top1, 'top5': top5}


def grid_weights():
    out = []
    for a in range(11):
        for b in range(11-a):
            for c in range(11-a-b):
                d = 10-a-b-c
                out.append(np.array([a,b,c,d], dtype=float)/10.0)
    return out


def main():
    src = Path('source/data')
    outdir = Path('artifacts/advisor_weight_quick')
    outdir.mkdir(parents=True, exist_ok=True)

    cards = load_many(str(src / 'programs/race_cards/*/*/*.csv'))
    results = load_many(str(src / 'results/realtime/*/*/*.csv'))
    cl = cards_to_long(cards)
    rl = results_to_long(results)
    panel = build_panel(cl, rl, pd.DataFrame()).dropna(subset=['race_date','regno','actual_course','finish']).copy()
    train = panel[panel.race_date <= m.TRAIN_END].copy()
    roles = m.build_role_metrics(train)
    f2, f3, chain = m.build_follow_metrics(train)
    f2lk, f3lk = m.follow_lookup(f2), m.follow_lookup(f3)
    b2, b3 = base_follow_dict(f2, 'follow2'), base_follow_dict(f3, 'follow3')
    chainlk = m.path_chain_lookup(chain)

    base = build_wide(cl, rl)
    base = m.attach_roles(base, roles)
    idx = load_index(src)
    keep_idx = ['レースコード'] + [c for c in idx.columns if '枠_' in c]
    base = base.merge(idx[keep_idx], on='レースコード', how='inner')
    base = base[(base.race_date >= m.CAL_START) & (base.race_date <= m.OOS_END)].copy()

    cal_all = base[(base.race_date >= m.CAL_START) & (base.race_date <= m.CAL_END)]
    oos_all = base[(base.race_date >= m.OOS_START) & (base.race_date <= m.OOS_END)]
    cal = stratified_sample(cal_all, CAL_N, SEED)
    oos = stratified_sample(oos_all, OOS_N, SEED+1)
    print(f'WEIGHT QUICK sample: cal={len(cal):,} oos={len(oos):,} standard-entry only')

    path_to_idx = {p:i for i,p in enumerate(PATHS)}
    def make_arrays(df):
        probs, y = [], []
        kept = []
        for _, row in df.iterrows():
            wp = tuple(row['winner_path'])
            if wp not in path_to_idx:
                continue
            probs.append(family_probs(row, f2lk, f3lk, b2, b3, chainlk))
            y.append(path_to_idx[wp])
            kept.append(row['レースコード'])
        p = np.stack(probs, axis=0)
        return np.log(np.clip(p, EPS, 1.0)), np.array(y, dtype=int), kept

    lcal, ycal, _ = make_arrays(cal)
    loos, yoos, _ = make_arrays(oos)

    rows = []
    for w in grid_weights():
        s = metric(lcal, ycal, w)
        rows.append({**{f'w_{FAMILIES[i]}': w[i] for i in range(4)}, **{f'cal_{k}':v for k,v in s.items()}})
    grid = pd.DataFrame(rows).sort_values(['cal_logloss','cal_top5'], ascending=[True,False]).reset_index(drop=True)
    grid.to_csv(outdir / 'weight_grid_cal.csv', index=False)

    top = grid.head(20).copy()
    oos_rows = []
    for _, r in top.iterrows():
        w = np.array([r[f'w_{f}'] for f in FAMILIES], dtype=float)
        s = metric(loos, yoos, w)
        oos_rows.append({**r.to_dict(), **{f'oos_{k}':v for k,v in s.items()}})
    top_oos = pd.DataFrame(oos_rows)
    top_oos.to_csv(outdir / 'top20_oos.csv', index=False)

    best = top.iloc[0]
    bestw = np.array([best[f'w_{f}'] for f in FAMILIES], dtype=float)
    best_oos = metric(loos, yoos, bestw)

    abl = []
    for f in FAMILIES:
        cand = grid[grid[f'w_{f}'].eq(0)].iloc[0]
        w = np.array([cand[f'w_{x}'] for x in FAMILIES], dtype=float)
        so = metric(loos, yoos, w)
        abl.append({'removed_family': f,
                    'best_cal_logloss_without': cand.cal_logloss,
                    'oos_logloss_without': so['logloss'],
                    'oos_top1_without': so['top1'], 'oos_top5_without': so['top5'],
                    'delta_oos_logloss_vs_full': so['logloss'] - best_oos['logloss'],
                    'delta_oos_top5_vs_full_pt': (so['top5'] - best_oos['top5']) * 100.0})
    abldf = pd.DataFrame(abl).sort_values('delta_oos_logloss_vs_full', ascending=False)
    abldf.to_csv(outdir / 'importance_ablation.csv', index=False)

    alone = []
    for i, f in enumerate(FAMILIES):
        w = np.zeros(4); w[i]=1.0
        sc, so = metric(lcal,ycal,w), metric(loos,yoos,w)
        alone.append({'family':f, **{f'cal_{k}':v for k,v in sc.items()}, **{f'oos_{k}':v for k,v in so.items()}})
    pd.DataFrame(alone).to_csv(outdir / 'family_alone.csv', index=False)

    print('\nPROVISIONAL JULY-BEST WEIGHTS')
    for i,f in enumerate(FAMILIES):
        print(f'{f}: {bestw[i]*100:.0f}%')
    print(f"July logloss={best.cal_logloss:.4f} top1={best.cal_top1*100:.2f}% top5={best.cal_top5*100:.2f}%")
    print(f"Aug  logloss={best_oos['logloss']:.4f} top1={best_oos['top1']*100:.2f}% top5={best_oos['top5']*100:.2f}%")
    print('\nIMPORTANCE: positive delta logloss means removing it hurts OOS')
    print(abldf.to_string(index=False))
    print('\nNOTE: external predictor weight intentionally not estimated here; same-period independent history is insufficient. Test as add-on after internal ratio is fixed.')


if __name__ == '__main__':
    main()
