"""B-08 acceptance: the conversation loop with ScriptedModel — no network, no API.

1. A scripted session builds a 2-unit flowsheet (feed → separator → compressor)
   and solves it; the event sequence is asserted exactly.
2. Two tool calls in one assistant message produce ONE user message with two
   ``tool_result`` blocks.
3. A failing tool yields an error result the model's next turn sees.
4. The 25-round cap ends the turn with an ``error`` event.
5. The showcase: a scripted plan (MDEA absorber + TEG contactor + compressor on
   the sample sour gas) ends with a converged solve and both renders. It starts
   from an EMPTY project with an explicit slate — the sample slice's slate has
   no MDEA/TEG/H2S, and component ids come only from the curated slate plus the
   flowsheet's own slate.

The showcase plan derives every port, param and composition from the units'
own ``example_case()`` — the plugins stay the single source of truth.
"""

from __future__ import annotations

from typing import Any, Protocol, cast

from ngdesign import registry
from ngdesign.agent.engine import DEFAULT_ENGINE
from ngdesign.agent.loop import MAX_TOOL_ROUNDS, run_conversation
from ngdesign.agent.model import ModelResponse, ScriptedModel, ToolUseRequest
from ngdesign.contracts import Flowsheet, Project


class _Store:
    """In-memory ProjectStore for loop tests (the API injects the real one)."""

    def __init__(self, project: Project) -> None:
        self._project = project

    def get(self) -> Project:
        return self._project

    def put(self, project: Project) -> Project:
        self._project = project
        return project


def _blank_project(components: list[str]) -> Project:
    return Project(
        name="blank",
        flowsheet=Flowsheet(name="blank", units=[], streams=[], thermo="pr", components=components),
    )


def _response(
    text: str,
    calls: list[tuple[str, dict[str, Any]]],
    *,
    start_id: int = 0,
) -> ModelResponse:
    """One scripted assistant turn: streamed text plus ordered tool calls."""
    return ModelResponse(
        text=text,
        tool_uses=tuple(
            ToolUseRequest(id=f"call-{start_id + i}", name=name, input=call_input)
            for i, (name, call_input) in enumerate(calls)
        ),
        stop_reason="tool_use" if calls else "end_turn",
        input_tokens=10,
        output_tokens=5,
    )


def _run(model: ScriptedModel, store: _Store) -> tuple[Any, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    done = run_conversation(model, store, DEFAULT_ENGINE, "build it", [], events.append)
    return done, events


def test_scripted_session_builds_and_solves_a_2unit_flowsheet() -> None:
    store = _Store(_blank_project(["C1", "C2", "N2"]))
    model = ScriptedModel(
        script=[
            _response(
                "Adding the vessels.",
                [("add_unit", {"tag": "V-201", "kind": "separator_3phase", "params": {}})],
            ),
            _response(
                "Adding the compressor.",
                [
                    (
                        "add_unit",
                        {
                            "tag": "K-201",
                            "kind": "compressor",
                            "params": {"P_out": 7.0e6, "eta_isentropic": 0.75},
                        },
                    )
                ],
            ),
            _response(
                "Wiring the train.",
                [
                    (
                        "add_feed",
                        {
                            "stream_id": "F-201",
                            "target_unit": "V-201",
                            "target_port": "inlet",
                            "T_K": 303.15,
                            "P_Pa": 5.0e6,
                            "molar_flow_mol_s": 50.0,
                            "composition": {"C1": 0.9, "C2": 0.05, "N2": 0.05},
                        },
                    ),
                    (
                        "connect",
                        {
                            "stream_id": "S-201",
                            "source_unit": "V-201",
                            "source_port": "gas_out",
                            "target_unit": "K-201",
                            "target_port": "inlet",
                        },
                    ),
                    ("connect", {"stream_id": "S-202", "source_unit": "K-201", "source_port": "outlet"}),
                ],
                start_id=2,
            ),
            _response("Solving.", [("solve", {})], start_id=5),
            _response("Converged on the first pass.", [], start_id=6),
        ]
    )
    done, events = _run(model, store)

    # The event sequence, asserted exactly: text, then per round every tool_call
    # before its results, one project_changed per mutating round, final text.
    assert [e["type"] for e in events] == [
        "text_delta",
        "tool_call",
        "tool_result",
        "project_changed",
        "text_delta",
        "tool_call",
        "tool_result",
        "project_changed",
        "text_delta",
        "tool_call",
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "tool_result",
        "project_changed",
        "text_delta",
        "tool_call",
        "tool_result",
        "text_delta",
    ]
    assert done.stop_reason == "end_turn"
    solved = next(e for e in events if e["type"] == "tool_result" and "converged" in (e.get("result") or {}))
    assert solved["result"]["converged"] is True
    assert [u.tag for u in store.get().flowsheet.units] == ["V-201", "K-201"]
    # Two rounds of accumulated usage.
    assert done.usage["input_tokens"] == 50


def test_two_tool_calls_in_one_message_get_one_user_message_with_two_results() -> None:
    store = _Store(_blank_project(["C1", "N2"]))
    model = ScriptedModel(
        script=[
            _response(
                "Two additions at once.",
                [
                    ("add_unit", {"tag": "V-201", "kind": "separator_3phase", "params": {}}),
                    ("add_unit", {"tag": "K-201", "kind": "compressor", "params": {}}),
                ],
            ),
            _response("Both are in.", [], start_id=2),
        ]
    )
    done, events = _run(model, store)

    assert done.stop_reason == "end_turn"
    assert [e["type"] for e in events].count("tool_call") == 2
    # The next model turn sees ONE user message carrying BOTH tool_result blocks
    # (the tool_use message's results always arrive together in one user turn).
    next_messages = model.calls[1][1]
    result_messages = [m for m in next_messages if m["role"] == "user" and isinstance(m["content"], list)]
    assert len(result_messages) == 1, next_messages
    blocks = result_messages[0]["content"]
    assert [b["type"] for b in blocks] == ["tool_result", "tool_result"]
    assert {b["tool_use_id"] for b in blocks} == {"call-0", "call-1"}


def test_failing_tool_is_visible_to_the_model_next_turn() -> None:
    store = _Store(_blank_project(["C1"]))
    model = ScriptedModel(
        script=[
            _response(
                "Trying an unregistered kind.",
                [("add_unit", {"tag": "X-101", "kind": "no_such_unit", "params": {}})],
            ),
            _response("Recovering.", [], start_id=1),
        ]
    )
    done, events = _run(model, store)

    assert done.stop_reason == "end_turn"
    failed = [e for e in events if e["type"] == "tool_result" and not e["ok"]]
    assert len(failed) == 1 and "no_such_unit" in failed[0]["summary"]
    # The model's next turn sees the error text in the tool_result block.
    next_messages = model.calls[1][1]
    blocks = next_messages[-1]["content"]
    assert blocks[0]["type"] == "tool_result"
    assert "no_such_unit" in blocks[0]["content"]
    # And the project never gained the unit.
    assert store.get().flowsheet.units == []


def test_round_cap_ends_with_an_error_event() -> None:
    store = _Store(_blank_project(["C1"]))
    model = ScriptedModel(
        script=[
            _response(f"round {i}", [("list_unit_kinds", {})], start_id=i) for i in range(MAX_TOOL_ROUNDS)
        ]
    )
    done, events = _run(model, store)

    assert done.stop_reason == "max_tool_rounds"
    assert events[-1]["type"] == "error"
    assert str(MAX_TOOL_ROUNDS) in events[-1]["message"]
    assert len(model.calls) == MAX_TOOL_ROUNDS


class _HasExampleCase(Protocol):
    """The registry returns bare types; tests need the unit plugins' example_case."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]: ...


def _showcase_script() -> list[ModelResponse]:
    """The scripted showcase plan, derived from the units' own example cases."""
    teg = cast(_HasExampleCase, registry.get("unit", "teg_contactor"))
    mdea = cast(_HasExampleCase, registry.get("unit", "mdea_absorber"))
    comp = cast(_HasExampleCase, registry.get("unit", "compressor"))
    teg_feeds, _ = teg.example_case()
    mdea_feeds, _ = mdea.example_case()
    _, comp_params = comp.example_case()

    def feed_call(
        stream_id: str, unit: str, port: str, spec: dict[str, Any], service: str
    ) -> tuple[str, dict[str, Any]]:
        return (
            "add_feed",
            {
                "stream_id": stream_id,
                "target_unit": unit,
                "target_port": port,
                "T_K": spec["T"],
                "P_Pa": spec["P"],
                "molar_flow_mol_s": spec["molar_flow"],
                "composition": spec["composition"],
                "service": service,
            },
        )

    sour_gas = dict(mdea_feeds["gas_in"])
    base = sour_gas["composition"]
    sour_gas["composition"] = {**base, "H2O": 0.02, "C1": base["C1"] - 0.02}
    return [
        _response(
            "Adding the dehydration, sweetening and compression units.",
            [
                ("add_unit", {"tag": "T-201", "kind": "teg_contactor", "params": {}}),
                ("add_unit", {"tag": "M-201", "kind": "mdea_absorber", "params": {}}),
                ("add_unit", {"tag": "K-201", "kind": "compressor", "params": dict(comp_params)}),
            ],
        ),
        _response(
            "Feeding the water-saturated sour gas and the lean TEG.",
            [
                feed_call("F-GAS", "T-201", "gas_in", sour_gas, "PG"),
                feed_call("F-TEG", "T-201", "lean_teg_in", teg_feeds["lean_teg_in"], "GL"),
            ],
            start_id=3,
        ),
        _response(
            "Routing the dried gas into the MDEA absorber and on to the compressor.",
            [
                (
                    "connect",
                    {
                        "stream_id": "S-TM",
                        "source_unit": "T-201",
                        "source_port": "gas_out",
                        "target_unit": "M-201",
                        "target_port": "gas_in",
                        "service": "PG",
                    },
                ),
                feed_call("F-LEAN", "M-201", "lean_amine_in", mdea_feeds["lean_amine_in"], "PL"),
                (
                    "connect",
                    {
                        "stream_id": "S-MK",
                        "source_unit": "M-201",
                        "source_port": "gas_out",
                        "target_unit": "K-201",
                        "target_port": "inlet",
                        "service": "PG",
                    },
                ),
                (
                    "connect",
                    {
                        "stream_id": "S-PROD",
                        "source_unit": "K-201",
                        "source_port": "outlet",
                        "service": "PG",
                    },
                ),
                ("set_thermo", {"name": "amine_ke"}),
            ],
            start_id=5,
        ),
        _response("Solving the full train.", [("solve", {})], start_id=10),
        _response(
            "Rendering both drawings.",
            [("render", {"view": "pfd"}), ("render", {"view": "pid"})],
            start_id=11,
        ),
        _response("The train converges; both drawings are on the URLs above.", [], start_id=13),
    ]


def test_scripted_showcase_converges_and_renders() -> None:
    """Sour gas → TEG contactor → MDEA absorber → compressor, solved and rendered.

    Dehydration precedes amine treating here because the MDEA absorber emits
    water-free gas: a TEG contactor AFTER it would see an infeasible water spec
    (inlet water content 0 lb/MMscf). The slate is explicit: the slice's slate
    has no MDEA/TEG/H2S.
    """
    slate = ["C1", "C2", "C3", "N2", "CO2", "H2S", "MDEA", "H2O", "TEG"]
    store = _Store(_blank_project(slate))
    model = ScriptedModel(script=_showcase_script())
    done, events = _run(model, store)

    assert done.stop_reason == "end_turn"
    solved = next(e for e in events if e["type"] == "tool_result" and "converged" in (e.get("result") or {}))
    assert solved["result"]["converged"] is True
    assert sorted(solved["result"]["units"]) == ["K-201", "M-201", "T-201"]
    renders = [e for e in events if e["type"] == "tool_result" and e.get("result", {}).get("url")]
    assert [e["result"]["url"] for e in renders] == ["/api/views/pfd.svg", "/api/views/pid.svg"]
    assert all(e["result"]["units"] >= 3 for e in renders)
    tags = [u.tag for u in store.get().flowsheet.units]
    assert tags == ["T-201", "M-201", "K-201"]
    # The failed-tool channel stayed silent: every tool call succeeded.
    assert not [e for e in events if e["type"] == "tool_result" and not e["ok"]]
