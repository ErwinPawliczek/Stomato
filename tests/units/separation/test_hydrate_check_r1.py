"""hydrate_check R1 step-1 tests: the Towler-Mokhatab Katz gas-gravity fit.

Closed-form check, hand-computed from the spec's equation
(T[°F] = 13.47·ln P + 34.27·ln γ − 1.675·(ln P)(ln γ) − 20.35, P in psia):

CF1: P = 7.0e6 Pa → P_psia = 7.0e6/6894.757293168 = 1015.26415...
     ln P = 6.9227377..., ln 0.65 = −0.4307829...
     T_F = 13.47·6.9227377 + 34.27·(−0.4307829)
           − 1.675·6.9227377·(−0.4307829) − 20.35
         = 93.2432... − 14.7621... + 5.0028... − 20.35 = 63.133888 °F
     T_K = (63.133888 + 459.67)/1.8 = 290.4466045623... K

The spec's printed table (290.446605, 282.69495, 295.805364) is this
quantity rounded to 6 decimal places; the full-precision constants below are
recomputed in the test runner's scratchpad and the printed values are
additionally asserted at their printing precision (±5e-7 K).
"""

from __future__ import annotations

import pytest

from ngdesign.units.separation.hydrate_check_r1 import (
    HydrateCheckR1SpecError,
    towler_mokhatab_T_K,
)

# Full-precision anchors, computed independently from the transcribed
# coefficients (scratchpad math only; see the module docstring for CF1).
_CF1 = (7.0e6, 0.65, 290.4466045623803)
_CF2 = (3.0e6, 0.60, 282.6949504904699)
_CF3 = (10.0e6, 0.80, 295.8053642171896)
_PRINTED = [
    (7.0e6, 0.65, 290.446605),
    (3.0e6, 0.60, 282.69495),
    (10.0e6, 0.80, 295.805364),
]


@pytest.mark.parametrize("P,sg,expected", [_CF1, _CF2, _CF3], ids=["CF1", "CF2", "CF3"])
def test_towler_mokhatab_cf(P: float, sg: float, expected: float) -> None:
    assert towler_mokhatab_T_K(P, sg) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("P,sg,printed", _PRINTED, ids=["CF1-printed", "CF2-printed", "CF3-printed"])
def test_towler_mokhatab_printed_table(P: float, sg: float, printed: float) -> None:
    # The spec's table is printed at 6 decimal places: ±5e-7 K rounding.
    assert towler_mokhatab_T_K(P, sg) == pytest.approx(printed, abs=5e-7)


def test_cf1_katz_chart_sanity() -> None:
    # CF1 sits within about 1 K of the Katz chart's reading near 1000 psia
    # for SG 0.65 (about 62-63 °F, i.e. 290 K): coarse guard.
    assert 285.0 < towler_mokhatab_T_K(7.0e6, 0.65) < 295.0


def test_towler_mokhatab_refuses_sg_out_of_range() -> None:
    with pytest.raises(HydrateCheckR1SpecError, match="Towler-Mokhatab range"):
        towler_mokhatab_T_K(7.0e6, 1.5)
    with pytest.raises(HydrateCheckR1SpecError, match="Towler-Mokhatab range"):
        towler_mokhatab_T_K(7.0e6, 0.5)


def test_towler_mokhatab_refuses_p_out_of_range() -> None:
    with pytest.raises(HydrateCheckR1SpecError, match="Towler-Mokhatab range"):
        towler_mokhatab_T_K(1.0e6, 0.65)  # below 1200 kPa
    with pytest.raises(HydrateCheckR1SpecError, match="Towler-Mokhatab range"):
        towler_mokhatab_T_K(4.5e7, 0.65)  # above 40000 kPa
