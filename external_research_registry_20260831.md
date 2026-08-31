# External boat-race research registry — 2026-08-31

Purpose: collect public research themes/definitions from other boat-race data sites and analysts, then reproduce the hypotheses on our own historical data. Do not copy proprietary datasets wholesale; use public facts, definitions, and published aggregate findings as research seeds.

## Priority A — Boat Race Biyori / 競艇日和

Source: https://kyoteibiyori.com/
Version-up archive: https://kyoteibiyori.com/vup/

High-value research themes already exposed by the site:

1. Front-push / 前付け
   - racer-specific front-push history by drawn boat
   - destination-course probabilities
   - alert when exhibition entry changes
   - published comparison of boat-1 ST / ST rank / win rate when boats 4–6 enter course 2 or 3 versus ordinary entry
   - our replication target: front-push probability, destination course, boat-1 win/escape/ST effects, affected surrounding courses, by racer/venue/depth

2. Deep start / 深イン and slow-vs-dash
   - results now tag slow/dash and starts around 100m as deep
   - replication target: start depth proxy, front-push depth, boat-1 ST deterioration, escape/win impact

3. 超展開データ
   - records how each racer attacks at turn 1, how they are attacked, and win/loss outcomes
   - explicitly records boat-1 resistance counts and courses 2–6 squeezing/closing-in counts
   - replication target: resist rate, squeeze rate, attack type, attack success, resistance success, downstream second/third supply

4. Losing-method tables
   - for courses 2–6: allow-escape, beaten-by-sashi, beaten-by-makuri, beaten-by-makuri-sashi
   - also identifies which course beat course 1 and by what method
   - replication target: full course×racer defensive profile and attacker-defender interactions

5. Escape-follow all-boat place rates
   - when a racer in courses 2–6 allows course 1 to escape, the site shows own/other boats' place rates
   - example use described by site: when racer X is course 2 and boat 1 escapes, compare 1-2 versus 1-3/1-6 etc.
   - replication target: P(second/third course | course1 escapes, follower racer/course), grade/sex/venue splits

6. Top-start analysis
   - top-start count/rate by course
   - first-place rate when top-starting
   - replication target: top-ST conversion rate and whether specific racers convert slit advantage into wins

7. Exhibition-ST vs race-ST gap
   - player-level stability grade C < B < A < S < SS
   - replication target: mean absolute gap, rank correlation, F exhibition handling, venue/racer reliability

8. Original exhibition analysis
   - racer lap-time analysis
   - lap comparison
   - exhibition comparison
   - venue-level original-exhibition rank-1 win rates

9. Tilt jump
   - tilt-jump first-place table
   - replication target: racer/course/venue tilt-change outcome and interaction with exhibition/attack type

10. Losing-other-course tendency / course-chain
    - when a racer fails from course 1, shows which course/method beat them
    - venue-specific result-pattern analysis by attack scenario

11. Phase/context filters
    - initial day, final day, night, F-holder average ST and ST rank
    - championship-only performance
    - grade/women/general-race splits
    - monthly up/down form list

12. Market information
    - odds history
    - ticket-sales history
    - real-time venue sales
    - research target: whether certain public signals are under/overpriced at 10/5 minutes before close

Published front-push study page:
https://kyoteibiyori.com/blog/20230301001
Definition used there: boats 4–6 enter course 2 or 3; compare boat-1 average ST, ST rank, and first-place rate with normal entry; one-year sample; accidents excluded.

Super-development-data explainer:
https://kyoteibiyori.com/blog/202509111001

## Priority A — BOATBoy WEB new-concept data

Source: https://www.boatboy.jp/forecast-data/shingainen-data/

Public definitions:
- course-1 first-place rate
- course-1 beaten-by-makuri rate
- course-1 beaten-by-sashi rate (winner method sashi or makuri-sashi when course 1 loses)
- course-2 allow-escape rate
- courses 2–6 sashi rate
- courses 2–6 makuri rate
- course-specific start counts and 2-place rates

Use: independent benchmark for our definitions and as a possible external consensus/filter. Do not assume denominator definitions match ours without checking.

## Priority A — AI BOAT RACE

Source: https://aiboatrace.jp/column

Public empirical themes to reproduce:
- motor 2-place-rate bands vs first-place rate; published result shows monotonic but small effect and no sharp universal threshold
- ST bands while controlling for course
- 5/6-course win conditions: class × fast start
- 3-course makuri-sashi conditions
- exhibition-time rank by venue
- start-exhibition vs race-ST discrepancy
- tilt-angle effects
- parts replacement effects
- night vs day
- water-type group effects
- venue×race-number patterns
- class effects and B-class good-course cases
- popularity/return and high-payout conditions
- model calibration and skip-rule / no-bet research

Published motor result (2024-03-01..2026-07-01, 767,625 starts):
- motor 2-rate <=30%: first-place 15.6%
- 30–35%: 16.3%
- 35–40%: 17.1%
- 40–45%: 18.3%
- >=45%: 19.3%
Interpretation from source: effect exists but is modest; course/racer dominate.

Published outer-course result:
- course 5 A1 first-place 10.8% vs B1 4.0%
- course 5 race ST <0.10 first-place 10.8% vs ST>=0.20 3.2%
Important caveat: race ST is not pre-race observable; reproduce with historical expected-ST predictors, not future actual ST.

## Priority B — ボートとデータ

Guide: https://www.boatrace-data.com/guide/
Blog: https://www.boatrace-data.com/blog/

Interesting design/data ideas:
- attack/defense ability bars: course 1 anti-makuri/anti-sashi; course 2 makuri/sashi; courses 3–6 makuri/makuri-sashi/sashi
- course-by-course finish-distribution heatmap versus venue average
- course-specialty spectrum
- Elo rating that accounts for opponent strength
- predicted payout category / volatility level
- historical answer-checking of AI predictions

Replication targets:
- opponent-adjusted racer rating
- venue-relative finish residuals
- attack/defense standardized scores
- payout-regime classifier separate from winner prediction

## Priority B — BR-STAT

Source: https://br-stat.jp/stats/stats-top

Public large-sample benchmarks:
- 5-year course win rates
- decision-method distribution and course-specific method shares
- venue first-course win rate
- venue upset / favorite-miss rate
- high-payout rate and payout distribution
- public AI prediction logs/accuracy

Use mainly as external sanity checks against our own aggregates and to detect bugs/sample-period effects.

## Priority B — other independent researchers

1. ボートレースデータ研究所 (note)
   - public tool described as using ~600k records
   - input ideas: venue, wind direction/speed, wave height, course-1 class, motor 2-rate, local racer, grade; exhibition-ST and ST rank after display
   - output is buy/skip or volatility class
   - research seed: explicit no-bet classification may matter more than universal prediction

2. どらかん＠競艇データ研究所 (note)
   - public article describes 2020-01..2026-02, 2,007,057 records testing exhibition ST vs race ST, including exhibition F as information
   - use as a hypothesis source; reproduce on our own data where available

3. もんさま (note)
   - focuses on original exhibition: straight, turn, exit, lap time; notes ordinary exhibition time has small spread and may be a weak standalone factor

## Research queue generated from external work

Tier S — should be tested/implemented first because our data can support it and it directly affects race structure:
1. front-push probability + destination course
2. deep-in/start-depth effect on boat 1
3. racer attack type / resistance / squeeze behavior
4. full losing-method matrix for all courses
5. escape-follow all-boat second/third distribution
6. top-ST conversion profile
7. exhibition-ST reliability by racer/venue
8. venue×attack-method×trifecta path

Tier A — context/modifier tests:
9. final day / initial day / championship / loser-race phase
10. F-holder / post-accident context
11. original exhibition rank and gaps by venue
12. tilt changes
13. parts replacement
14. current-meet form and trend
15. opponent-adjusted Elo / strength residual
16. class×course interactions
17. motor as a modest conditional modifier, not standalone trigger

Tier B — market/value research:
18. odds-history movement
19. ticket-sales concentration
20. market disagreement with validated structural signals
21. payout-regime / upset classifier
22. skip/no-bet classifier

## Rule for using external research

External published results are not treated as proof for our model. They enter as HYPOTHESIS_SOURCE. We promote only after:
- pre-race observable definition
- exact reproducible rule
- own-history discovery test
- untouched OOS validation
- adequate n and month stability
- ROI not driven by one payout if used as a betting rule
