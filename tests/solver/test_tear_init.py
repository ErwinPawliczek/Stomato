"""Spec P2-03: tears start from what actually enters their block.

The global-mean guess (pre-P2-03) averages every boundary feed. For a
flowsheet whose torn block sits downstream of another solved block, that
average is wrong twice: it blends in streams the block never sees, and it
blends at whole-sheet flows instead of the block's own. The fix seeds each
torn block from the molar-flow-weighted mean of its own entries -- boundary
feeds at their flashed spec plus already-solved upstream outlets.

The discriminator here is a two-block sheet whose blocks carry very different
recipes: a big gas block (N2/H2O at 100 mol/s) and a downstream loop block
that mixes the gas block's 10%-slipstream with a small pure-TEG make-up feed.
The loop block's own entries are ~half TEG (10 mol/s TEG against 10 mol/s
gas); the whole-sheet feed mean is ~9% TEG. Per-block seeding hands the tear
the 50%-TEG guess; the sheet has no amine units, so nothing else moves the
composition -- the assert is on ``_init_guess`` itself (tests/solver may reach
the seam; the P2-01 warm start takes precedence only when a design-spec run
asks for one, which this sheet has none of).

The fractions above are exact bookkeeping on the splitter fractions, so the
asserts pin them exactly; the flash sweep uses the real pr thermo plugin.
"""

from __future__ import annotations

from ngdesign import registry
from ngdesign.contracts import Flowsheet, PortRef, StreamSpec, StreamState, UnitSpec
from ngdesign.contracts.plugins import Thermo
from ngdesign.solver.sequential_modular import SequentialModular, _init_guess

COMPONENTS = ("N2", "H2O", "TEG")


def _two_block(*, with_block_two: bool) -> Flowsheet:
    """Gas block (heater + splitter) and, optionally, the TEG loop block.

    The loop block recycles half of its own outlet: MIX-201 -> HT-201 ->
    SPL-201, outlet_2 back to MIX-201.inlet_2 -- one tear (the solver picks
    S-201, the smallest in-loop stream id on the out-degree tie).
    """

    def p(u: str, port: str) -> PortRef:
        return PortRef(unit=u, port=port)

    units = [
        UnitSpec(tag="HT-101", kind="heater", params={"T_out": 350.0, "dP": 0.0}),
        UnitSpec(tag="SPL-101", kind="splitter", params={"fractions": [0.9, 0.1]}),
    ]
    streams = [
        StreamSpec(
            id="S-101",
            target=p("HT-101", "inlet"),
            service="PG",
            feed={"T": 300.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"N2": 0.98, "H2O": 0.02}},
        ),
        StreamSpec(id="S-102", source=p("HT-101", "outlet"), target=p("SPL-101", "inlet"), service="PG"),
        StreamSpec(id="S-103", source=p("SPL-101", "outlet_1"), service="PG"),
    ]
    if not with_block_two:
        # The slipstream becomes a product when the loop block is absent.
        streams.append(StreamSpec(id="S-104", source=p("SPL-101", "outlet_2"), service="PG"))
    if with_block_two:
        units += [
            UnitSpec(tag="MIX-201", kind="mixer", params={}),
            UnitSpec(tag="HT-201", kind="heater", params={"T_out": 330.0, "dP": 0.0}),
            UnitSpec(tag="SPL-201", kind="splitter", params={"fractions": [0.5, 0.5]}),
        ]
        streams += [
            StreamSpec(
                id="S-104", source=p("SPL-101", "outlet_2"), target=p("MIX-201", "inlet_1"), service="PG"
            ),
            StreamSpec(
                id="S-105",
                target=p("MIX-201", "inlet_3"),
                service="PL",
                feed={"T": 300.0, "P": 1.0e6, "molar_flow": 10.0, "composition": {"TEG": 1.0}},
            ),
            StreamSpec(id="S-201", source=p("MIX-201", "outlet"), target=p("HT-201", "inlet"), service="PL"),
            StreamSpec(id="S-202", source=p("HT-201", "outlet"), target=p("SPL-201", "inlet"), service="PL"),
            StreamSpec(id="S-203", source=p("SPL-201", "outlet_1"), service="PL"),
            StreamSpec(
                id="S-204", source=p("SPL-201", "outlet_2"), target=p("MIX-201", "inlet_2"), service="PL"
            ),
        ]
    return Flowsheet(name="tear-init-two-block", components=list(COMPONENTS), units=units, streams=streams)


def _flashed_states(thermo: Thermo) -> dict[str, StreamState]:
    """Feed states at their boundary spec, the way the solver flashes them."""
    states = {}
    fs = _two_block(with_block_two=True)
    for sid in ("S-101", "S-105"):
        stream = next(s for s in fs.streams if s.id == sid)
        assert stream.feed is not None
        states[sid] = thermo.flash_pt(
            dict(stream.feed.composition), stream.feed.T, stream.feed.P, stream.feed.molar_flow
        )
    return states


def test_block_guess_uses_block_entries() -> None:
    """The loop block's tear seed is its own 50%-TEG reality, not the sheet's 9%."""
    thermo = registry.create("thermo", "pr")
    fs = _two_block(with_block_two=True)

    # The gas block's outlet state: solve the acyclic part through the public API.
    solved = SequentialModular().solve(_two_block(with_block_two=False), thermo)
    assert solved.converged is True
    states = {"S-104": solved.streams["S-104"], **_flashed_states(thermo)}

    guess, _ = _init_guess(fs, COMPONENTS, block={"MIX-201", "HT-201", "SPL-201"}, states=states)
    flows = guess[: len(COMPONENTS)]
    total = sum(flows)
    assert abs(flows[2] / total - 0.5) < 1e-9, f"block guess should be 50% TEG, got {flows}"
    assert abs(flows[0] / total - 0.49) < 1e-9 and abs(flows[1] / total - 0.01) < 1e-9, (
        f"gas part should be the slipstream recipe, got {flows}"
    )

    global_guess, _ = _init_guess(fs, COMPONENTS)
    global_flows = global_guess[: len(COMPONENTS)]
    assert global_flows[2] == 10.0, f"the sheet-wide mean carries 10 mol/s TEG, got {global_flows}"
    assert global_flows[0] == 98.0 and global_flows[1] == 2.0, (
        f"the sheet-wide mean blends at whole-sheet flows, got {global_flows}"
    )


def test_two_block_solve_pins_first_record() -> None:
    """The full sheet solves in two blocks; the tear's first record is the seed's."""
    thermo = registry.create("thermo", "pr")
    solved = SequentialModular().solve(_two_block(with_block_two=True), thermo)
    assert solved.converged is True
    assert solved.errors == []
    # Two acyclic singleton blocks (HT-101, SPL-101) plus the one torn loop block.
    assert len(solved.history) == 3
    assert sum(1 for b in solved.history if not b.tears) == 2
    torn = [b for b in solved.history if b.tears]
    assert len(torn) == 1
    block = torn[0]
    assert block.tears == ["S-201"]
    assert block.converged is True
    first = block.records[0]
    assert first.acceleration == "direct"
    assert first.q is None
    assert set(first.residual_vector) == {"T", "P", *COMPONENTS}
