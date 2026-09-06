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


def trait_candidates(g6: pd.DataFrame, g1: pd.DataFrame, c6: list[dict], c1: list[dict]) -> list[dict]:
    out = []
    # Only deterministic, descriptive labels. These are not psychological claims.
    for course in range(1, 7):
        a, b = c6[course-1], c1[course-1]
        if a['n'] < 12 or b['n'] < 20:
            continue
        methods6, methods1 = a.get('methods', {}), b.get('methods', {})
        for method in ['逃げ', '差し', 'まくり', 'まくり差し']:
            x, y = methods6.get(method), methods1.get(method)
            if x is None or y is None:
                continue
            if x >= 55 and y >= 45:
                out.append({'label': f'{course}コース・{method}型', 'confidence': '高', 'note': f'半年 {x}% / 1年 {y}%（1着時の決まり手構成）'})
        if a['avg_st'] is not None and b['avg_st'] is not None and a['avg_st'] <= 0.14 and b['avg_st'] <= 0.15:
            out.append({'label': f'{course}コース・スタート速め', 'confidence': '中', 'note': f'平均ST 半年 {a["avg_st"]} / 1年 {b["avg_st"]}'})
    # recent change: same basic metric, avoid overclaiming
    p6, p1 = perf(g6), perf(g1)
    if p6['n'] >= 30 and p1['n'] >= 50 and p6['top3'] is not None and p1['top3'] is not None:
        d = p6['top3'] - p1['top3']
        if d >= 6:
            out.append({'label': '最近6か月で3連対率上向き', 'confidence': '中', 'note': f'半年 {p6["top3"]}% / 1年 {p1["top3"]}%'})
        elif d <= -6:
            out.append({'label': '最近6か月で3連対率下向き', 'confidence': '中', 'note': f'半年 {p6["top3"]}% / 1年 {p1["top3"]}%'})
    return out[:6]


def main():
    cards = load_many(str(SRC / 'programs/race_cards/*/*/*.csv'))
    results = load_many(str(SRC / 'results/realtime/*/*/*.csv'))
    if cards.empty or results.empty:
        raise SystemExit('race cards/results not found')

    cl = cards_to_long(cards)
    rl = results_to_long(results)
    panel = build_panel(cl, rl, pd.DataFrame()).dropna(subset=['race_date', 'regno', 'finish']).copy()
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
            'regno': int(reg),
            'name': name,
            'class': None if pd.isna(row.get('class_grade')) else str(row.get('class_grade')),
            'branch': None if pd.isna(row.get('branch')) else str(row.get('branch')),
            'birthplace': None if pd.isna(row.get('birthplace')) else str(row.get('birthplace')),
            'age': None if pd.isna(row.get('age')) else int(float(row.get('age'))),
            'term': None if pd.isna(row.get('term')) else str(row.get('term')),
            'six_month': perf(g6),
            'one_year': perf(g1),
            'courses_6m': c6,
            'courses_1y': c1,
            'strongest_course_6m': strongest_course(c6),
            'traits': trait_candidates(g6, g1, c6, c1),
        })

    racers.sort(key=lambda x: (x['class'] or '', x['one_year']['win1'] or 0, x['regno']), reverse=True)
    payload = {
        'updated': asof.strftime('%Y-%m-%d'),
        'window_6m_start': start_6m.strftime('%Y-%m-%d'),
        'window_1y_start': start_1y.strftime('%Y-%m-%d'),
        'count': len(racers),
        'racers': racers,
        'notes': [
            '半年・1年は実レース結果から再集計',
            '特殊能力欄は現時点では決まり手構成・ST・直近変化など再現可能な記述のみ',
            '心理・相手依存などの能力は別検証で裏が取れたものだけ後から追加'
        ]
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'wrote {OUT} racers={len(racers)} asof={asof.date()}')


if __name__ == '__main__':
    main()
