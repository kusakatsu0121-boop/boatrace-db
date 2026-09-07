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
    """Internal memo: paired-meet test of late improvement on relatively weak motors.

    The previous version pooled all early races and all late races. That could mix
    different meets/venues and mistake composition changes for adjustment skill.
    This version derives a meet key from venue + inferred meet start, keeps only
    low-motor meets that contain both early and late samples, and evaluates the
    within-meet deltas before declaring a reproducible trait.
    """
    base = {'window': label, 'status': '不足', 'confidence': '低'}
    required = {'motor_2rate', 'day_no', 'race_date', 'レース場', 'course_adjusted_perf', 'finish'}
    if g.empty or not required.issubset(g.columns):
        base['reason'] = '必要データなし'
        return base

    x = g.dropna(subset=['motor_2rate', 'day_no', 'race_date', 'レース場', 'course_adjusted_perf', 'finish']).copy()
    if len(x) < 20:
        base['reason'] = '標本不足'
        return base

    x['race_date'] = pd.to_datetime(x['race_date'])
    x['day_no'] = pd.to_numeric(x['day_no'], errors='coerce')
    x = x.dropna(subset=['day_no'])
    # day_no=1 is the inferred meet start. Venue is included to avoid accidental joins.
    x['meet_start'] = x['race_date'].dt.normalize() - pd.to_timedelta(x['day_no'] - 1, unit='D')
    x['meet_key'] = x['レース場'].astype(str) + '|' + x['meet_start'].dt.strftime('%Y-%m-%d')

    meet_motor = x.groupby('meet_key')['motor_2rate'].median().dropna()
    if len(meet_motor) < 4:
        base['reason'] = '節数不足'
        base['meet_n'] = int(len(meet_motor))
        return base

    # Racer-relative threshold, but now applied at meet level rather than race-row level.
    cutoff = float(meet_motor.quantile(.25))
    low_keys = set(meet_motor[meet_motor <= cutoff].index)
    bad = x[x['meet_key'].isin(low_keys)].copy()

    paired = []
    for key, h in bad.groupby('meet_key'):
        early = h[h['day_no'].between(1, 2)]
        late = h[h['day_no'] >= 5]
        if early.empty or late.empty:
            continue
        e, l = phase(early), phase(late)
        if e['course_adj'] is None or l['course_adj'] is None:
            continue
        paired.append({
            'meet_key': key,
            'motor_2rate': safe_num(meet_motor.get(key), 1),
            'early_n': e['n'],
            'late_n': l['n'],
            'course_adj_delta': safe_num(l['course_adj'] - e['course_adj']),
            'top3_delta_pt': None if e['top3'] is None or l['top3'] is None else safe_num(l['top3'] - e['top3'], 1),
            'finish_improve': None if e['avg_finish'] is None or l['avg_finish'] is None else safe_num(e['avg_finish'] - l['avg_finish'], 2),
        })

    min_meets = 3 if label == '6か月' else 5
    out = {
        'window': label,
        'motor_2rate_q25_meet_level': safe_num(cutoff, 1),
        'low_motor_meets': int(len(low_keys)),
        'paired_meets': int(len(paired)),
    }
    if len(paired) < min_meets:
        out.update({'status': '不足', 'confidence': '低', 'reason': f'前半・後半を同一節で比較できる低調機節が{min_meets}節未満'})
        return out

    p = pd.DataFrame(paired)
    cad_med = float(p['course_adj_delta'].median())
    positive_rate = float((p['course_adj_delta'] > 0).mean())
    top3_med = float(p['top3_delta_pt'].dropna().median()) if p['top3_delta_pt'].notna().any() else None
    finish_med = float(p['finish_improve'].dropna().median()) if p['finish_improve'].notna().any() else None

    early_all = bad[bad['day_no'].between(1, 2) & bad['meet_key'].isin(p['meet_key'])]
    late_all = bad[(bad['day_no'] >= 5) & bad['meet_key'].isin(p['meet_key'])]
    e_all, l_all = phase(early_all), phase(late_all)

    out.update({
        'paired_course_adj_delta_median': safe_num(cad_med),
        'paired_positive_meet_rate': safe_num(positive_rate * 100, 1),
        'paired_top3_delta_median_pt': safe_num(top3_med, 1) if top3_med is not None else None,
        'paired_finish_improve_median': safe_num(finish_med, 2) if finish_med is not None else None,
        'early_pooled': e_all,
        'late_pooled': l_all,
        'meet_examples': paired[:8],
    })

    supportive_up = (top3_med is not None and top3_med >= 4) or (finish_med is not None and finish_med >= .15)
    supportive_down = (top3_med is not None and top3_med <= -4) or (finish_med is not None and finish_med <= -.15)
    if cad_med >= .18 and positive_rate >= .67 and supportive_up:
        status = '低調機から後半立て直し候補'
    elif cad_med <= -.18 and positive_rate <= .33 and supportive_down:
        status = '低調機で後半悪化候補'
    else:
        status = '低調機で明確な後半差なし'

    confidence = '高' if len(paired) >= 8 and abs(cad_med) >= .25 and (positive_rate >= .75 or positive_rate <= .25) else ('中' if len(paired) >= 5 else '低')
    out.update({'status': status, 'confidence': confidence, 'validation': '同一節ペア比較'})
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
        # Remove stale tag if the stricter paired-meet validation no longer reproduces it.
        if not stable and '低調機でも節後半に立て直す' in tags:
            tags.remove('低調機でも節後半に立て直す')
        if stable and '低調機でも節後半に立て直す' not in tags:
            tags.append('低調機でも節後半に立て直す')
            reproduced += 1

    payload.setdefault('notes', []).append('低調機の節後半立て直し判定を、別節混在の集計から同一節ペア比較へ厳格化')
    payload['adjustment_memo_summary'] = {
        'reproduced_low_motor_recovery_racers': reproduced,
        'validation': 'paired_meet',
        'minimum_paired_meets_6m': 3,
        'minimum_paired_meets_1y': 5,
    }
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'enriched {TARGET} reproduced_low_motor_recovery={reproduced} validation=paired_meet')


if __name__ == '__main__':
    main()
