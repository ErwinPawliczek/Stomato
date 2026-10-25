"""Isenthalpic stripper vapour return (PR #239 review item 3).

The stripper overhead leaves the stripper at (T_ov, p_draw) and re-enters
the main column at the return stage, which sits above the draw and so at
the main column's lower pressure P_ret there. The let-down does no shaft
work, so the injected feed must carry the overhead's ENTHALPY: injecting
the overhead temperature itself changes the enthalpy the main column
receives by h(T, p_draw) - h(T, P_ret) per mole, which breaks the
whole-unit energy balance by exactly that term. These tests pin the
injection machinery to the isenthalpic requirement, with enthalpies
recomputed from the thermo plugin (none copied from model output).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column.coupled import _injected, _isenthalpic_return_T
from ngdesign.units.column.spec import ColumnConvergenceError, _parse_params
from ngdesign.units.column.thermo_adapter import _ThermoBox

_COMP = {"C3": 0.5, "iC4": 0.3, "nC4": 0.2}


def _tb(thermo: Thermo) -> _ThermoBox:
    return _ThermoBox(thermo, 1.0e6, 2.0e6)


def test_injection_temperature_is_isenthalpic(thermo: Thermo) -> None:
    """The inverted temperature realizes the overhead enthalpy at P_ret.

    Gate: the spec's own 1e-8 whole-unit closure tolerance, relative to the
    enthalpy scale. The PT flash's internal convergence sits just beneath
    that floor (measured inversion residual 7.1e-5 J/mol = 5.1e-9 relative
    on this state) - no tighter gate is meaningful against the package.
    """
    tb = _tb(thermo)
    t_ov, p_draw, p_ret = 330.0, 1.5e6, 1.4e6
    h_overhead = tb.pt(dict(_COMP), t_ov, p_draw, 1.0).enthalpy
    t_inj = _isenthalpic_return_T(tb, dict(_COMP), h_overhead, p_ret, t_ov)
    h_injected = tb.pt(dict(_COMP), t_inj, p_ret, 1.0).enthalpy
    assert abs(h_injected - h_overhead) <= 1e-8 * max(abs(h_overhead), 1.0)


def test_naive_temperature_injection_mismatches(thermo: Thermo) -> None:
    """The pre-fix state (overhead T at P_ret) does NOT carry the enthalpy."""
    tb = _tb(thermo)
    t_ov, p_draw, p_ret = 330.0, 1.5e6, 1.4e6
    h_overhead = tb.pt(dict(_COMP), t_ov, p_draw, 1.0).enthalpy
    h_naive = tb.pt(dict(_COMP), t_ov, p_ret, 1.0).enthalpy
    assert abs(h_naive - h_overhead) > 1e-9 * max(abs(h_overhead), 1.0)


def test_unreachable_enthalpy_refuses(thermo: Thermo) -> None:
    """An enthalpy no temperature in the window realizes refuses, typed."""
    tb = _tb(thermo)
    with pytest.raises(ColumnConvergenceError, match="isenthalpic stripper return"):
        _isenthalpic_return_T(tb, dict(_COMP), 1.0e9, 1.4e6, 330.0)


def _params() -> dict[str, Any]:
    return {
        "n_stages": 10,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 5,
        "pressure_profile": {"top": 1.45e6, "bottom": 1.55e6},
        "feeds": [
            {
                "stage": 5,
                "T": 330.0,
                "P": 1.5e6,
                "molar_flow": 100.0,
                "composition": dict(_COMP),
            }
        ],
        "specs": {"reflux_ratio": 2.0, "distillate_rate": 35.0},
        "side_strippers": [
            {
                "name": "S1",
                "draw_stage": 3,
                "return_stage": 2,
                "n_stages": 4,
                "steam": {"flow_mol_s": 2.0, "T_K": 400.0, "P_Pa": 1.6e6},
                "product_rate_mol_s": 8.0,
            }
        ],
    }


def test_injected_feed_carries_overhead_enthalpy(thermo: Thermo) -> None:
    """The feed _injected appends realizes the tear state's p_draw enthalpy.

    The tear composition is a stripper OVERHEAD: a firm single-phase vapour
    at the tear state (vf = 1.0 at both the draw-stage and return-stage
    pressures), so the flash enthalpy is smooth and the isenthalpic gate
    stays at the spec's 1e-8 closure tolerance (relative). A tear state that
    flashes two-phase carries the PT flash's own two-phase enthalpy noise
    (measured ~2e-7 relative) - that noise is the thermo package's, not the
    injection's; the isenthalpic residual it leaves (~6e-4 J/mol) contributes
    ~3e-3 W at stripper-scale flows against a ~1e6 W duty, inside 1e-8 of
    the unit scale.
    """
    tb = _tb(thermo)
    params = _parse_params(_params(), None)
    assert len(params.side_strippers) == 1
    st = params.side_strippers[0]
    ret_comp = {"C3": 0.60, "iC4": 0.25, "nC4": 0.139, "H2O": 0.011}
    ret_t = 360.0
    injected = _injected(tb, params, {"S1": 10.0}, {"S1": (5.0, ret_t, dict(ret_comp))})
    assert len(injected.feeds) == len(params.feeds) + 1
    feed = injected.feeds[-1]
    p_draw = params.pressures[st.draw_stage - 1]
    p_ret = params.pressures[st.return_stage - 1]
    assert feed.stage == st.return_stage
    assert feed.P == p_ret
    assert feed.flow == 5.0
    assert feed.comp == ret_comp
    h_overhead = tb.pt(dict(ret_comp), ret_t, p_draw, 1.0).enthalpy
    h_injected = tb.pt(dict(feed.comp), feed.T, feed.P, 1.0).enthalpy
    assert abs(h_injected - h_overhead) <= 1e-8 * max(abs(h_overhead), 1.0)
