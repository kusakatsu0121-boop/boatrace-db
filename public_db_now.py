#!/usr/bin/env python3
from pathlib import Path
import numpy as np
import pandas as pd

from racer_directory import load_many, cards_to_long, results_to_long, build_panel

SRC = Path('source/data')
OUT = Path('artifacts/public_db_now')
OUT.mkdir(parents=True, exist_ok=True)


def safe_div(a, b):
    return np.nan if not b else a / b


def main():
    cards = load_many(str(SRC/'programs/race_cards/*/*/*.csv'))
    results = load_many(str(SRC/'results/realtime/*/*/*.csv'))
    title = load_many(str(SRC/'programs/title/*/*/*.csv'))
    if cards.empty or results.empty:
        raise SystemExit('race_cards/results not found')

    p = build_panel(cards_to_long(cards), results_to_long(results), title)
    p = p.dropna(subset=['race_date','regno','actual_course','finish']).copy()
    p['actual_course'] = p['actual_course'].astype(int)
    p['finish'] = pd.to_numeric(p['finish'], errors='coerce')
    p['actual_st'] = pd.to_numeric(p['actual_st'], errors='coerce')
    p['method'] = p.get('決まり手', '').fillna('').astype(str)
    p['venue'] = p.get('レース場', '').fillna('').astype(str)

    latest_name = (p.sort_values('race_date').groupby('regno')['name'].last().to_dict()
                   if 'name' in p.columns else {})

    # Course baselines for lift calculations.
    base_rows = []
    for c, g in p.groupby('actual_course'):
        n = len(g)
        base_rows.append({
            'course': int(c), 'n': n,
            'p1': (g.finish.eq(1)).mean(),
            'p2': (g.finish.eq(2)).mean(),
            'p3': (g.finish.eq(3)).mean(),
            'avg_st': g.loc[g.get('f_start',0).fillna(0).eq(0),'actual_st'].mean(),
            'allow_escape_rate': (g.method.eq('逃げ')).mean(),
        })
    base = pd.DataFrame(base_rows).set_index('course')

    # 1) Racer x course metrics.
    rows = []
    for (reg, c), g in p.groupby(['regno','actual_course']):
        c = int(c); n = len(g); wins = g.finish.eq(1)
        normal = g[g.get('f_start',0).fillna(0).eq(0)]
        r = {
            'regno': int(reg), 'name': latest_name.get(int(reg), ''), 'course': c, 'n': n,
            'p1': wins.mean(), 'p2': g.finish.eq(2).mean(), 'p3': g.finish.eq(3).mean(),
            'top2': g.finish.le(2).mean(), 'top3': g.finish.le(3).mean(),
            'avg_st': normal.actual_st.mean(),
            'escape_win_rate': ((wins) & g.method.eq('逃げ')).mean(),
            'sashi_win_rate': ((wins) & g.method.eq('差し')).mean(),
            'makuri_win_rate': ((wins) & g.method.eq('まくり')).mean(),
            'makuri_sashi_win_rate': ((wins) & g.method.eq('まくり差し')).mean(),
            'allow_escape_rate': g.method.eq('逃げ').mean() if c != 1 else np.nan,
            'beaten_sashi_rate': ((~wins) & g.method.eq('差し')).mean() if c == 1 else np.nan,
            'beaten_makuri_rate': ((~wins) & g.method.eq('まくり')).mean() if c == 1 else np.nan,
            'beaten_makuri_sashi_rate': ((~wins) & g.method.eq('まくり差し')).mean() if c == 1 else np.nan,
        }
        if c in base.index:
            r['p1_lift_pt'] = r['p1'] - base.loc[c,'p1']
            r['p2_lift_pt'] = r['p2'] - base.loc[c,'p2']
            r['p3_lift_pt'] = r['p3'] - base.loc[c,'p3']
            r['st_edge_sec'] = base.loc[c,'avg_st'] - r['avg_st']
        rows.append(r)
    racer_course = pd.DataFrame(rows).sort_values(['regno','course'])
    racer_course.to_csv(OUT/'racer_course_metrics.csv', index=False)

    # Race order map: course occupying each finishing position.
    rr = p[['レースコード','regno','name','actual_course','finish']].copy()
    race_order = rr.pivot_table(index='レースコード', columns='finish', values='actual_course', aggfunc='first')
    race_order = race_order.rename(columns={1:'winner_course',2:'second_course',3:'third_course'})
    race_order = race_order[[c for c in ['winner_course','second_course','third_course'] if c in race_order.columns]]
    race_order = race_order.dropna().astype(int)

    # Winner-course conditional baselines.
    sec_base = (race_order.groupby(['winner_course','second_course']).size()
                / race_order.groupby('winner_course').size()).rename('rate').reset_index()
    thr_base = (race_order.groupby(['winner_course','third_course']).size()
                / race_order.groupby('winner_course').size()).rename('rate').reset_index()
    sec_map = {(int(r.winner_course),int(r.second_course)):float(r.rate) for _,r in sec_base.iterrows()}
    thr_map = {(int(r.winner_course),int(r.third_course)):float(r.rate) for _,r in thr_base.iterrows()}

    # 2) Focal racer winner -> target course follow rates.
    wins = p[p.finish.eq(1)][['レースコード','regno','name','actual_course']].rename(columns={'actual_course':'winner_course'})
    wins = wins.merge(race_order.reset_index(), on=['レースコード','winner_course'], how='inner')
    follow_rows = []
    for (reg, wc), g in wins.groupby(['regno','winner_course']):
        wn = len(g)
        for pos, col, bm in [(2,'second_course',sec_map),(3,'third_course',thr_map)]:
            counts = g[col].value_counts()
            for tc in range(1,7):
                if tc == int(wc):
                    continue
                k = int(counts.get(tc,0)); rate = safe_div(k,wn); b = bm.get((int(wc),tc),np.nan)
                follow_rows.append({
                    'regno':int(reg),'name':latest_name.get(int(reg),''),'winner_course':int(wc),
                    'position':pos,'target_course':tc,'wins_n':wn,'count':k,'rate':rate,
                    'baseline_rate':b,'lift_pt':rate-b if pd.notna(b) else np.nan,
                })
    pd.DataFrame(follow_rows).sort_values(['regno','winner_course','position','target_course']).to_csv(
        OUT/'winner_follow_courses.csv', index=False)

    # 3) Course chain: first -> second -> third.
    chain_rows = []
    for (wc, sc), g in race_order.groupby(['winner_course','second_course']):
        n = len(g); counts = g.third_course.value_counts()
        for tc in range(1,7):
            if tc in (int(wc),int(sc)):
                continue
            k=int(counts.get(tc,0)); rate=safe_div(k,n); b=thr_map.get((int(wc),tc),np.nan)
            chain_rows.append({
                'winner_course':int(wc),'second_course':int(sc),'third_course':tc,
                'first_second_n':n,'count':k,'rate':rate,'baseline_third_given_winner':b,
                'lift_pt':rate-b if pd.notna(b) else np.nan,
            })
    pd.DataFrame(chain_rows).sort_values(['winner_course','second_course','rate'],ascending=[True,True,False]).to_csv(
        OUT/'course_chain.csv', index=False)

    # 4) Venue x course baselines.
    venue_rows=[]
    for (venue,c),g in p.groupby(['venue','actual_course']):
        if not venue: continue
        wins=g.finish.eq(1); n=len(g)
        venue_rows.append({
            'venue':venue,'course':int(c),'n':n,'p1':wins.mean(),'p2':g.finish.eq(2).mean(),'p3':g.finish.eq(3).mean(),
            'top2':g.finish.le(2).mean(),'top3':g.finish.le(3).mean(),
            'avg_st':g.loc[g.get('f_start',0).fillna(0).eq(0),'actual_st'].mean(),
            'escape_rate':((wins)&g.method.eq('逃げ')).mean(),
            'sashi_win_rate':((wins)&g.method.eq('差し')).mean(),
            'makuri_win_rate':((wins)&g.method.eq('まくり')).mean(),
            'makuri_sashi_win_rate':((wins)&g.method.eq('まくり差し')).mean(),
        })
    pd.DataFrame(venue_rows).sort_values(['venue','course']).to_csv(OUT/'venue_course_metrics.csv',index=False)

    summary = {
        'race_min_date': str(p.race_date.min().date()),
        'race_max_date': str(p.race_date.max().date()),
        'races': int(p['レースコード'].nunique()),
        'entries': int(len(p)),
        'racers': int(p.regno.nunique()),
        'racer_course_rows': int(len(racer_course)),
        'winner_follow_rows': int(len(follow_rows)),
        'course_chain_rows': int(len(chain_rows)),
        'venue_course_rows': int(len(venue_rows)),
    }
    pd.DataFrame([summary]).to_csv(OUT/'summary.csv',index=False)
    print(pd.DataFrame([summary]).to_string(index=False))
    print('WROTE', OUT)

if __name__ == '__main__':
    main()
