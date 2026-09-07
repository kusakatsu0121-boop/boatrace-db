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


def add_meet_key(g: pd.DataFrame) -> pd.DataFrame:
    x = g.copy()
    x['race_date'] = pd.to_datetime(x['race_date'])
    x['day_no'] = pd.to_numeric(x['day_no'], errors='coerce')
    x = x.dropna(subset=['day_no', 'race_date', 'レース場', 'course_adjusted_perf'])
    x['meet_start'] = x['race_date'].dt.normalize() - pd.to_timedelta(x['day_no'] - 1, unit='D')
    x['meet_key'] = x['レース場'].astype(str) + '|' + x['meet_start'].dt.strftime('%Y-%m-%d')
    return x


def build_meet_rows(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for reg, g in panel.groupby('regno'):
        x = add_meet_key(g)
        if x.empty:
            continue
        overall = float(x['course_adjusted_perf'].mean())
        for key, h in x.groupby('meet_key'):
            early = h[h['day_no'].between(1, 2)]
            late = h[h['day_no'] >= 5]
            if early.empty or late.empty:
                continue
            e = float(early['course_adjusted_perf'].mean())
            l = float(late['course_adjusted_perf'].mean())
            bad_early = e <= overall - 0.25
            recovered = bad_early and l >= overall - 0.05 and (l - e) >= 0.25
            rows.append({
                'regno': int(reg),
                'meet_key': key,
                'overall_course_adj': overall,
                'early_course_adj': e,
                'late_course_adj': l,
                'delta': l - e,
                'early_n': int(len(early)),
                'late_n': int(len(late)),
                'bad_early': bool(bad_early),
                'recovered': bool(recovered),
            })
    return pd.DataFrame(rows)


def summarize(meets: pd.DataFrame, label: str, baseline_rate: float | None) -> dict:
    out = {
        'window': label,
        'validation': '同一節・前半不振節限定・全選手基準比較',
        'bad_early_definition': '前半course_adjusted_perfが本人期間平均より0.25以上低い',
        'recovery_definition': '後半が本人期間平均-0.05以上まで戻り、前半比+0.25以上',
        'population_recovery_rate': safe_num(baseline_rate * 100, 1) if baseline_rate is not None else None,
    }
    if meets.empty:
        out.update({'status': '不足', 'confidence': '低', 'reason': '同一節前半・後半データなし'})
        return out
    bad = meets[meets['bad_early']].copy()
    min_bad = 3 if label == '6か月' else 5
    out['paired_meets'] = int(len(meets))
    out['bad_early_meets'] = int(len(bad))
    if len(bad) < min_bad:
        out.update({'status': '不足', 'confidence': '低', 'reason': f'前半不振節が{min_bad}節未満'})
        return out
    rate = float(bad['recovered'].mean())
    med_delta = float(bad['delta'].median())
    lift = None if baseline_rate is None else rate - baseline_rate
    out.update({
        'recovery_rate': safe_num(rate * 100, 1),
        'recovery_rate_vs_population_pt': safe_num(lift * 100, 1) if lift is not None else None,
        'bad_early_delta_median': safe_num(med_delta),
        'examples': [
            {
                'meet_key': r['meet_key'],
                'early_course_adj': safe_num(r['early_course_adj']),
                'late_course_adj': safe_num(r['late_course_adj']),
                'delta': safe_num(r['delta']),
                'recovered': bool(r['recovered']),
            }
            for _, r in bad.head(8).iterrows()
        ],
    })
    if lift is not None and lift >= 0.20 and rate >= 0.60 and med_delta >= 0.25:
        status = '前半不振節から立て直す候補'
    elif lift is not None and lift <= -0.20 and rate <= 0.30 and med_delta < 0.15:
        status = '前半不振節を立て直しにくい候補'
    else:
        status = '前半不振節で明確な個人差なし'
    confidence = '高' if len(bad) >= 8 and lift is not None and abs(lift) >= 0.25 else ('中' if len(bad) >= 5 else '低')
    out.update({'status': status, 'confidence': confidence})
    return out


def window_stats(panel: pd.DataFrame, label: str):
    meet_rows = build_meet_rows(panel)
    if meet_rows.empty:
        return meet_rows, None
    bad = meet_rows[meet_rows['bad_early']]
    baseline = float(bad['recovered'].mean()) if len(bad) else None
    return meet_rows, baseline


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
    p6 = panel[panel['race_date'].ge(asof - pd.Timedelta(days=183))]
    p1 = panel[panel['race_date'].ge(asof - pd.Timedelta(days=365))]

    m6, base6 = window_stats(p6, '6か月')
    m1, base1 = window_stats(p1, '1年')
    by6 = {int(k): v for k, v in m6.groupby('regno')} if not m6.empty else {}
    by1 = {int(k): v for k, v in m1.groupby('regno')} if not m1.empty else {}

    payload = json.loads(TARGET.read_text(encoding='utf-8'))
    reproduced_up = 0
    reproduced_down = 0
    for racer in payload.get('racers', []):
        reg = int(racer['regno'])
        s6 = summarize(by6.get(reg, pd.DataFrame()), '6か月', base6)
        s1 = summarize(by1.get(reg, pd.DataFrame()), '1年', base1)
        stable_up = s6.get('status') == '前半不振節から立て直す候補' and s1.get('status') == '前半不振節から立て直す候補'
        stable_down = s6.get('status') == '前半不振節を立て直しにくい候補' and s1.get('status') == '前半不振節を立て直しにくい候補'
        memo = racer.setdefault('player_memo', {})
        memo['bad_early_recovery_6m'] = s6
        memo['bad_early_recovery_1y'] = s1
        memo['bad_early_recovery_reproduced'] = stable_up
        memo['bad_early_nonrecovery_reproduced'] = stable_down
        tags = memo.setdefault('memo_tags', [])
        for tag in ['前半不振節から立て直す', '前半不振節を立て直しにくい']:
            if tag in tags:
                tags.remove(tag)
        if stable_up:
            tags.append('前半不振節から立て直す')
            reproduced_up += 1
        elif stable_down:
            tags.append('前半不振節を立て直しにくい')
            reproduced_down += 1

    payload.setdefault('notes', []).append('節後半上昇と、前半不振節からの実質的な立て直しを分離。全選手の同条件回復率との差まで検証')
    summary = payload.setdefault('adjustment_memo_summary', {})
    summary.update({
        'bad_early_recovery_population_rate_6m': safe_num(base6 * 100, 1) if base6 is not None else None,
        'bad_early_recovery_population_rate_1y': safe_num(base1 * 100, 1) if base1 is not None else None,
        'reproduced_bad_early_recovery_racers': reproduced_up,
        'reproduced_bad_early_nonrecovery_racers': reproduced_down,
        'bad_early_validation': 'paired_meet_plus_population_baseline',
        'minimum_bad_early_meets_6m': 3,
        'minimum_bad_early_meets_1y': 5,
    })
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'enriched {TARGET} bad_early_recovery={reproduced_up} bad_early_nonrecovery={reproduced_down} population6={base6} population1={base1}')


if __name__ == '__main__':
    main()
