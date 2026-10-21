"""B-08 acceptance: POST /api/agent over SSE with an injected ScriptedModel.

The F-08 frontend contract, asserted frame by frame: ``data: {json}`` frames of
``text_delta``, ``tool_call``, ``tool_result``, ``project_changed``, then a final
``done`` carrying ``conversation_id``/``stop_reason``/``usage`` — or ``error``.
Session identity lives in the route: an unknown ``conversation_id`` is 404, the
transcript endpoint replays the Anthropic-shaped history, DELETE forgets it.
No test touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ngdesign.agent.model import ModelResponse, ScriptedModel, TextSink, ToolUseRequest
from ngdesign.api import routes_agent
from ngdesign.api.app import app

c = TestClient(app)


@pytest.fixture(autouse=True)
def _agent_isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fresh session table and a never-real model per test.

    The empty scripted model is the safety net: a test that forgets to inject
    its own script gets the loop's "script exhausted" error event, never a
    network call.
    """
    routes_agent.reset_sessions()
    monkeypatch.delenv("STOMATO_AGENT_MODE", raising=False)
    routes_agent.set_model(ScriptedModel(script=[]))
    assert c.post("/api/project/reset").status_code == 200
    yield
    routes_agent.reset_sessions()


def _text_turn(text: str, *, start_id: int = 0) -> list[ModelResponse]:
    """One scripted end_turn response."""
    return [
        ModelResponse(
            text=text,
            tool_uses=(),
            stop_reason="end_turn",
            input_tokens=10 + start_id,
            output_tokens=5 + start_id,
        )
    ]


def _post_sse(body: dict[str, Any]) -> list[dict[str, Any]]:
    """POST /api/agent and parse the SSE frames into event dicts."""
    response = c.post("/api/agent", json=body)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events: list[dict[str, Any]] = []
    for frame in response.text.split("\n\n"):
        if frame.startswith("data: "):
            events.append(json.loads(frame[len("data: ") :]))
    return events


def test_stream_ends_with_done_and_the_transcript_replays_history() -> None:
    routes_agent.set_model(ScriptedModel(script=_text_turn("Hello, engineer.")))
    events = _post_sse({"message": "hi"})

    assert [e["type"] for e in events] == ["text_delta", "done"]
    assert events[0]["text"] == "Hello, engineer."
    done = events[-1]
    assert done["stop_reason"] == "end_turn"
    assert done["usage"] == {"input_tokens": 10, "output_tokens": 5}
    conversation_id = done["conversation_id"]
    assert isinstance(conversation_id, str) and conversation_id

    listed = c.get("/api/agent").json()
    assert conversation_id in listed["conversations"]

    transcript = c.get(f"/api/agent/{conversation_id}").json()
    assert transcript["conversation_id"] == conversation_id
    assert [m["role"] for m in transcript["messages"]] == ["user", "assistant"]
    assert transcript["messages"][1]["content"] == [{"type": "text", "text": "Hello, engineer."}]

    assert c.delete(f"/api/agent/{conversation_id}").json() == {"deleted": conversation_id}
    assert c.get(f"/api/agent/{conversation_id}").status_code == 404
    assert c.delete(f"/api/agent/{conversation_id}").status_code == 404


def test_stream_carries_tool_rounds_and_project_changed() -> None:
    routes_agent.set_model(
        ScriptedModel(
            script=[
                ModelResponse(
                    text="Adding the vessel.",
                    tool_uses=(
                        ToolUseRequest(
                            id="t1",
                            name="add_unit",
                            input={"tag": "V-999", "kind": "separator_3phase", "params": {}},
                        ),
                    ),
                    stop_reason="tool_use",
                    input_tokens=8,
                    output_tokens=4,
                ),
                _text_turn("The vessel is in.", start_id=5)[0],
            ]
        )
    )
    events = _post_sse({"message": "add a vessel"})

    assert [e["type"] for e in events] == [
        "text_delta",
        "tool_call",
        "tool_result",
        "project_changed",
        "text_delta",
        "done",
    ]
    call = events[1]
    assert call["name"] == "add_unit" and call["input"]["tag"] == "V-999"
    result = events[2]
    assert result["ok"] is True and "V-999" in result["summary"]
    assert events[-1]["usage"] == {"input_tokens": 23, "output_tokens": 14}
    # The transcript keeps the tool exchange in Anthropic API shape.
    transcript = c.get(f"/api/agent/{events[-1]['conversation_id']}").json()
    assert [m["role"] for m in transcript["messages"]] == ["user", "assistant", "user", "assistant"]
    result_blocks = transcript["messages"][2]["content"]
    assert [b["type"] for b in result_blocks] == ["tool_result"]
    assert "V-999" in result_blocks[0]["content"]


def test_unknown_conversation_id_is_404_and_empty_message_422() -> None:
    response = c.post("/api/agent", json={"message": "hi", "conversation_id": "nope"})
    assert response.status_code == 404
    assert "unknown conversation_id" in response.json()["detail"]

    response = c.post("/api/agent", json={"message": "   "})
    assert response.status_code == 422


def test_second_post_with_the_conversation_id_continues_the_history() -> None:
    model = ScriptedModel(script=[*_text_turn("first"), *_text_turn("second")])
    routes_agent.set_model(model)

    first = _post_sse({"message": "one"})
    conversation_id = first[-1]["conversation_id"]
    second = _post_sse({"message": "two", "conversation_id": conversation_id})
    assert second[-1]["conversation_id"] == conversation_id

    transcript = c.get(f"/api/agent/{conversation_id}").json()
    assert [m["role"] for m in transcript["messages"]] == ["user", "assistant", "user", "assistant"]
    assert transcript["messages"][2]["content"] == "two"
    # The model's second turn saw the whole first exchange.
    _, second_turn_messages, _ = model.calls[1]
    assert [m["role"] for m in second_turn_messages] == ["user", "assistant", "user"]


def test_a_failing_model_becomes_an_error_event_never_a_hang() -> None:
    class ExplodingModel:
        def stream(
            self,
            system: str,
            messages: list[dict[str, Any]],
            tools: list[dict[str, Any]],
            on_text: TextSink,
        ) -> ModelResponse:
            raise RuntimeError("boom")

    routes_agent.set_model(ExplodingModel())
    events = _post_sse({"message": "hi"})

    assert [e["type"] for e in events] == ["error"]
    assert "boom" in events[0]["message"]


def test_scripted_env_mode_serves_the_demo_script(monkeypatch: pytest.MonkeyPatch) -> None:
    """``STOMATO_AGENT_MODE=scripted`` swaps in the deterministic demo model."""
    monkeypatch.setenv("STOMATO_AGENT_MODE", "scripted")
    model = routes_agent.get_model()
    assert isinstance(model, ScriptedModel)
    assert [use.name for response in model.script for use in response.tool_uses] == [
        "solve",
        "read_variable",
        "render",
    ]
