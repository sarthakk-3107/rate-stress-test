"""Charts and a plain-English summary for non-technical readers."""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RED, GREEN, GREY, BLUE = "#C0392B", "#2E8B57", "#7F8C8D", "#1F5A96"


def _money(x):
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e9:
        return f"{sign}${x / 1e9:.2f}bn"
    if x >= 1e6:
        return f"{sign}${x / 1e6:.1f}m"
    if x >= 1e3:
        return f"{sign}${x / 1e3:.0f}k"
    return f"{sign}${x:.0f}"


def plot_scenario_pnl(scenario_df, mv, loss_limit_pct, path):
    df = scenario_df.sort_values("pnl")
    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = [RED if v < 0 else GREEN for v in df["pnl"]]
    ax.barh(df["scenario"], df["pnl"] / 1e6, color=colors)
    limit = -loss_limit_pct / 100 * mv / 1e6
    ax.axvline(limit, color="black", linestyle="--", linewidth=1)
    ax.text(limit, -0.75, f" loss limit ({loss_limit_pct:.0f}% of MV)",
            fontsize=8, va="center")
    ax.axvline(0, color=GREY, linewidth=0.8)
    for i, v in enumerate(df["pnl"]):
        ax.text(v / 1e6, i, f" {_money(v)} ", va="center",
                ha="left" if v >= 0 else "right", fontsize=8)
    ax.set_xlabel("Change in portfolio market value ($m)")
    ax.set_title("Portfolio P&L under interest-rate stress scenarios")
    ax.margins(x=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_key_rates(krd_df, path):
    fig, ax = plt.subplots(figsize=(9, 4))
    labels = [f"{k:g}y" for k in krd_df["key_tenor"]]
    ax.bar(labels, krd_df["dv01"] / 1e3, color=BLUE)
    for i, (v, s) in enumerate(zip(krd_df["dv01"], krd_df["share_of_total"])):
        ax.text(i, v / 1e3, f"{s:.0%}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel("DV01 ($k per bp)")
    ax.set_xlabel("Key tenor")
    ax.set_title("Where the rate risk sits: key-rate DV01 by maturity bucket")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_curves(curves, path):
    fig, ax = plt.subplots(figsize=(9, 5))
    for name, z in curves.items():
        style = dict(color="black", linewidth=2.2) if name == "Base" else dict(linewidth=1.2)
        ax.plot(z.tenors, z.zero_rates * 100, label=name, **style)
    ax.set_xlabel("Maturity (years)")
    ax.set_ylabel("Zero rate (%)")
    ax.set_title("Base vs shocked zero curves")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_approximation(approx_df, path):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    x = approx_df["shift_bp"]
    ax.plot(x, approx_df["full_reval"] / 1e6, color="black", linewidth=2.2, label="Full revaluation")
    ax.plot(x, approx_df["duration_only"] / 1e6, linestyle="--", color=RED, label="Duration only")
    ax.plot(x, approx_df["duration_convexity"] / 1e6, linestyle=":", color=BLUE,
            linewidth=2, label="Duration + convexity")
    ax.axhline(0, color=GREY, linewidth=0.8)
    ax.axvline(0, color=GREY, linewidth=0.8)
    ax.set_xlabel("Parallel shift (bp)")
    ax.set_ylabel("P&L ($m)")
    ax.set_title("How good are duration and convexity approximations?")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_summary(path, as_of, curve_label, measures, scenario_df, krd_df,
                  limits_df, approx_df, by_bond_df):
    mv = measures["market_value"]
    worst = scenario_df.loc[scenario_df["pnl"].idxmin()]
    best = scenario_df.loc[scenario_df["pnl"].idxmax()]
    top = krd_df.sort_values("dv01", ascending=False).head(3)
    top_share = top["share_of_total"].sum()

    worst_bonds = (by_bond_df[by_bond_df["scenario"] == worst["scenario"]]
                   .sort_values("pnl").head(3))

    row = approx_df.loc[approx_df["shift_bp"] == 200].iloc[0]
    dur_err = row["duration_only"] - row["full_reval"]
    conv_err = row["duration_convexity"] - row["full_reval"]

    breaches = limits_df[limits_df["status"] == "BREACH"]
    warns = limits_df[limits_df["status"] == "WARN"]

    lines = []
    lines.append("# Interest-Rate Stress Test: Summary\n")
    lines.append(f"As of **{as_of}** · base curve: **{curve_label}** · "
                 f"portfolio market value **{_money(mv)}**\n")

    lines.append("## Key messages\n")
    lines.append(f"- **Worst case:** the *{worst['scenario']}* scenario reduces portfolio value by "
                 f"**{_money(-worst['pnl'])} ({-worst['pnl_pct_mv']:.1%} of market value)**.")
    lines.append(f"- **Sensitivity:** every 1bp rise in rates costs about **{_money(measures['dv01'])}** "
                 f"(DV01); effective duration is **{measures['duration']:.2f} years**.")
    lines.append(f"- **Concentration:** {top_share:.0%} of rate risk sits in the "
                 + ", ".join(f"{k:g}y" for k in top["key_tenor"]) + " buckets.")
    if len(breaches):
        lines.append(f"- **Limits:** {len(breaches)} limit breach(es): "
                     + "; ".join(breaches["indicator"]) + ". Escalation required.")
    else:
        lines.append("- **Limits:** no limit breaches.")
    if len(warns):
        lines.append(f"- **Early warning:** {len(warns)} indicator(s) above 80% of limit: "
                     + "; ".join(warns["indicator"]) + ".")
    lines.append("")

    lines.append("## Scenario results\n")
    lines.append("| Scenario | Type | P&L | % of MV |")
    lines.append("|---|---|---:|---:|")
    for _, r in scenario_df.sort_values("pnl").iterrows():
        lines.append(f"| {r['scenario']} | {r['family']} | {_money(r['pnl'])} | {r['pnl_pct_mv']:.2%} |")
    lines.append("")
    lines.append(f"Best outcome: *{best['scenario']}* ({_money(best['pnl'])}). "
                 "Falling rates raise bond values, so down-shocks produce gains.\n")

    lines.append(f"Largest contributors to the *{worst['scenario']}* loss:\n")
    for _, r in worst_bonds.iterrows():
        lines.append(f"- {r['description']}: {_money(r['pnl'])}")
    lines.append("")

    lines.append("## Key risk indicators vs limits\n")
    lines.append("| Indicator | Value | Limit | Used | Status |")
    lines.append("|---|---:|---:|---:|---|")
    for _, r in limits_df.iterrows():
        lines.append(f"| {r['indicator']} | {r['value']:,.2f} | {r['limit']:,.2f} | "
                     f"{r['utilisation_pct']:.0f}% | **{r['status']}** |")
    lines.append("")

    lines.append("## Model check: duration and convexity approximations\n")
    lines.append(f"For a +200bp parallel shift, full revaluation gives {_money(row['full_reval'])}. "
                 f"Duration alone is off by {_money(dur_err)}; adding convexity cuts the error "
                 f"to {_money(conv_err)}. The headline numbers above use full revaluation.\n")

    lines.append("## Method notes\n")
    lines.append("- Zero curve bootstrapped from par yields (semi-annual, linear interpolation).")
    lines.append("- IRRBB shocks (BCBS 2016 shapes, USD sizes 200/300/150bp) applied to the zero "
                 "curve, floored at 0%. The 2022 replay adds the end-2021 to end-2022 change in "
                 "Treasury par yields to today's par curve.")
    lines.append("- Credit spreads held constant: this isolates interest-rate risk only.")
    lines.append("- Holdings are a mock portfolio for illustration.")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
