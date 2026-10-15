"""Sour-gas MEA amine loop: absorber + regenerator with lean-solvent recycle.

The MEA twin of the MDEA golden amine loop (``amine_loop.py``): identical
topology -- sour gas, absorber, regenerator, lean-solvent recycle with
make-up/purge anchoring, water trim -- with the solvent amine switched to
aqueous MEA (``mea_absorber``/``mea_regenerator``, the primary-amine chemistry
with carbamate speciation). MEA binds both acid gases more strongly than MDEA,
so the same moderately sour feed clears the spec-driven feasibility checks
with more margin; the e2e golden mirrors the MDEA loop's convergence,
determinism and balance proofs.

See ``amine_loop.py`` for the full design rationale (tear choice, seeding,
make-up/purge anchor, no lean pump in v1).
"""

from __future__ import annotations

from ngdesign.contracts import Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.units.mdea_absorber import MeaAbsorber

#: Cooler setpoint: the lean solvent returns to the absorber at the example
#: absorber feed temperature (the rich/lean exchanger shortcut).
LEAN_RETURN_T = 303.15

#: Slipstream split of the regenerated solvent: recycle share to the mixer,
#: purge share (product). The pair with the make-up feed anchors circulation.
RECYCLE_FRACTION = 0.68
PURGE_FRACTION = 0.32

#: Demin-water trim to the solvent junction, mol/s (solvent water-content trim).
WATER_TRIM_MOLAR_FLOW = 5.0

#: Sour-gas feed: 6.5 MPa, 30 C, sweetened to pipeline spec downstream.
SOUR_GAS_MOLAR_FLOW = 100.0
_SOUR_GAS_RAW = {
    "N2": 0.005,
    "CO2": 0.03,
    "H2S": 300e-6,
    "C1": 0.90,
    "C2": 0.05,
    "C3": 0.02,
    "nC4": 0.01,
    "iC5": 0.002,
    "nC5": 0.002,
    "C6+": 0.001,
    "H2O": 0.0001,
}
SOUR_GAS_COMPOSITION = {c: f / sum(_SOUR_GAS_RAW.values()) for c, f in _SOUR_GAS_RAW.items()}


def build() -> Flowsheet:
    """The sour-gas MEA amine loop: 5 units, 11 streams, one lean-solvent recycle."""

    def p(u: str, port: str) -> PortRef:
        return PortRef(unit=u, port=port)

    makeup_lean = MeaAbsorber.example_case()[0]["lean_amine_in"]

    units = [
        UnitSpec(tag="A-101", kind="mea_absorber", params={}),
        UnitSpec(tag="R-101", kind="mea_regenerator", params={}),
        UnitSpec(tag="SPL-101", kind="splitter", params={"fractions": [RECYCLE_FRACTION, PURGE_FRACTION]}),
        UnitSpec(tag="E-101", kind="heater", params={"T_out": LEAN_RETURN_T, "dP": 0.0}),
        UnitSpec(tag="MIX-101", kind="mixer", params={}),
    ]
    streams = [
        StreamSpec(
            id="S-001",
            target=p("A-101", "gas_in"),
            service="PG",
            feed={
                "T": 303.15,
                "P": 6.5e6,
                "molar_flow": SOUR_GAS_MOLAR_FLOW,
                "composition": dict(SOUR_GAS_COMPOSITION),
            },
        ),
        StreamSpec(id="S-002", source=p("A-101", "gas_out"), service="PG"),
        StreamSpec(id="S-003", source=p("E-101", "outlet"), target=p("MIX-101", "inlet_1"), service="PL"),
        StreamSpec(id="S-004", source=p("R-101", "acid_gas_out"), service="AG"),
        StreamSpec(
            id="S-005", source=p("A-101", "rich_amine_out"), target=p("R-101", "rich_amine_in"), service="PL"
        ),
        StreamSpec(
            id="S-006", source=p("R-101", "lean_amine_out"), target=p("SPL-101", "inlet"), service="PL"
        ),
        StreamSpec(id="S-007", source=p("SPL-101", "outlet_1"), target=p("E-101", "inlet"), service="PL"),
        StreamSpec(id="S-008", source=p("SPL-101", "outlet_2"), service="PL"),
        StreamSpec(
            id="S-009",
            target=p("MIX-101", "inlet_2"),
            service="PL",
            feed={
                "T": makeup_lean["T"],
                "P": makeup_lean["P"],
                "molar_flow": makeup_lean["molar_flow"],
                "composition": dict(makeup_lean["composition"]),
            },
        ),
        StreamSpec(
            id="S-010",
            target=p("MIX-101", "inlet_3"),
            service="PL",
            feed={
                "T": 303.15,
                "P": 1.8e5,
                "molar_flow": WATER_TRIM_MOLAR_FLOW,
                "composition": {"H2O": 1.0},
            },
        ),
        StreamSpec(
            id="S-011", source=p("MIX-101", "outlet"), target=p("A-101", "lean_amine_in"), service="PL"
        ),
    ]
    return Flowsheet(name="sour-gas-mea-amine-loop", units=units, streams=streams)
