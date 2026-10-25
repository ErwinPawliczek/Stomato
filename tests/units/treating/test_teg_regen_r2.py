"""Tests for the R2 TEG regenerator (spec teg_regen R2).

Step-1 scope: the R0 delegation (zero stripping gas, exact identity), the
G -> 0 march limit, and one test per refusal row of the spec's table.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import create
from ngdesign.units.treating.teg_regen import (
    DEFAULT_P,
    DEFAULT_T_REBOILER,
    TEGRegen,
    TEGRegenError,
    _lean_water_mole_fraction,
)
from ngdesign.units.treating.teg_regen_r2 import TEGRegenR2
from ngdesign.units.treating.teg_stagewise import (
    TEGStageError,
    countercurrent_march,
    teg_x_of_y,
)

THERMO: Thermo = create("thermo", "pr")
PARAMS: dict[str, Any] = {
    "T_reboiler": DEFAULT_T_REBOILER,
    "P": DEFAULT_P,
    "n_stages": 2,
}


def _feed(
    composition: dict[str, float], T: float = 422.15, P: float = 1.5e5, molar_flow: float = 100.0
) -> StreamState:
    return THERMO.flash_pt(composition, T, P, molar_flow)


def _r0(rich: StreamState) -> UnitResult:
    return TEGRegen().solve({"rich_in": rich}, {"T_reboiler": DEFAULT_T_REBOILER, "P": DEFAULT_P}, THERMO)


def test_zero_stripping_gas_delegates_to_r0_exactly() -> None:
    """Identity: no gas port, a zero-flow gas, and n_stages = 0 each give
    R0's result exactly (==) on both outlets and the duty."""
    rich = _feed({"TEG": 0.84, "H2O": 0.15, "C1": 0.008, "CO2": 0.002})
    zero_gas = _feed({"N2": 1.0}, T=477.15, P=101325.0, molar_flow=0.0)

    r0 = _r0(rich)
    no_gas_params = {"T_reboiler": DEFAULT_T_REBOILER, "P": DEFAULT_P, "n_stages": 0}
    for inlets, params in [
        ({"rich_in": rich}, dict(PARAMS)),
        ({"rich_in": rich, "stripping_gas_in": zero_gas}, dict(PARAMS)),
        ({"rich_in": rich, "stripping_gas_in": zero_gas}, no_gas_params),
    ]:
        r2 = TEGRegenR2().solve(inlets, params, THERMO)
        assert r2.duty_W == r0.duty_W
        for port in ("lean_out", "water_out"):
            assert r2.outlets[port].molar_flow == r0.outlets[port].molar_flow
            assert r2.outlets[port].composition == r0.outlets[port].composition
            assert r2.outlets[port].enthalpy == r0.outlets[port].enthalpy
            assert r2.outlets[port].T == r0.outlets[port].T
            assert r2.outlets[port].P == r0.outlets[port].P
        for key, value in r0.info.items():
            assert r2.info[key] == value, key
        assert r2.info["n_stages"] == float(params["n_stages"])
        assert r2.info["stripping_gas_mol_s"] == 0.0
        assert r2.info["purity_enhancement_wt_pct"] == 0.0


def test_g0_limit_march_recovers_the_boiling_line_ratio() -> None:
    """As G -> 0 with N >= 1 the march itself stops stripping: X_N -> X_0.

    SPEC ISSUE (teg_regen R2, step 1): the spec claims "at G = 1e-9 mol/s,
    X_lean matches X_0 to rel 1e-6"; the shared march's numerics do not
    support that. Measured on this correlation (T = 477.15 K, S = 82 mol/s,
    N = 2, dry gas): the residual-scan root Y_1 ~ sqrt(S/(G k)) grows as G
    shrinks, and the liquid ratio gap falls only as sqrt(G) -- rel gap
    2.042e-5 at G = 1e-9 and 6.456e-6 at G = 1e-10, while at G = 1e-11 the
    scan (Y_1 in [1e-14, 1e6]) finds no bracket and the march raises
    TEGStageError. The assertions below use the measured gap with one order
    of headroom (rel 1e-4) and pin the singularity refusal at G = 1e-11.
    """
    T, P = DEFAULT_T_REBOILER, DEFAULT_P
    x_reb = _lean_water_mole_fraction(T, P)
    X_0 = x_reb / (1.0 - x_reb)
    y_1e9, x_1e9 = countercurrent_march(1.0e-9, 82.0, X_0, 0.0, 2, teg_x_of_y(T, P))
    assert x_1e9[-1] == pytest.approx(X_0, rel=1.0e-4)
    y_1e10, x_1e10 = countercurrent_march(1.0e-10, 82.0, X_0, 0.0, 2, teg_x_of_y(T, P))
    assert x_1e10[-1] == pytest.approx(X_0, rel=1.0e-4)
    # The gap tightens as G falls (the sqrt(G) law), and past G ~ 1e-11 the
    # shared march's bracket scan refuses: the singular limit belongs to the
    # delegation path, not the march.
    assert abs(X_0 - x_1e10[-1]) < abs(X_0 - x_1e9[-1])
    with pytest.raises(TEGStageError, match="no bracket"):
        countercurrent_march(1.0e-11, 82.0, X_0, 0.0, 2, teg_x_of_y(T, P))


def test_n_stages_non_integer_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    params = dict(PARAMS, n_stages=2.5)
    with pytest.raises(TEGRegenError, match="n_stages"):
        TEGRegenR2().solve({"rich_in": rich}, params, THERMO)


def test_negative_n_stages_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    with pytest.raises(TEGRegenError, match="n_stages"):
        TEGRegenR2().solve({"rich_in": rich}, dict(PARAMS, n_stages=-1), THERMO)


def test_stripping_gas_carrying_teg_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    gas = _feed({"N2": 0.995, "TEG": 0.005}, T=477.15, P=101325.0, molar_flow=2.0)
    with pytest.raises(TEGRegenError, match="stripping gas"):
        TEGRegenR2().solve({"rich_in": rich, "stripping_gas_in": gas}, dict(PARAMS), THERMO)


def test_pressure_above_water_saturation_is_refused() -> None:
    """R0's own no-boiling refusal, reached through the R2 gas path."""
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    gas = _feed({"N2": 1.0}, T=477.15, P=3.0e6, molar_flow=2.0)
    with pytest.raises(TEGRegenError, match="no boiling"):
        TEGRegenR2().solve(
            {"rich_in": rich, "stripping_gas_in": gas},
            {"T_reboiler": 477.15, "P": 3.0e6, "n_stages": 2},
            THERMO,
        )


def test_unknown_param_key_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    with pytest.raises(TEGRegenError, match="unknown"):
        TEGRegenR2().solve({"rich_in": rich}, dict(PARAMS, extra_key=1.0), THERMO)
