"""The relaxation's stage enthalpy model: ideal-gas part exact in composition.

A frozen stage model's phase enthalpy is the mixture's ideal-gas enthalpy
sum_i c_i h_i^ig(T) plus a departure line frozen at the stage's own phase
(relaxation.py). The former composition-blind line h_0 + c_p (T - T_0) read a
steam-stripper stage's hydrocarbon vapour at steam's molar enthalpy - an order
of magnitude low - and locked the crude column's relaxation into a limit
cycle. These checks need no column solve: the column is only built.
"""

from __future__ import annotations

import numpy as np
import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import _build_column, _parse_params, _ThermoBox
from ngdesign.units.column.inside_out import _Column
from ngdesign.units.column.relaxation import _IG_P, _ideal_gas, _refresh
from tests.units.column.test_relaxation_start import _steam_stripped


def _column(thermo: Thermo) -> tuple[_Column, _ThermoBox]:
    parsed = _parse_params(_steam_stripped(), None)
    tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
    return _build_column(parsed, tb), tb


def _vector(col: _Column, comp: dict[str, float]) -> np.ndarray:
    return np.array([comp.get(c, 0.0) for c in col.comps])


def test_ideal_gas_table_matches_the_package_across_the_band(thermo: Thermo) -> None:
    """The cubic Hermite table reproduces the package's own low-pressure pure
    vapour builds inside the band (anchored only at its ends)."""
    col, tb = _column(thermo)
    ig = _ideal_gas(col, tb)
    lo, hi = col.t_band_lo, col.t_band_hi
    for frac in (0.25, 0.5, 0.75):
        t = lo + frac * (hi - lo)
        h = ig.h(t)
        for i, cid in enumerate(col.comps):
            ref = thermo.phase_props({cid: 1.0}, t, _IG_P, PhaseKind.VAPOR)
            assert h[i] == pytest.approx(ref.enthalpy, rel=1e-2, abs=50.0), (cid, t)
            assert ig.cp(t)[i] == pytest.approx(ref.cp, rel=2e-2), (cid, t)


def test_stage_model_tracks_a_composition_swing_of_its_vapour(thermo: Thermo) -> None:
    """A stripper stage model frozen at a near-pure-steam vapour reads a
    hydrocarbon vapour at that vapour's own enthalpy (the package's build),
    not at steam's: the swing a steam stripper makes between relaxation
    passes."""
    col, tb = _column(thermo)
    ig = _ideal_gas(col, tb)
    s = col.n_graph - 1  # the stripper's bottom stage, under its steam
    t, p = 540.0, col.pressures[s]
    x = _vector(col, {"nC8": 0.2, "nC11": 0.4, "nC14": 0.4})
    y_steam = _vector(col, {"H2O": 0.98, "nC11": 0.02})
    y_hc = {"nC5": 0.2, "nC8": 0.5, "nC11": 0.3}
    model = _refresh(col, tb, s, t, x, y_steam, None, ig)
    steam = tb.phase_state({"H2O": 0.98, "nC11": 0.02}, t, p, vapor=True).enthalpy
    hc = tb.phase_state(y_hc, t, p, vapor=True).enthalpy
    assert hc > 5.0 * steam  # the swing is an order of magnitude per mole
    assert model.hv(t, y_steam) == pytest.approx(steam, rel=1e-9)
    assert model.hv(t, _vector(col, y_hc)) == pytest.approx(hc, rel=2e-2)
    # Off the anchor temperature the ideal-gas part follows the composition too.
    t2 = t + 20.0
    hc2 = tb.phase_state(y_hc, t2, p, vapor=True).enthalpy
    assert model.hv(t2, _vector(col, y_hc)) == pytest.approx(hc2, rel=2e-2)
