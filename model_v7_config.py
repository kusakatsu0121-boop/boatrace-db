"""Frozen V7 structural probability baseline.

Architecture was selected without using August payout/ROI:
- feature-family screen: May-June
- 120-path calibration: May-June
- candidate selection / market blend weight: July NLL
- August: retrospective OOS audit only

Do not silently add WEATHER_VENUE or F_STAGE back into V7.  Test new families as V8 experiments.
"""

MODEL_NAME = "V7_NO_WEATHER_NO_F"

SELECTED_FAMILIES = [
    "PUBLISHED_ABILITY",
    "VENUE",
    "ST",
    "MOTOR_BOAT",
    "EXHIBITION",
    "ATTACK_ESCAPE",
]

EXCLUDED_FAMILIES = [
    "WEATHER_VENUE",
    "F_STAGE",
]

# May-June path calibration winner for the selected architecture.
PATH_GAMMA = 1.0
PATH_TEMPERATURE = 1.2

# July log-loss selected blend.  model_prob receives this weight;
# normalized market implied probability receives (1 - MODEL_BLEND_WEIGHT).
MODEL_BLEND_WEIGHT = 0.20
MARKET_BLEND_WEIGHT = 0.80

# User rule for final ticket construction.
MAX_TRIFECTA_TICKETS_PER_RACE = 4

# Reference diagnostics from the architecture-selection run.
REFERENCE = {
    "may_june_path_nll": 3.994584726856186,
    "july_blend_nll": 3.8089760058762763,
    "august_standalone_nll": 4.045180461243992,
    "august_blend_nll": 3.8010739056604463,
    "august_market_nll": 3.810465708355836,
    "august_exact_top_rate": 0.10025888444339845,
    "august_market_exact_top_rate": 0.09978818545540127,
}
