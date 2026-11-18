# Interest-Rate Stress Test: Summary

As of **2026-11-17** · base curve: **base_curve.csv** · portfolio market value **$982.2m**

## Key messages

- **Worst case:** the *2022 replay* scenario reduces portfolio value by **$89.4m (9.1% of market value)**.
- **Sensitivity:** every 1bp rise in rates costs about **$364k** (DV01); effective duration is **3.70 years**.
- **Concentration:** 58% of rate risk sits in the 10y, 5y, 7y buckets.
- **Limits:** 2 limit breach(es): Portfolio DV01 ($ per bp); Worst-scenario loss, % of MV (2022 replay). Escalation required.
- **Early warning:** 1 indicator(s) above 80% of limit: Effective duration (years).

## Scenario results

| Scenario | Type | P&L | % of MV |
|---|---|---:|---:|
| 2022 replay | Historical | -$89.4m | -9.10% |
| Parallel up | IRRBB | -$66.8m | -6.81% |
| Short up | IRRBB | -$27.3m | -2.78% |
| Steepener | IRRBB | -$16.7m | -1.70% |
| Flattener | IRRBB | $3.0m | 0.30% |
| Short down | IRRBB | $28.4m | 2.89% |
| Parallel down | IRRBB | $79.9m | 8.13% |

Best outcome: *Parallel down* ($79.9m). Falling rates raise bond values, so down-shocks produce gains.

Largest contributors to the *2022 replay* loss:

- UST Note 10Y 4.375%: -$15.3m
- UST Note 5Y 4.125%: -$12.5m
- UST Note 7Y 4.250%: -$9.7m

## Key risk indicators vs limits

| Indicator | Value | Limit | Used | Status |
|---|---:|---:|---:|---|
| Portfolio DV01 ($ per bp) | 363,631.16 | 350,000.00 | 104% | **BREACH** |
| Effective duration (years) | 3.70 | 4.00 | 93% | **WARN** |
| Worst-scenario loss, % of MV (2022 replay) | 9.10 | 8.00 | 114% | **BREACH** |
| Largest key-rate bucket share (10y) | 22.00 | 30.00 | 73% | **OK** |

## Model check: duration and convexity approximations

For a +200bp parallel shift, full revaluation gives -$66.8m. Duration alone is off by -$5.9m; adding convexity cuts the error to $579k. The headline numbers above use full revaluation.

## Method notes

- Zero curve bootstrapped from par yields (semi-annual, linear interpolation).
- IRRBB shocks (BCBS 2016 shapes, USD sizes 200/300/150bp) applied to the zero curve, floored at 0%. The 2022 replay adds the end-2021 to end-2022 change in Treasury par yields to today's par curve.
- Credit spreads held constant: this isolates interest-rate risk only.
- Holdings are a mock portfolio for illustration.
