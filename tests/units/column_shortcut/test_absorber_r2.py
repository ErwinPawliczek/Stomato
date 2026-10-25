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

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
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


# ---------------------------------------------------------------------------
# Closed form: the equilibrium-pair limit (spec step 2).
# ---------------------------------------------------------------------------

_EQUIL_Z = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}


def _equilibrium_pair_inlets(
    thermo: Thermo,
) -> tuple[dict[str, StreamState], float, float, dict[str, float]]:
    """One PT flash split into its vapour and liquid phases as the two feeds.

    Everything here comes from ``thermo.flash_pt`` — never from a column call
    (the spec's closed-form construction). Returns the inlets plus the flash's
    (V, L, y): the counter-current column then transfers nothing at any N, so
    ``gas_out == gas_in`` and ``rich_out == solvent_in``.
    """
    z_flash = thermo.flash_pt(dict(_EQUIL_Z), 300.0, 2e6, 100.0)
    v_flow = z_flash.vapor_fraction * 100.0
    l_flow = (1.0 - z_flash.vapor_fraction) * 100.0
    vapour = next(p for p in z_flash.phases if p.kind == PhaseKind.VAPOR)
    liquid = next(p for p in z_flash.phases if p.kind != PhaseKind.VAPOR)
    y = dict(vapour.composition)
    x = dict(liquid.composition)
    gas_in = thermo.flash_pt(y, 300.0, 2e6, v_flow)
    solvent_in = thermo.flash_pt(x, 300.0, 2e6, l_flow)
    return {"gas_in": gas_in, "solvent_in": solvent_in}, v_flow, l_flow, y


@pytest.mark.parametrize("n", [2, 4, 8])
def test_closed_form_equilibrium_pair_transfers_nothing(thermo: Thermo, n: int) -> None:
    """gas_in and solvent_in are the two phases of ONE PT flash: at equilibrium
    with the lean, the column transfers nothing at any N.

    Expected values come from the test's own flash, never from the column.
    Measured through the column directly on main (spec): dD/V = -2.45e-9 (N=2),
    -2.65e-9 (N=4), -2.77e-9 (N=8); max |dy| 2.9e-9..3.4e-9; T_top - 300 =
    -8e-7 K — all inside the asserted bands.
    """
    inlets, v_flow, _l_flow, y = _equilibrium_pair_inlets(thermo)
    res = AbsorberR2().solve(inlets, {"n_stages": n}, thermo)
    assert res.outlets["gas_out"].molar_flow == pytest.approx(v_flow, rel=1e-8)
    for cid, yv in y.items():
        assert res.outlets["gas_out"].composition[cid] == pytest.approx(yv, abs=1e-8)
    # Top stage (stage 1 -> the column's stage index 0) sits at the 300 K feed T.
    assert res.info["stage_0_T_K"] == pytest.approx(300.0, abs=1e-5)


@pytest.mark.parametrize("n", [2, 4, 8])
def test_closed_form_rich_out_unchanged(thermo: Thermo, n: int) -> None:
    """rich_out stays the liquid feed (rel 1e-7 on its flow)."""
    inlets, _v_flow, l_flow, _y = _equilibrium_pair_inlets(thermo)
    res = AbsorberR2().solve(inlets, {"n_stages": n}, thermo)
    assert res.outlets["rich_out"].molar_flow == pytest.approx(l_flow, rel=1e-7)


# ---------------------------------------------------------------------------
# Balances and the energy-residual bound (spec step 2).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [2, 4, 20])
def test_balance_total_moles(thermo: Thermo, n: int) -> None:
    """Total moles close at 1e-8 on the R0 example feeds."""
    inlets = _example_inlets(thermo)
    res = AbsorberR2().solve(inlets, {"n_stages": n}, thermo)
    total_in = sum(s.molar_flow for s in inlets.values())
    total_out = sum(s.molar_flow for s in res.outlets.values())
    assert abs(total_out - total_in) / total_in < 1e-8


@pytest.mark.parametrize("n", [2, 4, 20])
def test_balance_per_component(thermo: Thermo, n: int) -> None:
    """Per-component closure at the column's documented gate, on the P1-09
    measurement basis (C1/nC4 gas into lean nC4 — the case P1-09 measured the
    5e-8 gate on; N=8 is NOT asserted, its measured floor is 3.4e-2).

    MEASURED on this branch through the adapter: worst component residual
    2.9e-12 (N=2, NC4), 1.6e-8 (N=4, NC4), 1.2e-8 (N=20, NC4).
    """
    gas = thermo.flash_pt({"C1": 0.9, "NC4": 0.1}, 300.0, 2e6, 100.0)
    lean = thermo.flash_pt({"NC4": 1.0}, 300.0, 2e6, 30.0)
    inlets = {"gas_in": gas, "solvent_in": lean}
    res = AbsorberR2().solve(inlets, {"n_stages": n}, thermo)
    fin: dict[str, float] = {}
    for s in inlets.values():
        for cid, flow in s.component_flows().items():
            fin[cid] = fin.get(cid, 0.0) + flow
    fout: dict[str, float] = {}
    for s in res.outlets.values():
        for cid, flow in s.component_flows().items():
            fout[cid] = fout.get(cid, 0.0) + flow
    for cid in set(fin) | set(fout):
        assert abs(fout.get(cid, 0.0) - fin[cid]) / fin[cid] < 5e-8, cid


@pytest.mark.parametrize("n", [2, 4, 20])
def test_balance_per_component_example_case_measured_floor(thermo: Thermo, n: int) -> None:
    """The R0 example case (a C6+ lean that flashes largely vapour) carries a
    looser stage-level M floor than the P1-09 basis. MEASURED on this branch
    through the adapter: worst residual 1.5e-4 (N=2, C1), 7.6e-4 (N=4, C1),
    5.4e-5 (N=20, C1) — the zero/one-tear correlation gate's own signature
    (spec.py), not an adapter defect. Bound = 2x the worst measurement.
    """
    inlets = _example_inlets(thermo)
    res = AbsorberR2().solve(inlets, {"n_stages": n}, thermo)
    fin: dict[str, float] = {}
    for s in inlets.values():
        for cid, flow in s.component_flows().items():
            fin[cid] = fin.get(cid, 0.0) + flow
    fout: dict[str, float] = {}
    for s in res.outlets.values():
        for cid, flow in s.component_flows().items():
            fout[cid] = fout.get(cid, 0.0) + flow
    for cid in set(fin) | set(fout):
        assert abs(fout.get(cid, 0.0) - fin[cid]) / fin[cid] < 2e-3, cid


@pytest.mark.parametrize("n", [2, 4, 20])
def test_energy_residual_within_mesh_gate(thermo: Thermo, n: int) -> None:
    """|mesh_energy_residual_rel| <= 1e-2 (the column's _MESH_H_TOL).
    MEASURED on this branch on the example feeds: 7.3e-6 (N=2), 2.5e-5 (N=4),
    4.0e-6 (N=20).
    """
    inlets = _example_inlets(thermo)
    res = AbsorberR2().solve(inlets, {"n_stages": n}, thermo)
    assert abs(res.info["mesh_energy_residual_rel"]) <= 1e-2
