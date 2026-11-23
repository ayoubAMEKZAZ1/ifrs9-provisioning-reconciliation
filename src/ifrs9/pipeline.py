"""Builds the whole picture: portfolio -> risk parameters -> stages -> ECL and local provisions
at every reporting date, plus the reconciliation, movement, validation and sensitivity tables."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as K
from . import ecl as EC
from . import facilities as F
from . import local_rules as LR
from . import risk_params as RP
from . import staging as ST
from .portfolio import generate

ORDER = K.LOCAL_BUCKETS


def year_of(month):
    return int(str(month)[:4])


class Engine:
    def __init__(self, seed=42, n=3000):
        self.D = generate(n, seed)
        self.panel, self.truth = self.D["monthly_panel"], self.D["ground_truth"]
        self.idx = F.property_index()
        self.terms = F.facility_terms(self.D["counterparties"], self.panel, seed)
        self.counts = RP.migration_counts(self.panel, self.truth)
        self.M, self.pd12, self.logit = RP.migration_matrix(self.counts)
        self.cum = RP.cumulative_pd(self.M)
        self.hazard = RP.conditional_hazard(self.cum)
        self.trig = ST.triggers(self.panel, self.terms, self.pd12)
        self.stages = ST.assign_stages(self.trig)

    # ------------------------------------------------------------------ one reporting date
    def snapshot(self, month, stages=None, scenarios=None, scenario_override=None, lgd_shift=0.0,
                 collateral_mult=1.0, sensitive_regime=K.LOCAL_SENSITIVE_REGIME):
        stages = self.stages if stages is None else stages
        X = F.exposures(self.panel, self.terms, [month], self.idx).merge(
            stages[["counterparty_id", "month", "stage"]], on=["counterparty_id", "month"])
        X["collateral_value"] = X.collateral_value * collateral_mult
        scen = K.SCENARIOS[year_of(month)] if scenarios is None else scenarios
        R = EC.compute(X, X.stage.to_numpy(), self.hazard, scen, scenario_override=scenario_override,
                       lgd_shift=lgd_shift)
        L = LR.provisions(X, LR.classify(X, sensitive_regime))
        keep = X[["counterparty_id", "segment", "sector", "internal_rating", "days_past_due", "exposure_mad_m",
                  "on_balance", "collateral_value", "public_guarantee_cover", "months_in_default"]]
        return keep.merge(R, on="counterparty_id").merge(L.drop(columns=["month", "on_balance"]), on="counterparty_id")

    def all_dates(self):
        return pd.concat([self.snapshot(m) for m in K.REPORTING_DATES], ignore_index=True)


# ------------------------------------------------------------------ reconciliation
def stage_bucket(S: pd.DataFrame, value="ead") -> pd.DataFrame:
    t = S.pivot_table(index="local_bucket", columns="stage", values=value, aggfunc="sum", fill_value=0)
    t = t.reindex(index=ORDER, columns=[1, 2, 3], fill_value=0)
    t.columns = [f"Stage {c}" for c in t.columns]
    t["Total"] = t.sum(axis=1)
    t.loc["Total"] = t.sum()
    return t


def bridge(S: pd.DataFrame) -> pd.DataFrame:
    """Local provisions -> IFRS 9 ECL, one step per local bucket (difference = ECL - local provision)."""
    rows = [("Local provisions (individual accounts)", S.local_provision.sum(), "total")]
    for b in ORDER:
        s = S[S.local_bucket == b]
        if len(s):
            what = {"Healthy": "Healthy names: 12-month / lifetime ECL, no local provision",
                    "Sensitive": "Sensitive names: lifetime ECL vs 10% local",
                    "Pre-doubtful": "Pre-doubtful: LGD-based ECL vs 20% local",
                    "Doubtful": "Doubtful: LGD-based ECL vs 50% local",
                    "Compromised": "Compromised: LGD-based ECL vs 100% local"}[b]
            rows.append((what, s.ecl.sum() - s.local_provision.sum(), "step"))
    rows.append(("IFRS 9 ECL (consolidated accounts)", S.ecl.sum(), "total"))
    return pd.DataFrame(rows, columns=["item", "mad_m", "kind"])


def coverage_by_stage(A: pd.DataFrame) -> pd.DataFrame:
    g = A.groupby(["month", "stage"]).agg(ead=("ead", "sum"), ecl=("ecl", "sum"), names=("ead", "size")).reset_index()
    g["coverage_pct"] = 100 * g.ecl / g.ead
    g["ead_share_pct"] = 100 * g.ead / g.groupby("month").ead.transform("sum")
    return g


def movement(eng: Engine, open_m="2024-12", close_m="2025-12") -> pd.DataFrame:
    """IFRS 7.35H-style reconciliation of the loss allowance by stage between two reporting dates."""
    O = eng.snapshot(open_m)
    C = eng.snapshot(close_m)
    C_old = eng.snapshot(close_m, scenarios=K.SCENARIOS[year_of(open_m)])     # closing book, opening scenarios
    o = O.set_index("counterparty_id")
    c = C.set_index("counterparty_id")
    co = C_old.set_index("counterparty_id")
    both = o.index.intersection(c.index)
    new = c.index.difference(o.index)
    gone = o.index.difference(c.index)
    written_off = gone[o.loc[gone, "stage"].eq(3).to_numpy()]
    repaid = gone.difference(written_off)
    cols = [1, 2, 3]
    T = pd.DataFrame(0.0, index=["Opening allowance", "Transfer to Stage 1", "Transfer to Stage 2", "Transfer to Stage 3",
                                 "Remeasurement after stage transfer", "Change in exposure",
                                 "Change in risk parameters and time in default", "New exposures", "Repaid or left the bank", "Write-offs",
                                 "Change in forward-looking scenarios", "Closing allowance"], columns=cols)
    T.loc["Opening allowance"] = o.groupby("stage").ecl.sum().reindex(cols, fill_value=0)
    s0, s1 = o.loc[both, "stage"], c.loc[both, "stage"]
    moved = both[(s0 != s1).to_numpy()]
    for cp in moved:   # move the opening allowance to the destination stage
        a, b, e = o.at[cp, "stage"], c.at[cp, "stage"], o.at[cp, "ecl"]
        T.loc[f"Transfer to Stage {b}", a] -= e
        T.loc[f"Transfer to Stage {b}", b] += e
    stay = both.difference(moved)
    d_tr = (co.loc[moved, "ecl"] - o.loc[moved, "ecl"]).groupby(c.loc[moved, "stage"]).sum()
    T.loc["Remeasurement after stage transfer"] = d_tr.reindex(cols, fill_value=0)
    cov0 = o.loc[stay, "ecl"] / o.loc[stay, "ead"].clip(lower=1e-9)
    d_ead = cov0 * (co.loc[stay, "ead"] - o.loc[stay, "ead"])          # opening coverage x change in EAD
    d_risk = co.loc[stay, "ecl"] - o.loc[stay, "ecl"] - d_ead
    T.loc["Change in exposure"] = d_ead.groupby(o.loc[stay, "stage"]).sum().reindex(cols, fill_value=0)
    T.loc["Change in risk parameters and time in default"] = d_risk.groupby(o.loc[stay, "stage"]).sum().reindex(cols, fill_value=0)
    T.loc["New exposures"] = c.loc[new].groupby("stage").ecl.sum().reindex(cols, fill_value=0)
    T.loc["Repaid or left the bank"] = -o.loc[repaid].groupby("stage").ecl.sum().reindex(cols, fill_value=0)
    T.loc["Write-offs"] = -o.loc[written_off].groupby("stage").ecl.sum().reindex(cols, fill_value=0)
    macro = (c.loc[both, "ecl"] - co.loc[both, "ecl"]).groupby(s1).sum()
    T.loc["Change in forward-looking scenarios"] = macro.reindex(cols, fill_value=0)
    T.loc["Closing allowance"] = c.groupby("stage").ecl.sum().reindex(cols, fill_value=0)
    T.columns = [f"Stage {x}" for x in cols]
    T["Total"] = T.sum(axis=1)
    check = T.iloc[:-1].sum() - T.loc["Closing allowance"]
    assert np.allclose(check, 0, atol=1e-6), check
    keep = (T.abs().sum(axis=1) > 1e-9) | T.index.isin(["Opening allowance", "Closing allowance"])
    return T[keep]       # rows with no movement (this synthetic book has no new or repaid names) are dropped


# ------------------------------------------------------------------ validation
def pd_backtest(eng: Engine, snap="2024-12") -> pd.DataFrame:
    """Predicted 12-month PD (PIT, scenario-weighted, and TTC) vs observed default rate in the next 12 months."""
    S = eng.snapshot(snap)
    S = S[S.stage < 3].copy()
    dm = eng.truth.set_index("counterparty_id").default_month
    start = pd.Period(snap, "M")
    d = pd.PeriodIndex(dm.reindex(S.counterparty_id).replace("", np.nan), freq="M")
    S["defaulted_12m"] = ((d > start) & (d <= start + 12)).astype(int)
    S["grade"] = pd.to_numeric(S.internal_rating).astype(int)
    S["pd_ttc"] = S.grade.map(eng.pd12)
    g = S.groupby("grade").agg(names=("grade", "size"), pd_pit=("pd_12m_pit", "mean"), pd_ttc=("pd_ttc", "mean"),
                               defaults=("defaulted_12m", "sum"))
    g["observed"] = g.defaults / g.names
    from scipy.stats import beta
    g["ci_low"] = beta.ppf(0.05, g.defaults + 0.5, g.names - g.defaults + 0.5)    # Jeffreys 90% interval
    g["ci_high"] = beta.ppf(0.95, g.defaults + 0.5, g.names - g.defaults + 0.5)
    by_stage = S.groupby("stage").agg(names=("stage", "size"), pd_pit=("pd_12m_pit", "mean"),
                                      observed=("defaulted_12m", "mean"))
    return g, by_stage


def implied_cycle(eng: Engine) -> pd.DataFrame:
    """Credit-cycle index implied by each calendar year's observed default rate (start-of-year cohort)."""
    rows = []
    dm = eng.truth.set_index("counterparty_id").default_month
    for y in range(2021, 2026):
        P = eng.panel[(eng.panel.month == f"{y}-01") & (eng.panel.status == "performing")]
        g = P.internal_rating.astype(int).map(eng.pd12).to_numpy()
        d = dm.reindex(P.counterparty_id).str[:4].eq(str(y)).mean()
        rows.append({"year": y, "observed_default_rate": d, "ttc_pd": g.mean(), "implied_Z": RP.implied_z(g, d)})
    return pd.DataFrame(rows)


def stage2_effectiveness(eng: Engine, year="2025", lags=range(1, 13)) -> pd.DataFrame:
    """Share of the year's defaults that were already in Stage 2, or classified Sensitive locally, k months before."""
    dm = eng.truth[eng.truth.default_month.str[:4] == year]
    P = eng.panel.merge(eng.stages[["counterparty_id", "month", "stage"]], on=["counterparty_id", "month"])
    P["local_bucket"] = LR.classify(P)
    key = P.set_index(["counterparty_id", "month"])
    rows = []
    for k in lags:
        months = (pd.PeriodIndex(dm.default_month, freq="M") - k).astype(str)
        sub = key.reindex(list(zip(dm.counterparty_id, months))).dropna(subset=["stage"])
        rows.append({"months_before_default": k, "defaults_observed": len(sub),
                     "in_stage_2_pct": 100 * (sub.stage == 2).mean(),
                     "local_sensitive_pct": 100 * (sub.local_bucket == "Sensitive").mean()})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ sensitivities
def sensitivities(eng: Engine, month="2025-12") -> pd.DataFrame:
    base = eng.snapshot(month).ecl.sum()
    y = year_of(month)
    rows = [("Reported (probability-weighted)", base)]
    for s in K.SCENARIOS[y]:
        rows.append((f"100% {s} scenario", eng.snapshot(month, scenario_override=s).ecl.sum()))
    rows.append(("Property values -15%", eng.snapshot(month, collateral_mult=0.85).ecl.sum()))
    rows.append(("LGD +10 points", eng.snapshot(month, lgd_shift=0.10).ecl.sum()))
    step = float(np.exp(eng.logit[1]))           # PD multiple of one rating notch
    for notches in (1, 3):
        ratio = step ** notches * 0.99
        st = ST.assign_stages(ST.triggers(eng.panel, eng.terms, eng.pd12, pd_ratio=ratio))
        rows.append((f"SICR at {notches} notch{'es' if notches > 1 else ''} (reported: 2)", eng.snapshot(month, stages=st).ecl.sum()))
    st = ST.assign_stages(ST.triggers(eng.panel, eng.terms, eng.pd12, absolute_grade=99))
    rows.append(("No absolute PD threshold", eng.snapshot(month, stages=st).ecl.sum()))
    st = ST.assign_stages(eng.trig, probation=0)
    rows.append(("No probation period", eng.snapshot(month, stages=st).ecl.sum()))
    S = pd.DataFrame(rows, columns=["scenario", "ecl_mad_m"])
    S["change_mad_m"] = S.ecl_mad_m - base
    S["change_pct"] = 100 * S.change_mad_m / base
    return S
