#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel

SRC = Path('source/data')
TARGET = Path('docs/racers.json')


def safe_num(v, digits=3):
    try:
        if v is None or not np.isfinite(float(v)):
            return None
        return round(float(v), digits)
    except Exception:
        return None


def phase(g: pd.DataFrame) -> dict:
    if g.empty:
        return {'n': 0, 'course_adj': None, 'top3': None, 'avg_finish': None, 'avg_st': None}
    normal = g[g['f_start'].fillna(0).eq(0)] if 'f_start' in g.columns else g
    return {
        'n': int(len(g)),
        'course_adj': safe_num(g['course_adjusted_perf'].mean()),
        'top3': safe_num(g['finish'].le(3).mean() * 100, 1),
        'avg_finish': safe_num(g['finish'].mean(), 2),
        'avg_st': safe_num(normal['actual_st'].mean()) if 'actual_st' in normal.columns and len(normal) else None,
    }


def low_motor_recovery(g: pd.DataFrame, label: str) -> dict:
    """Internal memo: does the racer improve late in meets when assigned a low-rated motor?"""
    base = {'window': label, 'status': '不足', 'confidence': '低'}
    required = {'motor_2rate', 'day_no', 'course_adjusted_perf', 'finish'}
    if g.empty or not required.issubset(g.columns):
        base['reason'] = '必要データなし'
        return base

    x = g.dropna(subset=['motor_2rate', 'day_no']).copy()
    if len(x) < 20:
        base['reason'] = '標本不足'
        return base

    # Racer-relative threshold: bottom quartile of motors actually assigned in this window.
    cutoff = x['motor_2rate'].quantile(.25)
    bad = x[x['motor_2rate'] <= cutoff]
    early = bad[bad['day_no'].between(1, 2)]
    late = bad[bad['day_no'] >= 5]
    e, l = phase(early), phase(late)
    out = {
        'window': label,
        'motor_2rate_q25': safe_num(cutoff, 1),
        'bad_motor_n': int(len(bad)),
        'early': e,
        'late': l,
    }

    if e['n'] < 6 or l['n'] < 6 or e['course_adj'] is None or l['course_adj'] is None:
        out.update({'status': '不足', 'confidence': '低', 'reason': '低調モーター時の初盤/終盤標本不足'})
        return out

    delta = l['course_adj'] - e['course_adj']
    top3_delta = None if e['top3'] is None or l['top3'] is None else l['top3'] - e['top3']
    finish_delta = None if e['avg_finish'] is None or l['avg_finish'] is None else e['avg_finish'] - l['avg_finish']
    out.update({
        'late_minus_early_course_adj': safe_num(delta),
        'late_minus_early_top3_pt': safe_num(top3_delta, 1) if top3_delta is not None else None,
        'early_minus_late_avg_finish': safe_num(finish_delta, 2) if finish_delta is not None else None,
    })

    supportive_up = (top3_delta is not None and top3_delta >= 5) or (finish_delta is not None and finish_delta >= .20)
    supportive_down = (top3_delta is not None and top3_delta <= -5) or (finish_delta is not None and finish_delta <= -.20)
    if delta >= .20 and supportive_up:
        status = '低調機から後半立て直し候補'
    elif delta <= -.20 and supportive_down:
        status = '低調機で後半悪化候補'
    else:
        status = '低調機で明確な後半差なし'

    nmin = min(e['n'], l['n'])
    confidence = '高' if nmin >= 18 and abs(delta) >= .28 else ('中' if nmin >= 10 else '低')
    out.update({'status': status, 'confidence': confidence})
    return out


def main():
    if not TARGET.exists():
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

    payload = json.loads(TARGET.read_text(encoding='utf-8'))
    by6 = {int(k): v for k, v in p6.groupby('regno')}
    by1 = {int(k): v for k, v in p1.groupby('regno')}
    reproduced = 0

    for racer in payload.get('racers', []):
        reg = int(racer['regno'])
        g6 = by6.get(reg, pd.DataFrame())
        g1 = by1.get(reg, pd.DataFrame())
        a6 = low_motor_recovery(g6, '6か月')
        a1 = low_motor_recovery(g1, '1年')
        stable = a6.get('status') == '低調機から後半立て直し候補' and a1.get('status') == '低調機から後半立て直し候補'
        memo = racer.setdefault('player_memo', {})
        memo['low_motor_recovery_6m'] = a6
        memo['low_motor_recovery_1y'] = a1
        memo['low_motor_recovery_reproduced'] = stable
        tags = memo.setdefault('memo_tags', [])
        if stable and '低調機でも節後半に立て直す' not in tags:
            tags.append('低調機でも節後半に立て直す')
            reproduced += 1

    payload.setdefault('notes', []).append('低調モーター時の節後半立て直しを半年・1年で選手メモへ追加')
    payload['adjustment_memo_summary'] = {'reproduced_low_motor_recovery_racers': reproduced}
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'enriched {TARGET} reproduced_low_motor_recovery={reproduced}')


if __name__ == '__main__':
    main()
