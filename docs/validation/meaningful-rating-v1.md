# Meaningful rating v1 — forward validation

Run: 33129846631  
Feature branch: `feature/meaningful-rating-validation-v1`

## Split

- Train: 2025-11-01 through 2026-07-28
- Test: 2026-07-29 through 2026-08-28
- Training races: 39,651
- Test races available: 4,768
- Complete races scored: 4,480
- Scored entries: 26,880
- Rated racers: 1,640

This is a forward holdout: ratings are built only from data before the test period.

## Results

| Metric | Official win rate at cutoff | Normalized base win rate | Normalized current win rate |
|---|---:|---:|---:|
| Centered MAE (lower is better) | **2.4808** | 2.5884 | 2.5598 |
| Spearman centered (higher is better) | **0.4284** | 0.4218 | 0.4166 |
| Pairwise accuracy | **66.12%** | 65.79% | 65.46% |
| Top-rated boat wins | 34.53% | **35.16%** | 34.60% |
| Top-rated boat finishes top 3 | 74.20% | **74.69%** | 74.64% |

## Decision

Do **not** label or display v1 normalized ratings as a superior or "true" win rate yet.

The model slightly improves the win/top-3 rate of the single highest-rated racer, but overall rank correlation, pairwise ordering, and centered MAE do not beat the official win-rate baseline in the 30-day forward holdout.

The next version should keep the official win rate as a strong anchor and add only corrections that prove useful or stable out of time. Candidate correction groups: opponent/event level, course/entry, motor/boat, venue, weather/water conditions, and current form. Small-sample or non-reproducible effects should receive zero correction.
