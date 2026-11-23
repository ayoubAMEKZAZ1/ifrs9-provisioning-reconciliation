import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ifrs9 import config as K  # noqa: E402
from src.ifrs9 import local_rules as LR  # noqa: E402
from src.ifrs9 import pipeline as PL  # noqa: E402
from src.ifrs9 import risk_params as RP  # noqa: E402


@pytest.fixture(scope="module")
def eng():
    return PL.Engine(seed=7, n=1200)


@pytest.fixture(scope="module")
def snap(eng):
    return eng.snapshot("2025-12")


def test_pd_monotone_and_lifetime_consistent(eng):
    assert np.all(np.diff(eng.pd12.to_numpy()) > 0)                       # worse grade, higher PD
    assert np.allclose(eng.M.sum(1), 1)                                    # matrix rows are probabilities
    assert np.all(np.diff(eng.cum, axis=1) >= -1e-12)                      # cumulative PD never falls
    assert np.allclose(eng.cum[:, 0], eng.pd12.to_numpy())


def test_vasicek_direction():
    h = np.array([0.02])
    assert RP.vasicek(h, -1.5)[0] > 0.02 > RP.vasicek(h, 1.0)[0]           # bad year raises PD


def test_lgd_bounds_and_collateral_effect():
    ead = np.array([100.0, 100.0, 100.0])
    l = RP.lgd(ead, collateral=np.array([0.0, 100.0, 1000.0]), guarantee_cover=np.zeros(3), eir=np.full(3, 0.06))
    assert np.all((l >= K.LGD_FLOOR) & (l <= 1))
    assert l[0] > l[1] > l[2] - 1e-12
    assert np.isclose(l[0], K.LGD_UNSECURED)


def test_ecl_formulas(snap):
    s1, s2, s3 = (snap[snap.stage == s] for s in (1, 2, 3))
    assert np.allclose(s1.ecl, s1.ecl_12m) and np.allclose(s2.ecl, s2.ecl_lifetime)
    assert np.allclose(s3.ecl, s3.lgd * s3.ead)
    assert np.all(snap.ecl_lifetime >= snap.ecl_12m - 1e-9)                # lifetime ECL >= 12-month ECL
    assert (snap.ecl <= snap.ead + 1e-9).all()


def test_staging_rules(eng):
    S = eng.stages.merge(eng.panel[["counterparty_id", "month", "status", "days_past_due", "internal_rating"]],
                         on=["counterparty_id", "month"])
    assert (S[S.status == "default"].stage == 3).all()
    perf = S[S.status == "performing"]
    assert (perf[perf.days_past_due > 30].stage == 2).all()
    assert (perf[pd.to_numeric(perf.internal_rating) >= 8].stage == 2).all()


def test_local_rules(snap):
    order = {b: i for i, b in enumerate(K.LOCAL_BUCKETS)}
    npl = snap[snap.stage == 3]
    assert npl.local_bucket.isin(["Pre-doubtful", "Doubtful", "Compromised"]).all()
    comp = snap[snap.local_bucket == "Compromised"]
    assert (comp.days_past_due >= 360).all()
    assert np.allclose(snap.local_provision, snap.local_rate * snap.provision_base)
    assert (snap.provision_base <= snap.on_balance + 1e-9).all()
    assert snap.local_bucket.map(order).notna().all()


def test_reconciliation_adds_up(eng, snap):
    B = PL.bridge(snap)
    assert np.isclose(B.mad_m.iloc[0] + B[B.kind == "step"].mad_m.sum(), B.mad_m.iloc[-1])
    mov = PL.movement(eng)
    assert np.isclose(mov.loc["Closing allowance", "Total"], snap.ecl.sum())
    assert np.isclose(mov.drop(index="Closing allowance")["Total"].sum(), mov.loc["Closing allowance", "Total"])


def test_development_window_excludes_reporting_period(eng):
    # migration counts only use cohorts whose 12-month window ends by DEVELOPMENT_END
    late = eng.panel[eng.panel.month > K.DEVELOPMENT_END]
    counts_without_late = RP.migration_counts(eng.panel[eng.panel.month <= K.DEVELOPMENT_END], eng.truth)
    assert counts_without_late.to_numpy().sum() == eng.counts.to_numpy().sum()
    assert len(late) > 0
