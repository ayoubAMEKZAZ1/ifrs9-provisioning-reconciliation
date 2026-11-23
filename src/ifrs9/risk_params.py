"""PD, lifetime PD and LGD.

PD   : one-year rating migration matrix estimated on the development window (2021-2023), with the
       default column smoothed by a logistic fit on the grade. Lifetime PDs come from matrix powers.
PIT  : forward-looking adjustment with the Vasicek one-factor formula. Each scenario gives a
       credit-cycle index Z for years 1-3; from year 4 the PD reverts to the through-the-cycle level.
LGD  : collateral-based. Recoveries = haircut collateral value, discounted over the recovery period,
       plus recoveries on the unsecured remainder, with an SME public guarantee where present.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import config as K

GRADES = np.arange(1, 10)
HORIZON = 8   # years of lifetime PD computed (longest remaining term is under 8 years)


# ------------------------------------------------------------------ migration matrix
def migration_counts(panel: pd.DataFrame, truth: pd.DataFrame, end=K.DEVELOPMENT_END) -> pd.DataFrame:
    """Counts of one-year transitions grade -> grade or D, over monthly cohorts that end by `end`."""
    P = panel[panel.status == "performing"][["counterparty_id", "month", "internal_rating"]].copy()
    P["grade"] = P.internal_rating.astype(int)
    P["t"] = pd.PeriodIndex(P.month, freq="M").astype("int64")
    end_t = pd.Period(end, "M").ordinal
    dm = truth.set_index("counterparty_id").default_month
    dmt = pd.PeriodIndex(dm.replace("", np.nan), freq="M").astype("int64")
    dmt = pd.Series(np.where(dm.eq(""), np.iinfo("int64").max, dmt), index=dm.index)
    start = P[P.t + 12 <= end_t]
    later = P.set_index(["counterparty_id", "t"]).grade
    key = list(zip(start.counterparty_id, start.t + 12))
    g12 = later.reindex(key).to_numpy()
    d_t = dmt.reindex(start.counterparty_id).to_numpy()
    defaulted = (d_t > start.t.to_numpy()) & (d_t <= start.t.to_numpy() + 12)
    to = np.where(defaulted, "D", pd.Series(g12).map(lambda x: "" if np.isnan(x) else str(int(x))))
    out = pd.DataFrame({"from": start.grade.to_numpy(), "to": to})
    out = out[out.to != ""]                                       # exits (repaid, left the bank) are dropped
    return out.groupby(["from", "to"]).size().unstack(fill_value=0).reindex(
        index=GRADES, columns=[str(g) for g in GRADES] + ["D"], fill_value=0)


def _logit_fit(x, k, n, iters=50):
    """Binomial logistic regression of k defaults out of n on grade x (IRLS)."""
    X = np.column_stack([np.ones_like(x, float), x])
    b = np.array([-7.0, 0.7])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        W = n * p * (1 - p)
        b = b + np.linalg.solve(X.T @ (X * W[:, None]) + 1e-9 * np.eye(2), X.T @ (k - n * p))
    return b


def migration_matrix(counts: pd.DataFrame):
    """Smoothed one-year matrix (10 x 10 with D absorbing), fitted 12-month TTC PD by grade, logit coefs."""
    n = counts.sum(axis=1).to_numpy(float)
    k = counts["D"].to_numpy(float)
    b = _logit_fit(GRADES.astype(float), k, n)
    pd12 = 1 / (1 + np.exp(-(b[0] + b[1] * GRADES)))
    nd = counts.drop(columns="D").to_numpy(float) + np.eye(9) * 0.5     # light prior on staying put
    nd = nd / nd.sum(1, keepdims=True) * (1 - pd12)[:, None]
    M = np.zeros((10, 10))
    M[:9, :9], M[:9, 9], M[9, 9] = nd, pd12, 1.0
    return M, pd.Series(pd12, index=GRADES, name="pd_12m_ttc"), b


def cumulative_pd(M, horizon=HORIZON) -> np.ndarray:
    """9 x horizon: cumulative default probability by grade after 1..horizon years."""
    out, Mk = np.zeros((9, horizon)), np.eye(10)
    for h in range(horizon):
        Mk = Mk @ M
        out[:, h] = Mk[:9, 9]
    return out


def conditional_hazard(cum) -> np.ndarray:
    """Probability of defaulting in year k given survival to the start of year k."""
    prev = np.concatenate([np.zeros((cum.shape[0], 1)), cum[:, :-1]], axis=1)
    return (cum - prev) / (1 - prev)


def vasicek(h, Z, rho=K.PD_ASSET_CORRELATION):
    """Point-in-time PD given credit-cycle index Z (Z > 0 good year, Z < 0 bad year)."""
    h = np.clip(h, 1e-6, 1 - 1e-6)
    return norm.cdf((norm.ppf(h) - np.sqrt(rho) * Z) / np.sqrt(1 - rho))


def pit_marginal_pd(grades, hazard, Z) -> np.ndarray:
    """n x horizon unconditional marginal PDs for each counterparty under one scenario's Z path."""
    h = hazard[np.asarray(grades) - 1].copy()
    for k, z in enumerate(Z):
        h[:, k] = vasicek(h[:, k], z)
    surv = np.cumprod(np.concatenate([np.ones((len(h), 1)), 1 - h[:, :-1]], axis=1), axis=1)
    return surv * h


def implied_z(pd_ttc, observed_rate, rho=K.PD_ASSET_CORRELATION):
    """Credit-cycle index that makes the average PIT PD of a cohort equal its observed default rate."""
    lo, hi = -4.0, 4.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if vasicek(pd_ttc, mid, rho).mean() > observed_rate:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ------------------------------------------------------------------ LGD
def lgd(ead, collateral, guarantee_cover, eir, property_change=0.0, months_in_default=0):
    """Loss given default, all vectors at counterparty level. property_change shifts collateral values."""
    ead = np.maximum(np.asarray(ead, float), 1e-9)
    coll = np.asarray(collateral, float) * (1 + property_change)
    secured = np.minimum(ead, coll * (1 - K.HAIRCUT_REAL_ESTATE))
    df = (1 + np.asarray(eir)) ** (-K.YEARS_TO_RECOVER_COLLATERAL)
    g = np.asarray(guarantee_cover, float)
    rest = ead - secured
    pv = secured * df + rest * ((1 - g) * (1 - K.LGD_UNSECURED) + g * (1 - K.LGD_GUARANTEED_PART))
    out = np.clip(1 - pv / ead, K.LGD_FLOOR, 1.0)
    years = np.asarray(months_in_default, float) / 12
    return np.minimum(out * (1 + K.LGD_TIME_IN_DEFAULT_UPLIFT * years), 1.0)
