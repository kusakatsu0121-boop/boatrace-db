# Optimal Race Engine v1

## Purpose

Use the findings already validated in this project to read one race in the order the race actually unfolds. Do not mix every factor into one global weighted score.

The engine is **condition-first and hierarchical**:

1. Estimate actual entry / front-push risk.
2. Judge whether boat 1 can hold the race.
3. If boat 1 is vulnerable, identify the most plausible attacker and attack method.
4. Conditional on the winner, rank 2nd-place paths.
5. Conditional on 1st+2nd, rank 3rd-place paths.
6. Apply venue/current-meet/exhibition/weather as late modifiers only where supported.
7. Keep market odds out of the race-reading logic. Use odds only in the final value/bet layer.
8. Never promote a rule to a betting rule unless it survives out-of-sample validation.

---

## Layer 0 — Base race view

Use a compact baseline only to establish ordinary strength/order. The baseline may be:

- Boat Advisor default forecast, when available; or
- public/base predictor + national/local/course/ST/motor/current-meet inputs.

The baseline is a reference point, not the final decision.

Do **not** force a fixed 70/30/global blend. Previous tests showed that such a blend can improve ordering but is not a good absolute probability model.

---

## Layer 1 — Entry / front-push risk

### Racer front-push profile

For each racer, calculate from races where drawn in boats 3–6:

- opportunities
- front-push count
- front-push rate
- average places moved inward
- maximum places moved inward
- destination-course distribution

Initial high-risk label used in the validated test:

- opportunities >= 15
- front-push rate >= 30%

### Current validated effect

Training: through 2026-06-30.
Evaluation: 2026-07-01 through 2026-08-31, 9,497 races.

When a historically high-front-push racer actually moved inward:

- 379 races: boat-1 win rate 35.09%
- matched expectation about 54.57%
- boat-1 win-rate reduction about 17.66 points

Even when boat 1 retained course 1:

- n=344
- boat-1 win 36.92%
- matched expectation 54.57%
- reduction about 17.66 points
- escape 35.76% vs matched expectation 52.10%
- escape reduction about 16.35 points

When the high-front-push racer reached course 2 and boat 1 retained course 1:

- n=231
- boat-1 win 33.77%
- matched expectation 54.17%
- reduction about 20.41 points
- escape 32.90% vs matched 51.54%
- reduction about 18.64 points

Important: these are effects **conditional on actual movement**, not a pre-race adjustment to subtract blindly.

### Pre-race use

Estimate:

`front_push_risk = P(racer moves inward today)`

Then use front-push as a scenario branch, not a flat deduction:

- normal-entry scenario
- front-push scenario

The final race view should weight these scenarios by estimated front-push probability.

---

## Layer 2 — Boat 1 stability

Evaluate boat 1 using only factors that directly affect whether the inside survives.

### Core boat-1 inputs

- racer/course-1 first-place rate
- racer/course-1 escape rate
- average ST / ST variation
- beaten-by-sashi rate
- beaten-by-makuri rate
- beaten-by-makuri-sashi rate
- venue/course baseline
- front-push scenario from Layer 1

### Validated attack interactions

#### Boat 2 sashi pressure

Condition:

- boat 1 beaten-by-sashi profile high
- boat 2 course-2 sashi-win profile high

Top-20% × top-20% historical interaction:

- July: 30/119 = 25.21% boat-2 wins
- August: 34/117 = 29.06%
- combined: 64/236 = 27.12%

This is a strong/stable boat-2 attack condition.

#### Boat 3 makuri pressure

Condition:

- boat 1 beaten-by-makuri profile high
- boat 3 course-3 makuri-win profile high

Top-20% × top-20% interaction:

- July: 33/114 = 28.95% boat-3 wins
- August: 31/95 = 32.63%
- combined: 64/209 = 30.62%

This is currently the strongest validated attack add-on.

#### Boat 3 makuri-sashi pressure

Condition:

- boat 1 beaten-by-makuri-sashi high
- boat 3 course-3 makuri-sashi high

Combined holdout:

- 52/270 = 19.26%

Useful, but weaker than direct makuri/sashi interactions.

### Rule

Boat-1 stability is not a single weighted score. It is a scenario classification:

- **INSIDE_STRONG**: no major attack/front-push condition
- **INSIDE_PRESSURED_2**: strong course-2 sashi interaction
- **INSIDE_PRESSURED_3_MAKURI**: strong course-3 makuri interaction
- **INSIDE_PRESSURED_3_MS**: strong course-3 makuri-sashi interaction
- **INSIDE_FRONT_PUSH_RISK**: meaningful front-push scenario
- multiple flags may coexist

---

## Layer 3 — First-place scenarios

Generate a small set of plausible winner branches instead of ranking all six with one score.

Priority branches:

1. boat 1 escape
2. boat 2 sashi when Layer-2 sashi condition is active
3. boat 3 makuri when Layer-2 makuri condition is active
4. boat 3 makuri-sashi when the corresponding condition is active
5. other course/venue-specific attack branches only after they are validated

The engine should explain why a branch exists.

Example:

- `1-HEAD`: ordinary inside strength
- `2-HEAD`: boat1 beaten-sashi high × boat2 sashi high
- `3-HEAD`: boat1 beaten-makuri high × boat3 makuri high
- `FRONTPUSH`: expected entry disturbance weakens the inside

---

## Layer 4 — Second-place path conditional on winner

Do not use generic second-place strength alone.

### Structural baseline when boat 1 wins

Historical course-2 and course-3 follow rates after a boat-1 win:

- course 2 second: 34.59%
- course 3 second: 28.86%

Both are substantially above their unconditional second-place baselines.

### Racer-specific winner-follow tendency

Use a racer's past winner → follower tendency.

Validated examples:

#### course-1 winner → course-2 second

Top 5% racer profiles by training lift:

- July 39.02%
- August 40.68%
- combined 39.83%

#### course-1 winner → course-3 second

Top 10% racer profiles:

- July 32.42%
- August 34.13%
- combined 33.26%

### Course-3 allow-escape interaction

Among boat-1 wins:

- high course-3 allow-escape profile → course-3 second 32.35%
- all → 29.24%

Combined with a course-1 winner who historically brings course 3 to second:

- 28/72 = 38.89%
- July 35.90%
- August 42.42%

Use this as a conditional `1-3` boost, with sample-size caution.

### Important negative finding

High course-2 allow-escape did **not** improve `1-2` generally. Do not promote it as a generic rule.

---

## Layer 5 — Third-place path conditional on first + second

This is where course-chain structure belongs.

Key validated structural chains after boat 1 wins:

- `1-2 -> 3`: 39.02% vs baseline 23.96%, +15.06 points
- `1-3 -> 2`: 35.47% vs baseline 22.49%, +12.98 points
- `1-4 -> 2`: 33.95%, +11.46 points
- `1-5 -> 2`: 33.25%, +10.76 points
- `1-6 -> 2`: 32.70%, +10.21 points
- `1-3 -> 4`: 29.50%, +7.18 points
- `1-2 -> 4`: 28.26%, +5.94 points

Do not mix this chain as a global feature across all 120 trifectas. Apply it **only after first and second are selected**.

### Racer-specific third follower

A course-1 winner → course-4 third top-10% profile showed:

- July 27.59%
- August 27.84%
- combined 27.70%

Useful as an additive conditional path feature.

---

## Layer 6 — Attack aftermath / outside supply

Treat as exploratory until stronger OOS support exists.

Observed tendencies:

### Boat 2 sashi-win condition

When boat-1 beaten-sashi high × boat-2 sashi high and boat 2 wins:

- course 4 second/third and outer courses showed some uplift
- course 3 third was lower than baseline

### Boat 3 makuri-win condition

When boat-1 beaten-makuri high × boat-3 makuri high and boat 3 wins:

- course 4 second showed a large exploratory uplift
- course 1 second was lower
- course 6 showed some uplift

These are development-supply hypotheses, not core rules yet.

---

## Layer 7 — Venue / environment / current meet

These are modifiers, not universal weights.

Available pre-race/realtime inputs include:

- venue
- local performance
- motor 2-rate / 3-rate
- boat 2-rate / 3-rate
- current-meet race/course/ST/finish history
- F/L and accident-related indicators
- weight / adjustment
- exhibition time
- exhibition entry/ST
- wind speed/direction
- wave height
- air/water temperature
- original exhibition metrics where available
- scoring-rate / semifinal-bubble state

Use venue-specific versions where enough sample exists, especially Edogawa.

Do not treat psychology as a free-form label. Use observable proxies such as scoring/bubble position, recent accident/F status, and assignment/context.

---

## Layer 8 — External forecasts

External forecasts are optional evidence, never a fixed untested percentage.

Possible inputs:

- Boat Advisor default prediction
- BOAT RACE official computer prediction
- BOATBoy marks/new-concept data

Use them as:

- agreement signal
- disagreement signal
- filter for candidate races

Do not invent a 10%/20% blend without empirical validation.

---

## Layer 9 — Market / betting layer

The market is not part of the race-reading model.

Use odds only after the race scenarios are produced.

Important finding from quick tests:

- own scenario model improved ordering in some tests
- raw own probabilities were badly calibrated for direct EV betting
- market implied probabilities had much better log-loss than the raw self model

Therefore v1 must **not** say "model probability × odds = EV" unless the scenario probability has been separately calibrated.

### Betting-rule promotion gate

A condition may be shown in the database before it becomes a bet.

To become a betting rule, require:

- pre-race observable condition
- discovery period separate from validation
- untouched OOS confirmation
- adequate n
- monthly stability
- fixed ticket construction
- ROI/return not driven by one payout
- preferably bootstrap CI and drawdown checks

If not passed: display as `DATA ONLY`, not `BET`.

---

## Final race output

Each race should output the following, in this order.

### 1. Entry risk

- expected standard entry
- front-push candidates
- each candidate's historical front-push rate
- expected destination course
- front-push scenario flag

### 2. Boat-1 status

- inside strength
- escape profile
- beaten-sashi/makuri/makuri-sashi profile
- front-push pressure
- final status flag(s)

### 3. Main winner scenarios

For each branch:

- winner/course
- expected method
- evidence/rule that activated it
- sample size and historical rate where available

### 4. Second-place candidates per winner

Use:

- structural course follow
- racer-specific winner-follow
- allow-escape interaction where validated

### 5. Third-place candidates per first+second

Use:

- first+second → third course chain
- racer-specific third follower

### 6. Context modifiers

- venue
- motor/current meet
- exhibition/weather
- observable motivation/bubble proxies

### 7. Market comparison

- market popularity/odds
- whether the market appears inconsistent with the activated condition
- no raw EV claim unless calibrated

### 8. Status

One of:

- `DATA_ONLY`
- `WATCH`
- `VALIDATED_SIGNAL`
- `BET_CANDIDATE` only after betting-rule gate

---

## What is deliberately excluded from v1 core

- human-to-human racer identity pairings
- exact racer pair/triple effects with weak OOS support
- generic course-2 allow-escape boost
- all-factor fixed global weights
- raw own probabilities used directly as betting EV
- unmeasured psychology labels

---

## Core database tables needed

1. `racer_course_metrics`
   - p1/p2/p3
   - avg ST / ST SD
   - escape/sashi/makuri/makuri-sashi
   - beaten-sashi/makuri/makuri-sashi
   - allow-escape

2. `racer_front_push`
   - opportunities
   - front-push rate
   - avg/max move
   - destination-course distribution

3. `winner_follow_courses`
   - winner racer/course -> target second course
   - winner racer/course -> target third course
   - baseline and lift

4. `course_chain`
   - first course + second course -> third-course distribution

5. `venue_course_metrics`

6. `current_meet_context`

7. `validated_interactions`
   - boat1 beaten-sashi × boat2 sashi
   - boat1 beaten-makuri × boat3 makuri
   - boat1 beaten-makuri-sashi × boat3 makuri-sashi
   - front-push impact
   - other rules only after OOS validation

8. `signal_registry`
   - condition definition
   - discovery n/rate
   - OOS n/rate
   - ROI if tested
   - confidence/status

---

## Decision principle

The engine asks four questions only:

1. **Will the entry/inside hold?**
2. **If not, who can break it and how?**
3. **Given the winner, who is naturally carried into second?**
4. **Given first+second, which course is structurally most likely third?**

Everything collected in this project must attach to one of those questions or stay out of the core model.
