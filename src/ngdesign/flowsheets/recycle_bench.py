"""Recycle-heavy benchmark flowsheet for OQ-3 (topology + specs only, no results).

The locked slice (``flowsheets/slice.py``) is acyclic, so the sequential-modular
solver's tear + Wegstein convergence work is never exercised. This companion
case keeps the slice's feed basis and gas-train physics but adds three recycle
loops that merge into one strongly connected component, making tear selection,
tear injection and Wegstein acceleration a measurable share of solve time:

    V-201 inlet scrubber -> MIX-201 suction mixer -> V-205 suction knockout
      -> K-201 compressor -> E-201 air cooler -> V-203 discharge separator
      -> T-201 TEG contactor -> SPL-204 -+-> MIX-205 chiller-feed mixer
          ^                              |     -> E-202 chiller -> V-204 cold
          |                              |        separator -> SPL-207
          |                              |          +-> SPL-210 -+-> sales gas
          |                              |          |            '-> E-215 preheater
          |                              |          '-> E-213 preheater   -> VLV-212
          |                              |            -> V-206 booster      -> MIX-201
          |                              |               knockout -> K-202
          |                              |               booster -> MIX-205
          |                              '-> (make-up gas feed, 6.9 MPa)
    V-204 and V-203 liquids -> NGL / water products

Recycle loops (all inside one SCC, so tear iteration covers the whole block):

- Loop A (S-216): 30% of dried gas from SPL-204 back to the suction mixer -
  compressor anti-surge style recycle.
- Loop B (S-223): 35% of cold-separator gas from SPL-207, warmed by E-213,
  through the K-202 booster back to MIX-205 - chilled-recycle compression.
- Loop C (S-231): 10% of the sales path from SPL-210, reheated by E-215 and
  let down by VLV-212 back to the suction mixer - plant recirculation; it
  couples both sections into one SCC (deliberate stress for the tear
  heuristic).

Recirculated flow is roughly 2.5x the boundary feed, so most of each pass
runs inside recycle units.

Well-posedness under tear iteration (why the knockouts, the make-up feed and
the preheaters are shaped the way they are):

- The solver's greedy tear pick can tear any stream whose source has the
  highest out-degree in a cycle, and the injected tear guess is the fed-mean
  state (two-phase here). Only compressors raise on two-phase inlets, so
  V-205 and V-206 sit directly ahead of K-201 and K-202: a separator's
  gas_out is always re-flashed single-phase vapor, which makes the solve
  robust to any tear choice.
- Separators re-flash each phase at their own (T, P). Near a phase boundary
  that re-flash can tip (a saturated vapor condensing), so no cold separator
  vapor reaches a compressor unheated: E-213 warms the chilled recycle to
  45 C and E-215 warms the letdown stream to 60 C - both far superheated at
  their pressures, mirroring suction preheat practice. (At the 243 K chiller
  the PR plugin's cached three-phase flasher can also miss the hydrocarbon
  liquid root entirely, so V-204's condensate outlets may stay near zero;
  the loops above carry gas and do not depend on condensation.)
- A tear stream whose pressure reaches a mixer's min-pressure rule maps back
  to itself offset by the in-loop dP (y = x - dP): its Wegstein secant is
  exactly 1.0, a degenerate case. Every recycle here therefore re-enters at
  a unit SETPOINT (VLV-212 3.6 MPa) or from a setpoint-anchored separator,
  and both mixer minimum pressures are pinned by boundary feeds (3.447 MPa
  wet gas, 6.9 MPa make-up) and compressor setpoints (7.0/7.2 MPa), never by
  a tear.

Basis: identical to the locked slice - 50 MMSCFD rich wet sweet gas at
3.447 MPa / 20 C (same composition and conversion constant, imported from
``flowsheets/slice.py``) plus a small 2.5 MMSCFD dry make-up stream needed to
anchor MIX-205's pressure - so recycle vs no-recycle solve cost is a clean
comparison. This is a benchmark case, not a plant design.
"""

from __future__ import annotations

from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.flowsheets.slice import INLET_COMPOSITION, LEAN_TEG_COMPOSITION, MMSCFD_TO_MOL_S

#: Lean TEG circulation to T-201, mol/s (slice S-006 basis).
LEAN_TEG_MOLAR_FLOW = 3.2

#: Make-up gas to MIX-205, mol/s (2.5 MMSCFD, dry residue-gas composition).
MAKEUP_MOLAR_FLOW = 2.5 * MMSCFD_TO_MOL_S

_dry_total = sum(x for cid, x in INLET_COMPOSITION.items() if cid != "H2O")
#: Dry residue-gas composition: the slice feed without free water, renormalized.
MAKEUP_COMPOSITION = {cid: x / _dry_total for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}


def build() -> Flowsheet:
    """The recycle-heavy benchmark flowsheet: 18 units, 32 streams, 3 loops."""

    def p(u: str, port: str) -> PortRef:
        return PortRef(unit=u, port=port)

    units = [
        UnitSpec(tag="V-201", kind="scrubber", params={}),
        UnitSpec(tag="MIX-201", kind="mixer", params={}),
        UnitSpec(tag="V-205", kind="scrubber", params={}),
        UnitSpec(tag="K-201", kind="compressor", params={"P_out": 7.0e6, "eta_isentropic": 0.75}),
        UnitSpec(tag="E-201", kind="air_cooler", params={"T_out": 322.15}),
        UnitSpec(tag="V-203", kind="separator_3phase", params={}),
        UnitSpec(tag="T-201", kind="teg_contactor", params={"water_out_lb_per_mmscf": 7.0}),
        UnitSpec(tag="SPL-204", kind="splitter", params={"fractions": [0.70, 0.30]}),
        UnitSpec(tag="MIX-205", kind="mixer", params={}),
        UnitSpec(
            tag="E-202",
            kind="shell_tube",
            params={"T_out": 243.15, "dP": 50e3, "utility_T_in": 233.15, "utility_T_out": 253.15},
        ),
        UnitSpec(tag="V-204", kind="separator_3phase", params={}),
        UnitSpec(tag="SPL-207", kind="splitter", params={"fractions": [0.65, 0.35]}),
        UnitSpec(tag="E-213", kind="heater", params={"T_out": 318.15, "dP": 0.0}),
        UnitSpec(tag="V-206", kind="scrubber", params={}),
        UnitSpec(tag="K-202", kind="compressor", params={"P_out": 7.2e6, "eta_isentropic": 0.75}),
        UnitSpec(tag="SPL-210", kind="splitter", params={"fractions": [0.90, 0.10]}),
        UnitSpec(tag="E-215", kind="heater", params={"T_out": 333.15, "dP": 0.0}),
        UnitSpec(tag="VLV-212", kind="jt_valve", params={"P_out": 3.6e6}),
    ]
    streams = [
        StreamSpec(
            id="S-201",
            target=p("V-201", "inlet"),
            service="PG",
            feed=FeedSpec(
                T=293.15, P=3.447e6, molar_flow=50 * MMSCFD_TO_MOL_S, composition=INLET_COMPOSITION
            ),
        ),
        StreamSpec(id="S-202", source=p("V-201", "gas_out"), target=p("MIX-201", "inlet_1"), service="PG"),
        StreamSpec(id="S-203", source=p("V-201", "liquid_out"), service="W"),
        StreamSpec(id="S-204", source=p("MIX-201", "outlet"), target=p("V-205", "inlet"), service="PG"),
        StreamSpec(id="S-205", source=p("V-205", "gas_out"), target=p("K-201", "inlet"), service="PG"),
        StreamSpec(id="S-206", source=p("V-205", "liquid_out"), service="W"),
        StreamSpec(id="S-207", source=p("K-201", "outlet"), target=p("E-201", "inlet"), service="PG"),
        StreamSpec(id="S-208", source=p("E-201", "outlet"), target=p("V-203", "inlet"), service="PG"),
        StreamSpec(id="S-209", source=p("V-203", "gas_out"), target=p("T-201", "gas_in"), service="PG"),
        StreamSpec(id="S-210", source=p("V-203", "hc_out"), service="PL"),
        StreamSpec(id="S-211", source=p("V-203", "water_out"), service="W"),
        StreamSpec(id="S-212", source=p("T-201", "gas_out"), target=p("SPL-204", "inlet"), service="PG"),
        StreamSpec(id="S-213", source=p("T-201", "rich_teg_out"), service="GL"),
        StreamSpec(
            id="S-214",
            target=p("T-201", "lean_teg_in"),
            service="GL",
            feed=FeedSpec(
                T=325.15, P=7.1e6, molar_flow=LEAN_TEG_MOLAR_FLOW, composition=LEAN_TEG_COMPOSITION
            ),
        ),
        StreamSpec(id="S-215", source=p("SPL-204", "outlet_1"), target=p("MIX-205", "inlet_1"), service="PG"),
        StreamSpec(id="S-216", source=p("SPL-204", "outlet_2"), target=p("MIX-201", "inlet_2"), service="PG"),
        StreamSpec(id="S-217", source=p("MIX-205", "outlet"), target=p("E-202", "inlet"), service="PG"),
        StreamSpec(id="S-218", source=p("E-202", "outlet"), target=p("V-204", "inlet"), service="PG"),
        StreamSpec(id="S-219", source=p("V-204", "gas_out"), target=p("SPL-207", "inlet"), service="PG"),
        StreamSpec(id="S-220", source=p("V-204", "hc_out"), service="PL"),
        StreamSpec(id="S-221", source=p("V-204", "water_out"), service="W"),
        StreamSpec(id="S-222", source=p("SPL-207", "outlet_1"), target=p("SPL-210", "inlet"), service="PG"),
        StreamSpec(id="S-223", source=p("SPL-207", "outlet_2"), target=p("E-213", "inlet"), service="PG"),
        StreamSpec(id="S-224", source=p("E-213", "outlet"), target=p("V-206", "inlet"), service="PG"),
        StreamSpec(id="S-225", source=p("V-206", "gas_out"), target=p("K-202", "inlet"), service="PG"),
        StreamSpec(id="S-226", source=p("V-206", "liquid_out"), service="W"),
        StreamSpec(id="S-227", source=p("K-202", "outlet"), target=p("MIX-205", "inlet_2"), service="PG"),
        StreamSpec(id="S-228", source=p("SPL-210", "outlet_1"), service="PG"),
        StreamSpec(id="S-229", source=p("SPL-210", "outlet_2"), target=p("E-215", "inlet"), service="PG"),
        StreamSpec(id="S-230", source=p("E-215", "outlet"), target=p("VLV-212", "inlet"), service="PG"),
        StreamSpec(id="S-231", source=p("VLV-212", "outlet"), target=p("MIX-201", "inlet_3"), service="PG"),
        StreamSpec(
            id="S-232",
            target=p("MIX-205", "inlet_3"),
            service="PG",
            feed=FeedSpec(T=293.15, P=6.9e6, molar_flow=MAKEUP_MOLAR_FLOW, composition=MAKEUP_COMPOSITION),
        ),
    ]
    return Flowsheet(name="recycle-bench", units=units, streams=streams)
