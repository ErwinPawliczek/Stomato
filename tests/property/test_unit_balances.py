"""Balance closure per catalogue-implemented level, on its example case. LOCKED.

Review round 2 (U-00, item 3): the test iterates the catalogue's implemented
levels instead of the registered unit list — one solve per (row, level) pair,
through the registry's ``LevelDispatch`` entry with ``params["model"]`` set to
the level. The assertions and tolerances are unchanged.

U-01b: ``balance: mass_elements`` rows (reactors) conserve total mass and
every element instead of each component, and close energy on the basis
``ngdesign.units.balance.energy_basis`` names. Molar rows are checked exactly
as before; the basis rules have one owner, shared with the V0 harness.
"""

import math

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.balance import energy_basis, mass_and_atoms, stream_enthalpy
from ngdesign.units.catalogue import load_rows
from ngdesign.units.levels import implemented_levels
from tests.conftest import flash_feed

ROWS = load_rows()
UNITS = [f"{row.id}/{level}" for row in ROWS.values() for level in implemented_levels(row)]


@pytest.mark.parametrize("name", UNITS or ["<none>"])
def test_balances(thermo: Thermo, name: str) -> None:
    if name == "<none>":
        pytest.skip("no unit plugins yet")
    row_id, level = name.split("/")
    unit = registry.create("unit", row_id)  # the per-row LevelDispatch entry
    # Each level solves on its OWN example case: a higher level's params differ
    # from the default level's, and level adapters refuse keys outside their schema.
    feeds, params = type(unit)._adapters[level].example_case()
    assert set(feeds) == set(unit.inlet_ports), f"{name}: example_case must feed every inlet port"
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    res = unit.solve(inlets, {**params, "model": level}, thermo)
    assert set(res.outlets) == set(unit.outlet_ports)

    balance = ROWS[row_id].balance
    if balance == "mass_elements":
        mass_in, atoms_in = mass_and_atoms(inlets.values())
        mass_out, atoms_out = mass_and_atoms(res.outlets.values())
        assert math.isclose(mass_in, mass_out, rel_tol=1e-6), f"{name}: mass not conserved"
        for element in set(atoms_in) | set(atoms_out):
            a_in, a_out = atoms_in.get(element, 0.0), atoms_out.get(element, 0.0)
            assert math.isclose(a_in, a_out, abs_tol=1e-6 * max(a_in, a_out, 1.0)), (
                f"{name}: element {element} not conserved"
            )
    else:
        fin: dict[str, float] = {}
        for s in inlets.values():
            for c, n in s.component_flows().items():
                fin[c] = fin.get(c, 0.0) + n
        fout: dict[str, float] = {}
        for s in res.outlets.values():
            for c, n in s.component_flows().items():
                fout[c] = fout.get(c, 0.0) + n
        total = sum(fin.values())
        for c in set(fin) | set(fout):
            assert math.isclose(fin.get(c, 0.0), fout.get(c, 0.0), abs_tol=1e-6 * total), (
                f"{name}: {c} not conserved"
            )

    basis = energy_basis(balance, inlets.values(), res.outlets.values(), res.info)
    h_in = stream_enthalpy(inlets.values(), basis)
    h_out = stream_enthalpy(res.outlets.values(), basis)
    scale = max(abs(h_in), abs(h_out), 1.0)
    assert math.isclose(h_in + res.duty_W + res.power_W, h_out, rel_tol=1e-4, abs_tol=1e-4 * scale), (
        f"{name}: energy balance off by {h_in + res.duty_W + res.power_W - h_out} W ({basis} basis)"
    )
