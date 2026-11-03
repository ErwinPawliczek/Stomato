"""PR package PT flash of a vapour at its dew point (``_state._FlashVLN``).

The state is captured from a crude column solve: the vapour leaving the flash
zone (16-cut light-crude slate plus light ends and stripping-steam water,
22 species) flashed at its own stage temperature and pressure. thermo's
FlashVLN finds the incipient liquid, its three-phase check fails, and the
liquid-liquid retry - two liquid-class objects both on the gas root - ran out
of its 1000-iteration polish budget and raised ``UnconvergedError`` ("End of SS
without convergence") out of the whole flash.
"""

from __future__ import annotations

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data.assay import CutScheme
from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
from ngdesign.units.refining.slate import register_slate

_P = "bagajewicz_ji_2001_light_NBP"
#: Captured stage vapour (mole fractions as the column handed them to the package).
_Z = {
    "C2": 0.004031354705475602,
    "C3": 0.022922485651679647,
    "H2O": 0.00916105968661392,
    f"{_P}1045": 3.2541200575316636e-07,
    f"{_P}1108": 4.074173454824019e-08,
    f"{_P}1172": 6.265152240992056e-09,
    f"{_P}1235": 1.5284591822538726e-09,
    f"{_P}1298": 8.722831500944525e-10,
    f"{_P}356": 0.20339728850762515,
    f"{_P}414": 0.19441729597929272,
    f"{_P}477": 0.1660110753031012,
    f"{_P}539": 0.1335249604654652,
    f"{_P}603": 0.09724962729776512,
    f"{_P}659": 0.04863092067677519,
    f"{_P}729": 0.016635600685473713,
    f"{_P}793": 0.00449634232897003,
    f"{_P}853": 0.00016187124497526144,
    f"{_P}919": 2.094551794884378e-05,
    f"{_P}982": 2.701140058022059e-06,
    "iC4": 0.012122698760750568,
    "iC5": 0.02323952372554673,
    "nC4": 0.034923307352566865,
    "nC5": 0.0290505661502814,
}
_T = 631.6835605310557
_PRESSURE = 2.0e5


@pytest.fixture(scope="module", autouse=True)
def _slate() -> None:
    register_slate(_EXAMPLE_ASSAY, CutScheme.equal_count(16))


def test_dew_point_vapour_flashes(thermo: Thermo) -> None:
    """The captured state flashes: a vapour carrying its incipient liquid
    (thermo's own VL solution, liquid fraction ~3e-10), no exception."""
    state = thermo.flash_pt(_Z, _T, _PRESSURE, 1.0)
    vapour = [p for p in state.phases if p.kind == PhaseKind.VAPOR]
    assert len(vapour) == 1
    assert state.vapor_fraction == pytest.approx(1.0, abs=1e-8)
