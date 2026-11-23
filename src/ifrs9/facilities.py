"""Facility layer on top of the synthetic counterparty panel, plus the collateral price index.

Each counterparty gets three facilities: an amortising term loan, an overdraft line and signature
commitments (guarantees and bonds). Its monthly total limit is the panel's exposure; the overdraft is
drawn at the panel's utilisation. Collateral values move with the official Bank Al-Maghrib / ANCFCC
real estate price index (IPAI), the same public series used in morocco-real-estate-credit-signals.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config as K

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ property price index
def property_index(path=None) -> pd.DataFrame:
    """Quarterly price index (2020Q4 = 100) per collateral type, chained from official q-o-q changes."""
    d = pd.read_csv(path or ROOT / "data/external/ipai_official_rates_2020Q1_2026Q2.csv")
    d = d[(d.metric == "price") & (d.change == "qoq")].pivot(index="quarter", columns="category", values="value_pct")
    idx = (1 + d / 100).cumprod()
    idx = 100 * idx / idx.loc["2020Q4"]
    out = pd.DataFrame({"Commercial": idx["Commercial"],
                        "Land and residential": (idx["Land"] + idx["Residential"]) / 2})
    out.index.name = "quarter"
    return out


def index_at(idx: pd.DataFrame, months: pd.Series, kind: pd.Series) -> np.ndarray:
    """Index level for each (month, collateral type); months take their quarter's value."""
    q = pd.PeriodIndex(months, freq="M").asfreq("Q").astype(str)
    q = np.where(q < idx.index.min(), idx.index.min(), q)
    stacked = idx.stack()
    return stacked.reindex(list(zip(q, kind))).to_numpy()


# ------------------------------------------------------------------ static facility terms
def facility_terms(cp: pd.DataFrame, panel: pd.DataFrame, seed=42) -> pd.DataFrame:
    """One row per counterparty: product split, maturities, EIR, collateral and guarantee terms."""
    rng = np.random.default_rng(seed + 1000)
    n = len(cp)
    seg = cp.segment.to_numpy()
    mix = np.array([K.PRODUCT_MIX[s] for s in seg])
    mix = mix * rng.uniform(0.85, 1.15, (n, 3))
    mix = mix / mix.sum(1, keepdims=True)

    def maturity(s):
        lo, hi = K.TERM_MATURITY.get(s, K.TERM_MATURITY["default"])
        rng_m = pd.period_range(lo, hi, freq="M")
        return str(rng_m[rng.integers(len(rng_m))])

    first = panel.groupby("counterparty_id", sort=False).agg(origination_month=("month", "first"),
                                                             origination_rating=("internal_rating", "first"),
                                                             origination_limit=("exposure_mad_m", "first"))
    T = cp[["counterparty_id", "segment", "sector"]].merge(first, on="counterparty_id", how="left")
    T["share_term"], T["share_overdraft"], T["share_signature"] = mix.T
    T["term_maturity"] = [maturity(s) for s in seg]
    T["eir"] = [K.EIR[s] for s in seg] + rng.normal(0, 0.004, n).round(4)
    has_mortgage = rng.random(n) < np.array([K.MORTGAGE_SHARE[s] for s in seg])
    ltv = rng.uniform(*K.LTV_AT_ORIGINATION, n)
    T["collateral_type"] = np.where(has_mortgage, [K.PROPERTY_TYPE.get(s, K.PROPERTY_TYPE["default"]) for s in seg],
                                    "None")
    # value at origination, set on the secured term loan (developers) or on the total limit (others)
    base = np.where(seg == "Property developer", T.share_term * T.origination_limit, T.origination_limit * 0.6)
    T["collateral_value_at_origination"] = np.where(has_mortgage, base / ltv, 0.0).round(3)
    share, cover = K.PUBLIC_GUARANTEE.get("SME", (0, 0))
    T["public_guarantee_cover"] = np.where((seg == "SME") & (rng.random(n) < share), cover, 0.0)
    return T


# ------------------------------------------------------------------ monthly exposures at reporting dates
def exposures(panel: pd.DataFrame, terms: pd.DataFrame, months, idx: pd.DataFrame | None = None) -> pd.DataFrame:
    """Counterparty-level drawn amount, undrawn, EAD by product and collateral value at each month."""
    idx = property_index() if idx is None else idx
    P = panel[panel.month.isin(months)].merge(terms, on="counterparty_id", how="left")
    limit = P.exposure_mad_m
    term = P.share_term * limit
    od_limit = P.share_overdraft * limit
    od_drawn = np.minimum(P.overdraft_utilisation, 1.15) * od_limit
    sig = P.share_signature * limit
    P["term_balance"] = term
    P["overdraft_limit"] = od_limit
    P["overdraft_drawn"] = od_drawn
    P["overdraft_undrawn"] = np.maximum(od_limit - od_drawn, 0)
    P["signature"] = sig
    P["on_balance"] = term + od_drawn
    defaulted = P.status.eq("default")
    # in default the limits are frozen: only what is drawn is at risk
    P["ead_overdraft"] = np.where(defaulted, od_drawn, od_drawn + K.CCF["overdraft"] * P.overdraft_undrawn)
    P["ead_signature"] = np.where(defaulted, 0.0, K.CCF["signature"] * sig)
    P["ead"] = term + P.ead_overdraft + P.ead_signature
    kind = P.collateral_type.where(P.collateral_type != "None", "Commercial")
    level_now = index_at(idx, P.month, kind)
    level_orig = index_at(idx, P.origination_month, kind)
    P["collateral_value"] = (P.collateral_value_at_origination * level_now / level_orig).round(3)
    P["months_in_default"] = np.where(defaulted, (P.days_past_due - 90) // 30, 0)
    t_now = pd.PeriodIndex(P.month, freq="M")
    t_mat = pd.PeriodIndex(P.term_maturity, freq="M")
    months_left = (t_mat.year - t_now.year) * 12 + (t_mat.month - t_now.month)
    P["term_remaining_years"] = np.maximum(np.asarray(months_left) / 12, 1 / 12)
    return P
