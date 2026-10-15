"""Own tests for the sequential-modular solver (spec S-30).

The fake unit models below exist to exercise solver topology (chain, split-and-remix,
recycle, non-convergence) without depending on any real unit plugin. They are pure
algebra on StreamState: flow-weighted mixing/splitting, a constant-dP heater, and a
fixed-draw consumer whose recycle loop has gain -1 (a period-2 oscillator that can
never converge). They emit single-pseudo-phase states (phases=[], vapor_fraction=1)
and are topology fixtures, not thermodynamic models.

Fakes are registered through the registry *inside a fixture* and removed afterwards:
the locked balance oracle snapshots registry.available("unit") at import time, so
fixture-timed registration never reaches it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import (
    FeedSpec,
    Flowsheet,
    PortRef,
    StreamSpec,
    StreamState,
    UnitResult,
    UnitSpec,
)
from ngdesign.contracts.plugins import Solver, Thermo
from ngdesign.flowsheets.slice import build as build_slice
from ngdesign.solver.sequential_modular import SequentialModular

#: Fake heat capacity for the fake heater, J/(mol.K).
CP_FAKE = 30.0

#: Kinds the slice flowsheet needs; the slice test skips until S-24..S-29 register them.
SLICE_KINDS = ("separator_3phase", "compressor", "air_cooler", "teg_contactor", "pump", "shell_tube")


class _FakeMixer:
    """Flow-weighted mix of two inlets at the minimum inlet pressure."""

    inlet_ports = ("in_a", "in_b")
    outlet_ports = ("out",)

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        comp: dict[str, float] = {}
        total = 0.0
        h = 0.0
        s = 0.0
        t_w = 0.0
        vf_w = 0.0
        p_min = float("inf")
        for state in inlets.values():
            n = state.molar_flow
            total += n
            for c, z in state.composition.items():
                comp[c] = comp.get(c, 0.0) + z * n
            h += state.enthalpy * n
            s += state.entropy * n
            t_w += state.T * n
            vf_w += state.vapor_fraction * n
            p_min = min(p_min, state.P)
        if total <= 0.0:
            first = next(iter(inlets.values()))
            out = first.model_copy(update={"molar_flow": 0.0, "vapor_fraction": 1.0, "phases": []})
            return UnitResult(outlets={"out": out})
        composition = {c: n / total for c, n in comp.items() if n > 0.0}
        out = StreamState(
            T=t_w / total,
            P=p_min,
            molar_flow=total,
            composition=composition,
            vapor_fraction=vf_w / total,
            enthalpy=h / total,
            entropy=s / total,
            phases=[],
        )
        return UnitResult(outlets={"out": out})


class _FakeSplitter:
    """Splits the inlet on a mole basis: fraction `f` to out_a, the rest to out_b."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out_a", "out_b")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        state = inlets["inlet"]
        f = float(params["f"])
        outlets: dict[str, StreamState] = {}
        for port, fraction in (("out_a", f), ("out_b", 1.0 - f)):
            outlets[port] = StreamState(
                T=state.T,
                P=state.P,
                molar_flow=fraction * state.molar_flow,
                composition=dict(state.composition),
                vapor_fraction=state.vapor_fraction,
                enthalpy=state.enthalpy,
                entropy=state.entropy,
                phases=[],
            )
        return UnitResult(outlets=outlets)


class _FakeHeater:
    """Raises stream temperature by dT (K) at constant pressure and composition."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        state = inlets["inlet"]
        d_t = float(params.get("dT", 0.0))
        out = StreamState(
            T=state.T + d_t,
            P=state.P,
            molar_flow=state.molar_flow,
            composition=dict(state.composition),
            vapor_fraction=state.vapor_fraction,
            enthalpy=state.enthalpy + CP_FAKE * d_t,
            entropy=state.entropy,
            phases=[],
        )
        return UnitResult(outlets={"outlet": out}, duty_W=state.molar_flow * CP_FAKE * d_t)


class _FakeDraw:
    """Fixed-draw consumer: returns max(draw - supplied, 0) - a gain -1 loop.

    The point of this unit is the non-convergence case: its recycle fixed point has
    secant slope -1, so bounded Wegstein clamps to direct substitution and the loop
    oscillates forever.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        state = inlets["inlet"]
        draw = float(params["draw"])
        out = StreamState(
            T=state.T,
            P=state.P,
            molar_flow=max(draw - state.molar_flow, 0.0),
            composition=dict(state.composition),
            vapor_fraction=state.vapor_fraction,
            enthalpy=state.enthalpy,
            entropy=state.entropy,
            phases=[],
        )
        return UnitResult(outlets={"outlet": out})


FAKES: dict[str, type] = {
    "fake_mixer": _FakeMixer,
    "fake_splitter": _FakeSplitter,
    "fake_heater": _FakeHeater,
    "fake_draw": _FakeDraw,
}


@pytest.fixture(autouse=True)
def _fake_units() -> Iterator[None]:
    """Register the fakes for the duration of each test and remove them afterwards.

    Unregistration reaches into the private registry store because there is no
    public unregister; fixture-timed registration keeps the fakes out of the
    locked balance oracle, which snapshots registry.available() at import time.
    """
    for name, cls in FAKES.items():
        registry.register("unit", name)(cls)
    yield
    for name in FAKES:
        registry._REGISTRY["unit"].pop(name, None)


def _port(unit: str, port: str) -> PortRef:
    return PortRef(unit=unit, port=port)


def _feed(flow: float) -> FeedSpec:
    return FeedSpec(T=300.0, P=1.0e6, molar_flow=flow, composition={"C1": 1.0})


def test_plugin_registered_and_satisfies_protocol() -> None:
    assert "sequential_modular" in registry.available("solver")
    assert isinstance(SequentialModular(), Solver)


def test_linear_chain_converges(thermo: Thermo) -> None:
    fs = Flowsheet(
        name="chain",
        units=[
            UnitSpec(tag="HTR-101", kind="fake_heater", params={"dT": 10.0}),
            UnitSpec(tag="HTR-102", kind="fake_heater", params={"dT": 5.0}),
        ],
        streams=[
            StreamSpec(id="S-001", target=_port("HTR-101", "inlet"), feed=_feed(100.0)),
            StreamSpec(id="S-002", source=_port("HTR-101", "outlet"), target=_port("HTR-102", "inlet")),
            StreamSpec(id="S-003", source=_port("HTR-102", "outlet")),
        ],
    )
    solved = SequentialModular().solve(fs, thermo)
    assert solved.converged
    assert solved.iterations == 1
    assert set(solved.streams) == {"S-001", "S-002", "S-003"}
    assert solved.streams["S-003"].T == pytest.approx(315.0)
    assert solved.streams["S-003"].molar_flow == pytest.approx(100.0)
    assert solved.streams["S-001"].phases  # feed was flashed, not copied
    assert solved.units["HTR-101"].duty_W == pytest.approx(100.0 * CP_FAKE * 10.0)


def test_split_and_remix_converges(thermo: Thermo) -> None:
    fs = Flowsheet(
        name="split-remix",
        units=[
            UnitSpec(tag="SPL-101", kind="fake_splitter", params={"f": 0.6}),
            UnitSpec(tag="HTR-101", kind="fake_heater", params={"dT": 10.0}),
            UnitSpec(tag="MIX-101", kind="fake_mixer"),
        ],
        streams=[
            StreamSpec(id="S-001", target=_port("SPL-101", "inlet"), feed=_feed(100.0)),
            StreamSpec(id="S-002", source=_port("SPL-101", "out_a"), target=_port("HTR-101", "inlet")),
            StreamSpec(id="S-003", source=_port("HTR-101", "outlet"), target=_port("MIX-101", "in_a")),
            StreamSpec(id="S-004", source=_port("SPL-101", "out_b"), target=_port("MIX-101", "in_b")),
            StreamSpec(id="S-005", source=_port("MIX-101", "out")),
        ],
    )
    solved = SequentialModular().solve(fs, thermo)
    assert solved.converged
    assert solved.iterations == 1
    out = solved.streams["S-005"]
    assert out.molar_flow == pytest.approx(100.0, rel=1e-9)
    assert out.T == pytest.approx(306.0, rel=1e-9)  # 0.6 * 310 + 0.4 * 300
    assert out.composition == {"C1": 1.0}


def test_recycle_loop_converges(thermo: Thermo) -> None:
    """Feed 100 mol/s loops back 40% of the mixed stream: x* = 200/3 mol/s.

    The heater in the loop lifts T by 5 K, so the tear converges on flows, T and P
    together: T_mix* = 303.333 K, T_recycle* = 308.333 K, and the loop closes with
    product flow exactly equal to the fresh feed.
    """
    fs = Flowsheet(
        name="recycle",
        units=[
            UnitSpec(tag="MIX-101", kind="fake_mixer"),
            UnitSpec(tag="HTR-101", kind="fake_heater", params={"dT": 5.0}),
            UnitSpec(tag="SPL-101", kind="fake_splitter", params={"f": 0.4}),
        ],
        streams=[
            StreamSpec(id="S-001", target=_port("MIX-101", "in_a"), feed=_feed(100.0)),
            StreamSpec(id="S-002", source=_port("SPL-101", "out_a"), target=_port("MIX-101", "in_b")),
            StreamSpec(id="S-003", source=_port("MIX-101", "out"), target=_port("HTR-101", "inlet")),
            StreamSpec(id="S-004", source=_port("HTR-101", "outlet"), target=_port("SPL-101", "inlet")),
            StreamSpec(id="S-005", source=_port("SPL-101", "out_b")),
        ],
    )
    solved = SequentialModular().solve(fs, thermo)
    assert solved.converged
    assert 1 < solved.iterations <= 100
    assert set(solved.units) == {"MIX-101", "HTR-101", "SPL-101"}
    recycle = solved.streams["S-002"]
    product = solved.streams["S-005"]
    assert recycle.molar_flow == pytest.approx(200.0 / 3.0, rel=1e-5)
    assert recycle.T == pytest.approx(303.3333 + 5.0, rel=1e-5)
    assert recycle.composition == {"C1": 1.0}
    assert product.molar_flow == pytest.approx(100.0, rel=1e-5)  # loop closes: product == feed
    assert product.T == pytest.approx(308.3333, rel=1e-5)  # splitter passes through the heater outlet


def test_non_converging_returns_flag_without_raising(thermo: Thermo) -> None:
    """A gain -1 recycle oscillates forever: 100 passes, converged=False, no raise."""
    fs = Flowsheet(
        name="oscillating",
        units=[
            UnitSpec(tag="MIX-101", kind="fake_mixer"),
            UnitSpec(tag="DRW-101", kind="fake_draw", params={"draw": 50.0}),
        ],
        streams=[
            StreamSpec(id="S-001", target=_port("MIX-101", "in_a"), feed=_feed(25.0)),
            StreamSpec(id="S-002", source=_port("DRW-101", "outlet"), target=_port("MIX-101", "in_b")),
            StreamSpec(id="S-003", source=_port("MIX-101", "out"), target=_port("DRW-101", "inlet")),
        ],
    )
    solved = SequentialModular().solve(fs, thermo)
    assert solved.converged is False
    assert solved.iterations == 100
    assert set(solved.streams) == {"S-001", "S-002", "S-003"}


def test_slice_converges_once_slice_units_exist(thermo: Thermo) -> None:
    """Spec S-30: the vertical slice solves once S-24..S-29 land. Skips until then."""
    missing = [kind for kind in SLICE_KINDS if kind not in registry.available("unit")]
    if missing:
        pytest.skip(f"slice unit kinds not registered yet: {missing}")
    solved = SequentialModular().solve(build_slice(), thermo)
    assert solved.converged
    assert set(solved.streams) == {s.id for s in solved.flowsheet.streams}
    assert set(solved.units) == {u.tag for u in solved.flowsheet.units}
