# Edogawa venue-first research plan — 2026-09-02

Goal: find stable, actionable betting information specific to BOAT RACE Edogawa. Bet type is NOT fixed: evaluate win, exacta, quinella, trifecta, and trio when data exists. Prefer stable OOS ROI over peak ROI.

## Public hypotheses to test, not assume
1. Wind x tide interaction changes the value of inside vs center/outside courses.
2. Rough-water / wave-skill is a racer-specific Edogawa effect that may survive controls for class and general ability.
3. Start/straight-line ability may matter more under strong falling tide / rough conditions.
4. Calm conditions may restore inside-course advantage.
5. Some conditions may make 2-course difference or 4-course attack relatively more valuable.

## Required features
- venue=03 Edogawa only
- race date/time
- actual course
- finish/order and winning method
- payout/odds for every available bet type
- wind direction, wind speed
- tide direction (rising/falling/slack), tide level and preferably tide velocity / time from high-low tide
- wave height if available
- racer class, national strength
- Edogawa historical performance PRIOR to race
- start timing / start ability PRIOR to race
- motor/straight-line proxy available before purchase
- F/L/accident context where available

## Leakage-safe derived indicators
- EdogawaSkill = prior Edogawa performance residual after controlling course, class, opponent strength and broad era.
- RoughSkill = prior performance residual specifically in rough/high-wind/high-wave Edogawa races.
- StartEdge = entrant start-strength relative to the other five racers.
- InsideFragility = estimated probability that course 1 loses, calibrated only on prior data.

## Candidate condition grid
Wind speed: <2, 2-4, 4-6, >=6 m/s.
Wind direction: head / tail / cross, using Edogawa-course-relative mapping.
Tide: rising / falling / slack; also bins by time from high/low tide if available.
Crosses: wind x tide, wind x RoughSkill, tide x StartEdge, course x RoughSkill.
Do not explode the grid unless each discovery cell has adequate n.

## Validation
Use chronological discovery -> validation -> untouched OOS. No random split for final claims.
Minimum promotion:
- discovery n >= 500 tickets (smaller cells remain exploratory)
- OOS n >= 300 tickets; prefer >=1000
- OOS ROI > 100%
- positive or near-positive performance across multiple calendar blocks, not one jackpot month
- remove largest payout and recalc ROI
- remove payouts >=10,000 and >=30,000 yen and recalc
- report max losing streak and max drawdown
- compare 1/2/3/4 tickets per race
- compare betting only top 1%, 3%, 5%, 10% of races by pre-race edge
- reject if profit is dominated by one payout or one month

## Product-oriented outputs
For each race produce only evidence-backed flags such as:
- INSIDE STRONG / INSIDE FRAGILE
- 2-COURSE DIFFERENCE LIVE
- CENTER ATTACK LIVE
- ROUGH-WATER SPECIALIST ADVANTAGE
- MARKET OVERPRICED / UNDERPRICED
Then show the bet type and small ticket set with the best validated stability. No guaranteed-win language.

## First priority tests
A. wind x tide -> course-1 loss / winning-method distribution
B. RoughSkill interaction -> OOS lift and market value
C. StartEdge under falling tide / strong wind
D. venue-specific EV ticket selection across bet types
E. stability ranking by OOS ROI, profitable-month share, jackpot-removed ROI, max drawdown
