"""Every assumption of the engine in one place. Change a number here and rerun scripts/run_all.py.

The values are illustrative choices for a synthetic Moroccan corporate book, not any bank's model.
docs/METHODOLOGY.md explains each one; docs/LOCAL_RULES.md gives the public sources for the local rules.
"""
from __future__ import annotations

# ------------------------------------------------------------------ timeline
DEVELOPMENT_END = "2023-12"            # PD / migration model estimated on 2021-01 .. 2023-12 only
REPORTING_DATES = ["2024-03", "2024-06", "2024-09", "2024-12", "2025-03", "2025-06", "2025-09", "2025-12"]

# ------------------------------------------------------------------ products (share of the counterparty's total limit)
PRODUCT_MIX = {          # term loan, overdraft / revolving line, signature (guarantees, bonds)
    "SME": (0.45, 0.45, 0.10),
    "Mid-corporate": (0.50, 0.30, 0.20),
    "Large corporate": (0.45, 0.25, 0.30),
    "Property developer": (0.85, 0.10, 0.05),
}
CCF = {"overdraft": 0.60, "signature": 0.50}       # credit conversion factors on undrawn / off-balance amounts
REVOLVING_LIFE_YEARS = 3.0                          # behavioural life for lifetime ECL of overdrafts (IFRS 9 B5.5.40)
SIGNATURE_LIFE_YEARS = 1.5
TERM_MATURITY = {"default": ("2026-06", "2031-12"), "Property developer": ("2026-03", "2028-12")}
EIR = {"SME": 0.065, "Mid-corporate": 0.055, "Large corporate": 0.048, "Property developer": 0.068}

# ------------------------------------------------------------------ collateral and guarantees
MORTGAGE_SHARE = {"SME": 0.45, "Mid-corporate": 0.30, "Large corporate": 0.10, "Property developer": 1.0}
LTV_AT_ORIGINATION = (0.55, 0.90)                  # uniform range, loan / collateral value
PROPERTY_TYPE = {"Property developer": "Land and residential", "default": "Commercial"}
PUBLIC_GUARANTEE = {"SME": (0.30, 0.60)}           # share of SMEs covered, cover ratio of the residual loss
HAIRCUT_REAL_ESTATE = 0.35                         # forced-sale discount and costs
YEARS_TO_RECOVER_COLLATERAL = 3.5                  # judicial recovery is slow in Morocco
LGD_UNSECURED = 0.65
LGD_GUARANTEED_PART = 0.05
LGD_FLOOR = 0.05
LGD_TIME_IN_DEFAULT_UPLIFT = 0.20                  # per year in default, recoveries get less likely
PD_ASSET_CORRELATION = 0.12                        # Vasicek rho for the forward-looking adjustment

# ------------------------------------------------------------------ forward-looking scenarios
# Z = credit-cycle index (0 = average year, negative = worse). Property = annual change in collateral values.
# Each reporting year has its own scenario set, as a bank would update them.
SCENARIOS = {
    2024: {"Base":     {"weight": 0.50, "Z": [-0.30, 0.00, 0.00], "property": [0.00, 0.01, 0.02]},
           "Upside":   {"weight": 0.20, "Z": [0.50, 0.30, 0.00], "property": [0.03, 0.03, 0.02]},
           "Downside": {"weight": 0.30, "Z": [-1.40, -0.80, -0.30], "property": [-0.10, -0.03, 0.00]}},
    2025: {"Base":     {"weight": 0.50, "Z": [-0.20, 0.00, 0.00], "property": [-0.01, 0.01, 0.02]},
           "Upside":   {"weight": 0.15, "Z": [0.60, 0.30, 0.00], "property": [0.03, 0.03, 0.02]},
           "Downside": {"weight": 0.35, "Z": [-1.60, -0.90, -0.30], "property": [-0.12, -0.04, 0.00]}},
}

# ------------------------------------------------------------------ staging (significant increase in credit risk)
SICR_PD_RATIO = 3.0              # 12-month PD now / at origination
LOW_CREDIT_RISK_GRADES = 3       # grades 1-3 stay in Stage 1 on the PD test (IFRS 9 5.5.10)
SICR_ABSOLUTE_GRADE = 7         # grade 7 or worse (12-month PD about 12%) = Stage 2 whatever the origination grade
SICR_DPD_BACKSTOP = 30           # more than 30 days past due (IFRS 9 5.5.11)
WATCH_LIST_GRADE = 8             # grades 8-9 = watch list, a qualitative SICR trigger
PROBATION_MONTHS = 3             # months without any trigger before a return to Stage 1

# ------------------------------------------------------------------ local (Bank Al-Maghrib) classification
LOCAL_BUCKETS = ["Healthy", "Sensitive", "Pre-doubtful", "Doubtful", "Compromised"]
LOCAL_DPD = {"Pre-doubtful": 90, "Doubtful": 180, "Compromised": 360}
LOCAL_RATES = {"Healthy": 0.00, "Sensitive": 0.10, "Pre-doubtful": 0.20, "Doubtful": 0.50, "Compromised": 1.00}
LOCAL_SENSITIVE_REGIME = True           # True = revised circular (sensitive class, from 2027); False = legacy rules
LOCAL_SENSITIVE_LARGE_EXPOSURE = 20.0   # MAD million; names this large with grade 7 are reviewed as sensitive
LOCAL_COLLATERAL_ELIGIBLE = 0.50        # share of the current collateral value deducted from the provision base
