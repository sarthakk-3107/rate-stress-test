"""Bond portfolio: cash-flow generation and full revaluation off a zero curve."""

import calendar
from datetime import date

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["bond_id", "description", "sector", "face_value",
                    "coupon_pct", "maturity", "frequency", "spread_bps"]


def add_months(d, months):
    """Add (possibly negative) months to a date, clamping to month end."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def load_portfolio(path):
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"portfolio file is missing columns: {missing}")
    df["maturity"] = pd.to_datetime(df["maturity"]).dt.date
    if (df["face_value"] <= 0).any():
        raise ValueError("face_value must be positive for every holding")
    return df


def cash_flows(coupon_pct, maturity, frequency, as_of):
    """Return (times_in_years, cash_flows_per_100_face) after as_of.

    Coupon dates are generated backwards from maturity so the final payment
    lands exactly on the maturity date. frequency 0 means zero-coupon / bill.
    """
    if maturity <= as_of:
        raise ValueError(f"bond matured on {maturity}, before as-of date {as_of}")

    if frequency == 0 or coupon_pct == 0:
        dates = [maturity]
        flows = [100.0]
    else:
        step = 12 // int(frequency)
        dates = []
        d = maturity
        k = 0
        while d > as_of:
            dates.append(d)
            k += 1
            d = add_months(maturity, -step * k)
        dates.reverse()
        coupon = coupon_pct / frequency
        flows = [coupon] * len(dates)
        flows[-1] += 100.0

    times = np.array([(d - as_of).days / 365.25 for d in dates])
    return times, np.array(flows)


def price_bond(row, curve, as_of):
    """Dirty price per 100 face, discounting at zero curve + bond spread."""
    t, cf = cash_flows(row["coupon_pct"], row["maturity"], int(row["frequency"]), as_of)
    spread = row["spread_bps"] / 10_000.0
    return float(np.sum(cf * curve.discount_factor(t, spread=spread)))


def revalue(portfolio, curve, as_of):
    """Full revaluation: price and market value of every holding."""
    out = portfolio[["bond_id", "description", "sector", "face_value"]].copy()
    out["price"] = [price_bond(r, curve, as_of) for _, r in portfolio.iterrows()]
    out["market_value"] = out["price"] / 100.0 * out["face_value"]
    out["years_to_maturity"] = [(m - as_of).days / 365.25 for m in portfolio["maturity"]]
    return out


def portfolio_value(portfolio, curve, as_of):
    return float(revalue(portfolio, curve, as_of)["market_value"].sum())
