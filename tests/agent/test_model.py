"""B-08 acceptance: the ModelClient seam, driven through SDK-shaped stubs.

No test here touches the network: the real :class:`AnthropicModel` is exercised
against :class:`StubAnthropicClient`, whose streams look exactly like the
anthropic SDK's (context manager, ``text_stream``, ``get_final_message``), and
:class:`ScriptedModel` covers the loop-side contract. The locked call shape is
asserted literally: model ``claude-opus-5-5``, ``output_config={"effort": ...}``,
no ``thinking``, no ``tool_choice``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ngdesign.agent.model import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    MAX_TOKENS,
    AnthropicModel,
    ModelResponse,
    ModelSetupError,
    ScriptedModel,
    StubAnthropicClient,
    StubStream,
    ToolUseRequest,
)


def _sdk_message(
    *,
    text: str | None = None,
    tool_uses: tuple[tuple[str, str, dict[str, object]], ...] = (),
    stop_reason: str | None = "end_turn",
    input_tokens: int = 5,
    output_tokens: int = 7,
) -> SimpleNamespace:
    """An SDK final Message shaped stub: content blocks, stop_reason, usage."""
    blocks: list[SimpleNamespace] = []
    if text is not None:
        blocks.append(SimpleNamespace(type="text", text=text))
    blocks.extend(
        SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)
        for tool_id, name, tool_input in tool_uses
    )
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_anthropic_model_streams_text_and_parses_tool_use() -> None:
    client = StubAnthropicClient(
        [
            StubStream(
                ["Hello ", "world"],
                _sdk_message(
                    text="Hello world",
                    tool_uses=(("t1", "solve", {}),),
                    stop_reason="tool_use",
                    input_tokens=5,
                    output_tokens=7,
                ),
            )
        ]
    )
    model = AnthropicModel(client=client)
    deltas: list[str] = []
    response = model.stream("system prompt", [], [], deltas.append)

    assert deltas == ["Hello ", "world"]
    assert response.text == "Hello world"
    assert response.stop_reason == "tool_use"
    assert response.tool_uses == (ToolUseRequest(id="t1", name="solve", input={}),)
    assert (response.input_tokens, response.output_tokens) == (5, 7)

    # The locked call shape, asserted literally on what the client was given.
    kwargs = client.requests[0]
    assert kwargs["model"] == DEFAULT_MODEL
    assert kwargs["max_tokens"] == MAX_TOKENS
    assert kwargs["system"] == [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
    assert kwargs["output_config"] == {"effort": DEFAULT_EFFORT}
    assert "thinking" not in kwargs
    assert "tool_choice" not in kwargs


def test_anthropic_model_parses_a_text_only_end_turn() -> None:
    client = StubAnthropicClient([StubStream([], _sdk_message(text="All done."))])
    deltas: list[str] = []
    response = AnthropicModel(client=client).stream("s", [], [], deltas.append)

    assert deltas == []  # nothing streamed; the loop still shows the final text
    assert response.text == "All done."
    assert response.tool_uses == ()
    assert response.stop_reason == "end_turn"


def test_anthropic_model_passes_the_configured_model_and_effort() -> None:
    client = StubAnthropicClient([StubStream([], _sdk_message())])
    AnthropicModel(model="cla-opus-x", effort="low", client=client).stream("s", [], [], lambda _d: None)

    kwargs = client.requests[0]
    assert kwargs["model"] == "cla-opus-x"
    assert kwargs["output_config"] == {"effort": "low"}


def test_missing_api_key_raises_a_setup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ModelSetupError, match="ANTHROPIC_API_KEY"):
        AnthropicModel()


def test_explicit_client_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    model = AnthropicModel(client=StubAnthropicClient([StubStream([], _sdk_message())]))
    assert model.stream("s", [], [], lambda _d: None).stop_reason == "end_turn"


def test_scripted_model_records_calls_and_raises_when_exhausted() -> None:
    model = ScriptedModel(
        script=[
            ModelResponse(text="hi", tool_uses=(), stop_reason="end_turn", input_tokens=1, output_tokens=1)
        ]
    )
    deltas: list[str] = []
    response = model.stream("sys", [{"role": "user", "content": "build"}], [{"name": "solve"}], deltas.append)

    assert deltas == ["hi"]
    assert response.text == "hi"
    system, messages, tools = model.calls[0]
    assert system == "sys"
    assert messages == [{"role": "user", "content": "build"}]
    assert tools == [{"name": "solve"}]

    with pytest.raises(AssertionError, match="exhausted"):
        model.stream("sys", [], [], deltas.append)
