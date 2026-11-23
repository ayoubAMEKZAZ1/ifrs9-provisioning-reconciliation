"""Local prudential classification and provisioning (statutory individual accounts).

Moroccan banks report IFRS 9 in their consolidated accounts and follow Bank Al-Maghrib's
classification rules (circular 19/G, revised) in their individual accounts. This module is a
simplified, configurable reading of the public descriptions of those rules (docs/LOCAL_RULES.md):

  Compromised  : 360+ days past due            -> at least 100% of the provision base
  Doubtful     : 180-359 days past due         -> at least 50%
  Pre-doubtful : 90-179 days past due          -> at least 20%
  Sensitive    : performing but on watch (grade 8-9, 30+ days past due, or a large exposure at
                 grade 7)                       -> at least 10% (revised circular, from 2027)
  Healthy      : everything else               -> no specific provision

Classification is by counterparty (contagion), and the provision base is the on-balance outstanding
net of eligible guarantees. Off-balance commitments and reserved interest are left out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as K


def classify(X: pd.DataFrame, sensitive_regime=K.LOCAL_SENSITIVE_REGIME) -> np.ndarray:
    dpd = X.days_past_due.to_numpy()
    default = X.status.eq("default").to_numpy()
    g = pd.to_numeric(X.internal_rating, errors="coerce").to_numpy()
    sensitive = (~default) & ((g >= 8) | (dpd >= 30) |
                              ((X.exposure_mad_m.to_numpy() >= K.LOCAL_SENSITIVE_LARGE_EXPOSURE) & (g >= 7)))
    if not sensitive_regime:
        sensitive = np.zeros(len(X), bool)
    return np.select([default & (dpd >= K.LOCAL_DPD["Compromised"]), default & (dpd >= K.LOCAL_DPD["Doubtful"]),
                      default, sensitive], ["Compromised", "Doubtful", "Pre-doubtful", "Sensitive"], "Healthy")


def provisions(X: pd.DataFrame, buckets: np.ndarray, rates=None,
               collateral_eligible=K.LOCAL_COLLATERAL_ELIGIBLE) -> pd.DataFrame:
    rates = K.LOCAL_RATES if rates is None else rates
    on_bal = X.on_balance.to_numpy()
    net = np.maximum(on_bal - collateral_eligible * X.collateral_value.to_numpy(), 0)
    base = net * (1 - X.public_guarantee_cover.to_numpy())
    rate = pd.Series(buckets).map(rates).to_numpy()
    return pd.DataFrame({"counterparty_id": X.counterparty_id.to_numpy(), "month": X.month.to_numpy(),
                         "local_bucket": buckets, "on_balance": on_bal, "provision_base": base,
                         "local_rate": rate, "local_provision": rate * base})
