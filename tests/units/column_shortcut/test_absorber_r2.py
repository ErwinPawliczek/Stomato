"""Absorber R2 tests: identity to the column row, and refusals (spec step 1).

The identity test asserts the adapter's outlets equal a direct
``Column().solve`` with the mapped params, field by field with ``==`` (the
same floats) — the level's identity is to the column row itself, since R0
(Kremser) and R2 (MESH) are different models with no exact reduction.

The closed-form equilibrium-pair and balance tests land in step 2 (spec
steps are committed in order).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column, ColumnConvergenceError
from ngdesign.units.column_shortcut import absorber_r2
from ngdesign.units.column_shortcut.absorber import Absorber
from ngdesign.units.column_shortcut.absorber_r2 import AbsorberR2, AbsorberR2Error


def _example_inlets(thermo: Thermo) -> dict[str, StreamState]:
    """The R0 example feeds, flashed into StreamStates (the R0 pattern)."""
    feeds, _ = Absorber.example_case()
    return {
        port: thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])
        for port, feed in feeds.items()
    }


def _mapped_column_params(inlets: dict[str, StreamState], n_stages: int) -> dict[str, Any]:
    """The adapter's mapping, written out (what the adapter must equal)."""
    gas_in = inlets["gas_in"]
    solvent_in = inlets["solvent_in"]
    return {
        "n_stages": n_stages,
        "condenser": "none",
        "reboiler": "none",
        "pressure_profile": gas_in.P,
        "feed_stage": n_stages,
        "feeds": [
            {
                "stage": 1,
                "T": solvent_in.T,
                "P": solvent_in.P,
                "molar_flow": solvent_in.molar_flow,
                "composition": dict(solvent_in.composition),
            }
        ],
    }


def test_identity_to_column_row(thermo: Thermo) -> None:
    """R0 example feeds, N = 4: the adapter IS a direct Column().solve.

    Field-by-field ``==``: the same thermo instance LRU-caches per package,
    so the two solve paths must return bit-identical states.
    """
    inlets = _example_inlets(thermo)
    res = AbsorberR2().solve(inlets, {"n_stages": 4}, thermo)
    direct = Column().solve({"feed": inlets["gas_in"]}, _mapped_column_params(inlets, 4), thermo)

    for out_port, col_port in (("gas_out", "distillate"), ("rich_out", "bottoms")):
        adapter_state = res.outlets[out_port]
        column_state = direct.outlets[col_port]
        assert adapter_state.T == column_state.T, out_port
        assert adapter_state.P == column_state.P, out_port
        assert adapter_state.molar_flow == column_state.molar_flow, out_port
        assert adapter_state.vapor_fraction == column_state.vapor_fraction, out_port
        assert adapter_state.enthalpy == column_state.enthalpy, out_port
        assert adapter_state.entropy == column_state.entropy, out_port
        assert adapter_state.composition == column_state.composition, out_port
        assert adapter_state.phases == column_state.phases, out_port

    # info: every stage_* key unchanged, plus the adapter's own keys.
    for key, value in direct.info.items():
        if key.startswith("stage_"):
            assert res.info[key] == value, key
    assert res.info["n_stages"] == 4.0
    assert res.info["outer_iterations"] == direct.info["outer_iterations"]
    assert res.info["inner_iterations"] == direct.info["inner_iterations"]
    assert res.info["ns_used"] == direct.info["ns_used"]
    # duty_W is the boundary residual; it must close V0 exactly by construction.
    h_in = sum(s.molar_flow * s.enthalpy for s in inlets.values())
    h_out = sum(s.molar_flow * s.enthalpy for s in res.outlets.values())
    assert res.duty_W == h_out - h_in
    assert res.power_W == 0.0
    assert res.info["mesh_energy_residual_W"] == res.duty_W


# ---------------------------------------------------------------------------
# Refusals: one test per row of the spec's refusal table.
# ---------------------------------------------------------------------------


def test_refusal_missing_n_stages(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    with pytest.raises(AbsorberR2Error, match="n_stages"):
        AbsorberR2().solve(inlets, {}, thermo)


def test_refusal_n_stages_not_an_int(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    with pytest.raises(AbsorberR2Error, match="n_stages"):
        AbsorberR2().solve(inlets, {"n_stages": 4.0}, thermo)


def test_refusal_n_stages_below_two(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    with pytest.raises(AbsorberR2Error, match="n_stages"):
        AbsorberR2().solve(inlets, {"n_stages": 1}, thermo)


def test_refusal_pressure_profile_wrong_length(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    with pytest.raises(AbsorberR2Error, match="pressure_profile"):
        AbsorberR2().solve(inlets, {"n_stages": 4, "pressure_profile": [2e6, 2e6]}, thermo)


def test_refusal_pressure_profile_nonpositive_entry(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    with pytest.raises(AbsorberR2Error, match="pressure_profile"):
        AbsorberR2().solve(inlets, {"n_stages": 4, "pressure_profile": [2e6, 0.0, 2e6, 2e6]}, thermo)


def test_refusal_gas_in_zero_flow(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    dead_gas = inlets["gas_in"].model_copy(update={"molar_flow": 0.0})
    with pytest.raises(AbsorberR2Error, match="gas_in"):
        AbsorberR2().solve({"gas_in": dead_gas, "solvent_in": inlets["solvent_in"]}, {"n_stages": 4}, thermo)


def test_refusal_solvent_in_zero_flow(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    dead_solvent = inlets["solvent_in"].model_copy(update={"molar_flow": 0.0})
    with pytest.raises(AbsorberR2Error, match="solvent_in"):
        AbsorberR2().solve({"gas_in": inlets["gas_in"], "solvent_in": dead_solvent}, {"n_stages": 4}, thermo)


def test_refusal_solvent_in_mostly_vapour(thermo: Thermo) -> None:
    """Vapour fraction > 0.5: the zero-tear seed assumes a liquid top feed."""
    inlets = _example_inlets(thermo)
    vapour_solvent = inlets["solvent_in"].model_copy(update={"vapor_fraction": 0.6})
    with pytest.raises(AbsorberR2Error, match="solvent_in"):
        AbsorberR2().solve(
            {"gas_in": inlets["gas_in"], "solvent_in": vapour_solvent},
            {"n_stages": 4},
            thermo,
        )


def test_refusal_unknown_parameter(thermo: Thermo) -> None:
    inlets = _example_inlets(thermo)
    with pytest.raises(AbsorberR2Error, match="unknown"):
        AbsorberR2().solve(inlets, {"n_stages": 4, "turbo_encabulator": 1.0}, thermo)


def test_column_convergence_error_propagates_unchanged(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adapter never catches or converts ColumnConvergenceError."""

    def _boom(self: Column, inlets: dict[str, StreamState], params: dict[str, Any], t: Thermo) -> UnitResult:
        raise ColumnConvergenceError("column convergence failure (test stub)")

    monkeypatch.setattr(absorber_r2, "Column", type("StubColumn", (), {"solve": _boom}))
    inlets = _example_inlets(thermo)
    with pytest.raises(ColumnConvergenceError, match="column convergence failure"):
        AbsorberR2().solve(inlets, {"n_stages": 4}, thermo)
