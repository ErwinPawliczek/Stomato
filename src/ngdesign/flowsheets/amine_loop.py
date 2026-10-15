"""Sour-gas amine loop: absorber + regenerator with lean-solvent recycle (topology only).

The golden end-to-end amine case for the expansion spec's sour-gas train: a
sour gas feed is sweetened in the MDEA absorber, the rich solvent is stripped
back to lean specifications in the regenerator, and the lean solvent returns
to the absorber -- one recycle loop through the solver's existing
SCC/tear-stream/Wegstein machinery (no solver work in the amine expansion):

    sour gas -> A-101 absorber -> R-101 regenerator -> SPL-101 -> E-101 cooler
                 ^   gas_out (sales gas)      acid_gas_out |        |
                 |                                          v        v
                 +---- A-101.lean_amine_in <---- MIX-101 <--------------+
                              (recycle + make-up + water trim)          |

Boundary feeds: the sour gas, the fresh lean solvent make-up (the absorber's
documented example solvent, so the loop's solvent basis cannot drift from the
unit's own example case), and a small demin-water trim stream -- amine plants
trim solvent water content, and the trim is the third stream the three-inlet
junction mixer needs.

The make-up/purge pair: the sequential-modular solver seeds the torn stream
with the molar-flow-weighted mean of the boundary feeds, so a fully closed
solvent loop would seed the absorber with a gas-like composition carrying no
MDEA -- a spec-driven unit cannot accept it. The pair (fresh-solvent make-up
and slipstream purge, the solvent-replacement convention) anchors the solvent
circulation the way a pump-around spec or adjust unit would in a simulator
with adjust units (the engine has none -- deferred in the expansion spec): at
the fixed point the purge removes exactly what the make-up adds, and the
circulation rate is set by the pair.

There is no lean pump in v1: the lean side runs at the regenerator pressure.
The pump plugin requires a single-phase liquid inlet, and the solver's tear
seeding transits two-phase solvent states on the lean line (light ends the
injected guess carries in); a pump-suction knockout drum was also tried and
rejected -- it separates the mixed solvent into phase-local streams that lose
the amine (the aqueous outlet comes back nearly pure water while the MDEA
lands in the hydrocarbon phase). The absorber's column conditions are set by
its gas feed regardless, and the overall-composition solvent handling both
amine units use is insensitive to the lean line's own pressure.

The tear is the cooled lean line S-003 into MIX-101 (smallest stream id on the
out-degree tie, and the one in-loop stream a unit consumes without inspecting
-- the mixer accepts whatever the injected guess carries, which makes the
solve robust to the seeding).

The sour gas is a moderately sour feed (3 mol% CO2, 300 ppmv H2S at 6.5 MPa)
sweetened to pipeline spec (2 mol% CO2, 4 ppmv H2S). The absorber's spec
floor check consumes the lean inlet it actually receives, so the first pass
is only feasible if the seeded blend (mean of the boundary feeds, mixed with
the make-up and trim) is clean enough -- the feed sourness level is what
makes the golden slice's first pass pass that check; deeper-sour feeds belong
behind a make-up/purge anchor sized for them, not behind this one.
"""

from __future__ import annotations

from ngdesign.contracts import Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.units.mdea_absorber import MdeaAbsorber

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
    """The sour-gas amine loop: 5 units, 11 streams, one lean-solvent recycle."""

    def p(u: str, port: str) -> PortRef:
        return PortRef(unit=u, port=port)

    makeup_lean = MdeaAbsorber.example_case()[0]["lean_amine_in"]

    units = [
        UnitSpec(tag="A-101", kind="mdea_absorber", params={}),
        UnitSpec(tag="R-101", kind="mdea_regenerator", params={}),
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
    return Flowsheet(name="sour-gas-amine-loop", units=units, streams=streams)
