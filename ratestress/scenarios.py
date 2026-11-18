"""Interest-rate shock scenarios.

1. Six standardised IRRBB shocks (Basel Committee, "Interest rate risk in the
   banking book", 2016). Shapes, with t in years:
       short-rate shock  S(t) = S_short * exp(-t / 4)
       long-rate shock   L(t) = S_long  * (1 - exp(-t / 4))
       parallel          +/- S_parallel
       steepener        -0.65 * |S(t)| + 0.9 * |L(t)|
       flattener        +0.80 * |S(t)| - 0.6 * |L(t)|
       short up / down  +/- S(t)
   USD shock sizes: parallel 200bp, short 300bp, long 150bp.
   These are applied to the zero curve.

2. A historical scenario that replays the 2022 move in US Treasury par yields
   (end-2021 -> end-2022) on top of today's par curve.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

USD_SHOCKS = {"parallel": 0.0200, "short": 0.0300, "long": 0.0150}

# Approximate US Treasury par (CMT) yields, %, at year-end 2021 and 2022.
# Source: U.S. Treasury Daily Par Yield Curve Rates. Verify exact values on
# home.treasury.gov before quoting them.
HIST_TENORS = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30])
YE2021 = np.array([0.06, 0.19, 0.39, 0.73, 0.97, 1.26, 1.44, 1.52, 1.94, 1.90])
YE2022 = np.array([4.42, 4.76, 4.73, 4.41, 4.22, 3.99, 3.96, 3.88, 4.14, 3.97])


@dataclass
class Scenario:
    name: str
    shift: Callable[[np.ndarray], np.ndarray]   # t (years) -> shift (decimal)
    applies_to: str                             # "zero" or "par"
    family: str                                 # "IRRBB" or "Historical"


def _short(t, size):
    return size * np.exp(-np.asarray(t, dtype=float) / 4.0)


def _long(t, size):
    return size * (1.0 - np.exp(-np.asarray(t, dtype=float) / 4.0))


def irrbb_scenarios(shocks=USD_SHOCKS):
    p, s, l = shocks["parallel"], shocks["short"], shocks["long"]
    return [
        Scenario("Parallel up",   lambda t: np.full_like(np.asarray(t, float), p),  "zero", "IRRBB"),
        Scenario("Parallel down", lambda t: np.full_like(np.asarray(t, float), -p), "zero", "IRRBB"),
        Scenario("Steepener",     lambda t: -0.65 * _short(t, s) + 0.9 * _long(t, l), "zero", "IRRBB"),
        Scenario("Flattener",     lambda t: 0.80 * _short(t, s) - 0.6 * _long(t, l), "zero", "IRRBB"),
        Scenario("Short up",      lambda t: _short(t, s),  "zero", "IRRBB"),
        Scenario("Short down",    lambda t: -_short(t, s), "zero", "IRRBB"),
    ]


def historical_2022():
    change = (YE2022 - YE2021) / 100.0
    return Scenario("2022 replay",
                    lambda t: np.interp(t, HIST_TENORS, change),
                    "par", "Historical")


def all_scenarios():
    return irrbb_scenarios() + [historical_2022()]
