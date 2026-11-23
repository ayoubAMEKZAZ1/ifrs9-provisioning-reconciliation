"""Expected credit loss per counterparty at a reporting date.

    Stage 1 : 12-month ECL = sum over products of PD(year 1) x LGD x EAD x discount, capped at maturity
    Stage 2 : lifetime ECL = sum over years k of marginal PD(k) x LGD(k) x EAD(k) x discount(k)
    Stage 3 : LGD in default x EAD (drawn amounts only, limits frozen)

PDs are point in time under each scenario and the result is the probability-weighted average
(IFRS 9 5.5.17). Term loans amortise straight-line to maturity; overdrafts and signature lines run
for their behavioural life. Collateral values follow each scenario's property-price path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as K
from . import risk_params as RP


def _year_weights(life, horizon):
    """n x horizon share of each year that falls within the remaining life."""
    k = np.arange(horizon)[None, :]
    return np.clip(np.asarray(life, float)[:, None] - k, 0, 1)


def ead_profile(X: pd.DataFrame, horizon=RP.HORIZON):
    """EAD by year for each product (n x horizon) and the year weights that bound each product's life."""
    rem = X.term_remaining_years.to_numpy()
    k_mid = np.arange(horizon)[None, :] + 0.5
    term = X.term_balance.to_numpy()[:, None] * np.clip(1 - k_mid / rem[:, None], 0, 1)
    term = np.where(k_mid - 0.5 < rem[:, None], np.maximum(term, 0), 0)
    od = np.repeat(X.ead_overdraft.to_numpy()[:, None], horizon, 1)
    sig = np.repeat(X.ead_signature.to_numpy()[:, None], horizon, 1)
    w = {"term": _year_weights(rem, horizon),
         "overdraft": _year_weights(np.full(len(X), K.REVOLVING_LIFE_YEARS), horizon),
         "signature": _year_weights(np.full(len(X), K.SIGNATURE_LIFE_YEARS), horizon)}
    return {"term": term, "overdraft": od, "signature": sig}, w


def compute(X: pd.DataFrame, stage: np.ndarray, hazard, scenarios: dict, horizon=RP.HORIZON,
            scenario_override: str | None = None, lgd_shift=0.0) -> pd.DataFrame:
    """ECL for every counterparty in X (one reporting date). Returns 12m, lifetime and stage-based ECL."""
    n = len(X)
    grades = pd.to_numeric(X.internal_rating, errors="coerce").fillna(9).astype(int).clip(1, 9).to_numpy()
    eir = X.eir.to_numpy()
    disc = (1 + eir[:, None]) ** -(np.arange(horizon)[None, :] + 0.5)
    E, W = ead_profile(X, horizon)
    ead_total = sum(E[p] * (W[p] > 0) for p in E)
    coll = X.collateral_value.to_numpy()
    cover = X.public_guarantee_cover.to_numpy()

    scen = scenarios if scenario_override is None else {scenario_override: {**scenarios[scenario_override], "weight": 1.0}}
    ecl12 = np.zeros(n)
    ecl_life = np.zeros(n)
    pd1 = np.zeros(n)
    for s in scen.values():
        marg = RP.pit_marginal_pd(grades, hazard, s["Z"])         # years after the Z path revert to TTC
        prop = np.cumprod(1 + np.array(list(s["property"]) + [0.0] * (horizon - len(s["property"])))) - 1
        lg = np.stack([RP.lgd(np.maximum(ead_total[:, k], 1e-9), coll, cover, eir, prop[k]) for k in range(horizon)], 1)
        lg = np.clip(lg + lgd_shift, K.LGD_FLOOR, 1)
        loss = sum(marg * W[p] * lg * E[p] * disc for p in E)        # n x horizon
        ecl12 += s["weight"] * loss[:, 0]
        pd1 += s["weight"] * marg[:, 0]
        ecl_life += s["weight"] * loss.sum(axis=1)

    # Stage 3: drawn exposure x LGD in default (current collateral, longer in default = lower recovery)
    lgd_def = np.clip(RP.lgd(X.ead, coll, cover, eir, 0.0, X.months_in_default.to_numpy()) + lgd_shift,
                      K.LGD_FLOOR, 1)
    ecl3 = lgd_def * X.ead.to_numpy()
    ecl = np.select([stage == 1, stage == 2, stage == 3], [ecl12, ecl_life, ecl3])
    base_lgd = RP.lgd(np.maximum(X.ead, 1e-9), coll, cover, eir)
    return pd.DataFrame({"counterparty_id": X.counterparty_id.to_numpy(), "month": X.month.to_numpy(),
                         "stage": stage, "ead": X.ead.to_numpy(), "ecl_12m": ecl12, "ecl_lifetime": ecl_life,
                         "ecl_default": ecl3, "ecl": ecl, "lgd": np.where(stage == 3, lgd_def, base_lgd),
                         "pd_12m_pit": np.where(stage == 3, 1.0, pd1)})
