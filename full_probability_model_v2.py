#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_ev as be
import full_probability_model as v1

PATHS = v1.PATHS
ROLE_TRAIN_END = v1.ROLE_TRAIN_END
CAL_START = v1.CAL_START
CAL_END = v1.CAL_END
TEST_START = v1.TEST_START
TEST_END = v1.TEST_END
PRIMARY_EV = 1.15
PRIMARY_MAX_BETS = 8
EV_GRID = [1.05, 1.10, 1.15, 1.20, 1.30, 1.50]
BET_GRID = [4, 6, 8, 12]
COND_GAMMA = 0.50
RATIO2 = np.ones((6, 6), dtype=float)
RATIO3 = np.ones((6, 6, 6), dtype=float)


def _num(s):
    return pd.to_numeric(s, errors='coerce')


def _clip_prob(x):
    return np.clip(np.asarray(x, dtype=float), 1e-5, 1 - 1e-5)


def _logit(x):
    x = _clip_prob(x)
    return np.log(x / (1 - x))


def _expit(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def _shr_rate(k, n, p0, prior=25.0):
    if n <= 0 or not np.isfinite(p0):
        return np.nan
    return (float(k) + float(prior) * float(p0)) / (float(n) + float(prior))


def _stage(v):
    s = str(v or '').replace(' ', '')
    if '優勝戦' in s:
        return 'FINAL'
    if '準優' in s:
        return 'SEMI'
    if '選抜' in s:
        return 'SELECT'
    if '予選' in s:
        return 'QUALIFY'
    if '特賞' in s or '特選' in s:
        return 'SPECIAL'
    return 'GENERAL'


def _merge_result_fields(e: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in ['レースコード', 'boat_no', 'actual_st', 'f_start'] if c in panel.columns]
    z = panel[cols].drop_duplicates(['レースコード', 'boat_no'], keep='last').copy()
    rename = {}
    if 'actual_st' in z.columns:
        rename['actual_st'] = 'result_actual_st'
    if 'f_start' in z.columns:
        rename['f_start'] = 'result_f_start'
    z = z.rename(columns=rename)
    return e.merge(z, on=['レースコード', 'boat_no'], how='left')


def _add_st_correction(e: pd.DataFrame) -> pd.DataFrame:
    e = e.copy()
    h = e[(e.race_date < ROLE_TRAIN_END)].copy()
    h['expo_st'] = _num(h.get('expo_st'))
    h['result_actual_st'] = _num(h.get('result_actual_st'))
    h['result_f_start'] = _num(h.get('result_f_start')).fillna(0)
    h = h[h.result_f_start.eq(0) & h.expo_st.notna() & h.result_actual_st.notna()].copy()
    h['st_delta'] = h['result_actual_st'] - h['expo_st']
    h = h[h.st_delta.between(-0.30, 0.30)]
    cb = h.groupby('expo_course')['st_delta'].mean().to_dict()
    gp = h.groupby(['regno', 'expo_course'])['st_delta'].agg(['mean', 'std', 'size']).reset_index()
    gp['course_mean'] = gp['expo_course'].map(cb)
    gp['st_correction'] = (gp['mean'] * gp['size'] + gp['course_mean'] * 20.0) / (gp['size'] + 20.0)
    gp['st_delta_sd'] = gp['std'].fillna(h['st_delta'].std(ddof=0)).clip(0.01, 0.20)
    e = e.merge(gp[['regno', 'expo_course', 'st_correction', 'st_delta_sd']], on=['regno', 'expo_course'], how='left')
    e['st_correction'] = e['st_correction'].fillna(e['expo_course'].map(cb)).fillna(0.0)
    e['st_delta_sd'] = e['st_delta_sd'].fillna(h['st_delta'].std(ddof=0)).fillna(0.06)
    e['pred_st'] = _num(e['expo_st']) + e['st_correction']
    e = e.sort_values(['レースコード', 'expo_course']).copy()
    grp = e.groupby('レースコード', sort=False)
    e['pred_st_rel'] = e['pred_st'] - grp['pred_st'].transform('mean')
    e['pred_st_rank'] = grp['pred_st'].rank(method='average', ascending=True)
    e['inner_pred_st'] = grp['pred_st'].shift(1)
    e['outer_pred_st'] = grp['pred_st'].shift(-1)
    e['st_edge_inner'] = e['inner_pred_st'] - e['pred_st']
    e['st_edge_outer'] = e['outer_pred_st'] - e['pred_st']
    c1 = e[e.expo_course.eq(1)].set_index('レースコード')['pred_st']
    attack_min = e[e.expo_course.isin([2, 3, 4])].groupby('レースコード')['pred_st'].min()
    e['inside_st_pressure'] = e['レースコード'].map(c1 - attack_min)
    e['pred_fastest_flag'] = e['pred_st_rank'].eq(1).astype(int)
    return e


def _attack_profiles(panel: pd.DataFrame) -> pd.DataFrame:
    h = panel[(panel.race_date < ROLE_TRAIN_END)].dropna(subset=['regno', 'actual_course', 'finish', 'actual_st']).copy()
    h = h[h.get('f_start', 0).fillna(0).eq(0)]
    h['actual_course'] = h['actual_course'].astype(int)
    subject_rows = []
    resist_rows = []
    for c in range(2, 7):
        s = h[h.actual_course.eq(c)][['レースコード', 'regno', 'finish', 'actual_st']].rename(columns={'regno': 'sub_reg', 'finish': 'sub_finish', 'actual_st': 'sub_st'})
        inn = h[h.actual_course.eq(c - 1)][['レースコード', 'regno', 'finish', 'actual_st']].rename(columns={'regno': 'inner_reg', 'finish': 'inner_finish', 'actual_st': 'inner_st'})
        q = s.merge(inn, on='レースコード', how='inner')
        if q.empty:
            continue
        q['course'] = c
        q['start_edge'] = q['inner_st'] - q['sub_st']
        q['attempt_proxy'] = q['start_edge'].ge(0.015).astype(int)
        q['beat_inner'] = q['sub_finish'].lt(q['inner_finish']).astype(int)
        q['inner_damage'] = q['inner_finish'].ge(4).astype(int)
        if c < 6:
            out = h[h.actual_course.eq(c + 1)][['レースコード', 'finish']].rename(columns={'finish': 'outer_finish'})
            q = q.merge(out, on='レースコード', how='left')
            q['outer_supply'] = q['outer_finish'].le(3).astype(float)
        else:
            q['outer_supply'] = np.nan
        subject_rows.append(q[['sub_reg', 'course', 'attempt_proxy', 'beat_inner', 'inner_damage', 'outer_supply', 'start_edge']])
        rr = q[q.attempt_proxy.eq(1)].copy()
        if len(rr):
            rr['resist_course'] = c - 1
            rr['resist_success'] = rr['inner_finish'].lt(rr['sub_finish']).astype(int)
            rr['resist_top3'] = rr['inner_finish'].le(3).astype(int)
            resist_rows.append(rr[['inner_reg', 'resist_course', 'resist_success', 'resist_top3']])
    if not subject_rows:
        return pd.DataFrame(columns=['regno', 'course'])
    s = pd.concat(subject_rows, ignore_index=True)
    out = []
    for c, cc in s.groupby('course'):
        p_attempt = cc.attempt_proxy.mean()
        pa = cc[cc.attempt_proxy.eq(1)]
        p_conv = pa.beat_inner.mean() if len(pa) else 0.5
        p_damage = pa.inner_damage.mean() if len(pa) else 0.3
        p_supply = pa.outer_supply.mean() if pa.outer_supply.notna().any() else 0.3
        for reg, g in cc.groupby('sub_reg'):
            n = len(g); ga = g[g.attempt_proxy.eq(1)]; na = len(ga)
            row = {'regno': int(reg), 'course': int(c), 'attack_profile_n': n}
            row['attack_proxy_rate'] = _shr_rate(g.attempt_proxy.sum(), n, p_attempt, 25)
            row['attack_start_edge'] = float((g.start_edge.mean() * n) / (n + 25.0))
            row['attack_conversion'] = _shr_rate(ga.beat_inner.sum(), na, p_conv, 20) if na else p_conv
            row['inner_damage_rate'] = _shr_rate(ga.inner_damage.sum(), na, p_damage, 20) if na else p_damage
            oks = ga.outer_supply.dropna()
            row['outer_supply_rate'] = _shr_rate(oks.sum(), len(oks), p_supply, 20) if len(oks) else p_supply
            out.append(row)
    prof = pd.DataFrame(out)
    if resist_rows:
        r = pd.concat(resist_rows, ignore_index=True)
        rr = []
        for c, cc in r.groupby('resist_course'):
            p1 = cc.resist_success.mean(); p3 = cc.resist_top3.mean()
            for reg, g in cc.groupby('inner_reg'):
                rr.append({'regno': int(reg), 'course': int(c), 'resist_rate': _shr_rate(g.resist_success.sum(), len(g), p1, 20), 'resist_top3': _shr_rate(g.resist_top3.sum(), len(g), p3, 20)})
        prof = prof.merge(pd.DataFrame(rr), on=['regno', 'course'], how='outer')
    return prof


def _true_escape_profiles(panel: pd.DataFrame, roles: pd.DataFrame):
    h = panel[(panel.race_date < ROLE_TRAIN_END)].dropna(subset=['regno', 'actual_course', 'finish']).copy()
    h['actual_course'] = h['actual_course'].astype(int)
    rb = roles[['regno', 'course', 'allow_escape']].dropna().copy()
    base_allow = rb.groupby('course')['allow_escape'].mean().to_dict()
    z = h.merge(rb, left_on=['regno', 'actual_course'], right_on=['regno', 'course'], how='left').drop(columns=['course'])
    pieces = []
    for c in (1, 2, 3, 4):
        q = z[z.actual_course.eq(c)][['レースコード', 'regno', 'finish', '決まり手', 'allow_escape']].rename(columns={'regno': f'reg{c}', 'finish': f'finish{c}', '決まり手': f'method{c}', 'allow_escape': f'allow{c}'})
        pieces.append(q)
    if any(x.empty for x in pieces):
        return pd.DataFrame(columns=['regno', 'true_escape_adj']), base_allow
    q = pieces[0]
    for p in pieces[1:]:
        q = q.merge(p, on='レースコード', how='inner')
    q['escape'] = (q.finish1.eq(1) & q.method1.astype(str).str.replace(' ', '').eq('逃げ')).astype(int)
    p0 = float(q.escape.mean())
    base_logit = float(_logit(p0))
    pressure = np.zeros(len(q), dtype=float)
    for c in (2, 3, 4):
        b = float(base_allow.get(c, p0))
        vals = q[f'allow{c}'].fillna(b).to_numpy(float)
        pressure += (_logit(vals) - float(_logit(b)))
    pressure /= 3.0
    q['expected_escape'] = _expit(base_logit + pressure)
    q['escape_resid'] = q['escape'] - q['expected_escape']
    rows = []
    for reg, g in q.groupby('reg1'):
        n = len(g)
        rows.append({'regno': int(reg), 'true_escape_n': n, 'true_escape_adj': float(g.escape_resid.mean() * n / (n + 30.0)), 'raw_escape_rate': float(g.escape.mean()), 'opp_adjusted_expected_escape': float(g.expected_escape.mean())})
    return pd.DataFrame(rows), base_allow


def _add_f_recency(e: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    e = e.copy()
    events = panel[panel.get('f_start', 0).fillna(0).eq(1) & panel.race_date.notna()][['regno', 'race_date']].drop_duplicates().sort_values(['regno', 'race_date'])
    event_map = {int(reg): g.race_date.values.astype('datetime64[D]') for reg, g in events.groupby('regno')}
    days = np.full(len(e), 999.0)
    dates = pd.to_datetime(e.race_date).values.astype('datetime64[D]')
    regs = e.regno.fillna(-1).astype(int).to_numpy()
    for reg in np.unique(regs):
        if reg < 0 or reg not in event_map:
            continue
        idxs = np.flatnonzero(regs == reg)
        ev = event_map[reg]
        pos = np.searchsorted(ev, dates[idxs], side='left') - 1
        ok = pos >= 0
        if ok.any():
            days[idxs[ok]] = (dates[idxs[ok]] - ev[pos[ok]]).astype('timedelta64[D]').astype(float)
    e['days_since_f'] = np.clip(days, 0, 999)
    e['f_recent30'] = e.days_since_f.le(30).astype(int)
    e['f_recent60'] = e.days_since_f.le(60).astype(int)
    return e


def _add_context_features(e: pd.DataFrame, panel: pd.DataFrame, roles: pd.DataFrame) -> pd.DataFrame:
    e = _merge_result_fields(e, panel)
    e = _add_st_correction(e)
    attack = _attack_profiles(panel)
    e = e.merge(attack, left_on=['regno', 'expo_course'], right_on=['regno', 'course'], how='left').drop(columns=['course'], errors='ignore')
    esc, base_allow = _true_escape_profiles(panel, roles)
    e = e.merge(esc, on='regno', how='left')
    role_base = roles.groupby('course')['allow_escape'].mean().to_dict()
    e['escape_influence_score'] = e['allow_escape'] - e['expo_course'].map(role_base)
    c1_true = e[e.expo_course.eq(1)].set_index('レースコード')['true_escape_adj']
    e['c1_true_escape_adj'] = e['レースコード'].map(c1_true).fillna(0.0)
    press = e[e.expo_course.isin([2, 3, 4])].groupby('レースコード')['escape_influence_score'].sum()
    e['race_escape_pressure'] = -e['レースコード'].map(press).fillna(0.0)
    e = _add_f_recency(e, panel)
    e['race_stage'] = e.get('レース名', pd.Series('', index=e.index)).map(_stage)
    e['day_no'] = _num(e.get('日次', pd.Series(np.nan, index=e.index)).astype(str).str.extract(r'(\d+)')[0])
    e['late_series'] = e['day_no'].ge(5).astype(int)
    for c in ['attack_proxy_rate', 'attack_start_edge', 'attack_conversion', 'inner_damage_rate', 'outer_supply_rate', 'resist_rate', 'resist_top3', 'true_escape_adj', 'escape_influence_score']:
        if c not in e.columns:
            e[c] = np.nan
    return e


def feature_columns_v2(e: pd.DataFrame):
    nums, cats = v1.feature_columns(e)
    extra_nums = [
        'st_correction', 'st_delta_sd', 'pred_st', 'pred_st_rel', 'pred_st_rank', 'st_edge_inner', 'st_edge_outer', 'inside_st_pressure', 'pred_fastest_flag',
        'attack_proxy_rate', 'attack_start_edge', 'attack_conversion', 'inner_damage_rate', 'outer_supply_rate', 'resist_rate', 'resist_top3',
        'true_escape_adj', 'c1_true_escape_adj', 'escape_influence_score', 'race_escape_pressure',
        'days_since_f', 'f_recent30', 'f_recent60', 'day_no', 'late_series', 'adjusted_rating_z'
    ]
    for c in extra_nums:
        if c in e.columns and c not in nums:
            nums.append(c)
    if 'race_stage' in e.columns and 'race_stage' not in cats:
        cats.append('race_stage')
    return nums, cats


def _build_conditional_ratios(e: pd.DataFrame):
    global RATIO2, RATIO3
    h = e[(e.race_date < ROLE_TRAIN_END) & e.finish.notna()].copy()
    paths = []
    for _, g in h.groupby('レースコード'):
        z = g.dropna(subset=['finish', 'expo_course']).sort_values('finish')
        if len(z) < 3:
            continue
        t = tuple(int(x) for x in z.head(3).expo_course)
        if len(set(t)) == 3 and all(1 <= x <= 6 for x in t):
            paths.append(t)
    if not paths:
        return
    arr = np.asarray(paths, dtype=int) - 1
    base2 = np.bincount(arr[:, 1], minlength=6).astype(float) + 1.0
    base2 /= base2.sum()
    base3 = np.bincount(arr[:, 2], minlength=6).astype(float) + 1.0
    base3 /= base3.sum()
    r2 = np.ones((6, 6), dtype=float)
    r3 = np.ones((6, 6, 6), dtype=float)
    for a in range(6):
        aa = arr[arr[:, 0] == a]
        n = len(aa)
        if n:
            for b in range(6):
                cnt = int((aa[:, 1] == b).sum())
                cond = (cnt + 80.0 * base2[b]) / (n + 80.0)
                r2[a, b] = cond / max(base2[b], 1e-9)
        for b in range(6):
            ab = arr[(arr[:, 0] == a) & (arr[:, 1] == b)]
            n2 = len(ab)
            if n2:
                for c in range(6):
                    cnt = int((ab[:, 2] == c).sum())
                    cond = (cnt + 45.0 * base3[c]) / (n2 + 45.0)
                    r3[a, b, c] = cond / max(base3[c], 1e-9)
    RATIO2 = np.clip(r2, 0.45, 2.50)
    RATIO3 = np.clip(r3, 0.45, 2.50)


def path_from_entries_v2(g, entry_pp, alpha=.0, beta=.0, temp=1.0, signal_lookup=None):
    g = g.sort_values('expo_course')
    if list(g.expo_course.astype(int)) != list(range(1, 7)):
        return None
    idx = g.index.to_numpy()
    w = entry_pp[idx].copy()
    rr = g[['role_ratio1', 'role_ratio2', 'role_ratio3']].to_numpy(float)
    rr = np.where(np.isfinite(rr), rr, 1.0)
    rz = g['adjusted_rating_z'].fillna(0).to_numpy(float)[:, None]
    w = w * np.power(rr, alpha) * np.exp(beta * rz)
    w = w / np.maximum(w.sum(axis=0, keepdims=True), 1e-12)
    p = np.zeros(len(PATHS), dtype=float)
    for i, (a1, b1, c1) in enumerate(PATHS):
        a = a1 - 1; b = b1 - 1; c = c1 - 1
        p1 = w[a, 0]
        sec = w[:, 1] * np.power(RATIO2[a], COND_GAMMA)
        sec[a] = 0.0
        s2 = sec.sum()
        if s2 <= 0:
            continue
        p2 = sec[b] / s2
        third = w[:, 2] * np.power(RATIO3[a, b], COND_GAMMA)
        third[a] = 0.0; third[b] = 0.0
        s3 = third.sum()
        if s3 <= 0:
            continue
        p3 = third[c] / s3
        p[i] = p1 * p2 * p3
    p /= max(p.sum(), 1e-12)
    if temp != 1.0:
        p = np.power(np.clip(p, 1e-12, 1.0), 1.0 / temp)
        p /= p.sum()
    if signal_lookup:
        best = {}
        for label in v1.LABELS:
            for a, b in v1.PAIRS:
                ta = str(g.iloc[a - 1][label]); tb = str(g.iloc[b - 1][label])
                if ta in ('nan', 'SAMPLE_LOW') or tb in ('nan', 'SAMPLE_LOW'):
                    continue
                for tc, pos, lift, strength in signal_lookup.get((label, a, ta, b, tb), []):
                    key = (tc, pos)
                    if key not in best or strength > best[key][1]:
                        best[key] = (lift, strength)
        if best:
            marg = np.zeros((3, 6), dtype=float)
            for i, (a, b, c) in enumerate(PATHS):
                marg[0, a - 1] += p[i]; marg[1, b - 1] += p[i]; marg[2, c - 1] += p[i]
            ratios = np.ones((3, 6), dtype=float)
            for (tc, pos), (lift, _) in best.items():
                base = marg[pos - 1, tc - 1]
                if base > 0:
                    ratios[pos - 1, tc - 1] = np.clip((base + lift) / base, 0.70, 1.40)
            for i, (a, b, c) in enumerate(PATHS):
                p[i] *= (ratios[0, a - 1] * ratios[1, b - 1] * ratios[2, c - 1]) ** 0.5
            p /= p.sum()
    return p


def _tune_gamma(e, entry_pp, alpha, beta, temp):
    global COND_GAMMA
    rows = []
    best = None
    for gamma in [0.0, 0.25, 0.50, 0.75, 1.00]:
        COND_GAMMA = gamma
        pr, win = v1.make_path_predictions(e, entry_pp, CAL_START, CAL_END, alpha, beta, temp)
        loss = v1.nll_for(pr, win)
        rows.append({'conditional_gamma': gamma, 'cal_nll': loss, 'races': len(pr)})
        if best is None or loss < best[0]:
            best = (loss, gamma)
    COND_GAMMA = best[1]
    return best, pd.DataFrame(rows)


def _evaluate(base, model_probs, ev_threshold, max_bets):
    races = base[(base.race_date >= TEST_START) & (base.race_date <= TEST_END)].reset_index(drop=True)
    odds_course, q, winner_path, _ = be.odds_in_exhibition_course_order(races)
    rows = []
    for i, r in races.iterrows():
        p = model_probs.get(str(r['レースコード']))
        wi = int(winner_path[i])
        if p is None or wi < 0:
            continue
        ev = p * odds_course[i]
        eligible = np.flatnonzero(np.isfinite(ev) & (ev >= ev_threshold))
        order = eligible[np.argsort(ev[eligible])[::-1]][:max_bets]
        for rank, pidx in enumerate(order, 1):
            hit = int(pidx == wi)
            rows.append({'レースコード': str(r['レースコード']), 'race_date': r.race_date, 'rank_in_race': rank, 'course_trifecta': '-'.join(map(str, PATHS[pidx])), 'snapshot_odds': float(odds_course[i, pidx]), 'model_prob': float(p[pidx]), 'model_ev': float(ev[pidx]), 'hit': hit, 'return_per_100': float(r.payout) if hit else 0.0})
    return pd.DataFrame(rows)


def _summarize(b):
    return be.summarize_bets(b)


def _band(v):
    if v < 20: return '<20'
    if v < 50: return '20-50'
    if v < 100: return '50-100'
    if v < 200: return '100-200'
    if v < 500: return '200-500'
    if v < 1000: return '500-1000'
    return '1000+'


def main():
    out = Path('artifacts/full_probability_v2'); out.mkdir(parents=True, exist_ok=True)
    e, panel, roles, base = v1.build_entries(Path('source/data'))
    e = _add_context_features(e, panel, roles)
    _build_conditional_ratios(e)

    v1.feature_columns = feature_columns_v2
    v1.path_from_entries = path_from_entries_v2
    model, nums, cats, train_rows = v1.fit_base_model(e)
    entry_pp = v1.base_entry_probs(model, e, nums, cats)

    # Tune ordinary calibration with conditional dependency half-on, then tune conditional strength separately.
    global COND_GAMMA
    COND_GAMMA = 0.50
    best, tuning = v1.tune_calibration(e, entry_pp)
    _, alpha, beta, temp = best
    gamma_best, gamma_grid = _tune_gamma(e, entry_pp, alpha, beta, temp)

    cal_pred, cal_win = v1.make_path_predictions(e, entry_pp, CAL_START, CAL_END, alpha, beta, temp)
    rf = v1.race_frame_for_signals(e, cal_pred, cal_win)
    signals = v1.discover_pair_signals(rf); lk = v1.signal_lookup(signals)
    test_pred, test_win = v1.make_path_predictions(e, entry_pp, TEST_START, TEST_END, alpha, beta, temp, lk)

    # Probability quality vs market.
    races = base[(base.race_date >= TEST_START) & (base.race_date <= TEST_END)].reset_index(drop=True)
    _, q, winner_path, _ = be.odds_in_exhibition_course_order(races)
    met = []
    for i, r in races.iterrows():
        p = test_pred.get(str(r['レースコード'])); wi = int(winner_path[i])
        if p is None or wi < 0: continue
        met.append({'race_date': r.race_date, 'model_nll': -math.log(max(float(p[wi]), 1e-12)), 'market_nll': -math.log(max(float(q[i, wi]), 1e-12)) if np.isfinite(q[i, wi]) else np.nan, 'model_top_hit': int(np.argmax(p) == wi), 'market_top_hit': int(np.nanargmax(q[i]) == wi) if np.isfinite(q[i]).any() else 0, 'winner_model_p': float(p[wi])})
    metrics = pd.DataFrame(met)
    mm = pd.DataFrame([{'test_races_scored': len(metrics), 'model_path_nll': metrics.model_nll.mean(), 'market_path_nll': metrics.market_nll.mean(), 'model_top_path_hit_rate': metrics.model_top_hit.mean(), 'market_top_path_hit_rate': metrics.market_top_hit.mean(), 'avg_model_prob_on_winner': metrics.winner_model_p.mean()}])

    rows = []
    primary = None
    for ev in EV_GRID:
        for k in BET_GRID:
            b = _evaluate(base, test_pred, ev, k)
            st = _summarize(b)
            rows.append({'ev_threshold': ev, 'max_bets': k, 'races_bet': int(b['レースコード'].nunique()) if len(b) else 0, **st})
            if abs(ev - PRIMARY_EV) < 1e-9 and k == PRIMARY_MAX_BETS:
                primary = b
    sensitivity = pd.DataFrame(rows)
    primary = primary if primary is not None else pd.DataFrame()
    periods = []
    for name, lo, hi in [('JULY', '2026-07-01', '2026-07-31'), ('AUGUST', '2026-08-01', '2026-08-28'), ('POOLED', '2026-07-01', '2026-08-28')]:
        b = primary[(primary.race_date >= pd.Timestamp(lo)) & (primary.race_date <= pd.Timestamp(hi))] if len(primary) else primary
        periods.append({'period': name, 'races_bet': int(b['レースコード'].nunique()) if len(b) else 0, **_summarize(b)})
    summary = pd.DataFrame(periods)
    if len(primary):
        bb = primary.copy(); bb['odds_band'] = bb.snapshot_odds.map(_band)
        bands = []
        for (month, band), g in bb.assign(month=bb.race_date.dt.strftime('%Y-%m')).groupby(['month', 'odds_band']):
            bands.append({'month': month, 'odds_band': band, **_summarize(g)})
        for band, g in bb.groupby('odds_band'):
            bands.append({'month': 'POOLED', 'odds_band': band, **_summarize(g)})
        band_df = pd.DataFrame(bands)
    else:
        band_df = pd.DataFrame()

    meta = pd.DataFrame([{'train_entry_rows': train_rows, 'all_entry_rows': len(e), 'numeric_features': len(nums), 'categorical_features': len(cats), 'alpha_role': alpha, 'beta_adjusted': beta, 'temperature': temp, 'conditional_gamma': COND_GAMMA, 'pair_signals': len(signals), 'primary_ev': PRIMARY_EV, 'primary_max_bets': PRIMARY_MAX_BETS}])
    summary.to_csv(out/'summary.csv', index=False)
    sensitivity.to_csv(out/'sensitivity.csv', index=False)
    mm.to_csv(out/'model_metrics.csv', index=False)
    meta.to_csv(out/'meta.csv', index=False)
    tuning.to_csv(out/'calibration_grid.csv', index=False)
    gamma_grid.to_csv(out/'conditional_gamma_grid.csv', index=False)
    signals.to_csv(out/'pair_signals.csv', index=False)
    primary.to_csv(out/'primary_bets.csv', index=False)
    band_df.to_csv(out/'odds_bands.csv', index=False)
    metrics.to_csv(out/'race_metrics.csv', index=False)

    print('FULL PROBABILITY MODEL V2 -- ODDS ONLY AT EV LAYER')
    print('\nMETA'); print(meta.to_string(index=False))
    print('\nMODEL QUALITY'); print(mm.to_string(index=False))
    print('\nPRIMARY EV>=1.15 MAX8'); print(summary.to_string(index=False))
    print('\nSENSITIVITY'); print(sensitivity.to_string(index=False))
    print('\nODDS BANDS'); print(band_df.to_string(index=False) if len(band_df) else 'none')


if __name__ == '__main__':
    main()
