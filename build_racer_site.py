#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel, latest_profile

SRC = Path('source/data')
OUT = Path('docs/racers.json')


def safe_num(v, digits=1):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    try:
        return round(float(v), digits)
    except Exception:
        return None


def perf(g: pd.DataFrame) -> dict:
    if g.empty:
        return {'n': 0, 'win1': None, 'top2': None, 'top3': None, 'avg_st': None, 'avg_finish': None}
    normal = g[g.get('f_start', 0).fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {
        'n': int(len(g)),
        'win1': safe_num((g['finish'].eq(1).mean() * 100), 1),
        'top2': safe_num((g['finish'].le(2).mean() * 100), 1),
        'top3': safe_num((g['finish'].le(3).mean() * 100), 1),
        'avg_st': safe_num(normal['actual_st'].mean(), 3) if 'actual_st' in normal.columns else None,
        'avg_finish': safe_num(g['finish'].mean(), 2),
    }


def method_mix(g: pd.DataFrame) -> dict:
    if g.empty or '決まり手' not in g.columns:
        return {}
    wins = g[g['finish'].eq(1) & g['決まり手'].notna()]
    if wins.empty:
        return {}
    c = wins['決まり手'].astype(str).str.replace(r'[\s　]+', '', regex=True).value_counts()
    total = c.sum()
    return {k: round(v / total * 100, 1) for k, v in c.items() if k}


def course_rows(g: pd.DataFrame) -> list[dict]:
    rows = []
    if 'actual_course' not in g.columns:
        return rows
    for course in range(1, 7):
        h = g[g['actual_course'].eq(course)]
        p = perf(h)
        p['course'] = course
        p['methods'] = method_mix(h)
        rows.append(p)
    return rows


def strongest_course(rows: list[dict]):
    valid = [r for r in rows if r['n'] >= 12 and r['win1'] is not None]
    if not valid:
        return None
    return max(valid, key=lambda r: r['win1'])['course']


def public_features(g6: pd.DataFrame, g1: pd.DataFrame) -> list[dict]:
    out = []
    p6, p1 = perf(g6), perf(g1)
    if p6['n'] >= 30 and p1['n'] >= 50 and p6['top3'] is not None and p1['top3'] is not None:
        d = p6['top3'] - p1['top3']
        if d >= 6:
            out.append({'label': '最近6か月で成績上向き', 'confidence': '中', 'note': f'3連対率 半年 {p6["top3"]}% / 1年 {p1["top3"]}%'})
        elif d <= -6:
            out.append({'label': '最近6か月で成績下向き', 'confidence': '中', 'note': f'3連対率 半年 {p6["top3"]}% / 1年 {p1["top3"]}%'})
    return out


def phase_stats(g: pd.DataFrame) -> dict:
    if g.empty:
        return {'n': 0, 'course_adj': None, 'top3': None, 'avg_finish': None, 'avg_st': None, 'opp': None}
    normal = g[g['f_start'].fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {
        'n': int(len(g)),
        'course_adj': safe_num(g['course_adjusted_perf'].mean(), 3),
        'top3': safe_num(g['finish'].le(3).mean() * 100, 1),
        'avg_finish': safe_num(g['finish'].mean(), 2),
        'avg_st': safe_num(normal['actual_st'].mean(), 3) if 'actual_st' in normal.columns else None,
        'opp': safe_num(g['opponent_strength'].mean(), 2) if 'opponent_strength' in g.columns else None,
    }


def late_meet_memo(g: pd.DataFrame, label: str) -> dict:
    if g.empty or 'day_no' not in g.columns:
        return {'window': label, 'status': '不足', 'reason': '節日次データなし'}
    x = g.dropna(subset=['day_no']).copy()
    if x.empty:
        return {'window': label, 'status': '不足', 'reason': '節日次データなし'}
    early = x[x['day_no'].between(1, 2)]
    middle = x[x['day_no'].between(3, 4)]
    late = x[x['day_no'] >= 5]
    e, m, l = phase_stats(early), phase_stats(middle), phase_stats(late)
    result = {'window': label, 'early': e, 'middle': m, 'late': l}
    if e['n'] < 10 or l['n'] < 10 or e['course_adj'] is None or l['course_adj'] is None:
        result.update({'status': '不足', 'confidence': '低', 'note': '初盤または終盤の標本不足'})
        return result
    delta = l['course_adj'] - e['course_adj']
    top3_delta = None if e['top3'] is None or l['top3'] is None else l['top3'] - e['top3']
    finish_delta = None if e['avg_finish'] is None or l['avg_finish'] is None else e['avg_finish'] - l['avg_finish']
    result['late_minus_early_course_adj'] = safe_num(delta, 3)
    result['late_minus_early_top3_pt'] = safe_num(top3_delta, 1) if top3_delta is not None else None
    result['early_minus_late_avg_finish'] = safe_num(finish_delta, 2) if finish_delta is not None else None
    supportive_up = (top3_delta is not None and top3_delta >= 4) or (finish_delta is not None and finish_delta >= 0.15)
    supportive_down = (top3_delta is not None and top3_delta <= -4) or (finish_delta is not None and finish_delta <= -0.15)
    if delta >= 0.18 and supportive_up:
        status = '後半上昇候補'
    elif delta <= -0.18 and supportive_down:
        status = '後半低下候補'
    else:
        status = '明確な後半差なし'
    nmin = min(e['n'], l['n'])
    confidence = '高' if nmin >= 30 and abs(delta) >= 0.25 else ('中' if nmin >= 15 else '低')
    result.update({'status': status, 'confidence': confidence})
    return result


def opponent_resilience_memo(g: pd.DataFrame, label: str) -> dict:
    """Internal: compare performance in stronger vs weaker fields within the same time window."""
    if g.empty or 'opponent_strength' not in g.columns or 'course_adjusted_perf' not in g.columns:
        return {'window': label, 'status': '不足', 'reason': '相手強度データなし'}
    x = g.dropna(subset=['opponent_strength', 'course_adjusted_perf', 'finish']).copy()
    if len(x) < 40:
        return {'window': label, 'status': '不足', 'reason': '全体標本不足', 'n': int(len(x))}
    q25 = x['opponent_strength'].quantile(.25)
    q75 = x['opponent_strength'].quantile(.75)
    weak = x[x['opponent_strength'] <= q25]
    strong = x[x['opponent_strength'] >= q75]
    w, s = phase_stats(weak), phase_stats(strong)
    result = {'window': label, 'weak_field': w, 'strong_field': s,
              'weak_cut': safe_num(q25, 3), 'strong_cut': safe_num(q75, 3)}
    if w['n'] < 10 or s['n'] < 10 or w['course_adj'] is None or s['course_adj'] is None:
        result.update({'status': '不足', 'confidence': '低', 'note': '強弱グループの標本不足'})
        return result
    cad = s['course_adj'] - w['course_adj']
    top3 = None if s['top3'] is None or w['top3'] is None else s['top3'] - w['top3']
    finish = None if s['avg_finish'] is None or w['avg_finish'] is None else w['avg_finish'] - s['avg_finish']
    result['strong_minus_weak_course_adj'] = safe_num(cad, 3)
    result['strong_minus_weak_top3_pt'] = safe_num(top3, 1) if top3 is not None else None
    result['weak_minus_strong_avg_finish'] = safe_num(finish, 2) if finish is not None else None
    # Strong-field resilience means the racer does not materially deteriorate as field strength rises.
    if cad >= 0.10 and ((top3 is not None and top3 >= -2) or (finish is not None and finish >= -0.10)):
        status = '強豪相手でも崩れにくい候補'
    elif cad <= -0.20 and ((top3 is not None and top3 <= -5) or (finish is not None and finish <= -0.20)):
        status = '強豪相手で低下候補'
    else:
        status = '明確な相手強度差なし'
    nmin = min(w['n'], s['n'])
    confidence = '高' if nmin >= 30 and abs(cad) >= 0.18 else ('中' if nmin >= 15 else '低')
    result.update({'status': status, 'confidence': confidence})
    return result


def build_player_memo(g6: pd.DataFrame, g1: pd.DataFrame) -> dict:
    lm6 = late_meet_memo(g6, '6か月')
    lm1 = late_meet_memo(g1, '1年')
    or6 = opponent_resilience_memo(g6, '6か月')
    or1 = opponent_resilience_memo(g1, '1年')
    tags = []
    if lm6.get('status') == '後半上昇候補' and lm1.get('status') == '後半上昇候補':
        tags.append('節後半に上げる')
    if or6.get('status') == '強豪相手でも崩れにくい候補' and or1.get('status') == '強豪相手でも崩れにくい候補':
        tags.append('強豪相手でも崩れにくい')
    return {
        'late_meet_6m': lm6,
        'late_meet_1y': lm1,
        'late_meet_reproduced': '節後半に上げる' in tags,
        'opponent_resilience_6m': or6,
        'opponent_resilience_1y': or1,
        'opponent_resilience_reproduced': '強豪相手でも崩れにくい' in tags,
        'memo_tags': tags,
        'visibility': 'internal_memo'
    }


def main():
    cards = load_many(str(SRC / 'programs/race_cards/*/*/*.csv'))
    results = load_many(str(SRC / 'results/realtime/*/*/*.csv'))
    title = load_many(str(SRC / 'programs/title/*/*/*.csv'))
    if cards.empty or results.empty:
        raise SystemExit('race cards/results not found')
    cl = cards_to_long(cards)
    rl = results_to_long(results)
    panel = build_panel(cl, rl, title).dropna(subset=['race_date', 'regno', 'finish']).copy()
    panel['race_date'] = pd.to_datetime(panel['race_date'])
    asof = panel['race_date'].max().normalize()
    start_1y = asof - pd.Timedelta(days=365)
    start_6m = asof - pd.Timedelta(days=183)
    p1 = panel[panel['race_date'].ge(start_1y)].copy()
    p6 = panel[panel['race_date'].ge(start_6m)].copy()
    prof = latest_profile(cl).set_index('regno')
    racers = []
    for reg, g1 in p1.groupby('regno'):
        if reg not in prof.index:
            continue
        g6 = p6[p6['regno'].eq(reg)]
        row = prof.loc[reg]
        c1 = course_rows(g1)
        c6 = course_rows(g6)
        name = str(row.get('name', '') or '').strip()
        if not name or name.lower() == 'nan':
            continue
        racers.append({
            'regno': int(reg), 'name': name,
            'class': None if pd.isna(row.get('class_grade')) else str(row.get('class_grade')),
            'branch': None if pd.isna(row.get('branch')) else str(row.get('branch')),
            'birthplace': None if pd.isna(row.get('birthplace')) else str(row.get('birthplace')),
            'age': None if pd.isna(row.get('age')) else int(float(row.get('age'))),
            'term': None if pd.isna(row.get('term')) else str(row.get('term')),
            'six_month': perf(g6), 'one_year': perf(g1),
            'courses_6m': c6, 'courses_1y': c1,
            'strongest_course_6m': strongest_course(c6),
            'features': public_features(g6, g1),
            'player_memo': build_player_memo(g6, g1),
        })
    racers.sort(key=lambda x: (x['class'] or '', x['one_year']['win1'] or 0, x['regno']), reverse=True)
    payload = {
        'updated': asof.strftime('%Y-%m-%d'),
        'window_6m_start': start_6m.strftime('%Y-%m-%d'),
        'window_1y_start': start_1y.strftime('%Y-%m-%d'),
        'count': len(racers), 'racers': racers,
        'notes': [
            '半年・1年は実レース結果から再集計',
            '何コース何型という分類は公開しない',
            '節後半上昇・相手強度耐性など分析途中の情報は選手メモに蓄積',
            '心理・相手依存などは半年/1年で再現し裏が取れたものだけ公開候補に昇格'
        ]
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'wrote {OUT} racers={len(racers)} asof={asof.date()}')


if __name__ == '__main__':
    main()
