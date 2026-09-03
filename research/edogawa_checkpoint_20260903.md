# Edogawa research checkpoint 2026-09-03

## Fixed muscle-ticket scan
Data: 1,668 Edogawa races, 2025-11-07 through 2026-08-26.
Chronological split: discovery 1,000 / validation 334 / OOS 334.

Strict promotion rule:
- discovery >= 500 races
- validation >= 100
- OOS >= 100
- ROI > 100% in all three splits
- jackpot-removed ROI >= 90% in all three splits

Result: 0 promoted fixed-muscle strategies.

Rejected examples:
- 4-3-1: DISC 86.72%, VAL 139.19%, OOS 303.29%; unstable regime/jackpot-sensitive, reject.
- 4-3-*: DISC 95.03%, VAL 122.67%, OOS 100.46%; jackpot-removed VAL 82.51%, OOS 67.09%, reject.
- 3-2-5: DISC 133.87%, VAL 154.46%, OOS 111.14%; jackpot-removed DISC 71.31%, VAL 73.56%, OOS 65.00%, reject.

Conclusion: unconditional fixed combinations are not the product. Continue only with condition-dependent venue-specific edges.

## Next priority
1. Weather/water condition x bet type: exacta, quinella, trio, trifecta.
2. Wind direction/speed x wave height.
3. Tide-state x wind once tide history is joined.
4. Attack-role -> follower combinations under those conditions.
5. Racer Edogawa/rough-water skill and start-edge interactions.
