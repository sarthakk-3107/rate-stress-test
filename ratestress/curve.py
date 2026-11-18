"""Yield curve construction: par curve -> bootstrapped zero curve.

Conventions
-----------
* Input yields are Treasury par (CMT) yields as decimals (0.042 = 4.2%).
* Zero rates use semi-annual compounding, matching US Treasury convention:
      DF(t) = (1 + z(t) / 2) ** (-2 t)
* Interpolation is linear in rate with flat extrapolation at both ends.
"""

import numpy as np
import pandas as pd

GRID_STEP = 0.5          # bootstrap grid in years (semi-annual coupon dates)
MAX_TENOR = 30.0


class ParCurve:
    """Par yield curve defined at a handful of tenors (e.g. CMT points)."""

    def __init__(self, tenors, yields, label="base"):
        tenors = np.asarray(tenors, dtype=float)
        yields = np.asarray(yields, dtype=float)
        if tenors.shape != yields.shape or tenors.size < 2:
            raise ValueError("tenors and yields must be equal-length arrays (>= 2 points)")
        if np.any(tenors <= 0):
            raise ValueError("tenors must be positive")
        order = np.argsort(tenors)
        self.tenors = tenors[order]
        self.yields = yields[order]
        self.label = label

    @classmethod
    def from_csv(cls, path, label="base"):
        df = pd.read_csv(path)
        return cls(df["tenor_years"], df["par_yield_pct"] / 100.0, label=label)

    def par_yield(self, t):
        return np.interp(t, self.tenors, self.yields)

    def shifted(self, shift_fn, label):
        """Return a new par curve with shift_fn(tenors) added (decimal)."""
        return ParCurve(self.tenors, self.yields + shift_fn(self.tenors), label=label)

    def to_frame(self):
        return pd.DataFrame({"tenor_years": self.tenors, "par_yield": self.yields})


class ZeroCurve:
    """Zero-coupon curve on a regular grid, semi-annual compounding."""

    def __init__(self, tenors, zero_rates, label="base"):
        self.tenors = np.asarray(tenors, dtype=float)
        self.zero_rates = np.asarray(zero_rates, dtype=float)
        self.label = label

    def rate(self, t):
        return np.interp(t, self.tenors, self.zero_rates)

    def discount_factor(self, t, spread=0.0):
        t = np.asarray(t, dtype=float)
        z = self.rate(t) + spread
        return (1.0 + z / 2.0) ** (-2.0 * t)

    def shifted(self, shift_fn, label, floor=None):
        """Add shift_fn(t) (decimal) to every zero rate; optionally floor rates."""
        new_rates = self.zero_rates + shift_fn(self.tenors)
        if floor is not None:
            new_rates = np.maximum(new_rates, floor)
        return ZeroCurve(self.tenors, new_rates, label=label)

    def to_frame(self):
        return pd.DataFrame({"tenor_years": self.tenors, "zero_rate": self.zero_rates})


def bootstrap(par_curve, step=GRID_STEP, max_tenor=MAX_TENOR):
    """Bootstrap semi-annual zero rates from a par curve.

    For the n-th semi-annual date t_n with par coupon c (paid c/2 per period),
    a par bond prices at 1:
        1 = (c/2) * sum_{i<n} DF_i + (1 + c/2) * DF_n
    which we solve for DF_n, then convert to a zero rate.
    """
    grid = np.arange(step, max_tenor + 1e-9, step)
    dfs = []
    zeros = []
    for t in grid:
        c = float(par_curve.par_yield(t))
        df_n = (1.0 - (c / 2.0) * sum(dfs)) / (1.0 + c / 2.0)
        if df_n <= 0:
            raise ValueError(f"bootstrap failed at t={t}: non-positive discount factor")
        dfs.append(df_n)
        zeros.append(2.0 * (df_n ** (-1.0 / (2.0 * t)) - 1.0))
    return ZeroCurve(grid, zeros, label=par_curve.label)


def fetch_live_par_curve():
    """Pull a coarse live Treasury curve from Yahoo Finance (optional).

    ^IRX = 13-week bill, ^FVX = 5y, ^TNX = 10y, ^TYX = 30y (all quoted in %).
    Only four points, so intermediate tenors are linearly interpolated.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed: pip install yfinance") from exc

    tickers = {"^IRX": 0.25, "^FVX": 5.0, "^TNX": 10.0, "^TYX": 30.0}
    tenors, yields = [], []
    for ticker, tenor in tickers.items():
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            raise RuntimeError(f"no data returned for {ticker}")
        tenors.append(tenor)
        yields.append(float(hist["Close"].iloc[-1]) / 100.0)
    return ParCurve(tenors, yields, label="live")
