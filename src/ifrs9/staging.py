"""IFRS 9 staging at counterparty level (all facilities of a name share its stage).

Stage 3 : in default (90+ days past due, the definition used by the portfolio).
Stage 2 : a significant increase in credit risk since origination, by any of
          - the 12-month TTC PD of the current grade is at least SICR_PD_RATIO times the origination PD,
            unless the name is still in the low-credit-risk grades 1-3;
          - grade 7 or worse (absolute PD threshold, a practical backstop many banks use);
          - more than 30 days past due (backstop);
          - grade 8-9 (watch list, qualitative trigger);
          and it stays in Stage 2 until PROBATION_MONTHS pass with no trigger.
Stage 1 : everything else.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as K


def triggers(panel: pd.DataFrame, terms: pd.DataFrame, pd12: pd.Series, pd_ratio=K.SICR_PD_RATIO,
             absolute_grade=K.SICR_ABSOLUTE_GRADE) -> pd.DataFrame:
    """Monthly SICR triggers for every performing counterparty-month."""
    P = panel[["counterparty_id", "month", "status", "internal_rating", "days_past_due"]].merge(
        terms[["counterparty_id", "origination_rating"]], on="counterparty_id", how="left")
    perf = P.status.eq("performing")
    g = pd.to_numeric(P.internal_rating, errors="coerce")
    g0 = pd.to_numeric(P.origination_rating, errors="coerce").fillna(g)
    pd_now, pd_orig = g.map(pd12), g0.map(pd12)
    P["trigger_pd"] = perf & (pd_now >= pd_ratio * pd_orig) & (g > K.LOW_CREDIT_RISK_GRADES)
    P["trigger_absolute"] = perf & (g >= absolute_grade)
    P["trigger_dpd"] = perf & (P.days_past_due > K.SICR_DPD_BACKSTOP)
    P["trigger_watch"] = perf & (g >= K.WATCH_LIST_GRADE)
    P["any_trigger"] = P.trigger_pd | P.trigger_absolute | P.trigger_dpd | P.trigger_watch
    return P


def assign_stages(trig: pd.DataFrame, probation=K.PROBATION_MONTHS) -> pd.DataFrame:
    """Monthly stage per counterparty, with a probation period before returning to Stage 1."""
    T = trig.sort_values(["counterparty_id", "month"]).copy()
    if probation > 0:
        recent = (T.groupby("counterparty_id").any_trigger
                  .transform(lambda s: s.astype(int).rolling(probation + 1, min_periods=1).max()).astype(bool))
    else:
        recent = T.any_trigger
    T["stage"] = np.where(T.status.eq("default"), 3, np.where(recent, 2, 1))
    return T[["counterparty_id", "month", "stage", "trigger_pd", "trigger_absolute", "trigger_dpd", "trigger_watch"]]
