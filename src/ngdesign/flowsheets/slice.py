"""Vertical-slice flowsheet (topology + specs only, no results). Human-owned.

V-101 inlet 3-phase separator -> K-101 compressor -> E-101 air cooler -> T-101 TEG contactor
V-101 HC liquid -> P-101 pump -> E-102 shell-and-tube heater -> condensate product

Basis: 50 MMSCFD rich wet sweet gas, 500 psia (3.447 MPa), 20 C.
At these conditions PR gives vapor + HC liquid (~1.1 mol%) + free water (~0.2 mol%).
"""

from __future__ import annotations

from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

# Explicit re-exports: slice keeps being the import surface for the sample basis.
__all__ = ["INLET_COMPOSITION", "LEAN_TEG_COMPOSITION", "MMSCFD_TO_MOL_S"]

# 98.7 wt% TEG lean glycol -> mole fractions
LEAN_TEG_COMPOSITION = {"TEG": 0.9011, "H2O": 0.0989}


def build() -> Flowsheet:
    def p(u: str, port: str) -> PortRef:
        return PortRef(unit=u, port=port)

    units = [
        UnitSpec(tag="V-101", kind="separator_3phase", params={}),
        UnitSpec(tag="K-101", kind="compressor", params={"P_out": 7.0e6, "eta_isentropic": 0.75}),
        UnitSpec(tag="E-101", kind="air_cooler", params={"T_out": 322.15, "dP": 35e3}),
        UnitSpec(tag="T-101", kind="teg_contactor", params={"water_out_lb_per_mmscf": 7.0}),
        UnitSpec(tag="P-101", kind="jt_valve", params={"P_out": 1.5e6}),
        UnitSpec(
            tag="E-102",
            kind="shell_tube",
            params={"T_out": 333.15, "dP": 50e3, "utility_T_in": 422.0, "utility_T_out": 415.0},
        ),
    ]
    streams = [
        StreamSpec(
            id="S-001",
            target=p("V-101", "inlet"),
            service="PG",
            feed=FeedSpec(
                T=293.15, P=3.447e6, molar_flow=50 * MMSCFD_TO_MOL_S, composition=INLET_COMPOSITION
            ),
        ),
        StreamSpec(id="S-002", source=p("V-101", "gas_out"), target=p("K-101", "inlet"), service="PG"),
        StreamSpec(id="S-003", source=p("K-101", "outlet"), target=p("E-101", "inlet"), service="PG"),
        StreamSpec(id="S-004", source=p("E-101", "outlet"), target=p("T-101", "gas_in"), service="PG"),
        StreamSpec(id="S-005", source=p("T-101", "gas_out"), service="PG"),
        StreamSpec(
            id="S-006",
            target=p("T-101", "lean_teg_in"),
            service="GL",
            feed=FeedSpec(T=325.15, P=7.1e6, molar_flow=3.2, composition=LEAN_TEG_COMPOSITION),
        ),
        StreamSpec(id="S-007", source=p("T-101", "rich_teg_out"), service="GL"),
        StreamSpec(id="S-008", source=p("V-101", "hc_out"), target=p("P-101", "inlet"), service="PL"),
        StreamSpec(id="S-009", source=p("P-101", "outlet"), target=p("E-102", "inlet"), service="PL"),
        StreamSpec(id="S-010", source=p("E-102", "outlet"), service="PL"),
        StreamSpec(id="S-011", source=p("V-101", "water_out"), service="W"),
    ]
    return Flowsheet(name="slice", units=units, streams=streams)
