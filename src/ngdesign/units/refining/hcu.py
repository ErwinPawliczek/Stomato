"""Hydrocracker: yield table (R0) and six-path lumped first-order kinetics (R1).

No yield or rate number here is a package default.  Published hydrocracker yield
correlations are chart-based (Gary, Handwerk & Kaiser, *Petroleum Refining*, 5th
ed., §7.6) and lumped constants are specific to a feed and catalyst, so the user
supplies them; a missing value is a typed refusal.

The lumps are representative real paraffins, the device of the reformer_cat
spec: a real H2 feed consumed into formula-free pseudo products cannot close the
element ledger (issue #222), while these close it exactly and give a real heat
of reaction on the formation basis.  VGO = nC24, diesel = nC12, naphtha = nC6,
gas = C3, and every scission halves the chain with one H2:

    nC24 + H2 -> 2 nC12      nC12 + H2 -> 2 nC6      nC6 + H2 -> 2 C3

with the three direct paths of the four-lump network (VGO, distillate, naphtha,
gas: Sadighi, Ahmad & Rashidzadeh, Korean J. Chem. Eng. 27 (2010) 1099) as their
sums: nC24 + 3 H2 -> 4 nC6, nC24 + 7 H2 -> 8 C3, nC12 + 3 H2 -> 4 C3.  Hydrogen
consumption therefore counts scissions only: it omits the aromatic saturation
and hydrotreating that dominate a real unit, and is a lower bound.

R0 reads conversion, diesel and naphtha mass yields from a user table (wt% on
VGO, linear interpolation, no extrapolation); gas and hydrogen follow from the
element balance of the three chain reactions, so the gas lump is by difference.
R1 integrates first-order loss of each parent over contact time 1/LHSV with
k_j = k0*exp(-Ea/(R*T)) at the isothermal bed temperature, hydrogen in excess:
d(n_parent)/dtau = -sum_j k_j*n_parent.  The network is linear, so the solution
is a matrix exponential.  The rows of the plan call R1 continuous lumping; this
is discrete lumping, and the catalogue note says so.

The separation is sharp and ideal: each lump leaves on its port at (T_out,
P_out), H2 and C3 on ``gas_out``.  Duty closes on the formation basis.  All SI.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.linalg import expm

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import Reaction, ReactionSet
from ngdesign.data import component_record
from ngdesign.units._physics.kinetics import R, ReactionExtentError, apply_extents, enthalpy_with_formation

VGO, DIESEL, NAPHTHA, GAS, HYDROGEN = "nC24", "nC12", "nC6", "C3", "H2"
_SLATE = [VGO, DIESEL, NAPHTHA, GAS, HYDROGEN]

#: Reaction id, stoichiometry and base component of each network path.
_PATHS: tuple[tuple[str, dict[str, float], str], ...] = (
    ("vgo_to_diesel", {VGO: -1.0, HYDROGEN: -1.0, DIESEL: 2.0}, VGO),
    ("vgo_to_naphtha", {VGO: -1.0, HYDROGEN: -3.0, NAPHTHA: 4.0}, VGO),
    ("vgo_to_gas", {VGO: -1.0, HYDROGEN: -7.0, GAS: 8.0}, VGO),
    ("diesel_to_naphtha", {DIESEL: -1.0, HYDROGEN: -1.0, NAPHTHA: 2.0}, DIESEL),
    ("diesel_to_gas", {DIESEL: -1.0, HYDROGEN: -3.0, GAS: 4.0}, DIESEL),
    ("naphtha_to_gas", {NAPHTHA: -1.0, HYDROGEN: -1.0, GAS: 2.0}, NAPHTHA),
)

#: The contract validates each path's element balance on construction.
NETWORK = ReactionSet(
    id="hcu_representative_paraffins",
    components=_SLATE,
    reactions=[
        Reaction(
            id=rid,
            stoichiometry=stoich,
            base_component=base,
            provenance="representative-paraffin scission network; four-lump paths of Sadighi et al. 2010",
        )
        for rid, stoich, base in _PATHS
    ],
)

#: Outlet port of each species.
_PORTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("naphtha_out", (NAPHTHA,)),
    ("diesel_out", (DIESEL,)),
    ("unconverted_out", (VGO,)),
    ("gas_out", (GAS, HYDROGEN)),
)


class HcuSpecError(ValueError):
    """Raised when hydrocracker parameters are missing or inconsistent."""


def _number(params: Mapping[str, Any], key: str, *, positive: bool = True) -> float:
    if key not in params:
        raise HcuSpecError(f"{key} is required: the hydrocracker has no default for it")
    value = float(params[key])
    if positive and value <= 0.0:
        raise HcuSpecError(f"{key} must be > 0")
    return value


def _mw(cid: str) -> float:
    return float(component_record(cid)["mw"])


def _inlet_flows(inlets: Mapping[str, StreamState]) -> dict[str, float]:
    """The mixed feed, refusing anything outside the representative slate."""
    vgo = inlets["vgo_in"].component_flows()
    hydrogen = inlets["hydrogen_in"].component_flows()
    if {cid for cid, n in vgo.items() if n > 0.0} != {VGO}:
        raise HcuSpecError(
            f"vgo_in must be the representative {VGO}: a pseudo VGO has no atoms to balance a real "
            "H2 feed against (elemental characterisation is issue #222)"
        )
    if {cid for cid, n in hydrogen.items() if n > 0.0} != {HYDROGEN}:
        raise HcuSpecError("hydrogen_in must be pure H2")
    return {VGO: vgo[VGO], HYDROGEN: hydrogen[HYDROGEN]}


def _finish(
    inlets: Mapping[str, StreamState],
    flows: Mapping[str, float],
    extents: Sequence[float],
    params: Mapping[str, Any],
    thermo: Thermo,
) -> UnitResult:
    """Sharp split, flashes, formation-basis duty and the common info."""
    t_out = _number(params, "T_out")
    p_out = _number(params, "P_out")
    try:
        n_out = apply_extents(flows, NETWORK, list(extents))
    except ReactionExtentError as exc:
        raise HcuSpecError(f"not enough hydrogen for this conversion: {exc}") from exc
    outlets: dict[str, StreamState] = {}
    for port, species in _PORTS:
        amounts = {cid: n_out.get(cid, 0.0) for cid in species if n_out.get(cid, 0.0) > 0.0}
        total = math.fsum(amounts.values())
        z = {cid: n / total for cid, n in amounts.items()} if total > 0.0 else {species[0]: 1.0}
        outlets[port] = thermo.flash_pt(z, t_out, p_out, total)
    h_in = math.fsum(enthalpy_with_formation(s) for s in inlets.values())
    h_out = math.fsum(enthalpy_with_formation(s) for s in outlets.values())
    mass_feed = flows[VGO] * _mw(VGO)
    info: dict[str, float] = {
        "conversion_wt_pct": 100.0 * (1.0 - n_out[VGO] / flows[VGO]),
        "diesel_wt_pct": 100.0 * n_out.get(DIESEL, 0.0) * _mw(DIESEL) / mass_feed,
        "naphtha_wt_pct": 100.0 * n_out.get(NAPHTHA, 0.0) * _mw(NAPHTHA) / mass_feed,
        "gas_wt_pct": 100.0 * n_out.get(GAS, 0.0) * _mw(GAS) / mass_feed,
        "h2_consumed_mol_s": flows[HYDROGEN] - n_out[HYDROGEN],
        "h2_consumed_wt_pct": 100.0 * (flows[HYDROGEN] - n_out[HYDROGEN]) * _mw(HYDROGEN) / mass_feed,
    }
    return UnitResult(outlets=outlets, duty_W=h_out - h_in, info=info)


class HcuR0:
    """Hydrocracker at R0: user yield table against conversion."""

    inlet_ports: tuple[str, ...] = ("vgo_in", "hydrogen_in")
    outlet_ports: tuple[str, ...] = tuple(port for port, _ in _PORTS)

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        flows = _inlet_flows(inlets)
        table = params.get("yield_table")
        if table is None:
            raise HcuSpecError(
                "yield_table is required: hydrocracker yields are feed- and catalyst-specific and "
                "the published correlations are charts, so the package carries no default table"
            )
        conversion = _number(params, "conversion_wt_pct")
        grid = [float(x) for x in table.get("conversion_wt_pct", ())]
        if len(grid) < 2 or any(b <= a for a, b in zip(grid, grid[1:], strict=False)):
            raise HcuSpecError("yield_table.conversion_wt_pct needs >= 2 strictly increasing points")
        for name in ("diesel_wt_pct", "naphtha_wt_pct"):
            if name not in table:
                raise HcuSpecError(f"yield_table.{name} is required")
            if len(table[name]) != len(grid):
                raise HcuSpecError(f"yield_table.{name} must have the same length as conversion_wt_pct")
        if not grid[0] <= conversion <= grid[-1]:
            raise HcuSpecError(
                f"conversion_wt_pct {conversion} is outside the table [{grid[0]}, {grid[-1]}]: "
                "no extrapolation"
            )
        mass_feed = flows[VGO] * _mw(VGO)
        diesel = float(np.interp(conversion, grid, table["diesel_wt_pct"])) * mass_feed / 100.0 / _mw(DIESEL)
        naphtha = (
            float(np.interp(conversion, grid, table["naphtha_wt_pct"])) * mass_feed / 100.0 / _mw(NAPHTHA)
        )
        # Chain extents from the stoichiometry: D = 2*xi1 - xi2, N = 2*xi2 - xi3.
        xi1 = flows[VGO] * conversion / 100.0
        xi2 = 2.0 * xi1 - diesel
        xi3 = 2.0 * xi2 - naphtha
        if xi2 < 0.0 or xi3 < 0.0:
            raise HcuSpecError(
                f"the yields at conversion {conversion} exceed the carbon converted: "
                "diesel and naphtha leave a negative gas yield"
            )
        extents = {"vgo_to_diesel": xi1, "diesel_to_naphtha": xi2, "naphtha_to_gas": xi3}
        return _finish(inlets, flows, [extents.get(rid, 0.0) for rid, _, _ in _PATHS], params, thermo)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A test-only table, NOT published data."""
        feeds = {
            "vgo_in": {"T": 650.0, "P": 1.5e7, "molar_flow": 1.0, "composition": {VGO: 1.0}},
            "hydrogen_in": {"T": 650.0, "P": 1.5e7, "molar_flow": 10.0, "composition": {HYDROGEN: 1.0}},
        }
        params: dict[str, Any] = {
            "conversion_wt_pct": 70.0,
            "T_out": 650.0,
            "P_out": 1.4e7,
            "yield_table": {
                "conversion_wt_pct": [50.0, 90.0],
                "diesel_wt_pct": [35.0, 45.0],
                "naphtha_wt_pct": [10.0, 30.0],
            },
        }
        return feeds, params


class HcuR1:
    """Hydrocracker at R1: discrete six-path first-order kinetics, isothermal bed."""

    inlet_ports: tuple[str, ...] = HcuR0.inlet_ports
    outlet_ports: tuple[str, ...] = HcuR0.outlet_ports

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        flows = _inlet_flows(inlets)
        kinetics = params.get("kinetics")
        if kinetics is None:
            raise HcuSpecError(
                "kinetics is required: lumped hydrocracking constants are feed- and "
                "catalyst-specific, so the package carries none"
            )
        ids = [rid for rid, _, _ in _PATHS]
        unknown = sorted(set(kinetics) - set(ids))
        if unknown:
            raise HcuSpecError(f"kinetics names unknown paths {unknown}; expected {ids}")
        temperature = _number(params, "T_bed_K")
        tau = 3600.0 / _number(params, "lhsv_per_h")
        k = np.zeros(len(ids))
        for j, rid in enumerate(ids):
            if rid not in kinetics:
                raise HcuSpecError(f"kinetics.{rid} is required (give k0_per_s 0 to switch it off)")
            k0 = _number(kinetics[rid], "k0_per_s", positive=False)
            k[j] = k0 * math.exp(-_number(kinetics[rid], "Ea_J_mol", positive=False) / (R * temperature))

        # Linear states: the three parents, then the extents; x' = A*x, x(0) = parents.
        parents = [VGO, DIESEL, NAPHTHA]
        n_x = len(parents) + len(ids)
        a = np.zeros((n_x, n_x))
        for j, (_, stoich, base) in enumerate(_PATHS):
            source = parents.index(base)
            a[len(parents) + j, source] = k[j]
            for row, cid in enumerate(parents):
                a[row, source] += stoich.get(cid, 0.0) * k[j]
        x0 = np.zeros(n_x)
        x0[0] = flows[VGO]
        x_end = expm(a * tau) @ x0
        return _finish(inlets, flows, [float(x) for x in x_end[len(parents) :]], params, thermo)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Test-only kinetics, NOT published constants or defaults."""
        feeds, _ = HcuR0.example_case()
        k = {"k0_per_s": 1.0e6, "Ea_J_mol": 1.2e5}
        params: dict[str, Any] = {
            "T_bed_K": 650.0,
            "lhsv_per_h": 1.0,
            "T_out": 650.0,
            "P_out": 1.4e7,
            "kinetics": {
                "vgo_to_diesel": k,
                "vgo_to_naphtha": {**k, "k0_per_s": 2.0e5},
                "vgo_to_gas": {**k, "k0_per_s": 5.0e4},
                "diesel_to_naphtha": {**k, "k0_per_s": 2.0e5},
                "diesel_to_gas": {**k, "k0_per_s": 2.0e4},
                "naphtha_to_gas": {**k, "k0_per_s": 2.0e4},
            },
        }
        return feeds, params
