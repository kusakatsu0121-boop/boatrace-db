#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel

SRC = Path('source/data')
OUT = Path('docs/racers.json')


def safe_num(v, digits=1):
    try:
        if v is None or not np.isfinite(float(v)):
            return None
        return round(float(v), digits)
    except Exception:
        return None


def stats(g: pd.DataFrame) -> dict:
    if g.empty:
        return {'n': 0, 'course_adj': None, 'top3': None, 'avg_finish': None, 'avg_st': None}
    normal = g[g['f_start'].fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {
        'n': int(len(g)),
        'course_adj': safe_num(g['course_adjusted_perf'].mean(), 3),
        'top3': safe_num(g['finish'].le(3).mean() * 100, 1),
        'avg_finish': safe_num(g['finish'].mean(), 2),
        'avg_st': safe_num(normal['actual_st'].mean(), 3) if 'actual_st' in normal.columns else None,
    }


def same_day_memo(g: pd.DataFrame, label: str) -> dict:
    need = {'race_date', 'race_no_num', 'finish', 'course_adjusted_perf'}
    if g.empty or not need.issubset(g.columns):
        return {'window': label, 'status': '不足', 'reason': '同日出走判定データなし'}

    x = g.dropna(subset=list(need)).copy()
    if 'レース場' not in x.columns:
        x['レース場'] = ''
    x = x.sort_values(['race_date', 'レース場', 'race_no_num', 'レースコード'])
    x['day_run_no'] = x.groupby(['race_date', 'レース場']).cumcount() + 1
    x['day_runs'] = x.groupby(['race_date', 'レース場'])['finish'].transform('size')
    x = x[x['day_runs'] >= 2]

    first = stats(x[x['day_run_no'].eq(1)])
    second = stats(x[x['day_run_no'].eq(2)])
    r = {'window': label, 'first_run': first, 'second_run': second, 'two_run_days': int((x[x['day_run_no'].eq(1)]).shape[0])}

    if first['n'] < 10 or second['n'] < 10 or first['course_adj'] is None or second['course_adj'] is None:
        r.update({'status': '不足', 'confidence': '低', 'note': '1走目または2走目が10走未満'})
        return r

    cad = second['course_adj'] - first['course_adj']
    t = second['top3'] - first['top3']
    f = first['avg_finish'] - second['avg_finish']
    st = None
    if first['avg_st'] is not None and second['avg_st'] is not None:
        st = first['avg_st'] - second['avg_st']

    r.update({
        'second_minus_first_course_adj': safe_num(cad, 3),
        'second_minus_first_top3_pt': safe_num(t, 1),
        'first_minus_second_avg_finish': safe_num(f, 2),
        'first_minus_second_avg_st_sec': safe_num(st, 3),
    })

    if cad >= 0.16 and (t >= 3 or f >= 0.12):
        status = '同日2走目で上げる候補'
    elif cad <= -0.16 and (t <= -3 or f <= -0.12):
        status = '同日2走目で落とす候補'
    else:
        status = '同日1走目/2走目で明確な差なし'

    n = min(first['n'], second['n'])
    confidence = '高' if n >= 25 and abs(cad) >= 0.22 else ('中' if n >= 15 else '低')
    r.update({'status': status, 'confidence': confidence})
    return r


def reproduced(a: dict, b: dict):
    accepted = {'同日2走目で上げる候補', '同日2走目で落とす候補'}
    if a.get('status') == b.get('status') and a.get('status') in accepted:
        return {
            'status': a['status'],
            'confidence': '高' if a.get('confidence') == '高' and b.get('confidence') == '高' else '中',
            'six_month': a,
            'one_year': b,
        }
    return None


def main():
    if not OUT.exists():
        raise SystemExit('docs/racers.json not found; run build_racer_site.py first')

    cards = load_many(str(SRC / 'programs/race_cards/*/*/*.csv'))
    results = load_many(str(SRC / 'results/realtime/*/*/*.csv'))
    title = load_many(str(SRC / 'programs/title/*/*/*.csv'))
    if cards.empty or results.empty:
        raise SystemExit('race cards/results not found')

    panel = build_panel(cards_to_long(cards), results_to_long(results), title).dropna(subset=['race_date', 'regno', 'finish']).copy()
    panel['race_date'] = pd.to_datetime(panel['race_date'])
    asof = panel['race_date'].max().normalize()
    p1 = panel[panel['race_date'].ge(asof - pd.Timedelta(days=365))]
    p6 = panel[panel['race_date'].ge(asof - pd.Timedelta(days=183))]

    payload = json.loads(OUT.read_text(encoding='utf-8'))
    by_reg = {int(r['regno']): r for r in payload.get('racers', [])}

    for reg, row in by_reg.items():
        g1 = p1[p1['regno'].eq(reg)]
        g6 = p6[p6['regno'].eq(reg)]
        m6 = same_day_memo(g6, '6か月')
        m1 = same_day_memo(g1, '1年')
        trait = reproduced(m6, m1)
        memo = row.setdefault('player_memo', {})
        memo['same_day_6m'] = m6
        memo['same_day_1y'] = m1
        memo['same_day_reproduced_trait'] = trait
        tags = memo.setdefault('memo_tags', [])
        for old in ['同日2走目で上げる', '同日2走目で落とす']:
            while old in tags:
                tags.remove(old)
        if trait:
            tag = trait['status'].replace('候補', '')
            if tag not in tags:
                tags.append(tag)

    notes = payload.setdefault('notes', [])
    note = '同日1走目→2走目の変化はコース補正成績を主軸に半年/1年で再現判定し、選手メモに蓄積'
    if note not in notes:
        notes.append(note)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'enriched same-day traits racers={len(by_reg)} asof={asof.date()}')


if __name__ == '__main__':
    main()
