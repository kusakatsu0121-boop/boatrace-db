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


def add_meet_key(g: pd.DataFrame) -> pd.DataFrame:
    x = g.copy()
    x['race_date'] = pd.to_datetime(x['race_date'])
    x['day_no'] = pd.to_numeric(x['day_no'], errors='coerce')
    x = x.dropna(subset=['day_no', 'race_date', 'レース場'])
    x['meet_start'] = x['race_date'].dt.normalize() - pd.to_timedelta(x['day_no'] - 1, unit='D')
    x['meet_key'] = x['レース場'].astype(str) + '|' + x['meet_start'].dt.strftime('%Y-%m-%d')
    return x


def paired_late_meet(g: pd.DataFrame, label: str) -> dict:
    """All-motor internal memo: validate early->late change within each meet.

    This deliberately avoids the old pooled comparison, which could mix different
    meets and create a false late-meet effect from venue/course/opponent composition.
    Only meets containing both day 1-2 and day 5+ samples are paired.
    """
    required = {'day_no', 'race_date', 'レース場', 'course_adjusted_perf', 'finish'}
    base = {'window': label, 'status': '不足', 'confidence': '低', 'validation': '同一節ペア比較'}
    if g.empty or not required.issubset(g.columns):
        base['reason'] = '必要データなし'
        return base
    x = g.dropna(subset=['day_no', 'race_date', 'レース場', 'course_adjusted_perf', 'finish']).copy()
    if len(x) < 20:
        base['reason'] = '標本不足'
        base['n'] = int(len(x))
        return base
    x = add_meet_key(x)
    paired = []
    for key, h in x.groupby('meet_key'):
        early = h[h['day_no'].between(1, 2)]
        late = h[h['day_no'] >= 5]
        if early.empty or late.empty:
            continue
        e, l = phase(early), phase(late)
        if e['course_adj'] is None or l['course_adj'] is None:
            continue
        paired.append({
            'meet_key': key,
            'early_n': e['n'],
            'late_n': l['n'],
            'course_adj_delta': safe_num(l['course_adj'] - e['course_adj']),
            'top3_delta_pt': None if e['top3'] is None or l['top3'] is None else safe_num(l['top3'] - e['top3'], 1),
            'finish_improve': None if e['avg_finish'] is None or l['avg_finish'] is None else safe_num(e['avg_finish'] - l['avg_finish'], 2),
        })
    min_meets = 4 if label == '6か月' else 7
    out = {'window': label, 'paired_meets': int(len(paired)), 'validation': '同一節ペア比較'}
    if len(paired) < min_meets:
        out.update({'status': '不足', 'confidence': '低', 'reason': f'前半・後半を同一節で比較できる節が{min_meets}節未満'})
        return out
    p = pd.DataFrame(paired)
    cad_med = float(p['course_adj_delta'].median())
    positive_rate = float((p['course_adj_delta'] > 0).mean())
    top3_med = float(p['top3_delta_pt'].dropna().median()) if p['top3_delta_pt'].notna().any() else None
    finish_med = float(p['finish_improve'].dropna().median()) if p['finish_improve'].notna().any() else None
    out.update({
        'paired_course_adj_delta_median': safe_num(cad_med),
        'paired_positive_meet_rate': safe_num(positive_rate * 100, 1),
        'paired_top3_delta_median_pt': safe_num(top3_med, 1) if top3_med is not None else None,
        'paired_finish_improve_median': safe_num(finish_med, 2) if finish_med is not None else None,
        'meet_examples': paired[:10],
    })
    supportive_up = (top3_med is not None and top3_med >= 4) or (finish_med is not None and finish_med >= .15)
    supportive_down = (top3_med is not None and top3_med <= -4) or (finish_med is not None and finish_med <= -.15)
    if cad_med >= .18 and positive_rate >= .67 and supportive_up:
        status = '節後半上昇候補'
    elif cad_med <= -.18 and positive_rate <= .33 and supportive_down:
        status = '節後半低下候補'
    else:
        status = '節後半に明確な差なし'
    confidence = '高' if len(paired) >= 10 and abs(cad_med) >= .25 and (positive_rate >= .75 or positive_rate <= .25) else ('中' if len(paired) >= 7 else '低')
    out.update({'status': status, 'confidence': confidence})
    return out


def low_motor_recovery(g: pd.DataFrame, label: str) -> dict:
    required = {'motor_2rate', 'day_no', 'race_date', 'レース場', 'course_adjusted_perf', 'finish'}
    base = {'window': label, 'status': '不足', 'confidence': '低', 'validation': '同一節ペア比較'}
    if g.empty or not required.issubset(g.columns):
        base['reason'] = '必要データなし'
        return base
    x = g.dropna(subset=['motor_2rate', 'day_no', 'race_date', 'レース場', 'course_adjusted_perf', 'finish']).copy()
    if len(x) < 20:
        base['reason'] = '標本不足'
        return base
    x = add_meet_key(x)
    meet_motor = x.groupby('meet_key')['motor_2rate'].median().dropna()
    if len(meet_motor) < 4:
        base['reason'] = '節数不足'
        base['meet_n'] = int(len(meet_motor))
        return base
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
    out = {'window': label, 'motor_2rate_q25_meet_level': safe_num(cutoff, 1), 'low_motor_meets': int(len(low_keys)), 'paired_meets': int(len(paired)), 'validation': '同一節ペア比較'}
    if len(paired) < min_meets:
        out.update({'status': '不足', 'confidence': '低', 'reason': f'前半・後半を同一節で比較できる低調機節が{min_meets}節未満'})
        return out
    p = pd.DataFrame(paired)
    cad_med = float(p['course_adj_delta'].median())
    positive_rate = float((p['course_adj_delta'] > 0).mean())
    top3_med = float(p['top3_delta_pt'].dropna().median()) if p['top3_delta_pt'].notna().any() else None
    finish_med = float(p['finish_improve'].dropna().median()) if p['finish_improve'].notna().any() else None
    out.update({
        'paired_course_adj_delta_median': safe_num(cad_med),
        'paired_positive_meet_rate': safe_num(positive_rate * 100, 1),
        'paired_top3_delta_median_pt': safe_num(top3_med, 1) if top3_med is not None else None,
        'paired_finish_improve_median': safe_num(finish_med, 2) if finish_med is not None else None,
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
    reproduced_low = 0
    reproduced_late = 0
    for racer in payload.get('racers', []):
        reg = int(racer['regno'])
        g6 = by6.get(reg, pd.DataFrame())
        g1 = by1.get(reg, pd.DataFrame())
        a6 = low_motor_recovery(g6, '6か月')
        a1 = low_motor_recovery(g1, '1年')
        l6 = paired_late_meet(g6, '6か月')
        l1 = paired_late_meet(g1, '1年')
        stable_low = a6.get('status') == '低調機から後半立て直し候補' and a1.get('status') == '低調機から後半立て直し候補'
        stable_late = l6.get('status') == '節後半上昇候補' and l1.get('status') == '節後半上昇候補'
        memo = racer.setdefault('player_memo', {})
        memo['low_motor_recovery_6m'] = a6
        memo['low_motor_recovery_1y'] = a1
        memo['low_motor_recovery_reproduced'] = stable_low
        memo['late_meet_paired_6m'] = l6
        memo['late_meet_paired_1y'] = l1
        memo['late_meet_paired_reproduced'] = stable_late
        tags = memo.setdefault('memo_tags', [])
        for stale in ['節後半に上げる', '節後半上昇']:
            if stale in tags:
                tags.remove(stale)
        if not stable_low and '低調機でも節後半に立て直す' in tags:
            tags.remove('低調機でも節後半に立て直す')
        if stable_low and '低調機でも節後半に立て直す' not in tags:
            tags.append('低調機でも節後半に立て直す')
            reproduced_low += 1
        if stable_late and '節後半に上げる（同一節で再現）' not in tags:
            tags.append('節後半に上げる（同一節で再現）')
            reproduced_late += 1
        if not stable_late and '節後半に上げる（同一節で再現）' in tags:
            tags.remove('節後半に上げる（同一節で再現）')
    payload.setdefault('notes', []).append('節前半→後半の判定を全モーター対象でも同一節ペア比較へ厳格化')
    payload['adjustment_memo_summary'] = {
        'reproduced_low_motor_recovery_racers': reproduced_low,
        'reproduced_late_meet_racers': reproduced_late,
        'validation': 'paired_meet',
        'minimum_paired_meets_late_6m': 4,
        'minimum_paired_meets_late_1y': 7,
        'minimum_paired_meets_low_motor_6m': 3,
        'minimum_paired_meets_low_motor_1y': 5,
    }
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'enriched {TARGET} reproduced_late={reproduced_late} reproduced_low_motor={reproduced_low} validation=paired_meet')


if __name__ == '__main__':
    main()
