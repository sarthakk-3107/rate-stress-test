"""Risk measures and stress-test engine."""

import numpy as np
import pandas as pd

from .curve import bootstrap
from .portfolio import portfolio_value, revalue

BP = 0.0001
KEY_TENORS = [0.5, 1, 2, 3, 5, 7, 10, 20, 30]
RATE_FLOOR = 0.0    # post-shock zero rates floored at 0% (simplification)


def parallel(size):
    return lambda t: np.full_like(np.asarray(t, dtype=float), size)


def effective_measures(portfolio, zero_curve, as_of, dy=10 * BP):
    """Effective duration, convexity and DV01 by bumping the zero curve."""
    p0 = portfolio_value(portfolio, zero_curve, as_of)
    p_up = portfolio_value(portfolio, zero_curve.shifted(parallel(dy), "up"), as_of)
    p_dn = portfolio_value(portfolio, zero_curve.shifted(parallel(-dy), "dn"), as_of)
    duration = (p_dn - p_up) / (2.0 * p0 * dy)
    convexity = (p_dn + p_up - 2.0 * p0) / (p0 * dy ** 2)
    return {"market_value": p0, "duration": duration,
            "convexity": convexity, "dv01": duration * p0 * BP}


def bond_level_dv01(portfolio, zero_curve, as_of):
    base = revalue(portfolio, zero_curve, as_of)
    up = revalue(portfolio, zero_curve.shifted(parallel(BP), "up"), as_of)
    dn = revalue(portfolio, zero_curve.shifted(parallel(-BP), "dn"), as_of)
    base["dv01"] = (dn["market_value"] - up["market_value"]) / 2.0
    base["mod_duration"] = base["dv01"] / (base["market_value"] * BP)
    return base


def _triangle(t, k, keys):
    """Triangular weight for key tenor k; flat beyond the first/last key."""
    t = np.asarray(t, dtype=float)
    i = keys.index(k)
    w = np.zeros_like(t)
    left = keys[i - 1] if i > 0 else None
    right = keys[i + 1] if i < len(keys) - 1 else None
    if left is None:
        w[t <= k] = 1.0
    else:
        m = (t > left) & (t <= k)
        w[m] = (t[m] - left) / (k - left)
    if right is None:
        w[t >= k] = 1.0
    else:
        m = (t > k) & (t < right)
        w[m] = (right - t[m]) / (right - k)
    w[t == k] = 1.0
    return w


def key_rate_dv01(portfolio, zero_curve, as_of, keys=KEY_TENORS):
    """DV01 per key tenor. Triangular bumps sum to a parallel bump, so the
    key-rate DV01s add up to the parallel DV01 (up to rounding)."""
    rows = []
    for k in keys:
        bump = lambda t, k=k: BP * _triangle(t, k, keys)
        up = portfolio_value(portfolio, zero_curve.shifted(bump, "up"), as_of)
        dn = portfolio_value(portfolio, zero_curve.shifted(lambda t, b=bump: -b(t), "dn"), as_of)
        rows.append({"key_tenor": k, "dv01": (dn - up) / 2.0})
    df = pd.DataFrame(rows)
    df["share_of_total"] = df["dv01"] / df["dv01"].sum()
    return df


def shocked_zero_curve(par_curve, scenario):
    base_zero = bootstrap(par_curve)
    if scenario.applies_to == "par":
        shocked_par = par_curve.shifted(scenario.shift, scenario.name)
        return bootstrap(shocked_par)
    return base_zero.shifted(scenario.shift, scenario.name, floor=RATE_FLOOR)


def run_scenarios(portfolio, par_curve, as_of, scenarios, measures):
    """Full revaluation under each scenario, plus a duration-convexity estimate
    for comparison where the shock is parallel."""
    base_zero = bootstrap(par_curve)
    base = revalue(portfolio, base_zero, as_of)
    mv0 = base["market_value"].sum()

    summary, by_bond, curves = [], [], {"Base": base_zero}
    for sc in scenarios:
        z = shocked_zero_curve(par_curve, sc)
        curves[sc.name] = z
        shocked = revalue(portfolio, z, as_of)
        pnl = shocked["market_value"].sum() - mv0

        # average shift across the portfolio's cash-flow horizon (for context)
        avg_shift_bp = float(np.mean(z.zero_rates - base_zero.zero_rates)) / BP

        summary.append({"scenario": sc.name, "family": sc.family,
                        "pnl": pnl, "pnl_pct_mv": pnl / mv0,
                        "avg_curve_shift_bp": avg_shift_bp})
        b = base[["bond_id", "description", "sector"]].copy()
        b["scenario"] = sc.name
        b["pnl"] = shocked["market_value"] - base["market_value"]
        by_bond.append(b)

    return pd.DataFrame(summary), pd.concat(by_bond, ignore_index=True), curves


def approximation_table(portfolio, zero_curve, as_of, measures,
                        shifts_bp=range(-300, 301, 25)):
    """Full revaluation vs duration-only vs duration+convexity for parallel shifts."""
    mv0, d, c = measures["market_value"], measures["duration"], measures["convexity"]
    rows = []
    for s in shifts_bp:
        dy = s * BP
        full = portfolio_value(portfolio, zero_curve.shifted(parallel(dy), "x"), as_of) - mv0
        rows.append({"shift_bp": s, "full_reval": full,
                     "duration_only": -d * mv0 * dy,
                     "duration_convexity": mv0 * (-d * dy + 0.5 * c * dy ** 2)})
    return pd.DataFrame(rows)


def check_limits(limits, measures, scenario_df, krd_df):
    """Compare risk numbers to limits; status is OK / WARN (>=80% used) / BREACH."""
    def status(used):
        return "BREACH" if used > 1.0 else ("WARN" if used >= 0.8 else "OK")

    worst = scenario_df.loc[scenario_df["pnl"].idxmin()]
    top = krd_df.loc[krd_df["dv01"].idxmax()]
    checks = [
        ("Portfolio DV01 ($ per bp)", measures["dv01"], limits["max_dv01"]),
        ("Effective duration (years)", measures["duration"], limits["max_duration"]),
        (f"Worst-scenario loss, % of MV ({worst['scenario']})",
         -worst["pnl_pct_mv"] * 100, limits["max_loss_pct_mv"]),
        (f"Largest key-rate bucket share ({top['key_tenor']:g}y)",
         top["share_of_total"] * 100, limits["max_bucket_share_pct"]),
    ]
    rows = []
    for name, value, limit in checks:
        used = value / limit
        rows.append({"indicator": name, "value": value, "limit": limit,
                     "utilisation_pct": used * 100, "status": status(used)})
    return pd.DataFrame(rows)
