"""Run the full interest-rate stress test and write results to ./output.

Examples
--------
    python run_stress_test.py
    python run_stress_test.py --as-of 2026-11-17 --curve data/base_curve.csv
    python run_stress_test.py --live            # pull a live curve via yfinance
"""

import argparse
import json
import os
import sys
from datetime import date

from ratestress import report, risk
from ratestress.curve import ParCurve, bootstrap, fetch_live_par_curve
from ratestress.portfolio import load_portfolio
from ratestress.scenarios import all_scenarios


def parse_args():
    p = argparse.ArgumentParser(description="Portfolio interest-rate stress test")
    p.add_argument("--portfolio", default="data/portfolio.csv")
    p.add_argument("--curve", default="data/base_curve.csv",
                   help="CSV of tenor_years, par_yield_pct")
    p.add_argument("--limits", default="data/limits.json")
    p.add_argument("--as-of", default="2026-11-17", help="valuation date YYYY-MM-DD")
    p.add_argument("--live", action="store_true",
                   help="use a live Treasury curve from yfinance instead of --curve")
    p.add_argument("--out", default="output")
    return p.parse_args()


def main():
    args = parse_args()
    as_of = date.fromisoformat(args.as_of)
    report.ensure_dir(args.out)

    portfolio = load_portfolio(args.portfolio)
    with open(args.limits) as f:
        limits = json.load(f)

    if args.live:
        par_curve = fetch_live_par_curve()
        curve_label = "live Treasury curve (yfinance)"
    else:
        par_curve = ParCurve.from_csv(args.curve)
        curve_label = os.path.basename(args.curve)
    zero_curve = bootstrap(par_curve)

    # 1. Base risk measures
    measures = risk.effective_measures(portfolio, zero_curve, as_of)
    bonds = risk.bond_level_dv01(portfolio, zero_curve, as_of)
    krd = risk.key_rate_dv01(portfolio, zero_curve, as_of)

    # 2. Scenarios (full revaluation)
    scen, by_bond, curves = risk.run_scenarios(portfolio, par_curve, as_of,
                                               all_scenarios(), measures)
    approx = risk.approximation_table(portfolio, zero_curve, as_of, measures)

    # 3. Limits / KRIs
    limit_df = risk.check_limits(limits, measures, scen, krd)

    # 4. Outputs
    bonds.to_csv(os.path.join(args.out, "holdings_risk.csv"), index=False)
    krd.to_csv(os.path.join(args.out, "key_rate_dv01.csv"), index=False)
    scen.to_csv(os.path.join(args.out, "scenario_results.csv"), index=False)
    by_bond.to_csv(os.path.join(args.out, "scenario_pnl_by_bond.csv"), index=False)
    limit_df.to_csv(os.path.join(args.out, "kri_limits.csv"), index=False)
    approx.to_csv(os.path.join(args.out, "approximation_check.csv"), index=False)
    zero_curve.to_frame().to_csv(os.path.join(args.out, "base_zero_curve.csv"), index=False)

    report.plot_scenario_pnl(scen, measures["market_value"], limits["max_loss_pct_mv"],
                             os.path.join(args.out, "scenario_pnl.png"))
    report.plot_key_rates(krd, os.path.join(args.out, "key_rate_dv01.png"))
    report.plot_curves(curves, os.path.join(args.out, "curves.png"))
    report.plot_approximation(approx, os.path.join(args.out, "approximation_check.png"))
    report.write_summary(os.path.join(args.out, "summary.md"), as_of, curve_label,
                         measures, scen, krd, limit_df, approx, by_bond)

    # Console recap
    print(f"Market value : ${measures['market_value']:,.0f}")
    print(f"Duration     : {measures['duration']:.2f} years")
    print(f"DV01         : ${measures['dv01']:,.0f} per bp")
    print("\nScenario P&L:")
    for _, r in scen.sort_values("pnl").iterrows():
        print(f"  {r['scenario']:<14} {r['pnl']:>16,.0f}  ({r['pnl_pct_mv']:+.2%})")
    print("\nKRIs:")
    for _, r in limit_df.iterrows():
        print(f"  [{r['status']:<6}] {r['indicator']}: {r['value']:,.2f} "
              f"(limit {r['limit']:,.2f})")
    print(f"\nResults written to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
