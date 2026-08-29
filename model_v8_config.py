"""Frozen interpretable V8 structural model configuration.

Selected using pre-May training and May-Jun calibration only.
Structural probabilities do NOT use odds.  Market/EV is a separate downstream layer.

Core = opponent-adjusted racer strength + racer x course p1/p2/p3/top2/top3 + actual exhibition course.
Addons are deliberately constrained and explainable.
"""

MODEL_NAME = "V8_INTERPRETABLE_CORE_FIRST"

# Explicit structural shares. These sum to 100%.
STRUCTURAL_SHARES_PCT = {
    "CORE_ABILITY_COURSE": 80.000000,
    "PUBLISHED_ABILITY": 10.430567,
    "ST": 5.960423,
    "EXHIBITION": 2.743186,
    "ATTACK_ESCAPE": 0.590670,
    "MOTOR_BOAT": 0.275154,
    "VENUE": 0.000000,
    "WEATHER_VENUE": 0.000000,
    "F_STAGE": 0.000000,
}

# Addon safety: no combined addon set may move an entry's p1/p2/p3
# more than five absolute percentage points away from CORE.
MAX_ENTRY_SHIFT_PT = 5.0

# May-Jun-selected 120-path conversion settings.
CONDITIONAL_COURSE_SHARE_PCT = 20.0
PATH_TEMPERATURE = 1.2

# Sanity diagnostics from the freeze run.
REFERENCE = {
    "mean_abs_entry_shift_pt": 0.324924,
    "p95_abs_entry_shift_pt": 1.030795,
    "max_abs_entry_shift_pt": 4.711140,
    "may_jun_core_path_nll": 4.223129,
    "may_jun_v8_path_nll": 4.160022,
    "july_core_path_nll": 4.257754,
    "july_v8_path_nll": 4.191185,
    "august_core_path_nll": 4.279341,
    "august_v8_path_nll": 4.205796,
    "may_jun_core_top_rate": 0.067540,
    "may_jun_v8_top_rate": 0.073053,
    "july_core_top_rate": 0.067843,
    "july_v8_top_rate": 0.065742,
    "august_core_top_rate": 0.056719,
    "august_v8_top_rate": 0.064015,
}

ODDS_USED_IN_STRUCTURAL_PREDICTION = False
