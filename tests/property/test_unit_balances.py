"""Balance closure per catalogue-implemented level, on its example case. LOCKED.

Review round 2 (U-00, item 3): the test iterates the catalogue's implemented
levels instead of the registered unit list — one solve per (row, level) pair,
through the registry's ``LevelDispatch`` entry with ``params["model"]`` set to
the level. The assertions and tolerances are unchanged.
"""

import math

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.catalogue import load_rows
from ngdesign.units.levels import implemented_levels
from tests.conftest import flash_feed

UNITS = [
    f"{row.id}/{level}"
    for row in load_rows().values()
    for level in implemented_levels(row)
]


@pytest.mark.parametrize("name", UNITS or ["<none>"])
def test_balances(thermo: Thermo, name: str) -> None:
    if name == "<none>":
        pytest.skip("no unit plugins yet")
    row_id, level = name.split("/")
    unit = registry.create("unit", row_id)  # the per-row LevelDispatch entry
    feeds, params = unit.example_case()
    assert set(feeds) == set(unit.inlet_ports), f"{name}: example_case must feed every inlet port"
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    res = unit.solve(inlets, {**params, "model": level}, thermo)
    assert set(res.outlets) == set(unit.outlet_ports)

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

    h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
    h_out = sum(s.enthalpy * s.molar_flow for s in res.outlets.values())
    scale = max(abs(h_in), abs(h_out), 1.0)
    assert math.isclose(h_in + res.duty_W + res.power_W, h_out, rel_tol=1e-4, abs_tol=1e-4 * scale), (
        f"{name}: energy balance off by {h_in + res.duty_W + res.power_W - h_out} W"
    )
