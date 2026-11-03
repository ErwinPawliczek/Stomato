"""'Trace demo: gas processing' - a small gas-plant front end for provenance review.

Inlet cooling, a two-inlet flash drum, an NGL pump, heater, let-down valve and
shortcut deethanizer on the hydrocarbon liquid, and a compressor with aftercooler
and anti-surge recycle (splitter -> JT valve -> suction mixer) on the vapour:

- S-001 well gas -> E-101 cooler -> S-003 -> V-101 flash drum (inlet_2: S-002 condensate)
- V-101 gas S-004 -> M-101 mixer (also S-007 lean gas, S-014 recycle) -> S-008
- S-008 -> K-101 compressor -> S-009 -> E-102 air cooler -> S-010 -> X-101 splitter
- X-101 -> S-011 sales gas; X-101 -> S-012 -> V-102 JT valve -> S-014 recycle to M-101
- V-101 HC liquid S-005 -> P-101 pump -> S-015 -> E-103 heater -> S-013
- S-013 -> V-103 let-down valve -> S-016 -> T-101 deethanizer (shortcut FUG column,
  keys C2/C3) -> S-017 overhead, S-018 C3+ NGL
- V-101 water S-006 (product)

Every component (N2, CO2, C1-C5, n-hexane for C6+, water) takes its EOS constants
and ideal-gas Cp from cited data sets (REFPROP critical constants, thermo HEOS_FIT
Cp fits), so the trace audits clean apart from model defaults the flowsheet leaves
unset on purpose. Feed conditions are user inputs; nothing here is plant data.
"""

from __future__ import annotations

from ngdesign.contracts import Flowsheet
from ngdesign.contracts.flowsheet import FeedSpec, PortRef, StreamSpec, UnitSpec

NAME = "Trace demo: gas processing"

#: Wet sweet well gas (mole fractions, user input).
WELL_GAS = {
    "N2": 0.010,
    "CO2": 0.020,
    "C1": 0.780,
    "C2": 0.080,
    "C3": 0.045,
    "iC4": 0.010,
    "nC4": 0.015,
    "iC5": 0.006,
    "nC5": 0.006,
    "C6+": 0.006,
    "H2O": 0.022,
}
#: Condensate from the slug catcher (user input).
CONDENSATE = {
    "C1": 0.150,
    "C2": 0.080,
    "C3": 0.150,
    "iC4": 0.080,
    "nC4": 0.150,
    "iC5": 0.100,
    "nC5": 0.110,
    "C6+": 0.180,
}
#: Lean gas from a neighbouring train (user input).
LEAN_GAS = {"N2": 0.015, "CO2": 0.010, "C1": 0.900, "C2": 0.055, "C3": 0.020}


def _p(unit: str, port: str) -> PortRef:
    return PortRef(unit=unit, port=port)


def build() -> Flowsheet:
    """The demo flowsheet (PR EOS; SI units)."""
    units = [
        UnitSpec(tag="E-101", kind="cooler", params={"T_out": 278.15, "dP": 30e3}),
        UnitSpec(tag="V-101", kind="flash_drum", params={}),
        UnitSpec(tag="M-101", kind="mixer", params={}),
        UnitSpec(tag="K-101", kind="compressor", params={"P_out": 8.0e6, "eta_isentropic": 0.78}),
        UnitSpec(tag="E-102", kind="air_cooler", params={"T_out": 308.15, "dP": 50e3}),
        UnitSpec(tag="X-101", kind="splitter", params={"fractions": [0.9, 0.1]}),
        UnitSpec(tag="V-102", kind="jt_valve", params={"P_out": 5.9e6}),
        UnitSpec(tag="P-101", kind="pump", params={"P_out": 7.0e6, "eta": 0.70}),
        UnitSpec(tag="E-103", kind="heater", params={"T_out": 313.15, "dP": 20e3}),
        UnitSpec(tag="V-103", kind="jt_valve", params={"P_out": 2.6e6}),
        UnitSpec(
            tag="T-101",
            kind="shortcut_distillation",
            params={
                "light_key": "C2",
                "heavy_key": "C3",
                "recovery_LK_D": 0.98,
                "recovery_HK_B": 0.98,
                "R_over_Rmin": 1.3,
                "P_top": 2.6e6,
                "P_bottom": 2.65e6,
                "condenser": "partial",
            },
        ),
    ]
    streams = [
        StreamSpec(
            id="S-001",
            target=_p("E-101", "inlet"),
            service="PG",
            feed=FeedSpec(T=308.15, P=6.0e6, molar_flow=500.0, composition=WELL_GAS),
        ),
        StreamSpec(
            id="S-002",
            target=_p("V-101", "inlet_2"),
            service="PL",
            feed=FeedSpec(T=290.15, P=5.97e6, molar_flow=20.0, composition=CONDENSATE),
        ),
        StreamSpec(id="S-003", source=_p("E-101", "outlet"), target=_p("V-101", "inlet"), service="PG"),
        StreamSpec(id="S-004", source=_p("V-101", "gas_out"), target=_p("M-101", "inlet_1"), service="PG"),
        StreamSpec(id="S-005", source=_p("V-101", "liquid_out"), target=_p("P-101", "inlet"), service="PL"),
        StreamSpec(id="S-006", source=_p("V-101", "aqueous_out"), service="W"),
        StreamSpec(
            id="S-007",
            target=_p("M-101", "inlet_2"),
            service="PG",
            feed=FeedSpec(T=300.15, P=5.95e6, molar_flow=150.0, composition=LEAN_GAS),
        ),
        StreamSpec(id="S-008", source=_p("M-101", "outlet"), target=_p("K-101", "inlet"), service="PG"),
        StreamSpec(id="S-009", source=_p("K-101", "outlet"), target=_p("E-102", "inlet"), service="PG"),
        StreamSpec(id="S-010", source=_p("E-102", "outlet"), target=_p("X-101", "inlet"), service="PG"),
        StreamSpec(id="S-011", source=_p("X-101", "outlet_1"), service="PG"),
        StreamSpec(id="S-012", source=_p("X-101", "outlet_2"), target=_p("V-102", "inlet"), service="PG"),
        StreamSpec(id="S-014", source=_p("V-102", "outlet"), target=_p("M-101", "inlet_3"), service="PG"),
        StreamSpec(id="S-015", source=_p("P-101", "outlet"), target=_p("E-103", "inlet"), service="PL"),
        StreamSpec(id="S-013", source=_p("E-103", "outlet"), target=_p("V-103", "inlet"), service="PL"),
        StreamSpec(id="S-016", source=_p("V-103", "outlet"), target=_p("T-101", "feed"), service="PL"),
        StreamSpec(id="S-017", source=_p("T-101", "distillate"), service="PG"),
        StreamSpec(id="S-018", source=_p("T-101", "bottoms"), service="PL"),
    ]
    return Flowsheet(name=NAME, units=units, streams=streams, thermo="pr")
