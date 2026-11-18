import os
import sys
from datetime import date

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ratestress import risk
from ratestress.curve import ParCurve, ZeroCurve, bootstrap
from ratestress.portfolio import add_months, cash_flows, load_portfolio, portfolio_value
from ratestress.scenarios import historical_2022, irrbb_scenarios

ROOT = os.path.join(os.path.dirname(__file__), "..")
AS_OF = date(2026, 11, 17)


@pytest.fixture
def portfolio():
    return load_portfolio(os.path.join(ROOT, "data", "portfolio.csv"))


@pytest.fixture
def par_curve():
    return ParCurve.from_csv(os.path.join(ROOT, "data", "base_curve.csv"))


def test_flat_par_curve_bootstraps_to_same_zero_rate():
    z = bootstrap(ParCurve([0.5, 30], [0.04, 0.04]))
    assert np.allclose(z.zero_rates, 0.04, atol=1e-10)


def test_par_bond_prices_at_100_on_its_own_curve():
    as_of = date(2026, 11, 15)
    z = bootstrap(ParCurve([0.5, 30], [0.05, 0.05]))
    t, cf = cash_flows(5.0, date(2036, 11, 15), 2, as_of)
    assert np.sum(cf * z.discount_factor(t)) == pytest.approx(100.0, abs=0.05)


def test_zero_coupon_matches_closed_form():
    z = ZeroCurve([0.5, 30], [0.04, 0.04])
    df = z.discount_factor(10.0)
    assert df == pytest.approx((1.02) ** -20)


def test_add_months_clamps_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 15), -6) == date(2026, 5, 15)


def test_cash_flows_end_on_maturity_with_principal():
    t, cf = cash_flows(4.0, date(2031, 11, 15), 2, AS_OF)
    assert cf[-1] == pytest.approx(102.0)
    assert len(cf) == 10


def test_matured_bond_raises():
    with pytest.raises(ValueError):
        cash_flows(4.0, date(2020, 1, 1), 2, AS_OF)


def test_key_rate_dv01s_sum_to_parallel_dv01(portfolio, par_curve):
    z = bootstrap(par_curve)
    krd = risk.key_rate_dv01(portfolio, z, AS_OF)
    m = risk.effective_measures(portfolio, z, AS_OF, dy=risk.BP)
    assert krd["dv01"].sum() == pytest.approx(m["dv01"], rel=1e-3)


def test_convexity_makes_down_gain_exceed_up_loss(portfolio, par_curve):
    z = bootstrap(par_curve)
    mv0 = portfolio_value(portfolio, z, AS_OF)
    up = portfolio_value(portfolio, z.shifted(risk.parallel(0.02), "u"), AS_OF) - mv0
    dn = portfolio_value(portfolio, z.shifted(risk.parallel(-0.02), "d"), AS_OF) - mv0
    assert up < 0 < dn
    assert dn > -up


def test_irrbb_shapes_at_short_and_long_end():
    sc = {s.name: s for s in irrbb_scenarios()}
    assert sc["Short up"].shift(np.array([0.0]))[0] == pytest.approx(0.03)
    assert sc["Short up"].shift(np.array([30.0]))[0] < 0.001
    assert sc["Steepener"].shift(np.array([0.0]))[0] < 0 < sc["Steepener"].shift(np.array([30.0]))[0]
    assert sc["Flattener"].shift(np.array([0.0]))[0] > 0 > sc["Flattener"].shift(np.array([30.0]))[0]


def test_2022_replay_is_a_bear_flattener():
    shift = historical_2022().shift
    assert shift(np.array([0.5]))[0] > shift(np.array([10.0]))[0] > 0


def test_limit_status_flags():
    import pandas as pd
    measures = {"dv01": 120, "duration": 3.0}
    scen = pd.DataFrame({"scenario": ["A"], "pnl": [-5], "pnl_pct_mv": [-0.05]})
    krd = pd.DataFrame({"key_tenor": [5.0], "dv01": [1.0], "share_of_total": [0.25]})
    limits = {"max_dv01": 100, "max_duration": 3.5, "max_loss_pct_mv": 10,
              "max_bucket_share_pct": 30}
    assert list(risk.check_limits(limits, measures, scen, krd)["status"]) == \
        ["BREACH", "WARN", "OK", "WARN"]
